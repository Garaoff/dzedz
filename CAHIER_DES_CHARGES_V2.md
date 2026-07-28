# 🏗️ BIBLE DE RECONSTRUCTION — Bot SMC/ICT v2 (from scratch)

> **Version** : 2.0 — 28 juillet 2026  
> **Statut** : Document fondateur ULTIME — À fournir à l'IA en ENTIER avant la première ligne de code  
> **Principe** : Ce document transforme chaque bug réel de la v1 en règle de conception, et définit chaque concept SMC/ICT avec une précision algorithmique suffisante pour coder sans ambiguïté.

---

## ⚠️ Réserve honnête

Ce document empêche de refaire les erreurs qu'on a déjà trouvées, mais il n'en empêche pas de nouvelles. **Réflexe permanent : demander des chiffres bruts et du code à l'appui plutôt que des affirmations, et tester chaque brique avant de l'empiler sur la suivante.**

---

# PARTIE I — LES 9 RÈGLES DE CONCEPTION (dérivées de bugs réels)

---

## Règle 1 — Une seule source de vérité par concept

**Ce qui a cassé** : cinq fonctions différentes calculaient chacune le SL/TP (`compute_ict_liquidity_sl_tp`, `OrderManager.compute_sl_tp`, `apply_dynamic_sl`, `apply_quality_fixed_tp`, `build_safe_stop`), sans qu'aucune ne soit clairement autoritaire. Pareil avec trois systèmes d'auto-optimisation séparés ajustant les mêmes paramètres.

**Règle** :
```
Pour chaque concept (calcul de SL/TP, biais HTF, taille de position,
auto-optimisation...), il ne doit exister qu'UNE fonction qui le calcule.
Si un ajustement en couche successive est nécessaire (ex: contrainte broker),
chaque couche doit logger: AVANT=... APRES=... RAISON=...
```

**Application concrète** :
- `ARCHITECTURE.md` liste chaque concept → unique fonction responsable
- Toute nouvelle fonction qui calcule quelque chose est validée contre ce registre AVANT d'être écrite
- Si une fonction modifie la sortie d'une autre : `logger.info(f"SL_ADJUST | layer=broker | before={v} | after={v2} | reason=...")`

---

## Règle 2 — Aucune fonction écrite sans preuve qu'elle est appelée

**Ce qui a cassé** : `apex_htf_bias.py`, `trailing_stop_candidate()`, `adv_sl_bull/adv_sl_source` — trois fois du code écrit, testé isolément, mais jamais branché dans le chemin live. Le paramètre `df_m1` accepté dans une signature sans jamais être utilisé.

**Règle** :
```
Après avoir écrit une fonction destinée au bot live, montre la ligne exacte
dans un fichier du pipeline live qui l'importe ET l'appelle ET utilise sa
valeur de retour. Si cette ligne n'existe pas encore, dis-le explicitement.
```

**Application concrète** :
- Test d'intégration par module : vérifie que la fonction est appelée dans le pipeline
- `scripts/check_dead_code.py` détecte les fonctions non appelées
- Convention : `# TODO: NOT WIRED` pour les fonctions non branchées — jamais présentées comme "prêtes"

---

## Règle 3 — Transition, pas état

**Ce qui a cassé** : le comptage de trades comptait un même setup plusieurs fois tant que sa condition restait vraie sur plusieurs bougies (16 326 "trades" pour 7 943 signaux réels).

**Règle** :
```
Tout signal se déclenche UNE SEULE FOIS, au moment précis où une condition
devient vraie après avoir été fausse à la bougie n-1 (comparaison explicite
avec l'état de la bougie précédente). Pour toute nouvelle détection, montre
le test qui empêche la répétition sur plusieurs bougies consécutives.
```

**Application concrète** :
- Pattern obligatoire : `signal = condition & ~condition.shift(1)`
- Chaque détecteur inclut un test unitaire : signal persistant sur N bougies → 1 signal, pas N
- `SignalRegistry` : deux signaux au même timestamp = rejet

---

## Règle 4 — Aucune valeur numérique fixe sans justification explicite

**Ce qui a cassé** : seuils fixes non documentés dans des modules prétendant ne pas en avoir (poids 0.4/0.6, seuil WFE 0.3, fenêtre 40 bougies pour iFVG).

**Règle** :
```
Pour chaque nombre en dur : soit remplace-le par un calcul dynamique (ATR,
volatilité), soit justifie par écrit pourquoi c'est structurel (ex: "3 points
minimum pour une droite" est structurel, "40 bougies" ne l'est pas sans
justification).
```

**Application concrète** :
- Tous les paramètres dans `config/params.py` avec `# STRUCTURAL: raison` ou `# DYNAMIC: calcul`
- Linter `scripts/check_magic_numbers.py` détecte les nombres en dur hors config

---

## Règle 5 — Gestion du risque : un seul verrou, jamais de bypass

**Ce qui a cassé** : `max_trade_loss_pct` et `absolute_max_risk_pct` configurés à 100%, avec un bypass pour les setups "Grade S".

**Règle** :
```
Le risque maximum par trade est un seul paramètre, vérifié à un seul endroit,
juste avant l'envoi de l'ordre. Aucune catégorie de setup ne peut contourner
cette vérification. Départ: 0.5-2% du capital, jamais >5% sans raison écrite.
Le lot minimum forcé est soumis à la même vérification, pas exempté.
```

**Application concrète** :
- `core/risk_guard.py` → `validate_risk()` appelé UNIQUEMENT dans `order_executor.py`
- Le grade du setup est EXPLICITEMENT ignoré dans le calcul
- Test unitaire : aucun chemin de code ne peut envoyer un ordre sans `validate_risk()`

---

## Règle 6 — Gestion d'erreur : jamais d'échec silencieux

**Ce qui a cassé** : des `except: pass` dans le module de protection de position.

**Règle** :
```
Interdiction du except:pass dans tout code touchant à l'exécution, la protection
de position, ou le calcul de risque. Toute exception doit être loguée avec son
message complet.
```

**Application concrète** :
- Pattern obligatoire : `except Exception as e: logger.error(f"CONTEXTE: {e}", exc_info=True)`
- Linter `scripts/check_silent_except.py` détecte les violations

---

## Règle 7 — Validation : échantillon réel, taille suffisante, hors échantillon

**Ce qui a cassé** : résultat "validé" sur 3 trades. Cache plafonné à 3000 bougies. Auto-optimisation sur 10 jours remplaçant des résultats sur 1 an.

**Règle** :
```
Aucun paramètre validé avec <200 trades sur données réelles, avec split IS/OOS.
Un auto-ajustement ne remplace jamais un résultat validé sur grand échantillon
par un résultat sur échantillon plus petit.
```

**Application concrète** :
- `MIN_TRADES_FOR_VALIDATION = 200` dans config
- Tout résultat affiche : nb trades, période, IS/OOS, win rate, PnL, max DD
- Auto-ajustement : nouveau sample ≥ ancien sample obligatoire

---

## Règle 8 — Process de développement : trace et réversibilité

**Ce qui a cassé** : dizaines de scripts `fix_*.py`/`patch_*.py`/`wipe_*.py` sans historique. Bypass de sécurité réintroduit sans être visible.

**Règle** :
```
Projet sous git dès le premier commit. Chaque changement = un commit avec
message clair. Avant de réintroduire un mécanisme retiré, vérifie l'historique.
```

**Application concrète** :
- Convention de commit : `feat:`, `fix:`, `refactor:`, `remove:`
- Aucun script patch — tout passe par git
- `git log --all --grep="remove" | grep <mécanisme>` avant réintroduction

---

## Règle 9 — Auto-évaluation : jamais suffisante seule

**Ce qui a cassé** : auto-évaluation "tout est coché ✅" révélée incomplète à la vérification.

**Règle** :
```
Pour chaque point d'audit : (1) chiffre brut, (2) fichier:ligne exact,
(3) conclusion. Si un chiffre n'est pas disponible, le dire explicitement.
Jamais de conclusion générale avant d'avoir traité chaque point.
```

---

# PARTIE II — CONCEPTS SMC/ICT : DÉFINITIONS ALGORITHMIQUES PRÉCISES

Chaque concept est défini avec suffisamment de précision pour être codé sans ambiguïté. Si un concept nécessite un jugement subjectif, le critère de décision est explicite.

---

## 2.1 Biais du Timeframe Supérieur (HTF Bias)

### Définition
Le biais HTF détermine la direction privilégiée des trades sur le timeframe d'exécution. Il est calculé UNIQUEMENT sur le timeframe supérieur (H4 ou D1 pour de l'exécution M5/M15).

### Algorithme de détermination

```
HTF_BIAS = déterminer_biais(df_htf)

1. Identifier la structure de marché sur HTF :
   - Dernier BOS haussier → tendance haussière
   - Dernier BOS baissier → tendance baissière
   - Si dernier CHOCH → changement de tendance

2. Confirmer avec la position du prix :
   - Prix au-dessus du dernier swing low structurel → biais long
   - Prix en-dessous du dernier swing high structurel → biais short

3. Résultat : "bullish" | "bearish" | "neutral"
   - neutral = conflit entre BOS et position du prix, ou pas assez de données
```

### Critère de swing detection (HTF)
```
SWING_HIGH = high[i] > high[i-1] AND high[i] > high[i+1]
SWING_LOW  = low[i]  < low[i-1]  AND low[i]  < low[i+1]

Pour HTF (H4/D1) : utiliser un lookback de 3-5 bougies de chaque côté
pour confirmer le swing (pas juste 1).
```

### Règle 1
`get_htf_bias()` dans `core/signal_detector.py` est la SEULE fonction qui calcule le biais HTF. Aucune autre fonction ne doit déterminer le biais HTF.

---

## 2.2 Break of Structure (BOS)

### Définition
Un BOS confirme la continuation de la tendance en cours. Il se produit quand le prix casse un swing structurel dans la direction de la tendance dominante.

### Algorithme de détection

```
BOS_BULL :
  condition = close[i] > swing_high_le_plus_recent  # Casse le plus haut structurel
  transition = condition AND NOT condition à la bougie [i-1]  # Règle 3

BOS_BEAR :
  condition = close[i] < swing_low_le_plus_recent    # Casse le plus bas structurel
  transition = condition AND NOT condition à la bougie [i-1]  # Règle 3
```

### Stockage des swings
```
À chaque swing détecté, stocker :
  - type: "swing_high" | "swing_low"
  - price: niveau du swing
  - timestamp: moment de détection
  - confirmed: bool (confirmé après 3 bougies sans dépassement)

Les swings non confirmés ne sont PAS utilisés pour BOS/CHOCH.
```

### Validation
- Le BOS doit se produire sur une bougie qui CLÔTURE au-dessus/en-dessous du swing (pas juste une mèche)
- Le volume de la bougie de BOS doit être > moyenne des 20 dernières bougies (confirmation institutionnelle)

---

## 2.3 Change of Character (CHOCH)

### Définition
Un CHOCH signale un potentiel changement de tendance. Il se produit quand le prix casse un swing structurel CONTRE la tendance dominante.

### Algorithme de détection

```
CHOCH_BULL (retournement haussier) :
  tendance_précédente = bearish
  condition = close[i] > dernier_swing_high  # Casse le plus haut alors qu'on était baissier
  transition = condition AND NOT condition à [i-1]  # Règle 3

CHOCH_BEAR (retournement baissier) :
  tendance_précédente = bullish
  condition = close[i] < dernier_swing_low   # Casse le plus bas alors qu'on était haussier
  transition = condition AND NOT condition à [i-1]  # Règle 3
```

### Différence BOS vs CHOCH
```
BOS   = continuation de la tendance (casse dans le sens de la tendance)
CHOCH = retournement (casse contre la tendance)
```

### Validation
- Un CHOCH est plus significatif s'il se produit sur un niveau de liquidité (voir 2.7)
- Un CHOCH sur HTF prime sur un BOS sur LTF

---

## 2.4 Fair Value Gap (FVG)

### Définition
Un FVG est un déséquilibre (imbalance) créé quand le prix se déplace si rapidement que le marché n'a pas le temps d'équilibrer les acheteurs et vendeurs. Il apparaît comme un gap entre la mèche d'une bougie et la mèche de la bougie deux positions plus tard.

### Algorithme de détection

```
FVG_BULL (gap haussier) :
  wicks_low_1 = low[i-1]     # Plus bas de la bougie du milieu
  wicks_high_3 = high[i+1]   # Plus haut de la bougie suivante (après close)
  
  # FVG existe si le plus haut de [i+1] ne remplit pas le plus bas de [i-1]
  gap_top = min(low[i-1], low[i+1])    # Bord supérieur du gap
  gap_bottom = max(high[i-1], high[i+1])  # Bord inférieur du gap
  
  WAIT — correction:
  
  FVG_BULL :
    gap_top = low[i-1]       # Bord supérieur = plus bas de la bougie avant
    gap_bottom = high[i+1]   # Bord inférieur = plus haut de la bougie après
    
  condition = gap_top > gap_bottom  # Il y a un gap
  taille_gap = gap_top - gap_bottom

FVG_BEAR (gap baissier) :
    gap_top = low[i+1]       # Bord supérieur = plus bas de la bougie après
    gap_bottom = high[i-1]   # Bord inférieur = plus haut de la bougie avant
    
  condition = gap_top > gap_bottom
  taille_gap = gap_top - gap_bottom
```

### Filtrage par taille minimum
```
taille_minimum = ATR * FVG_MIN_ATR_MULTIPLIER  # DYNAMIC, pas un seuil fixe
# FVG_MIN_ATR_MULTIPLIER = 0.3 (STRUCTURAL: en dessous, c'est du bruit, pas un vrai déséquilibre)

FVG_valide = taille_gap >= taille_minimum
```

### Inverse Fair Value Gap (iFVG) — FVG rempli
```
Un FVG est "fillé" (iFVG) quand le prix revient dans le gap et le traverse
complètement. Cela signifie que le déséquilibre a été résolu.

FVG_BULL_fillé = low[i] <= gap_bottom  # Prix repasse sous le gap
FVG_BEAR_fillé = high[i] >= gap_top    # Prix repasse au-dessus du gap

Les FVG fillés sont RETIRÉS de la liste des FVG actifs.
```

### Âge d'un FVG
```
age = nombre_de_bougies_depuis_creation

Un FVG trop vieux perd de sa pertinence :
  max_age = ATR_PERIOD * FVG_MAX_AGE_MULTIPLIER  # DYNAMIC
  # FVG_MAX_AGE_MULTIPLIER = 3 (STRUCTURAL: ~3x la période ATR = 42 bougies)
  # Si on veut un chiffre fixe, il DOIT être justifié par écrit.
  
FVG_actif = NOT fillé AND age <= max_age
```

---

## 2.5 Order Block (OB)

### Définition
Un Order Block est la dernière bougie haussière avant un mouvement baissier fort (OB vendeur) ou la dernière bougie baissière avant un mouvement haussier fort (OB acheteur). Il représente la zone où les institutions ont placé leurs ordres.

### Algorithme de détection

```
OB_BULL (zone d'accumulation — dernière bougie baissière avant un rally) :
  1. Identifier un mouvement haussier fort :
     move_up = (high[i+2] - low[i]) / ATR >= OB_MIN_MOVE_ATR  # DYNAMIC
     # OB_MIN_MOVE_ATR = 1.5 (STRUCTURAL: un OB doit montrer un mouvement disproportionné)
  
  2. La bougie i est la DERNIÈRE bougie bearish avant le mouvement :
     is_bearish = close[i] < open[i]
  
  3. Le mouvement suit immédiatement :
     next_bullish = close[i+1] > open[i+1]  # Au moins 1 bougie de confirmation
  
  4. La zone OB est définie par :
     ob_top = open[i]     # Ouverture de la bougie bearish
     ob_bottom = low[i]   # Plus bas de la bougie bearish

OB_BEAR (zone de distribution — dernière bougie haussière avant un dump) :
  1. move_down = (high[i] - low[i+2]) / ATR >= OB_MIN_MOVE_ATR
  2. is_bullish = close[i] > open[i]
  3. next_bearish = close[i+1] < open[i+1]
  4. ob_top = high[i]
     ob_bottom = open[i]
```

### Validation de l'OB
```
Un OB est valide tant que :
  - Le prix n'a pas traversé la zone (close au-delà du côté opposé)
  - L'OB est dans le timeframe correct (pas de micro-OB sur M1 si on trade M15)

OB_invalide = 
  OB_BULL: close[i] < ob_bottom  # Le prix a cassé en-dessous de l'OB
  OB_BEAR: close[i] > ob_top     # Le prix a cassé au-dessus de l'OB
```

### Confluence OB + FVG
```
Un OB dans un FVG est un signal plus fort :
  confluence_ob_fvg = OB_zone overlap FVG_zone
  
  Si confluence : score_de_confiance += CONFLUENCE_BONUS
  # CONFLUENCE_BONUS défini dans config/params.py avec justification
```

---

## 2.6 Liquidity Sweep (Sweep)

### Définition
Un liquidity sweep se produit quand le prix dépasse brièvement un niveau de liquidité (swing high/low, égal highs/lows) puis revient rapidement. C'est le signe que les institutions ont "chassé" les stops avant de reprendre le mouvement dans la direction opposée.

### Algorithme de détection

```
LIQUIDITY_SWEEP_HIGH :
  1. Identifier un niveau de liquidité au-dessus :
     niveau = swing_high_le_plus_proche OU égal_highs
   
  2. Le prix dépasse le niveau (mèche) :
     sweep = high[i] > niveau AND close[i] < niveau
     # La mèche dépasse, mais la clôture revient en-dessous
   
  3. Transition (Règle 3) :
     signal = sweep AND NOT sweep à [i-1]

LIQUIDITY_SWEEP_LOW :
  1. niveau = swing_low_le_plus_proche OU égal_lows
  2. sweep = low[i] < niveau AND close[i] > niveau
  3. signal = sweep AND NOT sweep à [i-1]
```

### Égaux Highs/Lows (Equal Highs/Lows)
```
EQUAL_HIGHS :
  Deux swing highs (ou plus) au même niveau (± tolérance)
  tolérance = ATR * EQUAL_TOLERANCE_ATR  # DYNAMIC
  # EQUAL_TOLERANCE_ATR = 0.1 (STRUCTURAL: 10% de l'ATR pour considérer "égal")

EQUAL_LOWS :
  Même logique pour les swing lows

Les niveaux de liquidité égaux sont PLUS susceptibles d'être sweepés
car les stops sont empilés au même niveau.
```

### Sweep + OB + FVG = Setup optimal
```
SETUP_OPTIMAL_LONG :
  1. Liquidity sweep low (chasse les stops en-dessous)
  2. Le prix revient dans un OB bull ou un FVG bull
  3. Le biais HTF est bullish

SETUP_OPTIMAL_SHORT :
  1. Liquidity sweep high (chasse les stops au-dessus)
  2. Le prix revient dans un OB bear ou un FVG bear
  3. Le biais HTF est bearish
```

---

## 2.7 Premium / Discount Zones

### Définition
Le concept de premium/discount divise le range entre un swing high et un swing low en zones. Les achats intelligents se font en zone discount (en-dessous de 50%), les ventes en zone premium (au-dessus de 50%).

### Calcul
```
range = swing_high - swing_low
equilibrium = swing_low + range * 0.5  # STRUCTURAL: 50% = équilibre

PREMIUM_ZONE   = prix > equilibrium  # Zone de vente (chers)
DISCOUNT_ZONE  = prix < equilibrium  # Zone d'achat (pas chers)

Plus précisément :
  Oblique (Fibonacci) :
  - Premium   : prix > 0.79 * range + swing_low  # DYNAMIC: 79% du range
  - Discount  : prix < 0.21 * range + swing_low  # DYNAMIC: 21% du range
  - Équilibre : entre 0.21 et 0.79
```

### Application
```
Un signal long en zone discount est PLUS FORT qu'un signal long en zone premium.
Un signal short en zone premium est PLUS FORT qu'un signal short en zone discount.

zone_score = 
  if signal_long AND prix en discount: +1
  if signal_long AND prix en premium: -1
  if signal_short AND prix en premium: +1
  if signal_short AND prix en discount: -1
```

---

## 2.8 Displacement

### Définition
Le displacement est un mouvement de prix fort et rapide qui indique la participation institutionnelle. C'est le mouvement qui CRÉE les FVG et les OB.

### Mesure
```
displacement = |close[i] - open[i]| / ATR

Si displacement >= DISPLACEMENT_MIN_ATR :  # DYNAMIC
  # DISPLACEMENT_MIN_ATR = 1.0 (STRUCTURAL: un displacement doit être au moins 1 ATR)
  → C'est un mouvement institutionnel significatif
  → Les FVG et OB créés pendant ce displacement sont plus pertinents
```

---

## 2.9 Market Structure Shift (MSS) — Synthèse

### Définition
Le MSS est la combinaison d'un CHOCH + un displacement. C'est le signal le plus fort de changement de tendance.

```
MSS_BULL :
  1. CHOCH_bull détecté (casse d'un swing high dans une tendance baissière)
  2. Le CHOCH est accompagné d'un displacement (bougie de BOS forte)
  3. Le biais HTF est aligned (bullish)

MSS_BEAR :
  1. CHOCH_bear détecté
  2. Displacement confirmé
  3. Biais HTF aligned (bearish)
```

---

# PARTIE III — ARCHITECTURE DÉTAILLÉE DU BOT

---

## 3.1 Vue d'ensemble du pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        PIPELINE LIVE                            │
│                                                                 │
│  1. DATA LAYER                                                  │
│     data/loader.py → data/validator.py → data/m1_builder.py    │
│                                                                 │
│  2. ANALYSIS LAYER                                              │
│     core/htf_bias.py (SEUL calcul biais HTF)                   │
│     core/structure.py (swings, BOS, CHOCH)                     │
│     core/fvg.py (FVG detection + iFVG)                         │
│     core/order_block.py (OB detection)                          │
│     core/liquidity.py (sweeps, equal H/L)                      │
│     core/displacement.py (mesure displacement)                  │
│     core/zones.py (premium/discount)                            │
│                                                                 │
│  3. SIGNAL LAYER                                                │
│     core/signal_detector.py (agrégation + confluence)           │
│     core/signal_types.py (types + SignalRegistry)               │
│                                                                 │
│  4. EXECUTION LAYER                                             │
│     core/sl_tp_calculator.py (SEUL calcul SL/TP)               │
│     core/position_sizer.py (SEULE taille de position)           │
│     core/risk_guard.py (SEULE vérification risque)             │
│     core/order_executor.py (exécution → appelle risk_guard)     │
│                                                                 │
│  5. MANAGEMENT LAYER                                            │
│     core/trade_manager.py (suivi des trades ouverts)            │
│     core/breakeven.py (déplacement à breakeven)                 │
│     core/partial_close.py (fermeture partielle)                 │
│                                                                 │
│  6. OPTIMIZATION LAYER                                          │
│     live/auto_optimize.py (auto-ajustement, Règle 7)           │
│     live/bot.py (point d'entrée)                                │
│                                                                 │
│  7. VALIDATION LAYER                                            │
│     backtest/engine.py (même modules core que le live)          │
│     backtest/walk_forward.py (split IS/OOS)                    │
│     backtest/metrics.py (métriques avec taille échantillon)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3.2 Structure des fichiers

```
dzedz/
├── CAHIER_DES_CHARGES_V2.md          ← Ce document
├── ARCHITECTURE.md                    ← Registre concepts → fonctions
├── README.md                          ← Guide du projet
│
├── config/
│   ├── __init__.py
│   ├── params.py                      ← Tous les paramètres (STRUCTURAL/DYNAMIC)
│   └── risk_config.py                 ← Config risque (Règle 5)
│
├── core/
│   ├── __init__.py
│   ├── signal_types.py                ← Types de signaux + SignalRegistry
│   ├── signal_detector.py             ← Agrégation + confluence
│   │
│   ├── htf_bias.py                    ← SEUL calcul biais HTF (Règle 1)
│   ├── structure.py                   ← Swings, BOS, CHOCH, MSS
│   ├── fvg.py                         ← FVG + iFVG detection
│   ├── order_block.py                 ← OB detection + validation
│   ├── liquidity.py                   ← Sweeps + equal H/L
│   ├── displacement.py                ← Mesure displacement
│   ├── zones.py                       ← Premium/Discount zones
│   │
│   ├── sl_tp_calculator.py            ← SEUL calcul SL/TP (Règle 1)
│   ├── position_sizer.py              ← SEULE taille position (Règle 1)
│   ├── risk_guard.py                  ← SEULE vérification risque (Règle 5)
│   ├── order_executor.py              ← Exécution (appelle risk_guard)
│   │
│   ├── trade_manager.py               ← Suivi trades ouverts
│   ├── breakeven.py                   ← Déplacement breakeven
│   ├── partial_close.py              ← Fermeture partielle
│   └── confluence.py                  ← Score de confluence
│
├── data/
│   ├── __init__.py
│   ├── loader.py                      ← Chargement données M1
│   ├── validator.py                   ← Validation intégrité
│   └── m1_builder.py                  ← Construction M1 si seulement M5 dispo
│
├── backtest/
│   ├── __init__.py
│   ├── engine.py                      ← Moteur (même modules core que live)
│   ├── walk_forward.py                ← Walk-forward IS/OOS
│   └── metrics.py                     ← Métriques + taille échantillon
│
├── live/
│   ├── __init__.py
│   ├── bot.py                         ← Point d'entrée live
│   └── auto_optimize.py              ← Auto-ajustement (Règle 7)
│
├── tests/
│   ├── __init__.py
│   ├── test_signal_dedup.py           ← Règle 3
│   ├── test_risk_guard.py             ← Règle 5
│   ├── test_no_silent_except.py       ← Règle 6
│   ├── test_magic_numbers.py          ← Règle 4
│   ├── test_dead_code.py             ← Règle 2
│   ├── test_structure.py             ← BOS/CHOCH detection
│   ├── test_fvg.py                   ← FVG/iFVG detection
│   ├── test_liquidity.py             ← Sweep detection
│   └── test_order_block.py           ← OB detection
│
├── scripts/
│   ├── check_silent_except.py         ← Linter Règle 6
│   ├── check_magic_numbers.py         ← Linter Règle 4
│   └── check_dead_code.py            ← Linter Règle 2
│
└── logs/                              ← Logs structurés (jamais silencieux)
```

---

## 3.3 Registre des concepts → fonctions responsables (Règle 1)

| Concept | Fonction responsable | Fichier | Appelé par |
|---------|---------------------|---------|------------|
| Biais HTF | `get_htf_bias()` | `core/htf_bias.py` | `signal_detector.py` |
| Swings | `detect_swings()` | `core/structure.py` | `structure.py`, `liquidity.py` |
| BOS | `detect_bos()` | `core/structure.py` | `signal_detector.py` |
| CHOCH | `detect_choch()` | `core/structure.py` | `signal_detector.py` |
| FVG | `detect_fvg()` | `core/fvg.py` | `signal_detector.py` |
| iFVG | `check_fvg_filled()` | `core/fvg.py` | `fvg.py` (auto-mise à jour) |
| Order Block | `detect_ob()` | `core/order_block.py` | `signal_detector.py` |
| Liquidity Sweep | `detect_sweep()` | `core/liquidity.py` | `signal_detector.py` |
| Equal H/L | `detect_equal_levels()` | `core/liquidity.py` | `liquidity.py` |
| Displacement | `measure_displacement()` | `core/displacement.py` | `structure.py`, `signal_detector.py` |
| Premium/Discount | `get_zone()` | `core/zones.py` | `signal_detector.py` |
| Calcul SL/TP | `calculate_sl_tp()` | `core/sl_tp_calculator.py` | `order_executor.py` |
| Taille position | `calculate_position_size()` | `core/position_sizer.py` | `order_executor.py` |
| Vérification risque | `validate_risk()` | `core/risk_guard.py` | `order_executor.py` |
| Exécution ordre | `execute_order()` | `core/order_executor.py` | `bot.py` |
| Confluence | `compute_confluence_score()` | `core/confluence.py` | `signal_detector.py` |
| Auto-optimisation | `auto_optimize()` | `live/auto_optimize.py` | `bot.py` |

---

# PARTIE IV — CALCUL DU SL/TP : DÉTAIL COMPLET

---

## 4.1 Principe fondamental

Le SL/TP est calculé UNIQUEMENT par `calculate_sl_tp()` dans `core/sl_tp_calculator.py`. Il n'y a JAMAIS de fonction alternative.

## 4.2 Calcul du SL

### SL pour un trade LONG

```
SL_long = min(
    niveau_de_liquidité_sous_le_prix,  # Swing low le plus proche
    bord_inférieur_du_FVG_le_plus_proche,  # Si FVG actif en-dessous
    bord_inférieur_de_l_OB_le_plus_proche,  # Si OB actif en-dessous
) - buffer

buffer = ATR * SL_BUFFER_ATR  # DYNAMIC
# SL_BUFFER_ATR = 0.1 (STRUCTURAL: 10% de l'ATR pour le buffer de spread)
```

### SL pour un trade SHORT

```
SL_short = max(
    niveau_de_liquidité_au_dessus_du_prix,  # Swing high le plus proche
    bord_supérieur_du_FVG_le_plus_proche,
    bord_supérieur_de_l_OB_le_plus_proche,
) + buffer
```

### Priorité des niveaux de SL

```
1. Si le setup est un liquidity sweep → SL derrière le niveau sweepé
   SL = niveau_sweepé ± buffer

2. Si le setup est un OB entry → SL derrière l'OB
   SL = bord_opposé_de_l_OB ± buffer

3. Si le setup est un FVG entry → SL derrière le FVG
   SL = bord_opposé_du_FVG ± buffer

4. Fallback → SL basé sur l'ATR
   SL = entry ± ATR * SL_DEFAULT_ATR_MULTIPLIER
   # SL_DEFAULT_ATR_MULTIPLIER = 1.5 (STRUCTURAL: 1.5 ATR = SL par défaut raisonnable)
```

## 4.3 Calcul du TP

### TP pour un trade LONG

```
TP_long = max(
    niveau_de_liquidité_au_dessus_du_prix,  # Swing high / equal highs
    bord_supérieur_du_FVG_opposé,  # FVG bear en zone de target
    objectif_Fibonacci,
)

Objectif Fibonacci :
  range = swing_high_récent - swing_low_récent
  TP_fib_1 = swing_low + range * 1.0   # 100% (même niveau)
  TP_fib_2 = swing_low + range * 1.618  # Extension 1.618 (STRUCTURAL)
  TP_fib_3 = swing_low + range * 2.618  # Extension 2.618 (STRUCTURAL)
```

### TP pour un trade SHORT

```
TP_short = min(
    niveau_de_liquidité_en_dessous,
    bord_inférieur_du_FVG_opposé,
    objectif_Fibonacci,
)
```

### Règle Risk/Reward minimum

```
RR = |TP - entry| / |entry - SL|

Si RR < RR_MINIMUM :  # DYNAMIC
  # RR_MINIMUM = 1.5 (STRUCTURAL: en dessous de 1:1.5, le setup n'est pas viable)
  → REJETER le trade (pas de compromis)
  → logger.warning(f"TRADE_REJECTED | reason=rr_below_minimum | rr={RR}")
```

---

# PARTIE V — GESTION DU RISQUE : DÉTAIL COMPLET

---

## 5.1 Calcul de la taille de position

```
risk_amount = capital * (MAX_RISK_PER_TRADE_PCT / 100)
sl_distance_pips = |entry - SL| / PIP_SIZE
lot_size = risk_amount / (sl_distance_pips * PIP_VALUE_PER_LOT)

Où :
  PIP_SIZE = 0.0001 (STRUCTURAL: 5-digit pricing pour la plupart des paires)
  PIP_VALUE_PER_LOT = dépend du symbole (ex: ~10$ pour EURUSD)
```

## 5.2 Vérification de risque (validate_risk)

```
Entrée : capital, entry, SL, lot_size, setup_grade

1. Calculer le risque :
   risk_pips = |entry - SL| / PIP_SIZE
   risk_dollars = risk_pips * PIP_VALUE_PER_LOT * lot_size
   risk_pct = (risk_dollars / capital) * 100

2. Vérifier le plafond absolu :
   SI risk_pct > ABSOLUTE_MAX_RISK_PCT (5%):
     → REJETER (RiskValidationError)
     → Aucune exception, même pour Grade S

3. Vérifier le plafond normal :
   SI risk_pct > MAX_RISK_PER_TRADE_PCT (1%):
     → Réduire le lot_size
     → adjusted_lot = (capital * MAX_RISK_PER_TRADE_PCT / 100) / (risk_pips * PIP_VALUE_PER_LOT)
     → SI adjusted_lot < MIN_LOT_SIZE:
       → REJETER (lot minimum forcé ne passe pas la vérification)
     → LOG: "RISK_ADJUST | before={lot_size} | after={adjusted_lot}"

4. Retourner le lot validé
```

## 5.3 Gestion du trade en cours

### Breakeven
```
Quand le prix atteint BE_TRIGGER_ATR * ATR dans le sens du trade :
  → Déplacer le SL à l'entry price (breakeven)
  → BE_TRIGGER_ATR = 1.0 (STRUCTURAL: 1 ATR de profit avant breakeven)
  
  LOG: "BE_MOVED | entry={entry} | new_sl={entry} | profit_atr={current_atr}"
```

### Partial Close
```
Quand le prix atteint TP1 (50% du TP) :
  → Fermer PARTIAL_CLOSE_PCT du trade
  → Déplacer le SL à breakeven
  → PARTIAL_CLOSE_PCT = 0.5 (STRUCTURAL: 50% de la position)
  → Le reste du trade roule vers TP2 avec un trailing stop
```

### Trailing Stop
```
Après breakeven + partial close :
  trail = ATR * TRAIL_ATR_MULTIPLIER
  # TRAIL_ATR_MULTIPLIER = 1.0 (STRUCTURAL: trailing à 1 ATR)
  
  new_sl = max(current_sl, high - trail)  # Pour un long
  new_sl = min(current_sl, low + trail)   # Pour un short
  
  Chaque ajustement du SL est LOGUÉ (Règle 1 : couche successive)
```

---

# PARTIE VI — SCORE DE CONFLUENCE

---

## 6.1 Principe

Chaque signal a un score de confluence qui mesure la qualité du setup. Plus le score est élevé, plus le setup est fiable. **Le score N'AUTORISE JAMAIS à contourner le risk_guard** (Règle 5).

## 6.2 Composantes du score

```
confluence_score = 0

# Biais HTF aligné
if signal_direction == htf_bias:
    confluence_score += HTF_BIAS_WEIGHT  # STRUCTURAL: justifié dans params.py

# Zone premium/discount
if signal_long AND prix en discount:
    confluence_score += ZONE_WEIGHT
if signal_short AND prix en premium:
    confluence_score += ZONE_WEIGHT

# FVG actif
if fvg_in_zone:
    confluence_score += FVG_WEIGHT

# OB actif
if ob_in_zone:
    confluence_score += OB_WEIGHT

# Liquidity sweep
if sweep_detected:
    confluence_score += SWEEP_WEIGHT

# Displacement
if displacement >= DISPLACEMENT_MIN_ATR:
    confluence_score += DISPLACEMENT_WEIGHT

# BOS/CHOCH récent
if bos_or_choch_recent:
    confluence_score += STRUCTURE_WEIGHT
```

## 6.3 Seuil de confluence

```
CONFLUENCE_MINIMUM = 2  # STRUCTURAL: en dessous de 2, le setup n'a pas assez de confluences

Si confluence_score < CONFLUENCE_MINIMUM:
  → REJETER le signal (pas assez de confluences)
  → logger.info(f"SIGNAL_REJECTED | reason=low_confluence | score={score}")
```

## 6.4 Le score NE BYPASSE PAS le risque

```
⚠️ IMPORTANT : le score de confluence influence UNIQUEMENT la décision
d'entrer ou non dans le trade. Il n'affecte JAMAIS :
  - La taille de position
  - Le SL/TP
  - Le risque maximum par trade

Même un setup avec confluence_score = 10 (maximum) passe par validate_risk()
avec les mêmes plafonds qu'un setup confluence_score = 2.
```

---

# PARTIE VII — PROTOCOLE DE VALIDATION (WALK-FORWARD)

---

## 7.1 Données requises

```
Timeframe : M1 (obligatoire pour ICT)
Volume : réel (pas synthétique)
Période : minimum 1 an, idéal 3+ ans
Paires : EURUSD, GBPUSD, USDJPY minimum (liquidité suffisante)
```

## 7.2 Processus de walk-forward

```
1. Diviser les données en N fenêtres (défaut: 5)
2. Pour chaque fenêtre :
   a. Split IS/OOS (60/40)
   b. Optimiser les paramètres sur IS
   c. Tester sur OOS SANS AJUSTEMENT
   d. Enregistrer les métriques IS et OOS

3. Vérification :
   - IS_trades >= 200 par fenêtre
   - OOS_trades >= 100 par fenêtre
   - Dégradation OOS vs IS < 30%
   - Si dégradation > 30% → paramètre REJETÉ

4. Résultat final :
   - Moyenne des performances OOS sur toutes les fenêtres
   - Si un seul paramètre est rejeté sur une fenêtre → revoir le paramètre
```

## 7.3 Métriques obligatoires

```
Pour chaque fenêtre IS/OOS :
  - Nombre de trades
  - Win rate
  - PnL total
  - Max drawdown
  - Sharpe ratio
  - Average RR
  - Durée moyenne des trades
  - Profit factor
```

## 7.4 Critère de rejet

```
Un paramètre est REJETÉ si :
  - OOS win rate < IS win rate * (1 - OOS_DEGRADATION_REJECT_THRESHOLD)
  - OOS profit factor < 1.0 (perte sur le hors-échantillon)
  - OOS_trades < 100
  - Le même paramètre est rejeté sur >50% des fenêtres
```

---

# PARTIE VIII — PROCESS DE DÉVELOPPEMENT

---

## 8.1 Ordre de développement (obligatoire)

```
Phase 1 : Fondations
  1. config/params.py — tous les paramètres justifiés
  2. core/signal_types.py — types + SignalRegistry
  3. core/risk_guard.py — verrou risque
  4. tests/ pour les 3 modules ci-dessus

Phase 2 : Détection de structure
  5. core/structure.py — swings, BOS, CHOCH
  6. tests/test_structure.py
  7. core/htf_bias.py — biais HTF
  8. tests/test_htf_bias.py

Phase 3 : Concepts ICT
  9. core/fvg.py — FVG + iFVG
  10. tests/test_fvg.py
  11. core/order_block.py — OB
  12. tests/test_order_block.py
  13. core/liquidity.py — sweeps + equal H/L
  14. tests/test_liquidity.py
  15. core/displacement.py — mesure
  16. core/zones.py — premium/discount

Phase 4 : Signal et exécution
  17. core/confluence.py — score de confluence
  18. core/signal_detector.py — agrégation
  19. core/sl_tp_calculator.py — calcul SL/TP
  20. core/position_sizer.py — taille de position
  21. core/order_executor.py — exécution

Phase 5 : Backtest
  22. data/loader.py + validator.py
  23. backtest/engine.py
  24. backtest/walk_forward.py
  25. backtest/metrics.py

Phase 6 : Live
  26. core/trade_manager.py
  27. core/breakeven.py
  28. core/partial_close.py
  29. live/bot.py
  30. live/auto_optimize.py
```

**Règle : chaque module est testé AVANT de passer au suivant.**

## 8.2 Convention de commit

```
feat: add FVG detection algorithm
fix: correct swing detection with lookback=3
refactor: extract premium/discount into zones.py
remove: delete old apply_dynamic_sl (replaced by sl_tp_calculator)
test: add FVG deduplication tests (Règle 3)
docs: update ARCHITECTURE.md with new concept
```

## 8.3 Convention de logging

```
TOUS les logs suivent ce format structuré :
  MODULE | ACTION | key=value | key=value

Exemples :
  RISK_GUARD | RISK_OK | lot=0.05 | risk_pct=0.8% | symbol=EURUSD
  SL_TP_CALC | SL_ADJUST | layer=broker | before=1.0990 | after=1.0988 | reason=min_distance
  FVG_DETECT | FVG_BULL | top=1.1050 | bottom=1.1045 | size_atr=0.5 | index=15234
  SIGNAL_DETECTED | type=liquidity_sweep_low | direction=long | confluence=4 | index=15234
  ORDER_SENT | symbol=EURUSD | direction=long | entry=1.1045 | sl=1.1020 | tp=1.1095 | lot=0.05
```

---

# PARTIE IX — CHECKLIST DE DÉMARRAGE

---

À cocher avec l'IA AVANT d'écrire le premier module de trading :

- [ ] Dépôt git initialisé ✅
- [ ] Format de données historiques confirmé (M1 réel disponible, pas seulement M5)
- [ ] Un seul module de calcul de SL/TP prévu dès l'architecture
- [ ] Le plafond de risque par trade est défini une fois, dans un seul fichier de config, avec une valeur raisonnable (≤5%)
- [ ] Le protocole de validation (walk-forward, taille d'échantillon minimum, split IS/OOS) est écrit avant le premier backtest
- [ ] L'ordre de développement (Phase 1→6) est accepté et respecté
- [ ] Le format de logging structuré est défini
- [ ] Les 9 règles sont lues et acceptées

---

# PARTIE X — PARAMÈTRES COMPLETS (config/params.py)

---

```python
# =============================================================================
# RISQUE — Règle 5
# =============================================================================
MAX_RISK_PER_TRADE_PCT = 1.0       # STRUCTURAL: 1% du capital par trade
ABSOLUTE_MAX_RISK_PCT = 5.0        # STRUCTURAL: plafond absolu jamais dépassé
MIN_LOT_SIZE = 0.01                 # STRUCTURAL: minimum broker
PIP_SIZE = 0.0001                   # STRUCTURAL: 5-digit pricing
PIP_VALUE_PER_LOT_EURUSD = 10.0    # STRUCTURAL: ~$10 par pip par lot standard EURUSD

# =============================================================================
# SL/TP
# =============================================================================
SL_BUFFER_ATR = 0.1                 # STRUCTURAL: 10% ATR buffer pour spread
SL_DEFAULT_ATR_MULTIPLIER = 1.5    # STRUCTURAL: SL par défaut = 1.5 ATR
RR_MINIMUM = 1.5                    # STRUCTURAL: RR minimum 1:1.5
BE_TRIGGER_ATR = 1.0               # STRUCTURAL: breakeven après 1 ATR de profit
PARTIAL_CLOSE_PCT = 0.5            # STRUCTURAL: 50% de la position à TP1
TRAIL_ATR_MULTIPLIER = 1.0         # STRUCTURAL: trailing à 1 ATR

# =============================================================================
# FVG
# =============================================================================
FVG_MIN_ATR_MULTIPLIER = 0.3       # STRUCTURAL: FVG < 0.3 ATR = bruit
FVG_MAX_AGE_MULTIPLIER = 3.0       # STRUCTURAL: FVG trop vieux après 3x période ATR
ATR_PERIOD = 14                     # STRUCTURAL: convention standard ATR

# =============================================================================
# ORDER BLOCK
# =============================================================================
OB_MIN_MOVE_ATR = 1.5              # STRUCTURAL: OB doit montrer un mouvement > 1.5 ATR

# =============================================================================
# LIQUIDITY
# =============================================================================
EQUAL_TOLERANCE_ATR = 0.1          # STRUCTURAL: 10% ATR pour considérer "égal"

# =============================================================================
# DISPLACEMENT
# =============================================================================
DISPLACEMENT_MIN_ATR = 1.0         # STRUCTURAL: displacement > 1 ATR = significatif

# =============================================================================
# CONFLUENCE
# =============================================================================
HTF_BIAS_WEIGHT = 1                # STRUCTURAL: biais HTF aligné = +1
ZONE_WEIGHT = 1                    # STRUCTURAL: zone premium/discount = +1
FVG_WEIGHT = 1                     # STRUCTURAL: FVG actif = +1
OB_WEIGHT = 1                      # STRUCTURAL: OB actif = +1
SWEEP_WEIGHT = 2                   # STRUCTURAL: sweep détecté = +2 (plus important)
DISPLACEMENT_WEIGHT = 1            # STRUCTURAL: displacement = +1
STRUCTURE_WEIGHT = 1               # STRUCTURAL: BOS/CHOCH récent = +1
CONFLUENCE_MINIMUM = 2             # STRUCTURAL: minimum 2 confluences pour entrer

# =============================================================================
# STRUCTURE
# =============================================================================
SWING_LOOKBACK = 3                 # STRUCTURAL: 3 bougies de chaque côté pour confirmer un swing
SWING_CONFIRM_BARS = 3             # STRUCTURAL: 3 bougies sans dépassement pour confirmer

# =============================================================================
# VALIDATION — Règle 7
# =============================================================================
MIN_TRADES_FOR_VALIDATION = 200    # STRUCTURAL: en dessous = pas significatif
MIN_OOS_TRADES = 100               # STRUCTURAL: minimum pour OOS
IS_OOS_SPLIT_RATIO = 0.6           # STRUCTURAL: 60% IS / 40% OOS
OOS_DEGRADATION_REJECT_THRESHOLD = 0.30  # STRUCTURAL: >30% dégradation = rejet
WALK_FORWARD_WINDOWS = 5           # STRUCTURAL: 5 fenêtres walk-forward

# =============================================================================
# DONNÉES
# =============================================================================
HISTORICAL_TIMEFRAME = "M1"        # STRUCTURAL: ICT nécessite M1
MIN_HISTORY_YEARS = 1              # STRUCTURAL: minimum 1 an
IDEAL_HISTORY_YEARS = 3            # STRUCTURAL: idéal 3 ans
```

---

*Document vivant — à mettre à jour si de nouveaux bugs sont découverts pendant le développement de la v2. Chaque ajout doit être un commit avec justification.*
