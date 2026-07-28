"""
Liquidity Sweep detection — Bot SMC/ICT v2.

RÈGLE 1 : detect_sweep() et detect_equal_levels() sont les SEULES fonctions.
RÈGLE 3 : Transition, pas état.
RÈGLE 4 : Pas de seuils fixes. EQUAL_TOLERANCE_ATR depuis config.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import EQUAL_TOLERANCE_ATR, ATR_PERIOD
from core.structure import Swing
from core.signal_types import SignalType

logger = logging.getLogger(__name__)


# =============================================================================
# Types de données
# =============================================================================

@dataclass
class LiquidityLevel:
    """Niveau de liquidité (swing ou equal highs/lows)."""
    type: str  # "swing_high", "swing_low", "equal_highs", "equal_lows"
    price: float
    source_indices: list[int]  # Indices des bougies qui composent ce niveau
    swept: bool = False  # True si le niveau a été sweepé
    sweep_index: Optional[int] = None


@dataclass
class LiquiditySweep:
    """Liquidity sweep détecté."""
    direction: str  # "high" (sweep au-dessus) or "low" (sweep en-dessous)
    swept_level: LiquidityLevel
    sweep_price: float  # Prix de la mèche qui dépasse
    close_price: float  # Close de la bougie (revient en-dessous/au-dessus)
    sweep_index: int
    
    @property
    def signal_type(self) -> SignalType:
        if self.direction == "high":
            return SignalType.LIQUIDITY_SWEEP_HIGH
        else:
            return SignalType.LIQUIDITY_SWEEP_LOW


# =============================================================================
# Détection des niveaux de liquidité
# =============================================================================

def detect_liquidity_levels(swings: list[Swing], df: pd.DataFrame) -> list[LiquidityLevel]:
    """
    Détecte les niveaux de liquidité (swings + equal highs/lows).
    
    Les niveaux de liquidité sont les zones où les stops sont concentrés :
    - Swing highs (stops longs au-dessus)
    - Swing lows (stops shorts en-dessous)
    - Equal highs (plusieurs highs au même niveau = stops empilés)
    - Equal lows (plusieurs lows au même niveau = stops empilés)
    """
    levels = []
    
    # Convertir swings en niveaux de liquidité
    for swing in swings:
        if swing.confirmed:
            level = LiquidityLevel(
                type=swing.type,
                price=swing.price,
                source_indices=[swing.index],
            )
            levels.append(level)
    
    # Détecter les equal highs/lows (niveaux avec plusieurs stops empilés)
    equal_levels = detect_equal_levels(swings, df)
    levels.extend(equal_levels)
    
    logger.info(
        f"LIQUIDITY_LEVELS | total={len(levels)} | "
        f"swing_levels={sum(1 for l in levels if l.type.startswith('swing'))} | "
        f"equal_levels={sum(1 for l in levels if l.type.startswith('equal'))}"
    )
    
    return levels


def detect_equal_levels(swings: list[Swing], df: pd.DataFrame) -> list[LiquidityLevel]:
    """
    Détecte les equal highs et equal lows.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte les equal levels.
    RÈGLE 4 : La tolérance est DYNAMIC (EQUAL_TOLERANCE_ATR * ATR).
    
    Equal Highs : 2+ swing highs au même niveau (± tolérance ATR)
    Equal Lows : 2+ swing lows au même niveau (± tolérance ATR)
    """
    equal_levels = []
    
    # Calcul de la tolérance dynamique
    atr = _calculate_atr_from_df(df)
    tolerance = atr * EQUAL_TOLERANCE_ATR  # DYNAMIC
    
    # Grouper les swing highs par niveau
    highs = [s for s in swings if s.type == "swing_high" and s.confirmed]
    lows = [s for s in swings if s.type == "swing_low" and s.confirmed]
    
    # Equal Highs
    if len(highs) >= 2:
        used_indices = set()
        for i, h1 in enumerate(highs):
            if i in used_indices:
                continue
            group = [h1]
            for j, h2 in enumerate(highs):
                if j != i and j not in used_indices:
                    if abs(h1.price - h2.price) <= tolerance:
                        group.append(h2)
                        used_indices.add(j)
            if len(group) >= 2:
                avg_price = sum(h.price for h in group) / len(group)
                level = LiquidityLevel(
                    type="equal_highs",
                    price=avg_price,
                    source_indices=[h.index for h in group],
                )
                equal_levels.append(level)
                logger.info(
                    f"EQUAL_HIGHS | price={avg_price:.5f} | "
                    f"count={len(group)} | indices={level.source_indices}"
                )
    
    # Equal Lows
    if len(lows) >= 2:
        used_indices = set()
        for i, l1 in enumerate(lows):
            if i in used_indices:
                continue
            group = [l1]
            for j, l2 in enumerate(lows):
                if j != i and j not in used_indices:
                    if abs(l1.price - l2.price) <= tolerance:
                        group.append(l2)
                        used_indices.add(j)
            if len(group) >= 2:
                avg_price = sum(l.price for l in group) / len(group)
                level = LiquidityLevel(
                    type="equal_lows",
                    price=avg_price,
                    source_indices=[l.index for l in group],
                )
                equal_levels.append(level)
                logger.info(
                    f"EQUAL_LOWS | price={avg_price:.5f} | "
                    f"count={len(group)} | indices={level.source_indices}"
                )
    
    return equal_levels


# =============================================================================
# Détection des Sweeps
# =============================================================================

def detect_sweep(
    df: pd.DataFrame,
    levels: list[LiquidityLevel],
    current_index: int,
) -> Optional[LiquiditySweep]:
    """
    Détecte un liquidity sweep à la bougie courante.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte les sweeps.
    RÈGLE 3 : Le sweep est détecté au moment de la TRANSITION.
    
    Sweep High : mèche dépasse un niveau de liquidité au-dessus, puis close revient
    Sweep Low : mèche dépasse un niveau de liquidité en-dessous, puis close revient
    
    Args:
        df: DataFrame OHLCV
        levels: Niveaux de liquidité (swings + equal)
        current_index: Index de la bougie à analyser
    
    Returns:
        LiquiditySweep si détecté, None sinon
    """
    if current_index < 1 or current_index >= len(df):
        return None
    
    # Seulement les niveaux non sweepés
    active_levels = [l for l in levels if not l.swept]
    
    if not active_levels:
        return None
    
    current_high = df["high"].iloc[current_index]
    current_low = df["low"].iloc[current_index]
    current_close = df["close"].iloc[current_index]
    prev_close = df["close"].iloc[current_index - 1]
    prev_high = df["high"].iloc[current_index - 1]
    prev_low = df["low"].iloc[current_index - 1]
    
    # Sweep High : mèche dépasse un niveau au-dessus, close revient en-dessous
    high_levels = [l for l in active_levels if l.price < current_high]
    
    for level in high_levels:
        # La mèche dépasse le niveau
        swept_now = current_high > level.price and current_close < level.price
        # TRANSITION (Règle 3) : la bougie précédente n'avait pas déjà sweepé ce niveau
        swept_prev = prev_high > level.price and prev_close < level.price
        
        if swept_now and not swept_prev:
            # TRANSITION détectée — sweep valide
            sweep = LiquiditySweep(
                direction="high",
                swept_level=level,
                sweep_price=current_high,
                close_price=current_close,
                sweep_index=current_index,
            )
            
            # Marquer le niveau comme sweepé
            level.swept = True
            level.sweep_index = current_index
            
            logger.info(
                f"SWEEP_HIGH | index={current_index} | level_price={level.price:.5f} | "
                f"sweep_price={current_high:.5f} | close={current_close:.5f} | "
                f"level_type={level.type}"
            )
            
            return sweep
    
    # Sweep Low : mèche dépasse un niveau en-dessous, close revient au-dessus
    low_levels = [l for l in active_levels if l.price > current_low]
    
    for level in low_levels:
        swept_now = current_low < level.price and current_close > level.price
        swept_prev = prev_low < level.price and prev_close > level.price
        
        if swept_now and not swept_prev:
            sweep = LiquiditySweep(
                direction="low",
                swept_level=level,
                sweep_price=current_low,
                close_price=current_close,
                sweep_index=current_index,
            )
            
            level.swept = True
            level.sweep_index = current_index
            
            logger.info(
                f"SWEEP_LOW | index={current_index} | level_price={level.price:.5f} | "
                f"sweep_price={current_low:.5f} | close={current_close:.5f} | "
                f"level_type={level.type}"
            )
            
            return sweep
    
    return None


# =============================================================================
# Helpers
# =============================================================================

def _calculate_atr_from_df(df: pd.DataFrame) -> float:
    """Calcul de l'ATR moyen sur les données."""
    period = ATR_PERIOD  # STRUCTURAL
    
    if len(df) < period:
        period = len(df)
    
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.tail(period).mean()
    
    return float(atr) if not pd.isna(atr) else 0.0001  # STRUCTURAL: fallback


def find_nearest_liquidity_level(
    levels: list[LiquidityLevel],
    price: float,
    direction: str,
) -> Optional[LiquidityLevel]:
    """
    Trouve le niveau de liquidité le plus proche dans une direction.
    
    Pour SL LONG : niveau en-dessous (stops shorts)
    Pour SL SHORT : niveau au-dessus (stops longs)
    Pour TP LONG : niveau au-dessus (liquidité à cibler)
    Pour TP SHORT : niveau en-dessous (liquidité à cibler)
    """
    active = [l for l in levels if not l.swept]
    
    if direction == "above":
        candidates = [l for l in active if l.price > price]
        return min(candidates, key=lambda l: l.price) if candidates else None
    
    elif direction == "below":
        candidates = [l for l in active if l.price < price]
        return max(candidates, key=lambda l: l.price) if candidates else None
    
    return None
