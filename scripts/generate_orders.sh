#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

for scenario in normal slow_io slow_cpu slow_db slow_memory; do
  echo "Creating order with scenario: ${scenario}"
  curl --fail-with-body --silent --show-error \
    -X POST "${BASE_URL}/orders" \
    -H 'Content-Type: application/json' \
    -d "{\"drink\":\"cappuccino\",\"size\":\"medium\",\"scenario\":\"${scenario}\"}"
  echo
  sleep 1
done
