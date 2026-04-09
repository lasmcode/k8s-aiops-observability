"""
Metric collection entrypoint.
Queries Prometheus for a configurable time window and saves
the processed feature matrix to disk.

Usage:
    uv run python -m src.collector.main
    uv run python -m src.collector.main --window 60 --label normal
    uv run python -m src.collector.main --window 10 --label anomaly
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from src.collector.preprocessor import (
    add_rolling_features,
    build_feature_matrix,
    parse_range_result,
)
from src.collector.prometheus_client import PrometheusClient
from src.collector.queries import build_queries

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Kubernetes metrics from Prometheus"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=int(os.getenv("COLLECTION_WINDOW_MINUTES", 30)),
        help="Collection window in minutes (default: 30)",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="normal",
        choices=["normal", "anomaly"],
        help="Label for this collection run (default: normal)",
    )
    parser.add_argument(
        "--step",
        type=str,
        default="15s",
        help="Prometheus scrape step (default: 15s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    namespace = os.getenv("NAMESPACE", "apps")
    data_dir = Path(os.getenv("DATA_DIR", "data"))

    client = PrometheusClient(base_url=prometheus_url)

    logger.info("Checking Prometheus connectivity at %s", prometheus_url)
    if not client.health_check():
        logger.error(
            "Cannot reach Prometheus. Is port-forward active? "
            "Run: ./scripts/port_forward.sh"
        )
        sys.exit(1)

    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=args.window)

    logger.info(
        "Collecting metrics | window=%dm | namespace=%s | label=%s",
        args.window,
        namespace,
        args.label,
    )
    logger.info(
        "Time range: %s -> %s",
        start_time.strftime("%H:%M:%S"),
        end_time.strftime("%H:%M:%S"),
    )

    queries = build_queries(namespace)
    metric_dfs = {}

    for metric_name, promql in queries.items():
        logger.info("Querying: %s", metric_name)
        try:
            raw = client.query_range(
                promql=promql,
                start=start_time,
                end=end_time,
                step=args.step,
            )
            metric_dfs[metric_name] = parse_range_result(raw, metric_name)
            logger.info(
                "  -> %d series, %d data points",
                len(raw),
                sum(len(s["values"]) for s in raw),
            )
        except Exception as e:
            logger.warning("Failed to collect %s: %s", metric_name, e)

    if not metric_dfs:
        logger.error("No metrics collected. Aborting.")
        sys.exit(1)

    logger.info("Building feature matrix...")
    feature_matrix = build_feature_matrix(metric_dfs)
    feature_matrix = add_rolling_features(feature_matrix)
    feature_matrix["label"] = args.label
    feature_matrix["collected_at"] = datetime.now().isoformat()

    # Save to disk
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = raw_dir / f"metrics_{args.label}_{timestamp_str}.csv"

    feature_matrix.to_csv(output_path, index=False)

    logger.info(
        "Saved %d rows x %d features -> %s",
        len(feature_matrix),
        len(feature_matrix.columns),
        output_path,
    )
    logger.info("Features: %s", list(feature_matrix.columns))


if __name__ == "__main__":
    main()
