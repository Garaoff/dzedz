"""
MT5 broker adapter — Bot SMC/ICT v2.

⚠️ MetaTrader5 package ONLY works on Windows.
On Linux/Mac, use OANDA or CCXT instead.

RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 7 : count=10000 par défaut.
"""

import logging
from typing import Optional

from live.brokers.base import BrokerAdapter, OrderResult, AccountInfo, PositionInfo
from config.trading_config import MT5_PATH, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

logger = logging.getLogger(__name__)


class MT5Adapter(BrokerAdapter):
    """MetaTrader 5 adapter — Windows only."""
    
    def __init__(self):
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            logger.error("MT5_INIT | reason=package_not_found | MetaTrader5 package not installed or not on Windows")
            raise ImportError("MetaTrader5 package not found. Install: pip install MetaTrader5 (Windows only)")
        
        self._connected = False
    
    def connect(self) -> bool:
        """Connexion MT5."""
        if not self.mt5.initialize(path=MT5_PATH if MT5_PATH else None):
            error = self.mt5.last_error()
            logger.error(f"MT5_CONNECT | reason=initialize_failed | error={error}")
            return False
        
        if not self.mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            error = self.mt5.last_error()
            logger.error(f"MT5_CONNECT | reason=login_failed | login={MT5_LOGIN} | server={MT5_SERVER} | error={error}")
            self.mt5.shutdown()
            return False
        
        self._connected = True
        info = self.mt5.account_info()
        logger.info(f"MT5_CONNECT | success | login={info.login} | balance={info.balance} | server={info.server}")
        return True
    
    def disconnect(self) -> None:
        """Déconnexion MT5."""
        self.mt5.shutdown()
        self._connected = False
        logger.info("MT5_DISCONNECT")
    
    def get_account_info(self) -> AccountInfo:
        """Récupère les infos du compte MT5."""
        info = self.mt5.account_info()
        
        if info is None:
            error = self.mt5.last_error()
            logger.error(f"MT5_ACCOUNT | reason=info_failed | error={error}")
            return AccountInfo(capital=0, currency="", margin_used=0, margin_available=0, open_positions=0, unrealized_pnl=0)
        
        return AccountInfo(
            capital=info.balance,
            currency=info.currency,
            margin_used=info.margin,
            margin_available=info.margin_free,
            open_positions=self.mt5.positions_total(),
            unrealized_pnl=info.profit,
        )
    
    def get_candles(self, symbol: str, timeframe: str, count: int = 10000) -> list[dict]:
        """
        Récupère les candles MT5.
        
        RÈGLE 7 : count=10000, pas 3000.
        
        MT5 format : EURUSD (pas underscore)
        """
        # MT5 timeframe mapping
        tf_map = {
            "M1": self.mt5.TIMEFRAME_M1,
            "M5": self.mt5.TIMEFRAME_M5,
            "M15": self.mt5.TIMEFRAME_M15,
            "H1": self.mt5.TIMEFRAME_H1,
            "H4": self.mt5.TIMEFRAME_H4,
            "D": self.mt5.TIMEFRAME_D1,
        }
        
        mt5_tf = tf_map.get(timeframe, self.mt5.TIMEFRAME_M1)
        
        # Convertir EUR_USD → EURUSD (MT5 format)
        mt5_symbol = symbol.replace("_", "")
        
        candles = self.mt5.copy_rates_from_pos(mt5_symbol, mt5_tf, 0, count)
        
        if candles is None:
            error = self.mt5.last_error()
            logger.error(f"MT5_CANDLES | reason=data_failed | symbol={mt5_symbol} | error={error}")
            return []
        
        result = []
        for c in candles:
            result.append({
                "time": str(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": int(c[5]),
            })
        
        logger.info(f"MT5_CANDLES | symbol={mt5_symbol} | timeframe={timeframe} | count={len(result)}")
        return result
    
    def get_current_price(self, symbol: str) -> dict:
        """Récupère le prix actuel MT5."""
        mt5_symbol = symbol.replace("_", "")
        tick = self.mt5.symbol_info_tick(mt5_symbol)
        
        if tick is None:
            logger.error(f"MT5_PRICE | reason=tick_failed | symbol={mt5_symbol}")
            return {"bid": 0, "ask": 0, "mid": 0}
        
        return {"bid": tick.bid, "ask": tick.ask, "mid": (tick.bid + tick.ask) / 2}
    
    def send_order(self, symbol: str, direction: str, lot: float,
                   entry_price: float, sl: float, tp: float) -> OrderResult:
        """Envoie un ordre MT5."""
        mt5_symbol = symbol.replace("_", "")
        
        if sl <= 0 or tp <= 0:
            logger.error(f"MT5_ORDER | reason=no_sl_tp | RÈGLE 5 VIOLÉE")
            return OrderResult(success=False, order_id="", entry_price=0, sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction, error="SL/TP obligatoires")
        
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": lot,
            "type": self.mt5.ORDER_TYPE_BUY if direction == "long" else self.mt5.ORDER_TYPE_SELL,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,  # STRUCTURAL: 20 points deviation tolerance
            "magic": 234000,  # STRUCTURAL: magic number pour identifier nos trades
            "comment": "SMCICT_v2",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        
        result = self.mt5.order_send(request)
        
        if result is None or result.retcode != self.mt5.TRADE_RETCODE_DONE:
            error = self.mt5.last_error() if result is None else result.retcode
            logger.error(f"MT5_ORDER | reason=order_failed | error={error} | request={request}")
            return OrderResult(success=False, order_id="", entry_price=0, sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction, error=str(error))
        
        logger.info(f"MT5_ORDER_SENT | success=True | ticket={result.order} | symbol={mt5_symbol} | direction={direction} | lot={lot} | entry={result.price} | sl={sl} | tp={tp}")
        
        return OrderResult(
            success=True, order_id=str(result.order), entry_price=result.price,
            sl=sl, tp=tp, lot=lot, symbol=symbol, direction=direction,
            message="Order filled",
        )
    
    def close_position(self, ticket: str) -> OrderResult:
        """Ferme une position MT5."""
        position = self.mt5.positions_get(ticket=int(ticket))
        
        if position is None or len(position) == 0:
            logger.error(f"MT5_CLOSE | reason=position_not_found | ticket={ticket}")
            return OrderResult(success=False, order_id=ticket, entry_price=0, sl=0, tp=0, lot=0, symbol="", direction="close", error="Position not found")
        
        pos = position[0]
        close_type = self.mt5.ORDER_TYPE_SEELL if pos.type == self.mt5.ORDER_TYPE_BUY else self.mt5.ORDER_TYPE_BUY
        price = pos.price_current
        
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": int(ticket),
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "SMCICT_v2_close",
        }
        
        result = self.mt5.order_send(request)
        
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5_CLOSE | reason=close_failed | ticket={ticket} | retcode={result.retcode}")
            return OrderResult(success=False, order_id=ticket, entry_price=0, sl=0, tp=0, lot=0, symbol="", direction="close", error=str(result.retcode))
        
        logger.info(f"MT5_CLOSE | success=True | ticket={ticket} | price={result.price}")
        return OrderResult(success=True, order_id=str(result.order), entry_price=result.price, sl=0, tp=0, lot=0, symbol="", direction="close", message="Position closed")
    
    def modify_position(self, ticket: str, sl: Optional[float] = None,
                        tp: Optional[float] = None) -> OrderResult:
        """Modifie SL/TP d'une position MT5."""
        position = self.mt5.positions_get(ticket=int(ticket))
        
        if position is None or len(position) == 0:
            return OrderResult(success=False, order_id=ticket, entry_price=0, sl=sl or 0, tp=tp or 0, lot=0, symbol="", direction="", error="Position not found")
        
        pos = position[0]
        
        request = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": int(ticket),
            "sl": sl if sl is not None else pos.sl,
            "tp": tp if tp is not None else pos.tp,
        }
        
        result = self.mt5.order_send(request)
        
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5_MODIFY | reason=modify_failed | ticket={ticket} | retcode={result.retcode}")
            return OrderResult(success=False, order_id=ticket, entry_price=0, sl=sl or 0, tp=tp or 0, lot=0, symbol="", direction="", error=str(result.retcode))
        
        logger.info(f"MT5_MODIFY | success=True | ticket={ticket} | sl={sl} | tp={tp}")
        return OrderResult(success=True, order_id=ticket, entry_price=0, sl=sl or 0, tp=tp or 0, lot=0, symbol="", direction="modify", message="Position modified")
    
    def get_open_positions(self, symbol: str = "") -> list[PositionInfo]:
        """Récupère les positions ouvertes MT5."""
        mt5_symbol = symbol.replace("_", "") if symbol else ""
        
        if mt5_symbol:
            positions = self.mt5.positions_get(symbol=mt5_symbol)
        else:
            positions = self.mt5.positions_get()
        
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            direction = "long" if pos.type == self.mt5.ORDER_TYPE_BUY else "short"
            result.append(PositionInfo(
                ticket=str(pos.ticket),
                symbol=pos.symbol,
                direction=direction,
                lot=pos.volume,
                entry_price=pos.price_open,
                sl=pos.sl,
                tp=pos.tp,
                open_time=str(pos.time),
                current_price=pos.price_current,
                pnl=pos.profit,
            ))
        
        return result
    
    def is_connected(self) -> bool:
        return self._connected
