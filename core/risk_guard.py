"""
Vérification de risque — Bot SMC/ICT v2.

RÈGLE 5 : Un seul verrou, jamais de bypass.
Ce fichier est le SEUL endroit où le risque est vérifié avant l'envoi d'un ordre.
Aucune catégorie de setup ne peut contourner validate_risk().

RÈGLE 6 : Jamais d'échec silencieux.
Toute exception est loguée avec son message complet.

RÈGLE 1 : Les paramètres par symbole (pip_size, pip_value) viennent
de config/symbols.py — la source unique de vérité.
"""

import logging
from config.risk_config import get_max_risk_pct, get_absolute_max_risk_pct, get_min_lot_size
from config.symbols import get_symbol_config, SymbolConfig

logger = logging.getLogger(__name__)


class RiskValidationError(Exception):
    """Exception levée quand un ordre ne passe pas la vérification de risque."""
    pass


def validate_risk(
    capital: float,
    entry_price: float,
    sl_price: float,
    lot_size: float,
    setup_grade: str = "",
    symbol: str = "",
    pip_size: float = 0.0001,    # STRUCTURAL: fallback si symbol non fourni — legacy EURUSD
    pip_value_per_lot: float = 10.0,  # STRUCTURAL: fallback si symbol non fourni — legacy EURUSD
) -> float:
    """
    Vérifie que le risque de l'ordre est dans les limites acceptables.
    
    C'EST LE SEUL POINT DE PASSAGE. Aucun ordre ne doit être envoyé sans
    passer par cette fonction.
    
    RÈGLE 1 : Les paramètres pip_size et pip_value_per_lot sont obtenus
    via config/symbols.py si le symbole est fourni. Sinon, les fallbacks
    legacy EURUSD sont utilisés (pour compatibilité tests existants).
    
    Args:
        capital: Capital disponible
        entry_price: Prix d'entrée
        sl_price: Prix du stop-loss
        lot_size: Taille de la position en lots
        setup_grade: Grade du setup (ignoré pour le risque — RÈGLE 5)
        symbol: Symbole tradé (XAUUSD, NAS100, BTCUSD) — pour obtenir les params
        pip_size: Fallback — pip_size si symbol non fourni
        pip_value_per_lot: Fallback — pip_value si symbol non fourni
    
    Returns:
        Le lot_size validé (peut être réduit si le risque est trop élevé)
    
    Raises:
        RiskValidationError: Si l'ordre ne peut pas être validé même avec le lot minimum
    """
    # RÈGLE 1 : Obtenir les paramètres par symbole si fourni
    if symbol:
        try:
            sym_config = get_symbol_config(symbol)
            pip_size = sym_config.pip_size
            pip_value_per_lot = sym_config.pip_value_per_lot
        except ValueError:
            logger.warning(f"RISK_FALLBACK | reason=symbol_not_found | symbol={symbol} | using_fallback_pip_values")
    
    if capital <= 0:
        logger.error(f"RISK_REJECT | reason=capital_invalid | capital={capital} | symbol={symbol}")
        raise RiskValidationError(f"Capital invalide: {capital}")
    
    if entry_price <= 0 or sl_price <= 0:
        logger.error(f"RISK_REJECT | reason=price_invalid | entry={entry_price} | sl={sl_price} | symbol={symbol}")
        raise RiskValidationError(f"Prix invalide: entry={entry_price}, sl={sl_price}")
    
    # Calcul du risque en pourcentage du capital
    # STRUCTURAL: 100 pour conversion pourcentage — mathématique, pas arbitraire
    PCT_FACTOR = 100  # STRUCTURAL: conversion fraction → pourcentage
    
    sl_distance_pips = abs(entry_price - sl_price) / pip_size  # DYNAMIC: conversion en pips via pip_size du symbole
    total_risk = sl_distance_pips * pip_value_per_lot * lot_size  # DYNAMIC: risk = pips × pip_value × lot
    risk_pct = (total_risk / capital) * PCT_FACTOR
    
    max_risk = get_max_risk_pct()
    absolute_max = get_absolute_max_risk_pct()
    min_lot = get_min_lot_size()
    
    # Note: setup_grade est intentionnellement IGNORÉ — Règle 5
    # Aucun bypass possible, même pour les setups "Grade S"
    
    if risk_pct > absolute_max:
        logger.error(
            f"RISK_REJECT | reason=absolute_max_exceeded | "
            f"risk_pct={risk_pct:.2f}% | absolute_max={absolute_max}% | "
            f"symbol={symbol} | grade={setup_grade} | "
            f"sl_pips={sl_distance_pips:.1f} | pip_value={pip_value_per_lot} | pip_size={pip_size}"
        )
        raise RiskValidationError(
            f"Risque absolu dépassé: {risk_pct:.2f}% > {absolute_max}% "
            f"(symbol={symbol}, grade={setup_grade})"
        )
    
    if risk_pct > max_risk:
        # Tenter de réduire le lot size
        max_allowed_risk_amount = capital * (max_risk / PCT_FACTOR)
        adjusted_lot = max_allowed_risk_amount / (sl_distance_pips * pip_value_per_lot) if sl_distance_pips > 0 else 0
        
        if adjusted_lot < min_lot:
            logger.error(
                f"RISK_REJECT | reason=lot_below_minimum | "
                f"adjusted_lot={adjusted_lot:.4f} | min_lot={min_lot} | "
                f"symbol={symbol} | grade={setup_grade}"
            )
            raise RiskValidationError(
                f"Lot minimum forcé ne passe pas la vérification de risque: "
                f"adjusted={adjusted_lot:.4f} < min={min_lot} "
                f"(symbol={symbol}, grade={setup_grade})"
            )
        
        logger.warning(
            f"RISK_ADJUST | before_lot={lot_size} | after_lot={adjusted_lot:.4f} | "
            f"risk_pct={risk_pct:.2f}% -> {max_risk}% | "
            f"reason=exceeds_max_risk | symbol={symbol} | pip_value={pip_value_per_lot}"
        )
        return adjusted_lot
    
    logger.info(
        f"RISK_OK | lot={lot_size} | risk_pct={risk_pct:.2f}% | "
        f"max={max_risk}% | symbol={symbol} | grade={setup_grade} | "
        f"sl_pips={sl_distance_pips:.1f} | pip_value={pip_value_per_lot}"
    )
    return lot_size
