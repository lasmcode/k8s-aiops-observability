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
# --- Monitoring & Observability ---
create-secret: ## Create or recreate Grafana admin secret (Safe for multiple runs)
	@read -p "Enter Grafana admin password: " PASS; \
	kubectl create namespace $(NS_MON) --dry-run=client -o yaml | kubectl apply -f -; \
	kubectl delete secret grafana-admin-credentials -n $(NS_MON) --ignore-not-found; \
	kubectl create secret generic grafana-admin-credentials \
	  --from-literal=admin-user=admin \
	  --from-literal=admin-password=$$PASS \
	  -n $(NS_MON)
	@echo "Secret 'grafana-admin-credentials' successfully (re)created in namespace $(NS_MON)."
monitoring-up: ## Install kube-prometheus-stack and SLO rules
	@kubectl get secret grafana-admin-credentials -n $(NS_MON) > /dev/null 2>&1 || \
		(echo "ERROR: Secret 'grafana-admin-credentials' not found. Run 'make create-secret' first." && exit 1)
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	kubectl create namespace $(NS_MON) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
		--namespace $(NS_MON) \
		--values k8s/monitoring/prometheus-values.yaml \
		--version 60.3.0 \
		--wait --timeout 10m
	kubectl apply -f k8s/monitoring/slo-rules.yaml

monitoring-status: ## Check the health of the monitoring stack
	kubectl get pods -n $(NS_MON)
	kubectl get prometheusrule -n $(NS_MON)

monitoring-down: ## Uninstall the monitoring stack [cite: 5]
	helm uninstall kube-prometheus-stack --namespace $(NS_MON) [cite: 5]
	kubectl delete namespace $(NS_MON) [cite: 5]

port-forward: ## Open tunnels for Prometheus (9090) and Grafana (3000)
	bash scripts/port_forward.sh

# --- Efficient Resource Control ---

pause-lab: ## Stop all containers to save RAM/CPU
	@echo "Pausing AIOps Lab..."
	docker stop $(CLUSTER_NAME)-control-plane $(CLUSTER_NAME)-worker $(CLUSTER_NAME)-worker2
	@echo "Lab paused. Metrics collection is suspended."

resume-lab: ## Resume containers and verify health
	@echo "Resuming AIOps Lab..."
	docker start $(CLUSTER_NAME)-control-plane $(CLUSTER_NAME)-worker $(CLUSTER_NAME)-worker2
	@echo "Waiting for nodes to be Ready..."
	@kubectl wait --for=condition=Ready nodes --all --timeout=60s
	@echo "Verifying monitoring stack..."
	@kubectl rollout status deployment/kube-prometheus-stack-operator -n $(NS_MON)
	@echo "Lab is back. Note: Expect a 5-15 min gap in Prometheus charts."
