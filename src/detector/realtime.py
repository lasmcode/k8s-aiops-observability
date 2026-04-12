"""
Real-time anomaly detector.
Loads the trained model from MLflow and queries Prometheus
every SCRAPE_INTERVAL seconds to detect live anomalies.

Usage:
    uv run python src/detector/realtime.py
    uv run python src/detector/realtime.py --interval 15 --threshold 0.6
"""

import argparse
import logging
import os
import time
from datetime import datetime, timedelta

import mlflow.sklearn
import numpy as np
from dotenv import load_dotenv

from src.collector.preprocessor import (
    add_rolling_features,
    build_feature_matrix,
    parse_range_result,
)
from src.collector.prometheus_client import PrometheusClient
from src.collector.queries import build_queries
from src.detector.features import select_features

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ANSI colors for terminal output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def load_model_and_scaler(
    model_uri: str = "models:/k8s-anomaly-detector/latest",
    scaler_path: str = "src/models/scaler.joblib",
):
    """Load trained model from MLflow registry and scaler from disk."""
    import joblib

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))
    logger.info("Loading model from MLflow: %s", model_uri)
    model = mlflow.sklearn.load_model(model_uri)

    logger.info("Loading scaler from: %s", scaler_path)
    scaler = joblib.load(scaler_path)

    return model, scaler


def detect_anomalies(
    model,
    scaler,
    X: np.ndarray,
    pod_names: list[str],
    threshold: float = 0.5,
) -> list[dict]:
    """
    Run inference on current metrics.

    Returns list of anomaly events with pod name and score.
    Score > threshold triggers an alert.
    """
    X_scaled = scaler.transform(X)

    # score_samples returns negative anomaly scores
    # More negative = more anomalous
    # We negate to get positive anomaly score (higher = more anomalous)
    anomaly_scores = -model.score_samples(X_scaled)
    predictions = model.predict(X_scaled)  # 1 = normal, -1 = anomaly

    events = []
    for i, (pod, score, pred) in enumerate(zip(pod_names, anomaly_scores, predictions)):
        is_anomaly = pred == -1
        events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "pod": pod,
                "anomaly_score": round(float(score), 4),
                "is_anomaly": is_anomaly,
                "severity": _compute_severity(score, threshold),
            }
        )

    return events


def _compute_severity(score: float, threshold: float) -> str:
    """Classify anomaly severity based on score magnitude."""
    if score < threshold:
        return "normal"
    elif score < threshold * 1.5:
        return "warning"
    else:
        return "critical"


def print_event(event: dict) -> None:
    """Pretty-print a detection event to the terminal."""
    severity = event["severity"]
    pod = event["pod"].split("-")[0]  # Short pod name for readability

    if severity == "critical":
        color = RED
        icon = "[CRITICAL]"
    elif severity == "warning":
        color = YELLOW
        icon = "[WARNING] "
    else:
        color = GREEN
        icon = "[OK]      "

    print(
        f"{color}{BOLD}{icon}{RESET} "
        f"pod={pod:<20} "
        f"score={event['anomaly_score']:.4f} "
        f"time={event['timestamp'][11:19]}"
    )


def run(
    interval: int = 30,
    threshold: float = 0.5,
    namespace: str = "apps",
    prometheus_url: str = "http://localhost:9090",
) -> None:
    """Main detection loop."""
    model, scaler = load_model_and_scaler()
    client = PrometheusClient(base_url=prometheus_url)
    queries = build_queries(namespace)

    logger.info(
        "Real-time detector started | interval=%ds | threshold=%.2f",
        interval,
        threshold,
    )
    print(f"\n{'=' * 60}")
    print("  K8s Anomaly Detector — Real-time mode")
    print(f"  Namespace: {namespace} | Interval: {interval}s")
    print(f"  Threshold: {threshold} | Press Ctrl+C to stop")
    print(f"{'=' * 60}\n")

    iteration = 0
    while True:
        iteration += 1
        now = datetime.now()
        window_start = now - timedelta(minutes=5)

        try:
            # Collect current metrics from Prometheus
            metric_dfs = {}
            for name, promql in queries.items():
                raw = client.query_range(
                    promql=promql,
                    start=window_start,
                    end=now,
                    step="15s",
                )
                metric_dfs[name] = parse_range_result(raw, name)

            # Build feature matrix from latest window
            df = build_feature_matrix(metric_dfs)
            df = add_rolling_features(df)

            # Use only the most recent observation per pod
            latest = df.sort_values("timestamp").groupby("pod").last()
            pod_names = latest.index.tolist()

            X_df = select_features(latest.reset_index())
            X = X_df.values

            if len(X) == 0:
                logger.warning("No data available for inference, skipping")
                time.sleep(interval)
                continue

            # Run detection
            events = detect_anomalies(model, scaler, X, pod_names, threshold)

            # Print results
            print(
                f"\n[{now.strftime('%H:%M:%S')}] "
                f"Iteration {iteration} — {len(events)} pods evaluated"
            )
            for event in sorted(events, key=lambda e: e["anomaly_score"], reverse=True):
                print_event(event)

            # Summary
            anomalies = [e for e in events if e["is_anomaly"]]
            if anomalies:
                logger.warning(
                    "ANOMALIES DETECTED: %d pods | scores: %s",
                    len(anomalies),
                    [e["anomaly_score"] for e in anomalies],
                )

        except KeyboardInterrupt:
            logger.info("Detector stopped by user")
            break
        except Exception as e:
            logger.error("Detection error: %s", e, exc_info=True)

        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real-time K8s anomaly detector")
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Detection interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Anomaly score threshold (default: 0.5)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        interval=args.interval,
        threshold=args.threshold,
        namespace=os.getenv("NAMESPACE", "apps"),
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
    )
