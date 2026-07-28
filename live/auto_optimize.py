"""
Auto-optimisation — Bot SMC/ICT v2.

RÈGLE 1 : Seule fonction d'auto-optimisation.
RÈGLE 7 : Ne remplace jamais un résultat validé sur grand échantillon
par un résultat sur échantillon plus petit.
"""

import logging

from config.params import MIN_TRADES_FOR_VALIDATION

logger = logging.getLogger(__name__)


def auto_optimize(
    current_params: dict,
    current_sample_size: int,
    new_params: dict,
    new_sample_size: int,
    new_metrics: dict,
) -> dict:
    """
    Auto-optimisation des paramètres en temps réel.
    
    RÈGLE 7 : Un auto-ajustement ne remplace un paramètre validé
    que si le nouvel échantillon est >= l'ancien.
    
    Args:
        current_params: Paramètres actuellement validés
        current_sample_size: Taille de l'échantillon sur lequel les paramètres ont été validés
        new_params: Nouveaux paramètres proposés
        new_sample_size: Taille de l'échantillon du nouveau résultat
        new_metrics: Métriques du nouveau résultat
    
    Returns:
        Les paramètres à utiliser (soit current, soit new)
    """
    # RÈGLE 7 : Comparer la taille des échantillons, pas seulement les métriques
    if new_sample_size < MIN_TRADES_FOR_VALIDATION:
        logger.warning(
            f"AUTO_OPT_REJECT | reason=insufficient_sample | "
            f"new_size={new_sample_size} | min_required={MIN_TRADES_FOR_VALIDATION} | "
            f"KEEPING current params"
        )
        return current_params
    
    if new_sample_size < current_sample_size:
        logger.warning(
            f"AUTO_OPT_REJECT | reason=smaller_sample | "
            f"new_size={new_sample_size} < current_size={current_sample_size} | "
            f"KEEPING current params (validés sur plus grand échantillon)"
        )
        return current_params
    
    # Si le nouvel échantillon est >= l'ancien ET >= le minimum, on peut considérer
    logger.info(
        f"AUTO_OPT_CONSIDER | "
        f"new_size={new_sample_size} >= current_size={current_sample_size} | "
        f"new_metrics={new_metrics}"
    )
    
    # TODO: Implémenter les critères de remplacement réels
    # (comparaison des métriques IS/OOS, dégradation, etc.)
    
    return current_params  # Placeholder — toujours garder les paramètres actuels pour l'instant
