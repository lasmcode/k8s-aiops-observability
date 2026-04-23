"""
Isolation Forest trainer with MLflow experiment tracking.

Usage:
    uv run python src/detector/trainer.py
    uv run python src/detector/trainer.py --contamination 0.1 --n-estimators 200
"""

import argparse
import glob
import logging
import os
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from src.detector.features import scale_features, select_features

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_dataset(data_dir: str = "data/raw") -> pd.DataFrame:
    """Load and merge all collected CSV files."""
    files = glob.glob(f"{data_dir}/metrics_*.csv")
    if not files:
        raise FileNotFoundError(
            f"No metric CSV files found in {data_dir}. "
            "Run: make collect-normal && make inject-anomaly && make collect-anomaly"
        )

    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info(
        "Loaded %d rows from %d files | labels: %s",
        len(df),
        len(files),
        df["label"].value_counts().to_dict(),
    )
    return df


def evaluate_model(
    model: IsolationForest,
    X_test_scaled: np.ndarray,
    y_test: np.ndarray,
) -> dict[str, float]:
    """
    Evaluate the model against ground-truth labels.

    Isolation Forest returns: 1 = normal, -1 = anomaly
    We convert to:           0 = normal,  1 = anomaly
    to match our label convention.
    """
    raw_predictions = model.predict(X_test_scaled)
    y_pred = np.where(raw_predictions == -1, 1, 0)

    # Anomaly scores: lower (more negative) = more anomalous
    anomaly_scores = -model.score_samples(X_test_scaled)

    metrics = {
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1_score": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, anomaly_scores),
        "test_samples": len(y_test),
        "anomaly_samples_detected": int(y_pred.sum()),
        "anomaly_samples_actual": int(y_test.sum()),
    }

    logger.info(
        "Classification report:\n%s",
        classification_report(y_test, y_pred, target_names=["normal", "anomaly"]),
    )
    logger.info("Confusion matrix:\n%s", confusion_matrix(y_test, y_pred))

    return metrics


def train(
    contamination: float = 0.148,
    n_estimators: int = 100,
    max_features: float = 1.0,
    random_state: int = 42,
    data_dir: str = "data/raw",
    model_dir: str = "src/models",
) -> str:
    """
    Train Isolation Forest and log everything to MLflow.

    Key design decision: train ONLY on normal data.
    This simulates production where anomalies are not labeled.
    Evaluate on a held-out set that includes both classes.

    Returns:
        MLflow run ID of the trained model.
    """
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))
    mlflow.set_experiment("k8s-anomaly-detection")

    df = load_dataset(data_dir)

    # Binary label: 1 = anomaly, 0 = normal
    df["is_anomaly"] = (df["label"] == "anomaly").astype(int)

    # Select and validate features
    X_all = select_features(df)
    y_all = df["is_anomaly"].values

    # Stratified split to preserve class ratio
    X_train_df, X_test_df, y_train, y_test = train_test_split(
        X_all,
        y_all,
        test_size=0.2,
        stratify=y_all,
        random_state=random_state,
    )

    # Train ONLY on normal samples — unsupervised setup
    X_train_normal = X_train_df[y_train == 0]
    logger.info(
        "Training on %d normal samples | Testing on %d samples (%d anomalies)",
        len(X_train_normal),
        len(X_test_df),
        int(y_test.sum()),
    )

    # Scale features — fit on train normal only
    X_train_scaled, X_test_scaled, scaler = scale_features(
        X_train_normal.values,
        X_test_df.values,
    )

    with mlflow.start_run() as run:
        run_id = run.info.run_id
        logger.info("MLflow run ID: %s", run_id)

        # Log parameters
        params = {
            "algorithm": "IsolationForest",
            "contamination": contamination,
            "n_estimators": n_estimators,
            "max_features": max_features,
            "random_state": random_state,
            "scaler": "RobustScaler",
            "train_on_normal_only": True,
            "feature_count": X_train_scaled.shape[1],
            "train_samples": len(X_train_scaled),
            "test_samples": len(X_test_scaled),
        }
        mlflow.log_params(params)

        # Train model
        model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            n_jobs=-1,
        )
        model.fit(X_train_scaled)

        # Evaluate
        metrics = evaluate_model(model, X_test_scaled, y_test)
        mlflow.log_metrics(metrics)

        logger.info(
            "Results | F1: %.3f | Precision: %.3f | Recall: %.3f | ROC-AUC: %.3f",
            metrics["f1_score"],
            metrics["precision"],
            metrics["recall"],
            metrics["roc_auc"],
        )

        # Log model and scaler as MLflow artifacts
        mlflow.sklearn.log_model(
            model,
            artifact_path="isolation_forest",
            registered_model_name="k8s-anomaly-detector",
        )

        # Save scaler separately (needed for inference)
        model_dir_path = Path(model_dir)
        model_dir_path.mkdir(parents=True, exist_ok=True)
        scaler_path = model_dir_path / "scaler.joblib"
        joblib.dump(scaler, scaler_path)
        mlflow.log_artifact(str(scaler_path), artifact_path="scaler")

        # Log feature list as artifact for reproducibility
        feature_path = model_dir_path / "features.txt"
        feature_path.write_text("\n".join(X_train_df.columns.tolist()))
        mlflow.log_artifact(str(feature_path))

        logger.info("Model registered in MLflow | run_id=%s", run_id)
        return run_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train Isolation Forest anomaly detector"
    )
    parser.add_argument(
        "--contamination",
        type=float,
        default=0.148,
        help="Expected fraction of anomalies (default: 0.148)",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=100,
        help="Number of trees in the forest (default: 100)",
    )
    parser.add_argument(
        "--max-features",
        type=float,
        default=1.0,
        help="Fraction of features per tree (default: 1.0)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        contamination=args.contamination,
        n_estimators=args.n_estimators,
        max_features=args.max_features,
    )
