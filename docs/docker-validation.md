# Docker acceptance validation

## Recorded result — 17 November 2026

The Docker end-to-end run is **pending**, not certified as passing.

| Check | Result |
|---|---|
| `docker compose config --quiet` | Passed with Compose v5.7.0 |
| Seven existing menu and workload test functions | Passed by direct Python invocation |
| pytest runner | Unavailable in default Python; `No module named pytest` |
| Shell script syntax | Passed (`bash -n`) |
| Docker daemon access | Blocked: permission denied on Docker Desktop socket |
| Image builds, container startup, workflow and signal delivery | Not executed; require daemon access |
| Profiling ingestion and Perses rendering | Not verified |

Default host Python is 3.9; containers use Python 3.12. Host checks do not establish container compatibility. The initial bytecode compilation attempted to write to a restricted host cache; syntax was subsequently checked without writing bytecode.

## Reproduce on a Docker-enabled host

Run from the repository root with Docker Compose and Python 3 available:

```bash
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 300
python3 scripts/validate_e2e.py
```

The validator creates five cappuccino orders and consumes inventory. It checks customer HTML, the eight-item menu, enabled scenario controls, all five scenario workflows, exact lifecycle history, a trace containing all three application services for each order, logs correlated by trace ID with span IDs, and stored coffee order metrics in Prometheus. Each eventual check retries for up to 120 seconds; each HTTP call has a 10-second timeout. A failing assertion or timeout exits nonzero. Existing metrics can satisfy the metrics check; it does not prove a counter increment for this run. Trace and log checks use the newly created order IDs.

Optional environment variables: `BASE_URL`, `JAEGER_URL`, `OPENSEARCH_URL`, `PROMETHEUS_URL`, and `TIMEOUT_SECONDS`. Default endpoints match Compose's published localhost ports. The validator needs no Python dependencies. It leaves orders and telemetry available for inspection.

Compose startup readiness alone does not prove telemetry delivery: several backend dependencies use `service_started`. Run the validator after startup to exercise actual ingestion. On failure, collect:

```bash
docker compose ps -a
docker compose logs --since=15m order-api inventory barista otel-collector jaeger data-prepper opensearch prometheus pyroscope
```

For the pinned Python dependencies and full pytest runner, use a virtual environment and install `requirements-dev.txt`, then run `PYTHONPATH=src pytest -q`.

## Complete the manual acceptance checks

- In Jaeger, open a newly created order trace. Confirm Inventory and Barista share its trace ID and inspect the scenario spans listed in README. Check the I/O and database waits are approximately 1.5 seconds.
- Generate repeated orders using `bash scripts/generate_orders.sh`. Allow at least a minute for profile upload, then inspect Pyroscope for samples from each application service. Compare the CPU calculation and temporary allocation workloads; HTTP readiness alone does not prove profiles were ingested.
- Open Perses and configure the datasource connections described in README. No dashboard is provisioned by this repository. Confirm panels can execute queries and render data; container startup alone does not validate plugins or datasources.
- Open the customer UI in a browser, place an order, and verify the tracking interaction. The automated HTML check does not execute JavaScript.

Record order IDs, trace IDs, observed profile labels, relevant query output, container image IDs, and any failures when completing a run. Do not report all four signals validated until the profile checks also pass.

Stop with `docker compose down` to preserve data. `docker compose down -v` deletes stored orders and telemetry; use it only when intentionally resetting the demo.

## Jaeger trace-search 404

The initial validator used the legacy `/api/traces` search route. The validator now uses `/api/v3/traces` with v3 query parameters and parses streamed OTLP `resourceSpans`, grouping services by trace ID. This matches the pinned Jaeger 2.23 API. See the [Jaeger API specification](https://github.com/jaegertracing/jaeger-idl/blob/main/proto/api_v3/query_service.proto).

Three dependency-free regression checks pass:

```bash
python3 -m unittest discover -s tests -p test_validate_e2e.py -v
```

Rerun `python3 scripts/validate_e2e.py`; no container rebuild is needed for this host-side script change. Live verification of the fix remains pending because this session cannot access Docker or localhost Jaeger. If the v3 route also returns 404, check that `JAEGER_URL` points to Jaeger's query HTTP endpoint (default `http://localhost:16686`) and includes any configured base path, without an extra `/api` suffix.

## Trace timeout with `last error: None`

The validator initially expected Docker service names (`inventory`, `barista`) instead of the application's telemetry resource names (`inventory-service`, `barista-service`). This rejected complete traces. The names are corrected, and regression coverage now checks them against the application source. All five validator regression tests pass locally. Incomplete or empty query results now report observed services by trace ID instead of silently returning no match. Live Docker validation remains pending.

Rerun the host-side validator without rebuilding containers:

```bash
python3 scripts/validate_e2e.py
```
