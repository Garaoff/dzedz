"""
OANDA broker adapter — Bot SMC/ICT v2.

RÈGLE 6 : Pas d'échec silencieux — toute erreur OANDA est loguée.
RÈGLE 1 : Implémente BrokerAdapter (interface unique).
RÈGLE 7 : count=10000 par défaut (pas 3000 comme dans la v1).

OANDA REST API v20 — works on Linux, Mac, Windows.
"""

import logging
import requests
from typing import Optional
from datetime import datetime

from live.brokers.base import BrokerAdapter, OrderResult, AccountInfo, PositionInfo
from config.trading_config import (
    OANDA_API_KEY,
    OANDA_ACCOUNT_ID,
    OANDA_ENVIRONMENT,
)

logger = logging.getLogger(__name__)


class OandaAdapter(BrokerAdapter):
    """
    OANDA REST API v20 adapter.
    
    OANDA format : EUR_USD (underscore), pas EURUSD
    OANDA candles : OANDA API retourne des dicts
    OANDA orders : market orders avec SL/TP obligatoires
    """
    
    def __init__(self):
        self.api_key = OANDA_API_KEY
        self.account_id = OANDA_ACCOUNT_ID
        self.environment = OANDA_ENVIRONMENT
        
        if self.environment == "practice":
            self.base_url = "https://api-fxpractice.oanda.com"  # STRUCTURAL: demo
        else:
            self.base_url = "https://api-fxtrade.oanda.com"     # STRUCTURAL: live
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._connected = False
    
    def connect(self) -> bool:
        """Connexion OANDA — vérifie que l'API est accessible."""
        if not self.api_key or not self.account_id:
            logger.error(f"OANDA_CONNECT | reason=missing_credentials | key={bool(self.api_key)} | account={bool(self.account_id)}")
            return False
        
        # Test : récupérer les infos du compte
        url = f"{self.base_url}/v3/accounts/{self.account_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        
        if response.status_code == 200:
            self._connected = True
            data = response.json()
            balance = data.get("account", {}).get("balance", "0")
            logger.info(f"OANDA_CONNECT | success | account={self.account_id} | balance={balance} | env={self.environment}")
            return True
        else:
            logger.error(f"OANDA_CONNECT | reason=api_error | status={response.status_code} | body={response.text[:200]}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """OANDA ne nécessite pas de déconnexion explicite."""
        self._connected = False
        logger.info("OANDA_DISCONNECT")
    
    def get_account_info(self) -> AccountInfo:
        """Récupère les informations du compte OANDA."""
        url = f"{self.base_url}/v3/accounts/{self.account_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"OANDA_ACCOUNT | reason=api_error | status={response.status_code}")
            return AccountInfo(capital=0, currency="", margin_used=0, margin_available=0, open_positions=0, unrealized_pnl=0)
        
        data = response.json()["account"]
        
        return AccountInfo(
            capital=float(data.get("balance", 0)),
            currency=data.get("currency", "USD"),
            margin_used=float(data.get("marginUsed", 0)),
            margin_available=float(data.get("marginAvailable", 0)),
            open_positions=int(data.get("openTradeCount", 0)),
            unrealized_pnl=float(data.get("unrealizedPL", 0)),
        )
    
    def get_candles(self, symbol: str, timeframe: str, count: int = 10000) -> list[dict]:
        """
        Récupère les candles OANDA.
        
        RÈGLE 7 : count=10000 par défaut — la v1 limitait à 3000 (bug).
        
        OANDA timeframes : M1, M5, M15, H1, H4, D
        """
        url = f"{self.base_url}/v3/instruments/{symbol}/candles"
        
        # OANDA granularity mapping
        granularity_map = {
            "M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30",
            "H1": "H1", "H4": "H4", "D": "D",
        }
        granularity = granularity_map.get(timeframe, "M1")
        
        params = {
            "granularity": granularity,
            "count": count,  # RÈGLE 7 : 10000, pas 3000
            "price": "MBA",  # Mid, Bid, Ask
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"OANDA_CANDLES | reason=api_error | symbol={symbol} | status={response.status_code} | body={response.text[:200]}")
            return []
        
        data = response.json()
        candles = data.get("candles", [])
        
        result = []
        for c in candles:
            if not c.get("complete", False):
                continue  # Skip incomplete candles
            
            mid = c.get("mid", {})
            result.append({
                "time": c.get("time", ""),
                "open": float(mid.get("o", 0)),
                "high": float(mid.get("h", 0)),
                "low": float(mid.get("l", 0)),
                "close": float(mid.get("c", 0)),
                "volume": int(c.get("volume", 0)),
            })
        
        logger.info(f"OANDA_CANDLES | symbol={symbol} | granularity={granularity} | count_requested={count} | count_received={len(result)}")
        
        return result
    
    def get_current_price(self, symbol: str) -> dict:
        """Récupère le prix actuel (bid/ask) via OANDA pricing."""
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing"
        params = {"instruments": symbol}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"OANDA_PRICE | reason=api_error | symbol={symbol} | status={response.status_code}")
            return {"bid": 0, "ask": 0, "mid": 0}
        
        data = response.json()
        prices = data.get("prices", [])
        
        if not prices:
            logger.error(f"OANDA_PRICE | reason=no_prices | symbol={symbol}")
            return {"bid": 0, "ask": 0, "mid": 0}
        
        price_data = prices[0]
        bid = float(price_data.get("bids", [{}])[0].get("price", 0))
        ask = float(price_data.get("asks", [{}])[0].get("price", 0))
        mid = (bid + ask) / 2
        
        return {"bid": bid, "ask": ask, "mid": mid}
    
    def send_order(self, symbol: str, direction: str, lot: float,
                   entry_price: float, sl: float, tp: float) -> OrderResult:
        """
        Envoie un ordre market via OANDA.
        
        RÈGLE 5 : SL obligatoire — pas d'ordre sans SL.
        """
        if sl <= 0 or tp <= 0:
            logger.error(f"OANDA_ORDER | reason=no_sl_tp | sl={sl} | tp={tp} | RÈGLE 5 VIOLÉE")
            return OrderResult(
                success=False, order_id="", entry_price=0, sl=sl, tp=tp,
                lot=lot, symbol=symbol, direction=direction,
                error="SL/TP obligatoires (Règle 5)",
            )
        
        # OANDA order format
        units = int(lot * 100000)  # STRUCTURAL: 1 lot standard = 100000 units
        if direction == "short":
            units = -units
        
        order_data = {
            "order": {
                "type": "MARKET",
                "instrument": symbol,
                "units": str(units),
                "timeInForce": "FOK",  # Fill or Kill
                "positionFill": "DEFAULT",
                "stopLossOnFill": {
                    "price": str(sl),
                    "timeInForce": "GTC",
                },
                "takeProfitOnFill": {
                    "price": str(tp),
                    "timeInForce": "GTC",
                },
            }
        }
        
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders"
        response = requests.post(url, headers=self.headers, json=order_data, timeout=15)
        
        if response.status_code in (200, 201):
            data = response.json()
            order_fill = data.get("orderFillTransaction", {})
            order_id = order_fill.get("id", "")
            fill_price = float(order_fill.get("price", entry_price))
            
            logger.info(
                f"OANDA_ORDER_SENT | success=True | order_id={order_id} | "
                f"symbol={symbol} | direction={direction} | units={units} | "
                f"entry={fill_price} | sl={sl} | tp={tp}"
            )
            
            return OrderResult(
                success=True, order_id=order_id, entry_price=fill_price,
                sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction,
                message="Order filled",
            )
        else:
            error_msg = response.text[:500]
            logger.error(
                f"OANDA_ORDER_REJECTED | status={response.status_code} | "
                f"symbol={symbol} | direction={direction} | error={error_msg}"
            )
            
            return OrderResult(
                success=False, order_id="", entry_price=0, sl=sl, tp=tp,
                lot=lot, symbol=symbol, direction=direction,
                error=error_msg,
            )
    
    def close_position(self, ticket: str) -> OrderResult:
        """Ferme une position OANDA par ticket."""
        url = f"{self.base_url}/v3/accounts/{self.account_id}/trades/{ticket}/close"
        response = requests.put(url, headers=self.headers, json={}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            close_price = float(data.get("orderFillTransaction", {}).get("price", 0))
            
            logger.info(f"OANDA_CLOSE | success=True | ticket={ticket} | price={close_price}")
            
            return OrderResult(
                success=True, order_id=ticket, entry_price=close_price,
                sl=0, tp=0, lot=0, symbol="", direction="close",
                message="Position closed",
            )
        else:
            logger.error(f"OANDA_CLOSE | reason=api_error | ticket={ticket} | status={response.status_code}")
            
            return OrderResult(
                success=False, order_id="", entry_price=0, sl=0, tp=0,
                lot=0, symbol="", direction="close",
                error=response.text[:200],
            )
    
    def modify_position(self, ticket: str, sl: Optional[float] = None,
                        tp: Optional[float] = None) -> OrderResult:
        """Modifie SL/TP d'une position OANDA."""
        # OANDA requires separate requests for SL and TP modification
        
        if sl is not None:
            url = f"{self.base_url}/v3/accounts/{self.account_id}/trades/{ticket}/orders"
            sl_order = {
                "order": {
                    "type": "STOP_LOSS",
                    "tradeID": ticket,
                    "price": str(sl),
                    "timeInForce": "GTC",
                }
            }
            response = requests.post(url, headers=self.headers, json=sl_order, timeout=10)
            
            if response.status_code not in (200, 201):
                logger.error(f"OANDA_MODIFY_SL | reason=api_error | ticket={ticket} | sl={sl} | status={response.status_code}")
                return OrderResult(success=False, order_id=ticket, entry_price=0, sl=sl, tp=tp or 0, lot=0, symbol="", direction="", error=response.text[:200])
        
        if tp is not None:
            url = f"{self.base_url}/v3/accounts/{self.account_id}/trades/{ticket}/orders"
            tp_order = {
                "order": {
                    "type": "TAKE_PROFIT",
                    "tradeID": ticket,
                    "price": str(tp),
                    "timeInForce": "GTC",
                }
            }
            response = requests.post(url, headers=self.headers, json=tp_order, timeout=10)
            
            if response.status_code not in (200, 201):
                logger.error(f"OANDA_MODIFY_TP | reason=api_error | ticket={ticket} | tp={tp} | status={response.status_code}")
                return OrderResult(success=False, order_id=ticket, entry_price=0, sl=sl or 0, tp=tp, lot=0, symbol="", direction="", error=response.text[:200])
        
        logger.info(f"OANDA_MODIFY | success=True | ticket={ticket} | sl={sl} | tp={tp}")
        
        return OrderResult(
            success=True, order_id=ticket, entry_price=0,
            sl=sl or 0, tp=tp or 0, lot=0, symbol="", direction="modify",
            message="Position modified",
        )
    
    def get_open_positions(self, symbol: str = "") -> list[PositionInfo]:
        """Récupère les positions ouvertes via OANDA."""
        url = f"{self.base_url}/v3/accounts/{self.account_id}/trades"
        params = {}
        if symbol:
            params["instrument"] = symbol
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"OANDA_POSITIONS | reason=api_error | status={response.status_code}")
            return []
        
        data = response.json()
        trades = data.get("trades", [])
        
        positions = []
        for trade in trades:
            units = int(trade.get("currentUnits", 0))
            direction = "long" if units > 0 else "short"
            
            positions.append(PositionInfo(
                ticket=trade.get("id", ""),
                symbol=trade.get("instrument", ""),
                direction=direction,
                lot=abs(units) / 100000,  # STRUCTURAL: 1 lot = 100000 units
                entry_price=float(trade.get("price", 0)),
                sl=float(trade.get("stopLossOrder", {}).get("price", 0)) if "stopLossOrder" in trade else 0,
                tp=float(trade.get("takeProfitOrder", {}).get("price", 0)) if "takeProfitOrder" in trade else 0,
                open_time=trade.get("openTime", ""),
                current_price=float(trade.get("currentUnits", 0)),  # Simplified
                pnl=float(trade.get("unrealizedPL", 0)),
            ))
        
        return positions
    
    def is_connected(self) -> bool:
        return self._connected
