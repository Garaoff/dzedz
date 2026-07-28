"""
Auto-optimisation en temps réel — Bot SMC/ICT v2.

RÈGLE 1 : auto_optimize() est la SEULE fonction d'auto-optimisation.
RÈGLE 7 : Ne remplace jamais un résultat sur grand échantillon par un petit.
RÈGLE 9 : Chiffres bruts pour chaque décision.
"""

import logging
from typing import Optional

from config.params import MIN_TRADES_FOR_VALIDATION
from backtest.metrics import compute_metrics
from backtest.engine import BacktestTrade

logger = logging.getLogger(__name__)


class AutoOptimizer:
    """
    Auto-optimisation des paramètres en temps réel.
    
    RÈGLE 7 : 
    - Un auto-ajustement ne remplace JAMAIS un résultat validé sur grand
      échantillon par un résultat sur échantillon plus petit.
    - La taille de l'échantillon est comparée, pas seulement les métriques.
    
    RÈGLE 9 :
    - Chaque décision est documentée avec chiffres bruts.
    """
    
    def __init__(self):
        self.current_params = {}
        self.current_sample_size = 0
        self.current_metrics = {}
        self.optimization_history = []
    
    def should_update(
        self,
        current_trades: list[BacktestTrade],
        current_sample_size: int,
        new_params: dict,
        new_trades: list[BacktestTrade],
        new_sample_size: int,
    ) -> dict:
        """
        Détermine si les paramètres doivent être mis à jour.
        
        RÈGLE 7 : Comparer la taille d'échantillon, pas seulement les métriques.
        
        Args:
            current_trades: Trades avec les paramètres actuels
            current_sample_size: Taille de l'échantillon actuel
            new_params: Nouveaux paramètres proposés
            new_trades: Trades avec les nouveaux paramètres
            new_sample_size: Taille du nouvel échantillon
        
        Returns:
            dict avec la décision et les chiffres bruts
        """
        # Calculer les métriques pour les deux sets
        current_metrics = compute_metrics(current_trades)
        new_metrics = compute_metrics(new_trades)
        
        # Chiffres bruts (Règle 9)
        decision = {
            "current_sample_size": current_sample_size,
            "new_sample_size": new_sample_size,
            "current_win_rate": current_metrics.get("win_rate", 0),
            "new_win_rate": new_metrics.get("win_rate", 0),
            "current_pnl": current_metrics.get("total_pnl", 0),
            "new_pnl": new_metrics.get("total_pnl", 0),
            "current_profit_factor": current_metrics.get("profit_factor", 0),
            "new_profit_factor": new_metrics.get("profit_factor", 0),
            "should_update": False,
            "reason": "",
        }
        
        # RÈGLE 7 : Minimum de trades pour validation
        if new_sample_size < MIN_TRADES_FOR_VALIDATION:
            decision["should_update"] = False
            decision["reason"] = (
                f"NEW_SAMPLE_TOO_SMALL | new_size={new_sample_size} | "
                f"min_required={MIN_TRADES_FOR_VALIDATION} | KEEPING current"
            )
            logger.warning(decision["reason"])
            return decision
        
        # RÈGLE 7 : Ne pas remplacer un grand échantillon par un petit
        if new_sample_size < current_sample_size:
            decision["should_update"] = False
            decision["reason"] = (
                f"NEW_SAMPLE_SMALLER | new={new_sample_size} < current={current_sample_size} | "
                f"KEEPING current (validé sur plus grand échantillon)"
            )
            logger.warning(decision["reason"])
            return decision
        
        # Comparer les métriques — le nouvel échantillon est >= l'ancien
        if new_metrics.get("win_rate", 0) > current_metrics.get("win_rate", 0) and \
           new_metrics.get("profit_factor", 0) > current_metrics.get("profit_factor", 0):
            decision["should_update"] = True
            decision["reason"] = (
                f"IMPROVED_METRICS | wr={current_metrics.get('win_rate', 0):.2%} -> {new_metrics.get('win_rate', 0):.2%} | "
                f"pf={current_metrics.get('profit_factor', 0):.2f} -> {new_metrics.get('profit_factor', 0):.2f} | "
                f"sample={current_sample_size} -> {new_sample_size}"
            )
            logger.info(decision["reason"])
        else:
            decision["should_update"] = False
            decision["reason"] = (
                f"NO_IMPROVEMENT | wr={current_metrics.get('win_rate', 0):.2%} -> {new_metrics.get('win_rate', 0):.2%} | "
                f"pf={current_metrics.get('profit_factor', 0):.2f} -> {new_metrics.get('profit_factor', 0):.2f} | "
                f"KEEPING current"
            )
            logger.info(decision["reason"])
        
        # Enregistrer dans l'historique
        self.optimization_history.append(decision)
        
        return decision
    
    def get_history(self) -> list[dict]:
        """Historique des optimisations — chiffres bruts."""
        return self.optimization_history
