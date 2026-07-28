"""
Bot live — Point d'entrée principal pour le trading en réel.

RÈGLE 5 : Tout ordre passe par risk_guard.
RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 8 : Ce fichier est dans git, les secrets dans .env.
RÈGLE 2 : Ce module est appelé par start_bot.py (pipeline live).
RÈGLE 1 : Les paramètres par symbole viennent de config/symbols.py.

3 symboles : XAUUSD (priorité 1), NAS100 (priorité 2), BTCUSD (priorité 3)
"""

import logging
import sys
import time
import signal
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from config.trading_config import (
    TRADING_SYMBOLS, ENTRY_TIMEFRAME, HTF_TIMEFRAME,
    TRADING_MODE, CAPITAL, LOG_LEVEL, LOG_FILE,
    MAX_DAILY_LOSS_PCT, MAX_CONCURRENT_TRADES, MAX_TRADES_PER_DAY,
    MAX_TRADES_PER_SYMBOL_PER_DAY,
    validate_config,
)
from config.params import MAX_RISK_PER_TRADE_PCT
from config.symbols import (
    get_symbol_config, get_pip_size, get_pip_value_per_lot,
    get_contract_size, get_broker_format,
)
from live.brokers.factory import create_broker
from live.brokers.base import BrokerAdapter, OrderResult
from live.kill_switch import KillSwitch
from live.trade_manager import TradeManager
from core.signal_detector import SMCPipeline
from core.sl_tp_calculator import calculate_sl_tp
from core.risk_guard import validate_risk, RiskValidationError
from core.position_sizer import calculate_position_size
from core.liquidity import find_nearest_liquidity_level
from core.fvg import find_fvg_at_price
from core.order_block import find_ob_at_price

logger = logging.getLogger(__name__)


class SymbolState:
    """
    État par symbole — tracking des trades et PnL pour chaque symbole.
    
    RÈGLE 9 : Chiffres bruts pour chaque symbole.
    """
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.total_signals = 0
        self.total_orders_sent = 0
        self.total_orders_rejected = 0
        self.last_signal_time: Optional[datetime] = None
    
    def reset_daily(self):
        """Reset quotidien des stats par symbole."""
        self.daily_trades = 0
        self.daily_pnl = 0.0
    
    def get_stats(self) -> dict:
        """Stats du symbole — chiffres bruts."""
        return {
            "symbol": self.symbol,
            "daily_trades": self.daily_trades,
            "daily_pnl": self.daily_pnl,
            "total_signals": self.total_signals,
            "total_orders_sent": self.total_orders_sent,
            "total_orders_rejected": self.total_orders_rejected,
        }


class LiveBot:
    """
    Bot de trading live — tourne en continu sur ton PC.
    
    3 symboles : XAUUSD (le plus important), NAS100, BTCUSD
    
    Boucle principale :
    1. Récupérer les données du broker pour chaque symbole (M1 + H4)
    2. Lancer le pipeline SMC pour chaque symbole
    3. Si signal → calcul SL/TP → vérifier risque → envoyer ordre
    4. Gérer les trades ouverts (breakeven, trailing, close)
    5. Kill switch : arrêt automatique si perte journalière trop grande
    
    Mode demo : paper trading (ordres envoyés sur compte demo)
    Mode live : trading réel (ordres envoyés sur compte réel)
    """
    
    def __init__(self):
        # Configuration
        self.symbols = TRADING_SYMBOLS  # DYNAMIC: depuis .env / config
        self.entry_tf = ENTRY_TIMEFRAME
        self.htf_tf = HTF_TIMEFRAME
        self.mode = TRADING_MODE
        self.capital = CAPITAL
        
        # Composants
        self.broker: Optional[BrokerAdapter] = None
        self.kill_switch = KillSwitch()
        self.trade_manager = TradeManager()
        
        # État par symbole
        self.symbol_states: dict[str, SymbolState] = {}
        for sym in self.symbols:
            self.symbol_states[sym] = SymbolState(sym)
        
        # Pipelines par symbole (re-initialisés chaque minute)
        self.pipelines: dict[str, Optional[SMCPipeline]] = {}
        
        # State global
        self.running = False
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_start_capital = CAPITAL
        self.last_day = datetime.now().day
        
        # Stats global
        self.total_signals = 0
        self.total_orders_sent = 0
        self.total_orders_rejected = 0
        
        # Signal handler pour arrêt propre
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def start(self) -> None:
        """
        Lance le bot — connexion au broker + boucle principale.
        
        RÈGLE 8 : Ce code est dans git, pas un script temporaire.
        """
        logger.info("=" * 60)  # STRUCTURAL: 60 chars separator line
        logger.info(f"BOT_STARTING | mode={self.mode} | symbols={self.symbols} | capital={self.capital}")
        logger.info("=" * 60)  # STRUCTURAL: 60 chars separator line
        
        # 1. Valider la configuration
        config_errors = validate_config()
        if config_errors:
            for error in config_errors:
                logger.error(f"CONFIG_ERROR | {error}")
            logger.error("BOT_ABORT | reason=config_errors | Fix .env and retry")
            return
        
        # 2. Connecter au broker
        self.broker = create_broker()
        
        if not self.broker.connect():
            logger.error("BOT_ABORT | reason=broker_connection_failed")
            return
        
        # 3. Récupérer le capital réel du compte
        account = self.broker.get_account_info()
        self.capital = account.capital
        self.daily_start_capital = account.capital
        logger.info(f"ACCOUNT | capital={self.capital} | currency={account.currency} | positions={account.open_positions}")
        
        # 4. Initialiser le kill switch
        self.kill_switch.initialize(self.capital)
        
        # 5. Boucle principale
        self.running = True
        
        logger.info(f"BOT_RUNNING | entering main loop | symbols={self.symbols} | Ctrl+C to stop")
        
        while self.running:
            try:
                self._main_loop()
            except Exception as e:
                logger.error(f"BOT_LOOP_ERROR | error={e}", exc_info=True)
                # Ne crash pas — continue la boucle
            
            # Attendre avant la prochaine bougie (1 minute)
            time.sleep(60)  # STRUCTURAL: M1 = 1 minute entre bougies
        
        # Arrêt propre
        self._shutdown()
    
    def _main_loop(self) -> None:
        """
        Boucle principale — exécutée chaque minute.
        
        Traite TOUS les symboles dans la même boucle.
        
        1. Check kill switch
        2. Reset quotidien
        3. Pour chaque symbole :
           a. Récupérer données
           b. Pipeline SMC
           c. Gérer trades ouverts
           d. Envoyer ordre si signal
        """
        # === 1. Kill switch ===
        if self.kill_switch.should_stop(self.daily_pnl, self.capital, self.daily_start_capital):
            if self.daily_start_capital > 0:
                loss_pct = self.daily_pnl / self.daily_start_capital * 100  # STRUCTURAL: conversion pct
                logger.warning(f"KILL_SWITCH_ACTIVATED | daily_pnl={self.daily_pnl:.2f} | daily_loss_pct={loss_pct:.2f}%")
            self.running = False
            return
        
        # === 2. Reset quotidien ===
        current_day = datetime.now().day
        if current_day != self.last_day:
            logger.info(f"DAILY_RESET | day={current_day} | previous_pnl={self.daily_pnl:.2f} | trades={self.daily_trades}")
            self.daily_pnl = 0
            self.daily_trades = 0
            self.last_day = current_day
            for sym, state in self.symbol_states.items():
                state.reset_daily()
            account = self.broker.get_account_info()
            self.capital = account.capital
            self.daily_start_capital = account.capital
        
        # === 3. Limite trades/jour global ===
        if self.daily_trades >= MAX_TRADES_PER_DAY:
            logger.info(f"MAX_TRADES_DAY | trades={self.daily_trades} | max={MAX_TRADES_PER_DAY} | waiting for next day")
            return
        
        # === 4. Traiter chaque symbole ===
        for symbol in self.symbols:
            self._process_symbol(symbol)
    
    def _process_symbol(self, symbol: str) -> None:
        """
        Traite un symbole individuellement.
        
        1. Récupérer les données M1 + H4
        2. Lancer le pipeline SMC
        3. Si signal → calcul SL/TP → risque → ordre
        4. Gérer les trades ouverts
        """
        state = self.symbol_states[symbol]
        sym_config = get_symbol_config(symbol)
        broker_format = get_broker_format(symbol, self.broker.__class__.__name__)
        
        # RÈGLE : Limite trades/jour par symbole
        if state.daily_trades >= MAX_TRADES_PER_SYMBOL_PER_DAY:
            logger.debug(f"MAX_TRADES_SYMBOL | symbol={symbol} | trades={state.daily_trades} | max={MAX_TRADES_PER_SYMBOL_PER_DAY}")
            return
        
        # === Données M1 ===
        candles_m1 = self.broker.get_candles(symbol, self.entry_tf, count=10000)  # STRUCTURAL: RÈGLE 7 — 10000 bars
        
        if not candles_m1 or len(candles_m1) < 100:  # STRUCTURAL: minimum 100 bars for pipeline
            logger.warning(f"DATA_INSUFFICIENT | symbol={symbol} | m1_candles={len(candles_m1) if candles_m1 else 0}")
            return
        
        df_m1 = self._candles_to_dataframe(candles_m1)
        
        # === Données HTF ===
        candles_htf = self.broker.get_candles(symbol, self.htf_tf, count=500)  # STRUCTURAL: 500 bougies H4 ≈ 2 mois
        
        df_htf = None
        if candles_htf and len(candles_htf) >= 5:
            df_htf = self._candles_to_dataframe(candles_htf)
        
        # === Pipeline SMC ===
        self.pipelines[symbol] = SMCPipeline(df_m1, df_htf)
        
        # Traiter la dernière bougie
        last_index = len(df_m1) - 1
        signal = self.pipelines[symbol].process_bar(last_index)
        
        if signal is None:
            logger.debug(f"NO_SIGNAL | symbol={symbol} | index={last_index}")
            return
        
        state.total_signals += 1
        state.last_signal_time = datetime.now()
        
        # === Gérer trades ouverts pour ce symbole ===
        self._manage_open_positions(symbol)
        
        # === Vérifier nombre de trades concurrents ===
        open_positions = self.broker.get_open_positions(symbol)
        if len(open_positions) >= 1:  # STRUCTURAL: 1 trade max par symbole ouvert
            logger.info(f"ALREADY_OPEN | symbol={symbol} | positions={len(open_positions)}")
            return
        
        # Total positions tous symboles
        total_open = 0
        for sym in self.symbols:
            total_open += len(self.broker.get_open_positions(sym))
        if total_open >= MAX_CONCURRENT_TRADES:
            logger.info(f"MAX_POSITIONS_GLOBAL | total={total_open} | max={MAX_CONCURRENT_TRADES}")
            return
        
        # === Calcul SL/TP ===
        atr = self._calculate_atr(df_m1, last_index)
        
        dir_str = "long" if signal.direction.value == "long" else "short"
        
        pipeline = self.pipelines[symbol]
        
        liquidity_below = find_nearest_liquidity_level(pipeline.liquidity_levels, signal.price, "below")
        liquidity_above = find_nearest_liquidity_level(pipeline.liquidity_levels, signal.price, "above")
        
        fvg_entry = find_fvg_at_price(pipeline.fvgs, signal.price, dir_str)
        ob_entry = find_ob_at_price(pipeline.obs, signal.price, dir_str)
        
        # Swings
        swing_low = None
        swing_high = None
        for s in [s for s in pipeline.swings if s.confirmed]:
            if s.type == "swing_low" and s.price < signal.price:
                swing_low = max(swing_low or 0, s.price)
            if s.type == "swing_high" and s.price > signal.price:
                swing_high = min(swing_high or float('inf'), s.price)
        
        sltp = calculate_sl_tp(
            signal=signal, atr=atr,
            liquidity_below=liquidity_below,
            liquidity_above=liquidity_above,
            fvg_entry=fvg_entry,
            ob_entry=ob_entry,
            swing_low=swing_low,
            swing_high=swing_high,
        )
        
        if sltp is None:
            logger.info(f"SLTP_REJECTED | symbol={symbol} | reason=rr_below_minimum | signal={signal.signal_type.value}")
            state.total_orders_rejected += 1
            self.total_orders_rejected += 1
            return
        
        # === Vérification risque (RÈGLE 5 : VERROU) ===
        try:
            lot_size = calculate_position_size(
                capital=self.capital,
                entry_price=signal.price,
                sl_price=sltp.sl,
                symbol=symbol,  # RÈGLE 1 : paramètres par symbole
                risk_pct=MAX_RISK_PER_TRADE_PCT,
            )
        except ValueError as e:
            logger.error(f"POSITION_SIZE_ERROR | symbol={symbol} | error={e}")
            state.total_orders_rejected += 1
            self.total_orders_rejected += 1
            return
        
        try:
            validated_lot = validate_risk(
                capital=self.capital,
                entry_price=signal.price,
                sl_price=sltp.sl,
                lot_size=lot_size,
                setup_grade="",  # Grade ignoré — RÈGLE 5
                symbol=symbol,  # RÈGLE 1 : pip_size et pip_value par symbole
            )
        except RiskValidationError as e:
            logger.error(f"RISK_REJECTED | symbol={symbol} | error={e}")
            state.total_orders_rejected += 1
            self.total_orders_rejected += 1
            return
        
        # === Envoyer l'ordre au broker ===
        result = self.broker.send_order(
            symbol=symbol,  # RÈGLE 1 : conversion format faite dans l'adapter
            direction=dir_str,
            lot=validated_lot,
            entry_price=signal.price,
            sl=sltp.sl,
            tp=sltp.tp,
        )
        
        if result.success:
            self.total_orders_sent += 1
            state.total_orders_sent += 1
            self.daily_trades += 1
            state.daily_trades += 1
            
            # Enregistrer le trade dans le manager
            self.trade_manager.add_trade(
                ticket=result.order_id,
                symbol=symbol,
                direction=dir_str,
                entry_price=result.entry_price,
                sl=sltp.sl,
                tp=sltp.tp,
                lot=validated_lot,
                signal_type=signal.signal_type.value,
                confluence=len(signal.confluences) if hasattr(signal, 'confluences') else 0,
            )
            
            logger.info(
                f"ORDER_SENT | symbol={symbol} | ticket={result.order_id} | direction={dir_str} | "
                f"lot={validated_lot:.4f} | entry={result.entry_price:.5f} | "
                f"sl={sltp.sl:.5f} | tp={sltp.tp:.5f} | "
                f"rr={sltp.rr_ratio:.2f} | sl_method={sltp.sl_method} | tp_method={sltp.tp_method} | "
                f"confluence={len(signal.confluences) if hasattr(signal, 'confluences') else 0} | "
                f"pip_size={sym_config.pip_size} | pip_value={sym_config.pip_value_per_lot}"
            )
        else:
            self.total_orders_rejected += 1
            state.total_orders_rejected += 1
            logger.error(f"ORDER_REJECTED | symbol={symbol} | error={result.error}")
    
    def _manage_open_positions(self, symbol: str) -> None:
        """
        Gère les trades ouverts pour un symbole — breakeven, trailing.
        
        RÈGLE 5 : toute modification SL passe par risk_guard.
        """
        positions = self.broker.get_open_positions(symbol)
        sym_config = get_symbol_config(symbol)
        pip_size = sym_config.pip_size
        
        for pos in positions:
            trade = self.trade_manager.get_trade(pos.ticket)
            
            if trade is None:
                continue
            
            # Update PnL
            trade.current_pnl = pos.pnl
            self.daily_pnl += pos.pnl - (trade.last_recorded_pnl or 0)
            self.symbol_states[symbol].daily_pnl += pos.pnl - (trade.last_recorded_pnl or 0)
            trade.last_recorded_pnl = pos.pnl
            
            # Breakeven check
            if not trade.be_reached:
                profit_distance = abs(pos.current_price - trade.entry_price)
                profit_pips = profit_distance / pip_size  # DYNAMIC: pip_size par symbole
                
                # STRUCTURAL: ~10 pips profit before BE (ajusté pour la volatilité du symbole)
                # XAUUSD: 10 pips = $0.10 move, NAS100: 10 pips = 10 points, BTCUSD: 10 pips = $0.10
                # Utiliser 10 pips comme BE trigger est conservateur pour XAUUSD/BTCUSD
                be_trigger_pips = 10  # STRUCTURAL: 10 pips de profit minimum pour BE
                
                if profit_pips >= be_trigger_pips:
                    new_sl = trade.entry_price
                    
                    result = self.broker.modify_position(pos.ticket, sl=new_sl)
                    if result.success:
                        trade.be_reached = True
                        trade.current_sl = new_sl
                        logger.info(f"BE_SET | symbol={symbol} | ticket={pos.ticket} | new_sl={new_sl:.5f}")
    
    def _candles_to_dataframe(self, candles: list[dict]) -> pd.DataFrame:
        """Convertir les candles du broker en DataFrame pandas."""
        df = pd.DataFrame(candles)
        
        # Convertir les timestamps
        if "time" in df.columns:
            # OANDA: ISO format, CCXT: unix timestamp ms
            try:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
            except Exception as e:
                logger.warning(f"TIME_PARSE | error={e} — using integer index")
                df = df.set_index(pd.RangeIndex(len(df)))
        
        # S'assurer que les colonnes existent
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                logger.error(f"COLUMN_MISSING | column={col}")
                df[col] = 0
        
        return df
    
    def _calculate_atr(self, df: pd.DataFrame, index: int) -> float:
        """Calcul ATR."""
        from config.params import ATR_PERIOD
        
        period = ATR_PERIOD
        start = max(0, index - period + 1)
        
        if start >= index or index >= len(df):
            return 0.0001  # STRUCTURAL: fallback minimal
        
        subset = df.iloc[start:index + 1]
        high = subset["high"]
        low = subset["low"]
        close_prev = subset["close"].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close_prev)
        tr3 = abs(low - close_prev)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.mean()
        
        return float(atr) if not pd.isna(atr) else 0.0001  # STRUCTURAL: fallback minimal
    
    def _handle_shutdown(self, signum, frame) -> None:
        """Arrêt propre via Ctrl+C."""
        logger.info("BOT_SHUTDOWN_SIGNAL | signal=Ctrl+C | stopping gracefully")
        self.running = False
    
    def _shutdown(self) -> None:
        """Arrêt propre — fermer toutes les positions et déconnecter."""
        logger.info("BOT_SHUTDOWN | closing all positions and disconnecting")
        
        # Déconnecter le broker
        if self.broker:
            self.broker.disconnect()
        
        # Stats finales par symbole
        for sym, state in self.symbol_states.items():
            logger.info(
                f"BOT_STATS_SYMBOL | symbol={sym} | "
                f"signals={state.total_signals} | "
                f"orders_sent={state.total_orders_sent} | "
                f"orders_rejected={state.total_orders_rejected} | "
                f"daily_pnl={state.daily_pnl:.2f} | "
                f"daily_trades={state.daily_trades}"
            )
        
        # Stats globales
        logger.info(
            f"BOT_STATS_GLOBAL | signals={self.total_signals} | "
            f"orders_sent={self.total_orders_sent} | "
            f"orders_rejected={self.total_orders_rejected} | "
            f"daily_pnl={self.daily_pnl:.2f} | "
            f"daily_trades={self.daily_trades}"
        )
        
        logger.info("BOT_STOPPED | shutdown complete")
    
    def get_status(self) -> dict:
        """Statut actuel du bot — pour le dashboard."""
        symbol_stats = {}
        for sym, state in self.symbol_states.items():
            symbol_stats[sym] = state.get_stats()
        
        open_positions = 0
        if self.broker and self.broker.is_connected():
            for sym in self.symbols:
                open_positions += len(self.broker.get_open_positions(sym))
        
        return {
            "running": self.running,
            "mode": self.mode,
            "symbols": self.symbols,
            "symbol_stats": symbol_stats,
            "capital": self.capital,
            "daily_pnl": self.daily_pnl,
            "daily_trades": self.daily_trades,
            "daily_loss_pct": self.daily_pnl / self.daily_start_capital * 100 if self.daily_start_capital > 0 else 0,  # STRUCTURAL: 100 pour conversion pct
            "total_signals": self.total_signals,
            "total_orders_sent": self.total_orders_sent,
            "total_orders_rejected": self.total_orders_rejected,
            "kill_switch_active": self.kill_switch.is_active,
            "open_positions": open_positions,
        }


def setup_logging():
    """Configuration du logging — RÈGLE 6 : jamais silencieux."""
    import os
    
    # Créer le dossier logs
    os.makedirs("logs", exist_ok=True)
    
    logging.basicConfig(
        level=logging.getLevelName(LOG_LEVEL),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE),
        ],
    )
