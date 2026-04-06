.PHONY: help cluster-up cluster-down monitoring-up monitoring-down \
        collect detect test lint clean stop-nodes start-nodes

# Variables
CLUSTER_NAME := aiops-lab
KUBECONFIG   := $(HOME)/.kube/config
NS_MON       := monitoring

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf " \033[36m%-20s\033[0m %s\n", $$1, $$2}'

cluster-up: ## Create the Kind cluster using the config file
	kind create cluster --name $(CLUSTER_NAME) --config k8s/cluster/kind-config.yaml
	kubectl cluster-info --context kind-$(CLUSTER_NAME)

cluster-down: ## Destroy the Kind cluster
	kind delete cluster --name $(CLUSTER_NAME)

monitoring-up: ## Install kube-prometheus-stack via Helm
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	kubectl create namespace $(NS_MON) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
		--namespace $(NS_MON) \
		--values k8s/monitoring/prometheus-values.yaml \
		--wait

monitoring-down: ## Uninstall the monitoring stack
	helm uninstall kube-prometheus-stack --namespace $(NS_MON)
	kubectl delete namespace $(NS_MON)

collect: ## Run the metrics collector using uv
	uv run python src/collector/main.py

detect: ## Run the detection model using uv
	uv run python src/detector/main.py

test: ## Run the tests with coverage
	uv run pytest --cov=src --cov-report=term-missing

lint: ## Check the code style with ruff
	uv run ruff check src/ tests/

clean: ## Clean temporary artifacts and python cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache

stop-nodes: ## Pause the cluster containers
	docker stop $(CLUSTER_NAME)-control-plane $(CLUSTER_NAME)-worker $(CLUSTER_NAME)-worker2

start-nodes: ## Resume the cluster containers
	docker start $(CLUSTER_NAME)-control-plane $(CLUSTER_NAME)-worker $(CLUSTER_NAME)-worker2

apps-deploy: ## Deploy sample applications to the apps namespace
	kubectl apply -f k8s/manifests/namespace.yaml
	kubectl apply -f k8s/manifests/web-frontend.yaml
	kubectl apply -f k8s/manifests/api-service.yaml
	kubectl apply -f k8s/manifests/stress-worker.yaml
	kubectl rollout status deployment/web-frontend -n apps
	kubectl rollout status deployment/api-service -n apps
	kubectl rollout status deployment/stress-worker -n apps

apps-status: ## Show the status of all applications in the apps namespace
	kubectl get all -n apps -o wide

apps-down: ## Delete the apps namespace and all its resources
	kubectl delete namespace apps
