"""
Calcul de taille de position — Bot SMC/ICT v2.

RÈGLE 1 : C'EST LA SEULE fonction qui calcule la taille de position.
RÈGLE 4 : Pas de valeurs fixes sans justification.
RÈGLE 5 : Le lot calculé est soumis à validate_risk(), pas exempté.
"""

import logging
from config.params import MAX_RISK_PER_TRADE_PCT

logger = logging.getLogger(__name__)

# STRUCTURAL: 100 pour conversion pourcentage — mathématique, pas arbitraire
PCT_FACTOR = 100


def calculate_position_size(
    capital: float,
    entry_price: float,
    sl_price: float,
    risk_pct: float = MAX_RISK_PER_TRADE_PCT,
    pip_value: float = 10.0,  # STRUCTURAL: valeur par pip par lot standard — dépend du symbole
) -> float:
    """
    Calcule la taille de position en lots.
    
    RÈGLE 1 : Seule fonction de calcul de taille de position.
    RÈGLE 5 : Le résultat EST soumis à validate_risk() dans order_executor.
    Le lot minimum forcé, s'il est appliqué, passe aussi par validate_risk().
    
    Args:
        capital: Capital disponible
        entry_price: Prix d'entrée
        sl_price: Prix du stop-loss
        risk_pct: Pourcentage du capital à risquer (défaut: depuis config)
        pip_value: Valeur par pip par lot (dépend du symbole)
    
    Returns:
        Taille de position en lots
    """
    if capital <= 0:
        logger.error(f"POSITION_SIZE | reason=capital_invalid | capital={capital}")
        raise ValueError(f"Capital invalide: {capital}")
    
    if entry_price <= 0 or sl_price <= 0:
        logger.error(f"POSITION_SIZE | reason=price_invalid | entry={entry_price} | sl={sl_price}")
        raise ValueError(f"Prix invalide: entry={entry_price}, sl={sl_price}")
    
    risk_amount = capital * (risk_pct / PCT_FACTOR)  # STRUCTURAL: 100 pour conversion pct
    sl_distance = abs(entry_price - sl_price)
    
    if sl_distance <= 0:
        logger.error(f"POSITION_SIZE | reason=sl_distance_zero | entry={entry_price} | sl={sl_price}")
        raise ValueError("Distance SL nulle")
    
    # Calcul du lot
    lot_size = risk_amount / (sl_distance * pip_value)
    
    logger.info(
        f"POSITION_SIZE | capital={capital} | risk_pct={risk_pct}% | "
        f"risk_amount={risk_amount:.2f} | sl_distance={sl_distance:.5f} | "
        f"lot={lot_size:.4f}"
    )
    
    return lot_size
