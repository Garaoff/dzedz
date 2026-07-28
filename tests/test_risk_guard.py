"""
Test Règle 5 : Aucun bypass possible pour la vérification de risque.

Vérifie que validate_risk() ne peut pas être contourné,
même par un setup "Grade S" ou un lot minimum forcé.
"""

import pytest
from core.risk_guard import validate_risk, RiskValidationError
from config.params import ABSOLUTE_MAX_RISK_PCT


class TestRiskGuard:
    """Règle 5 : Un seul verrou, jamais de bypass."""
    
    def test_grade_s_does_not_bypass_risk(self):
        """
        RÈGLE 5 CRITIQUE : Un setup "Grade S" ne doit PAS pouvoir
        contourner la vérification de risque.
        """
        capital = 10000
        entry = 1.1000
        sl = 1.0000  # SL très loin → risque énorme
        
        # Le grade "S" doit être IGNORE par validate_risk
        with pytest.raises(RiskValidationError):
            validate_risk(
                capital=capital,
                entry_price=entry,
                sl_price=sl,
                lot_size=1.0,
                setup_grade="S",  # Grade S — ne doit PAS bypasser
                symbol="EURUSD",
            )
    
    def test_normal_risk_passes(self):
        """Un risque normal (1%) passe la vérification."""
        capital = 10000
        entry = 1.1000
        sl = 1.0990  # SL à 10 pips → risque modéré
        
        validated_lot = validate_risk(
            capital=capital,
            entry_price=entry,
            sl_price=sl,
            lot_size=0.01,
            symbol="EURUSD",
        )
        
        assert validated_lot > 0
    
    def test_risk_exceeds_max_gets_adjusted(self):
        """
        Un lot qui dépasse le risque max (1%) mais reste sous l'absolu (5%)
        est ajusté, pas rejeté.
        """
        capital = 10000
        entry = 1.1000
        sl = 1.0990  # 10 pips de SL
        
        # Avec lot=0.5: 10 pips × $10/pip × 0.5 lot = $50 = 0.5% → OK (under max 1%)
        # Avec lot=2.0: 10 pips × $10/pip × 2.0 lot = $200 = 2% → above max 1%, below abs 5%
        validated_lot = validate_risk(
            capital=capital,
            entry_price=entry,
            sl_price=sl,
            lot_size=2.0,  # Risque = 2% (above 1% max, below 5% absolute)
            symbol="EURUSD",
        )
        
        # Le lot doit être réduit à 0.1 (= 1% max / 10 pips × $10)
        # max_risk_amount = 10000 × 1% = $100 → lot = 100 / (10 pips × $10) = 1.0 lot
        assert validated_lot < 2.0, f"Lot non réduit: {validated_lot} >= 2.0"
        assert validated_lot > 0
    
    def test_absolute_max_cannot_be_bypassed(self):
        """Le plafond absolu ne peut pas être dépassé, même accidentellement."""
        # Même avec un lot minimum forcé, si le risque dépasse l'absolu, c'est rejeté
        capital = 1000  # Petit capital
        entry = 1.1000
        sl = 1.0000  # SL très loin
        
        with pytest.raises(RiskValidationError):
            validate_risk(
                capital=capital,
                entry_price=entry,
                sl_price=sl,
                lot_size=1.0,  # Lot minimum forcé
                setup_grade="S",  # Grade S — ne doit PAS bypasser
                symbol="EURUSD",
            )
    
    def test_capital_zero_raises_error(self):
        """Un capital de 0 lève une erreur."""
        with pytest.raises(RiskValidationError):
            validate_risk(
                capital=0,
                entry_price=1.1000,
                sl_price=1.0990,
                lot_size=0.01,
                symbol="EURUSD",
            )
    
    def test_negative_price_raises_error(self):
        """Des prix négatifs lèvent une erreur."""
        with pytest.raises(RiskValidationError):
            validate_risk(
                capital=10000,
                entry_price=-1.0,
                sl_price=1.0990,
                lot_size=0.01,
                symbol="EURUSD",
            )
    
    def test_grade_is_ignored_in_risk_check(self):
        """
        Vérifie que le grade du setup est EXPLICITEMENT ignoré
        dans la vérification de risque — Règle 5.
        """
        # Les résultats doivent être IDENTIQUES quel que soit le grade
        capital = 10000
        entry = 1.1000
        sl = 1.0990
        
        result_grade_A = validate_risk(capital, entry, sl, 0.01, setup_grade="A", symbol="EURUSD")
        result_grade_S = validate_risk(capital, entry, sl, 0.01, setup_grade="S", symbol="EURUSD")
        result_no_grade = validate_risk(capital, entry, sl, 0.01, setup_grade="", symbol="EURUSD")
        
        assert result_grade_A == result_grade_S == result_no_grade, (
            "RÈGLE 5 VIOLÉE: le grade influence le risque check"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
