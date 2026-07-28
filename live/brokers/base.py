"""
Base broker adapter — Interface abstraite.

RÈGLE 1 : Tous les brokers implémentent la même interface.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Résultat d'un ordre envoyé au broker."""
    success: bool
    order_id: str
    entry_price: float
    sl: float
    tp: float
    lot: float
    symbol: str
    direction: str
    message: str = ""
    error: str = ""


@dataclass
class AccountInfo:
    """Informations du compte broker."""
    capital: float
    currency: str
    margin_used: float
    margin_available: float
    open_positions: int
    unrealized_pnl: float


@dataclass
class PositionInfo:
    """Position ouverte."""
    ticket: str
    symbol: str
    direction: str  # "long" | "short"
    lot: float
    entry_price: float
    sl: float
    tp: float
    open_time: str
    current_price: float
    pnl: float


class BrokerAdapter(ABC):
    """
    Interface abstraite pour tous les brokers.
    
    RÈGLE 1 : Un seul interface — les modules core ne connaissent
    que cette interface, pas le broker spécifique.
    
    Toute erreur de broker est loguée (Règle 6), jamais silencieuse.
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """Connexion au broker. Retourne True si réussi."""
        ...
    
    @abstractmethod
    def disconnect(self) -> None:
        """Déconnexion du broker."""
        ...
    
    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """Récupère les informations du compte."""
        ...
    
    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int = 10000) -> list[dict]:
        """
        Récupère les données historiques (candles).
        
        RÈGLE 7 : count=10000 par défaut — jamais 3000 (bug v1).
        
        Returns:
            list de dicts: {"open": ..., "high": ..., "low": ..., "close": ..., "volume": ..., "time": ...}
        """
        ...
    
    @abstractmethod
    def get_current_price(self, symbol: str) -> dict:
        """Récupère le prix actuel (bid/ask)."""
        ...
    
    @abstractmethod
    def send_order(self, symbol: str, direction: str, lot: float, 
                   entry_price: float, sl: float, tp: float) -> OrderResult:
        """
        Envoie un ordre au broker.
        
        RÈGLE 5 : SL et TP sont OBLIGATOIRES. Pas d'ordre sans SL.
        
        Args:
            symbol: Pair (ex: "EUR_USD")
            direction: "long" | "short"
            lot: Taille en lots
            entry_price: Prix d'entrée
            sl: Stop-loss price
            tp: Take-profit price
        
        Returns:
            OrderResult
        """
        ...
    
    @abstractmethod
    def close_position(self, ticket: str) -> OrderResult:
        """Ferme une position par ticket."""
        ...
    
    @abstractmethod
    def modify_position(self, ticket: str, sl: Optional[float] = None, 
                        tp: Optional[float] = None) -> OrderResult:
        """Modifie SL/TP d'une position ouverte."""
        ...
    
    @abstractmethod
    def get_open_positions(self, symbol: str = "") -> list[PositionInfo]:
        """Récupère les positions ouvertes."""
        ...
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Vérifie si le broker est connecté."""
        ...
