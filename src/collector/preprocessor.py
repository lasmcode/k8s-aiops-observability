"""
Metric preprocessor.
Converts raw Prometheus range query results into a clean DataFrame.
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def parse_range_result(
    raw_results: list[dict],
    metric_name: str,
) -> pd.DataFrame:
    """
    Parse a Prometheus range query result into a tidy DataFrame.

    Args:
        raw_results: List of result dicts from Prometheus API.
        metric_name: Column name for the metric values.

    Returns:
        DataFrame with columns: timestamp, pod, <metric_name>
    """
    records = []

    for series in raw_results:
        pod = series["metric"].get("pod", "unknown")
        for timestamp, value in series["values"]:
            records.append(
                {
                    "timestamp": datetime.fromtimestamp(float(timestamp)),
                    "pod": pod,
                    metric_name: float(value) if value != "NaN" else np.nan,
                }
            )

    if not records:
        logger.warning("No data returned for metric: %s", metric_name)
        return pd.DataFrame(columns=["timestamp", "pod", metric_name])

    return pd.DataFrame(records)


def build_feature_matrix(
    metric_dataframes: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Merge all metric DataFrames into a single feature matrix.
    One row per (timestamp, pod) combination.

    Args:
        metric_dataframes: Dict mapping metric_name -> DataFrame.

    Returns:
        Wide-format DataFrame ready for the anomaly detection model.
    """
    if not metric_dataframes:
        raise ValueError("No metric dataframes provided")

    merged = None
    for metric_name, df in metric_dataframes.items():
        if df.empty:
            logger.warning("Skipping empty DataFrame for: %s", metric_name)
            continue

        if merged is None:
            merged = df
        else:
            merged = pd.merge(merged, df, on=["timestamp", "pod"], how="outer")

    if merged is None:
        raise ValueError("All metric DataFrames were empty")

    merged = merged.sort_values(["timestamp", "pod"]).reset_index(drop=True)

    # Forward-fill gaps up to 2 intervals, then drop remaining NaNs
    merged = merged.groupby("pod", group_keys=False).apply(
        lambda g: g.set_index("timestamp").sort_index().ffill(limit=2).reset_index()
    )

    # Compute restart delta (model cares about rate, not cumulative count)
    if "pod_restarts_total" in merged.columns:
        merged["restart_delta"] = (
            merged.groupby("pod")["pod_restarts_total"].diff().fillna(0).clip(lower=0)
        )
        merged = merged.drop(columns=["pod_restarts_total"])

    # Drop rows still containing NaN after forward-fill
    before = len(merged)
    merged = merged.dropna()
    dropped = before - len(merged)
    if dropped > 0:
        logger.info("Dropped %d rows with NaN values after ffill", dropped)

    return merged


def add_rolling_features(
    df: pd.DataFrame,
    window: int = 5,
) -> pd.DataFrame:
    """
    Add rolling statistics per pod as additional features.
    These help Isolation Forest detect slow drifts, not just spikes.

    Args:
        df: Feature matrix from build_feature_matrix().
        window: Rolling window size in number of observations.

    Returns:
        DataFrame with additional rolling mean and std columns.
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols = [c for c in numeric_cols if not c.endswith(("_mean", "_std"))]

    result = df.copy()

    for col in feature_cols:
        result[f"{col}_rolling_mean"] = result.groupby("pod")[col].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )
        result[f"{col}_rolling_std"] = result.groupby("pod")[col].transform(
            lambda x: x.rolling(window, min_periods=1).std().fillna(0)
        )

    return result
