#!/usr/bin/env bash
# Full demo script — brings up the environment and injects anomalies
# Usage: ./scripts/demo.sh

set -euo pipefail

NAMESPACE="apps"
THRESHOLD="0.58"
INTERVAL="30"

echo "=============================================="
echo "  K8s AIOps Anomaly Detection — Demo"
echo "=============================================="
echo ""

# Step 1: Verify cluster
echo "[1/5] Verifying cluster..."
kubectl get nodes --no-headers | grep -c "Ready" | \
  xargs -I{} echo "  {} node(s) ready"

# Step 2: Verify apps
echo "[2/5] Verifying apps in namespace ${NAMESPACE}..."
kubectl get pods -n ${NAMESPACE} --no-headers | \
  grep "Running" | wc -l | \
  xargs -I{} echo "  {} pods running"

# Step 3: Start port-forwards in background
echo "[3/5] Starting port-forwards..."
kubectl port-forward svc/kube-prometheus-stack-prometheus \
  -n monitoring 9090:9090 &>/dev/null &
kubectl port-forward svc/kube-prometheus-stack-grafana \
  -n monitoring 3000:80 &>/dev/null &
sleep 3
echo "  Prometheus: http://localhost:9090"
echo "  Grafana:    http://localhost:3000"

# Step 4: Start real-time detector in background
echo "[4/5] Starting anomaly detector..."
PYTHONPATH=. uv run python src/detector/realtime.py \
  --interval ${INTERVAL} \
  --threshold ${THRESHOLD} &
DETECTOR_PID=$!
echo "  Detector PID: ${DETECTOR_PID}"

# Step 5: Wait, then inject anomaly
echo "[5/5] Waiting 60s for baseline, then injecting anomaly..."
sleep 60

echo ""
echo "  >>> INJECTING ANOMALY NOW <<<"
echo ""

bash scripts/inject_anomaly.sh 120 4 400

echo ""
echo "Demo complete. Dashboard: http://localhost:3000/d/k8s-aiops-v1"
echo "Press Ctrl+C to stop the detector"

trap "kill ${DETECTOR_PID} 2>/dev/null; pkill -f port-forward 2>/dev/null" EXIT
wait ${DETECTOR_PID}
