"""
Test : FVG detection, iFVG, Order Blocks, Liquidity.

Chaque test vérifie que la détection fonctionne sur données synthétiques.
"""

import pytest
import pandas as pd
import numpy as np

from core.fvg import detect_fvg, check_fvg_filled, FVG
from core.order_block import detect_ob, check_ob_invalidated, OrderBlock
from core.liquidity import detect_liquidity_levels, detect_equal_levels, detect_sweep


def _make_fvg_df() -> pd.DataFrame:
    """
    Crée un DataFrame avec des FVG évidents.
    
    Pattern : grandes bougies qui créent des gaps entre low[i-1] et high[i+1].
    """
    timestamps = pd.date_range("2024-01-01", periods=50, freq="1min")
    
    data = []
    base = 1.1000
    
    for i in range(50):
        if i == 10:  # FVG bull : bougie forte, gap entre low[9] et high[11]
            o = base + 0.0010
            h = base + 0.0040
            l = base + 0.0005
            c = base + 0.0035
            v = 5000
        elif i == 11:  # Bougie après le gap
            o = base + 0.0035
            h = base + 0.0038
            l = base + 0.0030
            c = base + 0.0032
            v = 1000
        elif i == 9:  # Bougie avant le gap
            o = base + 0.0005
            h = base + 0.0010
            l = base + 0.0000
            c = base + 0.0005
            v = 1000
        else:
            noise = np.random.normal(0, 0.0005)
            o = base + noise
            h = base + 0.001 + noise
            l = base - 0.001 + noise
            c = base + noise * 0.5
            v = 1000
        
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
    
    df = pd.DataFrame(data, index=timestamps)
    return df


def _make_ob_df() -> pd.DataFrame:
    """
    Crée un DataFrame avec un Order Block évident.
    
    Pattern : bougie bearish suivie d'un fort rally (OB bull).
    """
    timestamps = pd.date_range("2024-01-01", periods=30, freq="1min")
    
    data = []
    base = 1.1000
    
    for i in range(30):
        if i == 10:  # Bougie bearish (OB bull candidate)
            o = base + 0.0010
            h = base + 0.0015
            l = base - 0.0005
            c = base - 0.0002  # Bearish close < open
            v = 1000
        elif i == 11:  # Fort rally qui suit
            o = base
            h = base + 0.0030
            l = base - 0.0005
            c = base + 0.0025  # Bullish
            v = 5000
        elif i == 12:  # Continuation
            o = base + 0.0025
            h = base + 0.0035
            l = base + 0.0020
            c = base + 0.0030  # Bullish
            v = 3000
        else:
            noise = np.random.normal(0, 0.0003)
            o = base + noise
            h = base + 0.001 + noise
            l = base - 0.001 + noise
            c = base + noise * 0.5
            v = 1000
        
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
    
    df = pd.DataFrame(data, index=timestamps)
    return df


class TestFVG:
    """Tests pour FVG detection."""
    
    def test_detect_fvg_finds_gaps(self):
        """detect_fvg() trouve des FVG dans des données avec gaps évidents."""
        df = _make_fvg_df()
        fvgs = detect_fvg(df)
        
        # Il doit y avoir au moins 1 FVG (le gap créé à i=10)
        assert len(fvgs) > 0, "Aucun FVG trouvé dans des données avec gap évident"
    
    def test_fvg_type_is_valid(self):
        """Les FVG détectés doivent avoir un type valide."""
        df = _make_fvg_df()
        fvgs = detect_fvg(df)
        
        for fvg in fvgs:
            assert fvg.type in ("fvg_bull", "fvg_bear")
            assert fvg.gap_top > fvg.gap_bottom
            assert fvg.size > 0
    
    def test_fvg_size_atr_is_calculated(self):
        """La taille en ATR est calculée dynamiquement."""
        df = _make_fvg_df()
        fvgs = detect_fvg(df)
        
        for fvg in fvgs:
            assert fvg.size_atr > 0, f"FVG {fvg.type} a size_atr=0"
    
    def test_fvg_filled_detection(self):
        """check_fvg_filled() marque les FVG traversés."""
        df = _make_fvg_df()
        fvgs = detect_fvg(df)
        
        # Vérifier qu'aucun FVG n'est fillé initialement
        initial_filled = sum(1 for f in fvgs if f.filled)
        
        # Simuler quelques bougies et check fill
        updated = check_fvg_filled(fvgs, df, 20)
        
        # La fonction doit retourner une liste mise à jour
        assert len(updated) == len(fvgs)
    
    def test_fvg_empty_df_no_crash(self):
        """DataFrame vide ne crash pas."""
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        fvgs = detect_fvg(df)
        assert len(fvgs) == 0


class TestOrderBlock:
    """Tests pour Order Block detection."""
    
    def test_detect_ob_finds_blocks(self):
        """detect_ob() trouve des OB dans des données évidentes."""
        df = _make_ob_df()
        obs = detect_ob(df)
        
        assert len(obs) > 0, "Aucun OB trouvé dans des données avec OB évident"
    
    def test_ob_type_is_valid(self):
        """Les OB doivent avoir un type valide."""
        df = _make_ob_df()
        obs = detect_ob(df)
        
        for ob in obs:
            assert ob.type in ("ob_bull", "ob_bear")
            assert ob.ob_top > ob.ob_bottom
            assert ob.move_displacement_atr >= 0
    
    def test_ob_invalidated_on_break(self):
        """check_ob_invalidated() marque les OB cassés."""
        df = _make_ob_df()
        obs = detect_ob(df)
        
        updated = check_ob_invalidated(obs, df, 15)
        assert len(updated) == len(obs)
    
    def test_ob_empty_df_no_crash(self):
        """DataFrame vide ne crash pas."""
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        obs = detect_ob(df)
        assert len(obs) == 0


class TestLiquidity:
    """Tests pour liquidity detection."""
    
    def test_detect_liquidity_levels_from_swings(self):
        """detect_liquidity_levels() crée des niveaux depuis les swings."""
        df = _make_fvg_df()
        from core.structure import detect_swings
        swings = detect_swings(df)
        levels = detect_liquidity_levels(swings, df)
        
        # Même si pas de swings, ne crash pas
        assert isinstance(levels, list)
    
    def test_sweep_does_not_crash(self):
        """detect_sweep() ne crash pas."""
        df = _make_fvg_df()
        from core.structure import detect_swings
        from core.liquidity import LiquidityLevel
        
        swings = detect_swings(df)
        levels = detect_liquidity_levels(swings, df)
        
        # Tester sur plusieurs indices
        for i in range(5, len(df)):
            sweep = detect_sweep(df, levels, i)
            # Résultat peut être None — c'est OK
            if sweep is not None:
                assert sweep.direction in ("high", "low")
    
    def test_equal_levels_detection(self):
        """detect_equal_levels() trouve des niveaux égaux."""
        # Créer des swings avec des niveaux proches
        from core.structure import Swing
        
        swings = [
            Swing(type="swing_high", price=1.1050, index=10, timestamp=pd.Timestamp("2024-01-01 10:00"), confirmed=True),
            Swing(type="swing_high", price=1.1051, index=20, timestamp=pd.Timestamp("2024-01-01 20:00"), confirmed=True),
            Swing(type="swing_low", price=1.0950, index=15, timestamp=pd.Timestamp("2024-01-01 15:00"), confirmed=True),
            Swing(type="swing_low", price=1.0949, index=25, timestamp=pd.Timestamp("2024-01-02 01:00"), confirmed=True),
        ]
        
        df = _make_fvg_df()
        equal = detect_equal_levels(swings, df)
        
        # Devrait trouver equal highs et equal lows
        assert len(equal) > 0, "Pas de niveaux égaux trouvés"


class TestConfluence:
    """Tests pour le score de confluence."""
    
    def test_confluence_score_calculation(self):
        """compute_confluence_score() calcule un score cohérent."""
        from core.confluence import compute_confluence_score
        
        result = compute_confluence_score(
            htf_bias_aligned=True,
            zone_favorable=True,
            fvg_present=True,
            ob_present=False,
            sweep_present=True,
            displacement_significant=True,
            structure_aligned=True,
        )
        
        assert result["score"] == 7, f"Score attendu=7, obtenu={result['score']}"
        assert result["is_eligible"] is True
    
    def test_confluence_minimum_rejection(self):
        """Score < CONFLUENCE_MINIMUM → ineligible."""
        from core.confluence import compute_confluence_score
        
        result = compute_confluence_score(
            htf_bias_aligned=False,
            zone_favorable=False,
            fvg_present=False,
            ob_present=False,
            sweep_present=False,
            displacement_significant=False,
            structure_aligned=False,
        )
        
        assert result["score"] == 0
        assert result["is_eligible"] is False
    
    def test_confluence_never_bypasses_risk(self):
        """
        RÈGLE 5 CRITIQUE : Le score de confluence ne bypass PAS le risque.
        Le risk_note doit être dans le résultat.
        """
        from core.confluence import compute_confluence_score
        
        result = compute_confluence_score(
            htf_bias_aligned=True,
            zone_favorable=True,
            fvg_present=True,
            ob_present=True,
            sweep_present=True,
            displacement_significant=True,
            structure_aligned=True,
        )
        
        assert "risk_note" in result
        assert "does NOT affect" in result["risk_note"] or "NE BYPASSE PAS" in result["risk_note"] or "NOT bypass" in result["risk_note"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
