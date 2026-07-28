"""
PDHL — Previous Day/Week High/Low comme niveaux de liquidité.

RÈGLE 1 : compute_pdhl() est la SEULE fonction qui calcule les PDHL.
RÈGLE 4 : Pas de seuils fixes. Paramètres depuis config.
RÈGLE 6 : Pas d'échec silencieux.

ICT utilise les PDH/PDL (Previous Day High/Low) et PWH/PWL 
(Previous Week High/Low) comme NIVEAUX DE LIQUIDITÉ MAJEURS.

Ces niveaux sont les zones où les stops institutionnels sont
concentrés. Un sweep de PDHL est un setup très haute probabilité.

Structure :
- PDH = high de la journée précédente (stops longs au-dessus)
- PDL = low de la journée précédente (stops shorts en-dessous)
- PWH = high de la semaine précédente (liquidité majeure)
- PWL = low de la semaine précédente (liquidité majeure)
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import PDHL_EQUAL_TOLERANCE_ATR, ATR_PERIOD

logger = logging.getLogger(__name__)


@dataclass
class PDHLLevel:
    """Niveau PDHL (Previous Day/Week High/Low)."""
    type: str  # "pdh", "pdl", "pwh", "pwl"
    price: float
    date: pd.Timestamp  # Date du jour qui a créé ce niveau
    swept: bool = False
    sweep_index: Optional[int] = None

    @property
    def direction(self) -> str:
        """Direction de la liquidité."""
        if self.type in ("pdh", "pwh"):
            return "above"  # Stops longs au-dessus
        elif self.type in ("pdl", "pwl"):
            return "below"  # Stops shorts en-dessous
        return "unknown"


def compute_pdhl(df: pd.DataFrame) -> list[PDHLLevel]:
    """
    Calcule les PDHL depuis les données OHLCV.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui calcule les PDHL.
    
    Algorithme :
    1. Identifier les journées dans les données (groupement par date)
    2. Pour chaque journée : high = PDH, low = PDL
    3. Le PDH/PDL du jour J = high/low du jour J-1
    4. PWH/PWL = high/low de la semaine précédente
    
    Args:
        df: DataFrame OHLCV avec index timestamp
    
    Returns:
        Liste de PDHLLevel (PDH, PDL pour chaque journée)
    """
    levels = []
    
    if len(df) < 2:
        logger.warning(f"PDHL | reason=insufficient_data | bars={len(df)} | need=2+")
        return levels
    
    # Vérifier que l'index est un DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        logger.warning("PDHL | reason=no_datetime_index | attempting to convert")
        return levels
    
    # Grouper par jour
    try:
        daily = df.groupby(df.index.date).agg({
            "high": "max",
            "low": "min",
            "close": "last",
        })
    except Exception as e:
        logger.error(f"PDHL_GROUPBY_ERROR | error={e}", exc_info=True)
        return levels
    
    if len(daily) < 2:
        logger.warning(f"PDHL | reason=insufficient_days | days={len(daily)} | need=2+")
        return levels
    
    # Calculer PDH/PDL pour chaque journée (à partir du jour précédent)
    daily_dates = list(daily.index)
    
    for i in range(1, len(daily_dates)):
        prev_date = daily_dates[i - 1]
        current_date = daily_dates[i]
        
        prev_high = daily.loc[prev_date, "high"]
        prev_low = daily.loc[prev_date, "low"]
        
        # PDH = high du jour précédent
        pdh = PDHLLevel(
            type="pdh",
            price=float(prev_high),
            date=pd.Timestamp(prev_date),
        )
        levels.append(pdh)
        logger.debug(f"PDH | price={prev_high:.5f} | date={prev_date} | current_date={current_date}")
        
        # PDL = low du jour précédent
        pdl = PDHLLevel(
            type="pdl",
            price=float(prev_low),
            date=pd.Timestamp(prev_date),
        )
        levels.append(pdl)
        logger.debug(f"PDL | price={prev_low:.5f} | date={prev_date} | current_date={current_date}")
    
    # PWH/PWL : high/low de la semaine précédente
    # STRUCTURAL: on identifie les semaines dans les données
    try:
        weekly = df.groupby(df.index.to_period("W")).agg({
            "high": "max",
            "low": "min",
        })
        
        if len(weekly) >= 2:
            prev_week = weekly.index[-2]
            pwh_price = float(weekly.loc[prev_week, "high"])
            pwl_price = float(weekly.loc[prev_week, "low"])
            
            pwh = PDHLLevel(
                type="pwh",
                price=pwh_price,
                date=pd.Timestamp(prev_week.start_time),
            )
            levels.append(pwh)
            logger.info(f"PWH | price={pwh_price:.5f} | week={prev_week}")
            
            pwl = PDHLLevel(
                type="pwl",
                price=pwl_price,
                date=pd.Timestamp(prev_week.start_time),
            )
            levels.append(pwl)
            logger.info(f"PWL | price={pwl_price:.5f} | week={prev_week}")
    except Exception as e:
        logger.warning(f"PDHL_WEEKLY_ERROR | error={e} — skipping PWH/PWL")
    
    logger.info(
        f"PDHL_COMPLETE | total={len(levels)} | "
        f"pdh={sum(1 for l in levels if l.type == 'pdh')} | "
        f"pdl={sum(1 for l in levels if l.type == 'pdl')} | "
        f"pwh={sum(1 for l in levels if l.type == 'pwh')} | "
        f"pwl={sum(1 for l in levels if l.type == 'pwl')}"
    )
    
    return levels


def check_pdhl_sweep(
    levels: list[PDHLLevel],
    df: pd.DataFrame,
    current_index: int,
) -> list[PDHLLevel]:
    """
    Vérifie si des PDHL ont été sweepés à la bougie courante.
    
    RÈGLE 3 : Le sweep est détecté au moment de la TRANSITION.
    
    PDH sweepé : mèche dépasse le PDH + close revient en-dessous
    PDL sweepé : mèche dépasse le PDL + close revient au-dessus
    
    Args:
        levels: Liste des PDHL existants
        df: DataFrame OHLCV
        current_index: Index de la bougie courante
    
    Returns:
        Liste mise à jour des PDHL
    """
    if current_index < 1 or current_index >= len(df):
        return levels
    
    updated = []
    
    for level in levels:
        if level.swept:
            updated.append(level)
            continue
        
        current_high = df["high"].iloc[current_index]
        current_low = df["low"].iloc[current_index]
        current_close = df["close"].iloc[current_index]
        prev_high = df["high"].iloc[current_index - 1]
        prev_low = df["low"].iloc[current_index - 1]
        prev_close = df["close"].iloc[current_index - 1]
        
        # PDH/PWH sweepé : mèche dépasse au-dessus, close revient en-dessous
        if level.type in ("pdh", "pwh"):
            swept_now = current_high > level.price and current_close < level.price
            swept_prev = prev_high > level.price and prev_close < level.price
            
            if swept_now and not swept_prev:
                level.swept = True
                level.sweep_index = current_index
                logger.info(
                    f"PDHL_SWEPT | type={level.type} | price={level.price:.5f} | "
                    f"sweep_price={current_high:.5f} | close={current_close:.5f} | "
                    f"index={current_index}"
                )
        
        # PDL/PWL sweepé : mèche dépasse en-dessous, close revient au-dessus
        elif level.type in ("pdl", "pwl"):
            swept_now = current_low < level.price and current_close > level.price
            swept_prev = prev_low < level.price and prev_close > level.price
            
            if swept_now and not swept_prev:
                level.swept = True
                level.sweep_index = current_index
                logger.info(
                    f"PDHL_SWEPT | type={level.type} | price={level.price:.5f} | "
                    f"sweep_price={current_low:.5f} | close={current_close:.5f} | "
                    f"index={current_index}"
                )
        
        updated.append(level)
    
    return updated


def find_nearest_pdhl(
    levels: list[PDHLLevel],
    price: float,
    direction: str,
) -> Optional[PDHLLevel]:
    """
    Trouve le niveau PDHL le plus proche dans une direction.
    
    Pour SL LONG : PDHL en-dessous (PDL/PWL)
    Pour TP LONG : PDHL au-dessus (PDH/PWH)
    Pour SL SHORT : PDHL au-dessus (PDH/PWH)
    Pour TP SHORT : PDHL en-dessous (PDL/PWL)
    """
    active = [l for l in levels if not l.swept]
    
    if direction == "above":
        candidates = [l for l in active if l.price > price]
        return min(candidates, key=lambda l: l.price) if candidates else None
    
    elif direction == "below":
        candidates = [l for l in active if l.price < price]
        return max(candidates, key=lambda l: l.price) if candidates else None
    
    return None
