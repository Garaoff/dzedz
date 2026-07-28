"""
Exécution d'ordres — Bot SMC/ICT v2.

RÈGLE 5 : L'ordre ne part JAMAIS sans passer par risk_guard.validate_risk().
RÈGLE 6 : Jamais d'échec silencieux.
"""

import logging
from core.risk_guard import validate_risk, RiskValidationError
from core.signal_types import Signal
from core.sl_tp_calculator import calculate_sl_tp

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Exécuteur d'ordres — le SEUL point d'entrée pour envoyer un ordre.
    
    Flux obligatoire :
    1. calculate_sl_tp() → SL/TP structurel
    2. validate_risk() → vérification du risque (VERROU)
    3. _send_order() → envoi effectif (si validate_risk a passé)
    """
    
    def __init__(self, capital: float, broker_min_distance: float = None):
        self.capital = capital
        self.broker_min_distance = broker_min_distance
        self._orders_sent = 0
        self._orders_rejected = 0
    
    def execute_order(
        self,
        signal: Signal,
        lot_size: float,
        high: float,
        low: float,
    ) -> dict:
        """
        Exécute un ordre après vérification de risque.
        
        ÉTAPES (dans l'ordre, jamais court-circuitées) :
        1. Calcul SL/TP via sl_tp_calculator (Règle 1)
        2. Vérification risque via risk_guard (Règle 5)
        3. Envoi de l'ordre
        
        Returns:
            dict avec le résultat de l'ordre
        """
        # 1. Calcul SL/TP — Règle 1 : seule source de vérité
        try:
            sltp = calculate_sl_tp(
                signal=signal,
                high=high,
                low=low,
                broker_min_distance=self.broker_min_distance,
            )
        except Exception as e:
            logger.error(f"ORDER_REJECT | reason=sltp_calc_failed | error={e}", exc_info=True)
            self._orders_rejected += 1
            return {"status": "rejected", "reason": f"SL/TP calculation failed: {e}"}
        
        # 2. Vérification de risque — Règle 5 : VERROU, jamais de bypass
        try:
            validated_lot = validate_risk(
                capital=self.capital,
                entry_price=signal.price,
                sl_price=sltp.sl,
                lot_size=lot_size,
                setup_grade="",  # Le grade est ignoré par validate_risk (Règle 5)
                symbol=signal.signal_type.value,  # RÈGLE 1 : pip_size/pip_value par symbole
            )
        except RiskValidationError as e:
            logger.error(f"ORDER_REJECT | reason=risk_validation | error={e}", exc_info=True)
            self._orders_rejected += 1
            return {"status": "rejected", "reason": f"Risk validation failed: {e}"}
        
        # 3. Envoi de l'ordre
        order = {
            "status": "sent",
            "symbol": signal.signal_type.value,
            "direction": signal.direction.value,
            "entry": signal.price,
            "sl": sltp.sl,
            "tp": sltp.tp,
            "lot": validated_lot,
            "sl_method": sltp.sl_method,
            "tp_method": sltp.tp_method,
            "rr": sltp.rr_ratio,
            "timestamp": signal.timestamp.isoformat(),
        }
        
        self._orders_sent += 1
        logger.info(f"ORDER_SENT | {order}")
        
        # TODO: Implémenter l'envoi réel au broker
        return order
    
    def get_stats(self) -> dict:
        """Statistiques d'exécution."""
        return {
            "orders_sent": self._orders_sent,
            "orders_rejected": self._orders_rejected,
        }
