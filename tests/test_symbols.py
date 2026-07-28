"""
Test config/symbols.py — Règle 1 : source unique de vérité par symbole.

Vérifie que :
1. Les 3 symboles sont configurés (XAUUSD, NAS100, BTCUSD)
2. Les paramètres pip_size, pip_value_per_lot sont cohérents
3. Les conversions de format broker fonctionnent
4. Les calculs de PnL, pips, risque sont corrects
5. Les fonctions d'accès (get_pip_size, etc.) retournent les bonnes valeurs
"""

import pytest
from config.symbols import (
    get_symbol_config, get_all_symbol_names, get_pip_size,
    get_pip_value_per_lot, get_contract_size, get_broker_format,
    get_min_lot, is_symbol_available_on_broker,
    SYMBOLS, SymbolConfig,
)


class TestSymbolConfig:
    """Règle 1 : Les 3 symboles sont configurés et cohérents."""
    
    def test_all_three_symbols_exist(self):
        """Les 3 symboles XAUUSD, NAS100, BTCUSD sont configurés."""
        names = get_all_symbol_names()
        assert "XAUUSD" in names
        assert "NAS100" in names
        assert "BTCUSD" in names
    
    def test_unsupported_symbol_raises_error(self):
        """Un symbole non supporté lève ValueError."""
        with pytest.raises(ValueError):
            get_symbol_config("EUR_USD")
    
    def test_symbol_not_found_error_message(self):
        """L'erreur contient la liste des symboles supportés."""
        try:
            get_symbol_config("FAKE")
        except ValueError as e:
            assert "XAUUSD" in str(e)
            assert "NAS100" in str(e)
            assert "BTCUSD" in str(e)


class TestSymbolParameters:
    """Règle 4 : Les paramètres sont justifiés et cohérents."""
    
    def test_xauusd_pip_size(self):
        """XAUUSD pip_size = 0.01 (prix en 2 décimales)."""
        assert get_pip_size("XAUUSD") == 0.01
    
    def test_nas100_pip_size(self):
        """NAS100 pip_size = 1.0 (1 point = 1 pip)."""
        assert get_pip_size("NAS100") == 1.0
    
    def test_btcusd_pip_size(self):
        """BTCUSD pip_size = 0.01 (prix en 2 décimales)."""
        assert get_pip_size("BTCUSD") == 0.01
    
    def test_xauusd_pip_value(self):
        """XAUUSD pip_value_per_lot = $1.00 (100 oz × $0.01 = $1/pip/lot)."""
        assert get_pip_value_per_lot("XAUUSD") == 1.00
    
    def test_nas100_pip_value(self):
        """NAS100 pip_value_per_lot = $1.00 (1 contract × $1.00/point)."""
        assert get_pip_value_per_lot("NAS100") == 1.00
    
    def test_btcusd_pip_value(self):
        """BTCUSD pip_value_per_lot = $0.01 (1 BTC × $0.01 = $0.01/pip/lot)."""
        assert get_pip_value_per_lot("BTCUSD") == 0.01
    
    def test_xauusd_contract_size(self):
        """XAUUSD contract_size = 100 (1 lot = 100 oz)."""
        assert get_contract_size("XAUUSD") == 100
    
    def test_nas100_contract_size(self):
        """NAS100 contract_size = 1 (1 lot = 1 contract unit)."""
        assert get_contract_size("NAS100") == 1
    
    def test_btcusd_contract_size(self):
        """BTCUSD contract_size = 1 (1 lot = 1 BTC)."""
        assert get_contract_size("BTCUSD") == 1
    
    def test_pip_value_equals_pip_size_times_contract(self):
        """
        Règle 4 : pip_value_per_lot = pip_size × contract_size 
        (vérification mathématique pour instruments USD-denominated).
        """
        for name, config in SYMBOLS.items():
            expected = config.pip_size * config.contract_size
            assert config.pip_value_per_lot == expected, (
                f"{name}: pip_value={config.pip_value_per_lot} != "
                f"pip_size × contract_size = {config.pip_size} × {config.contract_size} = {expected}"
            )


class TestBrokerFormats:
    """Règle 1 : Conversion format broker via source unique."""
    
    def test_xauusd_oanda_format(self):
        """XAUUSD → XAU_USD sur OANDA."""
        assert get_broker_format("XAUUSD", "oanda") == "XAU_USD"
    
    def test_xauusd_mt5_format(self):
        """XAUUSD → XAUUSD sur MT5."""
        assert get_broker_format("XAUUSD", "mt5") == "XAUUSD"
    
    def test_nas100_oanda_format(self):
        """NAS100 → NAS100_USD sur OANDA."""
        assert get_broker_format("NAS100", "oanda") == "NAS100_USD"
    
    def test_nas100_mt5_format(self):
        """NAS100 → NAS100 sur MT5."""
        assert get_broker_format("NAS100", "mt5") == "NAS100"
    
    def test_btcusd_oanda_format(self):
        """BTCUSD → BTC_USD sur OANDA."""
        assert get_broker_format("BTCUSD", "oanda") == "BTC_USD"
    
    def test_btcusd_ccxt_format(self):
        """BTCUSD → BTC/USDT sur CCXT."""
        assert get_broker_format("BTCUSD", "ccxt") == "BTC/USDT"
    
    def test_xauusd_no_ccxt_format(self):
        """XAUUSD n'est pas disponible sur CCXT (CFD)."""
        assert get_broker_format("XAUUSD", "ccxt") is None
    
    def test_nas100_no_ccxt_format(self):
        """NAS100 n'est pas disponible sur CCXT (CFD)."""
        assert get_broker_format("NAS100", "ccxt") is None
    
    def test_unknown_broker_format(self):
        """Broker inconnu retourne le nom interne."""
        result = get_broker_format("XAUUSD", "unknown_broker")
        assert result == "XAUUSD"


class TestBrokerAvailability:
    """Vérifie quels brokers supportent quels symboles."""
    
    def test_xauusd_available_oanda(self):
        assert is_symbol_available_on_broker("XAUUSD", "oanda") is True
    
    def test_xauusd_available_mt5(self):
        assert is_symbol_available_on_broker("XAUUSD", "mt5") is True
    
    def test_xauusd_not_available_ccxt(self):
        assert is_symbol_available_on_broker("XAUUSD", "ccxt") is False
    
    def test_nas100_available_oanda(self):
        assert is_symbol_available_on_broker("NAS100", "oanda") is True
    
    def test_nas100_not_available_ccxt(self):
        assert is_symbol_available_on_broker("NAS100", "ccxt") is False
    
    def test_btcusd_available_all_brokers(self):
        assert is_symbol_available_on_broker("BTCUSD", "oanda") is True
        assert is_symbol_available_on_broker("BTCUSD", "mt5") is True
        assert is_symbol_available_on_broker("BTCUSD", "ccxt") is True


class TestPnLCalculations:
    """
    Vérifie les calculs de PnL, pips, risque par symbole.
    
    Formule : pnl = pips × pip_value_per_lot × lot
    """
    
    def test_xauusd_pnl_calculation(self):
        """
        XAUUSD : 0.1 lot (10 oz), $0.50 move → pnl = $5
        
        pips = 0.50 / 0.01 = 50
        pnl = 50 × 1.00 × 0.1 = $5
        Vérifié : 10 oz × $0.50 = $5
        """
        config = get_symbol_config("XAUUSD")
        pnl = config.calculate_pnl(1950.50, 1951.00, 0.1, True)
        assert pnl == 5.0
    
    def test_nas100_pnl_calculation(self):
        """
        NAS100 : 1 lot (1 contract), $10 move → pnl = $10
        
        pips = 10 / 1.0 = 10
        pnl = 10 × 1.00 × 1.0 = $10
        Vérifié : 1 contract × $10 = $10
        """
        config = get_symbol_config("NAS100")
        pnl = config.calculate_pnl(19500, 19510, 1.0, True)
        assert pnl == 10.0
    
    def test_btcusd_pnl_calculation(self):
        """
        BTCUSD : 0.1 BTC, $100 move → pnl = $10
        
        pips = 100 / 0.01 = 10000
        pnl = 10000 × 0.01 × 0.1 = $10
        Vérifié : 0.1 BTC × $100 = $10
        """
        config = get_symbol_config("BTCUSD")
        pnl = config.calculate_pnl(65000, 65100, 0.1, True)
        assert pnl == 10.0
    
    def test_short_position_pnl(self):
        """Position SHORT : pnl = pips × pip_value × lot (positif si prix baisse)."""
        config = get_symbol_config("XAUUSD")
        pnl = config.calculate_pnl(1951.00, 1950.50, 0.1, False)
        assert pnl == 5.0  # Short gain = $5
    
    def test_calculate_pips(self):
        """Conversion prix → pips pour chaque symbole."""
        assert get_symbol_config("XAUUSD").calculate_pips(0.50) == 50.0
        assert get_symbol_config("NAS100").calculate_pips(10.0) == 10.0
        assert get_symbol_config("BTCUSD").calculate_pips(100.0) == 10000.0
    
    def test_calculate_risk_amount(self):
        """
        XAUUSD : 0.1 lot, SL distance $2.50 (250 pips) → risk = $25
        
        risk = 250 × 1.00 × 0.1 = $25
        """
        config = get_symbol_config("XAUUSD")
        risk = config.calculate_risk_amount(2.50, 0.1)
        assert risk == 25.0
    
    def test_calculate_lot_for_risk(self):
        """
        XAUUSD : risk_amount=$100, SL distance $2.50 → lot = 0.4
        
        lot = $100 / (250 pips × $1.00/pip/lot) = 0.4
        """
        config = get_symbol_config("XAUUSD")
        lot = config.calculate_lot_for_risk(100, 2.50)
        assert lot == 0.4
    
    def test_btcusd_lot_for_risk(self):
        """
        BTCUSD : risk_amount=$100, SL distance $200 (20000 pips) → lot
        
        lot = $100 / (20000 × $0.01) = 0.5 BTC
        """
        config = get_symbol_config("BTCUSD")
        lot = config.calculate_lot_for_risk(100, 200)
        assert lot == 0.5
    
    def test_nas100_lot_for_risk(self):
        """
        NAS100 : risk_amount=$100, SL distance 10 points → lot
        
        lot = $100 / (10 × $1.00) = 10 contracts
        """
        config = get_symbol_config("NAS100")
        lot = config.calculate_lot_for_risk(100, 10)
        assert lot == 10.0
    
    def test_calculate_units_for_broker_oanda(self):
        """Conversion lot → units pour OANDA."""
        # XAUUSD : 0.1 lot → 10 units (10 oz)
        config = get_symbol_config("XAUUSD")
        assert config.calculate_units_for_broker(0.1, "oanda") == 10
        
        # BTCUSD : 0.5 lot → 0.5 units (0.5 BTC)
        btc_config = get_symbol_config("BTCUSD")
        assert btc_config.calculate_units_for_broker(0.5, "oanda") == 0.5
    
    def test_zero_pips_returns_zero_lot(self):
        """SL distance = 0 → lot = 0."""
        for name in SYMBOLS:
            config = get_symbol_config(name)
            assert config.calculate_lot_for_risk(100, 0) == 0


class TestRiskGuardWithSymbols:
    """Vérifie que validate_risk utilise les paramètres par symbole."""
    
    def test_xauusd_risk_validation(self):
        """validate_risk avec XAUUSD utilise pip_size=0.01 et pip_value=1.00."""
        from core.risk_guard import validate_risk
        
        # XAUUSD: capital=10000, entry=1950, sl=1947.50 (2.50 distance = 250 pips)
        # risk = 250 × 1.00 × lot → with lot=0.04 → risk = $10 = 1%
        validated = validate_risk(
            capital=10000,
            entry_price=1950.00,
            sl_price=1947.50,
            lot_size=0.04,
            symbol="XAUUSD",
        )
        assert validated > 0
    
    def test_btcusd_risk_validation(self):
        """validate_risk avec BTCUSD utilise pip_size=0.01 et pip_value=0.01."""
        from core.risk_guard import validate_risk
        
        # BTCUSD: capital=10000, entry=65000, sl=64800 (200 distance = 20000 pips)
        # risk = 20000 × 0.01 × lot → with lot=0.5 → risk = $100 = 1%
        validated = validate_risk(
            capital=10000,
            entry_price=65000,
            sl_price=64800,
            lot_size=0.5,
            symbol="BTCUSD",
        )
        assert validated > 0
    
    def test_nas100_risk_validation(self):
        """validate_risk avec NAS100 utilise pip_size=1.0 et pip_value=1.00."""
        from core.risk_guard import validate_risk
        
        # NAS100: capital=10000, entry=19500, sl=19490 (10 distance = 10 pips)
        # risk = 10 × 1.00 × lot → with lot=10 → risk = $100 = 1%
        validated = validate_risk(
            capital=10000,
            entry_price=19500,
            sl_price=19490,
            lot_size=10.0,
            symbol="NAS100",
        )
        assert validated > 0
    
    def test_risk_guard_symbol_overrides_fallback(self):
        """
        Quand symbol est fourni, les pip_size/pip_value par symbole 
        sont utilisés, pas les fallbacks legacy EURUSD.
        """
        from core.risk_guard import validate_risk, RiskValidationError
        
        # XAUUSD avec pip_size=0.01 : 2.50 distance = 250 pips
        # Si EURUSD fallback était utilisé: 2.50 / 0.0001 = 25000 pips (completely wrong!)
        # Cela provoquerait un RiskValidationError car le risque serait énorme
        
        # Avec le bon symbol, 250 pips × 1.00 × 0.04 = $10 (1% risk) → OK
        result = validate_risk(
            capital=10000,
            entry_price=1950.00,
            sl_price=1947.50,
            lot_size=0.04,
            symbol="XAUUSD",
        )
        assert result > 0


class TestPositionSizerWithSymbols:
    """Vérifie que calculate_position_size utilise les paramètres par symbole."""
    
    def test_xauusd_position_size(self):
        """Position size pour XAUUSD avec SL de $2.50."""
        from core.position_sizer import calculate_position_size
        
        # XAUUSD: capital=10000, risk=1%=$100, sl_distance=$2.50
        # sl_pips = 2.50 / 0.01 = 250
        # lot = 100 / (250 × 1.00) = 0.4
        lot = calculate_position_size(
            capital=10000,
            entry_price=1950.00,
            sl_price=1947.50,
            symbol="XAUUSD",
        )
        assert lot == 0.4
    
    def test_btcusd_position_size(self):
        """Position size pour BTCUSD avec SL de $200."""
        from core.position_sizer import calculate_position_size
        
        # BTCUSD: capital=10000, risk=1%=$100, sl_distance=$200
        # sl_pips = 200 / 0.01 = 20000
        # lot = 100 / (20000 × 0.01) = 0.5 BTC
        lot = calculate_position_size(
            capital=10000,
            entry_price=65000,
            sl_price=64800,
            symbol="BTCUSD",
        )
        assert lot == 0.5
    
    def test_nas100_position_size(self):
        """Position size pour NAS100 avec SL de 10 points."""
        from core.position_sizer import calculate_position_size
        
        # NAS100: capital=10000, risk=1%=$100, sl_distance=10 points
        # sl_pips = 10 / 1.0 = 10
        # lot = 100 / (10 × 1.00) = 10 contracts
        lot = calculate_position_size(
            capital=10000,
            entry_price=19500,
            sl_price=19490,
            symbol="NAS100",
        )
        assert lot == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
