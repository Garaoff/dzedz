"""
Point d'entrée live — Bot SMC/ICT v2.

RÈGLE 1 : Utilise les modules core comme source unique de vérité.
RÈGLE 5 : Tout ordre passe par risk_guard via order_executor.
RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 8 : Ce fichier est dans git, pas un script temporaire.
"""

import logging
import sys

from data.loader import load_historical_data
from data.validator import validate_data_integrity
from core.signal_detector import detect_signal, get_htf_bias
from core.signal_types import SignalRegistry
from core.sl_tp_calculator import calculate_sl_tp  # Règle 1 : SEULE source de SL/TP
from core.position_sizer import calculate_position_size  # Règle 1 : SEULE source de taille de position
from core.order_executor import OrderExecutor  # Appelle risk_guard automatiquement (Règle 5)

logger = logging.getLogger(__name__)

# Règle 8 : configuration du logging structuré — jamais silencieux
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log"),
    ],
)


def run_bot():
    """
    Point d'entrée principal du bot live.
    
    Pipeline obligatoire :
    1. load_historical_data() → données M1
    2. validate_data_integrity() → vérification
    3. get_htf_bias() → biais HTF (Règle 1 : seule source)
    4. detect_signal() → signal (Règle 3 : transition)
    5. OrderExecutor.execute_order() → ordre (Règle 5 : verrou risque)
    """
    logger.info("BOT_START | version=v2 | rules=9")
    
    # TODO: Implémenter la connexion au broker
    # TODO: Implémenter la boucle live
    
    logger.info("BOT_READY | waiting for implementation")


if __name__ == "__main__":
    run_bot()
