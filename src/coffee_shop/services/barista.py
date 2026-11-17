"""Barista service: prepares drinks and contains controlled performance scenarios."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import trace

from coffee_shop.models import PrepareRequest
from coffee_shop.performance import allocate_temporary_memory, calculate_recipe
from coffee_shop.telemetry import configure_telemetry, instrument_fastapi

SERVICE_NAME = "barista-service"
telemetry = configure_telemetry(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)
tracer = trace.get_tracer(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    telemetry.tracer_provider.shutdown()
    telemetry.meter_provider.shutdown()
    telemetry.logger_provider.shutdown()


app = FastAPI(title="Coffee Shop Barista Service", version="0.2.0", lifespan=lifespan)
instrument_fastapi(app)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/prepare")
async def prepare_coffee(payload: PrepareRequest):
    started = time.perf_counter()
    outcome = "failed"
    attributes = {
        "drink": payload.drink,
        "size": payload.size,
        "scenario": payload.scenario,
    }
    try:
        with tracer.start_as_current_span("barista.prepare") as span:
            span.set_attribute("coffee.order_id", payload.order_id)
            span.set_attribute("coffee.drink", payload.drink)
            span.set_attribute("coffee.size", payload.size)
            span.set_attribute("coffee.scenario", payload.scenario)
            logger.info(
                "Coffee preparation started",
                extra={"order_id": payload.order_id, **attributes},
            )

            if payload.scenario == "slow_io":
                with tracer.start_as_current_span("barista.simulate_io_wait"):
                    await asyncio.sleep(1.5)
            elif payload.scenario == "slow_cpu":
                iterations = int(os.getenv("SLOW_CPU_ITERATIONS", "8000000"))
                with tracer.start_as_current_span("barista.recipe_calculation") as cpu_span:
                    cpu_span.set_attribute("coffee.cpu_iterations", iterations)
                    calculate_recipe(iterations)
            elif payload.scenario == "slow_memory":
                with tracer.start_as_current_span("barista.temporary_allocation"):
                    temporary = allocate_temporary_memory()
                    allocated_bytes = sum(len(block) for block in temporary)
                    span.set_attribute("coffee.temporary_allocation_bytes", allocated_bytes)
                    await asyncio.sleep(0.75)
                    del temporary
            else:
                # Preparation time makes the customer-facing progress stages observable.
                await asyncio.sleep(1.0)

            outcome = "success"
            telemetry.metrics.preparations.add(1, {**attributes, "outcome": outcome})
            logger.info(
                "Coffee prepared",
                extra={"order_id": payload.order_id, **attributes},
            )
            return {
                "prepared": True,
                "order_id": payload.order_id,
                "drink": payload.drink,
                "size": payload.size,
                "prepared_by": SERVICE_NAME,
            }
    except Exception:
        telemetry.metrics.preparations.add(1, {**attributes, "outcome": outcome})
        logger.exception(
            "Coffee preparation failed", extra={"order_id": payload.order_id, **attributes}
        )
        raise
    finally:
        telemetry.metrics.preparation_duration.record(
            time.perf_counter() - started, {**attributes, "outcome": outcome}
        )
