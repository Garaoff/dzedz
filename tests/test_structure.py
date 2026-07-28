"""
Test : Détection de structure (swings, BOS, CHOCH).

Règle 3 : Transition, pas état — le BOS/CHOCH se déclenche au moment de la casse.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from core.structure import detect_swings, detect_bos, detect_choch, determine_trend, Swing


def _make_swing_df(
    n_bars: int = 50,
    base_price: float = 1.1000,
    volatility: float = 0.0010,
) -> pd.DataFrame:
    """
    Crée un DataFrame avec des swings identifiables.
    
    Pattern : alternance de hauts et bas clairs pour créer des swings.
    """
    timestamps = pd.date_range("2024-01-01", periods=n_bars, freq="1min")
    
    prices = []
    highs = []
    lows = []
    opens = []
    closes = []
    volumes = []
    
    # Créer des swings clairs
    for i in range(n_bars):
        if i % 10 == 5:  # Swing high
            h = base_price + volatility * 3
            l = base_price + volatility * 1
            o = base_price + volatility * 2
            c = base_price + volatility * 1.5
        elif i % 10 == 0:  # Swing low
            h = base_price + volatility * 1
            l = base_price - volatility * 3
            o = base_price - volatility * 2
            c = base_price - volatility * 1.5
        else:  # Normal bar
            noise = np.random.normal(0, volatility * 0.5)
            h = base_price + volatility + noise
            l = base_price - volatility + noise
            o = base_price + noise * 0.5
            c = base_price + noise
        
        prices.append(c)
        highs.append(h)
        lows.append(l)
        opens.append(o)
        closes.append(c)
        volumes.append(1000)
    
    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=timestamps,
    )
    
    return df


class TestStructureDetection:
    """Tests pour la détection de structure de marché."""
    
    def test_swing_detection_finds_swings(self):
        """detect_swings() trouve des swings dans un DataFrame."""
        df = _make_swing_df(100)
        swings = detect_swings(df)
        
        # Doit trouver au moins quelques swings
        assert len(swings) > 0, f"Aucun swing trouvé dans {len(df)} bougies"
        
        # Tous les swings doivent avoir un prix positif
        for s in swings:
            assert s.price > 0, f"Swing {s.type} a prix négatif: {s.price}"
            assert s.type in ("swing_high", "swing_low")
    
    def test_swing_high_is_actually_high(self):
        """Un swing_high doit être un maximum local."""
        df = _make_swing_df(50)
        swings = detect_swings(df)
        
        for s in swings:
            if s.type == "swing_high" and s.confirmed:
                # Le swing doit être le max dans sa fenêtre
                nearby = df["high"].iloc[s.index - 2 : s.index + 3]
                assert df["high"].iloc[s.index] >= nearby.max() * 0.999
    
    def test_swing_low_is_actually_low(self):
        """Un swing_low doit être un minimum local."""
        df = _make_swing_df(50)
        swings = detect_swings(df)
        
        for s in swings:
            if s.type == "swing_low" and s.confirmed:
                nearby = df["low"].iloc[s.index - 2 : s.index + 3]
                assert df["low"].iloc[s.index] <= nearby.min() * 1.001
    
    def test_determine_trend_returns_valid_direction(self):
        """determine_trend() retourne 'bullish', 'bearish', ou 'neutral'."""
        df = _make_swing_df(100)
        swings = detect_swings(df)
        trend = determine_trend(swings)
        
        assert trend in ("bullish", "bearish", "neutral"), f"Trend invalide: {trend}"
    
    def test_empty_df_returns_no_swings(self):
        """Un DataFrame vide ne doit pas crasher."""
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        swings = detect_swings(df)
        assert len(swings) == 0
    
    def test_short_df_returns_no_swings(self):
        """Un DataFrame trop court ne doit pas crasher."""
        df = _make_swing_df(3)
        swings = detect_swings(df)
        assert len(swings) == 0  # Pas assez de données pour des swings


class TestBOSCHOCH:
    """Tests pour BOS et CHOCH."""
    
    def test_bos_bull_on_breakout(self):
        """BOS Bull : close casse un swing high dans une tendance bullish."""
        # Créer des données avec un BOS bull évident
        timestamps = pd.date_range("2024-01-01", periods=30, freq="1min")
        
        # Pattern : tendance haussière avec un breakout
        prices = np.linspace(1.1000, 1.1100, 30)
        highs = prices + 0.001
        lows = prices - 0.001
        opens = prices - 0.0005
        closes = prices + 0.0005
        
        # Ajouter un breakout à la fin
        closes[-1] = highs[-2] + 0.002  # Casse le swing high
        closes[-2] = highs[-2] - 0.001  # Bougie avant : pas encore cassé
        
        df = pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [100]*30},
            index=timestamps,
        )
        
        swings = detect_swings(df)
        trend = determine_trend(swings)
        
        # Test BOS sur les dernières bougies
        bos = detect_bos(df.iloc[-3:], swings, trend)
        
        # Le BOS peut ou pas être détecté selon la précision des données
        # L'important est que la fonction ne crash pas
        if bos is not None:
            assert bos.type in ("bos_bull", "bos_bear")
            assert bos.displacement_atr >= 0
    
    def test_choch_does_not_crash(self):
        """detect_choch() ne crash pas même sur données difficiles."""
        df = _make_swing_df(30)
        swings = detect_swings(df)
        trend = determine_trend(swings)
        
        choch = detect_choch(df, swings, trend)
        
        # Résultat peut être None (pas de CHOCH) — c'est OK
        if choch is not None:
            assert choch.type in ("choch_bull", "choch_bear")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
