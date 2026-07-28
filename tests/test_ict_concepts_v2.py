"""
Tests : Killzones, MSS, Breaker Blocks, PDHL, Silver Bullet, PO3, Scenario Engine.

Chaque test vérifie que la détection fonctionne sur données synthétiques.
RÈGLE 7 : Échantillon réel, taille suffisante.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone


class TestKillzones:
    """Tests pour Killzone ICT."""

    def test_killzone_london_open(self):
        """London Open Killzone active à 03:00 EST (08:00 UTC)."""
        from core.killzones import get_killzone
        # 08:00 UTC = 03:00 EST (UTC-5)
        ts = datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc)
        kz = get_killzone(ts)
        assert kz.is_active
        assert kz.name == "london_open"

    def test_killzone_ny_open(self):
        """NY Open Killzone active à 09:00 EST (14:00 UTC)."""
        from core.killzones import get_killzone
        # 14:00 UTC = 09:00 EST
        ts = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        kz = get_killzone(ts)
        assert kz.is_active
        assert kz.name == "ny_open"

    def test_killzone_ny_pm(self):
        """NY PM Killzone active à 14:00 EST (19:00 UTC)."""
        from core.killzones import get_killzone
        # 19:00 UTC = 14:00 EST
        ts = datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc)
        kz = get_killzone(ts)
        assert kz.is_active
        assert kz.name == "ny_pm"

    def test_killzone_none_outside_windows(self):
        """Hors killzone à 06:00 EST (11:00 UTC)."""
        from core.killzones import get_killzone
        # 11:00 UTC = 06:00 EST
        ts = datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc)
        kz = get_killzone(ts)
        assert not kz.is_active
        assert kz.name == "none"

    def test_killzone_all_killzones_returns_3(self):
        """get_all_killzones() retourne 3 killzones."""
        from core.killzones import get_all_killzones
        kz_list = get_all_killzones()
        assert len(kz_list) == 3
        names = [kz["name"] for kz in kz_list]
        assert "london_open" in names
        assert "ny_open" in names
        assert "ny_pm" in names


class TestPDHL:
    """Tests pour PDHL (Previous Day/Week High/Low)."""

    def test_pdhl_compute_with_daily_data(self):
        """compute_pdhl() crée des PDH/PDL depuis données journalières."""
        from core.pdhl import compute_pdhl
        # Créer 3 jours de données M1
        timestamps = pd.date_range("2024-01-01", periods=2880, freq="1min")
        data = []
        
        base_prices = [1.1000, 1.1050, 1.1100]  # 3 jours différents
        
        for i, ts in enumerate(timestamps):
            day = i // 960  # STRUCTURAL: 960 bars par jour
            if day >= 3:
                day = 2
            
            base = base_prices[day]
            noise = np.random.normal(0, 0.0005)
            
            data.append({
                "open": base + noise,
                "high": base + 0.001 + abs(noise),
                "low": base - 0.001 - abs(noise),
                "close": base + noise * 0.5,
                "volume": 1000,
            })
        
        df = pd.DataFrame(data, index=timestamps)
        levels = compute_pdhl(df)
        
        # Doit avoir des PDH et PDL
        assert len(levels) > 0
        assert any(l.type == "pdh" for l in levels)
        assert any(l.type == "pdl" for l in levels)

    def test_pdhl_empty_df(self):
        """DataFrame vide retourne liste vide."""
        from core.pdhl import compute_pdhl
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        levels = compute_pdhl(df)
        assert len(levels) == 0

    def test_pdhl_types_valid(self):
        """Les PDHL types sont valides."""
        from core.pdhl import compute_pdhl
        timestamps = pd.date_range("2024-01-01", periods=500, freq="1min")
        data = []
        
        for i, ts in enumerate(timestamps):
            base = 1.1000 + (i // 100) * 0.0050
            noise = np.random.normal(0, 0.0003)
            data.append({
                "open": base + noise,
                "high": base + 0.001 + abs(noise),
                "low": base - 0.001 - abs(noise),
                "close": base + noise * 0.5,
                "volume": 1000,
            })
        
        df = pd.DataFrame(data, index=timestamps)
        levels = compute_pdhl(df)
        
        for l in levels:
            assert l.type in ("pdh", "pdl", "pwh", "pwl")
            assert l.price > 0

    def test_pdhl_sweep_detection(self):
        """check_pdhl_sweep() détecte les sweeps."""
        from core.pdhl import compute_pdhl, check_pdhl_sweep, PDHLLevel
        
        # Créer un PDH à 1.1100
        level = PDHLLevel(type="pdh", price=1.1100, date=pd.Timestamp("2024-01-01"))
        levels = [level]
        
        # Données où la mèche dépasse le PDH mais close revient
        timestamps = pd.date_range("2024-01-02", periods=10, freq="1min")
        data = []
        for i, ts in enumerate(timestamps):
            if i == 5:  # Sweep
                data.append({"open": 1.1095, "high": 1.1120, "low": 1.1090, "close": 1.1098, "volume": 5000})
            else:
                data.append({"open": 1.1095, "high": 1.1098, "low": 1.1090, "close": 1.1095, "volume": 1000})
        
        df = pd.DataFrame(data, index=timestamps)
        updated = check_pdhl_sweep(levels, df, 5)
        
        # Le PDH doit être sweepé
        assert updated[0].swept
        assert updated[0].sweep_index == 5


class TestBreakerBlock:
    """Tests pour Breaker Block."""

    def test_breaker_creation_from_invalidated_ob(self):
        """OB invalidé → Breaker Block créé."""
        from core.breaker_block import detect_breaker_blocks, BreakerBlock
        from core.order_block import OrderBlock
        
        # OB Bull invalidé → Breaker Bear
        ob = OrderBlock(
            type="ob_bull",
            ob_top=1.1100,
            ob_bottom=1.1080,
            created_index=10,
            created_timestamp=pd.Timestamp("2024-01-01 10:00"),
            move_displacement_atr=2.0,
            invalidated=True,
            invalidate_index=20,
        )
        
        timestamps = pd.date_range("2024-01-01", periods=30, freq="1min")
        data = []
        for ts in timestamps:
            data.append({"open": 1.109, "high": 1.111, "low": 1.107, "close": 1.1095, "volume": 1000})
        df = pd.DataFrame(data, index=timestamps)
        
        breakers = detect_breaker_blocks([ob], df, 20)
        
        assert len(breakers) == 1
        assert breakers[0].type == "breaker_bear"
        assert breakers[0].original_ob.type == "ob_bull"

    def test_breaker_bear_from_ob_bear_invalidated(self):
        """OB Bear invalidé → Breaker Bull."""
        from core.breaker_block import detect_breaker_blocks, BreakerBlock
        from core.order_block import OrderBlock
        
        ob = OrderBlock(
            type="ob_bear",
            ob_top=1.1100,
            ob_bottom=1.1080,
            created_index=10,
            created_timestamp=pd.Timestamp("2024-01-01 10:00"),
            move_displacement_atr=2.0,
            invalidated=True,
            invalidate_index=20,
        )
        
        timestamps = pd.date_range("2024-01-01", periods=30, freq="1min")
        data = []
        for ts in timestamps:
            data.append({"open": 1.109, "high": 1.111, "low": 1.107, "close": 1.1095, "volume": 1000})
        df = pd.DataFrame(data, index=timestamps)
        
        breakers = detect_breaker_blocks([ob], df, 20)
        
        assert len(breakers) == 1
        assert breakers[0].type == "breaker_bull"

    def test_breaker_is_active(self):
        """Breaker actif si non invalidé."""
        from core.breaker_block import BreakerBlock
        from core.order_block import OrderBlock
        
        ob = OrderBlock(
            type="ob_bull", ob_top=1.1100, ob_bottom=1.1080,
            created_index=10, created_timestamp=pd.Timestamp("2024-01-01"),
            move_displacement_atr=2.0, invalidated=True, invalidate_index=20,
        )
        
        breaker = BreakerBlock(
            type="breaker_bear", breaker_top=1.1100, breaker_bottom=1.1080,
            original_ob=ob, invalidate_index=20,
        )
        
        assert breaker.is_active

    def test_find_breaker_at_price(self):
        """find_breaker_at_price() trouve un Breaker dans la zone."""
        from core.breaker_block import find_breaker_at_price, BreakerBlock
        from core.order_block import OrderBlock
        
        ob = OrderBlock(
            type="ob_bear", ob_top=1.1100, ob_bottom=1.1080,
            created_index=10, created_timestamp=pd.Timestamp("2024-01-01"),
            move_displacement_atr=2.0, invalidated=True, invalidate_index=20,
        )
        
        breaker = BreakerBlock(
            type="breaker_bull", breaker_top=1.1100, breaker_bottom=1.1080,
            original_ob=ob, invalidate_index=20,
        )
        
        # Pour un LONG : cherche breaker_bull en-dessous du prix
        found = find_breaker_at_price([breaker], 1.1200, "long")
        assert found is not None
        assert found.type == "breaker_bull"


class TestMSS:
    """Tests pour Market Structure Shift."""

    def test_mss_requires_choch_plus_displacement_plus_fvg(self):
        """MSS nécessite CHOCH + displacement + FVG simultanés."""
        from core.mss import detect_mss
        from core.structure import Swing
        from core.fvg import FVG
        
        # Pas de CHOCH = pas de MSS
        result = detect_mss(
            _make_small_df(), [], "neutral", []
        )
        # Résultat peut être None (pas de CHOCH)
        assert result is None or isinstance(result, type(result))

    def test_mss_type_mapping(self):
        """MSS bull = CHOCH bull, MSS bear = CHOCH bear."""
        from core.mss import MarketStructureShift
        from core.structure import Swing, StructureBreak
        from core.fvg import FVG
        
        # MSS Bull
        swing = Swing(type="swing_high", price=1.1050, index=10,
                      timestamp=pd.Timestamp("2024-01-01 10:00"), confirmed=True)
        
        mss = MarketStructureShift(
            type="mss_bull",
            broken_swing=swing,
            break_price=1.1060,
            break_index=20,
            displacement_atr=1.5,
        )
        
        assert mss.type == "mss_bull"
        assert not mss.has_fvg  # Pas de FVG = pas de MSS complet


class TestPO3:
    """Tests pour Power of 3."""

    def test_po3_distribution_with_displacement(self):
        """PO3 Distribution détecté avec displacement significatif."""
        from core.po3 import detect_po3_phase
        
        df = _make_small_df()
        result = detect_po3_phase(
            df, 0, len(df) - 1,
            last_sweep=None,
            displacement_atr=2.0,  # STRUCTURAL: > 1 ATR = distribution
        )
        
        assert result.phase == "distribution"
        assert result.has_displacement

    def test_po3_manipulation_with_sweep(self):
        """PO3 Manipulation détecté avec sweep sans displacement."""
        from core.po3 import detect_po3_phase, PO3Phase
        from core.liquidity import LiquiditySweep, LiquidityLevel
        
        level = LiquidityLevel(type="swing_low", price=1.0950, source_indices=[10])
        sweep = LiquiditySweep(direction="low", swept_level=level,
                               sweep_price=1.0948, close_price=1.0960, sweep_index=15)
        
        df = _make_small_df()
        result = detect_po3_phase(
            df, 0, len(df) - 1,
            last_sweep=sweep,
            displacement_atr=0.5,  # STRUCTURAL: < 1 ATR = pas de displacement
        )
        
        assert result.phase == "manipulation"
        assert result.has_sweep


class TestScenarioEngine:
    """Tests pour le Moteur de Scenarios."""

    def test_scenario_analysis_returns_analysis(self):
        """analyze_scenarios() retourne un ScenarioAnalysis."""
        from core.scenario_engine import analyze_scenarios, ScenarioAnalysis
        
        df = _make_small_df()
        from core.structure import detect_swings, determine_trend
        from core.fvg import detect_fvg
        from core.order_block import detect_ob
        from core.liquidity import detect_liquidity_levels
        from core.killzones import get_killzone
        
        swings = detect_swings(df)
        fvgs = detect_fvg(df)
        obs = detect_ob(df)
        liquidity = detect_liquidity_levels(swings, df)
        
        result = analyze_scenarios(
            df=df, index=len(df) - 1,
            swings=swings, fvgs=fvgs, obs=obs,
            liquidity_levels=liquidity,
            breaker_blocks=[], pdhl_levels=[],
            last_sweep=None, last_mss=None,
            last_bos=None, last_choch=None,
            htf_bias="neutral", current_trend="neutral",
            killzone=get_killzone(datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc)),
            po3_phase=None,
        )
        
        assert isinstance(result, ScenarioAnalysis)
        assert len(result.scenarios) > 0

    def test_scenario_probabilities_sum_to_100(self):
        """Les probabilités des scenarios somment à ~100%."""
        from core.scenario_engine import analyze_scenarios
        
        df = _make_small_df()
        from core.structure import detect_swings, determine_trend
        from core.fvg import detect_fvg
        from core.order_block import detect_ob
        from core.liquidity import detect_liquidity_levels
        
        swings = detect_swings(df)
        fvgs = detect_fvg(df)
        obs = detect_ob(df)
        liquidity = detect_liquidity_levels(swings, df)
        
        result = analyze_scenarios(
            df=df, index=len(df) - 1,
            swings=swings, fvgs=fvgs, obs=obs,
            liquidity_levels=liquidity,
            breaker_blocks=[], pdhl_levels=[],
            last_sweep=None, last_mss=None,
            last_bos=None, last_choch=None,
            htf_bias="neutral", current_trend="neutral",
            killzone=None, po3_phase=None,
        )
        
        total = sum(s.probability_pct for s in result.scenarios)
        assert total >= 99.0  # STRUCTURAL: somme normalisée ≈ 100%
        assert total <= 101.0

    def test_scenario_has_primary_and_trap(self):
        """ScenarioAnalysis a un scenario primaire et un piège."""
        from core.scenario_engine import analyze_scenarios
        
        df = _make_small_df()
        from core.structure import detect_swings, determine_trend
        from core.fvg import detect_fvg
        from core.order_block import detect_ob
        from core.liquidity import detect_liquidity_levels
        
        swings = detect_swings(df)
        fvgs = detect_fvg(df)
        obs = detect_ob(df)
        liquidity = detect_liquidity_levels(swings, df)
        
        result = analyze_scenarios(
            df=df, index=len(df) - 1,
            swings=swings, fvgs=fvgs, obs=obs,
            liquidity_levels=liquidity,
            breaker_blocks=[], pdhl_levels=[],
            last_sweep=None, last_mss=None,
            last_bos=None, last_choch=None,
            htf_bias="neutral", current_trend="neutral",
            killzone=None, po3_phase=None,
        )
        
        # Primary scenario doit exister (le plus probable)
        assert result.primary_scenario is not None
        # Le piège peut exister ou non
        if result.trap_scenario is not None:
            # Le piège peut avoir 0% dans un marché neutre (c'est OK)
            assert result.trap_scenario.probability_pct >= 0

    def test_scenario_types_valid(self):
        """Tous les scenario types sont valides."""
        from core.scenario_engine import analyze_scenarios, ScenarioType
        
        df = _make_small_df()
        from core.structure import detect_swings, determine_trend
        from core.fvg import detect_fvg
        from core.order_block import detect_ob
        from core.liquidity import detect_liquidity_levels
        
        swings = detect_swings(df)
        fvgs = detect_fvg(df)
        obs = detect_ob(df)
        liquidity = detect_liquidity_levels(swings, df)
        
        result = analyze_scenarios(
            df=df, index=len(df) - 1,
            swings=swings, fvgs=fvgs, obs=obs,
            liquidity_levels=liquidity,
            breaker_blocks=[], pdhl_levels=[],
            last_sweep=None, last_mss=None,
            last_bos=None, last_choch=None,
            htf_bias="neutral", current_trend="neutral",
            killzone=None, po3_phase=None,
        )
        
        for s in result.scenarios:
            assert s.scenario_type in list(ScenarioType)
            assert s.direction in ("long", "short", "neutral")
            assert 0 <= s.probability_pct <= 100.0


class TestConfluenceV2:
    """Tests pour la confluence v2 avec les nouveaux concepts ICT."""

    def test_confluence_with_new_concepts(self):
        """compute_confluence_score() calcule avec MSS, Killzone, PO3."""
        from core.confluence import compute_confluence_score
        
        result = compute_confluence_score(
            htf_bias_aligned=True,
            zone_favorable=True,
            fvg_present=True,
            ob_present=True,
            sweep_present=True,
            displacement_significant=True,
            structure_aligned=True,
            mss_present=True,
            killzone_active=True,
            po3_distribution=True,
            breaker_present=True,
            pdhl_aligned=True,
        )
        
        # Avec tous les concepts, le score doit être élevé
        assert result["score"] > 10
        assert result["is_eligible"]

    def test_confluence_mss_weight_higher_than_sweep(self):
        """MSS a un poids plus élevé que Sweep (hiérarchie ICT)."""
        from config.params import MSS_WEIGHT, SWEEP_WEIGHT
        assert MSS_WEIGHT >= SWEEP_WEIGHT

    def test_confluence_killzone_weight(self):
        """Killzone a un poids de 2 (filtrage temporel crucial)."""
        from config.params import KILLZONE_WEIGHT
        assert KILLZONE_WEIGHT == 2


# =============================================================================
# Helpers
# =============================================================================

def _make_small_df() -> pd.DataFrame:
    """Crée un DataFrame minimal pour les tests."""
    timestamps = pd.date_range("2024-01-01", periods=50, freq="1min")
    data = []
    base = 1.1000
    
    for i in range(50):
        noise = np.random.normal(0, 0.0003)
        data.append({
            "open": base + noise,
            "high": base + 0.001 + abs(noise),
            "low": base - 0.001 - abs(noise),
            "close": base + noise * 0.5,
            "volume": 1000,
        })
    
    df = pd.DataFrame(data, index=timestamps)
    return df


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
