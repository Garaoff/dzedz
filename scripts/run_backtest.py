#!/usr/bin/env python3
"""
Script de backtest — Teste le bot sur des données historiques.

Usage:
    python scripts/run_backtest.py                    # Backtest avec données OANDA
    python scripts/run_backtest.py --csv data.csv     # Backtest avec fichier CSV local
    python scripts/run_backtest.py --walk-forward     # Walk-forward test
    
RÈGLE 7 : Échantillon minimum, IS/OOS, chiffres bruts.
"""

import argparse
import logging
import sys
import os

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

import pandas as pd


def load_data_from_csv(filepath: str) -> pd.DataFrame:
    """Charge les données depuis un fichier CSV."""
    logger = logging.getLogger("backtest_loader")
    
    df = pd.read_csv(filepath, parse_dates=True)
    
    # Essayer de trouver la colonne temps
    time_cols = ["time", "timestamp", "date", "datetime", "Time", "Date"]
    for col in time_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
            df = df.set_index(col)
            break
    
    if df.index.name is None:
        # Pas de colonne temps trouvée — utiliser un index numérique
        df = df.set_index(pd.RangeIndex(len(df)))
    
    logger.info(f"CSV_LOADED | filepath={filepath} | bars={len(df)} | columns={list(df.columns)}")
    
    return df


def load_data_from_broker(pair: str, timeframe: str) -> pd.DataFrame:
    """Charge les données depuis le broker (OANDA)."""
    from live.brokers.factory import create_broker
    
    broker = create_broker()
    
    if not broker.connect():
        logging.error("BROKER_CONNECT_FAILED — cannot load data")
        return pd.DataFrame()
    
    candles = broker.get_candles(pair, timeframe, count=10000)  # RÈGLE 7
    
    if not candles:
        logging.error("NO_CANDLES — cannot run backtest")
        return pd.DataFrame()
    
    df = pd.DataFrame(candles)
    
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
    
    broker.disconnect()
    
    return df


def run_simple_backtest(df: pd.DataFrame, capital: float) -> dict:
    """Lance un backtest simple."""
    from backtest.engine import BacktestEngine
    from backtest.metrics import compute_metrics
    
    engine = BacktestEngine(capital=capital)
    result = engine.run(df)
    
    metrics = compute_metrics(result["trades"])
    
    # Print résultats — chiffres bruts (Règle 9)
    print("\n" + "=" * 60)
    print("  RÉSULTATS BACKTEST — Chiffres bruts")
    print("=" * 60)
    print(f"  Trades:           {metrics.get('n_trades', 0)}")
    print(f"  Win rate:          {metrics.get('win_rate', 0):.2%}")
    print(f"  Total PnL:         ${metrics.get('total_pnl', 0):.2f}")
    print(f"  Avg win:           ${metrics.get('avg_win', 0):.2f}")
    print(f"  Avg loss:          ${metrics.get('avg_loss', 0):.2f}")
    print(f"  Max drawdown:      ${metrics.get('max_drawdown', 0):.2f}")
    print(f"  Max DD %:          {metrics.get('max_drawdown_pct', 0):.2%}")
    print(f"  Sharpe ratio:      {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  Profit factor:     {metrics.get('profit_factor', 0):.2f}")
    print(f"  Avg RR:            {metrics.get('avg_rr', 0):.2f}")
    print(f"  Avg duration:      {metrics.get('avg_duration_bars', 0):.0f} bars")
    print(f"  TP hits:           {metrics.get('tp_hits', 0)}")
    print(f"  SL hits:           {metrics.get('sl_hits', 0)}")
    print(f"  Breakeven reached: {metrics.get('be_reached_rate', 0):.2%}")
    print(f"  Partial close rate: {metrics.get('partial_close_rate', 0):.2%}")
    
    if "sample_warning" in metrics:
        print(f"\n  ⚠️  {metrics['sample_warning']}")
    
    if metrics.get('sl_methods'):
        print("\n  SL Methods breakdown:")
        for method, data in metrics['sl_methods'].items():
            print(f"    {method}: {data['count']} trades, PnL=${data['pnl']:.2f}")
    
    if metrics.get('tp_methods'):
        print("\n  TP Methods breakdown:")
        for method, data in metrics['tp_methods'].items():
            print(f"    {method}: {data['count']} trades, PnL=${data['pnl']:.2f}")
    
    print("=" * 60)
    
    return {"result": result, "metrics": metrics}


def run_walk_forward_test(df: pd.DataFrame, capital: float) -> dict:
    """Lance un walk-forward test."""
    from backtest.walk_forward import run_walk_forward
    
    wf_result = run_walk_forward(df, capital=capital)
    
    print("\n" + "=" * 60)
    print("  WALK-FORWARD TEST — Chiffres bruts par fenêtre")
    print("=" * 60)
    
    for window in wf_result["windows"]:
        print(f"\n  Fenêtre {window['window']}:")
        print(f"    IS trades:    {window['is_trades']}")
        print(f"    OOS trades:   {window['oos_trades']}")
        print(f"    IS win rate:  {window['is_win_rate']:.2%}")
        print(f"    OOS win rate: {window['oos_win_rate']:.2%}")
        print(f"    IS PnL:       ${window['is_pnl']:.2f}")
        print(f"    OOS PnL:      ${window['oos_pnl']:.2f}")
        print(f"    IS PF:        {window['is_profit_factor']:.2f}")
        print(f"    OOS PF:       {window['oos_profit_factor']:.2f}")
        print(f"    Dégradation WR: {window['degradation_wr']:.1%}")
        print(f"    Dégradation PF: {window['degradation_pf']:.1%}")
        print(f"    Dégradation max: {window['degradation_max']:.1%}")
        print(f"    Rejected:     {window['rejected']}")
    
    print(f"\n  Total IS trades:  {wf_result['total_is_trades']}")
    print(f"  Total OOS trades: {wf_result['total_oos_trades']}")
    print(f"  Avg dégradation:  {wf_result['avg_degradation']:.1%}")
    print(f"  Fenêtres rejected: {wf_result['n_rejected_windows']}/{len(wf_result['windows'])}")
    print(f"  All passed:       {wf_result['all_windows_passed']}")
    print("=" * 60)
    
    return wf_result


def main():
    parser = argparse.ArgumentParser(description="Backtest SMC/ICT v2")
    parser.add_argument("--csv", type=str, help="Fichier CSV avec données historiques")
    parser.add_argument("--capital", type=float, default=10000, help="Capital initial")
    parser.add_argument("--pair", type=str, default="EUR_USD", help="Pair (OANDA format)")
    parser.add_argument("--walk-forward", action="store_true", help="Walk-forward test")
    args = parser.parse_args()
    
    # Setup logging
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    
    logger = logging.getLogger("run_backtest")
    
    # Charger les données
    if args.csv:
        logger.info(f"Loading from CSV: {args.csv}")
        df = load_data_from_csv(args.csv)
    else:
        logger.info(f"Loading from broker: {args.pair}")
        df = load_data_from_broker(args.pair, "M1")
    
    if df.empty:
        logger.error("NO DATA — cannot run backtest")
        return
    
    logger.info(f"Data loaded: {len(df)} bars, columns: {list(df.columns)}")
    
    # Run backtest
    if args.walk_forward:
        result = run_walk_forward_test(df, args.capital)
    else:
        result = run_simple_backtest(df, args.capital)


if __name__ == "__main__":
    main()
