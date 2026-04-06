#!/usr/bin/env bash
# Load generator for standard API services
# Usage: ./scripts/load_generator.sh [duration_seconds]

set -euo pipefail

DURATION=${1:-300}
NAMESPACE="apps"
POD_NAME="load-generator"

echo "Starting load generator by ${DURATION}s..."

kubectl run ${POD_NAME} \
  --image=curlimages/curl:latest \
  --restart=Never \
  --namespace=${NAMESPACE} \
  -- sh -c "
    END=\$(( \$(date +%s) + ${DURATION} ))
    while [ \$(date +%s) -lt \$END ]; do
      curl -s http://api-service/get > /dev/null
      curl -s http://api-service/delay/1 > /dev/null
      curl -s http://web-frontend/ > /dev/null
      sleep 2
    done
    echo 'Carga completada'
  "

echo "Charging pod created: ${POD_NAME}"
echo "View logs with: kubectl logs -f ${POD_NAME} -n ${NAMESPACE}"
