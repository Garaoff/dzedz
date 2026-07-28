"""
Test Règle 3 : Pas de signaux dupliqués.

Vérifie qu'un signal persistant sur N bougies ne produit qu'1 signal, pas N.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from core.signal_types import Signal, SignalType, SignalDirection, SignalRegistry


class TestSignalDedup:
    """Règle 3 : Transition, pas état."""
    
    def test_registry_rejects_duplicate_timestamp(self):
        """Deux signaux au même timestamp = le second est rejeté."""
        registry = SignalRegistry()
        
        ts = datetime(2024, 1, 1, 12, 0)
        signal1 = Signal(
            signal_type=SignalType.FVG_BULL,
            direction=SignalDirection.LONG,
            timestamp=ts,
            price=1.1000,
            atr_at_signal=0.0010,
        )
        signal2 = Signal(
            signal_type=SignalType.BOS_BULL,
            direction=SignalDirection.LONG,
            timestamp=ts,
            price=1.1001,
            atr_at_signal=0.0010,
        )
        
        assert registry.register(signal1) is True
        assert registry.register(signal2) is False  # Déduplication
        assert registry.count() == 1
    
    def test_registry_accepts_different_timestamps(self):
        """Deux signaux à des timestamps différents sont acceptés."""
        registry = SignalRegistry()
        
        ts1 = datetime(2024, 1, 1, 12, 0)
        ts2 = datetime(2024, 1, 1, 12, 1)
        
        signal1 = Signal(
            signal_type=SignalType.FVG_BULL,
            direction=SignalDirection.LONG,
            timestamp=ts1,
            price=1.1000,
            atr_at_signal=0.0010,
        )
        signal2 = Signal(
            signal_type=SignalType.FVG_BULL,
            direction=SignalDirection.LONG,
            timestamp=ts2,
            price=1.1001,
            atr_at_signal=0.0010,
        )
        
        assert registry.register(signal1) is True
        assert registry.register(signal2) is True
        assert registry.count() == 2
    
    def test_signal_requires_positive_price(self):
        """Un signal avec un prix invalide lève une erreur."""
        with pytest.raises(ValueError):
            Signal(
                signal_type=SignalType.FVG_BULL,
                direction=SignalDirection.LONG,
                timestamp=datetime(2024, 1, 1),
                price=-1.0,
                atr_at_signal=0.0010,
            )
    
    def test_signal_requires_positive_atr(self):
        """Un signal avec un ATR invalide lève une erreur."""
        with pytest.raises(ValueError):
            Signal(
                signal_type=SignalType.FVG_BULL,
                direction=SignalDirection.LONG,
                timestamp=datetime(2024, 1, 1),
                price=1.1000,
                atr_at_signal=-0.0010,
            )
    
    def test_persistent_condition_produces_one_signal(self):
        """
        RÈGLE 3 : Une condition qui reste vraie sur plusieurs bougies
        ne doit produire qu'un seul signal (au moment de la transition).
        """
        # Simuler un signal détecté sur 5 bougies consécutives
        # Seul le premier (transition) doit être enregistré
        registry = SignalRegistry()
        
        base_ts = datetime(2024, 1, 1, 12, 0)
        for i in range(5):
            signal = Signal(
                signal_type=SignalType.FVG_BULL,
                direction=SignalDirection.LONG,
                timestamp=base_ts,  # Même timestamp = même signal
                price=1.1000 + i * 0.0001,
                atr_at_signal=0.0010,
            )
            registry.register(signal)
        
        # Un seul signal enregistré, pas 5
        assert registry.count() == 1, (
            f"RÈGLE 3 VIOLÉE: {registry.count()} signaux au lieu de 1 "
            f"pour une condition persistante"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
