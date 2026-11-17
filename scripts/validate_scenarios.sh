#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
POLL_INTERVAL="${POLL_INTERVAL:-1}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-60}"

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

curl --fail-with-body --silent --show-error "${BASE_URL}/healthz" >/dev/null

echo "Coffee shop API is reachable at ${BASE_URL}"
echo "Running each scenario sequentially and waiting for its final status."
echo

for scenario in normal slow_io slow_cpu slow_db slow_memory; do
  echo "=== Scenario: ${scenario} ==="

  response=$(curl --fail-with-body --silent --show-error \
    -X POST "${BASE_URL}/orders" \
    -H 'Content-Type: application/json' \
    -d "{\"drink\":\"cappuccino\",\"size\":\"medium\",\"scenario\":\"${scenario}\"}")

  order_id=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["order_id"])')
  echo "Created order ${order_id}"

  deadline=$((SECONDS + TIMEOUT_SECONDS))
  while true; do
    tracking=$(curl --fail-with-body --silent --show-error "${BASE_URL}/orders/${order_id}")
    status=$(printf '%s' "$tracking" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')

    case "$status" in
      ready)
        echo "PASS: order ${order_id} reached status=ready"
        break
        ;;
      failed)
        echo "FAIL: order ${order_id} reached status=failed" >&2
        printf '%s\n' "$tracking" | python3 -m json.tool >&2
        exit 1
        ;;
    esac

    if (( SECONDS >= deadline )); then
      echo "TIMEOUT: order ${order_id} remained in status=${status}" >&2
      printf '%s\n' "$tracking" | python3 -m json.tool >&2
      exit 1
    fi
    sleep "$POLL_INTERVAL"
  done

  printf '%s\n' "$tracking" | python3 -c '
import json,sys
order=json.load(sys.stdin)
print("  lifecycle: " + " -> ".join(item["status"] for item in order.get("history", [])))
'
  echo
 done

echo "All five order scenarios completed successfully."
echo "Wait at least 10 seconds for batched telemetry export before checking Jaeger and OpenSearch."
echo "Jaeger:     http://localhost:16686"
echo "Prometheus: http://localhost:9090"
echo "OpenSearch: http://localhost:9200"
