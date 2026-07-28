"""
Calcul de SL/TP — Bot SMC/ICT v2.

RÈGLE 1 : C'EST LA SEULE fonction qui calcule le SL/TP.
Aucune autre fonction ne doit calculer un SL ou un TP.

Algorithme :
1. Trouver les niveaux structurels (liquidity, OB, FVG)
2. SL = niveau structurel + buffer ATR
3. TP = niveau de liquidité opposé ou extension Fibonacci
4. Si pas de niveau structurel → fallback ATR
5. Vérifier RR >= RR_MINIMUM
"""

import logging
from dataclasses import dataclass
from typing import Optional

from config.params import (
    SL_BUFFER_ATR,
    SL_DEFAULT_ATR_MULTIPLIER,
    RR_MINIMUM,
    PIP_SIZE,
    EQUILIBRIUM_RATIO,
)
from core.signal_types import Signal, SignalDirection
from core.liquidity import LiquidityLevel
from core.fvg import FVG
from core.order_block import OrderBlock
from core.structure import Swing

logger = logging.getLogger(__name__)


@dataclass
class SLTPResult:
    """Résultat du calcul SL/TP."""
    sl: float
    tp: float
    sl_method: str
    tp_method: str
    sl_distance_atr: float
    tp_distance_atr: float
    rr_ratio: float
    
    def __post_init__(self):
        if self.sl <= 0 or self.tp <= 0:
            raise ValueError(f"SL/TP invalide: sl={self.sl}, tp={self.tp}")
        if self.rr_ratio <= 0:
            raise ValueError(f"RR ratio invalide: {self.rr_ratio}")


def calculate_sl_tp(
    signal: Signal,
    atr: float,
    # Niveaux structurels (passés par signal_detector)
    liquidity_below: Optional[LiquidityLevel] = None,
    liquidity_above: Optional[LiquidityLevel] = None,
    fvg_entry: Optional[FVG] = None,
    ob_entry: Optional[OrderBlock] = None,
    swing_low: Optional[float] = None,
    swing_high: Optional[float] = None,
    # Contrainte broker (couche successive — Règle 1 : loggue avant/après)
    broker_min_distance: Optional[float] = None,
) -> SLTPResult:
    """
    Calcule le SL/TP pour un signal donné.
    
    RÈGLE 1 : C'EST LA SEULE FONCTION DE CALCUL SL/TP DU PROJET.
    
    Priorités SL :
    1. Sweep → SL derrière le niveau sweepé
    2. OB entry → SL derrière l'OB (bord opposé + buffer)
    3. FVG entry → SL derrière le FVG (bord opposé + buffer)
    4. Liquidity → SL derrière le niveau de liquidité + buffer
    5. Fallback → SL = entry ± ATR * SL_DEFAULT_ATR_MULTIPLIER
    
    Priorités TP :
    1. Liquidity opposée (niveau de liquidité à cibler)
    2. Extension Fibonacci 1.618
    3. Fallback → TP = entry ± 2 * (entry - SL)
    
    Args:
        signal: Signal d'entrée
        atr: ATR au moment du signal
        liquidity_below: Niveau de liquidité en-dessous
        liquidity_above: Niveau de liquidité au-dessus
        fvg_entry: FVG dans la zone d'entrée
        ob_entry: OB dans la zone d'entrée
        swing_low: Dernier swing low
        swing_high: Dernier swing high
        broker_min_distance: Distance minimum broker
    
    Returns:
        SLTPResult ou None si RR < minimum
    """
    if atr <= 0:
        logger.error(f"SLTP_REJECT | reason=atr_invalid | atr={atr}")
        raise ValueError(f"ATR invalide: {atr}")
    
    buffer = atr * SL_BUFFER_ATR  # DYNAMIC: buffer = 10% de l'ATR
    
    # === Calcul du SL ===
    sl, sl_method = _calculate_sl(
        signal, atr, buffer,
        liquidity_below, liquidity_above,
        fvg_entry, ob_entry,
        swing_low, swing_high,
    )
    
    # === Calcul du TP ===
    tp, tp_method = _calculate_tp(
        signal, atr, sl,
        liquidity_below, liquidity_above,
        swing_low, swing_high,
    )
    
    # === Ajustement broker (couche successive — Règle 1) ===
    if broker_min_distance is not None:
        sl_before = sl
        tp_before = tp
        
        if signal.direction == SignalDirection.LONG:
            if signal.price - sl < broker_min_distance:
                sl = signal.price - broker_min_distance
                logger.warning(
                    f"SL_ADJUST | layer=broker_constraint | direction=long | "
                    f"before={sl_before:.5f} | after={sl:.5f} | reason=broker_min_distance"
                )
            if tp - signal.price < broker_min_distance:
                tp = signal.price + broker_min_distance
                logger.warning(
                    f"TP_ADJUST | layer=broker_constraint | direction=long | "
                    f"before={tp_before:.5f} | after={tp:.5f} | reason=broker_min_distance"
                )
        elif signal.direction == SignalDirection.SHORT:
            if sl - signal.price < broker_min_distance:
                sl = signal.price + broker_min_distance
                logger.warning(
                    f"SL_ADJUST | layer=broker_constraint | direction=short | "
                    f"before={sl_before:.5f} | after={sl:.5f} | reason=broker_min_distance"
                )
            if signal.price - tp < broker_min_distance:
                tp = signal.price - broker_min_distance
                logger.warning(
                    f"TP_ADJUST | layer=broker_constraint | direction=short | "
                    f"before={tp_before:.5f} | after={tp:.5f} | reason=broker_min_distance"
                )
    
    # === Calcul distances et RR ===
    sl_distance = abs(signal.price - sl)
    tp_distance = abs(tp - signal.price)
    sl_distance_atr = sl_distance / atr
    tp_distance_atr = tp_distance / atr
    rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0
    
    # === Vérification RR minimum ===
    if rr_ratio < RR_MINIMUM:
        logger.warning(
            f"SLTP_REJECT | reason=rr_below_minimum | rr={rr_ratio:.2f} | "
            f"minimum={RR_MINIMUM} | sl_method={sl_method} | tp_method={tp_method}"
        )
        return None
    
    result = SLTPResult(
        sl=sl,
        tp=tp,
        sl_method=sl_method,
        tp_method=tp_method,
        sl_distance_atr=sl_distance_atr,
        tp_distance_atr=tp_distance_atr,
        rr_ratio=rr_ratio,
    )
    
    logger.info(
        f"SLTP_CALC | direction={signal.direction.value} | "
        f"entry={signal.price:.5f} | sl={sl:.5f} | tp={tp:.5f} | "
        f"sl_method={sl_method} | tp_method={tp_method} | "
        f"sl_atr={sl_distance_atr:.2f} | tp_atr={tp_distance_atr:.2f} | "
        f"rr={rr_ratio:.2f}"
    )
    
    return result


def _calculate_sl(
    signal: Signal,
    atr: float,
    buffer: float,
    liquidity_below: Optional[LiquidityLevel],
    liquidity_above: Optional[LiquidityLevel],
    fvg_entry: Optional[FVG],
    ob_entry: Optional[OrderBlock],
    swing_low: Optional[float],
    swing_high: Optional[float],
) -> tuple[float, str]:
    """
    Calcule le SL avec priorités structurelles.
    
    Priorités (LONG) :
    1. OB entry → SL = ob_bottom - buffer
    2. FVG entry → SL = fvg_bottom - buffer
    3. Liquidity below → SL = level.price - buffer
    4. Swing low → SL = swing_low - buffer
    5. Fallback → SL = entry - atr * multiplier
    
    Priorités (SHORT) : inversée
    """
    if signal.direction == SignalDirection.LONG:
        # 1. OB entry
        if ob_entry is not None:
            sl = ob_entry.ob_bottom - buffer
            method = "ob_bottom"
            logger.debug(f"SL_SOURCE | method=ob_bottom | sl={sl:.5f}")
            return sl, method
        
        # 2. FVG entry
        if fvg_entry is not None:
            sl = fvg_entry.gap_bottom - buffer
            method = "fvg_bottom"
            logger.debug(f"SL_SOURCE | method=fvg_bottom | sl={sl:.5f}")
            return sl, method
        
        # 3. Liquidity below
        if liquidity_below is not None:
            sl = liquidity_below.price - buffer
            method = "liquidity_below"
            logger.debug(f"SL_SOURCE | method=liquidity_below | sl={sl:.5f}")
            return sl, method
        
        # 4. Swing low
        if swing_low is not None:
            sl = swing_low - buffer
            method = "swing_low"
            logger.debug(f"SL_SOURCE | method=swing_low | sl={sl:.5f}")
            return sl, method
        
        # 5. Fallback
        sl = signal.price - atr * SL_DEFAULT_ATR_MULTIPLIER
        method = "atr_default"
        logger.debug(f"SL_SOURCE | method=atr_default | sl={sl:.5f}")
        return sl, method
    
    elif signal.direction == SignalDirection.SHORT:
        # 1. OB entry
        if ob_entry is not None:
            sl = ob_entry.ob_top + buffer
            method = "ob_top"
            return sl, method
        
        # 2. FVG entry
        if fvg_entry is not None:
            sl = fvg_entry.gap_top + buffer
            method = "fvg_top"
            return sl, method
        
        # 3. Liquidity above
        if liquidity_above is not None:
            sl = liquidity_above.price + buffer
            method = "liquidity_above"
            return sl, method
        
        # 4. Swing high
        if swing_high is not None:
            sl = swing_high + buffer
            method = "swing_high"
            return sl, method
        
        # 5. Fallback
        sl = signal.price + atr * SL_DEFAULT_ATR_MULTIPLIER
        method = "atr_default"
        return sl, method
    
    # Impossible
    sl = signal.price - atr * SL_DEFAULT_ATR_MULTIPLIER
    method = "unknown_direction"
    return sl, method


def _calculate_tp(
    signal: Signal,
    atr: float,
    sl: float,
    liquidity_below: Optional[LiquidityLevel],
    liquidity_above: Optional[LiquidityLevel],
    swing_low: Optional[float],
    swing_high: Optional[float],
) -> tuple[float, str]:
    """
    Calcule le TP avec priorités structurelles.
    
    Priorités (LONG) :
    1. Liquidity above (niveau de liquidité à cibler)
    2. Extension Fibonacci 1.618
    3. Fallback → TP = entry + 2 * (entry - SL)
    
    Priorités (SHORT) : inversée
    """
    sl_distance = abs(signal.price - sl)
    
    if signal.direction == SignalDirection.LONG:
        # 1. Liquidity above
        if liquidity_above is not None:
            tp = liquidity_above.price
            method = "liquidity_above"
            return tp, method
        
        # 2. Fibonacci extension 1.618
        if swing_low is not None and swing_high is not None:
            range_size = swing_high - swing_low
            tp = swing_low + range_size * 1.618  # STRUCTURAL: Fibonacci extension 1.618 — standard ICT target
            method = "fib_1.618"
            return tp, method
        
        # 3. Fallback → RR 2:1 minimum
        tp = signal.price + sl_distance * 2.0
        method = "rr_2x"
        return tp, method
    
    elif signal.direction == SignalDirection.SHORT:
        # 1. Liquidity below
        if liquidity_below is not None:
            tp = liquidity_below.price
            method = "liquidity_below"
            return tp, method
        
        # 2. Fibonacci extension 1.618
        if swing_low is not None and swing_high is not None:
            range_size = swing_high - swing_low
            tp = swing_high - range_size * 1.618  # STRUCTURAL: Fibonacci extension 1.618 — standard ICT target
            method = "fib_1.618"
            return tp, method
        
        # 3. Fallback → RR 2:1 minimum
        tp = signal.price - sl_distance * 2.0
        method = "rr_2x"
        return tp, method
    
    tp = signal.price + sl_distance * 2.0
    method = "unknown_direction"
    return tp, method
