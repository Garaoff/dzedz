"""
Chargement de données historiques — Bot SMC/ICT v2.

RÈGLE 7 : Données réelles, pas synthétiques. M1 nécessaire pour ICT.
RÈGLE 6 : Pas d'échec silencieux.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def load_historical_data(
    filepath: str,
    timeframe: str = "M1",
    required_columns: list = None,
) -> pd.DataFrame:
    """
    Charge les données historiques depuis un fichier CSV.
    
    RÈGLE 7 : Les données doivent être réelles (pas synthétiques) et en M1.
    
    Args:
        filepath: Chemin vers le fichier de données
        timeframe: Timeframe attendu (défaut: M1)
        required_columns: Colonnes obligatoires
    
    Returns:
        DataFrame avec les données OHLCV
    
    Raises:
        ValueError: Si les données sont invalides ou manquantes
        FileNotFoundError: Si le fichier n'existe pas
    """
    if required_columns is None:
        required_columns = ["open", "high", "low", "close", "volume"]
    
    path = Path(filepath)
    if not path.exists():
        logger.error(f"DATA_LOAD | reason=file_not_found | path={filepath}")
        raise FileNotFoundError(f"Fichier non trouvé: {filepath}")
    
    try:
        df = pd.read_csv(filepath, parse_dates=True, index_col=0)
    except Exception as e:
        logger.error(f"DATA_LOAD | reason=parse_error | path={filepath} | error={e}", exc_info=True)
        raise
    
    # Validation des colonnes
    missing_cols = [c for c in required_columns if c not in df.columns]
    if missing_cols:
        logger.error(f"DATA_LOAD | reason=missing_columns | missing={missing_cols}")
        raise ValueError(f"Colonnes manquantes: {missing_cols}")
    
    # Vérification du timeframe
    if timeframe != "M1":
        logger.warning(
            f"DATA_LOAD | timeframe_warning | "
            f"expected=M1 | got={timeframe} | "
            f"Les setups ICT nécessitent des données M1"
        )
    
    # Vérification de la taille des données
    n_bars = len(df)
    logger.info(
        f"DATA_LOAD | path={filepath} | bars={n_bars} | "
        f"start={df.index[0]} | end={df.index[-1]} | "
        f"columns={list(df.columns)}"
    )
    
    if n_bars < 1000:  # STRUCTURAL: 1000 bougies = minimum pour un contexte significatif
        logger.warning(
            f"DATA_LOAD | low_data | bars={n_bars} | "
            f"Un minimum de données significatif est nécessaire pour la validation"
        )
    
    return df
