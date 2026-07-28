"""
Détection de signaux SMC/ICT — Pipeline COMPLET.

RÈGLE 1 : Chaque concept est calculé par son module unique.
RÈGLE 3 : Transition, pas état.
RÈGLE 2 : Ce module est appelé par backtest/engine.py et live/bot.py.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from typing import Optional

import pandas as pd

from core.signal_types import Signal, SignalType, SignalDirection, SignalRegistry
from core.htf_bias import get_htf_bias
from core.structure import detect_swings, detect_bos, detect_choch, determine_trend, Swing
from core.fvg import detect_fvg, check_fvg_filled, find_fvg_at_price, FVG
from core.order_block import detect_ob, check_ob_invalidated, find_ob_at_price, OrderBlock
from core.liquidity import (
    detect_liquidity_levels,
    detect_sweep,
    detect_equal_levels,
    find_nearest_liquidity_level,
    LiquidityLevel,
    LiquiditySweep,
)
from core.displacement import measure_displacement
from core.zones import get_zone, PriceZone
from core.confluence import compute_confluence_score
from config.params import CONFLUENCE_MINIMUM

logger = logging.getLogger(__name__)


class SMCPipeline:
    """
    Pipeline complet de détection SMC/ICT.
    
    Ce pipeline est le CERVEAU du bot. Il agrège toutes les détections
    et produit des signaux avec un score de confluence.
    
    UTILISATION :
    1. Initialiser avec les données
    2. Pour chaque nouvelle bougie : call process_bar()
    3. Si un signal est retourné : passer à sl_tp_calculator puis risk_guard
    """
    
    def __init__(self, df: pd.DataFrame, df_htf: Optional[pd.DataFrame] = None):
        self.df = df
        self.df_htf = df_htf
        self.registry = SignalRegistry()
        
        # State accumulé (persiste entre les bougies)
        self.swings: list[Swing] = []
        self.fvgs: list[FVG] = []
        self.obs: list[OrderBlock] = []
        self.liquidity_levels: list[LiquidityLevel] = []
        self.last_sweep: Optional[LiquiditySweep] = None
        self.current_trend: str = "neutral"
        self.htf_bias: str = "neutral"
        self.last_bos: Optional[str] = None
        self.last_choch: Optional[str] = None
        
        # Initialiser avec les données existantes (warmup)
        self._warmup()
    
    def _warmup(self):
        """
        Initialiser les détections sur les données existantes.
        
        Cela permet d'avoir un état initial (swings, FVG, OB, etc.)
        avant de commencer à traiter les nouvelles bougies.
        """
        if len(self.df) < 10:  # STRUCTURAL: minimum 10 bars for warmup — enough for ATR + basic structure
            logger.warning(f"WARMUP | reason=insufficient_data | bars={len(self.df)}")
            return
        
        # Biais HTF
        if self.df_htf is not None and len(self.df_htf) >= 5:  # STRUCTURAL: minimum 5 HTF bars for bias
            self.htf_bias = get_htf_bias(self.df_htf)
            logger.info(f"WARMUP | htf_bias={self.htf_bias}")
        
        # Swings
        self.swings = detect_swings(self.df)
        self.current_trend = determine_trend(self.swings)
        logger.info(f"WARMUP | trend={self.current_trend} | swings={len(self.swings)}")
        
        # FVG
        self.fvgs = detect_fvg(self.df)
        logger.info(f"WARMUP | fvgs={len(self.fvgs)}")
        
        # Order Blocks
        self.obs = detect_ob(self.df)
        logger.info(f"WARMUP | obs={len(self.obs)}")
        
        # Liquidity
        self.liquidity_levels = detect_liquidity_levels(self.swings, self.df)
        logger.info(f"WARMUP | liquidity_levels={len(self.liquidity_levels)}")
    
    def process_bar(self, index: int) -> Optional[Signal]:
        """
        Traite une bougie et retourne un signal si un setup est détecté.
        
        RÈGLE 3 : Le signal est émis UNIQUEMENT sur la TRANSITION.
        RÈGLE 1 : Chaque concept est calculé par son module unique.
        
        Args:
            index: Index de la bougie à traiter dans self.df
        
        Returns:
            Signal avec confluence si setup détecté, None sinon
        """
        if index < 1 or index >= len(self.df):
            return None
        
        # === 1. Mise à jour des détections ===
        
        # Update FVG (vérifier les fillés + âge)
        self.fvgs = check_fvg_filled(self.fvgs, self.df, index)
        
        # Update OB (vérifier les invalidés)
        self.obs = check_ob_invalidated(self.obs, self.df, index)
        
        # Re-détecter les swings si on a enough data
        if index >= 10:  # STRUCTURAL: minimum bars needed for structure detection
            self.swings = detect_swings(self.df.iloc[:index + 1])
            self.current_trend = determine_trend(self.swings)
        
        # === 2. Détection des événements structurels ===
        
        # BOS
        bos = detect_bos(self.df.iloc[:index + 1], self.swings, self.current_trend)
        if bos is not None:
            self.last_bos = bos.type
            logger.info(f"BOS | type={bos.type} | index={index}")
        
        # CHOCH
        choch = detect_choch(self.df.iloc[:index + 1], self.swings, self.current_trend)
        if choch is not None:
            self.last_choch = choch.type
            logger.info(f"CHOCH | type={choch.type} | index={index}")
        
        # Sweep
        self.liquidity_levels = detect_liquidity_levels(self.swings, self.df)
        sweep = detect_sweep(self.df, self.liquidity_levels, index)
        if sweep is not None:
            self.last_sweep = sweep
            logger.info(f"SWEEP | direction={sweep.direction} | index={index}")
        
        # === 3. Évaluation de la zone ===
        
        price = self.df["close"].iloc[index]
        confirmed_swings = [s for s in self.swings if s.confirmed]
        
        last_high = None
        last_low = None
        for s in reversed(confirmed_swings):
            if s.type == "swing_high" and last_high is None:
                last_high = s
            if s.type == "swing_low" and last_low is None:
                if last_high and last_low:
                    break
        
        zone = get_zone(price, last_high, last_low)
        
        # === 4. Détermination de la direction du signal ===
        
        # Un signal long est pertinent si :
        # - Sweep low (chasse les stops en-dessous)
        # - OU BOS bull / CHOCH bull
        # - ET prix en zone discount
        # - ET biais HTF bullish
        
        signal_direction = None
        signal_type = None
        
        # Sweep low → signal long
        if self.last_sweep and self.last_sweep.direction == "low":
            signal_direction = SignalDirection.LONG
            signal_type = SignalType.LIQUIDITY_SWEEP_LOW
        
        # Sweep high → signal short
        elif self.last_sweep and self.last_sweep.direction == "high":
            signal_direction = SignalDirection.SHORT
            signal_type = SignalType.LIQUIDITY_SWEEP_HIGH
        
        # CHOCH bull (retournement) → signal long
        elif self.last_choch == "choch_bull":
            signal_direction = SignalDirection.LONG
            signal_type = SignalType.CHOCH_BULL
        
        # CHOCH bear (retournement) → signal short
        elif self.last_choch == "choch_bear":
            signal_direction = SignalDirection.SHORT
            signal_type = SignalType.CHOCH_BEAR
        
        # BOS bull (continuation) → signal long
        elif self.last_bos == "bos_bull" and self.htf_bias == "bullish":
            signal_direction = SignalDirection.LONG
            signal_type = SignalType.BOS_BULL
        
        # BOS bear (continuation) → signal short
        elif self.last_bos == "bos_bear" and self.htf_bias == "bearish":
            signal_direction = SignalDirection.SHORT
            signal_type = SignalType.BOS_BEAR
        
        if signal_direction is None or signal_type is None:
            return None
        
        # === 5. Vérification de la confluence ===
        
        dir_str = "long" if signal_direction == SignalDirection.LONG else "short"
        
        htf_aligned = (self.htf_bias == "bullish" and dir_str == "long") or \
                       (self.htf_bias == "bearish" and dir_str == "short")
        
        zone_favorable = (zone.zone == "discount" and dir_str == "long") or \
                         (zone.zone == "premium" and dir_str == "short")
        
        fvg_present = find_fvg_at_price(self.fvgs, price, dir_str) is not None
        
        ob_present = find_ob_at_price(self.obs, price, dir_str) is not None
        
        sweep_present = self.last_sweep is not None
        
        displacement_result = measure_displacement(self.df, index)
        displacement_significant = displacement_result["is_significant"]
        
        structure_aligned = (self.last_bos is not None or self.last_choch is not None) and htf_aligned
        
        confluence = compute_confluence_score(
            htf_bias_aligned=htf_aligned,
            zone_favorable=zone_favorable,
            fvg_present=fvg_present,
            ob_present=ob_present,
            sweep_present=sweep_present,
            displacement_significant=displacement_significant,
            structure_aligned=structure_aligned,
        )
        
        if not confluence["is_eligible"]:
            logger.info(
                f"SETUP_REJECTED | type={signal_type.value} | direction={dir_str} | "
                f"score={confluence['score']} | minimum={CONFLUENCE_MINIMUM}"
            )
            return None
        
        # === 6. Construction du signal ===
        
        # Calcul de l'ATR au moment du signal
        atr_result = measure_displacement(self.df, index)
        atr_value = self.df["close"].iloc[index] - self.df["open"].iloc[index]
            atr_value = abs(atr_value) / max(atr_result["displacement_atr"], 0.001) if atr_result["displacement_atr"] > 0 else 0.0001  # STRUCTURAL: fallback minimal non-zero
        
        signal = Signal(
            signal_type=signal_type,
            direction=signal_direction,
            timestamp=self.df.index[index],
            price=price,
            atr_at_signal=_calculate_atr(self.df, index),
            htf_bias=self.htf_bias,
            confluences=[k for k, v in confluence["breakdown"].items() if v > 0],
        )
        
        # Enregistrement dans le registry (déduplication Règle 3)
        if self.registry.register(signal):
            logger.info(
                f"SIGNAL_DETECTED | type={signal_type.value} | direction={dir_str} | "
                f"confluence={confluence['score']} | breakdown={confluence['breakdown']} | "
                f"zone={zone.zone} | index={index} | price={price:.5f}"
            )
            return signal
        else:
            logger.warning(f"SIGNAL_DUPLICATE | timestamp={signal.timestamp}")
            return None
    
    def get_stats(self) -> dict:
        """Statistiques du pipeline."""
        return {
            "total_signals": self.registry.count(),
            "htf_bias": self.htf_bias,
            "current_trend": self.current_trend,
            "active_swings": len([s for s in self.swings if s.confirmed]),
            "active_fvgs": len([f for f in self.fvgs if f.is_active]),
            "active_obs": len([o for o in self.obs if o.is_active]),
            "active_liquidity_levels": len([l for l in self.liquidity_levels if not l.swept]),
        }


def _calculate_atr(df: pd.DataFrame, index: int) -> float:
    """Calcul ATR à un index."""
    from config.params import ATR_PERIOD
    
    period = ATR_PERIOD
    start = max(0, index - period + 1)
    
    if start >= index or index >= len(df):
        return 0.0001  # STRUCTURAL: fallback minimal non-zero
    
    subset = df.iloc[start:index + 1]
    
    high = subset["high"]
    low = subset["low"]
    close_prev = subset["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.mean()
    
    return float(atr) if not pd.isna(atr) else 0.0001  # STRUCTURAL: fallback minimal
