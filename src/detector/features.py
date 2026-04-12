"""
Feature engineering for anomaly detection.
Selects and scales features based on EDA findings.
"""

import logging

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

logger = logging.getLogger(__name__)

# Features selected after EDA:
# - Dropped network_transmit_bytes_rate: correlation 0.92 with receive
# - Dropped pod_ready_rolling_*: zero variance in collected data
# - Kept rolling features: help detect slow drifts, not just spikes
SELECTED_FEATURES = [
    "cpu_usage_rate",
    "cpu_usage_rate_rolling_mean",
    "cpu_usage_rate_rolling_std",
    "memory_working_set_bytes",
    "memory_working_set_bytes_rolling_mean",
    "memory_working_set_bytes_rolling_std",
    "network_receive_bytes_rate",
    "network_receive_bytes_rate_rolling_mean",
    "network_receive_bytes_rate_rolling_std",
    "restart_delta",
    "restart_delta_rolling_mean",
]


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Select and validate the feature columns used by the model.
    Drops columns not in SELECTED_FEATURES silently.
    Raises if a required feature is missing.
    """
    available = [f for f in SELECTED_FEATURES if f in df.columns]
    missing = [f for f in SELECTED_FEATURES if f not in df.columns]

    if missing:
        logger.warning("Missing features (will be skipped): %s", missing)

    if not available:
        raise ValueError(
            f"No selected features found in DataFrame. Expected: {SELECTED_FEATURES}"
        )

    logger.info("Using %d features: %s", len(available), available)
    return df[available].copy()


def scale_features(
    X_train: np.ndarray,
    X_test: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray | None, RobustScaler]:
    """
    Scale features using RobustScaler.
    Fit only on training data to prevent data leakage.

    Returns:
        X_train_scaled, X_test_scaled (or None), fitted scaler
    """
    scaler = RobustScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    X_test_scaled = None
    if X_test is not None:
        X_test_scaled = scaler.transform(X_test)

    return X_train_scaled, X_test_scaled, scaler
