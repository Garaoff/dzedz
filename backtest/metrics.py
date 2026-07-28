"""
Métriques de backtest — Bot SMC/ICT v2.

RÈGLE 7 : Affiche TOUJOURS le nombre de trades et la période.
RÈGLE 9 : Chiffres bruts, pas de conclusions générales sans preuve.

Calcul RÉALISTE : PnL tiré des trades simulés, pas placeholder.
"""

import logging
from typing import List

import numpy as np

from backtest.engine import BacktestTrade
from config.params import MIN_TRADES_FOR_VALIDATION

logger = logging.getLogger(__name__)


def compute_metrics(trades: List[BacktestTrade]) -> dict:
    """
    Calcule les métriques de performance d'un backtest.
    
    RÈGLE 7 : Affiche TOUJOURS le nombre de trades.
    RÈGLE 9 : Chiffres bruts uniquement.
    """
    n_trades = len(trades)
    
    if n_trades == 0:
        logger.warning("METRICS | no_trades | Aucun trade à analyser")
        return {
            "n_trades": 0,
            "warning": "AUCUN TRADE — métriques non significatives",
        }
    
    # PnL par trade (RÉALISTE, pas placeholder)
    pnls = [t.pnl for t in trades]
    pnls_pct = [t.pnl_pct for t in trades]
    
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    
    win_rate = len(wins) / n_trades
    total_pnl = sum(pnls)
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    
    # Max drawdown
    cumulative_pnl = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative_pnl)
    drawdowns = cumulative_pnl - running_max
    max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0
    
    # Max drawdown en pourcentage
    capital_values = [0] + list(np.cumsum([t.pnl for t in trades]))
    # Starting from initial capital, not tracking it here — simplified
    max_dd_pct = 0
    peak = 0
    for pnl in cumulative_pnl:
        if pnl > peak:
            peak = pnl
        dd = (peak - pnl) / abs(peak) if peak != 0 else 0
        max_dd_pct = max(max_dd_pct, dd)
    
    # Sharpe ratio (annualisé, approximation)
    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe = float(np.mean(pnls) / np.std(pnls) * np.sqrt(252))  # STRUCTURAL: 252 jours
    else:
        sharpe = 0.0
    
    # Profit factor
    gross_profit = sum([t.pnl for t in wins]) if wins else 0
    gross_loss = abs(sum([t.pnl for t in losses])) if losses else 0.001  # STRUCTURAL: avoid division by zero in profit factor
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Average trade duration
    avg_duration = np.mean([t.duration_bars for t in trades])
    
    # Average RR ratio
    avg_rr = np.mean([t.rr_ratio for t in trades])
    
    # SL vs TP hit rates
    tp_hits = sum(1 for t in trades if t.result == "tp_hit")
    sl_hits = sum(1 for t in trades if t.result == "sl_hit")
    be_hits = sum(1 for t in trades if t.result == "be_hit")
    timeouts = sum(1 for t in trades if t.result == "timeout")
    
    # SL methods breakdown
    sl_methods = {}
    for t in trades:
        method = t.sl_method
        if method not in sl_methods:
            sl_methods[method] = {"count": 0, "pnl": 0}
        sl_methods[method]["count"] += 1
        sl_methods[method]["pnl"] += t.pnl
    
    # TP methods breakdown
    tp_methods = {}
    for t in trades:
        method = t.tp_method
        if method not in tp_methods:
            tp_methods[method] = {"count": 0, "pnl": 0}
        tp_methods[method]["count"] += 1
        tp_methods[method]["pnl"] += t.pnl
    
    metrics = {
        "n_trades": n_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "sharpe_ratio": sharpe,
        "profit_factor": profit_factor,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "avg_duration_bars": avg_duration,
        "avg_rr": avg_rr,
        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "be_hits": be_hits,
        "timeouts": timeouts,
        "sl_methods": sl_methods,
        "tp_methods": tp_methods,
        "confluence_avg": np.mean([t.confluence_score for t in trades]),
        "partial_close_rate": sum(1 for t in trades if t.partial_closed) / n_trades,
        "be_reached_rate": sum(1 for t in trades if t.be_reached) / n_trades,
    }
    
    # Règle 7 : avertissement si échantillon trop petit
    if n_trades < MIN_TRADES_FOR_VALIDATION:  # DYNAMIC: seuil depuis config
        metrics["sample_warning"] = (
            f"ECHANTILLON INSUFFISANT ({n_trades} trades < {MIN_TRADES_FOR_VALIDATION}). "
            f"Les métriques ne sont PAS statistiquement significatives."
        )
    
    logger.info(
        f"METRICS | n_trades={n_trades} | win_rate={win_rate:.2%} | "
        f"pnl={total_pnl:.2f} | max_dd={max_dd:.2f} | "
        f"sharpe={sharpe:.2f} | pf={profit_factor:.2f} | "
        f"avg_rr={avg_rr:.2f} | avg_duration={avg_duration:.1f} bars"
    )
    
    return metrics
