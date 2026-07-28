"""
MT5 broker adapter — Bot SMC/ICT v2.

⚠️ MetaTrader5 package ONLY works on Windows.
On Linux/Mac, use OANDA or CCXT instead.

RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 7 : count=10000 par défaut.

Le bot OUVRT AUTOMATIQUEMENT MT5 et se connecte au compte.
Pas besoin d'ouvrir MT5 manuellement avant de lancer le bot.

mt5.initialize() lance MT5 et se connecte en une seule commande :
  - Si MT5 est déjà ouvert → se connecte directement
  - Si MT5 est fermé → ouvre MT5 automatiquement et se connecte
  - Login/password/server passés directement à initialize()
"""

import logging
import os
import subprocess
import time
from typing import Optional

from live.brokers.base import BrokerAdapter, OrderResult, AccountInfo, PositionInfo
from config.trading_config import MT5_PATH, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
from config.symbols import get_broker_format, get_contract_size

logger = logging.getLogger(__name__)


class MT5Adapter(BrokerAdapter):
    """
    MetaTrader 5 adapter — Windows only.
    
    Le bot ouvre MT5 AUTOMATIQUEMENT et se connecte au compte.
    Tu n'as PAS besoin d'ouvrir MT5 manuellement avant de lancer le bot.
    
    Flux automatique :
    1. mt5.initialize(path, login, password, server) → ouvre MT5 + connecte
    2. Si MT5 est déjà ouvert → se connecte au compte directement
    3. Si MT5 est fermé → le lance et se connecte
    """
    
    def __init__(self):
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            logger.error("MT5_INIT | reason=package_not_found | MetaTrader5 package not installed or not on Windows")
            raise ImportError("MetaTrader5 package not found. Install: pip install MetaTrader5 (Windows only)")
        
        self._connected = False
    
    def connect(self) -> bool:
        """
        Ouvre MT5 automatiquement et se connecte au compte.
        
        mt5.initialize() avec login/password/server :
        - Lance MT5 si pas déjà ouvert
        - Se connecte au compte spécifié
        - Tout en une seule commande
        
        RÈGLE 6 : Pas d'échec silencieux — tout est logué.
        """
        # === 1. Trouver le chemin MT5 automatiquement ===
        mt5_path = self._find_mt5_path()
        
        logger.info(f"MT5_CONNECT | step=find_path | path={mt5_path}")
        
        # === 2. initialize() — ouvre MT5 + connecte en une commande ===
        # STRUCTURAL: mt5.initialize() avec login/password/server ouvre MT5
        # automatiquement et se connecte au compte. Pas besoin d'ouvrir MT5 manuellement.
        init_params = {}
        if mt5_path:
            init_params["path"] = mt5_path
        
        # Passer login/password/server directement à initialize()
        # Cela permet à MT5 de se connecter au bon compte automatiquement
        if MT5_LOGIN and MT5_LOGIN > 0:
            init_params["login"] = MT5_LOGIN
        if MT5_PASSWORD:
            init_params["password"] = MT5_PASSWORD
        if MT5_SERVER:
            init_params["server"] = MT5_SERVER
        
        logger.info(
            f"MT5_CONNECT | step=initialize | login={MT5_LOGIN} | "
            f"server={MT5_SERVER} | path={mt5_path} | "
            f"auto_open=True | auto_login=True"
        )
        
        # mt5.initialize() ouvre MT5 et se connecte au compte
        if not self.mt5.initialize(**init_params):
            error = self.mt5.last_error()
            logger.error(
                f"MT5_CONNECT | reason=initialize_failed | "
                f"login={MT5_LOGIN} | server={MT5_SERVER} | "
                f"path={mt5_path} | error={error}"
            )
            
            # === Retry : parfois MT5 prend du temps à démarrer ===
            logger.info("MT5_CONNECT | step=retry | waiting 5 seconds for MT5 to start...")
            time.sleep(5)  # STRUCTURAL: 5s pour laisser MT5 démarrer
            
            if not self.mt5.initialize(**init_params):
                error = self.mt5.last_error()
                logger.error(
                    f"MT5_CONNECT | reason=initialize_failed_retry | "
                    f"login={MT5_LOGIN} | server={MT5_SERVER} | error={error}"
                )
                return False
        
        # === 3. Vérifier la connexion ===
        info = self.mt5.account_info()
        
        if info is None:
            error = self.mt5.last_error()
            logger.error(
                f"MT5_CONNECT | reason=account_info_failed | "
                f"login={MT5_LOGIN} | server={MT5_SERVER} | error={error}"
            )
            # Le initialize() a réussi mais on ne peut pas lire le compte
            # Possible : login/password incorrect
            self.mt5.shutdown()
            return False
        
        self._connected = True
        
        logger.info(
            f"MT5_CONNECT | success | auto_open=True | "
            f"login={info.login} | balance={info.balance} | "
            f"currency={info.currency} | server={info.server} | "
            f"leverage={info.leverage} | margin_mode={info.margin_mode}"
        )
        
        # === 4. Activer les symboles dans Market Watch ===
        self._enable_symbols()
        
        return True
    
    def _find_mt5_path(self) -> str:
        """
        Trouve le chemin de MT5 automatiquement.
        
        Cherche dans :
        1. MT5_PATH du .env (si configuré)
        2. Chemins par défaut Windows
        
        RÈGLE 6 : Pas d'échec silencieux — logue le chemin trouvé.
        """
        # Si MT5_PATH est configuré dans .env → l'utiliser
        if MT5_PATH and os.path.exists(MT5_PATH):
            logger.info(f"MT5_PATH | source=env | path={MT5_PATH}")
            return MT5_PATH
        
        # Chercher dans les chemins par défaut Windows
        default_paths = [
            "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
            "C:\\Program Files (x86)\\MetaTrader 5\\terminal64.exe",
            os.path.expandvars("%APPDATA%\\MetaTrader 5\\terminal64.exe"),
            # Chemins pour différents brokers
            "C:\\Program Files\\ICMarkets - MetaTrader 5\\terminal64.exe",
            "C:\\Program Files\\Exness - MetaTrader 5\\terminal64.exe",
            "C:\\Program Files\\FBS - MetaTrader 5\\terminal64.exe",
            "C:\\Program Files\\XM Global - MetaTrader 5\\terminal64.exe",
            "C:\\Program Files\\Pepperstone - MetaTrader 5\\terminal64.exe",
            "C:\\Program Files\\RoboForex - MetaTrader 5\\terminal64.exe",
            "C:\\Program Files\\OctaFX - MetaTrader 5\\terminal64.exe",
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                logger.info(f"MT5_PATH | source=auto_found | path={path}")
                return path
        
        # Chercher dans APPDATA (MT5 installé par broker)
        appdata = os.path.expandvars("%APPDATA%")
        for folder in os.listdir(appdata):
            if "MetaTrader" in folder:
                candidate = os.path.join(appdata, folder, "terminal64.exe")
                if os.path.exists(candidate):
                    logger.info(f"MT5_PATH | source=appdata_scan | path={candidate}")
                    return candidate
        
        logger.warning(
            "MT5_PATH | source=not_found | MT5 non trouvé dans les chemins par défaut. "
            "Le package MetaTrader5 va chercher automatiquement. "
            "Si ça ne marche pas, configure MT5_PATH dans le fichier .env"
        )
        return ""  # STRUCTURAL: mt5.initialize() sans path cherche automatiquement
    
    def _enable_symbols(self) -> None:
        """
        Ajoute les symboles XAUUSD, NAS100, BTCUSD dans Market Watch de MT5.
        
        MT5 ne permet pas de récupérer les données d'un symbole
        si il n'est pas dans le Market Watch. Cette fonction
        l'ajoute automatiquement.
        
        RÈGLE 6 : Pas d'échec silencieux.
        """
        from config.trading_config import TRADING_SYMBOLS
        
        for symbol in TRADING_SYMBOLS:
            mt5_symbol = get_broker_format(symbol, "mt5")
            
            # Vérifier si le symbole est déjà visible
            info = self.mt5.symbol_info(mt5_symbol)
            
            if info is None:
                logger.warning(
                    f"MT5_SYMBOL | reason=not_available | symbol={mt5_symbol} | "
                    f"Ce symbole n'est pas disponible sur ce compte/broker. "
                    f"Vérifie que ton broker offre {mt5_symbol}"
                )
                continue
            
            if not info.visible:
                # Ajouter le symbole au Market Watch
                if self.mt5.symbol_select(mt5_symbol, True):
                    logger.info(f"MT5_SYMBOL | action=added_to_market_watch | symbol={mt5_symbol}")
                else:
                    logger.error(
                        f"MT5_SYMBOL | reason=cannot_add | symbol={mt5_symbol} | "
                        f"Impossible d'ajouter {mt5_symbol} au Market Watch"
                    )
            else:
                logger.info(f"MT5_SYMBOL | action=already_visible | symbol={mt5_symbol}")
    
    def disconnect(self) -> None:
        """Déconnexion MT5 — MT5 reste ouvert, on juste se déconnecte."""
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
        
        # RÈGLE 1 : Conversion via config/symbols.py
        mt5_symbol = get_broker_format(symbol, "mt5")
        
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
        mt5_symbol = get_broker_format(symbol, "mt5")
        tick = self.mt5.symbol_info_tick(mt5_symbol)
        
        if tick is None:
            logger.error(f"MT5_PRICE | reason=tick_failed | symbol={mt5_symbol}")
            return {"bid": 0, "ask": 0, "mid": 0}
        
        return {"bid": tick.bid, "ask": tick.ask, "mid": (tick.bid + tick.ask) / 2}
    
    def send_order(self, symbol: str, direction: str, lot: float,
                   entry_price: float, sl: float, tp: float) -> OrderResult:
        """Envoie un ordre MT5."""
        mt5_symbol = get_broker_format(symbol, "mt5")
        
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
        mt5_symbol = get_broker_format(symbol, "mt5") if symbol else ""
        
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
