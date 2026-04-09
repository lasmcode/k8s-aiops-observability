"""
Prometheus API client.
Handles all communication with the Prometheus HTTP API.
"""

import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Thin wrapper around the Prometheus HTTP API v1."""

    def __init__(self, base_url: str = "http://localhost:9090"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def health_check(self) -> bool:
        """Return True if Prometheus is reachable and ready."""
        try:
            response = self.session.get(f"{self.base_url}/-/ready", timeout=5)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error("Prometheus health check failed: %s", e)
            return False

    def query_instant(self, promql: str) -> list[dict]:
        """
        Execute an instant query against Prometheus.
        Returns the result list from the API response.
        """
        response = self.session.get(
            f"{self.base_url}/api/v1/query",
            params={"query": promql},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] != "success":
            raise ValueError(f"Prometheus query failed: {data}")

        return data["data"]["result"]

    def query_range(
        self,
        promql: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> list[dict]:
        """
        Execute a range query against Prometheus.
        Returns time series data between start and end.
        """
        response = self.session.get(
            f"{self.base_url}/api/v1/query_range",
            params={
                "query": promql,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] != "success":
            raise ValueError(f"Prometheus range query failed: {data}")

        return data["data"]["result"]
