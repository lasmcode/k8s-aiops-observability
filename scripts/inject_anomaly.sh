#!/usr/bin/env bash
# Inject controlled CPU and memory anomalies via stress-worker.
# Usage: ./scripts/inject_anomaly.sh [duration_seconds] [cpu_workers] [memory_mb]

set -euo pipefail

DURATION=${1:-120}
CPU_WORKERS=${2:-2}
MEMORY_MB=${3:-256}
NAMESPACE="apps"
POD=$(kubectl get pod -n ${NAMESPACE} -l app=stress-worker \
      -o jsonpath='{.items[0].metadata.name}')

echo "Injecting anomaly into pod: ${POD}"
echo "  CPU workers : ${CPU_WORKERS}"
echo "  Memory      : ${MEMORY_MB}MB"
echo "  Duration    : ${DURATION}s"
echo ""
echo "Start time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

kubectl exec -n ${NAMESPACE} ${POD} -- \
  stress \
    --cpu ${CPU_WORKERS} \
    --vm 1 \
    --vm-bytes "${MEMORY_MB}M" \
    --timeout ${DURATION}s \
    --verbose

echo "End time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Anomaly injection complete."
