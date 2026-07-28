"""
Order Block (OB) detection — Bot SMC/ICT v2.

RÈGLE 1 : detect_ob() est la SEULE fonction pour la détection des OB.
RÈGLE 4 : Pas de seuils fixes. OB_MIN_MOVE_ATR depuis config.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.params import OB_MIN_MOVE_ATR, ATR_PERIOD
from core.signal_types import SignalType

logger = logging.getLogger(__name__)


# =============================================================================
# Types de données
# =============================================================================

@dataclass
class OrderBlock:
    """Order Block détecté."""
    type: str  # "ob_bull" or "ob_bear"
    ob_top: float  # Bord supérieur de la zone OB
    ob_bottom: float  # Bord inférieur de la zone OB
    created_index: int  # Index de la bougie OB
    created_timestamp: pd.Timestamp
    move_displacement_atr: float  # DYNAMIC: displacement du mouvement qui suit
    invalidated: bool = False  # True si le prix a traversé la zone
    invalidate_index: Optional[int] = None
    
    def __post_init__(self):
        if self.type not in ("ob_bull", "ob_bear"):
            raise ValueError(f"Type OB invalide: {self.type}")
        if self.ob_top <= self.ob_bottom:
            raise ValueError(f"OB invalide: top={self.ob_top} <= bottom={self.ob_bottom}")
    
    @property
    def is_active(self) -> bool:
        """OB actif = non invalidé."""
        return not self.invalidated
    
    @property
    def signal_type(self) -> SignalType:
        return SignalType.OB_BULL if self.type == "ob_bull" else SignalType.OB_BEAR


# =============================================================================
# Détection des Order Blocks
# =============================================================================

def detect_ob(df: pd.DataFrame, start_index: int = 0) -> list[OrderBlock]:
    """
    Détecte tous les Order Blocks dans les données.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui détecte les OB.
    
    OB_BULL (zone d'accumulation) :
      1. La bougie i est DÉCLINAISON (close < open)
      2. Le mouvement suivant est haussier et fort :
         (high[i+2] - low[i]) / ATR >= OB_MIN_MOVE_ATR (DYNAMIC)
      3. La zone OB = [open[i], low[i]] (ouverture au top, plus bas au bottom)
    
    OB_BEAR (zone de distribution) :
      1. La bougie i est haussière (close > open)
      2. Le mouvement suivant est baissier et fort :
         (high[i] - low[i+2]) / ATR >= OB_MIN_MOVE_ATR (DYNAMIC)
      3. La zone OB = [high[i], open[i]] (plus haut au top, ouverture au bottom)
    
    Args:
        df: DataFrame OHLCV
        start_index: Index de départ
    
    Returns:
        Liste d'OB détectés
    """
    obs = []
    
    if len(df) < 3:
        logger.warning(f"OB_DETECT | reason=insufficient_data | bars={len(df)} | need=3")
        return obs
    
    # Calcul de l'ATR pour chaque bougie (DYNAMIC)
    atr_values = _calculate_atr_series(df)
    
    for i in range(max(1, start_index), len(df) - 2):
        atr = atr_values.iloc[i] if i < len(atr_values) else 0.0001  # STRUCTURAL: fallback minimal non-zero pour éviter division par zéro
        
        if atr <= 0:
            continue
        
        current_open = df["open"].iloc[i]
        current_close = df["close"].iloc[i]
        current_high = df["high"].iloc[i]
        current_low = df["low"].iloc[i]
        
        # OB_BULL : bougie bearish suivie d'un mouvement haussier fort
        is_bearish = current_close < current_open
        
        if is_bearish:
            # Mesurer le mouvement haussier qui suit
            # DYNAMIC: le mouvement doit être >= OB_MIN_MOVE_ATR en ATR
            move_up = (df["high"].iloc[i + 2] - current_low) / atr
            
            if move_up >= OB_MIN_MOVE_ATR:
                # Confirmer avec la bougie suivante (au moins 1 bullish)
                next_bullish = df["close"].iloc[i + 1] > df["open"].iloc[i + 1]
                
                if next_bullish:
                    ob = OrderBlock(
                        type="ob_bull",
                        ob_top=current_open,  # Open de la bougie bearish = top
                        ob_bottom=current_low,  # Low de la bougie bearish = bottom
                        created_index=i,
                        created_timestamp=df.index[i],
                        move_displacement_atr=move_up,
                    )
                    obs.append(ob)
                    logger.info(
                        f"OB_BULL | index={i} | top={current_open:.5f} | "
                        f"bottom={current_low:.5f} | displacement={move_up:.2f}"
                    )
        
        # OB_BEAR : bougie bullish suivie d'un mouvement baissier fort
        is_bullish = current_close > current_open
        
        if is_bullish:
            move_down = (current_high - df["low"].iloc[i + 2]) / atr
            
            if move_down >= OB_MIN_MOVE_ATR:
                next_bearish = df["close"].iloc[i + 1] < df["open"].iloc[i + 1]
                
                if next_bearish:
                    ob = OrderBlock(
                        type="ob_bear",
                        ob_top=current_high,  # High de la bougie bullish = top
                        ob_bottom=current_open,  # Open de la bougie bullish = bottom
                        created_index=i,
                        created_timestamp=df.index[i],
                        move_displacement_atr=move_down,
                    )
                    obs.append(ob)
                    logger.info(
                        f"OB_BEAR | index={i} | top={current_high:.5f} | "
                        f"bottom={current_open:.5f} | displacement={move_down:.2f}"
                    )
    
    logger.info(
        f"OB_DETECT_COMPLETE | total={len(obs)} | "
        f"bull={sum(1 for o in obs if o.type == 'ob_bull')} | "
        f"bear={sum(1 for o in obs if o.type == 'ob_bear')}"
    )
    
    return obs


# =============================================================================
# Validation des OB (invalidation)
# =============================================================================

def check_ob_invalidated(obs: list[OrderBlock], df: pd.DataFrame, current_index: int) -> list[OrderBlock]:
    """
    Vérifie si des OB actifs ont été invalidés à la bougie courante.
    
    OB_BULL invalidé : close[current] < ob_bottom (le prix a cassé en-dessous)
    OB_BEAR invalidé : close[current] > ob_top (le prix a cassé au-dessus)
    """
    updated = []
    
    for ob in obs:
        if ob.invalidated:
            updated.append(ob)
            continue
        
        if current_index >= len(df):
            updated.append(ob)
            continue
        
        current_close = df["close"].iloc[current_index]
        
        if ob.type == "ob_bull" and current_close < ob.ob_bottom:
            ob.invalidated = True
            ob.invalidate_index = current_index
            logger.info(
                f"OB_INVALIDATED | type=bull | created_index={ob.created_index} | "
                f"invalidate_index={current_index} | "
                f"close={current_close:.5f} < ob_bottom={ob.ob_bottom:.5f}"
            )
        
        elif ob.type == "ob_bear" and current_close > ob.ob_top:
            ob.invalidated = True
            ob.invalidate_index = current_index
            logger.info(
                f"OB_INVALIDATED | type=bear | created_index={ob.created_index} | "
                f"invalidate_index={current_index} | "
                f"close={current_close:.5f} > ob_top={ob.ob_top:.5f}"
            )
        
        updated.append(ob)
    
    return updated


def find_ob_at_price(obs: list[OrderBlock], price: float, direction: str) -> Optional[OrderBlock]:
    """
    Trouve l'OB actif le plus proche du prix, dans la direction du trade.
    
    Pour un LONG : cherche OB bull en-dessous du prix (zone d'entrée en discount)
    Pour un SHORT : cherche OB bear au-dessus du prix (zone d'entrée en premium)
    """
    active_obs = [o for o in obs if o.is_active]
    
    if direction == "long":
        # OB bull en-dessous du prix
        candidates = [o for o in active_obs if o.type == "ob_bull" and o.ob_top <= price]
        if candidates:
            return max(candidates, key=lambda o: o.ob_top)
    
    elif direction == "short":
        # OB bear au-dessus du prix
        candidates = [o for o in active_obs if o.type == "ob_bear" and o.ob_bottom >= price]
        if candidates:
            return min(candidates, key=lambda o: o.ob_bottom)
    
    return None


# =============================================================================
# Helpers
# =============================================================================

def _calculate_atr_series(df: pd.DataFrame) -> pd.Series:
    """Calcul de l'ATR pour chaque bougie."""
    period = ATR_PERIOD  # STRUCTURAL
    
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr.fillna(0.0001)  # STRUCTURAL: fallback
