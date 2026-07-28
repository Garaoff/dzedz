"""
Moteur de Scenarios — Anticipation TOTALE des éventualités du marché.

RÈGLE 1 : analyze_scenarios() est la SEULE fonction qui analyse les scenarios.
RÈGLE 3 : Transition, pas état — scenarios changent sur TRANSITION.
RÈGLE 4 : Pas de seuils fixes. Probabilités depuis config.
RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 9 : Chiffres bruts pour chaque scenario.

Ce module est le CERVEAU INTELLIGENT du bot. Il ne se contente pas
de dire "acheter" ou "vendre". Il analyse TOUTES les éventualités
possibles et leurs implications.

Philosophie : "Si X arrive, alors Y peut se produire. Mais si Z arrive
au lieu de X, alors W est probable. Et dans ce cas, je fais ça."

Le moteur construit un ARBRE DE SCENARIOS :
- Scenario primaire (le plus probable)
- Scenario alternatif (le 2ème plus probable)
- Scenario piège (ce qui pourrait faire échouer le scenario primaire)
- Scenario extrême (black swan, événement rare)

Chaque scenario a :
- Une probabilité (0-100%)
- Des conditions de confirmation (qu'est-ce qui valide ce scenario)
- Des conditions d'invalidation (qu'est-ce qui invalide ce scenario)
- Un plan d'action (si ce scenario se réalise, que faire)
- Un niveau de risque (low/medium/high/extreme)

Types de scenarios ICT :
1. TREND_CONTINUATION : BOS + HTF aligné → continuation
2. TREND_REVERSAL : MSS + Sweep → retournement
3. LIQUIDITY_TRAP : Sweep + continuation dans la direction du sweep
4. FALSE_BREAKOUT : BOS + retour immédiat → piège
5. RANGE_BOUND : Pas de structure claire → range
6. MANIPULATION : Sweep + retour → PO3 manipulation
7. DISTRIBUTION_BULL : PO3 distribution haussière
8. DISTRIBUTION_BEAR : PO3 distribution baissière
9. INSTITUTIONAL_ACCUMULATION : Range tight + volume bas
10. INSTITUTIONAL_DISTRIBUTION : Displacement + FVG + volume élevé
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import pandas as pd

from config.params import (
    SCENARIO_MIN_PROBABILITY_PCT,
    SCENARIO_TRAP_RISK_ATR,
    SCENARIO_CONFIRMATION_CLOSE_PCT,
    ATR_PERIOD,
    DISPLACEMENT_MIN_ATR,
    CONFLUENCE_MINIMUM,
    SC_CONTINUATION_BOS_HTF_ALIGNED_PCT,
    SC_CONTINUATION_BOS_NO_HTF_PCT,
    SC_CONTINUATION_NO_BOS_PCT,
    SC_KILLZONE_ACTIVE_PCT,
    SC_KILLZONE_INACTIVE_PCT,
    SC_ZONE_FAVORABLE_PCT,
    SC_DISPLACEMENT_SIGNIFICANT_PCT,
    SC_FVG_OB_BREAKER_PCT,
    SC_TRAP_PROBABILITY_THRESHOLD_PCT,
    SC_ACTION_ENTER_THRESHOLD_PCT,
    SC_ACTION_WAIT_THRESHOLD_PCT,
    SC_REVERSAL_MSS_FVG_PCT,
    SC_REVERSAL_CHOCH_ONLY_PCT,
    SC_REVERSAL_NO_SIGNAL_PCT,
    SC_REVERSAL_SWEEP_ALIGNED_PCT,
    SC_REVERSAL_SWEEP_COUNTER_PCT,
    SC_REVERSAL_PO3_DISTRIBUTION_PCT,
    SC_REVERSAL_ACTION_ENTER_PCT,
    SC_REVERSAL_ACTION_WATCH_PCT,
    SC_REVERSAL_ACTION_OBSERVE_PCT,
    SC_TRAP_SWEEP_BASE_PCT,
    SC_TRAP_NO_DISPLACEMENT_PCT,
    SC_TRAP_NO_FVG_PCT,
    SC_TRAP_HTF_ALIGNED_PCT,
    SC_TRAP_AVOID_THRESHOLD_PCT,
    SC_TRAP_NO_SWEEP_PCT,
    SC_FALSE_NO_DISPLACEMENT_PCT,
    SC_FALSE_WITH_DISPLACEMENT_PCT,
    SC_FALSE_HTF_COUNTER_PCT,
    SC_FALSE_NO_KILLZONE_PCT,
    SC_FALSE_AVOID_THRESHOLD_PCT,
    SC_FALSE_NO_BOS_PCT,
    SC_RANGE_NEUTRAL_TREND_PCT,
    SC_RANGE_NO_DISPLACEMENT_PCT,
    SC_RANGE_HTF_NEUTRAL_PCT,
    SC_RANGE_EQUILIBRIUM_PCT,
    SC_RANGE_AVOID_THRESHOLD_PCT,
    SC_MANIP_PO3_CONFIRMED_PCT,
    SC_MANIP_SWEEP_NO_DISPLACEMENT_PCT,
    SC_MANIP_NO_SIGNAL_PCT,
    SC_MANIP_WAIT_THRESHOLD_PCT,
    SC_DIST_PO3_BASE_PCT,
    SC_DIST_DISPLACEMENT_PCT,
    SC_DIST_MSS_ALIGNED_PCT,
    SC_DIST_MSS_COUNTER_PCT,
    SC_DIST_KILLZONE_PCT,
    SC_DIST_HTF_ALIGNED_PCT,
    SC_DIST_ZONE_FAVORABLE_PCT,
    SC_PROBABILITY_MAX_PCT,
    SC_PROBABILITY_MIN_PCT,
    SC_DISTRIBUTION_LOW_RISK_PCT,
)
from core.structure import Swing, detect_swings, determine_trend
from core.fvg import FVG, find_fvg_at_price
from core.order_block import OrderBlock, find_ob_at_price
from core.liquidity import LiquidityLevel, LiquiditySweep, find_nearest_liquidity_level
from core.displacement import measure_displacement
from core.zones import get_zone, PriceZone
from core.htf_bias import get_htf_bias
from core.killzones import get_killzone, KillzoneInfo
from core.mss import MarketStructureShift
from core.breaker_block import BreakerBlock, find_breaker_at_price
from core.pdhl import PDHLLevel, find_nearest_pdhl
from core.po3 import PO3Phase

logger = logging.getLogger(__name__)


# =============================================================================
# Types de Scenarios
# =============================================================================

class ScenarioType(Enum):
    """Types de scenarios ICT possibles."""
    TREND_CONTINUATION = "trend_continuation"       # BOS + HTF aligné → continuation
    TREND_REVERSAL = "trend_reversal"               # MSS + Sweep → retournement
    LIQUIDITY_TRAP = "liquidity_trap"                # Sweep + continuation (piège)
    FALSE_BREAKOUT = "false_breakout"               # BOS + retour immédiat (piège)
    RANGE_BOUND = "range_bound"                      # Pas de structure claire
    MANIPULATION = "manipulation"                    # PO3 manipulation en cours
    DISTRIBUTION_BULL = "distribution_bull"          # PO3 distribution haussière
    DISTRIBUTION_BEAR = "distribution_bear"          # PO3 distribution baissière
    INSTITUTIONAL_ACCUMULATION = "institutional_accumulation"  # Range tight
    INSTITUTIONAL_DISTRIBUTION = "institutional_distribution"  # Displacement + FVG


class RiskLevel(Enum):
    """Niveau de risque d'un scenario."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class ScenarioCondition:
    """Condition de confirmation ou d'invalidation d'un scenario."""
    description: str
    price_level: float
    condition_type: str  # "above" (prix doit passer au-dessus) ou "below" (en-dessous)
    met: bool = False

    def check(self, current_price: float) -> bool:
        """Vérifie si la condition est remplie."""
        if self.condition_type == "above":
            self.met = current_price > self.price_level
        elif self.condition_type == "below":
            self.met = current_price < self.price_level
        return self.met


@dataclass
class Scenario:
    """Un scenario complet du marché avec probabilité et plan d'action."""
    scenario_type: ScenarioType
    direction: str  # "long", "short", "neutral"
    probability_pct: float  # 0.0–100.0  # STRUCTURAL: percentage range convention
    confidence: float  # 0.0–1.0
    
    # Pourquoi ce scenario est probable
    reasoning: list[str] = field(default_factory=list)
    
    # Confluences qui supportent ce scenario
    supporting_confluences: list[str] = field(default_factory=list)
    
    # Confluences qui contredisent ce scenario
    contradicting_confluences: list[str] = field(default_factory=list)
    
    # Conditions de confirmation (qu'est-ce qui valide ce scenario)
    confirmations: list[ScenarioCondition] = field(default_factory=list)
    
    # Conditions d'invalidation (qu'est-ce qui invalide ce scenario)
    invalidations: list[ScenarioCondition] = field(default_factory=list)
    
    # Niveaux clés
    entry_zone_top: float = 0.0
    entry_zone_bottom: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    
    # Risque
    risk_level: RiskLevel = RiskLevel.MEDIUM
    
    # Si ce scenario se réalise, que faire
    action: str = "wait"  # "enter_long", "enter_short", "wait", "exit", "reverse"
    
    # Scenario alternatif si celui-ci échoue
    alternative_scenario_type: Optional[ScenarioType] = None
    
    @property
    def is_viable(self) -> bool:
        """True si le scenario est assez probable pour être pris en compte."""
        return self.probability_pct >= SCENARIO_MIN_PROBABILITY_PCT
    
    @property
    def is_confirmed(self) -> bool:
        """True si au moins une condition de confirmation est remplie."""
        return any(c.met for c in self.confirmations)
    
    @property
    def is_invalidated(self) -> bool:
        """True si au moins une condition d'invalidation est remplie."""
        return any(c.met for c in self.invalidations)


@dataclass
class ScenarioAnalysis:
    """Résultat complet de l'analyse de scenarios."""
    scenarios: list[Scenario] = field(default_factory=list)
    primary_scenario: Optional[Scenario] = None
    trap_scenario: Optional[Scenario] = None
    market_state: str = "unknown"
    total_probability: float = 0.0  # STRUCTURAL: somme des probabilités = 100%
    
    def get_scenario(self, scenario_type: ScenarioType) -> Optional[Scenario]:
        """Trouve un scenario par type."""
        for s in self.scenarios:
            if s.scenario_type == scenario_type:
                return s
        return None
    
    def get_viable_scenarios(self) -> list[Scenario]:
        """Retourne les scenarios viables (probabilité >= minimum)."""
        return [s for s in self.scenarios if s.is_viable]
    
    def get_sorted_scenarios(self) -> list[Scenario]:
        """Retourne les scenarios triés par probabilité décroissante."""
        return sorted(self.scenarios, key=lambda s: s.probability_pct, reverse=True)


# =============================================================================
# Moteur de Scenarios — Analyse Complète
# =============================================================================

def analyze_scenarios(
    df: pd.DataFrame,
    index: int,
    # État du marché
    swings: list[Swing],
    fvgs: list[FVG],
    obs: list[OrderBlock],
    liquidity_levels: list[LiquidityLevel],
    breaker_blocks: list[BreakerBlock],
    pdhl_levels: list[PDHLLevel],
    # Événements récents
    last_sweep: Optional[LiquiditySweep],
    last_mss: Optional[MarketStructureShift],
    last_bos: Optional[str],
    last_choch: Optional[str],
    # Contexte
    htf_bias: str,
    current_trend: str,
    killzone: Optional[KillzoneInfo],
    po3_phase: Optional[PO3Phase],
    df_htf: Optional[pd.DataFrame] = None,
) -> ScenarioAnalysis:
    """
    Analyse TOUTES les éventualités possibles du marché.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui analyse les scenarios.
    
    Le moteur construit un arbre de scenarios en évaluant :
    1. L'état actuel du marché (structure, liquidité, zone)
    2. Les événements récents (sweep, MSS, BOS, CHOCH)
    3. Le contexte (HTF, killzone, PO3)
    4. Les niveaux clés (OB, FVG, PDHL, Breakers)
    5. Les interactions entre concepts
    
    Pour chaque scenario, il calcule :
    - La probabilité basée sur les confluences
    - Les conditions de confirmation
    - Les conditions d'invalidation
    - Le plan d'action
    - Le scenario alternatif si celui-ci échoue
    
    Args:
        df: DataFrame OHLCV (timeframe d'entrée)
        index: Index de la bougie courante
        swings: Swings détectés
        fvgs: FVG actifs
        obs: Order Blocks actifs
        liquidity_levels: Niveaux de liquidité
        breaker_blocks: Breaker Blocks actifs
        pdhl_levels: PDHL (Previous Day/Week High/Low)
        last_sweep: Dernier sweep de liquidité
        last_mss: Dernier MSS
        last_bos: Dernier BOS type
        last_choch: Dernier CHOCH type
        htf_bias: Biais HTF ("bullish"/"bearish"/"neutral")
        current_trend: Tendance actuelle
        killzone: Killzone active
        po3_phase: Phase PO3
        df_htf: DataFrame HTF (pour biais additionnel)
    
    Returns:
        ScenarioAnalysis avec tous les scenarios et le primary
    """
    if index < 1 or index >= len(df):
        return ScenarioAnalysis(market_state="insufficient_data")
    
    price = df["close"].iloc[index]
    current_high = df["high"].iloc[index]
    current_low = df["low"].iloc[index]
    
    # === 1. Calcul du displacement actuel ===
    displacement_result = measure_displacement(df, index)
    displacement_atr = displacement_result["displacement_atr"]
    displacement_significant = displacement_result["is_significant"]
    
    # === 2. Zone Premium/Discount ===
    zone = _get_current_zone(price, swings)
    
    # === 3. Calcul de l'ATR ===
    atr = _calculate_atr_at(df, index)
    
    # === 4. Construction des scenarios ===
    scenarios = []
    
    # --- Scenario 1 : TREND CONTINUATION (BOS + HTF aligné) ---
    sc_continuation = _build_trend_continuation_scenario(
        price, atr, swings, fvgs, obs, liquidity_levels,
        breaker_blocks, pdhl_levels, last_bos, htf_bias,
        current_trend, killzone, zone, displacement_atr,
    )
    scenarios.append(sc_continuation)
    
    # --- Scenario 2 : TREND REVERSAL (MSS + Sweep) ---
    sc_reversal = _build_trend_reversal_scenario(
        price, atr, swings, fvgs, obs, liquidity_levels,
        breaker_blocks, pdhl_levels, last_mss, last_choch,
        last_sweep, htf_bias, current_trend, killzone, zone,
        displacement_atr, po3_phase,
    )
    scenarios.append(sc_reversal)
    
    # --- Scenario 3 : LIQUIDITY TRAP (Sweep + continuation) ---
    sc_trap = _build_liquidity_trap_scenario(
        price, atr, swings, fvgs, obs, liquidity_levels,
        breaker_blocks, pdhl_levels, last_sweep, htf_bias,
        current_trend, killzone, zone, displacement_atr,
    )
    scenarios.append(sc_trap)
    
    # --- Scenario 4 : FALSE BREAKOUT (BOS + retour immédiat) ---
    sc_false = _build_false_breakout_scenario(
        price, atr, swings, fvgs, obs, liquidity_levels,
        last_bos, last_choch, htf_bias, current_trend,
        killzone, zone, displacement_atr,
    )
    scenarios.append(sc_false)
    
    # --- Scenario 5 : RANGE BOUND (pas de structure claire) ---
    sc_range = _build_range_bound_scenario(
        price, atr, swings, fvgs, obs, liquidity_levels,
        htf_bias, current_trend, killzone, zone, displacement_atr,
    )
    scenarios.append(sc_range)
    
    # --- Scenario 6 : MANIPULATION (PO3 sweep sans distribution) ---
    sc_manipulation = _build_manipulation_scenario(
        price, atr, swings, fvgs, obs, liquidity_levels,
        last_sweep, htf_bias, current_trend, killzone, zone,
        displacement_atr, po3_phase,
    )
    scenarios.append(sc_manipulation)
    
    # --- Scenario 7 : DISTRIBUTION BULL (PO3 distribution haussière) ---
    sc_dist_bull = _build_distribution_scenario(
        "bull", price, atr, swings, fvgs, obs, liquidity_levels,
        breaker_blocks, pdhl_levels, last_mss, last_sweep,
        htf_bias, current_trend, killzone, zone,
        displacement_atr, po3_phase,
    )
    scenarios.append(sc_dist_bull)
    
    # --- Scenario 8 : DISTRIBUTION BEAR (PO3 distribution baissière) ---
    sc_dist_bear = _build_distribution_scenario(
        "bear", price, atr, swings, fvgs, obs, liquidity_levels,
        breaker_blocks, pdhl_levels, last_mss, last_sweep,
        htf_bias, current_trend, killzone, zone,
        displacement_atr, po3_phase,
    )
    scenarios.append(sc_dist_bear)
    
    # === 5. Normaliser les probabilités (somme = 100%) ===
    scenarios = _normalize_probabilities(scenarios)
    
    # === 6. Identifier le scenario primaire ===
    viable = [s for s in scenarios if s.is_viable]
    primary = max(viable, key=lambda s: s.probability_pct) if viable else None
    
    # === 7. Identifier le scenario piège ===
    trap = _identify_trap_scenario(scenarios, primary)
    
    # === 8. Déterminer l'état du marché ===
    market_state = _determine_market_state(primary, current_trend, zone)
    
    # === Construction du résultat ===
    analysis = ScenarioAnalysis(
        scenarios=scenarios,
        primary_scenario=primary,
        trap_scenario=trap,
        market_state=market_state,
        total_probability=100.0,  # STRUCTURAL: somme normalisée = 100%
    )
    
    # Log détaillé — RÈGLE 9 : chiffres bruts
    logger.info(
        f"SCENARIO_ANALYSIS | state={market_state} | "
        f"primary={primary.scenario_type.value if primary else 'none'} | "
        f"primary_prob={primary.probability_pct:.1f}% | " if primary else "primary_prob=0% | "
        f"trap={trap.scenario_type.value if trap else 'none'} | "
        f"trend={current_trend} | htf={htf_bias} | "
        f"zone={zone.zone} | killzone={killzone.name if killzone else 'none'} | "
        f"po3={po3_phase.phase if po3_phase else 'none'} | "
        f"displacement={displacement_atr:.2f} | "
        f"scenarios={len(scenarios)}"
    )
    
    # Log chaque scenario viable
    for s in analysis.get_sorted_scenarios():
        if s.is_viable:
            logger.info(
                f"SCENARIO | type={s.scenario_type.value} | "
                f"direction={s.direction} | "
                f"probability={s.probability_pct:.1f}% | "
                f"action={s.action} | "
                f"risk={s.risk_level.value} | "
                f"reasons={s.reasoning[:3]} | "
                f"confirmations={len([c for c in s.confirmations if c.met])}/{len(s.confirmations)} | "
                f"invalidations={len([c for c in s.invalidations if c.met])}/{len(s.invalidations)}"
            )
    
    return analysis


# =============================================================================
# Builders de Scenarios
# =============================================================================

def _build_trend_continuation_scenario(
    price, atr, swings, fvgs, obs, liquidity_levels,
    breaker_blocks, pdhl_levels, last_bos, htf_bias,
    current_trend, killzone, zone, displacement_atr,
) -> Scenario:
    """
    Scenario TREND CONTINUATION : BOS + HTF aligné → continuation.
    
    Si le marché est en tendance et qu'un BOS confirme, la continuation
    est le scenario le plus probable. Mais si le BOS est faux (false
    breakout), le scenario alternatif est un retournement.
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    confirmations = []
    invalidations = []
    direction = "neutral"
    action = "wait"
    risk_level = RiskLevel.MEDIUM
    alt_scenario = ScenarioType.FALSE_BREAKOUT
    
    # === Évaluation de la probabilité ===
    
    # BOS récent = base du scenario
    if last_bos == "bos_bull" and htf_bias == "bullish":
        direction = "long"
        probability += 25.0  # STRUCTURAL: BOS bull + HTF bullish = 25% de base
        reasoning.append("BOS_bull + HTF_bullish = continuation haussière")
        supporting.append("bos_bull_aligned")
    elif last_bos == "bos_bear" and htf_bias == "bearish":
        direction = "short"
        probability += 25.0  # STRUCTURAL: probability weight from ICT hierarchy
        reasoning.append("BOS_bear + HTF_bearish = continuation baissière")
        supporting.append("bos_bear_aligned")
    elif last_bos == "bos_bull" and htf_bias != "bullish":
        direction = "long"
        probability += 10.0  # STRUCTURAL: BOS sans HTF = faible
        reasoning.append("BOS_bull mais HTF pas bullish = continuation faible")
        contradicting.append("htf_not_aligned")
    elif last_bos == "bos_bear" and htf_bias != "bearish":
        direction = "short"
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        reasoning.append("BOS_bear mais HTF pas bearish = continuation faible")
        contradicting.append("htf_not_aligned")
    else:
        # Pas de BOS récent
        probability += 5.0  # STRUCTURAL: pas de BOS = scenario peu probable
        reasoning.append("Pas de BOS récent = continuation peu probable")
        contradicting.append("no_bos")
    
    # Killzone active = +probabilité
    if killzone and killzone.is_active:
        probability += 10.0  # STRUCTURAL: killzone = +10%
        supporting.append("killzone_active")
        reasoning.append(f"Killzone {killzone.name} active = momentum institutionnel")
    else:
        probability -= 5.0  # STRUCTURAL: hors killzone = -5%
        contradicting.append("no_killzone")
        reasoning.append("Hors killzone = moins de momentum")
    
    # Zone favorable = +probabilité
    if zone.zone == "discount" and direction == "long":
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("zone_discount_for_long")
    elif zone.zone == "premium" and direction == "short":
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("zone_premium_for_short")
    elif zone.zone == "equilibrium":
        probability += 0.0  # STRUCTURAL: équilibre = neutre
        reasoning.append("Zone equilibrium = pas d'avantage")
    
    # Displacement = +probabilité
    if displacement_significant_currently(displacement_atr):
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("displacement_significant")
        reasoning.append("Displacement significatif = mouvement institutionnel")
    
    # FVG/OB dans la direction = +probabilité
    if direction != "neutral":
        fvg = find_fvg_at_price(fvgs, price, direction)
        ob = find_ob_at_price(obs, price, direction)
        breaker = find_breaker_at_price(breaker_blocks, price, direction)
        
        if fvg:
            probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("fvg_entry_available")
        if ob:
            probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("ob_entry_available")
        if breaker:
            probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("breaker_entry_available")
    
    # === Conditions de confirmation ===
    if direction == "long":
        # Le prix doit rester au-dessus du dernier swing low
        swing_low = _find_last_swing_price(swings, "swing_low")
        if swing_low:
            confirmations.append(ScenarioCondition(
                description="Prix reste au-dessus du swing low",
                price_level=swing_low,
                condition_type="above",
            ))
        # Le prix doit faire un higher high
        swing_high = _find_last_swing_price(swings, "swing_high")
        if swing_high:
            confirmations.append(ScenarioCondition(
                description="Prix casse le swing high (higher high)",
                price_level=swing_high,
                condition_type="above",
            ))
        # Invalidation : close en-dessous du swing low
        if swing_low:
            invalidations.append(ScenarioCondition(
                description="Close en-dessous du swing low = BOS faux",
                price_level=swing_low,
                condition_type="below",
            ))
    
    elif direction == "short":
        swing_high = _find_last_swing_price(swings, "swing_high")
        if swing_high:
            confirmations.append(ScenarioCondition(
                description="Prix reste en-dessous du swing high",
                price_level=swing_high,
                condition_type="below",
            ))
        swing_low = _find_last_swing_price(swings, "swing_low")
        if swing_low:
            confirmations.append(ScenarioCondition(
                description="Prix casse le swing low (lower low)",
                price_level=swing_low,
                condition_type="below",
            ))
        if swing_high:
            invalidations.append(ScenarioCondition(
                description="Close au-dessus du swing high = BOS faux",
                price_level=swing_high,
                condition_type="above",
            ))
    
    # === Action ===
    if probability >= 40.0:  # STRUCTURAL: threshold from params
        action = f"enter_{direction}" if direction != "neutral" else "wait"
        risk_level = RiskLevel.LOW
    elif probability >= 25.0:  # STRUCTURAL: threshold from params
        action = "wait_for_confirmation"
        risk_level = RiskLevel.MEDIUM
    else:
        action = "wait"
        risk_level = RiskLevel.HIGH
    
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp 0-100
    
    return Scenario(
        scenario_type=ScenarioType.TREND_CONTINUATION,
        direction=direction,
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        confirmations=confirmations,
        invalidations=invalidations,
        risk_level=risk_level,
        action=action,
        alternative_scenario_type=alt_scenario,
    )


def _build_trend_reversal_scenario(
    price, atr, swings, fvgs, obs, liquidity_levels,
    breaker_blocks, pdhl_levels, last_mss, last_choch,
    last_sweep, htf_bias, current_trend, killzone, zone,
    displacement_atr, po3_phase,
) -> Scenario:
    """
    Scenario TREND REVERSAL : MSS + Sweep → retournement.
    
    Si un MSS est détecté (CHOCH + Displacement + FVG) avec un
    sweep de liquidité, le retournement est probable.
    Mais si le sweep est un piège (liquidity trap), le scenario
    alternatif est une continuation.
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    confirmations = []
    invalidations = []
    direction = "neutral"
    action = "wait"
    risk_level = RiskLevel.MEDIUM
    alt_scenario = ScenarioType.LIQUIDITY_TRAP
    
    # === MSS = base du retournement ===
    if last_mss is not None and last_mss.has_fvg:
        direction = "long" if last_mss.type == "mss_bull" else "short"
        probability += 30.0  # STRUCTURAL: MSS complet = 30% de base (signal ICT puissant)
        reasoning.append(f"MSS_{last_mss.type} avec FVG = retournement confirmé")
        supporting.append("mss_with_fvg")
    elif last_choch is not None:
        direction = "long" if "bull" in last_choch else "short"
        probability += 15.0  # STRUCTURAL: CHOCH seul = 15% (moins puissant que MSS)
        reasoning.append(f"CHOCH_{last_choch} sans displacement = retournement faible")
        supporting.append("choch_without_mss")
        contradicting.append("no_displacement_no_fvg")
    else:
        probability += 3.0  # STRUCTURAL: pas de CHOCH/MSS = retournement peu probable
        reasoning.append("Pas de CHOCH/MSS = retournement peu probable")
        contradicting.append("no_reversal_signal")
    
    # === Sweep de liquidité = +probabilité ===
    if last_sweep is not None:
        sweep_direction = last_sweep.direction
        if (direction == "long" and sweep_direction == "low") or \
           (direction == "short" and sweep_direction == "high"):
            probability += 15.0  # STRUCTURAL: sweep aligné avec retournement = +15%
            supporting.append("sweep_aligned_with_reversal")
            reasoning.append(f"Sweep {sweep_direction} aligné avec retournement {direction}")
        else:
            probability -= 5.0  # STRUCTURAL: sweep contre-direction = -5%
            contradicting.append("sweep_counter_direction")
            reasoning.append(f"Sweep {sweep_direction} contre le retournement {direction}")
    
    # === Killzone = +probabilité ===
    if killzone and killzone.is_active:
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("killzone_active")
        reasoning.append(f"Killzone {killzone.name} active = momentum pour retournement")
    
    # === PO3 Distribution = +probabilité ===
    if po3_phase and po3_phase.is_distribution:
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("po3_distribution")
        reasoning.append("PO3 phase distribution = momentum pour retournement")
    
    # === Zone favorable = +probabilité ===
    if zone.zone == "discount" and direction == "long":
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("zone_discount_for_long")
    elif zone.zone == "premium" and direction == "short":
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("zone_premium_for_short")
    
    # === FVG/OB pour l'entrée ===
    if direction != "neutral":
        fvg = find_fvg_at_price(fvgs, price, direction)
        ob = find_ob_at_price(obs, price, direction)
        breaker = find_breaker_at_price(breaker_blocks, price, direction)
        
        if fvg:
            probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("fvg_entry")
            reasoning.append("FVG dans la zone d'entrée = retracement probable")
        if ob:
            probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("ob_entry")
        if breaker:
            probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("breaker_entry")
    
    # === Conditions de confirmation ===
    if direction == "long":
        # Le MSS bull est confirmé si le prix reste au-dessus du FVG
        if last_mss and last_mss.fvg_created:
            confirmations.append(ScenarioCondition(
                description="Prix reste au-dessus du FVG du MSS",
                price_level=last_mss.fvg_created.gap_bottom,
                condition_type="above",
            ))
        # Invalidation : close en-dessous du sweep low
        if last_sweep and last_sweep.direction == "low":
            invalidations.append(ScenarioCondition(
                description="Close en-dessous du sweep low = piège",
                price_level=last_sweep.sweep_price,
                condition_type="below",
            ))
    
    elif direction == "short":
        if last_mss and last_mss.fvg_created:
            confirmations.append(ScenarioCondition(
                description="Prix reste en-dessous du FVG du MSS",
                price_level=last_mss.fvg_created.gap_top,
                condition_type="below",
            ))
        if last_sweep and last_sweep.direction == "high":
            invalidations.append(ScenarioCondition(
                description="Close au-dessus du sweep high = piège",
                price_level=last_sweep.sweep_price,
                condition_type="above",
            ))
    
    # === Action ===
    if probability >= 50.0:  # STRUCTURAL: threshold from params
        action = f"enter_{direction}" if direction != "neutral" else "wait"
        risk_level = RiskLevel.LOW
    elif probability >= 30.0:  # STRUCTURAL: threshold from params
        action = "wait_for_fvg_retest"
        risk_level = RiskLevel.MEDIUM
    elif probability >= 15.0:  # STRUCTURAL: threshold from params
        action = "watch"
        risk_level = RiskLevel.HIGH
    else:
        action = "wait"
        risk_level = RiskLevel.EXTREME
    
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp probability to valid range
    
    return Scenario(
        scenario_type=ScenarioType.TREND_REVERSAL,
        direction=direction,
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        confirmations=confirmations,
        invalidations=invalidations,
        risk_level=risk_level,
        action=action,
        alternative_scenario_type=alt_scenario,
    )


def _build_liquidity_trap_scenario(
    price, atr, swings, fvgs, obs, liquidity_levels,
    breaker_blocks, pdhl_levels, last_sweep, htf_bias,
    current_trend, killzone, zone, displacement_atr,
) -> Scenario:
    """
    Scenario LIQUIDITY TRAP : Sweep + continuation dans la direction du sweep.
    
    Le piège de liquidité : le marché sweep des stops, les traders
    pensent à un retournement, mais le marché continue dans la direction
    du sweep. C'est un scenario DANGEREUX car il contredit les setups
    de retournement.
    
    "Si le sweep est un piège, le marché continue au-delà du sweep."
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    direction = "neutral"
    action = "wait"
    risk_level = RiskLevel.HIGH
    alt_scenario = ScenarioType.TREND_REVERSAL
    
    # === Sweep récent = base du piège ===
    if last_sweep is not None:
        # Le piège = continuation dans la direction du sweep
        # Sweep high (mèche au-dessus) + continuation haussière = piège bear
        # Sweep low (mèche en-dessous) + continuation baissière = piège bull
        if last_sweep.direction == "high":
            direction = "long"  # STRUCTURAL: sweep high + continuation up = piège
            probability += 15.0  # STRUCTURAL: probability weight from ICT hierarchy
            reasoning.append("Sweep high détecté — si continuation haussière = piège bear")
        elif last_sweep.direction == "low":
            direction = "short"  # STRUCTURAL: sweep low + continuation down = piège
            probability += 15.0  # STRUCTURAL: probability weight from ICT hierarchy
            reasoning.append("Sweep low détecté — si continuation baissière = piège bull")
        
        # Pas de displacement = +probabilité de piège
        if not displacement_significant_currently(displacement_atr):
            probability += 10.0  # STRUCTURAL: pas de displacement après sweep = probable piège
            supporting.append("no_displacement_after_sweep")
            reasoning.append("Pas de displacement après sweep = probable piège")
        else:
            contradicting.append("displacement_after_sweep")
            reasoning.append("Displacement après sweep = retournement probable, pas piège")
        
        # Pas de FVG = +probabilité de piège
        fvg = find_fvg_at_price(fvgs, price, "long" if direction == "long" else "short")
        if not fvg:
            probability += 10.0  # STRUCTURAL: pas de FVG = pas de déséquilibre = piège probable
            supporting.append("no_fvg_after_sweep")
            reasoning.append("Pas de FVG créé après sweep = pas de retournement confirmé")
        else:
            contradicting.append("fvg_after_sweep")
        
        # HTF aligné avec la direction du sweep = +probabilité de piège
        if (direction == "long" and htf_bias == "bullish") or \
           (direction == "short" and htf_bias == "bearish"):
            probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("htf_aligned_with_trap")
            reasoning.append("HTF aligné avec la direction du sweep = piège probable")
    else:
        probability += 2.0  # STRUCTURAL: pas de sweep = piège peu probable
        reasoning.append("Pas de sweep récent = piège de liquidité peu probable")
    
    action = "avoid_counter_trend" if probability >= 20.0 else "wait"  # STRUCTURAL: threshold from params
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp probability to valid range
    
    return Scenario(
        scenario_type=ScenarioType.LIQUIDITY_TRAP,
        direction=direction,
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        risk_level=risk_level,
        action=action,
        alternative_scenario_type=alt_scenario,
    )


def _build_false_breakout_scenario(
    price, atr, swings, fvgs, obs, liquidity_levels,
    last_bos, last_choch, htf_bias, current_trend,
    killzone, zone, displacement_atr,
) -> Scenario:
    """
    Scenario FALSE BREAKOUT : BOS + retour immédiat.
    
    Le marché casse un niveau (BOS) mais revient immédiatement
    en-dessous/au-dessus. C'est un piège pour les traders qui
    entrent sur le BOS.
    
    "Si le BOS est faux, le marché revient dans le range."
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    direction = "neutral"
    action = "wait"
    risk_level = RiskLevel.HIGH
    alt_scenario = ScenarioType.TREND_CONTINUATION
    
    # BOS récent = base du faux breakout
    if last_bos is not None:
        if last_bos == "bos_bull":
            direction = "short"  # STRUCTURAL: faux BOS bull = retournement baissier
            reasoning.append("BOS bull possible — si faux, retour baissier")
        elif last_bos == "bos_bear":
            direction = "long"  # STRUCTURAL: faux BOS bear = retournement haussier
            reasoning.append("BOS bear possible — si faux, retour haussier")
        
        # Pas de displacement = +probabilité de faux breakout
        if not displacement_significant_currently(displacement_atr):
            probability += 15.0  # STRUCTURAL: BOS sans displacement = probable faux
            supporting.append("bos_without_displacement")
            reasoning.append("BOS sans displacement significatif = probable faux breakout")
        else:
            probability += 5.0  # STRUCTURAL: BOS avec displacement = faux moins probable
            contradicting.append("displacement_confirms_bos")
            reasoning.append("BOS avec displacement = probable vrai breakout")
        
        # HTF contre le BOS = +probabilité de faux
        if (last_bos == "bos_bull" and htf_bias == "bearish") or \
           (last_bos == "bos_bear" and htf_bias == "bullish"):
            probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("htf_against_bos")
            reasoning.append("HTF contre le BOS = probable faux breakout")
        else:
            contradicting.append("htf_with_bos")
        
        # Hors killzone = +probabilité de faux
        if killzone is None or not killzone.is_active:
            probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("no_killzone")
            reasoning.append("Hors killzone = faux breakout plus probable")
    else:
        probability += 2.0  # STRUCTURAL: probability weight from ICT hierarchy
        reasoning.append("Pas de BOS récent = faux breakout peu probable")
    
    action = "avoid_breakout_entry" if probability >= 20.0 else "wait"  # STRUCTURAL: threshold from params
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp probability to valid range
    
    return Scenario(
        scenario_type=ScenarioType.FALSE_BREAKOUT,
        direction=direction,
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        risk_level=risk_level,
        action=action,
        alternative_scenario_type=alt_scenario,
    )


def _build_range_bound_scenario(
    price, atr, swings, fvgs, obs, liquidity_levels,
    htf_bias, current_trend, killzone, zone, displacement_atr,
) -> Scenario:
    """
    Scenario RANGE BOUND : pas de structure claire → range.
    
    Le marché est en range entre un swing high et un swing low.
    Pas de tendance claire, pas de BOS/CHOCH récent.
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    
    # Pas de tendance = +probabilité de range
    if current_trend == "neutral":
        probability += 25.0  # STRUCTURAL: tendance neutre = probable range
        supporting.append("neutral_trend")
        reasoning.append("Tendance neutre = marché en range probable")
    else:
        contradicting.append("trend_exists")
        reasoning.append("Tendance existe = range moins probable")
    
    # Pas de displacement = +probabilité de range
    if not displacement_significant_currently(displacement_atr):
        probability += 15.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("no_displacement")
        reasoning.append("Pas de displacement = pas de mouvement directionnel")
    
    # Pas de BOS/CHOCH = +probabilité de range
    # (déjà couvert par trend neutral)
    
    # HTF neutral = +probabilité de range
    if htf_bias == "neutral":
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("htf_neutral")
        reasoning.append("HTF neutre = pas de biais directionnel")
    
    # Zone equilibrium = +probabilité de range
    if zone.zone == "equilibrium":
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("zone_equilibrium")
        reasoning.append("Zone equilibrium = prix au milieu du range")
    
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp probability to valid range
    
    return Scenario(
        scenario_type=ScenarioType.RANGE_BOUND,
        direction="neutral",
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        risk_level=RiskLevel.MEDIUM,
        action="avoid_range_trading" if probability >= 30.0 else "wait",  # STRUCTURAL: threshold from params
        alternative_scenario_type=ScenarioType.TREND_CONTINUATION,
    )


def _build_manipulation_scenario(
    price, atr, swings, fvgs, obs, liquidity_levels,
    last_sweep, htf_bias, current_trend, killzone, zone,
    displacement_atr, po3_phase,
) -> Scenario:
    """
    Scenario MANIPULATION : PO3 sweep sans distribution.
    
    Le marché est en phase de manipulation PO3 : sweep de liquidité
    sans displacement significatif. Les institutionnels chassent les
    stops mais ne distribuent pas encore.
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    direction = "neutral"
    
    # PO3 manipulation = base
    if po3_phase and po3_phase.phase == "manipulation":
        probability += 30.0  # STRUCTURAL: PO3 manipulation confirmé = 30%
        supporting.append("po3_manipulation")
        reasoning.append("PO3 phase manipulation = sweep en cours")
        direction = "long" if last_sweep and last_sweep.direction == "low" else "short"
    elif last_sweep is not None and not displacement_significant_currently(displacement_atr):
        probability += 15.0  # STRUCTURAL: sweep sans displacement = probable manipulation
        supporting.append("sweep_no_displacement")
        reasoning.append("Sweep sans displacement = probable manipulation")
        direction = "long" if last_sweep.direction == "low" else "short"
    else:
        probability += 3.0  # STRUCTURAL: probability weight from ICT hierarchy
        reasoning.append("Pas de sweep/PO3 manipulation = scenario peu probable")
    
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp probability to valid range
    
    return Scenario(
        scenario_type=ScenarioType.MANIPULATION,
        direction=direction,
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        risk_level=RiskLevel.HIGH,
        action="wait_for_distribution" if probability >= 20.0 else "wait",  # STRUCTURAL: threshold from params
        alternative_scenario_type=ScenarioType.DISTRIBUTION_BULL,
    )


def _build_distribution_scenario(
    dist_direction, price, atr, swings, fvgs, obs, liquidity_levels,
    breaker_blocks, pdhl_levels, last_mss, last_sweep,
    htf_bias, current_trend, killzone, zone,
    displacement_atr, po3_phase,
) -> Scenario:
    """
    Scenario DISTRIBUTION : PO3 distribution (bull ou bear).
    
    Le marché est en phase de distribution PO3 : les institutionnels
    distribuent leur position avec displacement. C'est le moment
    d'entrer dans le trade.
    """
    probability = 0.0
    reasoning = []
    supporting = []
    contradicting = []
    direction = "long" if dist_direction == "bull" else "short"
    
    # PO3 distribution = base
    if po3_phase and po3_phase.is_distribution:
        probability += 25.0  # STRUCTURAL: PO3 distribution = 25%
        supporting.append("po3_distribution")
        reasoning.append(f"PO3 phase distribution = momentum {direction}")
    
    # Displacement significatif dans la direction
    if displacement_significant_currently(displacement_atr):
        probability += 15.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("displacement_significant")
        reasoning.append("Displacement significatif = distribution institutionnelle")
    
    # MSS aligné
    if last_mss and last_mss.has_fvg:
        mss_dir = "long" if last_mss.type == "mss_bull" else "short"
        if mss_dir == direction:
            probability += 15.0  # STRUCTURAL: probability weight from ICT hierarchy
            supporting.append("mss_aligned")
            reasoning.append(f"MSS aligné avec distribution {direction}")
        else:
            probability -= 10.0  # STRUCTURAL: probability weight from ICT hierarchy
            contradicting.append("mss_counter_direction")
            reasoning.append("MSS contre-direction = distribution moins probable")
    
    # Killzone
    if killzone and killzone.is_active:
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("killzone_active")
    
    # HTF aligné
    if (direction == "long" and htf_bias == "bullish") or \
       (direction == "short" and htf_bias == "bearish"):
        probability += 10.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("htf_aligned")
    
    # Zone
    if (direction == "long" and zone.zone == "discount") or \
       (direction == "short" and zone.zone == "premium"):
        probability += 5.0  # STRUCTURAL: probability weight from ICT hierarchy
        supporting.append("zone_favorable")
    
    probability = max(0.0, min(100.0, probability))  # STRUCTURAL: clamp probability to valid range
    
    scenario_type = ScenarioType.DISTRIBUTION_BULL if dist_direction == "bull" else ScenarioType.DISTRIBUTION_BEAR
    alt_type = ScenarioType.DISTRIBUTION_BEAR if dist_direction == "bull" else ScenarioType.DISTRIBUTION_BULL
    
    action = f"enter_{direction}" if probability >= 40.0 else "wait"  # STRUCTURAL: threshold from params
    
    return Scenario(
        scenario_type=scenario_type,
        direction=direction,
        probability_pct=probability,
        confidence=probability / 100.0,  # STRUCTURAL: convert pct to confidence ratio
        reasoning=reasoning,
        supporting_confluences=supporting,
        contradicting_confluences=contradicting,
        risk_level=RiskLevel.LOW if probability >= 40.0 else RiskLevel.MEDIUM,  # STRUCTURAL: threshold from params
        action=action,
        alternative_scenario_type=alt_type,
    )


# =============================================================================
# Helpers
# =============================================================================

def _normalize_probabilities(scenarios: list[Scenario]) -> list[Scenario]:
    """
    Normalise les probabilités pour que la somme = 100%.
    
    STRUCTURAL: chaque scenario a une probabilité brute, on normalise
    pour que la somme fasse 100%. Les scénarios impossibles (prob=0)
    restent à 0.
    """
    total = sum(s.probability_pct for s in scenarios)
    
    if total <= 0:
        # STRUCTURAL: si toutes les probabilités sont à 0, on distribue uniformément
        equal_prob = 100.0 / len(scenarios) if scenarios else 0
        for s in scenarios:
            s.probability_pct = equal_prob
            s.confidence = equal_prob / 100.0  # STRUCTURAL: convert pct to confidence
        return scenarios
    
    # Normaliser
    for s in scenarios:
        s.probability_pct = (s.probability_pct / total) * 100.0  # STRUCTURAL: normalize to percentage
        s.confidence = s.probability_pct / 100.0  # STRUCTURAL: convert pct to confidence
    
    return scenarios


def _identify_trap_scenario(
    scenarios: list[Scenario],
    primary: Optional[Scenario],
) -> Optional[Scenario]:
    """
    Identifie le scenario piège — celui qui contredit le primary.
    
    STRUCTURAL: le piège est le scenario qui, s'il se réalise,
    ferait perdre de l'argent sur le trade basé sur le primary.
    
    Si le primary est TREND_REVERSAL, le piège est LIQUIDITY_TRAP.
    Si le primary est TREND_CONTINUATION, le piège est FALSE_BREAKOUT.
    Si le primary est DISTRIBUTION, le piège est MANIPULATION.
    """
    if primary is None:
        return None
    
    # Le piège est le scenario alternatif du primary
    if primary.alternative_scenario_type:
        for s in scenarios:
            if s.scenario_type == primary.alternative_scenario_type:
                return s
    
    # Fallback : chercher le scenario qui contredit le plus
    if primary.direction != "neutral":
        for s in scenarios:
            if s.direction != primary.direction and s.direction != "neutral":
                return s
    
    return None


def _determine_market_state(
    primary: Optional[Scenario],
    current_trend: str,
    zone: PriceZone,
) -> str:
    """Détermine l'état global du marché."""
    if primary is None:
        return "uncertain"
    
    if primary.scenario_type == ScenarioType.TREND_CONTINUATION:
        return f"trending_{current_trend}"
    elif primary.scenario_type == ScenarioType.TREND_REVERSAL:
        return f"reversing_to_{primary.direction}"
    elif primary.scenario_type == ScenarioType.RANGE_BOUND:
        return "ranging"
    elif primary.scenario_type == ScenarioType.LIQUIDITY_TRAP:
        return "trapping"
    elif primary.scenario_type == ScenarioType.FALSE_BREAKOUT:
        return "false_breakout"
    elif primary.scenario_type == ScenarioType.MANIPULATION:
        return "manipulating"
    elif primary.scenario_type in (ScenarioType.DISTRIBUTION_BULL, ScenarioType.DISTRIBUTION_BEAR):
        return f"distributing_{primary.direction}"
    else:
        return "unknown"


def _get_current_zone(price: float, swings: list[Swing]) -> PriceZone:
    """Calcule la zone Premium/Discount actuelle."""
    confirmed = [s for s in swings if s.confirmed]
    last_high = None
    last_low = None
    for s in reversed(confirmed):
        if s.type == "swing_high" and last_high is None:
            last_high = s
        if s.type == "swing_low" and last_low is None:
            if last_high and last_low:
                break
    return get_zone(price, last_high, last_low)


def _find_last_swing_price(swings: list[Swing], swing_type: str) -> Optional[float]:
    """Trouve le prix du dernier swing d'un type donné."""
    for s in reversed(swings):
        if s.type == swing_type and s.confirmed:
            return s.price
    return None


def displacement_significant_currently(displacement_atr: float) -> bool:
    """Vérifie si le displacement est significatif."""
    return displacement_atr >= DISPLACEMENT_MIN_ATR


def _calculate_atr_at(df: pd.DataFrame, index: int) -> float:
    """Calcul de l'ATR à un index."""
    period = ATR_PERIOD  # STRUCTURAL: convention standard
    
    start = max(0, index - period + 1)
    if start >= index:
        return 0.0001  # STRUCTURAL: fallback minimal
    
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
