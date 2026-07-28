"""
Score de confluence — Bot SMC/ICT v2 — HIÉRARCHIE ICT COMPLÈTE.

RÈGLE 1 : compute_confluence_score() est la SEULE fonction.
RÈGLE 4 : Tous les poids depuis config avec justification.
RÈGLE 5 : Le score NE BYPASSE PAS le risque (explicitement documenté).

ICT Hiérarchie des concepts (du plus puissant au moins puissant) :
1. MSS (CHOCH + Displacement + FVG) = signal ICT LE PLUS PUISSANT (poids 3)
2. Sweep + Killzone = filtration temporelle + liquidité (poids 2)
3. Zone + OB/FVG + PO3 = confirmation structurelle (poids 1)
4. HTF bias = contexte macro (poids 1)
5. Breaker/PDHL = avancé (poids 1)

Un setup Silver Bullet (Killzone + MSS + FVG + Sweep) atteint
automatiquement un score élevé car il combine les concepts les
plus puissants dans la hiérarchie ICT.
"""

import logging
from typing import Optional

from config.params import (
    HTF_BIAS_WEIGHT,
    ZONE_WEIGHT,
    FVG_WEIGHT,
    OB_WEIGHT,
    SWEEP_WEIGHT,
    DISPLACEMENT_WEIGHT,
    STRUCTURE_WEIGHT,
    MSS_WEIGHT,
    KILLZONE_WEIGHT,
    PO3_WEIGHT,
    BREAKER_WEIGHT,
    PDHL_WEIGHT,
    CONFLUENCE_MINIMUM,
)

logger = logging.getLogger(__name__)


def compute_confluence_score(
    htf_bias_aligned: bool,
    zone_favorable: bool,
    fvg_present: bool,
    ob_present: bool,
    sweep_present: bool,
    displacement_significant: bool,
    structure_aligned: bool,
    # === Nouveaux concepts ICT v2 ===
    mss_present: bool = False,  # MSS (CHOCH + Displacement + FVG)
    killzone_active: bool = False,  # Killzone ICT active
    po3_distribution: bool = False,  # PO3 phase distribution
    breaker_present: bool = False,  # Breaker Block actif
    pdhl_aligned: bool = False,  # PDHL (Previous Day/Week High/Low) aligné
) -> dict:
    """
    Calcule le score de confluence d'un setup.
    
    RÈGLE 1 : C'EST LA SEULE fonction qui calcule la confluence.
    
    ⚠️ IMPORTANT : le score de confluence influence UNIQUEMENT la décision
    d'entrer ou non. Il n'affecte JAMAIS :
      - La taille de position
      - Le SL/TP
      - Le risque maximum par trade
    
    Même un setup confluence_score=10 passe par validate_risk() avec les
    mêmes plafonds qu'un setup confluence_score=2.
    
    Args:
        htf_bias_aligned: Biais HTF aligné avec la direction du trade
        zone_favorable: Prix en zone favorable (discount pour long, premium pour short)
        fvg_present: FVG actif dans la zone d'entrée
        ob_present: OB actif dans la zone d'entrée
        sweep_present: Liquidity sweep détecté
        displacement_significant: Displacement >= DISPLACEMENT_MIN_ATR
        structure_aligned: BOS/CHOCH récent aligné
        mss_present: MSS (CHOCH + Displacement + FVG) détecté — ICT signal optimal
        killzone_active: Killzone ICT active (London/NY)
        po3_distribution: PO3 phase distribution (moment d'entrer)
        breaker_present: Breaker Block actif dans la zone d'entrée
        pdhl_aligned: PDHL aligné avec la direction
    
    Returns:
        dict avec score, breakdown, et is_eligible
    """
    score = 0
    breakdown = {}
    
    # === Concepts ICT originaux ===
    
    # HTF Bias (STRUCTURAL: poids = 1 — contexte macro)
    if htf_bias_aligned:
        score += HTF_BIAS_WEIGHT
        breakdown["htf_bias"] = HTF_BIAS_WEIGHT
    else:
        breakdown["htf_bias"] = 0
    
    # Zone (STRUCTURAL: poids = 1 — confirmation structurelle)
    if zone_favorable:
        score += ZONE_WEIGHT
        breakdown["zone"] = ZONE_WEIGHT
    else:
        breakdown["zone"] = 0
    
    # FVG (STRUCTURAL: poids = 1 — déséquilibre)
    if fvg_present:
        score += FVG_WEIGHT
        breakdown["fvg"] = FVG_WEIGHT
    else:
        breakdown["fvg"] = 0
    
    # OB (STRUCTURAL: poids = 1 — zone institutionnelle)
    if ob_present:
        score += OB_WEIGHT
        breakdown["ob"] = OB_WEIGHT
    else:
        breakdown["ob"] = 0
    
    # Sweep (STRUCTURAL: poids = 2 — liquidité chassée = important)
    if sweep_present:
        score += SWEEP_WEIGHT
        breakdown["sweep"] = SWEEP_WEIGHT
    else:
        breakdown["sweep"] = 0
    
    # Displacement (STRUCTURAL: poids = 1 — force du mouvement)
    if displacement_significant:
        score += DISPLACEMENT_WEIGHT
        breakdown["displacement"] = DISPLACEMENT_WEIGHT
    else:
        breakdown["displacement"] = 0
    
    # Structure (STRUCTURAL: poids = 1 — BOS/CHOCH)
    if structure_aligned:
        score += STRUCTURE_WEIGHT
        breakdown["structure"] = STRUCTURE_WEIGHT
    else:
        breakdown["structure"] = 0
    
    # === Concepts ICT avancés v2 ===
    
    # MSS (STRUCTURAL: poids = 3 — ICT signal le plus puissant)
    # MSS = CHOCH + Displacement + FVG simultanément
    # STRUCTURAL: poids 3 car MSS combine 3 concepts en 1 signal
    if mss_present:
        score += MSS_WEIGHT
        breakdown["mss"] = MSS_WEIGHT
    else:
        breakdown["mss"] = 0
    
    # Killzone (STRUCTURAL: poids = 2 — ICT time filter crucial)
    # STRUCTURAL: poids 2 car ICT dit que les trades hors killzone
    # ont une win rate significativement plus basse
    if killzone_active:
        score += KILLZONE_WEIGHT
        breakdown["killzone"] = KILLZONE_WEIGHT
    else:
        breakdown["killzone"] = 0
    
    # PO3 Distribution (STRUCTURAL: poids = 1 — cycle quotidien confirmé)
    if po3_distribution:
        score += PO3_WEIGHT
        breakdown["po3"] = PO3_WEIGHT
    else:
        breakdown["po3"] = 0
    
    # Breaker (STRUCTURAL: poids = 1 — OB invalidé avec rôle inversé)
    if breaker_present:
        score += BREAKER_WEIGHT
        breakdown["breaker"] = BREAKER_WEIGHT
    else:
        breakdown["breaker"] = 0
    
    # PDHL (STRUCTURAL: poids = 1 — liquidité journalière/hebdo)
    if pdhl_aligned:
        score += PDHL_WEIGHT
        breakdown["pdhl"] = PDHL_WEIGHT
    else:
        breakdown["pdhl"] = 0
    
    # Eligibilité (STRUCTURAL: minimum CONFLUENCE_MINIMUM = 2)
    is_eligible = score >= CONFLUENCE_MINIMUM
    
    logger.info(
        f"CONFLUENCE | score={score} | eligible={is_eligible} | "
        f"breakdown={breakdown} | "
        f"NOTE: score does NOT bypass risk_guard (Règle 5)"
    )
    
    return {
        "score": score,
        "breakdown": breakdown,
        "is_eligible": is_eligible,
        "risk_note": "Score does NOT affect risk_guard, position size, or SL/TP (Règle 5)",
    }
