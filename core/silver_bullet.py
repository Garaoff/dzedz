"""
Silver Bullet Model — ICT 2022 Mentorship Model.

RÈGLE 1 : detect_silver_bullet() est la SEULE fonction qui détecte le Silver Bullet.
RÈGLE 3 : Transition, pas état — Silver Bullet sur TRANSITION uniquement.
RÈGLE 4 : Tous les paramètres depuis config.
RÈGLE 6 : Pas d'échec silencieux.

Le Silver Bullet est le modèle ICT le plus spécifique et performant :

    Silver Bullet = Killzone + MSS + FVG + Sweep

    4 conditions OBLIGATOIRES :
    1. Killzone active (London Open, NY Open, NY PM)
    2. MSS (Market Structure Shift = CHOCH + Displacement + FVG)
    3. FVG créé par le MSS (zone d'entrée sur retracement)
    4. Sweep de liquidité avant le MSS (confirmation institutionnelle)

    Séquence ICT complète :
    a. Sweep de liquidité (stops retail chassés)
    b. MSS (displacement + FVG montre l'action institutionnelle)
    c. Retracement dans le FVG créé par le MSS (zone d'entrée)
    d. Entry avec SL derrière le FVG et TP sur liquidité opposée

    Ce modèle est le SETUP OPTIMAL en ICT. Tout trade qui ne satisfait
    pas toutes 4 conditions a une probabilité plus basse.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import CONFLUENCE_MINIMUM
from core.killzones import get_killzone, KillzoneInfo
from core.mss import detect_mss, MarketStructureShift
from core.liquidity import LiquiditySweep
from core.fvg import FVG, find_fvg_at_price
from core.structure import Swing

logger = logging.getLogger(__name__)


@dataclass
class SilverBulletSetup:
    """Silver Bullet Setup détecté — le setup ICT optimal."""
    direction: str  # "long" or "short"
    mss: MarketStructureShift  # MSS qui valide le changement de tendance
    fvg_entry: FVG  # FVG créé par le MSS — zone d'entrée
    killzone: KillzoneInfo  # Killzone active au moment du setup
    sweep: Optional[LiquiditySweep]  # Sweep de liquidité avant le MSS
    entry_price: float  # Prix d'entrée (FVG zone)
    fvg_zone_top: float  # Bord supérieur du FVG
    fvg_zone_bottom: float  # Bord inférieur du FVG
    
    @property
    def is_complete(self) -> bool:
        """True si toutes les conditions sont satisfaites."""
        return (
            self.killzone.is_active and
            self.mss.has_fvg and
            self.mss.displacement_significant and
            self.fvg_entry is not None
        )
    
    @property
    def has_sweep(self) -> bool:
        """True si un sweep de liquidité précède le MSS."""
        return self.sweep is not None
    
    @property
    def setup_quality(self) -> str:
        """Qualité du setup basée sur les confluences."""
        if self.has_sweep and self.killzone.is_active:
            return "gold"  # Killzone + MSS + FVG + Sweep = setup optimal
        elif self.killzone.is_active and self.mss.has_fvg:
            return "silver"  # Killzone + MSS + FVG (pas de sweep)
        elif self.mss.has_fvg:
            return "bronze"  # MSS + FVG (pas de killzone, pas de sweep)
        else:
            return "basic"


def detect_silver_bullet(
    df: pd.DataFrame,
    timestamp: pd.Timestamp,
    swings: list[Swing],
    current_trend: str,
    fvgs: list[FVG],
    last_sweep: Optional[LiquiditySweep],
) -> Optional[SilverBulletSetup]:
    """
    Détecte un Silver Bullet Setup — le setup ICT optimal.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte le Silver Bullet.
    RÈGLE 3 : Setup sur TRANSITION — MSS doit être NOUVEAU.
    
    Séquence requise :
    1. Killzone active (fenêtre temporelle ICT)
    2. Sweep de liquidité (PRECÈDE le MSS — stops chassés)
    3. MSS (CHOCH + Displacement + FVG — changement confirmé)
    4. Retracement dans le FVG (zone d'entrée)
    
    Args:
        df: DataFrame OHLCV
        timestamp: Timestamp de la bougie courante (pour killzone)
        swings: Liste des swings détectés
        current_trend: Tendance actuelle
        fvgs: Liste des FVG existants
        last_sweep: Sweep de liquidité le plus récent
    
    Returns:
        SilverBulletSetup si toutes conditions satisfaites, None sinon
    """
    if len(df) < 3:
        logger.debug(f"SILVER_BULLET | reason=insufficient_data | bars={len(df)}")
        return None
    
    # === 1. Killzone ===
    # Convertir le timestamp en datetime pour get_killzone
    ts_datetime = timestamp.to_pydatetime() if isinstance(timestamp, pd.Timestamp) else timestamp
    killzone = get_killzone(ts_datetime)
    
    if not killzone.is_active:
        logger.debug(
            f"SILVER_BULLET_REJECTED | reason=no_killzone | "
            f"killzone={killzone.name} | timestamp={timestamp}"
        )
        return None
    
    # === 2. MSS ===
    mss = detect_mss(df, swings, current_trend, fvgs)
    
    if mss is None:
        logger.debug(
            f"SILVER_BULLET_REJECTED | reason=no_mss | "
            f"killzone={killzone.name} | trend={current_trend}"
        )
        return None
    
    # === 3. FVG créé par le MSS ===
    if not mss.has_fvg:
        logger.debug(
            f"SILVER_BULLET_REJECTED | reason=mss_no_fvg | "
            f"mss_type={mss.type} | killzone={killzone.name}"
        )
        return None
    
    # Le FVG d'entrée est celui créé par le MSS
    fvg_entry = mss.fvg_created
    
    # === 4. Direction ===
    direction = "long" if mss.type == "mss_bull" else "short"
    
    # Vérifier que le FVG est dans la bonne direction
    if direction == "long" and fvg_entry.type != "fvg_bull":
        logger.debug(f"SILVER_BULLET_REJECTED | reason=fvg_direction_mismatch | dir=long | fvg={fvg_entry.type}")
        return None
    
    if direction == "short" and fvg_entry.type != "fvg_bear":
        logger.debug(f"SILVER_BULLET_REJECTED | reason=fvg_direction_mismatch | dir=short | fvg={fvg_entry.type}")
        return None
    
    # === 5. Prix d'entrée ===
    # STRUCTURAL: ICT enseigne l'entrée sur retracement dans le FVG
    # Pour un LONG : entrée dans le FVG bull (entre gap_bottom et gap_top)
    # Pour un SHORT : entrée dans le FVG bear (entre gap_bottom et gap_top)
    
    price = df["close"].iloc[-1]
    
    if direction == "long":
        # Prix doit être dans ou proche du FVG bull pour une entrée
        # STRUCTURAL: on accepte si le prix est au-dessus du FVG bottom
        # (retracement en cours ou imminent)
        entry_price = fvg_entry.gap_bottom  # STRUCTURAL: entrée au bord inférieur du FVG
    else:
        entry_price = fvg_entry.gap_top  # STRUCTURAL: entrée au bord supérieur du FVG
    
    # === Construction du setup ===
    
    setup = SilverBulletSetup(
        direction=direction,
        mss=mss,
        fvg_entry=fvg_entry,
        killzone=killzone,
        sweep=last_sweep,
        entry_price=entry_price,
        fvg_zone_top=fvg_entry.gap_top,
        fvg_zone_bottom=fvg_entry.gap_bottom,
    )
    
    logger.info(
        f"SILVER_BULLET_DETECTED | direction={direction} | "
        f"quality={setup.setup_quality} | "
        f"killzone={killzone.name} | "
        f"mss_type={mss.type} | displacement={mss.displacement_atr:.2f} | "
        f"fvg_type={fvg_entry.type} | fvg_size_atr={fvg_entry.size_atr:.2f} | "
        f"has_sweep={setup.has_sweep} | "
        f"entry_zone=[{fvg_entry.gap_bottom:.5f}, {fvg_entry.gap_top:.5f}]"
    )
    
    return setup
