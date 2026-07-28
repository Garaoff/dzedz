"""
CCXT broker adapter — Crypto exchanges.

RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 1 : Implémente BrokerAdapter.

Supports: Binance, Bybit, Kraken, OKX, etc.
"""

import logging
from typing import Optional

import ccxt

from live.brokers.base import BrokerAdapter, OrderResult, AccountInfo, PositionInfo
from config.trading_config import CCXT_EXCHANGE, CCXT_API_KEY, CCXT_SECRET, CCXT_TESTNET
from config.symbols import get_broker_format, get_symbol_config, get_contract_size

logger = logging.getLogger(__name__)


class CCXTAdapter(BrokerAdapter):
    """
    CCXT exchange adapter for crypto.
    
    Format : EUR/USDT (slash), pas EUR_USD
    """
    
    def __init__(self):
        self.exchange_name = CCXT_EXCHANGE
        
        exchange_class = getattr(ccxt, self.exchange_name)
        self.exchange = exchange_class({
            "apiKey": CCXT_API_KEY,
            "secret": CCXT_SECRET,
        })
        
        if CCXT_TESTNET:
            self.exchange.set_sandbox_mode(True)  # STRUCTURAL: testnet pour demo
        
        self._connected = False
    
    def connect(self) -> bool:
        """Connexion CCXT — vérifie que l'exchange est accessible."""
        try:
            self.exchange.load_markets()
            balance = self.exchange.fetch_balance()
            
            self._connected = True
            
            total_balance = balance.get("total", {})
            logger.info(f"CCXT_CONNECT | success | exchange={self.exchange_name} | testnet={CCXT_TESTNET} | balance={total_balance}")
            return True
        
        except Exception as e:
            logger.error(f"CCXT_CONNECT | reason=connection_failed | exchange={self.exchange_name} | error={e}", exc_info=True)
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        self.exchange.close()
        self._connected = False
        logger.info("CCXT_DISCONNECT")
    
    def get_account_info(self) -> AccountInfo:
        """Récupère les infos du compte CCXT."""
        try:
            balance = self.exchange.fetch_balance()
            total = balance.get("total", {})
            
            # Crypto balance is in USDT/USD equivalent
            capital = total.get("USDT", 0) or total.get("USD", 0) or 0
            
            return AccountInfo(
                capital=capital,
                currency="USDT",
                margin_used=0,  # Spot trading, no margin
                margin_available=capital,
                open_positions=0,
                unrealized_pnl=0,
            )
        
        except Exception as e:
            logger.error(f"CCXT_ACCOUNT | reason=balance_failed | error={e}", exc_info=True)
            return AccountInfo(capital=0, currency="", margin_used=0, margin_available=0, open_positions=0, unrealized_pnl=0)
    
    def get_candles(self, symbol: str, timeframe: str, count: int = 10000) -> list[dict]:
        """
        Récupère les candles via CCXT.
        
        RÈGLE 7 : count=10000, pas 3000.
        RÈGLE 1 : La conversion de format utilise config/symbols.py.
        
        CCXT format : BTC/USDT (slash)
        CCXT timeframes : 1m, 5m, 15m, 1h, 4h, 1d
        """
        # RÈGLE 1 : Conversion via config/symbols.py
        ccxt_symbol = get_broker_format(symbol, "ccxt")
        
        if not ccxt_symbol:
            logger.error(f"CCXT_CANDLES | reason=symbol_not_available | symbol={symbol} | CCXT ne supporte pas ce symbole (CFD)")
            return []
        
        # CCXT timeframe mapping
        tf_map = {
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H4": "4h", "D": "1d",
        }
        ccxt_tf = tf_map.get(timeframe, "1m")
        
        try:
            # CCXT has a limit per request, so we fetch in batches
            all_candles = []
            remaining = count
            
            while remaining > 0:
                batch_size = min(remaining, 1000)  # STRUCTURAL: CCXT max per request = ~1000
                
                ohlcv = self.exchange.fetch_ohlcv(ccxt_symbol, ccxt_tf, limit=batch_size)
                
                for c in ohlcv:
                    all_candles.append({
                        "time": c[0],  # Timestamp ms
                        "open": c[1],
                        "high": c[2],
                        "low": c[3],
                        "close": c[4],
                        "volume": c[5],
                    })
                
                remaining -= batch_size
                
                if len(ohlcv) < batch_size:
                    break  # No more data
            
            logger.info(f"CCXT_CANDLES | symbol={ccxt_symbol} | timeframe={ccxt_tf} | count={len(all_candles)}")
            return all_candles
        
        except Exception as e:
            logger.error(f"CCXT_CANDLES | reason=fetch_failed | symbol={ccxt_symbol} | error={e}", exc_info=True)
            return []
    
    def get_current_price(self, symbol: str) -> dict:
        """Récupère le prix actuel CCXT."""
        ccxt_symbol = get_broker_format(symbol, "ccxt")
        
        if not ccxt_symbol:
            logger.error(f"CCXT_PRICE | reason=symbol_not_available | symbol={symbol}")
            return {"bid": 0, "ask": 0, "mid": 0}
        
        try:
            ticker = self.exchange.fetch_ticker(ccxt_symbol)
            bid = ticker.get("bid", 0)
            ask = ticker.get("ask", 0)
            mid = (bid + ask) / 2
            
            return {"bid": bid, "ask": ask, "mid": mid}
        
        except Exception as e:
            logger.error(f"CCXT_PRICE | reason=ticker_failed | symbol={ccxt_symbol} | error={e}", exc_info=True)
            return {"bid": 0, "ask": 0, "mid": 0}
    
    def send_order(self, symbol: str, direction: str, lot: float,
                   entry_price: float, sl: float, tp: float) -> OrderResult:
        """
        Envoie un ordre via CCXT (spot market order).
        
        RÈGLE 5 : SL obligatoire.
        RÈGLE 1 : Les conversions de format et lot→amount via config/symbols.py.
        
        Note: CCXT spot orders don't natively support SL/TP.
        We place the market order and set stop-loss via separate orders.
        """
        ccxt_symbol = get_broker_format(symbol, "ccxt")
        
        if not ccxt_symbol:
            logger.error(f"CCXT_ORDER | reason=symbol_not_available | symbol={symbol}")
            return OrderResult(success=False, order_id="", entry_price=0, sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction, error=f"CCXT ne supporte pas {symbol} (CFD uniquement)")
        
        if sl <= 0:
            logger.error(f"CCXT_ORDER | reason=no_sl | RÈGLE 5 VIOLÉE")
            return OrderResult(success=False, order_id="", entry_price=0, sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction, error="SL obligatoire (Règle 5)")
        
        side = "buy" if direction == "long" else "sell"
        
        # RÈGLE 1 : Convertir lot → amount via contract_size du symbole
        contract_size = get_contract_size(symbol)
        amount = lot * contract_size  # DYNAMIC: amount en unités de base
        
        try:
            # Place market order
            order = self.exchange.create_order(ccxt_symbol, "market", side, amount)
            
            order_id = order.get("id", "")
            fill_price = float(order.get("average", entry_price) or entry_price)
            
            # Place stop-loss order
            sl_side = "sell" if direction == "long" else "buy"
            sl_amount = amount
            
            try:
                sl_order = self.exchange.create_order(
                    ccxt_symbol, "stop_loss", sl_side, sl_amount, sl,
                    params={"triggerPrice": sl},
                )
                logger.info(f"CCXT_SL_SET | symbol={ccxt_symbol} | sl={sl} | sl_order_id={sl_order.get('id', '')}")
            except Exception as e:
                logger.warning(f"CCXT_SL_FAILED | symbol={ccxt_symbol} | sl={sl} | error={e} — ordre principal envoyé sans SL automatique")
            
            # Place TP limit order
            tp_side = "sell" if direction == "long" else "buy"
            
            try:
                tp_order = self.exchange.create_order(
                    ccxt_symbol, "limit", tp_side, amount, tp,
                )
                logger.info(f"CCXT_TP_SET | symbol={ccxt_symbol} | tp={tp} | tp_order_id={tp_order.get('id', '')}")
            except Exception as e:
                logger.warning(f"CCXT_TP_FAILED | symbol={ccxt_symbol} | tp={tp} | error={e} — ordre principal envoyé sans TP automatique")
            
            logger.info(f"CCXT_ORDER_SENT | success=True | order_id={order_id} | symbol={ccxt_symbol} | direction={direction} | amount={amount} | entry={fill_price} | sl={sl} | tp={tp}")
            
            return OrderResult(
                success=True, order_id=order_id, entry_price=fill_price,
                sl=sl, tp=tp, lot=amount, symbol=symbol, direction=direction,
                message="Order filled",
            )
        
        except Exception as e:
            logger.error(f"CCXT_ORDER | reason=order_failed | symbol={ccxt_symbol} | direction={direction} | error={e}", exc_info=True)
            return OrderResult(success=False, order_id="", entry_price=0, sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction, error=str(e))
    
    def close_position(self, ticket: str) -> OrderResult:
        """Ferme un ordre CCXT."""
        try:
            result = self.exchange.cancel_order(ticket)
            logger.info(f"CCXT_CLOSE | success=True | ticket={ticket}")
            return OrderResult(success=True, order_id=ticket, entry_price=0, sl=0, tp=0, lot=0, symbol="", direction="close", message="Order cancelled")
        
        except Exception as e:
            logger.error(f"CCXT_CLOSE | reason=close_failed | ticket={ticket} | error={e}", exc_info=True)
            return OrderResult(success=False, order_id="", entry_price=0, sl=0, tp=0, lot=0, symbol="", direction="close", error=str(e))
    
    def modify_position(self, ticket: str, sl: Optional[float] = None,
                        tp: Optional[float] = None) -> OrderResult:
        """CCXT spot orders cannot modify SL/TP after placement."""
        logger.warning(f"CCXT_MODIFY | reason=not_supported | CCXT spot ne supporte pas la modification SL/TP")
        return OrderResult(success=False, order_id=ticket, entry_price=0, sl=sl or 0, tp=tp or 0, lot=0, symbol="", direction="", error="CCXT spot orders cannot modify SL/TP")
    
    def get_open_positions(self, symbol: str = "") -> list[PositionInfo]:
        """Récupère les ordres ouverts CCXT."""
        ccxt_symbol = get_broker_format(symbol, "ccxt") if symbol else None
        
        if symbol and not ccxt_symbol:
            return []  # CFD symbol — not available on CCXT
        
        try:
            orders = self.exchange.fetch_open_orders(ccxt_symbol)
            
            positions = []
            for order in orders:
                direction = "long" if order.get("side") == "buy" else "short"
                positions.append(PositionInfo(
                    ticket=order.get("id", ""),
                    symbol=order.get("symbol", ""),
                    direction=direction,
                    lot=float(order.get("amount", 0)),
                    entry_price=float(order.get("price", 0)),
                    sl=0,  # CCXT spot doesn't track SL in position
                    tp=0,
                    open_time=str(order.get("timestamp", "")),
                    current_price=0,
                    pnl=0,
                ))
            
            return positions
        
        except Exception as e:
            logger.error(f"CCXT_POSITIONS | reason=fetch_failed | error={e}", exc_info=True)
            return []
    
    def is_connected(self) -> bool:
        return self._connected
