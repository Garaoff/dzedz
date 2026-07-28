# dzedz — Bot SMC/ICT v2 (from scratch)

## Reconstruction depuis zéro avec les lessons learned

Ce projet est une reconstruction complète du bot SMC/ICT, repartant de zéro avec 9 règles de conception explicites, chacune dérivée d'un bug réel de la v1.

## Documents fondateurs

- **[CAHIER_DES_CHARGES_V2.md](CAHIER_DES_CHARGES_V2.md)** — Document ULTIME (10 parties : 9 règles, concepts ICT détaillés, architecture, SL/TP, risque, confluence, validation, process, checklist, params)
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Registre des concepts → fonctions responsables (Règle 1)

## Architecture

```
dzedz/
├── CAHIER_DES_CHARGES_V2.md      ← Document fondateur ULTIME
├── ARCHITECTURE.md                ← Registre concepts → fonctions
│
├── config/                        ← Paramètres justifiés (Règle 4)
│   ├── params.py                  ← Tous les paramètres (STRUCTURAL/DYNAMIC)
│   └── risk_config.py             ← Configuration risque (Règle 5)
│
├── core/                          ← Modules cœur (une seule source par concept)
│   ├── signal_types.py            ← Types + SignalRegistry (Règle 3)
│   ├── signal_detector.py         ← Agrégation + transition (Règle 1, 3)
│   │
│   ├── htf_bias.py                ← SEUL biais HTF (Règle 1)
│   ├── structure.py               ← Swings, BOS, CHOCH, MSS (Règle 1)
│   ├── fvg.py                     ← FVG + iFVG (Règle 1)
│   ├── order_block.py             ← OB + invalidation (Règle 1)
│   ├── liquidity.py               ← Sweeps + equal H/L (Règle 1)
│   ├── displacement.py            ← Mesure displacement (Règle 1)
│   ├── zones.py                   ← Premium/Discount (Règle 1)
│   │
│   ├── confluence.py              ← Score confluence (NE BYPASSE PAS risque)
│   ├── sl_tp_calculator.py        ← SEUL SL/TP (Règle 1)
│   ├── position_sizer.py          ← SEULE taille position (Règle 1)
│   ├── risk_guard.py              ← SEULE vérification risque (Règle 5)
│   ├── order_executor.py          ← Exécution (appelle risk_guard)
│
├── data/                          ← Chargement/validation données
│   ├── loader.py                  ← Données M1 (Règle 7)
│   ├── validator.py               ← Intégrité données
│
├── backtest/                      ← Backtest et walk-forward
│   ├── engine.py                  ← Même modules core que live
│   ├── walk_forward.py            ← Split IS/OOS (Règle 7)
│   ├── metrics.py                 ← Métriques + taille échantillon
│
├── live/                          ← Pipeline live
│   ├── bot.py                     ← Point d'entrée
│   ├── auto_optimize.py           ← Auto-ajustement (Règle 7)
│
├── tests/                         ← Tests (garde-fous pour chaque règle)
├── scripts/                       ← Linters (Règles 4, 6)
└── logs/                          ← Logs structurés
```

## Les 9 règles

1. **Une seule source de vérité** — pas 5 fonctions de SL/TP
2. **Pas de fonction non branchée** — chaque fonction live est appelée dans le pipeline
3. **Transition, pas état** — signal sur changement, pas sur état persistant
4. **Pas de nombre en dur** sans justification STRUCTURAL ou DYNAMIC
5. **Un seul verrou risque** — aucun bypass, même pour Grade S
6. **Pas de except:pass** — tout échec est logué
7. **Échantillon minimum** — 200 trades, IS/OOS, pas de petit sample
8. **Git, pas scripts patch** — chaque changement est un commit
9. **Chiffres bruts** pour l'audit, pas de conclusions générales

## Concepts SMC/ICT implémentés

| Concept | Module | Algorithme |
|---------|--------|------------|
| Biais HTF | `htf_bias.py` | Structure + position prix |
| Swings | `structure.py` | lookback=3, confirmation=3 |
| BOS | `structure.py` | Close > dernier swing high (transition) |
| CHOCH | `structure.py` | Close > swing high contre tendance (transition) |
| FVG | `fvg.py` | low[i-1] > high[i+1] (bull), filtrage ATR |
| iFVG | `fvg.py` | Prix traverse le gap → retiré |
| Order Block | `order_block.py` | Dernière bougie bear/bull avant displacement > 1.5 ATR |
| OB invalidé | `order_block.py` | Close traverse la zone OB |
| Liquidity | `liquidity.py` | Swings + equal H/L (± 10% ATR) |
| Sweep | `liquidity.py` | Mèche dépasse niveau + close revient (transition) |
| Displacement | `displacement.py` | |close - open| / ATR |
| Zones | `zones.py` | Premium > 79%, Discount < 21% du range |
| Confluence | `confluence.py` | Score = somme des poids (min 2 pour entrer) |

## Linters

```bash
python scripts/check_silent_except.py   # Règle 6
python scripts/check_magic_numbers.py   # Règle 4
python scripts/check_dead_code.py       # Règle 2
```

## Tests

```bash
pytest tests/ -v                        # 16 tests (règles 2,3,4,5,6)
```

## Checklist de démarrage

- [x] Dépôt git initialisé
- [x] Format M1 confirmé dans params
- [x] Un seul module SL/TP
- [x] Plafond risque ≤15% dans config/risk_config.py
- [x] Protocole de validation défini (walk-forward, 200 trades min, IS/OOS)
- [ ] Données M1 réelles chargées et validées
- [ ] Premiers tests de détection sur données réelles

## Réflexe permanent

> Demander des chiffres bruts et du code à l'appui plutôt que des affirmations. Tester chaque brique avant de l'empiler sur la suivante.
