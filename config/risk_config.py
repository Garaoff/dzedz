"""
Configuration risque — Bot SMC/ICT v2.

RÈGLE 5 : Un seul verrou, jamais de bypass.
Ce fichier est la SEULE source de configuration pour le risque.
core/risk_guard.py est le SEUL endroit où cette config est lue et appliquée.

Aucune catégorie de setup (Grade S, Grade A, etc.) ne peut contourner
les vérifications définies ici.
"""

from config.params import MAX_RISK_PER_TRADE_PCT, ABSOLUTE_MAX_RISK_PCT, MIN_LOT_SIZE


def get_max_risk_pct() -> float:
    """
    Retourne le risque maximum par trade en pourcentage du capital.
    
    Cette fonction est la SEULE interface pour obtenir le plafond de risque.
    Elle est appelée UNIQUEMENT par core/risk_guard.py validate_risk().
    """
    return MAX_RISK_PER_TRADE_PCT


def get_absolute_max_risk_pct() -> float:
    """
    Plafond absolu — même si un opérateur configure MAX_RISK_PER_TRADE_PCT
    à une valeur déraisonnable, ce plafond ne sera jamais dépassé.
    """
    return ABSOLUTE_MAX_RISK_PCT


def get_min_lot_size() -> float:
    """
    Taille minimum de lot imposée par le broker.
    Ce lot minimum est soumis à la vérification de risque, pas exempté.
    """
    return MIN_LOT_SIZE
