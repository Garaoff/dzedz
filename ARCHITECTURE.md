# Architecture — Bot SMC/ICT v2

## Registre des concepts → fonctions responsables

> **Règle 1** : Pour chaque concept, UNE SEULE fonction est autoritaire.
> Toute modification de ce registre doit être un commit avec justification.

| Concept | Fonction responsable | Fichier | Appelé par | Statut |
|---------|---------------------|---------|------------|--------|
| Biais HTF | `get_htf_bias()` | `core/htf_bias.py` | `signal_detector.py` | ✅ Implémenté |
| Swings | `detect_swings()` | `core/structure.py` | `structure.py`, `liquidity.py`, `zones.py` | ✅ Implémenté |
| BOS | `detect_bos()` | `core/structure.py` | `signal_detector.py` | ✅ Implémenté |
| CHOCH | `detect_choch()` | `core/structure.py` | `signal_detector.py` | ✅ Implémenté |
| Tendance | `determine_trend()` | `core/structure.py` | `htf_bias.py`, `signal_detector.py` | ✅ Implémenté |
| FVG | `detect_fvg()` | `core/fvg.py` | `signal_detector.py` | ✅ Implémenté |
| iFVG (FVG fillé) | `check_fvg_filled()` | `core/fvg.py` | `fvg.py` (auto-update) | ✅ Implémenté |
| Order Block | `detect_ob()` | `core/order_block.py` | `signal_detector.py` | ✅ Implémenté |
| OB invalidation | `check_ob_invalidated()` | `core/order_block.py` | `order_block.py` (auto-update) | ✅ Implémenté |
| Liquidity Levels | `detect_liquidity_levels()` | `core/liquidity.py` | `liquidity.py`, `signal_detector.py` | ✅ Implémenté |
| Equal H/L | `detect_equal_levels()` | `core/liquidity.py` | `liquidity.py` | ✅ Implémenté |
| Liquidity Sweep | `detect_sweep()` | `core/liquidity.py` | `signal_detector.py` | ✅ Implémenté |
| Displacement | `measure_displacement()` | `core/displacement.py` | `signal_detector.py` | ✅ Implémenté |
| Premium/Discount | `get_zone()` | `core/zones.py` | `signal_detector.py` | ✅ Implémenté |
| Confluence | `compute_confluence_score()` | `core/confluence.py` | `signal_detector.py` | ✅ Implémenté |
| Calcul SL/TP | `calculate_sl_tp()` | `core/sl_tp_calculator.py` | `order_executor.py` | ✅ Implémenté |
| Taille position | `calculate_position_size()` | `core/position_sizer.py` | `order_executor.py` | ✅ Implémenté |
| Vérification risque | `validate_risk()` | `core/risk_guard.py` | `order_executor.py` | ✅ Implémenté |
| Exécution ordre | `execute_order()` | `core/order_executor.py` | `bot.py` | ✅ Implémenté |
| Auto-optimisation | `auto_optimize()` | `live/auto_optimize.py` | `bot.py` | ⬜ TODO |

## Couches de modification

Si une couche successive modifie la sortie d'une fonction responsable, elle DOIT logger :

```
logger.info(f"SL_ADJUST | layer=broker_constraint | before={sl_before} | after={sl_after} | reason=broker_min_distance")
```

## Flux de données (pipeline live)

```
data/loader.py → data/validator.py
        ↓
core/htf_bias.py → "bullish"/"bearish"/"neutral"
        ↓
core/structure.py → detect_swings() → detect_bos()/detect_choch()
core/fvg.py → detect_fvg() → check_fvg_filled()
core/order_block.py → detect_ob() → check_ob_invalidated()
core/liquidity.py → detect_liquidity_levels() → detect_sweep()
core/displacement.py → measure_displacement()
core/zones.py → get_zone()
        ↓
core/confluence.py → compute_confluence_score()
        ↓
core/signal_detector.py → agrégation + transition (Règle 3)
        ↓
core/sl_tp_calculator.py → SL/TP (SEULE source, Règle 1)
core/position_sizer.py → taille (SEULE source, Règle 1)
        ↓
core/risk_guard.py → validate_risk() (VERROU, Règle 5)
        ↓
core/order_executor.py → execute_order()
```

Aucun ordre ne peut être envoyé sans passer par `risk_guard.py`.
Aucune fonction ne peut calculer un SL/TP en dehors de `sl_tp_calculator.py`.
Aucune fonction ne peut déterminer le biais HTF en dehors de `htf_bias.py`.

## Flux de données (backtest)

```
data/loader.py → data/validator.py → backtest/engine.py
                                          ↓
                                    backtest/walk_forward.py
                                          ↓
                                    backtest/metrics.py
```

Le backtest utilise les MÊMES modules core que le live.
Si un module se comporte différemment en backtest vs live, c'est un bug.

## ⚠️ Score de confluence NE BYPASSE PAS le risque

Le score de confluence (`compute_confluence_score()`) influence UNIQUEMENT la décision
d'entrer ou non dans un trade. Il n'affecte JAMAIS :
- La taille de position
- Le SL/TP
- Le risque maximum par trade

Même un setup confluence_score=10 passe par `validate_risk()` avec les mêmes
plafonds qu'un setup confluence_score=2. (Règle 5)
