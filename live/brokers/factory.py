"""
Broker factory — Crée le bon adapter selon BROKER_TYPE.

RÈGLE 1 : Un seul point d'entrée pour créer un broker.
"""

import logging

from live.brokers.base import BrokerAdapter
from config.trading_config import BROKER_TYPE

logger = logging.getLogger(__name__)


def create_broker(broker_type: str = BROKER_TYPE) -> BrokerAdapter:
    """
    Crée le broker adapter selon le type configuré.
    
    RÈGLE 1 : Un seul factory — tous les modules passent par ici.
    """
    if broker_type == "oanda":
        from live.brokers.oanda import OandaAdapter
        adapter = OandaAdapter()
        logger.info(f"BROKER_CREATE | type=oanda | env={adapter.environment}")
        return adapter
    
    elif broker_type == "mt5":
        try:
            from live.brokers.mt5 import MT5Adapter
            adapter = MT5Adapter()
            logger.info(f"BROKER_CREATE | type=mt5")
            return adapter
        except ImportError:
            logger.error("BROKER_CREATE | reason=mt5_not_available | MetaTrader5 package only works on Windows")
            raise ImportError("MetaTrader5 n'est disponible que sur Windows. Utilise OANDA ou CCXT sur Linux/Mac.")
    
    elif broker_type == "ccxt":
        from live.brokers.ccxt_adapter import CCXTAdapter
        adapter = CCXTAdapter()
        logger.info(f"BROKER_CREATE | type=ccxt | exchange={adapter.exchange_name}")
        return adapter
    
    else:
        logger.error(f"BROKER_CREATE | reason=unknown_type | type={broker_type}")
        raise ValueError(f"Broker type inconnu: {broker_type}. Utilise: oanda, mt5, ccxt")
