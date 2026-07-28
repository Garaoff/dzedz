"""
Détection de signaux SMC/ICT — Pipeline COMPLET v2.

RÈGLE 1 : Chaque concept est calculé par son module unique.
RÈGLE 3 : Transition, pas état.
RÈGLE 2 : Ce module est appelé par backtest/engine.py et live/bot.py.
RÈGLE 6 : Pas d'échec silencieux.

Pipeline v2 — Concepts ICT intégrés :
1. Market Structure (Swings, BOS, CHOCH)
2. FVG (Fair Value Gap) + iFVG
3. Order Blocks (OB)
4. Liquidity Sweeps + Equal Highs/Lows
5. Displacement
6. Premium/Discount Zones
7. HTF Bias
8. 🆕 Killzones (London/NY time windows)
9. 🆕 PDHL (Previous Day/Week High/Low)
10. 🆕 MSS (CHOCH + Displacement + FVG = Market Structure Shift)
11. 🆕 Breaker Blocks (OB invalidé → rôle inversé)
12. 🆕 Silver Bullet (Killzone + MSS + FVG + Sweep)
13. 🆕 PO3 (Power of 3 — Accumulation/Manipulation/Distribution)

Hiérarchie ICT des signaux (du plus puissant au moins puissant) :
- Silver Bullet (Killzone + MSS + FVG + Sweep) = GOLD
- MSS (CHOCH + Displacement + FVG) = SILVER
- Sweep + CHOCH = BRONZE
- BOS + HTF = BASIC
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
from core.killzones import get_killzone, KillzoneInfo
from core.pdhl import compute_pdhl, check_pdhl_sweep, find_nearest_pdhl, PDHLLevel
from core.mss import detect_mss, MarketStructureShift
from core.breaker_block import (
    detect_breaker_blocks,
    check_breaker_invalidated,
    find_breaker_at_price,
    BreakerBlock,
)
from core.silver_bullet import detect_silver_bullet, SilverBulletSetup
from core.po3 import detect_po3_phase, PO3Phase
from core.scenario_engine import analyze_scenarios, ScenarioAnalysis, ScenarioType
from config.params import CONFLUENCE_MINIMUM, SC_TRAP_PROBABILITY_THRESHOLD_PCT

logger = logging.getLogger(__name__)


class SMCPipeline:
    """
    Pipeline complet de détection SMC/ICT v2.
    
    Ce pipeline est le CERVEAU du bot. Il agrège TOUTES les détections
    ICT et produit des signaux avec un score de confluence.
    
    UTILISATION :
    1. Initialiser avec les données
    2. Pour chaque nouvelle bougie : call process_bar()
    3. Si un signal est retourné : passer à sl_tp_calculator puis risk_guard
    
    Concepts ICT v2 (13 concepts) :
    - Structure (Swings, BOS, CHOCH) — base
    - FVG + iFVG — déséquilibre
    - Order Blocks — zone institutionnelle
    - Liquidity Sweeps + Equal Highs/Lows — liquidité
    - Displacement — force
    - Zones Premium/Discount — position dans le range
    - HTF Bias — contexte macro
    - Killzones — time filter ICT
    - PDHL — liquidité journalière/hebdo
    - MSS — signal ICT optimal
    - Breaker Blocks — OB invalidé inversé
    - Silver Bullet — setup ICT complet
    - PO3 — cycle quotidien
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
        self.pdhl_levels: list[PDHLLevel] = []
        self.breaker_blocks: list[BreakerBlock] = []
        self.last_sweep: Optional[LiquiditySweep] = None
        self.current_trend: str = "neutral"
        self.htf_bias: str = "neutral"
        self.last_bos: Optional[str] = None
        self.last_choch: Optional[str] = None
        self.last_mss: Optional[MarketStructureShift] = None
        self.last_silver_bullet: Optional[SilverBulletSetup] = None
        self.current_killzone: Optional[KillzoneInfo] = None
        self.current_po3_phase: Optional[PO3Phase] = None
        self.last_scenario_analysis: Optional[ScenarioAnalysis] = None
        
        # Initialiser avec les données existantes (warmup)
        self._warmup()
    
    def _warmup(self):
        """
        Initialiser les détections sur les données existantes.
        
        Cela permet d'avoir un état initial (swings, FVG, OB, etc.)
        avant de commencer à traiter les nouvelles bougies.
        """
        if len(self.df) < 10:  # STRUCTURAL: minimum 10 bars for warmup
            logger.warning(f"WARMUP | reason=insufficient_data | bars={len(self.df)}")
            return
        
        # Biais HTF
        if self.df_htf is not None and len(self.df_htf) >= 5:  # STRUCTURAL: minimum 5 HTF bars
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
        
        # PDHL
        self.pdhl_levels = compute_pdhl(self.df)
        logger.info(f"WARMUP | pdhl_levels={len(self.pdhl_levels)}")
        
        # Breaker Blocks (from invalidated OBs)
        for i in range(len(self.df)):
            self.obs = check_ob_invalidated(self.obs, self.df, i)
            new_breakers = detect_breaker_blocks(self.obs, self.df, i)
            self.breaker_blocks.extend(new_breakers)
        logger.info(f"WARMUP | breaker_blocks={len(self.breaker_blocks)}")
    
    def process_bar(self, index: int) -> Optional[Signal]:
        """
        Traite une bougie et retourne un signal si un setup est détecté.
        
        RÈGLE 3 : Le signal est émis UNIQUEMENT sur la TRANSITION.
        RÈGLE 1 : Chaque concept est calculé par son module unique.
        
        Pipeline v2 — ordre de priorité ICT :
        1. Silver Bullet (Killzone + MSS + FVG + Sweep) = GOLD setup
        2. MSS (CHOCH + Displacement + FVG) = SILVER setup
        3. Sweep + Zone + FVG = BRONZE setup
        4. BOS + HTF = BASIC continuation
        
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
        
        # Update Breaker Blocks (OB invalidés → Breakers)
        new_breakers = detect_breaker_blocks(self.obs, self.df, index)
        self.breaker_blocks.extend(new_breakers)
        self.breaker_blocks = check_breaker_invalidated(self.breaker_blocks, self.df, index)
        
        # Update PDHL (vérifier sweeps)
        self.pdhl_levels = check_pdhl_sweep(self.pdhl_levels, self.df, index)
        
        # Re-détecter les swings si on a enough data
        if index >= 10:  # STRUCTURAL: minimum bars needed for structure
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
        
        # MSS (CHOCH + Displacement + FVG)
        mss = detect_mss(self.df.iloc[:index + 1], self.swings, self.current_trend, self.fvgs)
        if mss is not None:
            self.last_mss = mss
            logger.info(f"MSS | type={mss.type} | displacement={mss.displacement_atr:.2f} | has_fvg={mss.has_fvg} | index={index}")
        
        # Sweep
        self.liquidity_levels = detect_liquidity_levels(self.swings, self.df)
        sweep = detect_sweep(self.df, self.liquidity_levels, index)
        if sweep is not None:
            self.last_sweep = sweep
            logger.info(f"SWEEP | direction={sweep.direction} | index={index}")
        
        # === 3. Killzone ICT ===
        timestamp = self.df.index[index]
        if isinstance(timestamp, pd.Timestamp):
            ts_datetime = timestamp.to_pydatetime()
        else:
            ts_datetime = timestamp
        
        self.current_killzone = get_killzone(ts_datetime)
        
        # === 4. PO3 (Power of 3) ===
        displacement_result = measure_displacement(self.df, index)
        displacement_atr = displacement_result["displacement_atr"]
        
        # STRUCTURAL: PO3 nécessite de connaître le début de journée
        daily_start = _find_daily_start(self.df, index)
        self.current_po3_phase = detect_po3_phase(
            self.df, daily_start, index,
            last_sweep=self.last_sweep,
            displacement_atr=displacement_atr,
        )
        
        # === 5. Silver Bullet ===
        sb = detect_silver_bullet(
            self.df.iloc[:index + 1], timestamp,
            self.swings, self.current_trend,
            self.fvgs, self.last_sweep,
        )
        if sb is not None:
            self.last_silver_bullet = sb
        
        # === 5b. Moteur de Scenarios — Anticipation de TOUTES les éventualités ===
        self.last_scenario_analysis = analyze_scenarios(
            df=self.df,
            index=index,
            swings=self.swings,
            fvgs=self.fvgs,
            obs=self.obs,
            liquidity_levels=self.liquidity_levels,
            breaker_blocks=self.breaker_blocks,
            pdhl_levels=self.pdhl_levels,
            last_sweep=self.last_sweep,
            last_mss=self.last_mss,
            last_bos=self.last_bos,
            last_choch=self.last_choch,
            htf_bias=self.htf_bias,
            current_trend=self.current_trend,
            killzone=self.current_killzone,
            po3_phase=self.current_po3_phase,
            df_htf=self.df_htf,
        )
        
        # === 6. Évaluation de la zone ===
        
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
        
        # === 7. Détermination de la direction du signal ===
        # PRIORITÉ ICT : Silver Bullet > MSS > Sweep > CHOCH > BOS
        
        signal_direction = None
        signal_type = None
        setup_grade = "basic"
        
        # 🥇 Silver Bullet (Killzone + MSS + FVG + Sweep) = GOLD
        if self.last_silver_bullet is not None and self.last_silver_bullet.is_complete:
            sb = self.last_silver_bullet
            signal_direction = SignalDirection.LONG if sb.direction == "long" else SignalDirection.SHORT
            signal_type = SignalType.SILVER_BULLET_LONG if sb.direction == "long" else SignalType.SILVER_BULLET_SHORT
            setup_grade = "gold"
            logger.info(f"SETUP_GOLD | silver_bullet | direction={sb.direction} | quality={sb.setup_quality}")
        
        # 🥈 MSS (CHOCH + Displacement + FVG) = SILVER
        elif self.last_mss is not None and self.last_mss.has_fvg:
            mss = self.last_mss
            signal_direction = SignalDirection.LONG if mss.type == "mss_bull" else SignalDirection.SHORT
            signal_type = SignalType.MSS_BULL if mss.type == "mss_bull" else SignalType.MSS_BEAR
            setup_grade = "silver"
            logger.info(f"SETUP_SILVER | mss | type={mss.type} | displacement={mss.displacement_atr:.2f}")
        
        # Sweep → signal (BRONZE)
        elif self.last_sweep and self.last_sweep.direction == "low":
            signal_direction = SignalDirection.LONG
            signal_type = SignalType.LIQUIDITY_SWEEP_LOW
            setup_grade = "bronze"
        
        elif self.last_sweep and self.last_sweep.direction == "high":
            signal_direction = SignalDirection.SHORT
            signal_type = SignalType.LIQUIDITY_SWEEP_HIGH
            setup_grade = "bronze"
        
        # CHOCH (retournement) — sans displacement significatif = bronze
        elif self.last_choch == "choch_bull":
            signal_direction = SignalDirection.LONG
            signal_type = SignalType.CHOCH_BULL
            setup_grade = "bronze"
        
        elif self.last_choch == "choch_bear":
            signal_direction = SignalDirection.SHORT
            signal_type = SignalType.CHOCH_BEAR
            setup_grade = "bronze"
        
        # BOS (continuation) — basic
        elif self.last_bos == "bos_bull" and self.htf_bias == "bullish":
            signal_direction = SignalDirection.LONG
            signal_type = SignalType.BOS_BULL
            setup_grade = "basic"
        
        elif self.last_bos == "bos_bear" and self.htf_bias == "bearish":
            signal_direction = SignalDirection.SHORT
            signal_type = SignalType.BOS_BEAR
            setup_grade = "basic"
        
        if signal_direction is None or signal_type is None:
            return None
        
        # === 8. Vérification de la confluence (13 concepts ICT) ===
        
        dir_str = "long" if signal_direction == SignalDirection.LONG else "short"
        
        htf_aligned = (self.htf_bias == "bullish" and dir_str == "long") or \
                       (self.htf_bias == "bearish" and dir_str == "short")
        
        zone_favorable = (zone.zone == "discount" and dir_str == "long") or \
                         (zone.zone == "premium" and dir_str == "short")
        
        fvg_present = find_fvg_at_price(self.fvgs, price, dir_str) is not None
        
        ob_present = find_ob_at_price(self.obs, price, dir_str) is not None
        
        sweep_present = self.last_sweep is not None
        
        displacement_significant = displacement_result["is_significant"]
        
        structure_aligned = (self.last_bos is not None or self.last_choch is not None) and htf_aligned
        
        # 🆕 MSS
        mss_present = self.last_mss is not None and self.last_mss.has_fvg
        
        # 🆕 Killzone
        killzone_active = self.current_killzone is not None and self.current_killzone.is_active
        
        # 🆕 PO3 Distribution
        po3_distribution = self.current_po3_phase is not None and self.current_po3_phase.is_distribution
        
        # 🆕 Breaker Block
        breaker_present = find_breaker_at_price(self.breaker_blocks, price, dir_str) is not None
        
        # 🆕 PDHL
        pdhl_aligned = _check_pdhl_alignment(self.pdhl_levels, price, dir_str)
        
        confluence = compute_confluence_score(
            htf_bias_aligned=htf_aligned,
            zone_favorable=zone_favorable,
            fvg_present=fvg_present,
            ob_present=ob_present,
            sweep_present=sweep_present,
            displacement_significant=displacement_significant,
            structure_aligned=structure_aligned,
            mss_present=mss_present,
            killzone_active=killzone_active,
            po3_distribution=po3_distribution,
            breaker_present=breaker_present,
            pdhl_aligned=pdhl_aligned,
        )
        
        if not confluence["is_eligible"]:
            logger.info(
                f"SETUP_REJECTED | type={signal_type.value} | direction={dir_str} | "
                f"grade={setup_grade} | score={confluence['score']} | minimum={CONFLUENCE_MINIMUM}"
            )
            return None
        
        # === 8b. Vérification du Scenario Piège ===
        # Si le scenario piège est trop probable, on REJETTE le signal
        # Le bot doit savoir : "Si X arrive, alors Y peut se produire"
        # Si le piège est probable, le bot n'entre PAS
        if self.last_scenario_analysis is not None:
            trap = self.last_scenario_analysis.trap_scenario
            if trap is not None and trap.is_viable:
                trap_prob = trap.probability_pct
                # STRUCTURAL: si le piège a plus de 25% de probabilité,
                # on ne prend pas le risque. C'est la prudence intelligente.
                if trap_prob >= SC_TRAP_PROBABILITY_THRESHOLD_PCT:  # STRUCTURAL: seuil de piège depuis params
                    logger.warning(
                        f"SETUP_TRAP_DETECTED | signal={signal_type.value} | "
                        f"direction={dir_str} | trap_type={trap.scenario_type.value} | "
                        f"trap_prob={trap_prob:.1f}% | trap_action={trap.action} | "
                        f"REJECTING — scenario piège trop probable"
                    )
                    return None
        
        # === 9. Construction du signal ===
        
        signal = Signal(
            signal_type=signal_type,
            direction=signal_direction,
            timestamp=self.df.index[index],
            price=price,
            atr_at_signal=_calculate_atr(self.df, index),
            htf_bias=self.htf_bias,
            confluences=[k for k, v in confluence["breakdown"].items() if v > 0],
            killzone=self.current_killzone.name if self.current_killzone else None,
            po3_phase=self.current_po3_phase.phase if self.current_po3_phase else None,
        )
        
        # Enregistrement dans le registry (déduplication Règle 3)
        if self.registry.register(signal):
            logger.info(
                f"SIGNAL_DETECTED | type={signal_type.value} | direction={dir_str} | "
                f"grade={setup_grade} | confluence={confluence['score']} | "
                f"breakdown={confluence['breakdown']} | zone={zone.zone} | "
                f"killzone={self.current_killzone.name if self.current_killzone else 'none'} | "
                f"po3={self.current_po3_phase.phase if self.current_po3_phase else 'none'} | "
                f"index={index} | price={price:.5f}"
            )
            return signal
        else:
            logger.warning(f"SIGNAL_DUPLICATE | timestamp={signal.timestamp}")
            return None
    
    def get_stats(self) -> dict:
        """Statistiques du pipeline — chiffres bruts (Règle 9)."""
        return {
            "total_signals": self.registry.count(),
            "htf_bias": self.htf_bias,
            "current_trend": self.current_trend,
            "active_swings": len([s for s in self.swings if s.confirmed]),
            "active_fvgs": len([f for f in self.fvgs if f.is_active]),
            "active_obs": len([o for o in self.obs if o.is_active]),
            "active_liquidity_levels": len([l for l in self.liquidity_levels if not l.swept]),
            "active_pdhl_levels": len([l for l in self.pdhl_levels if not l.swept]),
            "active_breaker_blocks": len([b for b in self.breaker_blocks if b.is_active]),
            "killzone": self.current_killzone.name if self.current_killzone else "none",
            "po3_phase": self.current_po3_phase.phase if self.current_po3_phase else "none",
            "last_mss_type": self.last_mss.type if self.last_mss else "none",
            "scenario_primary": self.last_scenario_analysis.primary_scenario.scenario_type.value if self.last_scenario_analysis and self.last_scenario_analysis.primary_scenario else "none",
            "scenario_trap": self.last_scenario_analysis.trap_scenario.scenario_type.value if self.last_scenario_analysis and self.last_scenario_analysis.trap_scenario else "none",
            "scenario_state": self.last_scenario_analysis.market_state if self.last_scenario_analysis else "none",
        }


# =============================================================================
# Helpers
# =============================================================================

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


def _find_daily_start(df: pd.DataFrame, current_index: int) -> int:
    """
    Trouve l'index du début de la journée courante.
    
    STRUCTURAL: utilisé pour PO3 — il faut connaître le début
    de journée pour calculer le range et la phase.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        return 0  # STRUCTURAL: fallback si pas de DatetimeIndex
    
    current_date = df.index[current_index].date()
    
    # Trouver le premier index de cette journée
    for i in range(current_index, -1, -1):
        if df.index[i].date != current_date:
            # STRUCTURAL: .date est une property sur Timestamp
            if hasattr(df.index[i], 'date'):
                if df.index[i].date() != current_date:
                    return i + 1
            else:
                return i + 1
    
    return 0


def _check_pdhl_alignment(pdhl_levels: list[PDHLLevel], price: float, direction: str) -> bool:
    """
    Vérifie si un PDHL est aligné avec la direction du trade.
    
    Pour un LONG : PDL/PWL en-dessous (support) ou PDH/PWH au-dessus (TP target)
    Pour un SHORT : PDH/PWH au-dessus (résistance) ou PDL/PWL en-dessous (TP target)
    
    STRUCTURAL: on vérifie la proximité, pas le niveau exact.
    Un PDHL proche = zone de liquidité importante à prendre en compte.
    """
    # Pour un LONG : PDL en-dessous du prix = support (liquidité shorts)
    # Pour un SHORT : PDH au-dessus du prix = résistance (liquidité longs)
    
    if direction == "long":
        pdl_nearby = find_nearest_pdhl(pdhl_levels, price, "below")
        return pdl_nearby is not None and pdl_nearby.type in ("pdl", "pwl")
    
    elif direction == "short":
        pdh_nearby = find_nearest_pdhl(pdhl_levels, price, "above")
        return pdh_nearby is not None and pdh_nearby.type in ("pdh", "pwh")
    
    return False
