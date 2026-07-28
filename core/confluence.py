"""
Score de confluence — Bot SMC/ICT v2.

RÈGLE 1 : compute_confluence_score() est la SEULE fonction.
RÈGLE 4 : Tous les poids depuis config avec justification.
RÈGLE 5 : Le score NE BYPASSE PAS le risque (explicitement documenté).
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
    
    Returns:
        dict avec score, breakdown, et is_eligible
    """
    score = 0
    breakdown = {}
    
    # HTF Bias (STRUCTURAL: poids = 1)
    if htf_bias_aligned:
        score += HTF_BIAS_WEIGHT
        breakdown["htf_bias"] = HTF_BIAS_WEIGHT
    else:
        breakdown["htf_bias"] = 0
    
    # Zone (STRUCTURAL: poids = 1)
    if zone_favorable:
        score += ZONE_WEIGHT
        breakdown["zone"] = ZONE_WEIGHT
    else:
        breakdown["zone"] = 0
    
    # FVG (STRUCTURAL: poids = 1)
    if fvg_present:
        score += FVG_WEIGHT
        breakdown["fvg"] = FVG_WEIGHT
    else:
        breakdown["fvg"] = 0
    
    # OB (STRUCTURAL: poids = 1)
    if ob_present:
        score += OB_WEIGHT
        breakdown["ob"] = OB_WEIGHT
    else:
        breakdown["ob"] = 0
    
    # Sweep (STRUCTURAL: poids = 2 — plus important)
    if sweep_present:
        score += SWEEP_WEIGHT
        breakdown["sweep"] = SWEEP_WEIGHT
    else:
        breakdown["sweep"] = 0
    
    # Displacement (STRUCTURAL: poids = 1)
    if displacement_significant:
        score += DISPLACEMENT_WEIGHT
        breakdown["displacement"] = DISPLACEMENT_WEIGHT
    else:
        breakdown["displacement"] = 0
    
    # Structure (STRUCTURAL: poids = 1)
    if structure_aligned:
        score += STRUCTURE_WEIGHT
        breakdown["structure"] = STRUCTURE_WEIGHT
    else:
        breakdown["structure"] = 0
    
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
