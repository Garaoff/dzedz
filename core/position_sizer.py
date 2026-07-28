"""
Calcul de taille de position — Bot SMC/ICT v2.

RÈGLE 1 : C'EST LA SEULE fonction qui calcule la taille de position.
RÈGLE 4 : Pas de valeurs fixes sans justification.
RÈGLE 5 : Le lot calculé est soumis à validate_risk(), pas exempté.

RÈGLE 1 : Les paramètres par symbole viennent de config/symbols.py.
"""

import logging
from config.params import MAX_RISK_PER_TRADE_PCT
from config.symbols import get_symbol_config, get_pip_value_per_lot, get_pip_size

logger = logging.getLogger(__name__)

# STRUCTURAL: 100 pour conversion pourcentage — mathématique, pas arbitraire
PCT_FACTOR = 100


def calculate_position_size(
    capital: float,
    entry_price: float,
    sl_price: float,
    symbol: str = "XAUUSD",
    risk_pct: float = MAX_RISK_PER_TRADE_PCT,
) -> float:
    """
    Calcule la taille de position en lots pour un symbole donné.
    
    RÈGLE 1 : Seule fonction de calcul de taille de position.
    RÈGLE 5 : Le résultat EST soumis à validate_risk() dans order_executor.
    
    Formule : lot = risk_amount / (sl_pips × pip_value_per_lot)
    où sl_pips = abs(entry - sl) / pip_size
    
    Args:
        capital: Capital disponible
        entry_price: Prix d'entrée
        sl_price: Prix du stop-loss
        symbol: Symbole tradé (XAUUSD, NAS100, BTCUSD) — RÈGLE 1: source unique dans config/symbols.py
        risk_pct: Pourcentage du capital à risquer (défaut: depuis config)
    
    Returns:
        Taille de position en lots
    """
    if capital <= 0:
        logger.error(f"POSITION_SIZE | reason=capital_invalid | capital={capital} | symbol={symbol}")
        raise ValueError(f"Capital invalide: {capital}")
    
    if entry_price <= 0 or sl_price <= 0:
        logger.error(f"POSITION_SIZE | reason=price_invalid | entry={entry_price} | sl={sl_price} | symbol={symbol}")
        raise ValueError(f"Prix invalide: entry={entry_price}, sl={sl_price}")
    
    # RÈGLE 1 : Obtenir les paramètres par symbole depuis la source unique
    pip_size = get_pip_size(symbol)
    pip_value = get_pip_value_per_lot(symbol)
    
    risk_amount = capital * (risk_pct / PCT_FACTOR)  # STRUCTURAL: 100 pour conversion pct
    sl_distance = abs(entry_price - sl_price)
    sl_distance_pips = sl_distance / pip_size
    
    if sl_distance_pips <= 0:
        logger.error(f"POSITION_SIZE | reason=sl_distance_zero | entry={entry_price} | sl={sl_price} | symbol={symbol}")
        raise ValueError("Distance SL nulle")
    
    # Calcul du lot
    lot_size = risk_amount / (sl_distance_pips * pip_value)
    
    logger.info(
        f"POSITION_SIZE | symbol={symbol} | capital={capital} | risk_pct={risk_pct}% | "
        f"risk_amount={risk_amount:.2f} | sl_distance_pips={sl_distance_pips:.1f} | "
        f"pip_size={pip_size} | pip_value={pip_value} | lot={lot_size:.4f}"
    )
    
    return lot_size
