"""
Kill switch — Arrêt d'urgence automatique.

RÈGLE 5 : Si la perte journalière dépasse MAX_DAILY_LOSS_PCT, le bot s'arrête.
RÈGLE 6 : Pas d'échec silencieux — tout arrêt est logué.
RÈGLE 9 : Chiffres bruts pour la décision d'arrêt.
"""

import logging
from config.trading_config import MAX_DAILY_LOSS_PCT, MAX_CONCURRENT_TRADES

logger = logging.getLogger(__name__)


class KillSwitch:
    """
    Kill switch — arrête le bot automatiquement si :
    - Perte journalière > MAX_DAILY_LOSS_PCT (3% par défaut)
    - Erreur critique du broker
    
    AUCUN bypass possible. Le bot s'arrête, pas de "Grade S exception".
    """
    
    def __init__(self):
        self.is_active = False
        self.reason = ""
        self.initial_capital = 0
    
    def initialize(self, capital: float) -> None:
        """Initialise le kill switch avec le capital de départ."""
        self.initial_capital = capital
        self.is_active = False
        self.reason = ""
        logger.info(f"KILL_SWITCH_INIT | capital={capital} | max_daily_loss_pct={MAX_DAILY_LOSS_PCT}%")
    
    def should_stop(self, daily_pnl: float, capital: float, daily_start_capital: float) -> bool:
        """
        Détermine si le bot doit s'arrêter.
        
        RÈGLE 5 : AUCUN bypass possible — même les setups "Grade S" 
        ne peuvent pas contourner le kill switch.
        
        RÈGLE 9 : Chiffres bruts pour la décision.
        
        Args:
            daily_pnl: PnL cumulé du jour
            capital: Capital actuel
            daily_start_capital: Capital au début du jour
        
        Returns:
            True si le bot doit s'arrêter
        """
        if self.is_active:
            return True  # Déjà activé — ne redémarre pas
        
        # Calcul de la perte journalière en pourcentage
        if daily_start_capital <= 0:
            logger.warning("KILL_SWITCH | reason=zero_capital | cannot compute loss pct")
            return False
        
        daily_loss_pct = daily_pnl / daily_start_capital * 100  # STRUCTURAL: pct conversion
        
        # RÈGLE 5 : Seuil de perte journalière — AUCUN bypass
        if daily_loss_pct < -MAX_DAILY_LOSS_PCT:
            self.is_active = True
            self.reason = (
                f"DAILY_LOSS_EXCEEDED | "
                f"loss_pct={daily_loss_pct:.2f}% | "
                f"threshold=-{MAX_DAILY_LOSS_PCT}% | "
                f"daily_pnl={daily_pnl:.2f} | "
                f"start_capital={daily_start_capital:.2f} | "
                f"NO_BYPASS_POSSIBLE"
            )
            logger.error(self.reason)
            return True
        
        # Capital tombé à zéro
        if capital <= 0:
            self.is_active = True
            self.reason = f"CAPITAL_ZERO | capital={capital} | EMERGENCY_STOP"
            logger.error(self.reason)
            return True
        
        return False
    
    def manual_stop(self, reason: str = "manual") -> None:
        """Arrêt manuel — via dashboard ou commande."""
        self.is_active = True
        self.reason = f"MANUAL_STOP | reason={reason}"
        logger.warning(self.reason)
    
    def get_status(self) -> dict:
        """Statut du kill switch — chiffres bruts."""
        return {
            "is_active": self.is_active,
            "reason": self.reason,
            "initial_capital": self.initial_capital,
            "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
            "max_concurrent_trades": MAX_CONCURRENT_TRADES,
        }
