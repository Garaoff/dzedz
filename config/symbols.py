"""
Configuration des symboles — Bot SMC/ICT v2.

RÈGLE 1 : C'EST LA SEULE source de vérité pour les paramètres par symbole.
RÈGLE 4 : Chaque valeur est justifiée (STRUCTURAL ou DYNAMIC).

Les 3 symboles tradés :
  - XAUUSD (Or) — le plus important
  - NAS100 (NASDAQ Index)
  - BTCUSD (Bitcoin)

Chaque symbole a des caractéristiques UNIQUES :
  - pip_size : le plus petit incrément de prix significatif
  - contract_size : nombre d'unités par 1 lot standard (broker)
  - pip_value_per_lot : valeur en $ de 1 pip pour 1 lot standard
  - format broker : chaque broker a un format différent pour le même symbole

Formule de PnL : pnl = pips × pip_value_per_lot × lot
  où pips = (exit - entry) / pip_size

Formule de risque : risk_amount = sl_distance_pips × pip_value_per_lot × lot
  où sl_distance_pips = abs(entry - sl) / pip_size

Vérification :
  - XAUUSD : pips=50, pip_value=1.00, lot=0.1 → pnl = 50 × 1.00 × 0.1 = $5
    Vérifié : 0.1 lot = 10 oz, $0.50 move → 10 × $0.50 = $5 ✓
  - NAS100 : pips=10, pip_value=1.00, lot=1 → pnl = 10 × 1.00 × 1 = $10
    Vérifié : 1 contract × $10 move = $10 ✓
  - BTCUSD : pips=10000, pip_value=0.01, lot=0.1 → pnl = 10000 × 0.01 × 0.1 = $10
    Vérifié : 0.1 BTC × $100 move = $10 ✓
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolConfig:
    """
    Configuration complète d'un symbole de trading.
    
    RÈGLE 1 : C'EST LE SEUL endroit qui définit ces paramètres.
    RÈGLE 4 : Toutes les valeurs sont justifiées.
    """
    name: str               # Nom interne : XAUUSD, NAS100, BTCUSD
    pip_size: float         # STRUCTURAL: plus petit incrément de prix (ex: 0.01 pour XAUUSD)
    contract_size: float    # STRUCTURAL: unités par 1 lot standard (OANDA: 1 lot = contract_size units)
    pip_value_per_lot: float  # STRUCTURAL: valeur $ de 1 pip par 1 lot standard
    oanda_format: str       # STRUCTURAL: format OANDA (underscore)
    mt5_format: str         # STRUCTURAL: format MT5 (pas d'underscore)
    ccxt_format: Optional[str]  # STRUCTURAL: format CCXT (slash) ou None si CFD
    min_lot: float          # STRUCTURAL: taille minimum de lot broker
    available_brokers: list  # STRUCTURAL: brokers qui supportent ce symbole
    
    def get_broker_format(self, broker_type: str) -> Optional[str]:
        """
        Retourne le format du symbole pour le broker donné.
        
        RÈGLE 1 : C'EST LA SEULE fonction de conversion de format.
        
        Returns None si le symbole n'est pas disponible sur ce broker.
        """
        if broker_type == "oanda":
            return self.oanda_format
        elif broker_type == "mt5":
            return self.mt5_format
        elif broker_type == "ccxt":
            return self.ccxt_format  # None si CFD (XAUUSD, NAS100)
        else:
            logger.error(f"SYMBOL_FORMAT | reason=unknown_broker | broker={broker_type}")
            return self.name
    
    def calculate_pnl(self, entry: float, exit_price: float, lot: float, is_long: bool) -> float:
        """
        Calcule le PnL en dollars pour ce symbole.
        
        RÈGLE 1 : C'EST LA SEULE fonction de calcul de PnL par symbole.
        Formule : pnl = pips × pip_value_per_lot × lot × direction
        
        Args:
            entry: Prix d'entrée
            exit_price: Prix de sortie
            lot: Taille de position en lots
            is_long: True si position longue
        
        Returns:
            PnL en dollars
        """
        if is_long:
            pips = (exit_price - entry) / self.pip_size
        else:
            pips = (entry - exit_price) / self.pip_size
        
        pnl = pips * self.pip_value_per_lot * lot
        return pnl
    
    def calculate_pips(self, price_distance: float) -> float:
        """
        Convertit une distance en prix en nombre de pips.
        
        RÈGLE 1 : C'EST LA SEULE fonction de conversion prix→pips.
        """
        return abs(price_distance) / self.pip_size
    
    def calculate_risk_amount(self, sl_distance_price: float, lot: float) -> float:
        """
        Calcule le montant risqué en dollars.
        
        Formule : risk = sl_pips × pip_value_per_lot × lot
        
        Args:
            sl_distance_price: Distance SL en prix (abs(entry - sl))
            lot: Taille de position en lots
        """
        sl_pips = self.calculate_pips(sl_distance_price)
        return sl_pips * self.pip_value_per_lot * lot
    
    def calculate_lot_for_risk(self, risk_amount: float, sl_distance_price: float) -> float:
        """
        Calcule le lot nécessaire pour risquer un montant donné.
        
        Formule : lot = risk_amount / (sl_pips × pip_value_per_lot)
        
        Args:
            risk_amount: Montant à risquer en $
            sl_distance_price: Distance SL en prix
        """
        sl_pips = self.calculate_pips(sl_distance_price)
        if sl_pips <= 0 or self.pip_value_per_lot <= 0:
            return 0
        return risk_amount / (sl_pips * self.pip_value_per_lot)
    
    def calculate_units_for_broker(self, lot: float, broker_type: str) -> float:
        """
        Calcule le nombre d'unités à envoyer au broker.
        
        OANDA : units = lot × contract_size
        MT5 : volume = lot (MT5 gère le contract_size lui-même)
        CCXT : amount = lot × contract_size (en unités de base)
        
        RÈGLE 1 : C'EST LA SEULE fonction de conversion lot→units.
        """
        if broker_type == "oanda":
            return lot * self.contract_size
        elif broker_type == "mt5":
            return lot  # MT5 gère contract_size via le broker
        elif broker_type == "ccxt":
            return lot * self.contract_size
        else:
            logger.error(f"SYMBOL_UNITS | reason=unknown_broker | broker={broker_type}")
            return lot * self.contract_size


# =============================================================================
# SYMBOLES — RÈGLE 1 : source unique de vérité
# =============================================================================

SYMBOLS: dict[str, SymbolConfig] = {
    "XAUUSD": SymbolConfig(
        name="XAUUSD",
        # STRUCTURAL: Or — prix en 2 décimales (ex: 1950.50)
        # Le plus petit incrément = $0.01 = 1 pip
        pip_size=0.01,
        # STRUCTURAL: 1 lot standard = 100 oz (convention OANDA/MT5)
        # OANDA: 1 unit = 1 oz, 1 lot = 100 units
        contract_size=100,
        # DYNAMIC: pip_value_per_lot = pip_size × contract_size = 0.01 × 100 = $1.00
        # Vérifié : 100 oz × $0.01/oz = $1.00 per pip per lot
        pip_value_per_lot=1.00,
        # STRUCTURAL: OANDA format = XAU_USD (underscore)
        oanda_format="XAU_USD",
        # STRUCTURAL: MT5 format = XAUUSD (pas underscore)
        mt5_format="XAUUSD",
        # STRUCTURAL: Pas de spot crypto pour l'or — CFD uniquement
        ccxt_format=None,
        # STRUCTURAL: minimum broker pour XAUUSD — 0.01 lot = 1 oz
        min_lot=0.01,
        # STRUCTURAL: CFD disponible sur OANDA et MT5, pas sur CCXT
        available_brokers=["oanda", "mt5"],
    ),
    
    "NAS100": SymbolConfig(
        name="NAS100",
        # STRUCTURAL: NASDAQ Index — prix en entier (ex: 19500)
        # Le plus petit incrément = 1.0 = 1 point = 1 pip
        pip_size=1.0,
        # STRUCTURAL: 1 lot = 1 contract unit (OANDA NAS100 contract)
        # OANDA: 1 unit = 1 contract, valeur ~$1 per 1-point move
        contract_size=1,
        # DYNAMIC: pip_value_per_lot = pip_size × contract_size = 1.0 × 1 = $1.00
        # Vérifié : 1 contract × $1.00/point = $1.00 per pip per lot
        pip_value_per_lot=1.00,
        # STRUCTURAL: OANDA format = NAS100_USD
        oanda_format="NAS100_USD",
        # STRUCTURAL: MT5 format = NAS100
        mt5_format="NAS100",
        # STRUCTURAL: Pas de spot crypto pour un index — CFD uniquement
        ccxt_format=None,
        # STRUCTURAL: minimum broker pour NAS100
        min_lot=0.01,
        # STRUCTURAL: CFD disponible sur OANDA et MT5
        available_brokers=["oanda", "mt5"],
    ),
    
    "BTCUSD": SymbolConfig(
        name="BTCUSD",
        # STRUCTURAL: Bitcoin — prix en 2 décimales (ex: 65000.00)
        # Le plus petit incrément = $0.01 = 1 pip
        pip_size=0.01,
        # STRUCTURAL: 1 lot = 1 BTC (OANDA: 1 unit = 1 BTC)
        # Sur CCXT exchanges, on trade en BTC (unité de base)
        contract_size=1,
        # DYNAMIC: pip_value_per_lot = pip_size × contract_size = 0.01 × 1 = $0.01
        # Vérifié : 1 BTC × $0.01 move = $0.01 per pip per lot
        # ATTENTION: pip_value très petit → les SL en pips sont très grands
        # Un SL de $100 = 10000 pips × $0.01 = $100 risque pour 1 lot = 1 BTC
        pip_value_per_lot=0.01,
        # STRUCTURAL: OANDA format = BTC_USD
        oanda_format="BTC_USD",
        # STRUCTURAL: MT5 format = BTCUSD
        mt5_format="BTCUSD",
        # STRUCTURAL: CCXT format = BTC/USDT (Binance, Bybit, etc.)
        ccxt_format="BTC/USDT",
        # STRUCTURAL: minimum pour crypto — 0.001 lot = 0.001 BTC
        min_lot=0.001,
        # STRUCTURAL: Crypto disponible sur OANDA, MT5 (CFD) et CCXT (spot)
        available_brokers=["oanda", "mt5", "ccxt"],
    ),
}


# =============================================================================
# FONCTIONS D'ACCÈS — RÈGLE 1 : interface unique
# =============================================================================

def get_symbol_config(symbol_name: str) -> SymbolConfig:
    """
    RÈGLE 1 : C'EST LA SEULE fonction pour obtenir la config d'un symbole.
    
    Args:
        symbol_name: Nom interne du symbole (XAUUSD, NAS100, BTCUSD)
    
    Returns:
        SymbolConfig pour le symbole
    
    Raises:
        ValueError: Si le symbole n'est pas supporté
    """
    config = SYMBOLS.get(symbol_name)
    if config is None:
        supported = list(SYMBOLS.keys())
        logger.error(f"SYMBOL_CONFIG | reason=symbol_not_found | symbol={symbol_name} | supported={supported}")
        raise ValueError(f"Symbole non supporté: {symbol_name}. Symboles disponibles: {supported}")
    return config


def get_all_symbol_names() -> list[str]:
    """Retourne la liste de tous les symboles configurés."""
    return list(SYMBOLS.keys())


def get_pip_size(symbol_name: str) -> float:
    """RÈGLE 1 : Seule fonction pour obtenir le pip_size d'un symbole."""
    return get_symbol_config(symbol_name).pip_size


def get_pip_value_per_lot(symbol_name: str) -> float:
    """RÈGLE 1 : Seule fonction pour obtenir le pip_value d'un symbole."""
    return get_symbol_config(symbol_name).pip_value_per_lot


def get_contract_size(symbol_name: str) -> float:
    """RÈGLE 1 : Seule fonction pour obtenir le contract_size d'un symbole."""
    return get_symbol_config(symbol_name).contract_size


def get_broker_format(symbol_name: str, broker_type: str) -> Optional[str]:
    """RÈGLE 1 : Seule fonction pour obtenir le format broker d'un symbole. Retourne None si non disponible."""
    return get_symbol_config(symbol_name).get_broker_format(broker_type)


def get_min_lot(symbol_name: str) -> float:
    """RÈGLE 1 : Seule fonction pour obtenir le min_lot d'un symbole."""
    return get_symbol_config(symbol_name).min_lot


def is_symbol_available_on_broker(symbol_name: str, broker_type: str) -> bool:
    """Vérifie si un symbole est tradable sur un broker donné."""
    config = get_symbol_config(symbol_name)
    return broker_type in config.available_brokers
