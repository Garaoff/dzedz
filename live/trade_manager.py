"""
Trade manager — Suivi des trades ouverts en temps réel.

RÈGLE 6 : Pas d'échec silencieux — tout événement sur un trade est logué.
RÈGLE 9 : Chiffres bruts pour chaque trade.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ManagedTrade:
    """Trade en cours de gestion."""
    ticket: str
    symbol: str
    direction: str
    entry_price: float
    sl: float
    tp: float
    lot: float
    signal_type: str
    confluence: int
    open_time: str = ""
    be_reached: bool = False
    partial_closed: bool = False
    current_sl: float = 0
    current_pnl: float = 0
    last_recorded_pnl: float = 0
    max_profit: float = 0  # Maximum profit atteint
    max_loss: float = 0    # Maximum loss atteint
    
    def __post_init__(self):
        self.current_sl = self.sl


class TradeManager:
    """
    Gère les trades ouverts — tracking, breakeven, trailing.
    
    RÈGLE 1 : C'est le seul endroit qui track les trades ouverts.
    RÈGLE 9 : Chiffres bruts pour chaque trade.
    """
    
    def __init__(self):
        self.trades: dict[str, ManagedTrade] = {}
    
    def add_trade(
        self,
        ticket: str,
        symbol: str,
        direction: str,
        entry_price: float,
        sl: float,
        tp: float,
        lot: float,
        signal_type: str,
        confluence: int,
    ) -> ManagedTrade:
        """Ajoute un trade à la gestion."""
        trade = ManagedTrade(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            lot=lot,
            signal_type=signal_type,
            confluence=confluence,
            open_time=str(__import__("datetime").datetime.now()),
        )
        
        self.trades[ticket] = trade
        
        logger.info(
            f"TRADE_ADDED | ticket={ticket} | direction={direction} | "
            f"entry={entry_price:.5f} | sl={sl:.5f} | tp={tp:.5f} | "
            f"lot={lot:.4f} | signal_type={signal_type} | confluence={confluence}"
        )
        
        return trade
    
    def remove_trade(self, ticket: str, reason: str = "") -> Optional[ManagedTrade]:
        """Retire un trade de la gestion (SL/TP hit ou fermeture manuelle)."""
        trade = self.trades.pop(ticket, None)
        
        if trade is not None:
            logger.info(
                f"TRADE_REMOVED | ticket={ticket} | reason={reason} | "
                f"pnl={trade.current_pnl:.2f} | be_reached={trade.be_reached} | "
                f"max_profit={trade.max_profit:.2f} | max_loss={trade.max_loss:.2f}"
            )
        
        return trade
    
    def get_trade(self, ticket: str) -> Optional[ManagedTrade]:
        """Récupère un trade par ticket."""
        return self.trades.get(ticket)
    
    def get_all_trades(self) -> list[ManagedTrade]:
        """Récupère tous les trades ouverts."""
        return list(self.trades.values())
    
    def count(self) -> int:
        """Nombre de trades ouverts."""
        return len(self.trades)
    
    def update_pnl(self, ticket: str, pnl: float) -> None:
        """Update le PnL d'un trade."""
        trade = self.trades.get(ticket)
        if trade is None:
            return
        
        trade.current_pnl = pnl
        
        # Track max profit/loss
        if pnl > trade.max_profit:
            trade.max_profit = pnl
        
        if pnl < trade.max_loss:
            trade.max_loss = pnl
    
    def get_stats(self) -> dict:
        """Statistiques globales des trades en cours."""
        trades = self.get_all_trades()
        
        total_pnl = sum(t.current_pnl for t in trades)
        be_count = sum(1 for t in trades if t.be_reached)
        
        return {
            "open_trades": len(trades),
            "total_pnl": total_pnl,
            "be_reached_count": be_count,
            "trades": [
                {
                    "ticket": t.ticket,
                    "direction": t.direction,
                    "entry": t.entry_price,
                    "sl": t.current_sl,
                    "tp": t.tp,
                    "pnl": t.current_pnl,
                    "be_reached": t.be_reached,
                    "confluence": t.confluence,
                }
                for t in trades
            ],
        }
