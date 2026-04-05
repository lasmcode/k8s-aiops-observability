.PHONY: help cluster-up cluster-down monitoring-up monitoring-down \
        apps-deploy collect detect test lint clean

CLUSTER_NAME := aiops-lab
KUBECONFIG := $(HOME)/.kube/config

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf " \033[36m%-20s\033[0m %s\n", $$1, $$2}'

cluster-up: ## Create the Kind cluster
	kind create cluster --config k8s/cluster/kind-config.yaml
	kubectl cluster-info --context kind-$(CLUSTER_NAME)

cluster-down: ## Destroy the Kind cluster
	kind delete cluster --name $(CLUSTER_NAME)

monitoring-up: ## Install kube-prometheus-stack via Helm
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack

--namespace monitoring

--values ​​k8s/monitoring/prometheus-values.yaml

--wait

monitoring-down: ## Uninstall the monitoring stack

helm uninstall kube-prometheus-stack --namespace monitoring

collect: ## Run the metrics collector

uv run python src/collector/main.py

detect: ## Run the detection model

uv run python src/detector/main.py

test: ## Run the tests

uv run pytest --cov=src --cov-report=term-missing

lint: ## Check the code with ruff

uv run ruff check src/tests/

clean: ## Clean temporary artifacts

find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage

stop-nodes: ## Stop cluster containers (pause)
	docker stop aiops-lab-control-plane aiops-lab-worker aiops-lab-worker2

start-nodes: ## Start previously stopped containers
	docker start aiops-lab-control-plane aiops-lab-worker aiops-lab-worker2