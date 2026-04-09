"""
PromQL queries for metric collection.
Each query extracts one feature used by the anomaly detection model.
"""

# Namespace to monitor — injected at runtime from config
NAMESPACE = "{namespace}"

METRIC_QUERIES: dict[str, str] = {
    # CPU usage rate per pod (cores/second averaged over 5m window)
    "cpu_usage_rate": (
        f"sum by (pod) ("
        f"  rate(container_cpu_usage_seconds_total{{"
        f"    namespace='{NAMESPACE}', container!=''"
        f"  }}[5m])"
        f")"
    ),
    # Memory working set per pod (bytes — excludes reclaimable cache)
    "memory_working_set_bytes": (
        f"sum by (pod) ("
        f"  container_memory_working_set_bytes{{"
        f"    namespace='{NAMESPACE}', container!=''"
        f"  }}"
        f")"
    ),
    # Network received bytes rate per pod
    "network_receive_bytes_rate": (
        f"sum by (pod) ("
        f"  rate(container_network_receive_bytes_total{{"
        f"    namespace='{NAMESPACE}'"
        f"  }}[5m])"
        f")"
    ),
    # Network transmitted bytes rate per pod
    "network_transmit_bytes_rate": (
        f"sum by (pod) ("
        f"  rate(container_network_transmit_bytes_total{{"
        f"    namespace='{NAMESPACE}'"
        f"  }}[5m])"
        f")"
    ),
    # Pod restart count (cumulative — we compute delta in preprocessor)
    "pod_restarts_total": (
        f"sum by (pod) ("
        f"  kube_pod_container_status_restarts_total{{"
        f"    namespace='{NAMESPACE}'"
        f"  }}"
        f")"
    ),
    # Pod readiness (1 = ready, 0 = not ready)
    "pod_ready": (
        f"sum by (pod) ("
        f"  kube_pod_status_ready{{"
        f"    namespace='{NAMESPACE}', condition='true'"
        f"  }}"
        f")"
    ),
}


def build_queries(namespace: str) -> dict[str, str]:
    """Return metric queries with the target namespace substituted."""
    return {
        name: query.replace(NAMESPACE, namespace)
        for name, query in METRIC_QUERIES.items()
    }
