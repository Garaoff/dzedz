"""
Walk-forward — Bot SMC/ICT v2.

RÈGLE 7 : Split IS/OOS, taille d'échantillon, dégradation OOS vs IS.
RÈGLE 3 : Pas de signaux dupliqués.
RÈGLE 9 : Chiffres bruts pour chaque fenêtre.
"""

import logging
from typing import Optional

import pandas as pd

from backtest.engine import BacktestEngine
from backtest.metrics import compute_metrics
from config.params import (
    IS_OOS_SPLIT_RATIO,
    MIN_TRADES_FOR_VALIDATION,
    MIN_OOS_TRADES,
    OOS_DEGRADATION_REJECT_THRESHOLD,
    WALK_FORWARD_WINDOWS,
)

logger = logging.getLogger(__name__)


def run_walk_forward(
    df: pd.DataFrame,
    capital: float,
    risk_pct: float = 1.0,
    n_windows: int = WALK_FORWARD_WINDOWS,
    df_htf: Optional[pd.DataFrame] = None,
    symbol: str = "XAUUSD",
) -> dict:
    """
    Walk-forward test — chaque fenêtre IS/OOS avec métriques RÉELLES.
    
    RÈGLE 7 :
    - Split IS/OOS explicite
    - Minimum de trades vérifié
    - Dégradation OOS vs IS calculée avec chiffres bruts
    """
    total_bars = len(df)
    window_size = total_bars // n_windows
    is_ratio = IS_OOS_SPLIT_RATIO
    
    results = []
    
    for w in range(n_windows - 1):
        is_start = w * window_size
        is_end = is_start + int(window_size * is_ratio)
        oos_start = is_end
        oos_end = (w + 1) * window_size
        
        df_is = df.iloc[is_start:is_end]
        df_oos = df.iloc[oos_start:oos_end]
        
        logger.info(
            f"WALK_FORWARD | window={w+1}/{n_windows-1} | "
            f"IS={is_start}:{is_end} ({len(df_is)} bars) | "
            f"OOS={oos_start}:{oos_end} ({len(df_oos)} bars)"
        )
        
        # Backtest IS
        engine_is = BacktestEngine(capital=capital, risk_pct=risk_pct, symbol=symbol)  # DYNAMIC: symbol pour pip_size/pip_value
        result_is = engine_is.run(df_is, df_htf)
        metrics_is = compute_metrics(result_is["trades"])
        
        # Backtest OOS
        engine_oos = BacktestEngine(capital=capital, risk_pct=risk_pct, symbol=symbol)  # DYNAMIC: symbol pour pip_size/pip_value
        result_oos = engine_oos.run(df_oos, df_htf)
        metrics_oos = compute_metrics(result_oos["trades"])
        
        # Calcul de la dégradation OOS vs IS (RÈGLE 7 : chiffres bruts)
        is_trades = result_is["n_trades"]
        oos_trades = result_oos["n_trades"]
        
        is_win_rate = metrics_is.get("win_rate", 0)
        oos_win_rate = metrics_oos.get("win_rate", 0)
        
        is_pnl = metrics_is.get("total_pnl", 0)
        oos_pnl = metrics_oos.get("total_pnl", 0)
        
        is_profit_factor = metrics_is.get("profit_factor", 0)
        oos_profit_factor = metrics_oos.get("profit_factor", 0)
        
        # Dégradation win rate
        if is_win_rate > 0:
            degradation_wr = (is_win_rate - oos_win_rate) / is_win_rate
        else:
            degradation_wr = 0
        
        # Dégradation profit factor
        if is_profit_factor > 0:
            degradation_pf = (is_profit_factor - oos_profit_factor) / is_profit_factor
        else:
            degradation_pf = 0
        
        # Dégradation PnL
        if is_pnl > 0:
            degradation_pnl = (is_pnl - oos_pnl) / is_pnl
        else:
            degradation_pnl = 0
        
        # Dégradation max (la plus sévère)
        degradation_max = max(degradation_wr, degradation_pf, degradation_pnl)
        
        # Validation taille échantillon
        if is_trades < MIN_TRADES_FOR_VALIDATION:
            logger.warning(
                f"WALK_FORWARD | window={w+1} | IS_TRADES_INSUFFICIENT | "
                f"trades={is_trades} | min={MIN_TRADES_FOR_VALIDATION}"
            )
        
        if oos_trades < MIN_OOS_TRADES:
            logger.warning(
                f"WALK_FORWARD | window={w+1} | OOS_TRADES_INSUFFICIENT | "
                f"trades={oos_trades} | min={MIN_OOS_TRADES}"
            )
        
        # Critère de rejet
        rejected = degradation_max > OOS_DEGRADATION_REJECT_THRESHOLD
        
        if rejected:
            logger.warning(
                f"WALK_FORWARD | window={w+1} | PARAMETER_REJECTED | "
                f"degradation_wr={degradation_wr:.1%} | "
                f"degradation_pf={degradation_pf:.1%} | "
                f"degradation_pnl={degradation_pnl:.1%} | "
                f"threshold={OOS_DEGRADATION_REJECT_THRESHOLD:.1%}"
            )
        
        window_result = {
            "window": w + 1,
            "is_trades": is_trades,
            "oos_trades": oos_trades,
            "is_validated": is_trades >= MIN_TRADES_FOR_VALIDATION,
            "oos_validated": oos_trades >= MIN_OOS_TRADES,
            # Chiffres bruts (Règle 9)
            "is_win_rate": is_win_rate,
            "oos_win_rate": oos_win_rate,
            "is_pnl": is_pnl,
            "oos_pnl": oos_pnl,
            "is_profit_factor": is_profit_factor,
            "oos_profit_factor": oos_profit_factor,
            "is_sharpe": metrics_is.get("sharpe_ratio", 0),
            "oos_sharpe": metrics_oos.get("sharpe_ratio", 0),
            "is_max_dd": metrics_is.get("max_drawdown", 0),
            "oos_max_dd": metrics_oos.get("max_drawdown", 0),
            "is_avg_rr": metrics_is.get("avg_rr", 0),
            "oos_avg_rr": metrics_oos.get("avg_rr", 0),
            # Dégradations
            "degradation_wr": degradation_wr,
            "degradation_pf": degradation_pf,
            "degradation_pnl": degradation_pnl,
            "degradation_max": degradation_max,
            "rejected": rejected,
        }
        
        results.append(window_result)
        
        # Print chiffres bruts pour cette fenêtre
        logger.info(
            f"WALK_FORWARD | window={w+1} | "
            f"IS: trades={is_trades} | wr={is_win_rate:.2%} | pnl={is_pnl:.2f} | pf={is_profit_factor:.2f} | "
            f"OOS: trades={oos_trades} | wr={oos_win_rate:.2%} | pnl={oos_pnl:.2f} | pf={oos_profit_factor:.2f} | "
            f"DEGRADATION: wr={degradation_wr:.1%} | pf={degradation_pf:.1%} | max={degradation_max:.1%} | "
            f"rejected={rejected}"
        )
    
    # Résumé global
    total_is_trades = sum(r["is_trades"] for r in results)
    total_oos_trades = sum(r["oos_trades"] for r in results)
    avg_degradation = np.mean([r["degradation_max"] for r in results]) if results else 0
    n_rejected = sum(1 for r in results if r["rejected"])
    
    logger.info(
        f"WALK_FORWARD_COMPLETE | "
        f"windows={len(results)} | "
        f"total_is_trades={total_is_trades} | "
        f"total_oos_trades={total_oos_trades} | "
        f"avg_degradation={avg_degradation:.1%} | "
        f"rejected_windows={n_rejected}/{len(results)}"
    )
    
    return {
        "windows": results,
        "total_is_trades": total_is_trades,
        "total_oos_trades": total_oos_trades,
        "avg_degradation": avg_degradation,
        "n_rejected_windows": n_rejected,
        "all_windows_passed": n_rejected == 0,
    }


import numpy as np
