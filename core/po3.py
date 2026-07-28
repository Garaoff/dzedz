"""
Power of 3 (PO3) — Accumulation, Manipulation, Distribution.

RÈGLE 1 : detect_po3_phase() est la SEULE fonction qui détecte la phase PO3.
RÈGLE 4 : Pas de seuils fixes. Paramètres depuis config.
RÈGLE 6 : Pas d'échec silencieux.

ICT Power of 3 (PO3) est le cycle quotidien de 3 phases :

1. ACCUMULATION : Les institutionnels accumulent leur position.
   Prix range dans la killzone morning. Volume discret.
   → Range tight dans la morning session

2. MANIPULATION : Les institutionnels manipulent le prix pour
   chasser les stops retail (liquidity sweep). 
   → Sweep de PDH/PDL ou equal highs/lows

3. DISTRIBUTION : Les institutionnels distribuent (exécutent)
   leur position avec displacement. Crée MSS + FVG.
   → Displacement + MSS + FVG

La séquence PO3 est le CYCLE COMPLET d'un jour ICT :
Accumulation → Manipulation → Distribution

On peut identifier la phase PO3 en analysant :
- Le range du matin (accumulation = range tight)
- Le sweep (manipulation = sweep de liquidité)
- Le displacement (distribution = MSS + FVG)

Trading PO3 : on ENTRE en distribution, PAS en accumulation/manipulation.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import (
    PO3_ACCUMULATION_RANGE_ATR_RATIO,
    ATR_PERIOD,
)
from core.liquidity import LiquiditySweep

logger = logging.getLogger(__name__)


@dataclass
class PO3Phase:
    """Phase du Power of 3."""
    phase: str  # "accumulation", "manipulation", "distribution", "unknown"
    confidence: float  # 0.0–1.0, confiance dans l'identification
    range_size: float  # Taille du range en pips
    range_size_atr: float  # Taille du range en ATR
    has_sweep: bool  # Manipulation : sweep détecté
    has_displacement: bool  # Distribution : displacement significatif
    
    @property
    def is_distribution(self) -> bool:
        """True si on est en phase distribution — le moment d'entrer."""
        return self.phase == "distribution"


def detect_po3_phase(
    df: pd.DataFrame,
    daily_start_index: int,
    current_index: int,
    last_sweep: Optional[LiquiditySweep] = None,
    displacement_atr: float = 0.0,
) -> PO3Phase:
    """
    Détermine la phase PO3 du cycle quotidien.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte la phase PO3.
    
    Algorithme :
    1. Calculer le range depuis le début de journée
    2. Si range < ATR * PO3_ACCUMULATION_RANGE_ATR_RATIO → accumulation
    3. Si sweep détecté (pas de displacement) → manipulation
    4. Si displacement significatif → distribution
    
    Args:
        df: DataFrame OHLCV
        daily_start_index: Index du début de journée
        current_index: Index de la bougie courante
        last_sweep: Sweep de liquidité le plus récent
        displacement_atr: Displacement en ATR
    
    Returns:
        PO3Phase avec la phase identifiée et la confiance
    """
    if daily_start_index >= current_index or current_index >= len(df):
        logger.debug("PO3 | reason=invalid_indices | returning unknown")
        return PO3Phase(
            phase="unknown", confidence=0.0,
            range_size=0.0, range_size_atr=0.0,
            has_sweep=False, has_displacement=False,
        )
    
    # === Calcul du range depuis le début de journée ===
    daily_data = df.iloc[daily_start_index:current_index + 1]
    
    if len(daily_data) < 2:
        return PO3Phase(
            phase="accumulation", confidence=0.1,  # STRUCTURAL: confiance minimale si données insuffisantes
            range_size=0.0, range_size_atr=0.0,
            has_sweep=False, has_displacement=False,
        )
    
    range_high = daily_data["high"].max()
    range_low = daily_data["low"].min()
    range_size = range_high - range_low
    
    # Calcul ATR pour normaliser
    atr = _calculate_atr_at(df, current_index)
    range_size_atr = range_size / atr if atr > 0 else 0
    
    has_sweep = last_sweep is not None
    has_displacement = displacement_atr >= 1.0  # STRUCTURAL: 1 ATR minimum pour distribution — même seuil que DISPLACEMENT_MIN_ATR
    
    # === Identification de la phase ===
    
    # DISTRIBUTION : displacement significatif = institutionnels distribuent
    if has_displacement and displacement_atr >= 1.0:  # STRUCTURAL: 1 ATR = DISPLACEMENT_MIN_ATR
        phase = "distribution"
        confidence = min(displacement_atr / 2.0, 1.0)  # DYNAMIC: plus de displacement = plus de confiance
        logger.info(
            f"PO3_DISTRIBUTION | range_atr={range_size_atr:.2f} | "
            f"displacement_atr={displacement_atr:.2f} | has_sweep={has_sweep} | "
            f"confidence={confidence:.2f} — ENTRY OPPORTUNITY"
        )
        
        return PO3Phase(
            phase=phase, confidence=confidence,
            range_size=range_size, range_size_atr=range_size_atr,
            has_sweep=has_sweep, has_displacement=has_displacement,
        )
    
    # MANIPULATION : sweep de liquidité = institutionnels chassent stops
    if has_sweep and not has_displacement:
        phase = "manipulation"
        confidence = 0.6  # STRUCTURAL: sweep = probable manipulation — confiance modérée
        logger.info(
            f"PO3_MANIPULATION | range_atr={range_size_atr:.2f} | "
            f"has_sweep={has_sweep} | displacement={displacement_atr:.2f} | "
            f"confidence={confidence:.2f} — WAITING FOR DISTRIBUTION"
        )
        
        return PO3Phase(
            phase=phase, confidence=confidence,
            range_size=range_size, range_size_atr=range_size_atr,
            has_sweep=has_sweep, has_displacement=has_displacement,
        )
    
    # ACCUMULATION : range tight = institutionnels accumulent
    if range_size_atr <= PO3_ACCUMULATION_RANGE_ATR_RATIO:
        phase = "accumulation"
        confidence = max(0.3, 1.0 - range_size_atr / PO3_ACCUMULATION_RANGE_ATR_RATIO)  # DYNAMIC
        logger.debug(
            f"PO3_ACCUMULATION | range_atr={range_size_atr:.2f} | "
            f"max_accumulation={PO3_ACCUMULATION_RANGE_ATR_RATIO:.2f} | "
            f"confidence={confidence:.2f} — NOT ENTRY YET"
        )
        
        return PO3Phase(
            phase=phase, confidence=confidence,
            range_size=range_size, range_size_atr=range_size_atr,
            has_sweep=has_sweep, has_displacement=has_displacement,
        )
    
    # UNKNOWN : range large mais pas de sweep/displacement
    phase = "unknown"
    confidence = 0.0
    logger.debug(
        f"PO3_UNKNOWN | range_atr={range_size_atr:.2f} | "
        f"has_sweep={has_sweep} | displacement={displacement_atr:.2f}"
    )
    
    return PO3Phase(
        phase=phase, confidence=confidence,
        range_size=range_size, range_size_atr=range_size_atr,
        has_sweep=has_sweep, has_displacement=has_displacement,
    )


def _calculate_atr_at(df: pd.DataFrame, index: int) -> float:
    """Calcul de l'ATR à un index."""
    period = ATR_PERIOD  # STRUCTURAL: convention standard
    
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
    
    return float(atr) if not pd.isna(atr) else 0.0001  # STRUCTURAL: fallback minimal non-zero
