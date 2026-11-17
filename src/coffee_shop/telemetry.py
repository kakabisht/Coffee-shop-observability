"""Shared OpenTelemetry and Pyroscope setup for the demo services."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import pyroscope
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


@dataclass(frozen=True)
class CoffeeMetrics:
    orders_created: Any
    order_duration: Any
    inventory_reservations: Any
    inventory_duration: Any
    preparations: Any
    preparation_duration: Any
    order_status_changes: Any


@dataclass
class TelemetryRuntime:
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider
    metrics: CoffeeMetrics


def configure_telemetry(service_name: str) -> TelemetryRuntime:
    """Configure traces, metrics, and logs to export through the OTel Collector.

    The application uses OTLP/gRPC for all three signals. Pyroscope profiling is
    configured separately because the Python SDK sends profiles directly to it.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "coffee-shop",
            "service.version": "0.1.0",
            "deployment.environment.name": os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
        }
    )

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=5_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    meter = metrics.get_meter("coffee-shop")
    coffee_metrics = CoffeeMetrics(
        orders_created=meter.create_counter(
            "coffee.orders", unit="{order}", description="Coffee order attempts"
        ),
        order_duration=meter.create_histogram(
            "coffee.order.duration", unit="s", description="End-to-end order duration"
        ),
        inventory_reservations=meter.create_counter(
            "coffee.inventory.reservations",
            unit="{reservation}",
            description="Inventory reservation attempts",
        ),
        inventory_duration=meter.create_histogram(
            "coffee.inventory.reservation.duration",
            unit="s",
            description="Inventory reservation duration",
        ),
        preparations=meter.create_counter(
            "coffee.preparations", unit="{preparation}", description="Coffee preparation attempts"
        ),
        preparation_duration=meter.create_histogram(
            "coffee.preparation.duration", unit="s", description="Coffee preparation duration"
        ),
        order_status_changes=meter.create_counter(
            "coffee.order.status_changes", unit="{transition}", description="Order lifecycle status transitions"
        ),
    )

    # Logs. The OpenTelemetry Logs SDK is still marked as development in Python.
    # This tutorial uses the SDK bridge so log records can carry trace/span context.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(isinstance(handler, LoggingHandler) for handler in root_logger.handlers):
        root_logger.addHandler(
            LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        )
    if not any(type(handler) is logging.StreamHandler for handler in root_logger.handlers):
        root_logger.addHandler(logging.StreamHandler())

    # Automatic HTTP instrumentation. FastAPI server spans are attached per app
    # below; HTTPX instrumentation injects W3C trace context into service calls.
    HTTPXClientInstrumentor().instrument()

    # Profiling is independent from the OpenTelemetry Collector pipeline.
    if os.getenv("PYROSCOPE_ENABLED", "true").lower() == "true":
        try:
            pyroscope.configure(
                application_name=f"coffee-shop.{service_name}",
                server_address=os.getenv(
                    "PYROSCOPE_SERVER_ADDRESS", "http://pyroscope:4040"
                ),
                sample_rate=100,
                cpu_enabled=True,
                mem_enabled=True,
                tags={"service": service_name, "environment": "local"},
            )
        except Exception:
            logging.getLogger(__name__).exception("Could not start Pyroscope profiler")

    return TelemetryRuntime(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        metrics=coffee_metrics,
    )


def instrument_fastapi(app: Any) -> None:
    """Add server-side HTTP spans to a FastAPI application."""
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz")
