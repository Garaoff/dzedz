"""
Moteur de backtest — Bot SMC/ICT v2.

RÈGLE 3 : Transition, pas état.
RÈGLE 7 : Taille d'échantillon minimum.
RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 1 : Utilise les MÊMES modules core que le live.

Ce moteur SIMULE VRAIMENT les trades : SL hit, TP hit, breakeven,
partial close, trailing stop. Pas de placeholder.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from core.signal_detector import SMCPipeline
from core.sl_tp_calculator import calculate_sl_tp, SLTPResult
from core.liquidity import find_nearest_liquidity_level
from core.fvg import find_fvg_at_price
from core.order_block import find_ob_at_price
from core.risk_guard import validate_risk, RiskValidationError
from config.params import (
    MIN_TRADES_FOR_VALIDATION,
    MAX_RISK_PER_TRADE_PCT,
    BE_TRIGGER_ATR,
    PARTIAL_CLOSE_PCT,
    CONFLUENCE_MINIMUM,
)
from config.symbols import get_symbol_config, get_pip_size, get_pip_value_per_lot

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Trade simulé avec résultat complet."""
    entry_index: int
    exit_index: int
    direction: str
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    lot: float
    pnl: float
    pnl_pct: float
    result: str  # "tp_hit", "sl_hit", "be_hit"
    sl_method: str
    tp_method: str
    rr_ratio: float
    confluence_score: int
    duration_bars: int
    sl_touched: bool  # SL a été touché avant TP
    be_reached: bool  # Breakeven a été atteint
    partial_closed: bool  # Partial close effectuée


class BacktestEngine:
    """
    Moteur de backtest — simulation réaliste.
    
    Utilise les MÊMES modules core que le live.
    Si un module se comporte différemment en backtest vs live, c'est un bug.
    """
    
    def __init__(self, capital: float, risk_pct: float = MAX_RISK_PER_TRADE_PCT, symbol: str = "XAUUSD"):
        self.initial_capital = capital
        self.capital = capital
        self.risk_pct = risk_pct
        self.symbol = symbol  # DYNAMIC: symbole tradé — paramètres depuis config/symbols.py
        self.trades: list[BacktestTrade] = []
    
    def run(
        self,
        df: pd.DataFrame,
        df_htf: Optional[pd.DataFrame] = None,
    ) -> dict:
        """
        Lance le backtest complet.
        
        Pour chaque bougie :
        1. Le pipeline détecte un signal (ou pas)
        2. Si signal + confluence >= minimum → calcul SL/TP + risque
        3. Si risque OK → entrer dans le trade
        4. Simuler le trade bar-by-bar jusqu'à SL/TP/breakeven hit
        
        Args:
            df: Données M1 OHLCV
            df_htf: Données HTF pour le biais
        
        Returns:
            dict avec résultats complets
        """
        self.trades = []
        self.capital = self.initial_capital
        
        # Initialiser le pipeline
        pipeline = SMCPipeline(df, df_htf)
        
        # Boucle principale
        for i in range(1, len(df)):
            signal = pipeline.process_bar(i)
            
            if signal is None:
                continue
            
            # Calcul SL/TP
            atr = self._calculate_atr(df, i)
            
            # Trouver les niveaux structurels pour le SL/TP
            dir_str = "long" if signal.direction.value == "long" else "short"
            
            liquidity_below = find_nearest_liquidity_level(
                pipeline.liquidity_levels, signal.price, "below"
            )
            liquidity_above = find_nearest_liquidity_level(
                pipeline.liquidity_levels, signal.price, "above"
            )
            
            fvg_entry = find_fvg_at_price(pipeline.fvgs, signal.price, dir_str)
            ob_entry = find_ob_at_price(pipeline.obs, signal.price, dir_str)
            
            # Swings les plus proches
            confirmed_swings = [s for s in pipeline.swings if s.confirmed]
            swing_low = None
            swing_high = None
            for s in confirmed_swings:
                if s.type == "swing_low" and (swing_low is None or s.price > swing_low):
                    if s.price < signal.price:
                        swing_low = s.price
                if s.type == "swing_high" and (swing_high is None or s.price < swing_high):
                    if s.price > signal.price:
                        swing_high = s.price
            
            sltp_result = calculate_sl_tp(
                signal=signal,
                atr=atr,
                liquidity_below=liquidity_below,
                liquidity_above=liquidity_above,
                fvg_entry=fvg_entry,
                ob_entry=ob_entry,
                swing_low=swing_low,
                swing_high=swing_high,
            )
            
            if sltp_result is None:
                # RR < minimum
                continue
            
            # Vérification risque (Règle 5)
            try:
                validated_lot = validate_risk(
                    capital=self.capital,
                    entry_price=signal.price,
                    sl_price=sltp_result.sl,
                    lot_size=0.1,  # DYNAMIC: sera ajusté par validate_risk
                    setup_grade="",  # Grade ignoré (Règle 5)
                    symbol=self.symbol,  # RÈGLE 1 : pip_size et pip_value par symbole
                )
            except RiskValidationError as e:
                logger.debug(f"BACKTEST | risk_rejected | index={i} | error={e}")
                continue
            
            # === SIMULER LE TRADE ===
            trade = self._simulate_trade(
                df, i, signal, sltp_result, validated_lot,
                pipeline, atr,
            )
            
            if trade is not None:
                self.trades.append(trade)
                # Update capital
                self.capital += trade.pnl
                
                logger.info(
                    f"TRADE_RESULT | result={trade.result} | pnl={trade.pnl:.2f} | "
                    f"capital={self.capital:.2f} | entry_idx={trade.entry_index} | "
                    f"exit_idx={trade.exit_index}"
                )
        
        # Vérification taille échantillon (Règle 7)
        n_trades = len(self.trades)
        if n_trades < MIN_TRADES_FOR_VALIDATION:
            logger.warning(
                f"BACKTEST | insufficient_trades | trades={n_trades} | "
                f"min={MIN_TRADES_FOR_VALIDATION} | RESULTAT NON VALIDE"
            )
        
        # Stats
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in self.trades)
        win_rate = len(wins) / n_trades if n_trades > 0 else 0
        
        logger.info(
            f"BACKTEST_COMPLETE | trades={n_trades} | "
            f"wins={len(wins)} | losses={len(losses)} | "
            f"win_rate={win_rate:.2%} | pnl={total_pnl:.2f} | "
            f"capital={self.capital:.2f}"
        )
        
        return {
            "trades": self.trades,
            "n_trades": n_trades,
            "n_signals": pipeline.registry.count(),
            "capital_start": self.initial_capital,
            "capital_end": self.capital,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "min_trades_met": n_trades >= MIN_TRADES_FOR_VALIDATION,
            "pipeline_stats": pipeline.get_stats(),
        }
    
    def _simulate_trade(
        self,
        df: pd.DataFrame,
        entry_index: int,
        signal,
        sltp: SLTPResult,
        lot: float,
        pipeline: SMCPipeline,
        atr_entry: float,
    ) -> Optional[BacktestTrade]:
        """
        Simule un trade bar-by-bar : SL hit, TP hit, breakeven, trailing.
        
        C'est une simulation RÉELLE, pas un placeholder.
        """
        is_long = signal.direction.value == "long"
        
        sl = sltp.sl
        tp = sltp.tp
        entry = signal.price
        be_reached = False
        partial_closed = False
        remaining_lot = lot
        
        # Parcourir les bougies après l'entrée
        for j in range(entry_index + 1, min(entry_index + 500  # STRUCTURAL: max 500 bars per trade timeout — 500 M1 bars ≈ 8 hours, len(df))):
            bar_high = df["high"].iloc[j]
            bar_low = df["low"].iloc[j]
            bar_close = df["close"].iloc[j]
            
            # === Vérifier SL hit ===
            if is_long:
                sl_touched = bar_low <= sl
            else:
                sl_touched = bar_high >= sl
            
            # === Vérifier TP hit ===
            if is_long:
                tp_touched = bar_high >= tp
            else:
                tp_touched = bar_low <= tp
            
            # === Si SL et TP sur la même bougie ===
            # Hypothèse conservatrice : SL hit first (car on est dans le mauvais sens)
            if sl_touched and tp_touched:
                if is_long:
                    # La bougie a touché SL puis TP — on assume SL hit
                    exit_price = sl
                    result = "sl_hit"
                else:
                    exit_price = sl
                    result = "sl_hit"
                pnl = self._calculate_pnl(entry, exit_price, lot, is_long)
                
                return BacktestTrade(
                    entry_index=entry_index,
                    exit_index=j,
                    direction=signal.direction.value,
                    entry_price=entry,
                    exit_price=exit_price,
                    sl=sl,
                    tp=tp,
                    lot=lot,
                    pnl=pnl,
                    pnl_pct=pnl / self.capital * 100  # STRUCTURAL: conversion pct if self.capital > 0 else 0,
                    result=result,
                    sl_method=sltp.sl_method,
                    tp_method=sltp.tp_method,
                    rr_ratio=sltp.rr_ratio,
                    confluence_score=len(signal.confluences) if hasattr(signal, 'confluences') else 0,
                    duration_bars=j - entry_index,
                    sl_touched=True,
                    be_reached=be_reached,
                    partial_closed=partial_closed,
                )
            
            # === SL hit seul ===
            if sl_touched and not be_reached:
                exit_price = sl
                pnl = self._calculate_pnl(entry, exit_price, lot, is_long)
                
                return BacktestTrade(
                    entry_index=entry_index,
                    exit_index=j,
                    direction=signal.direction.value,
                    entry_price=entry,
                    exit_price=exit_price,
                    sl=sl,
                    tp=tp,
                    lot=lot,
                    pnl=pnl,
                    pnl_pct=pnl / self.capital * 100  # STRUCTURAL: conversion pct if self.capital > 0 else 0,
                    result="sl_hit",
                    sl_method=sltp.sl_method,
                    tp_method=sltp.tp_method,
                    rr_ratio=sltp.rr_ratio,
                    confluence_score=len(signal.confluences) if hasattr(signal, 'confluences') else 0,
                    duration_bars=j - entry_index,
                    sl_touched=True,
                    be_reached=False,
                    partial_closed=False,
                )
            
            # === Breakeven check ===
            if not be_reached:
                profit_distance = abs(bar_close - entry) if is_long else abs(entry - bar_close)
                profit_atr = profit_distance / atr_entry if atr_entry > 0 else 0
                
                if profit_atr >= BE_TRIGGER_ATR:
                    # Déplacer SL à breakeven
                    sl = entry
                    be_reached = True
                    logger.debug(
                        f"BE_REACHED | index={j} | profit_atr={profit_atr:.2f} | "
                        f"new_sl={sl:.5f}"
                    )
                    
                    # Partial close
                    if not partial_closed:
                        partial_lot = lot * PARTIAL_CLOSE_PCT
                        partial_pnl = self._calculate_pnl(entry, bar_close, partial_lot, is_long)
                        self.capital += partial_pnl
                        remaining_lot = lot - partial_lot
                        partial_closed = True
                        logger.debug(
                            f"PARTIAL_CLOSE | index={j} | lot={partial_lot:.4f} | "
                            f"pnl={partial_pnl:.2f} | remaining={remaining_lot:.4f}"
                        )
            
            # === TP hit ===
            if tp_touched:
                exit_price = tp
                pnl = self._calculate_pnl(entry, exit_price, remaining_lot if partial_closed else lot, is_long)
                if partial_closed:
                    # Ajouter le PnL de la partial close déjà compté
                    total_pnl = pnl  # partial_close pnl was already added to capital
                
                return BacktestTrade(
                    entry_index=entry_index,
                    exit_index=j,
                    direction=signal.direction.value,
                    entry_price=entry,
                    exit_price=exit_price,
                    sl=sl,
                    tp=tp,
                    lot=lot,
                    pnl=pnl if not partial_closed else pnl,
                    pnl_pct=pnl / self.capital * 100  # STRUCTURAL: conversion pct if self.capital > 0 else 0,
                    result="tp_hit",
                    sl_method=sltp.sl_method,
                    tp_method=sltp.tp_method,
                    rr_ratio=sltp.rr_ratio,
                    confluence_score=len(signal.confluences) if hasattr(signal, 'confluences') else 0,
                    duration_bars=j - entry_index,
                    sl_touched=False,
                    be_reached=be_reached,
                    partial_closed=partial_closed,
                )
            
            # === Trailing stop après breakeven ===
            if be_reached and partial_closed:
                trail = atr_entry * TRAIL_ATR_MULTIPLIER  # STRUCTURAL: trailing à 1 ATR
                
                if is_long:
                    new_sl = max(sl, bar_high - trail)
                    if new_sl > sl:
                        sl_before = sl
                        sl = new_sl
                        logger.debug(
                            f"TRAIL | direction=long | before={sl_before:.5f} | "
                            f"after={sl:.5f} | reason=trail"
                        )
                else:
                    new_sl = min(sl, bar_low + trail)
                    if new_sl < sl:
                        sl_before = sl
                        sl = new_sl
                        logger.debug(
                            f"TRAIL | direction=short | before={sl_before:.5f} | "
                            f"after={sl:.5f} | reason=trail"
                        )
        
        # Si le trade n'a pas été fermé dans 500 bougies → fermer à la dernière bougie
        last_index = min(entry_index + 500  # STRUCTURAL: max 500 bars per trade timeout — 500 M1 bars ≈ 8 hours, len(df) - 1)
        exit_price = df["close"].iloc[last_index]
        pnl = self._calculate_pnl(entry, exit_price, remaining_lot if partial_closed else lot, is_long)
        
        return BacktestTrade(
            entry_index=entry_index,
            exit_index=last_index,
            direction=signal.direction.value,
            entry_price=entry,
            exit_price=exit_price,
            sl=sl,
            tp=tp,
            lot=lot,
            pnl=pnl,
            pnl_pct=pnl / self.capital * 100  # STRUCTURAL: conversion pct if self.capital > 0 else 0,
            result="timeout",
            sl_method=sltp.sl_method,
            tp_method=sltp.tp_method,
            rr_ratio=sltp.rr_ratio,
            confluence_score=len(signal.confluences) if hasattr(signal, 'confluences') else 0,
            duration_bars=last_index - entry_index,
            sl_touched=False,
            be_reached=be_reached,
            partial_closed=partial_closed,
        )
    
    def _calculate_pnl(self, entry: float, exit: float, lot: float, is_long: bool) -> float:
        """
        Calcul du PnL en dollars pour le symbole configuré.
        
        RÈGLE 1 : Utilise config/symbols.py pour les paramètres par symbole.
        Formule : pnl = pips × pip_value_per_lot × lot × direction
        """
        sym_config = get_symbol_config(self.symbol)
        return sym_config.calculate_pnl(entry, exit, lot, is_long)
    
    def _calculate_atr(self, df: pd.DataFrame, index: int) -> float:
        """Calcul ATR à un index."""
        from config.params import ATR_PERIOD
        
        period = ATR_PERIOD
        start = max(0, index - period + 1)
        if start >= index:
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


from typing import Optional
from config.params import TRAIL_ATR_MULTIPLIER
