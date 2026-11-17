# Portfolio extension: Coffee Shop Observability Lab

## Recommended placement

Add the project as a fourth entry on the existing Projects page:

- Project card: **Coffee Shop Observability Lab**
- Detail page: `/projects/coffee-shop-observability`
- Live customer demo: `https://coffee.hridyesh.dev`

Keep the portfolio case study and the running application as separate surfaces. The portfolio page explains the engineering decisions; the app lets visitors place and track an order.

## Suggested page structure

1. **The problem:** A customer asks, “Where is my coffee?” The developer needs to answer a different question: “What happened while the order moved through the system?”
2. **Try the application:** Embed or link to the coffee-shop app. Let visitors place a sample order and follow its lifecycle.
3. **Follow the telemetry:** Explain one order as four correlated views:
   - Traces: the order's path across the Order, Inventory, and Barista services (Jaeger).
   - Metrics: order rate, failures, inventory reservation time, and preparation duration (Prometheus).
   - Logs: status changes, warnings, and errors with trace context (OpenSearch).
   - Profiles: CPU and memory usage in the Python services (Pyroscope).
4. **Architecture:** Show the application, OpenTelemetry Collector, storage backends, and Perses dashboard.
5. **Open source first, Dash0 next:** Explain that the application uses OpenTelemetry instrumentation and can export the same signals to Dash0. Compare operational setup and investigation workflows, not just feature checklists.
6. **Source and write-up:** Link to the repository, the article, and a short run-it-locally guide.

## Safe hosting boundary

- Host the customer UI and API separately from the personal site, for example on `coffee.hridyesh.dev`.
- Keep PostgreSQL, the OpenTelemetry Collector, Jaeger, Prometheus, OpenSearch, Data Prepper, Pyroscope, and Perses private or behind authentication.
- Do not embed private backend credentials in browser code.
- For public visitors, show sanitized traces, example metrics, and redacted logs. A curated trace view or pre-recorded telemetry is safer than public access to production observability backends.
- Disable the developer performance scenarios on the public deployment (`ENABLE_DEMO_SCENARIOS=false`).
- Add request rate limits, resource limits, and a periodic reset for demo data before exposing the order API publicly.
- Do not collect customer names, email addresses, payment information, or other personal data in this learning project.

## Why this project belongs on the portfolio

It demonstrates a complete developer-facing system: a customer workflow, multi-service Python application, OpenTelemetry instrumentation, open-source observability backends, profiling, and a clear comparison with an integrated observability platform. The case study should emphasize the design decisions and the debugging walkthrough, not claim production readiness.
