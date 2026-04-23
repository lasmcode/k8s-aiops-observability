#!/usr/bin/env bash
# Start port-forwards for Prometheus and Grafana
# Usage: ./scripts/port_forward.sh

set -euo pipefail

echo "Starting port-forwards..."

kubectl port-forward svc/kube-prometheus-stack-prometheus \
  -n monitoring 9090:9090 &
PID_PROM=$!

kubectl port-forward svc/kube-prometheus-stack-grafana \
  -n monitoring 3000:80 &
PID_GRAF=$!

echo "Prometheus: http://localhost:9090"
echo "Grafana:    http://localhost:3000 (admin / aiops-lab)"
echo ""
echo "Press Ctrl+C to stop all port-forwards"

trap "kill $PID_PROM $PID_GRAF 2>/dev/null; echo 'Port-forwards stopped'" EXIT
wait
