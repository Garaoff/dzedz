"""
Broker adapters — Bot SMC/ICT v2.

RÈGLE 6 : Pas d'échec silencieux — toute erreur de broker est loguée.
RÈGLE 1 : Une seule interface pour tous les brokers.

Trois brokers supportés :
- OANDA : REST API, forex, works everywhere
- MT5 : Windows only, forex/CFD
- CCXT : Crypto exchanges (Binance, Bybit, etc.)
"""

from live.brokers.base import BrokerAdapter, OrderResult, AccountInfo, PositionInfo
from live.brokers.factory import create_broker
