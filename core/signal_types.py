"""
Types de signaux — Bot SMC/ICT v2.

RÈGLE 3 : Transition, pas état.
Chaque signal a un timestamp unique. Deux signaux au même timestamp = erreur.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalType(Enum):
    """Types de signaux SMC/ICT reconnus."""
    # === Concepts ICT originaux ===
    FVG_BULL = "fvg_bull"
    FVG_BEAR = "fvg_bear"
    BOS_BULL = "bos_bull"
    BOS_BEAR = "bos_bear"
    CHOCH_BULL = "choch_bull"
    CHOCH_BEAR = "choch_bear"
    LIQUIDITY_SWEEP_HIGH = "liquidity_sweep_high"
    LIQUIDITY_SWEEP_LOW = "liquidity_sweep_low"
    OB_BULL = "ob_bull"  # Order Block
    OB_BEAR = "ob_bear"
    
    # === Concepts ICT avancés (v2 amélioré) ===
    MSS_BULL = "mss_bull"  # Market Structure Shift (CHOCH + Displacement + FVG)
    MSS_BEAR = "mss_bear"
    BREAKER_BULL = "breaker_bull"  # Breaker Block (OB invalidé → rôle inversé)
    BREAKER_BEAR = "breaker_bear"
    SILVER_BULLET_LONG = "silver_bullet_long"  # Silver Bullet setup (Killzone + MSS + FVG + Sweep)
    SILVER_BULLET_SHORT = "silver_bullet_short"
    
    # === PDHL (Previous Day/Week High/Low) ===
    PDHL_SWEEP_HIGH = "pdhl_sweep_high"  # Sweep de PDH/PWH
    PDHL_SWEEP_LOW = "pdhl_sweep_low"  # Sweep de PDL/PWL


class SignalDirection(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Signal:
    """
    Signal d'entrée unique.
    
    RÈGLE 3 : Un signal est émis au moment de la TRANSITION (condition devient vraie
    après avoir été fausse à la bougie n-1). Jamais sur l'état seul.
    
    L'unicité du timestamp est garantie par le SignalRegistry.
    """
    signal_type: SignalType
    direction: SignalDirection
    timestamp: datetime
    price: float
    atr_at_signal: float  # DYNAMIC: ATR au moment du signal, sert aux calculs SL/TP
    htf_bias: Optional[str] = None  # DYNAMIC: biais timeframe supérieur
    confluences: list = field(default_factory=list)  # Autres confluences détectées
    killzone: Optional[str] = None  # DYNAMIC: killzone active au moment du signal
    po3_phase: Optional[str] = None  # DYNAMIC: phase PO3 au moment du signal
    
    def __post_init__(self):
        """Validation à la création."""
        if self.price <= 0:
            raise ValueError(f"Prix invalide: {self.price}")
        if self.atr_at_signal <= 0:
            raise ValueError(f"ATR invalide: {self.atr_at_signal}")


class SignalRegistry:
    """
    Registre des signaux — garantit l'unicité du timestamp.
    
    RÈGLE 3 : Empêche les signaux dupliqués au même timestamp.
    """
    
    def __init__(self):
        self._signals: dict[datetime, Signal] = {}
    
    def register(self, signal: Signal) -> bool:
        """
        Enregistre un signal. Retourne False si un signal existe déjà
        au même timestamp (déduplication Règle 3).
        """
        if signal.timestamp in self._signals:
            return False  # Signal déjà enregistré à ce timestamp → déduplication
        self._signals[signal.timestamp] = signal
        return True
    
    def get_signals(self) -> list[Signal]:
        """Retourne tous les signaux triés par timestamp."""
        return sorted(self._signals.values(), key=lambda s: s.timestamp)
    
    def count(self) -> int:
        """Nombre de signaux uniques enregistrés."""
        return len(self._signals)
    
    def clear(self):
        """Vide le registre."""
        self._signals.clear()
