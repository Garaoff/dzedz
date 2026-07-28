"""
Structure de marché — Swings, BOS, CHOCH, MSS.

RÈGLE 1 : detect_swings(), detect_bos(), detect_choch() sont les SEULES
fonctions pour ces concepts.
RÈGLE 3 : Transition, pas état. Tout signal se déclenche sur TRANSITION.
RÈGLE 4 : Pas de seuils fixes sans justification. Paramètres depuis config.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np

from config.params import (
    SWING_LOOKBACK,
    SWING_CONFIRM_BARS,
    BOS_CONFIRMATION_CLOSE,
    CHOCH_CONFIRMATION_CLOSE,
    DISPLACEMENT_MIN_ATR,
    ATR_PERIOD,
)
from core.signal_types import SignalType

logger = logging.getLogger(__name__)


# =============================================================================
# Types de données
# =============================================================================

@dataclass
class Swing:
    """Niveau de swing (structure de marché)."""
    type: str  # "swing_high" or "swing_low"
    price: float
    index: int
    timestamp: pd.Timestamp
    confirmed: bool = False
    
    def __post_init__(self):
        if self.type not in ("swing_high", "swing_low"):
            raise ValueError(f"Type de swing invalide: {self.type}")
        if self.price <= 0:
            raise ValueError(f"Prix de swing invalide: {self.price}")


@dataclass
class StructureBreak:
    """Cassure de structure (BOS ou CHOCH)."""
    type: str  # "bos_bull", "bos_bear", "choch_bull", "choch_bear"
    broken_swing: Swing
    break_price: float
    break_index: int
    displacement_atr: float  # DYNAMIC: force du mouvement qui casse
    
    @property
    def signal_type(self) -> SignalType:
        mapping = {
            "bos_bull": SignalType.BOS_BULL,
            "bos_bear": SignalType.BOS_BEAR,
            "choch_bull": SignalType.CHOCH_BULL,
            "choch_bear": SignalType.CHOCH_BEAR,
        }
        return mapping.get(self.type, SignalType.FVG_BULL)


# =============================================================================
# Détection des swings
# =============================================================================

def detect_swings(df: pd.DataFrame) -> list[Swing]:
    """
    Détecte tous les swings (highs et lows) dans les données.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte les swings.
    Les swings sont utilisés par BOS, CHOCH, liquidity, zones.
    
    Algorithme :
    - Un swing high est un high[i] qui est le maximum dans une fenêtre
      de SWING_LOOKBACK bougies de chaque côté
    - Un swing low est un low[i] qui est le minimum dans une fenêtre
      de SWING_LOOKBACK bougies de chaque côté
    
    Args:
        df: DataFrame OHLCV
    
    Returns:
        Liste de swings détectés, triés par index
    """
    swings = []
    lookback = SWING_LOOKBACK  # STRUCTURAL: justifié dans params
    
    if len(df) < lookback * 2 + 1:
        logger.warning(f"SWING_DETECT | reason=insufficient_data | bars={len(df)} | need={lookback*2+1}")
        return swings
    
    for i in range(lookback, len(df) - lookback):
        # Swing High : high[i] > tous les highs dans la fenêtre
        window_highs = df["high"].iloc[i - lookback : i + lookback + 1]
        is_swing_high = df["high"].iloc[i] == window_highs.max()
        
        # Swing Low : low[i] < tous les lows dans la fenêtre
        window_lows = df["low"].iloc[i - lookback : i + lookback + 1]
        is_swing_low = df["low"].iloc[i] == window_lows.min()
        
        if is_swing_high:
            swing = Swing(
                type="swing_high",
                price=df["high"].iloc[i],
                index=i,
                timestamp=df.index[i],
                confirmed=_check_swing_confirmation(df, i, "swing_high", SWING_CONFIRM_BARS),
            )
            swings.append(swing)
            logger.debug(f"SWING_HIGH | index={i} | price={swing.price:.5f} | confirmed={swing.confirmed}")
        
        elif is_swing_low:
            swing = Swing(
                type="swing_low",
                price=df["low"].iloc[i],
                index=i,
                timestamp=df.index[i],
                confirmed=_check_swing_confirmation(df, i, "swing_low", SWING_CONFIRM_BARS),
            )
            swings.append(swing)
            logger.debug(f"SWING_LOW | index={i} | price={swing.price:.5f} | confirmed={swing.confirmed}")
    
    # Trier par index
    swings.sort(key=lambda s: s.index)
    
    logger.info(
        f"SWING_DETECT_COMPLETE | total={len(swings)} | "
        f"highs={sum(1 for s in swings if s.type == 'swing_high')} | "
        f"lows={sum(1 for s in swings if s.type == 'swing_low')} | "
        f"confirmed={sum(1 for s in swings if s.confirmed)}"
    )
    
    return swings


def _check_swing_confirmation(
    df: pd.DataFrame,
    index: int,
    swing_type: str,
    confirm_bars: int,
) -> bool:
    """
    Vérifie qu'un swing est confirmé (pas de dépassement dans les N bougies suivantes).
    
    STRUCTURAL: confirm_bars est dans params.py avec justification.
    """
    future_end = min(index + confirm_bars + 1, len(df))
    
    if future_end <= index + 1:
        return False  # Pas assez de données futures
    
    future_data = df.iloc[index + 1 : future_end]
    
    if swing_type == "swing_high":
        # Confirmé si aucun high futur dépasse le swing
        return future_data["high"].max() <= df["high"].iloc[index]
    elif swing_type == "swing_low":
        # Confirmé si aucun low futur est en-dessous du swing
        return future_data["low"].min() >= df["low"].iloc[index]
    
    return False


# =============================================================================
# Détection BOS (Break of Structure — continuation)
# =============================================================================

def detect_bos(
    df: pd.DataFrame,
    swings: list[Swing],
    current_trend: str,
) -> Optional[StructureBreak]:
    """
    Détecte un BOS (Break of Structure) — continuation de la tendance.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte le BOS.
    RÈGLE 3 : Le BOS est détecté au moment de la TRANSITION (casse).
    
    BOS_BULL : close casse le dernier swing high (continuation haussière)
    BOS_BEAR : close casse le dernier swing low (continuation baissière)
    
    Args:
        df: DataFrame OHLCV
        swings: Liste des swings détectés
        current_trend: "bullish" ou "bearish" ou "neutral"
    
    Returns:
        StructureBreak si BOS détecté, None sinon
    """
    if len(df) < 2:
        return None
    
    current_idx = len(df) - 1
    previous_idx = current_idx - 1
    
    if current_trend == "bullish" or current_trend == "neutral":
        # BOS Bull : close casse le dernier swing high confirmé
        last_swing_high = _find_last_confirmed_swing(swings, "swing_high", current_idx)
        if last_swing_high is not None:
            current_close = df["close"].iloc[current_idx]
            prev_close = df["close"].iloc[previous_idx]
            
            # RÈGLE 3 : TRANSITION — close passe au-dessus à cette bougie, pas la précédente
            if BOS_CONFIRMATION_CLOSE:  # STRUCTURAL: confirmé sur clôture
                condition_now = current_close > last_swing_high.price
                condition_prev = prev_close > last_swing_high.price
            else:
                condition_now = df["high"].iloc[current_idx] > last_swing_high.price
                condition_prev = df["high"].iloc[previous_idx] > last_swing_high.price
            
            if condition_now and not condition_prev:
                # TRANSITION détectée — BOS Bull
                displacement = _calculate_displacement_atr(df, current_idx)
                
                bos = StructureBreak(
                    type="bos_bull",
                    broken_swing=last_swing_high,
                    break_price=current_close,
                    break_index=current_idx,
                    displacement_atr=displacement,
                )
                
                logger.info(
                    f"BOS_BULL | index={current_idx} | break_price={current_close:.5f} | "
                    f"swing_price={last_swing_high.price:.5f} | displacement_atr={displacement:.2f}"
                )
                return bos
    
    if current_trend == "bearish" or current_trend == "neutral":
        # BOS Bear : close casse le dernier swing low confirmé
        last_swing_low = _find_last_confirmed_swing(swings, "swing_low", current_idx)
        if last_swing_low is not None:
            current_close = df["close"].iloc[current_idx]
            prev_close = df["close"].iloc[previous_idx]
            
            if BOS_CONFIRMATION_CLOSE:
                condition_now = current_close < last_swing_low.price
                condition_prev = prev_close < last_swing_low.price
            else:
                condition_now = df["low"].iloc[current_idx] < last_swing_low.price
                condition_prev = df["low"].iloc[previous_idx] < last_swing_low.price
            
            if condition_now and not condition_prev:
                displacement = _calculate_displacement_atr(df, current_idx)
                
                bos = StructureBreak(
                    type="bos_bear",
                    broken_swing=last_swing_low,
                    break_price=current_close,
                    break_index=current_idx,
                    displacement_atr=displacement,
                )
                
                logger.info(
                    f"BOS_BEAR | index={current_idx} | break_price={current_close:.5f} | "
                    f"swing_price={last_swing_low.price:.5f} | displacement_atr={displacement:.2f}"
                )
                return bos
    
    return None


# =============================================================================
# Détection CHOCH (Change of Character — retournement)
# =============================================================================

def detect_choch(
    df: pd.DataFrame,
    swings: list[Swing],
    current_trend: str,
) -> Optional[StructureBreak]:
    """
    Détecte un CHOCH (Change of Character) — retournement de tendance.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte le CHOCH.
    RÈGLE 3 : Le CHOCH est détecté au moment de la TRANSITION.
    
    CHOCH_BULL : close casse le dernier swing high alors qu'on était bearish
    CHOCH_BEAR : close casse le dernier swing low alors qu'on était bullish
    
    Args:
        df: DataFrame OHLCV
        swings: Liste des swings détectés
        current_trend: "bullish" ou "bearish" ou "neutral"
    
    Returns:
        StructureBreak si CHOCH détecté, None sinon
    """
    if len(df) < 2:
        return None
    
    current_idx = len(df) - 1
    previous_idx = current_idx - 1
    
    # CHOCH Bull : retournement de bearish → bullish
    # Close casse un swing high alors que la tendance était bearish
    if current_trend == "bearish":
        last_swing_high = _find_last_confirmed_swing(swings, "swing_high", current_idx)
        if last_swing_high is not None:
            current_close = df["close"].iloc[current_idx]
            prev_close = df["close"].iloc[previous_idx]
            
            if CHOCH_CONFIRMATION_CLOSE:
                condition_now = current_close > last_swing_high.price
                condition_prev = prev_close > last_swing_high.price
            else:
                condition_now = df["high"].iloc[current_idx] > last_swing_high.price
                condition_prev = df["high"].iloc[previous_idx] > last_swing_high.price
            
            if condition_now and not condition_prev:
                displacement = _calculate_displacement_atr(df, current_idx)
                
                choch = StructureBreak(
                    type="choch_bull",
                    broken_swing=last_swing_high,
                    break_price=current_close,
                    break_index=current_idx,
                    displacement_atr=displacement,
                )
                
                logger.info(
                    f"CHOCH_BULL | index={current_idx} | break_price={current_close:.5f} | "
                    f"swing_price={last_swing_high.price:.5f} | displacement_atr={displacement:.2f} | "
                    f"previous_trend=bearish"
                )
                return choch
    
    # CHOCH Bear : retournement de bullish → bearish
    if current_trend == "bullish":
        last_swing_low = _find_last_confirmed_swing(swings, "swing_low", current_idx)
        if last_swing_low is not None:
            current_close = df["close"].iloc[current_idx]
            prev_close = df["close"].iloc[previous_idx]
            
            if CHOCH_CONFIRMATION_CLOSE:
                condition_now = current_close < last_swing_low.price
                condition_prev = prev_close < last_swing_low.price
            else:
                condition_now = df["low"].iloc[current_idx] < last_swing_low.price
                condition_prev = df["low"].iloc[previous_idx] < last_swing_low.price
            
            if condition_now and not condition_prev:
                displacement = _calculate_displacement_atr(df, current_idx)
                
                choch = StructureBreak(
                    type="choch_bear",
                    broken_swing=last_swing_low,
                    break_price=current_close,
                    break_index=current_idx,
                    displacement_atr=displacement,
                )
                
                logger.info(
                    f"CHOCH_BEAR | index={current_idx} | break_price={current_close:.5f} | "
                    f"swing_price={last_swing_low.price:.5f} | displacement_atr={displacement:.2f} | "
                    f"previous_trend=bullish"
                )
                return choch
    
    return None


# =============================================================================
# Helpers
# =============================================================================

def _find_last_confirmed_swing(
    swings: list[Swing],
    swing_type: str,
    before_index: int,
) -> Optional[Swing]:
    """
    Trouve le dernier swing confirmé d'un type donné avant un index.
    """
    for swing in reversed(swings):
        if swing.type == swing_type and swing.confirmed and swing.index < before_index:
            return swing
    return None


def _calculate_displacement_atr(df: pd.DataFrame, index: int) -> float:
    """
    Calcule le displacement de la bougie en multiples d'ATR.
    
    DYNAMIC: basé sur l'ATR, pas sur un seuil fixe.
    """
    atr = _calculate_atr_value(df, index)
    if atr <= 0:
        return 0.0
    
    body = abs(df["close"].iloc[index] - df["open"].iloc[index])
    return body / atr


def _calculate_atr_value(df: pd.DataFrame, index: int) -> float:
    """
    Calcul de l'ATR à un index donné.
    DYNAMIC: ATR_PERIOD est STRUCTURAL (convention standard).
    """
    period = ATR_PERIOD  # STRUCTURAL
    
    start = max(0, index - period + 1)
    if start >= index:
        return 0.0001  # STRUCTURAL: fallback minimal
    
    subset = df.iloc[start:index + 1]
    
    high = subset["high"]
    low = subset["low"]
    close_prev = subset["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.mean()
    
    return float(atr) if not pd.isna(atr) else 0.0001  # STRUCTURAL: fallback minimal


def determine_trend(swings: list[Swing]) -> str:
    """
    Détermine la tendance actuelle basée sur les swings.
    
    Algorithme : comparer les derniers swing_high et swing_low.
    - Si le dernier swing_high est plus haut que le précédent → bullish
    - Si le dernier swing_low est plus bas que le précédent → bearish
    """
    confirmed_swings = [s for s in swings if s.confirmed]
    
    highs = [s for s in confirmed_swings if s.type == "swing_high"]
    lows = [s for s in confirmed_swings if s.type == "swing_low"]
    
    if len(highs) < 2 or len(lows) < 2:
        return "neutral"
    
    # Comparer les 2 derniers swings de chaque type
    last_high = highs[-1]
    prev_high = highs[-2]
    last_low = lows[-1]
    prev_low = lows[-2]
    
    higher_high = last_high.price > prev_high.price
    higher_low = last_low.price > prev_low.price
    lower_high = last_high.price < prev_high.price
    lower_low = last_low.price < prev_low.price
    
    if higher_high and higher_low:
        return "bullish"
    elif lower_high and lower_low:
        return "bearish"
    else:
        return "neutral"  # Conflit — pas de tendance claire
