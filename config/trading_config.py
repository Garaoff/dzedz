"""
Configuration de trading — Bot SMC/ICT v2.

RÈGLE 5 : Le risque est centralisé ici. Aucune bypass possible.
RÈGLE 4 : Tous les paramètres justifiés.
RÈGLE 8 : Ce fichier est dans git, les secrets sont dans .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Charge les valeurs depuis .env (pas dans git)

# =============================================================================
# BROKER
# =============================================================================

BROKER_TYPE = os.getenv("BROKER_TYPE", "oanda")  # oanda | mt5 | ccxt

# OANDA
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")  # STRUCTURAL: practice=demo, live=réel

# MT5
MT5_PATH = os.getenv("MT5_PATH", "")
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# CCXT
CCXT_EXCHANGE = os.getenv("CCXT_EXCHANGE", "binance")
CCXT_API_KEY = os.getenv("CCXT_API_KEY", "")
CCXT_SECRET = os.getenv("CCXT_SECRET", "")
CCXT_TESTNET = os.getenv("CCXT_TESTNET", "true").lower() == "true"

# =============================================================================
# PAIR & TIMEFRAME
# =============================================================================

TRADING_PAIR = os.getenv("TRADING_PAIR", "EUR_USD")
ENTRY_TIMEFRAME = os.getenv("ENTRY_TIMEFRAME", "M1")  # STRUCTURAL: ICT nécessite M1
HTF_TIMEFRAME = os.getenv("HTF_TIMEFRAME", "H4")     # STRUCTURAL: H4 pour biais ICT

# =============================================================================
# RISQUE — Règle 5
# =============================================================================

CAPITAL = float(os.getenv("CAPITAL", "10000"))
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "1.0"))
ABSOLUTE_MAX_RISK_PCT = float(os.getenv("ABSOLUTE_MAX_RISK_PCT", "5.0"))
MIN_LOT_SIZE = float(os.getenv("MIN_LOT_SIZE", "0.01"))

# =============================================================================
# MODE
# =============================================================================

TRADING_MODE = os.getenv("TRADING_MODE", "demo")  # demo | live | backtest
# STRUCTURAL: demo = paper trading, live = réel, backtest = historique uniquement

# =============================================================================
# KILL SWITCH — Arrêt d'urgence
# =============================================================================

MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "3.0"))  # STRUCTURAL: arrêt si -3%/jour
MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES", "3"))  # STRUCTURAL: max 3 trades ouverts
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "10"))      # STRUCTURAL: max 10 trades/jour

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")


def validate_config():
    """
    Valide la configuration avant de lancer le bot.
    
    RÈGLE 6 : Pas d'échec silencieux — toute erreur est loguée.
    """
    errors = []
    
    if BROKER_TYPE not in ("oanda", "mt5", "ccxt"):
        errors.append(f"BROKER_TYPE invalide: {BROKER_TYPE}")
    
    if BROKER_TYPE == "oanda":
        if not OANDA_API_KEY:
            errors.append("OANDA_API_KEY manquant")
        if not OANDA_ACCOUNT_ID:
            errors.append("OANDA_ACCOUNT_ID manquant")
    
    if BROKER_TYPE == "mt5":
        if not MT5_LOGIN:
            errors.append("MT5_LOGIN manquant")
        if not MT5_PASSWORD:
            errors.append("MT5_PASSWORD manquant")
    
    if BROKER_TYPE == "ccxt":
        if not CCXT_API_KEY:
            errors.append("CCXT_API_KEY manquant")
        if not CCXT_SECRET:
            errors.append("CCXT_SECRET manquant")
    
    if CAPITAL <= 0:
        errors.append(f"CAPITAL invalide: {CAPITAL}")
    
    if MAX_RISK_PER_TRADE_PCT > ABSOLUTE_MAX_RISK_PCT:
        errors.append(f"MAX_RISK_PER_TRADE_PCT ({MAX_RISK_PER_TRADE_PCT}) > ABSOLUTE_MAX_RISK_PCT ({ABSOLUTE_MAX_RISK_PCT})")
    
    if TRADING_MODE not in ("demo", "live", "backtest"):
        errors.append(f"TRADING_MODE invalide: {TRADING_MODE}")
    
    if TRADING_MODE == "live" and MAX_RISK_PER_TRADE_PCT > 5:
        errors.append(f"RISQUE DANGEREUX: MAX_RISK_PER_TRADE_PCT={MAX_RISK_PER_TRADE_PCT}% en mode LIVE — max recommandé: 5%")
    
    return errors
