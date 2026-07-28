"""
Displacement measurement — Bot SMC/ICT v2.

RÈGLE 1 : measure_displacement() est la SEULE fonction.
RÈGLE 4 : DISPLACEMENT_MIN_ATR depuis config.
"""

import logging

import pandas as pd

from config.params import DISPLACEMENT_MIN_ATR, ATR_PERIOD

logger = logging.getLogger(__name__)


def measure_displacement(df: pd.DataFrame, index: int) -> dict:
    """
    Mesure le displacement d'une bougie.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui mesure le displacement.
    
    Le displacement est un mouvement de prix fort et rapide qui indique
    la participation institutionnelle. C'est le mouvement qui CRÉE les
    FVG et les Order Blocks.
    
    Calcul :
      body_size = |close - open|
      displacement_atr = body_size / ATR
      direction = "bullish" if close > open, "bearish" if close < open
      is_significant = displacement_atr >= DISPLACEMENT_MIN_ATR
    
    Args:
        df: DataFrame OHLCV
        index: Index de la bougie
    
    Returns:
        dict avec displacement_atr, direction, is_significant
    """
    if index < 0 or index >= len(df):
        logger.warning(f"DISPLACEMENT | reason=index_out_of_range | index={index}")
        return {"displacement_atr": 0, "direction": "neutral", "is_significant": False}
    
    current_open = df["open"].iloc[index]
    current_close = df["close"].iloc[index]
    
    # Calcul du body size
    body_size = abs(current_close - current_open)
    
    # Calcul de l'ATR
    atr = _calculate_atr_at(df, index)
    
    # Displacement en multiples d'ATR (DYNAMIC)
    displacement_atr = body_size / atr if atr > 0 else 0
    
    # Direction
    if current_close > current_open:
        direction = "bullish"
    elif current_close < current_open:
        direction = "bearish"
    else:
        direction = "neutral"
    
    # Significance (DYNAMIC threshold from config)
    is_significant = displacement_atr >= DISPLACEMENT_MIN_ATR
    
    logger.debug(
        f"DISPLACEMENT | index={index} | displacement_atr={displacement_atr:.2f} | "
        f"direction={direction} | significant={is_significant}"
    )
    
    return {
        "displacement_atr": displacement_atr,
        "direction": direction,
        "is_significant": is_significant,
    }


def _calculate_atr_at(df: pd.DataFrame, index: int) -> float:
    """Calcul de l'ATR à un index donné."""
    period = ATR_PERIOD  # STRUCTURAL
    
    start = max(0, index - period + 1)
    if start >= index:
        return 0.0001  # STRUCTURAL: fallback
    
    subset = df.iloc[start:index + 1]
    
    high = subset["high"]
    low = subset["low"]
    close_prev = subset["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.mean()
    
    return float(atr) if not pd.isna(atr) else 0.0001  # STRUCTURAL: fallback
