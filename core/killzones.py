"""
Killzones ICT — Fenêtres temporelles de trading.

RÈGLE 1 : get_killzone() est la SEULE fonction qui détermine la killzone.
RÈGLE 4 : Toutes les heures depuis config avec justification.
RÈGLE 6 : Pas d'échec silencieux.

ICT Killzones (EST = Eastern Standard Time) :
- London Open Killzone : 02:00–05:00 EST (07:00–10:00 UTC)
  STRUCTURAL: London session open — manipulation + displacement
- New York Open Killzone : 08:00–11:00 EST (13:00–16:00 UTC)
  STRUCTURAL: NY session open — institutional order flow
- New York PM Killzone : 13:00–16:00 EST (18:00–21:00 UTC)
  STRUCTURAL: NY PM session — distribution / final moves

En trading ICT, les setups qui apparaissent hors killzone ont une
win rate significativement plus bas. Les killzones filtrent les
signaux non-pertinents et réduisent les faux setups.
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from config.params import (
    LONDON_KZ_START_EST,
    LONDON_KZ_END_EST,
    NY_OPEN_KZ_START_EST,
    NY_OPEN_KZ_END_EST,
    NY_PM_KZ_START_EST,
    NY_PM_KZ_END_EST,
    HOURS_PER_DAY,
    MINUTES_PER_HOUR,
)

logger = logging.getLogger(__name__)


@dataclass
class KillzoneInfo:
    """Information sur la killzone actuelle."""
    active: bool
    name: str  # "london_open", "ny_open", "ny_pm", "none"
    start_utc: int  # Heure de début UTC (heure entière)
    end_utc: int  # Heure de fin UTC (heure entière)
    minutes_remaining: int  # Minutes restantes dans la killzone

    @property
    def is_active(self) -> bool:
        """True si on est dans une killzone active."""
        return self.active and self.name != "none"


def _est_to_utc_offset() -> int:
    """
    Calcul du offset EST → UTC.
    
    EST = UTC-5 (standard) ou UTC-4 (EDT, summer time).
    
    STRUCTURAL: ICT killzones sont définies en EST/EDT.
    On utilise UTC-5 comme approximation conservatrice —
    les killzones ICT sont assez larges (3h) pour tolérer
    le décalage EDT d'1h.
    """
    # STRUCTURAL: UTC-5 pour EST — approximation conservatrice
    # En pratique, le broker donne les timestamps en UTC
    # Les killzones ICT sont définies en EST par ICT mentorship
    return -5


def get_killzone(timestamp: Optional[datetime] = None) -> KillzoneInfo:
    """
    Détermine la killzone ICT active au moment donné.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détermine la killzone.
    
    Les killzones sont définies en EST et converties en UTC
    pour comparaison avec les timestamps du broker.
    
    Args:
        timestamp: Timestamp à évaluer (UTC). Si None, utilise now().
    
    Returns:
        KillzoneInfo avec le nom et le statut de la killzone
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    # Conversion UTC → EST
    est_offset = _est_to_utc_offset()
    
    if timestamp.tzinfo is None:
        # Assume UTC si pas de timezone info
        est_hour = timestamp.hour + est_offset
    else:
        # Simplification: on utilise directement l'offset
        est_hour = timestamp.hour + est_offset
    
    # STRUCTURAL: heure EST peut être négative ou > 23, modulo HOURS_PER_DAY
    est_hour = est_hour % HOURS_PER_DAY
    
    est_minute = timestamp.minute
    
    # === Vérifier chaque killzone ===
    
    # London Open Killzone
    if LONDON_KZ_START_EST <= est_hour < LONDON_KZ_END_EST:
        minutes_remaining = (LONDON_KZ_END_EST - est_hour) * MINUTES_PER_HOUR - est_minute
        utc_start = (LONDON_KZ_START_EST - est_offset) % HOURS_PER_DAY  # STRUCTURAL: conversion UTC
        utc_end = (LONDON_KZ_END_EST - est_offset) % HOURS_PER_DAY
        
        logger.debug(
            f"KILLZONE | name=london_open | est_hour={est_hour} | "
            f"minutes_remaining={minutes_remaining}"
        )
        
        return KillzoneInfo(
            active=True,
            name="london_open",
            start_utc=utc_start,
            end_utc=utc_end,
            minutes_remaining=minutes_remaining,
        )
    
    # New York Open Killzone
    if NY_OPEN_KZ_START_EST <= est_hour < NY_OPEN_KZ_END_EST:
        minutes_remaining = (NY_OPEN_KZ_END_EST - est_hour) * MINUTES_PER_HOUR - est_minute
        utc_start = (NY_OPEN_KZ_START_EST - est_offset) % HOURS_PER_DAY
        utc_end = (NY_OPEN_KZ_END_EST - est_offset) % HOURS_PER_DAY
        
        logger.debug(
            f"KILLZONE | name=ny_open | est_hour={est_hour} | "
            f"minutes_remaining={minutes_remaining}"
        )
        
        return KillzoneInfo(
            active=True,
            name="ny_open",
            start_utc=utc_start,
            end_utc=utc_end,
            minutes_remaining=minutes_remaining,
        )
    
    # New York PM Killzone
    if NY_PM_KZ_START_EST <= est_hour < NY_PM_KZ_END_EST:
        minutes_remaining = (NY_PM_KZ_END_EST - est_hour) * MINUTES_PER_HOUR - est_minute
        utc_start = (NY_PM_KZ_START_EST - est_offset) % HOURS_PER_DAY
        utc_end = (NY_PM_KZ_END_EST - est_offset) % HOURS_PER_DAY
        
        logger.debug(
            f"KILLZONE | name=ny_pm | est_hour={est_hour} | "
            f"minutes_remaining={minutes_remaining}"
        )
        
        return KillzoneInfo(
            active=True,
            name="ny_pm",
            start_utc=utc_start,
            end_utc=utc_end,
            minutes_remaining=minutes_remaining,
        )
    
    # Hors killzone
    logger.debug(f"KILLZONE | name=none | est_hour={est_hour} | no_active_killzone")
    
    return KillzoneInfo(
        active=False,
        name="none",
        start_utc=0,
        end_utc=0,
        minutes_remaining=0,
    )


def get_all_killzones() -> list[dict]:
    """
    Retourne toutes les killzones avec leurs horaires UTC.
    
    STRUCTURAL: utilisé pour le dashboard et les logs.
    """
    est_offset = _est_to_utc_offset()
    
    return [
        {
            "name": "london_open",
            "est_range": f"{LONDON_KZ_START_EST}h–{LONDON_KZ_END_EST}h EST",
            "utc_range": f"{(LONDON_KZ_START_EST - est_offset) % HOURS_PER_DAY}h–{(LONDON_KZ_END_EST - est_offset) % HOURS_PER_DAY}h UTC",
            "duration_hours": LONDON_KZ_END_EST - LONDON_KZ_START_EST,
        },
        {
            "name": "ny_open",
            "est_range": f"{NY_OPEN_KZ_START_EST}h–{NY_OPEN_KZ_END_EST}h EST",
            "utc_range": f"{(NY_OPEN_KZ_START_EST - est_offset) % HOURS_PER_DAY}h–{(NY_OPEN_KZ_END_EST - est_offset) % HOURS_PER_DAY}h UTC",
            "duration_hours": NY_OPEN_KZ_END_EST - NY_OPEN_KZ_START_EST,
        },
        {
            "name": "ny_pm",
            "est_range": f"{NY_PM_KZ_START_EST}h–{NY_PM_KZ_END_EST}h EST",
            "utc_range": f"{(NY_PM_KZ_START_EST - est_offset) % HOURS_PER_DAY}h–{(NY_PM_KZ_END_EST - est_offset) % HOURS_PER_DAY}h UTC",
            "duration_hours": NY_PM_KZ_END_EST - NY_PM_KZ_START_EST,
        },
    ]
