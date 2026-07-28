"""
Fair Value Gap (FVG) detection — Bot SMC/ICT v2.

RÈGLE 1 : detect_fvg() et check_fvg_filled() sont les SEULES fonctions
pour la détection et la validation des FVG.
RÈGLE 3 : Transition, pas état.
RÈGLE 4 : Pas de seuils fixes sans justification. Filtres depuis config.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import (
    FVG_MIN_ATR_MULTIPLIER,
    FVG_MAX_AGE_MULTIPLIER,
    ATR_PERIOD,
)
from core.signal_types import SignalType

logger = logging.getLogger(__name__)


# =============================================================================
# Types de données
# =============================================================================

@dataclass
class FVG:
    """Fair Value Gap détecté."""
    type: str  # "fvg_bull" or "fvg_bear"
    gap_top: float  # Bord supérieur du gap
    gap_bottom: float  # Bord inférieur du gap
    size: float  # Taille du gap en pips
    size_atr: float  # Taille du gap en multiples d'ATR (DYNAMIC)
    created_index: int  # Index de la bougie qui crée le FVG
    created_timestamp: pd.Timestamp
    filled: bool = False  # True si le gap a été traversé (iFVG)
    fill_index: Optional[int] = None  # Index où le gap a été fillé
    age: int = 0  # Nombre de bougies depuis la création
    
    def __post_init__(self):
        if self.type not in ("fvg_bull", "fvg_bear"):
            raise ValueError(f"Type FVG invalide: {self.type}")
        if self.gap_top <= self.gap_bottom:
            raise ValueError(f"FVG invalide: gap_top={self.gap_top} <= gap_bottom={self.gap_bottom}")
        if self.size <= 0:
            raise ValueError(f"Taille FVG invalide: {self.size}")
    
    @property
    def is_active(self) -> bool:
        """FVG actif = non fillé et pas trop vieux."""
        max_age = ATR_PERIOD * FVG_MAX_AGE_MULTIPLIER  # DYNAMIC
        return not self.filled and self.age <= max_age
    
    @property
    def signal_type(self) -> SignalType:
        return SignalType.FVG_BULL if self.type == "fvg_bull" else SignalType.FVG_BEAR


# =============================================================================
# Détection des FVG
# =============================================================================

def detect_fvg(df: pd.DataFrame, start_index: int = 0) -> list[FVG]:
    """
    Détecte tous les FVG dans les données à partir de start_index.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte les FVG.
    
    Algorithme :
    FVG_BULL (gap haussier — bougie i-1, i, i+1) :
      gap_top = low[i-1]       # Bord supérieur = plus bas de la bougie avant
      gap_bottom = high[i+1]   # Bord inférieur = plus haut de la bougie après
      condition = gap_top > gap_bottom  # Il y a un gap
    
    FVG_BEAR (gap baissier) :
      gap_top = low[i+1]       # Bord supérieur = plus bas de la bougie après
      gap_bottom = high[i-1]   # Bord inférieur = plus haut de la bougie avant
      condition = gap_top > gap_bottom
    
    Filtrage :
      taille_minimum = ATR * FVG_MIN_ATR_MULTIPLIER (DYNAMIC)
    
    Args:
        df: DataFrame OHLCV
        start_index: Index de départ pour la détection
    
    Returns:
        Liste de FVG détectés
    """
    fvgs = []
    
    if len(df) < 3:
        logger.warning(f"FVG_DETECT | reason=insufficient_data | bars={len(df)} | need=3")
        return fvgs
    
    # Calcul de l'ATR pour chaque bougie (DYNAMIC)
    atr_values = _calculate_atr_series(df)
    
    for i in range(max(1, start_index), len(df) - 1):
        # FVG Bull : gap entre low[i-1] et high[i+1]
        gap_top_bull = df["low"].iloc[i - 1]
        gap_bottom_bull = df["high"].iloc[i + 1]
        size_bull = gap_top_bull - gap_bottom_bull
        
        if size_bull > 0:
            atr = atr_values.iloc[i] if i < len(atr_values) else 0.0001  # STRUCTURAL: fallback minimal non-zero pour éviter division par zéro
            size_atr_bull = size_bull / atr if atr > 0 else 0
            
            # Filtrage par taille minimum (DYNAMIC)
            if size_atr_bull >= FVG_MIN_ATR_MULTIPLIER:
                fvg = FVG(
                    type="fvg_bull",
                    gap_top=gap_top_bull,
                    gap_bottom=gap_bottom_bull,
                    size=size_bull / 0.0001,  # STRUCTURAL: conversion en pips (PIP_SIZE)
                    size_atr=size_atr_bull,
                    created_index=i,
                    created_timestamp=df.index[i],
                )
                fvgs.append(fvg)
                logger.info(
                    f"FVG_BULL | index={i} | top={gap_top_bull:.5f} | "
                    f"bottom={gap_bottom_bull:.5f} | size_atr={size_atr_bull:.2f}"
                )
        
        # FVG Bear : gap entre low[i+1] et high[i-1]
        gap_top_bear = df["low"].iloc[i + 1]
        gap_bottom_bear = df["high"].iloc[i - 1]
        size_bear = gap_top_bear - gap_bottom_bear
        
        if size_bear > 0:
            atr = atr_values.iloc[i] if i < len(atr_values) else 0.0001  # STRUCTURAL: fallback minimal non-zero pour éviter division par zéro
            size_atr_bear = size_bear / atr if atr > 0 else 0
            
            if size_atr_bear >= FVG_MIN_ATR_MULTIPLIER:
                fvg = FVG(
                    type="fvg_bear",
                    gap_top=gap_top_bear,
                    gap_bottom=gap_bottom_bear,
                    size=size_bear / 0.0001,  # STRUCTURAL: conversion en pips
                    size_atr=size_atr_bear,
                    created_index=i,
                    created_timestamp=df.index[i],
                )
                fvgs.append(fvg)
                logger.info(
                    f"FVG_BEAR | index={i} | top={gap_top_bear:.5f} | "
                    f"bottom={gap_bottom_bear:.5f} | size_atr={size_atr_bear:.2f}"
                )
    
    logger.info(
        f"FVG_DETECT_COMPLETE | total={len(fvgs)} | "
        f"bull={sum(1 for f in fvgs if f.type == 'fvg_bull')} | "
        f"bear={sum(1 for f in fvgs if f.type == 'fvg_bear')}"
    )
    
    return fvgs


# =============================================================================
# Vérification des FVG fillés (iFVG)
# =============================================================================

def check_fvg_filled(fvgs: list[FVG], df: pd.DataFrame, current_index: int) -> list[FVG]:
    """
    Vérifie si des FVG actifs ont été fillés (iFVG) à la bougie courante.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui vérifie les FVG fillés.
    
    Un FVG bull est fillé si le prix repasse complètement en-dessous du gap :
      low[current_index] <= fvg.gap_bottom
    
    Un FVG bear est fillé si le prix repasse complètement au-dessus du gap :
      high[current_index] >= fvg.gap_top
    
    Les FVG fillés sont marqués et retirés des FVG actifs.
    
    Args:
        fvgs: Liste des FVG existants
        df: DataFrame OHLCV
        current_index: Index de la bougie courante
    
    Returns:
        Liste mise à jour des FVG (avec status filled)
    """
    updated = []
    
    for fvg in fvgs:
        if fvg.filled:
            updated.append(fvg)  # Déjà fillé, pas de changement
            continue
        
        # Mettre à jour l'âge
        fvg.age = current_index - fvg.created_index
        
        if current_index >= len(df):
            updated.append(fvg)
            continue
        
        current_low = df["low"].iloc[current_index]
        current_high = df["high"].iloc[current_index]
        
        # FVG Bull fillé : prix repasse en-dessous du gap bottom
        if fvg.type == "fvg_bull" and current_low <= fvg.gap_bottom:
            fvg.filled = True
            fvg.fill_index = current_index
            logger.info(
                f"FVG_FILLED | type=bull | created_index={fvg.created_index} | "
                f"fill_index={current_index} | age={fvg.age} | "
                f"gap_top={fvg.gap_top:.5f} | gap_bottom={fvg.gap_bottom:.5f}"
            )
        
        # FVG Bear fillé : prix repasse au-dessus du gap top
        elif fvg.type == "fvg_bear" and current_high >= fvg.gap_top:
            fvg.filled = True
            fvg.fill_index = current_index
            logger.info(
                f"FVG_FILLED | type=bear | created_index={fvg.created_index} | "
                f"fill_index={current_index} | age={fvg.age} | "
                f"gap_top={fvg.gap_top:.5f} | gap_bottom={fvg.gap_bottom:.5f}"
            )
        
        updated.append(fvg)
    
    active = sum(1 for f in updated if f.is_active)
    filled = sum(1 for f in updated if f.filled)
    
    logger.debug(f"FVG_UPDATE | total={len(updated)} | active={active} | filled={filled}")
    
    return updated


# =============================================================================
# Helpers
# =============================================================================

def _calculate_atr_series(df: pd.DataFrame) -> pd.Series:
    """
    Calcul de l'ATR pour chaque bougie.
    
    DYNAMIC: ATR_PERIOD est STRUCTURAL (convention standard).
    """
    period = ATR_PERIOD  # STRUCTURAL: convention standard
    
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr.fillna(0.0001)  # STRUCTURAL: fallback minimal


def find_fvg_at_price(fvgs: list[FVG], price: float, direction: str) -> Optional[FVG]:
    """
    Trouve le FVG actif le plus proche du prix actuel, dans la direction du trade.
    
    Pour un LONG : cherche un FVG bull en-dessous du prix (zone d'entrée)
    Pour un SHORT : cherche un FVG bear au-dessus du prix (zone d'entrée)
    """
    active_fvgs = [f for f in fvgs if f.is_active]
    
    if direction == "long":
        # FVG bull en-dessous du prix
        candidates = [f for f in active_fvgs if f.type == "fvg_bull" and f.gap_top <= price]
        if candidates:
            # Le plus proche du prix
            return max(candidates, key=lambda f: f.gap_top)
    
    elif direction == "short":
        # FVG bear au-dessus du prix
        candidates = [f for f in active_fvgs if f.type == "fvg_bear" and f.gap_bottom >= price]
        if candidates:
            return min(candidates, key=lambda f: f.gap_bottom)
    
    return None
