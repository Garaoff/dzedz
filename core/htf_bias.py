"""
HTF Bias — Bot SMC/ICT v2.

RÈGLE 1 : get_htf_bias() est la SEULE fonction qui calcule le biais HTF.
Aucune autre fonction ne doit déterminer le biais HTF.
RÈGLE 4 : Pas de seuils fixes. Paramètres depuis config.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging

import pandas as pd

from core.structure import detect_swings, determine_trend

logger = logging.getLogger(__name__)


def get_htf_bias(df_htf: pd.DataFrame) -> str:
    """
    Calcule le biais du timeframe supérieur.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui calcule le biais HTF.
    Aucune autre fonction ne doit déterminer le biais HTF.
    
    Algorithme :
    1. Détecter la structure sur HTF (swings)
    2. Déterminer la tendance (BOS/CHOCH)
    3. Confirmer avec la position du prix
    4. Résultat : "bullish" | "bearish" | "neutral"
    
    Args:
        df_htf: DataFrame du timeframe supérieur (H4, D1)
    
    Returns:
        "bullish", "bearish", ou "neutral"
    """
    if len(df_htf) < 5:
        logger.warning(f"HTF_BIAS | reason=insufficient_data | bars={len(df_htf)} | need=5")
        return "neutral"
    
    # 1. Détecter les swings sur HTF
    swings = detect_swings(df_htf)
    
    if not swings:
        logger.warning(f"HTF_BIAS | reason=no_swings | bars={len(df_htf)}")
        return "neutral"
    
    # 2. Déterminer la tendance basée sur la structure
    trend = determine_trend(swings)
    
    # 3. Confirmer avec la position du prix
    current_price = df_htf["close"].iloc[-1]
    
    # Trouver le dernier swing low et swing high
    confirmed_swings = [s for s in swings if s.confirmed]
    lows = [s for s in confirmed_swings if s.type == "swing_low"]
    highs = [s for s in confirmed_swings if s.type == "swing_high"]
    
    if lows and highs:
        last_low = max(lows, key=lambda s: s.index)
        last_high = max(highs, key=lambda s: s.index)
        
        above_low = current_price > last_low.price
        below_high = current_price < last_high.price
        
        # Conflit entre structure et position du prix
        if trend == "bullish" and not above_low:
            logger.warning(f"HTF_BIAS | conflict=structure_bullish_but_below_low | returning neutral")
            return "neutral"
        
        if trend == "bearish" and not below_high:
            logger.warning(f"HTF_BIAS | conflict=structure_bearish_but_above_high | returning neutral")
            return "neutral"
    
    logger.info(
        f"HTF_BIAS | bias={trend} | bars={len(df_htf)} | "
        f"swings={len(swings)} | price={current_price:.5f}"
    )
    
    return trend
