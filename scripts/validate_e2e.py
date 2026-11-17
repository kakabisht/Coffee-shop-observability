#!/usr/bin/env python3
"""Live Docker acceptance checks; standard library only. Leaves test orders in DB."""
import json
from datetime import datetime, timezone
import os
import time
import urllib.parse
import urllib.request

BASE = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
JAEGER = os.getenv("JAEGER_URL", "http://localhost:16686").rstrip("/")
SEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200").rstrip("/")
PROM = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
TIMEOUT = int(os.getenv("TIMEOUT_SECONDS", "120"))


def request(url, payload=None, raw=False):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read()
        return body.decode() if raw else json.loads(body)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def eventually(check, description):
    deadline = time.monotonic() + TIMEOUT
    last = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                print("PASS:", description, flush=True)
                return result
        except Exception as exc:
            last = exc
        time.sleep(2)
    raise RuntimeError("Timed out: {} (last error: {})".format(description, last))


def distributed_trace_id(body):
    # gRPC gateway streams newline-delimited result envelopes containing OTLP JSON.
    services_by_trace = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        envelope = json.loads(line)
        if "error" in envelope:
            raise RuntimeError("Jaeger query error: " + str(envelope["error"]))
        for resource in envelope.get("result", {}).get("resourceSpans", []):
            attributes = resource.get("resource", {}).get("attributes", [])
            service = next((a["value"].get("stringValue") for a in attributes
                            if a["key"] == "service.name"), None)
            for scope in resource.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    services_by_trace.setdefault(span["traceId"], set()).add(service)
    for trace_id, services in services_by_trace.items():
        if {"order-api", "inventory-service", "barista-service"} <= services:
            return trace_id
    observed = {trace_id: sorted(str(s) for s in services)
                for trace_id, services in services_by_trace.items()}
    raise RuntimeError(
        "No complete distributed trace. Expected order-api, inventory-service, "
        "barista-service; observed services by trace: " + str(observed)
    )


def trace_for(order_id):
    def timestamp(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")

    now = time.time()
    query = urllib.parse.urlencode({
        "query.serviceName": "order-api",
        "query.attributes": json.dumps({"coffee.order_id": str(order_id)}),
        "query.startTimeMin": timestamp(now - 3600),
        "query.startTimeMax": timestamp(now + 60),
        "query.searchDepth": 100,
    })
    return distributed_trace_id(request(JAEGER + "/api/v3/traces?" + query, raw=True))


def main():
    eventually(lambda: request(BASE + "/healthz").get("status") == "ok", "Order API ready")
    require("<html" in request(BASE + "/", raw=True).lower(), "Customer HTML missing")
    require(len(request(BASE + "/menu")["items"]) == 8, "Expected eight coffees")
    require(request(BASE + "/config")["demo_scenarios_enabled"], "Enable demo scenarios before validation")
    expected = ["received", "checking_inventory", "ingredients_reserved", "preparing", "ready"]
    orders = []
    for scenario in ("normal", "slow_io", "slow_cpu", "slow_db", "slow_memory"):
        created = request(BASE + "/orders", {"drink": "cappuccino", "size": "medium", "scenario": scenario})
        order_id = created["order_id"]
        orders.append(order_id)

        def ready():
            order = request(BASE + "/orders/" + str(order_id))
            require(order["status"] != "failed", "Order failed: " + str(order))
            if order["status"] != "ready":
                return False
            require([h["status"] for h in order["history"]] == expected, "Incomplete lifecycle")
            return True

        eventually(ready, "{} order {} lifecycle".format(scenario, order_id))
    for order_id in orders:
        trace_id = eventually(lambda: trace_for(order_id), "distributed trace for order " + str(order_id))

        def correlated_logs():
            result = request(SEARCH + "/coffee-shop-logs-*/_search", {"size": 10, "query": {"match": {"traceId": trace_id}}})
            return any(hit["_source"].get("spanId") for hit in result["hits"]["hits"])

        eventually(correlated_logs, "trace-correlated logs for order " + str(order_id))
    query = urllib.parse.urlencode({"query": '{__name__=~"coffee_orders.*"}'})
    eventually(lambda: request(PROM + "/api/v1/query?" + query)["data"]["result"], "business metrics stored in Prometheus")
    print("PASS: workflow, distributed traces, correlated logs, and metrics. Verify profiles and dashboard rendering manually.")


if __name__ == "__main__":
    main()
