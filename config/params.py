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
ABSOLUTE_MAX_RISK_PCT = 15.0  # STRUCTURAL: plafond absolu — 15% maximum (décision utilisateur), jamais dépassé même par erreur de config
MIN_LOT_SIZE = 0.01  # STRUCTURAL: minimum broker — ne peut pas être contourné

# RÈGLE 1 : pip_size et pip_value_per_lot sont DÉFINIS dans config/symbols.py
# par symbole (XAUUSD, NAS100, BTCUSD). Ces valeurs ne sont PLUS hardcoded ici.
# Utilise config.symbols.get_pip_size(symbol) et config.symbols.get_pip_value_per_lot(symbol)
#
# Valeurs par symbole (pour référence — la source unique est config/symbols.py) :
#   XAUUSD : pip_size=0.01, pip_value_per_lot=1.00 (100 oz × $0.01 = $1/pip/lot)
#   NAS100 : pip_size=1.0,  pip_value_per_lot=1.00 (1 contract × $1.00/point = $1/pip/lot)
#   BTCUSD : pip_size=0.01, pip_value_per_lot=0.01 (1 BTC × $0.01 = $0.01/pip/lot)
#
# ATTENTION : ces constantes sont gardées TEMPORAIREMENT pour compatibilité
# avec les tests existants et le backtest engine. Elles seront retirées
# quand tous les modules seront migrés vers config/symbols.py.
PIP_SIZE_EURUSD_LEGACY = 0.0001  # STRUCTURAL: legacy — EURUSD 5-digit pricing
PIP_VALUE_PER_LOT_EURUSD_LEGACY = 10.0  # STRUCTURAL: legacy — EURUSD $10/pip/lot

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
# KILLZONES ICT (Eastern Standard Time)
# =============================================================================

LONDON_KZ_START_EST = 2  # STRUCTURAL: 02:00 EST — ICT London Open Killzone start
LONDON_KZ_END_EST = 5  # STRUCTURAL: 05:00 EST — ICT London Open Killzone end (3h window)
NY_OPEN_KZ_START_EST = 8  # STRUCTURAL: 08:00 EST — ICT NY Open Killzone start
NY_OPEN_KZ_END_EST = 11  # STRUCTURAL: 11:00 EST — ICT NY Open Killzone end (3h window)
NY_PM_KZ_START_EST = 13  # STRUCTURAL: 13:00 EST — ICT NY PM Killzone start
NY_PM_KZ_END_EST = 16  # STRUCTURAL: 16:00 EST — ICT NY PM Killzone end (3h window)

# =============================================================================
# PDHL (Previous Day/Week High/Low)
# =============================================================================

PDHL_EQUAL_TOLERANCE_ATR = 0.15  # STRUCTURAL: 15% ATR pour considérer PDHL ≈ swing level
HOURS_PER_DAY = 24  # STRUCTURAL: 24 heures dans une journée — conversion horaire
MINUTES_PER_HOUR = 60  # STRUCTURAL: 60 minutes dans une heure — conversion horaire

# =============================================================================
# MSS (Market Structure Shift) — CHOCH + Displacement + FVG
# =============================================================================

MSS_FVG_TOLERANCE_INDEX = 1  # STRUCTURAL: FVG doit être créé ±1 bougie du MSS

# =============================================================================
# PO3 (Power of 3)
# =============================================================================

PO3_ACCUMULATION_RANGE_ATR_RATIO = 1.5  # STRUCTURAL: range < 1.5 ATR = phase accumulation (range tight)

# =============================================================================
# CONFLUENCE — Poids améliorés avec hiérarchie ICT
# =============================================================================

# STRUCTURAL: ICT hiérarchie des concepts — MSS est le signal le plus puissant
# puis Sweep, puis Zone, puis OB/FVG
MSS_WEIGHT = 3  # STRUCTURAL: MSS (CHOCH+Displacement+FVG) = poids 3 — signal ICT le plus puissant
KILLZONE_WEIGHT = 2  # STRUCTURAL: Killzone active = poids 2 — time filter crucial en ICT
PO3_WEIGHT = 1  # STRUCTURAL: PO3 phase distribution = poids 1 — confirme le cycle quotidien
BREAKER_WEIGHT = 1  # STRUCTURAL: Breaker Block = poids 1 — OB invalidé avec rôle inversé
PDHL_WEIGHT = 1  # STRUCTURAL: PDHL aligné = poids 1 — liquidité journalière/hebdo

# =============================================================================
# SCENARIO ENGINE — Probabilités et seuils
# =============================================================================

SCENARIO_MIN_PROBABILITY_PCT = 5.0  # STRUCTURAL: scenario < 5% de probabilité = ignoré
SCENARIO_TRAP_RISK_ATR = 1.5  # STRUCTURAL: si le prix dépasse 1.5 ATR dans la direction du piège, le piège est confirmé
SCENARIO_CONFIRMATION_CLOSE_PCT = 0.1  # STRUCTURAL: 10% au-delà du niveau = confirmation sur close

# =============================================================================
# SCENARIO ENGINE — Poids de probabilité par concept ICT
# =============================================================================

# STRUCTURAL: Ces poids définissent la contribution de chaque concept ICT
# à la probabilité d'un scenario. Ils sont basés sur la hiérarchie ICT :
# MSS > Sweep > Killzone > HTF > Zone > OB/FVG/Breaker/PDHL

# --- Trend Continuation (BOS + HTF) ---
SC_CONTINUATION_BOS_HTF_ALIGNED_PCT = 25.0  # STRUCTURAL: BOS + HTF aligné = 25% base (signal de continuation confirmé)
SC_CONTINUATION_BOS_NO_HTF_PCT = 10.0  # STRUCTURAL: BOS sans HTF = 10% (signal faible)
SC_CONTINUATION_NO_BOS_PCT = 5.0  # STRUCTURAL: pas de BOS = 5% (continuation peu probable)
SC_KILLZONE_ACTIVE_PCT = 10.0  # STRUCTURAL: killzone active = +10% probabilité (momentum institutionnel)
SC_KILLZONE_INACTIVE_PCT = 5.0  # STRUCTURAL: hors killzone = -5% (moins de momentum)
SC_ZONE_FAVORABLE_PCT = 10.0  # STRUCTURAL: zone favorable = +10% (position optimale)
SC_DISPLACEMENT_SIGNIFICANT_PCT = 10.0  # STRUCTURAL: displacement significatif = +10% (mouvement institutionnel)
SC_FVG_OB_BREAKER_PCT = 5.0  # STRUCTURAL: FVG/OB/Breaker dans la zone = +5% each (zone d'entrée)
SC_TRAP_PROBABILITY_THRESHOLD_PCT = 25.0  # STRUCTURAL: piège >= 25% = REJECT signal (prudence intelligente)
SC_ACTION_ENTER_THRESHOLD_PCT = 40.0  # STRUCTURAL: probabilité >= 40% = enter (setup viable)
SC_ACTION_WAIT_THRESHOLD_PCT = 25.0  # STRUCTURAL: probabilité >= 25% = wait for confirmation

# --- Trend Reversal (MSS + Sweep) ---
SC_REVERSAL_MSS_FVG_PCT = 30.0  # STRUCTURAL: MSS avec FVG = 30% base (signal ICT le plus puissant)
SC_REVERSAL_CHOCH_ONLY_PCT = 15.0  # STRUCTURAL: CHOCH seul = 15% (moins puissant que MSS)
SC_REVERSAL_NO_SIGNAL_PCT = 3.0  # STRUCTURAL: pas de signal retournement = 3%
SC_REVERSAL_SWEEP_ALIGNED_PCT = 15.0  # STRUCTURAL: sweep aligné avec retournement = +15%
SC_REVERSAL_SWEEP_COUNTER_PCT = 5.0  # STRUCTURAL: sweep contre-direction = -5%
SC_REVERSAL_PO3_DISTRIBUTION_PCT = 10.0  # STRUCTURAL: PO3 distribution = +10%
SC_REVERSAL_ACTION_ENTER_PCT = 50.0  # STRUCTURAL: reversal >= 50% = enter (setup très probable)
SC_REVERSAL_ACTION_WATCH_PCT = 30.0  # STRUCTURAL: reversal >= 30% = wait for retest
SC_REVERSAL_ACTION_OBSERVE_PCT = 15.0  # STRUCTURAL: reversal >= 15% = watch only

# --- Liquidity Trap ---
SC_TRAP_SWEEP_BASE_PCT = 15.0  # STRUCTURAL: sweep = 15% base pour piège
SC_TRAP_NO_DISPLACEMENT_PCT = 10.0  # STRUCTURAL: pas de displacement après sweep = +10% piège probable
SC_TRAP_NO_FVG_PCT = 10.0  # STRUCTURAL: pas de FVG après sweep = +10% piège probable
SC_TRAP_HTF_ALIGNED_PCT = 10.0  # STRUCTURAL: HTF aligné avec direction du sweep = +10%
SC_TRAP_AVOID_THRESHOLD_PCT = 20.0  # STRUCTURAL: piège >= 20% = avoid counter-trend
SC_TRAP_NO_SWEEP_PCT = 2.0  # STRUCTURAL: pas de sweep = 2% (piège peu probable)

# --- False Breakout ---
SC_FALSE_NO_DISPLACEMENT_PCT = 15.0  # STRUCTURAL: BOS sans displacement = +15% faux probable
SC_FALSE_WITH_DISPLACEMENT_PCT = 5.0  # STRUCTURAL: BOS avec displacement = 5% faux moins probable
SC_FALSE_HTF_COUNTER_PCT = 10.0  # STRUCTURAL: HTF contre BOS = +10% faux probable
SC_FALSE_NO_KILLZONE_PCT = 10.0  # STRUCTURAL: hors killzone = +10% faux probable
SC_FALSE_AVOID_THRESHOLD_PCT = 20.0  # STRUCTURAL: faux >= 20% = avoid breakout entry
SC_FALSE_NO_BOS_PCT = 2.0  # STRUCTURAL: pas de BOS = 2% (faux breakout peu probable)

# --- Range Bound ---
SC_RANGE_NEUTRAL_TREND_PCT = 25.0  # STRUCTURAL: tendance neutre = 25% (range probable)
SC_RANGE_NO_DISPLACEMENT_PCT = 15.0  # STRUCTURAL: pas de displacement = +15% range probable
SC_RANGE_HTF_NEUTRAL_PCT = 10.0  # STRUCTURAL: HTF neutre = +10% range
SC_RANGE_EQUILIBRIUM_PCT = 10.0  # STRUCTURAL: zone equilibrium = +10% range
SC_RANGE_AVOID_THRESHOLD_PCT = 30.0  # STRUCTURAL: range >= 30% = avoid trading

# --- Manipulation (PO3) ---
SC_MANIP_PO3_CONFIRMED_PCT = 30.0  # STRUCTURAL: PO3 manipulation = 30% base
SC_MANIP_SWEEP_NO_DISPLACEMENT_PCT = 15.0  # STRUCTURAL: sweep sans displacement = 15% manipulation
SC_MANIP_NO_SIGNAL_PCT = 3.0  # STRUCTURAL: pas de sweep = 3%
SC_MANIP_WAIT_THRESHOLD_PCT = 20.0  # STRUCTURAL: manipulation >= 20% = wait for distribution

# --- Distribution (PO3) ---
SC_DIST_PO3_BASE_PCT = 25.0  # STRUCTURAL: PO3 distribution = 25% base
SC_DIST_DISPLACEMENT_PCT = 15.0  # STRUCTURAL: displacement dans la direction = +15%
SC_DIST_MSS_ALIGNED_PCT = 15.0  # STRUCTURAL: MSS aligné = +15%
SC_DIST_MSS_COUNTER_PCT = 10.0  # STRUCTURAL: MSS contre-direction = -10%
SC_DIST_KILLZONE_PCT = 10.0  # STRUCTURAL: killzone active = +10%
SC_DIST_HTF_ALIGNED_PCT = 10.0  # STRUCTURAL: HTF aligné = +10%
SC_DIST_ZONE_FAVORABLE_PCT = 5.0  # STRUCTURAL: zone favorable = +5%

# --- Normalisation ---
SC_PROBABILITY_MAX_PCT = 100.0  # STRUCTURAL: probabilité max = 100% (pourcentage)
SC_PROBABILITY_MIN_PCT = 0.0  # STRUCTURAL: probabilité min = 0% (pourcentage)
SC_DISTRIBUTION_LOW_RISK_PCT = 40.0  # STRUCTURAL: distribution >= 40% = LOW risk, enter

# =============================================================================
# DONNÉES
# =============================================================================

HISTORICAL_TIMEFRAME = "M1"  # STRUCTURAL: ICT nécessite des données M1
MIN_HISTORY_YEARS = 1  # STRUCTURAL: minimum 1 an de données
IDEAL_HISTORY_YEARS = 3  # STRUCTURAL: idéal pour validation robuste
