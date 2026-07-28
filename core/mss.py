"""
Market Structure Shift (MSS) — Bot SMC/ICT v2.

RÈGLE 1 : detect_mss() est la SEULE fonction qui détecte le MSS.
RÈGLE 3 : Transition, pas état. MSS se déclenche sur TRANSITION.
RÈGLE 4 : DISPLACEMENT_MIN_ATR depuis config.
RÈGLE 6 : Pas d'échec silencieux.

MSS = Market Structure Shift

Dans ICT, un vrai MSS nécessite TROIS conditions simultanées :
1. Cassure de structure (close passe au-dessus/au-dessous d'un swing)
2. Displacement significatif (bougie de cassure >= DISPLACEMENT_MIN_ATR)
3. Création d'un FVG pendant le mouvement de cassure

Le CHOCH simple (juste close > swing) est une condition PARTIELLE.
Le MSS est le concept COMPLET avec confirmation displacement + FVG.

Un MSS est le signal ICT le plus puissant — il indique que les
institutionnels ont déplacé le prix avec force et ont créé un
déséquilibre (FVG) qu'ils vont revisiter.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import DISPLACEMENT_MIN_ATR, ATR_PERIOD
from core.structure import detect_swings, Swing, StructureBreak, detect_choch
from core.displacement import measure_displacement
from core.fvg import detect_fvg, FVG

logger = logging.getLogger(__name__)


@dataclass
class MarketStructureShift:
    """Market Structure Shift détecté — le signal ICT le plus puissant."""
    type: str  # "mss_bull" or "mss_bear"
    broken_swing: Swing  # Swing qui a été cassé
    break_price: float  # Prix de la cassure
    break_index: int  # Index de la bougie de cassure
    displacement_atr: float  # DYNAMIC: force du displacement
    fvg_created: Optional[FVG] = None  # FVG créé par le displacement
    choch_base: Optional[StructureBreak] = None  # CHOCH qui forme la base
    
    @property
    def displacement_significant(self) -> bool:
        """True si displacement >= DISPLACEMENT_MIN_ATR."""
        return self.displacement_atr >= DISPLACEMENT_MIN_ATR
    
    @property
    def has_fvg(self) -> bool:
        """True si un FVG a été créé pendant le displacement."""
        return self.fvg_created is not None


def detect_mss(
    df: pd.DataFrame,
    swings: list[Swing],
    current_trend: str,
    fvgs: list[FVG],
) -> Optional[MarketStructureShift]:
    """
    Détecte un Market Structure Shift (MSS) — signal ICT COMPLET.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte le MSS.
    RÈGLE 3 : MSS est détecté au moment de la TRANSITION.
    
    MSS = CHOCH + Displacement + FVG
    Toutes 3 conditions doivent être simultanées pour un vrai MSS.
    
    Si le CHOCH existe mais sans displacement significatif, c'est juste
    un CHOCH (moins puissant). Si displacement existe mais pas de FVG,
    c'est un BOS fort mais pas un MSS.
    
    La hiérarchie ICT :
    - MSS (CHOCH + displacement + FVG) = signal le plus puissant
    - CHOCH + displacement (sans FVG) = signal moyen
    - BOS + displacement = continuation confirmée
    - CHOCH simple (sans displacement) = signal faible
    
    Args:
        df: DataFrame OHLCV
        swings: Liste des swings détectés
        current_trend: Tendance actuelle ("bullish"/"bearish"/"neutral")
        fvgs: Liste des FVG existants (pour vérifier création simultanée)
    
    Returns:
        MarketStructureShift si MSS détecté, None sinon
    """
    if len(df) < 3:
        logger.warning(f"MSS | reason=insufficient_data | bars={len(df)} | need=3+")
        return None
    
    current_idx = len(df) - 1
    
    # === 1. Base : CHOCH (cassure de structure) ===
    choch = detect_choch(df, swings, current_trend)
    
    if choch is None:
        logger.debug("MSS | reason=no_choch_base | MSS requires CHOCH as base")
        return None
    
    # === 2. Displacement significatif ===
    displacement_result = measure_displacement(df, current_idx)
    displacement_atr = displacement_result["displacement_atr"]
    is_significant = displacement_result["is_significant"]
    
    if not is_significant:
        logger.debug(
            f"MSS_REJECTED | reason=no_significant_displacement | "
            f"displacement_atr={displacement_atr:.2f} | min={DISPLACEMENT_MIN_ATR} | "
            f"choch_type={choch.type} — this is a CHOCH only, not MSS"
        )
        return None
    
    # === 3. FVG créé par le displacement ===
    # STRUCTURAL: on vérifie si un FVG a été créé AU MOMENT du MSS
    # Le FVG doit être créé à la même bougie que la cassure
    # ou à la bougie juste avant/après (±1 index)
    
    mss_fvg = _find_fvg_at_mss(fvgs, current_idx)
    
    if mss_fvg is None:
        # Pas de FVG simultané — c'est un CHOCH + displacement, pas un vrai MSS
        logger.debug(
            f"MSS_REJECTED | reason=no_simultaneous_fvg | "
            f"displacement={displacement_atr:.2f} | choch={choch.type} — "
            f"CHOCH+displacement but no FVG = not full MSS"
        )
        return None
    
    # === MSS COMPLET détecté ===
    
    mss_type = "mss_bull" if choch.type == "choch_bull" else "mss_bear"
    
    mss = MarketStructureShift(
        type=mss_type,
        broken_swing=choch.broken_swing,
        break_price=choch.break_price,
        break_index=current_idx,
        displacement_atr=displacement_atr,
        fvg_created=mss_fvg,
        choch_base=choch,
    )
    
    logger.info(
        f"MSS_DETECTED | type={mss_type} | break_price={choch.break_price:.5f} | "
        f"displacement_atr={displacement_atr:.2f} | "
        f"fvg_type={mss_fvg.type} | fvg_size_atr={mss_fvg.size_atr:.2f} | "
        f"previous_trend={current_trend} | "
        f"ALL_3_CONDITIONS_MET=choch+displacement+fvg"
    )
    
    return mss


def _find_fvg_at_mss(fvgs: list[FVG], mss_index: int) -> Optional[FVG]:
    """
    Trouve un FVG créé au moment du MSS.
    
    STRUCTURAL: le FVG doit être créé à la même bougie que la cassure
    ou à ±1 index (le displacement qui crée le MSS crée aussi le FVG
    dans un intervalle de ±1 bougie).
    
    Args:
        fvgs: Liste des FVG existants
        mss_index: Index de la bougie où le MSS se produit
    
    Returns:
        FVG créé au moment du MSS, None sinon
    """
    # STRUCTURAL: ±1 index tolerance — le FVG est créé par le displacement
    # et peut apparaître 1 bougie avant ou après la cassure
    tolerance = 1  # STRUCTURAL: ICT enseigne que le FVG et le MSS sont simultanés
    
    candidates = []
    for fvg in fvgs:
        if not fvg.filled and abs(fvg.created_index - mss_index) <= tolerance:
            candidates.append(fvg)
    
    if not candidates:
        return None
    
    # Retourner le FVG le plus proche du MSS
    return min(candidates, key=lambda f: abs(f.created_index - mss_index))
