# 🛡️ K8s Anomaly Detector

**AIOps platform for infrastructure observability and real-time anomaly detection.**

> [!IMPORTANT]
> **Status: Work in Progress (WIP)** 🏗️
> This project is currently in the active development phase. The infrastructure and data collection layers are complete, and we are now moving into the model training and evaluation phase.

---

## 🏗️ Architecture & Stack

The system follows a modern data pipeline: **Metrics Generation -> Collection -> Feature Engineering -> ML Inference**.

* **Orchestration:** `Kind` (Kubernetes in Docker) for lightweight and reproducible clusters.
* **Observability Stack:** `kube-prometheus-stack` (Prometheus, Grafana, AlertManager).
* **Machine Learning:** `Python`, `Scikit-learn` (Isolation Forest), `Pandas`.
* **Lifecycle Management:** `MLflow` for experiment tracking and model versioning.
* **Tooling & DX:** `uv` (Fast Python package manager), `ruff`, `Make` for task automation.

---

## 🚀 Quick Start (Current Progress)

### 1. Infrastructure Setup ✅
Deploy the environment:
```bash
make cluster-up      # Starts the Kind cluster
make monitoring-up   # Deploys Prometheus + Grafana via Helm
make apps-deploy     # Deploys test microservices
