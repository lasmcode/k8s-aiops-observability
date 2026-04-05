# k8s-anomaly-detector

Anomaly detection system in Kubernetes using Prometheus, Grafana, and Isolation Forest.

## Stack
- **Cluster:** Kind (Kubernetes in Docker)
- **Package manager K8s:** Helm 3
- **Observability:** kube-prometheus-stack (Prometheus + Grafana + AlertManager)
- **ML:** Python · Scikit-learn · Isolation Forest · MLflow
- **Tooling:** uv · ruff · pre-commit · Make

## Quick Start
```bash
make cluster-up # Starts the Kind cluster
make monitoring-up # Installs Prometheus + Grafana
make apps-deploy # Deploys test apps
make collect # Collects metrics
make detect # Detects anomalies
```