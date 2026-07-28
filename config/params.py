"""
Paramètres du bot SMC/ICT v2 — COMPLET.

RÈGLE 4 : Aucune valeur numérique fixe sans justification explicite.
Convention :
  # STRUCTURAL: <raison> — choix structurel, pas besoin d'être dynamique
  # DYNAMIC: <calcul> — calculé dynamiquement à partir de X

Tout ajout doit être accompagné d'une justification.
"""

# =============================================================================
# RISQUE — Règle 5 : un seul verrou, jamais de bypass
# =============================================================================

MAX_RISK_PER_TRADE_PCT = 1.0  # STRUCTURAL: 1% du capital par trade — conservateur
ABSOLUTE_MAX_RISK_PCT = 5.0  # STRUCTURAL: plafond absolu — jamais dépassé, même par erreur de config
MIN_LOT_SIZE = 0.01  # STRUCTURAL: minimum broker — ne peut pas être contourné

PIP_SIZE = 0.0001  # STRUCTURAL: 5-digit pricing pour la plupart des paires forex
PIP_VALUE_PER_LOT_EURUSD = 10.0  # STRUCTURAL: ~10$ par pip par lot standard EURUSD

# =============================================================================
# SL/TP
# =============================================================================

SL_BUFFER_ATR = 0.1  # STRUCTURAL: 10% ATR buffer pour spread/slippage
SL_DEFAULT_ATR_MULTIPLIER = 1.5  # STRUCTURAL: SL par défaut = 1.5 ATR si aucun niveau structurel
RR_MINIMUM = 1.5  # STRUCTURAL: RR minimum 1:1.5 — en dessous, le setup n'est pas viable

BE_TRIGGER_ATR = 1.0  # STRUCTURAL: breakeven déplacé après 1 ATR de profit dans le sens du trade
PARTIAL_CLOSE_PCT = 0.5  # STRUCTURAL: 50% de la position fermée à TP1
TRAIL_ATR_MULTIPLIER = 1.0  # STRUCTURAL: trailing stop à 1 ATR après breakeven

# =============================================================================
# STRUCTURE DE MARCHE (swings, BOS, CHOCH)
# =============================================================================

SWING_LOOKBACK = 3  # STRUCTURAL: 3 bougies de chaque côté pour confirmer un swing
SWING_CONFIRM_BARS = 3  # STRUCTURAL: 3 bougies sans dépassement pour confirmer un swing
BOS_CONFIRMATION_CLOSE = True  # STRUCTURAL: BOS confirmé sur clôture, pas sur mèche
CHOCH_CONFIRMATION_CLOSE = True  # STRUCTURAL: CHOCH confirmé sur clôture

# =============================================================================
# FVG (Fair Value Gap)
# =============================================================================

FVG_MIN_ATR_MULTIPLIER = 0.3  # STRUCTURAL: FVG < 0.3 ATR = bruit, pas un vrai déséquilibre
FVG_MAX_AGE_MULTIPLIER = 3.0  # STRUCTURAL: FVG trop vieux après 3x la période ATR (~42 bougies)
ATR_PERIOD = 14  # STRUCTURAL: convention standard pour ATR

# =============================================================================
# ORDER BLOCK
# =============================================================================

OB_MIN_MOVE_ATR = 1.5  # STRUCTURAL: OB doit montrer un mouvement > 1.5 ATR pour être significatif

# =============================================================================
# LIQUIDITY (sweeps, equal highs/lows)
# =============================================================================

EQUAL_TOLERANCE_ATR = 0.1  # STRUCTURAL: 10% de l'ATR pour considérer deux niveaux "égaux"

# =============================================================================
# DISPLACEMENT
# =============================================================================

DISPLACEMENT_MIN_ATR = 1.0  # STRUCTURAL: displacement > 1 ATR = mouvement institutionnel significatif

# =============================================================================
# ZONES (Premium / Discount)
# =============================================================================

EQUILIBRIUM_RATIO = 0.5  # STRUCTURAL: 50% = équilibre entre swing high et swing low
PREMIUM_THRESHOLD = 0.79  # STRUCTURAL: zone premium = prix > 79% du range (Fibonacci 0.79)
DISCOUNT_THRESHOLD = 0.21  # STRUCTURAL: zone discount = prix < 21% du range (Fibonacci 0.21)

# =============================================================================
# CONFLUENCE (score de qualité du setup)
# =============================================================================

HTF_BIAS_WEIGHT = 1  # STRUCTURAL: biais HTF aligné = +1 point
ZONE_WEIGHT = 1  # STRUCTURAL: zone premium/discount favorable = +1
FVG_WEIGHT = 1  # STRUCTURAL: FVG actif dans la zone = +1
OB_WEIGHT = 1  # STRUCTURAL: OB actif dans la zone = +1
SWEEP_WEIGHT = 2  # STRUCTURAL: liquidity sweep détecté = +2 (plus important)
DISPLACEMENT_WEIGHT = 1  # STRUCTURAL: displacement confirmé = +1
STRUCTURE_WEIGHT = 1  # STRUCTURAL: BOS/CHOCH récent = +1
CONFLUENCE_MINIMUM = 2  # STRUCTURAL: minimum 2 confluences pour entrer dans un trade

# =============================================================================
# VALIDATION — Règle 7 : échantillon réel, taille suffisante, hors échantillon
# =============================================================================

MIN_TRADES_FOR_VALIDATION = 200  # STRUCTURAL: en dessous de 200 trades = pas statistiquement significatif
MIN_OOS_TRADES = 100  # STRUCTURAL: minimum pour le hors-échantillon
IS_OOS_SPLIT_RATIO = 0.6  # STRUCTURAL: 60% in-sample / 40% out-of-sample
OOS_DEGRADATION_REJECT_THRESHOLD = 0.30  # STRUCTURAL: >30% dégradation OOS vs IS = rejet
WALK_FORWARD_WINDOWS = 5  # STRUCTURAL: 5 fenêtres walk-forward standard

# =============================================================================
# DONNÉES
# =============================================================================

HISTORICAL_TIMEFRAME = "M1"  # STRUCTURAL: ICT nécessite des données M1
MIN_HISTORY_YEARS = 1  # STRUCTURAL: minimum 1 an de données
IDEAL_HISTORY_YEARS = 3  # STRUCTURAL: idéal pour validation robuste
