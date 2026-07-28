#!/usr/bin/env python3
"""
Script de lancement du bot — RÉEL par défaut.

Usage:
    python scripts/start_bot.py              # Lancer en LIVE (réel)
    python scripts/start_bot.py --demo       # Mode demo (paper trading)
    python scripts/start_bot.py --dashboard  # Live + dashboard
    
RÈGLE 8 : Ce script est dans git, pas un script temporaire.
"""

import argparse
import logging
import sys
import os
import threading

# Ajouter le project root au path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)


def main():
    parser = argparse.ArgumentParser(description="Bot SMC/ICT v2 — Lancement")
    parser.add_argument("--demo", action="store_true", help="Mode demo (paper trading)")
    parser.add_argument("--live", action="store_true", help="Mode live (défaut)")
    parser.add_argument("--dashboard", action="store_true", help="Lancer dashboard web")
    parser.add_argument("--port", type=int, default=5000, help="Port du dashboard")
    args = parser.parse_args()
    
    # Déterminer le mode — LIVE par défaut (le bot trade en réel)
    if args.demo:
        os.environ["TRADING_MODE"] = "demo"
        print("📊 MODE DEMO — Paper trading (pas d'argent réel)")
    else:
        os.environ["TRADING_MODE"] = "live"
        print("🚀 MODE LIVE — TRADING RÉEL — XAUUSD/NAS100/BTCUSD")
    
    # Setup logging
    os.makedirs("logs", exist_ok=True)
    
    from live.bot import LiveBot, setup_logging
    setup_logging()
    
    logger = logging.getLogger("start_bot")
    logger.info("=" * 60)  # STRUCTURAL: 60 chars separator
    logger.info("STARTING BOT SMC/ICT v2 — LIVE")
    logger.info(f"Mode: {os.environ.get('TRADING_MODE', 'live')}")
    logger.info("=" * 60)  # STRUCTURAL: 60 chars separator
    
    # Créer le bot
    bot = LiveBot()
    
    # Lancer le dashboard en thread séparé si demandé
    if args.dashboard:
        from live.monitor import start_dashboard
        
        dashboard_thread = threading.Thread(
            target=start_dashboard,
            args=(bot, args.port),
            daemon=True,
        )
        dashboard_thread.start()
        
        print(f"🌐 Dashboard: http://localhost:{args.port}")
    
    # Lancer le bot
    print("🤖 Bot LIVE en cours de lancement...")
    print("   Ctrl+C pour arrêter")
    print()
    
    bot.start()


if __name__ == "__main__":
    main()
