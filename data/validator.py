"""
Validation d'intégrité des données — Bot SMC/ICT v2.

RÈGLE 6 : Pas d'échec silencieux.
RÈGLE 7 : Taille d'échantillon suffisante.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def validate_data_integrity(df: pd.DataFrame, min_bars: int = 10000) -> dict:  # STRUCTURAL: 10k bougies M1 ≈ 1 semaine de données
    """
    Valide l'intégrité des données historiques.
    
    RÈGLE 7 : Vérifie que la taille de l'échantillon est suffisante.
    RÈGLE 6 : Toute anomalie est loguée, jamais silencieuse.
    
    Args:
        df: DataFrame OHLCV
        min_bars: Nombre minimum de bougies attendu
    
    Returns:
        dict avec les résultats de validation
    """
    results = {
        "valid": True,
        "total_bars": len(df),
        "issues": [],
    }
    
    # 1. Vérification de la taille
    if len(df) < min_bars:
        msg = f"Taille insuffisante: {len(df)} < {min_bars} bougies"
        results["issues"].append(msg)
        logger.warning(f"DATA_VALIDATION | {msg}")
    
    # 2. Vérification des valeurs NaN
    nan_counts = df.isnull().sum()
    for col, count in nan_counts.items():
        if count > 0:
            msg = f"NaN dans {col}: {count} valeurs"
            results["issues"].append(msg)
            logger.warning(f"DATA_VALIDATION | {msg}")
    
    # 3. Vérification high >= low
    if "high" in df.columns and "low" in df.columns:
        invalid_hl = df[df["high"] < df["low"]]
        if len(invalid_hl) > 0:
            msg = f"high < low sur {len(invalid_hl)} bougies"
            results["issues"].append(msg)
            logger.warning(f"DATA_VALIDATION | {msg}")
    
    # 4. Vérification des prix négatifs
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            neg = df[df[col] <= 0]
            if len(neg) > 0:
                msg = f"Prix <= 0 dans {col}: {len(neg)} bougies"
                results["issues"].append(msg)
                logger.warning(f"DATA_VALIDATION | {msg}")
    
    # 5. Vérification de la continuité temporelle (trous)
    if isinstance(df.index, pd.DatetimeIndex):
        time_diffs = df.index.to_series().diff()
        median_diff = time_diffs.median()
        large_gaps = time_diffs[time_diffs > median_diff * 10]  # STRUCTURAL: 10x l'intervalle médian = gap significatif
        if len(large_gaps) > 0:
            msg = f"Trous temporels détectés: {len(large_gaps)} gaps > 10x l'intervalle médian"
            results["issues"].append(msg)
            logger.warning(f"DATA_VALIDATION | {msg}")
    
    # 6. Vérification des doublons de timestamp
    duplicates = df.index.duplicated()
    if duplicates.any():
        msg = f"Timestamps dupliqués: {duplicates.sum()}"
        results["issues"].append(msg)
        logger.warning(f"DATA_VALIDATION | {msg}")
    
    if results["issues"]:
        results["valid"] = False
    
    logger.info(
        f"DATA_VALIDATION | valid={results['valid']} | "
        f"bars={results['total_bars']} | issues={len(results['issues'])}"
    )
    
    return results
