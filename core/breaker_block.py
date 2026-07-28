"""
Breaker Block detection — Bot SMC/ICT v2.

RÈGLE 1 : detect_breaker_blocks() est la SEULE fonction qui détecte les Breakers.
RÈGLE 3 : Transition — Breaker est détecté quand un OB est invalidé.
RÈGLE 4 : Pas de seuils fixes. Breaker tolerance depuis config.
RÈGLE 6 : Pas d'échec silencieux.

Breaker Block = Order Block invalidé qui change de rôle.

Concept ICT :
- Un OB bull est une zone d'accumulation (support). Quand le prix
  casse en-dessous (invalidation), cette zone devient une zone de
  DISTRIBUTION (résistance) — c'est un Breaker Block bear.
- Un OB bear est une zone de distribution (résistance). Quand le prix
  casse au-dessus (invalidation), cette zone devient une zone d'ACCUMULATION
  (support) — c'est un Breaker Block bull.

C'est un concept avancé ICT très puissant car les Breakers sont
des zones où les institutionnels ont déjà agi, et quand ces zones
sont invalidées, les stops des traders retail sont concentrés là.

Hiérarchie de zones ICT :
- OB = zone institutionnelle active
- Breaker = OB invalidé → rôle inversé
- Mitigation Block = FVG partiellement fillé → zone revisitée
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.order_block import OrderBlock, check_ob_invalidated
from config.params import ATR_PERIOD

logger = logging.getLogger(__name__)


@dataclass
class BreakerBlock:
    """Breaker Block — OB invalidé qui a changé de rôle."""
    type: str  # "breaker_bull" or "breaker_bear"
    # STRUCTURAL: un breaker_bull était un ob_bear invalidé (résistance → support)
    # STRUCTURAL: un breaker_bear était un ob_bull invalidé (support → résistance)
    breaker_top: float  # Bord supérieur de la zone
    breaker_bottom: float  # Bord inférieur de la zone
    original_ob: OrderBlock  # OB original qui a été invalidé
    invalidate_index: int  # Index où l'OB a été invalidé → Breaker créé
    invalidated_as_breaker: bool = False  # True si le Breaker lui-même est invalidé
    
    @property
    def is_active(self) -> bool:
        """Breaker actif = non invalidé."""
        return not self.invalidated_as_breaker
    
    @property
    def original_type(self) -> str:
        """Type de l'OB original avant invalidation."""
        return self.original_ob.type


def detect_breaker_blocks(
    obs: list[OrderBlock],
    df: pd.DataFrame,
    current_index: int,
) -> list[BreakerBlock]:
    """
    Détecte les Breaker Blocks — OB invalidés qui changent de rôle.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte les Breakers.
    RÈGLE 3 : Breaker est créé au moment de la TRANSITION (invalidation).
    
    Logique :
    - OB_BULL invalidé (close < ob_bottom) → Breaker Block BEAR
      L'ancien support devient résistance
    - OB_BEAR invalidé (close > ob_top) → Breaker Block BULL
      L'ancienne résistance devient support
    
    Args:
        obs: Liste des Order Blocks existants
        df: DataFrame OHLCV
        current_index: Index de la bougie courante
    
    Returns:
        Liste de Breaker Blocks nouvellement créés
    """
    new_breakers = []
    
    # DÉTECTER les OB qui ont JUSTE été invalidés (TRANSITION — Règle 3)
    for ob in obs:
        if ob.invalidated and ob.invalidate_index == current_index:
            # TRANSITION : l'OB vient d'être invalidé à CETTE bougie
            
            if ob.type == "ob_bull":
                # OB Bull invalidé → Breaker Bear (support → résistance)
                breaker = BreakerBlock(
                    type="breaker_bear",
                    breaker_top=ob.ob_top,
                    breaker_bottom=ob.ob_bottom,
                    original_ob=ob,
                    invalidate_index=current_index,
                )
                new_breakers.append(breaker)
                logger.info(
                    f"BREAKER_CREATED | type=breaker_bear | "
                    f"from_ob_type=ob_bull | top={ob.ob_top:.5f} | "
                    f"bottom={ob.ob_bottom:.5f} | "
                    f"reason=ob_bull_invalidated (support → resistance)"
                )
            
            elif ob.type == "ob_bear":
                # OB Bear invalidé → Breaker Bull (résistance → support)
                breaker = BreakerBlock(
                    type="breaker_bull",
                    breaker_top=ob.ob_top,
                    breaker_bottom=ob.ob_bottom,
                    original_ob=ob,
                    invalidate_index=current_index,
                )
                new_breakers.append(breaker)
                logger.info(
                    f"BREAKER_CREATED | type=breaker_bull | "
                    f"from_ob_type=ob_bear | top={ob.ob_top:.5f} | "
                    f"bottom={ob.ob_bottom:.5f} | "
                    f"reason=ob_bear_invalidated (resistance → support)"
                )
    
    if new_breakers:
        logger.info(
            f"BREAKER_DETECT_COMPLETE | new_breakers={len(new_breakers)} | "
            f"breaker_bull={sum(1 for b in new_breakers if b.type == 'breaker_bull')} | "
            f"breaker_bear={sum(1 for b in new_breakers if b.type == 'breaker_bear')}"
        )
    
    return new_breakers


def check_breaker_invalidated(
    breakers: list[BreakerBlock],
    df: pd.DataFrame,
    current_index: int,
) -> list[BreakerBlock]:
    """
    Vérifie si des Breaker Blocks actifs ont été invalidés.
    
    Breaker Bull invalidé : close < breaker_bottom
    Breaker Bear invalidé : close > breaker_top
    
    RÈGLE 3 : Invalidation sur TRANSITION uniquement.
    """
    updated = []
    
    if current_index >= len(df):
        return breakers
    
    for breaker in breakers:
        if breaker.invalidated_as_breaker:
            updated.append(breaker)
            continue
        
        current_close = df["close"].iloc[current_index]
        prev_close = df["close"].iloc[current_index - 1] if current_index >= 1 else current_close
        
        # Breaker Bull invalidé : close passe en-dessous du breaker
        if breaker.type == "breaker_bull":
            condition_now = current_close < breaker.breaker_bottom
            condition_prev = prev_close < breaker.breaker_bottom
            
            if condition_now and not condition_prev:
                breaker.invalidated_as_breaker = True
                logger.info(
                    f"BREAKER_INVALIDATED | type=breaker_bull | "
                    f"bottom={breaker.breaker_bottom:.5f} | "
                    f"close={current_close:.5f} | index={current_index}"
                )
        
        # Breaker Bear invalidé : close passe au-dessus du breaker
        elif breaker.type == "breaker_bear":
            condition_now = current_close > breaker.breaker_top
            condition_prev = prev_close > breaker.breaker_top
            
            if condition_now and not condition_prev:
                breaker.invalidated_as_breaker = True
                logger.info(
                    f"BREAKER_INVALIDATED | type=breaker_bear | "
                    f"top={breaker.breaker_top:.5f} | "
                    f"close={current_close:.5f} | index={current_index}"
                )
        
        updated.append(breaker)
    
    return updated


def find_breaker_at_price(
    breakers: list[BreakerBlock],
    price: float,
    direction: str,
) -> Optional[BreakerBlock]:
    """
    Trouve le Breaker Block actif le plus proche du prix.
    
    Pour un LONG : cherche Breaker Bull en-dessous du prix (zone d'entrée en support)
    Pour un SHORT : cherche Breaker Bear au-dessus du prix (zone d'entrée en résistance)
    """
    active = [b for b in breakers if b.is_active]
    
    if direction == "long":
        # Breaker Bull en-dessous du prix
        candidates = [b for b in active if b.type == "breaker_bull" and b.breaker_top <= price]
        if candidates:
            return max(candidates, key=lambda b: b.breaker_top)
    
    elif direction == "short":
        # Breaker Bear au-dessus du prix
        candidates = [b for b in active if b.type == "breaker_bear" and b.breaker_bottom >= price]
        if candidates:
            return min(candidates, key=lambda b: b.breaker_bottom)
    
    return None
