"""
Zones Premium/Discount — Bot SMC/ICT v2.

RÈGLE 1 : get_zone() est la SEULE fonction pour les zones.
RÈGLE 4 : Paramètres depuis config (EQUILIBRIUM_RATIO, thresholds).
"""

import logging
from dataclasses import dataclass
from typing import Optional

from config.params import EQUILIBRIUM_RATIO, PREMIUM_THRESHOLD, DISCOUNT_THRESHOLD
from core.structure import Swing

logger = logging.getLogger(__name__)


@dataclass
class PriceZone:
    """Zone de prix (premium/discount)."""
    zone: str  # "premium", "discount", "equilibrium"
    ratio: float  # Position dans le range (0.0 à 1.0)
    swing_high_price: float
    swing_low_price: float


def get_zone(price: float, swing_high: Optional[Swing], swing_low: Optional[Swing]) -> PriceZone:
    """
    Détermine la zone de prix (premium/discount) relative aux swings.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui calcule les zones.
    RÈGLE 4 : Thresholds depuis config.
    
    Premium : prix > PREMIUM_THRESHOLD du range (0.79)
    Discount : prix < DISCOUNT_THRESHOLD du range (0.21)
    Equilibrium : entre les deux
    
    Args:
        price: Prix actuel
        swing_high: Swing high structurel le plus récent
        swing_low: Swing low structurel le plus récent
    
    Returns:
        PriceZone avec la zone et le ratio
    """
    if swing_high is None or swing_low is None:
        logger.warning(f"ZONE | reason=no_swings | returning equilibrium")
        return PriceZone(
            zone="equilibrium",
            ratio=EQUILIBRIUM_RATIO,
            swing_high_price=0,
            swing_low_price=0,
        )
    
    range_size = swing_high.price - swing_low.price
    
    if range_size <= 0:
        logger.warning(f"ZONE | reason=zero_range | high={swing_high.price} | low={swing_low.price}")
        return PriceZone(
            zone="equilibrium",
            ratio=EQUILIBRIUM_RATIO,
            swing_high_price=swing_high.price,
            swing_low_price=swing_low.price,
        )
    
    # DYNAMIC: ratio calculé à partir des swings
    ratio = (price - swing_low.price) / range_size
    
    if ratio >= PREMIUM_THRESHOLD:
        zone = "premium"
    elif ratio <= DISCOUNT_THRESHOLD:
        zone = "discount"
    else:
        zone = "equilibrium"
    
    logger.debug(
        f"ZONE | zone={zone} | ratio={ratio:.2f} | "
        f"price={price:.5f} | high={swing_high.price:.5f} | low={swing_low.price:.5f}"
    )
    
    return PriceZone(
        zone=zone,
        ratio=ratio,
        swing_high_price=swing_high.price,
        swing_low_price=swing_low.price,
    )
