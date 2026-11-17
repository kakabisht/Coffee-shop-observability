"""Inventory service: checks and reserves ingredients in PostgreSQL."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from opentelemetry import trace

from coffee_shop.database import create_pool_with_retry, traced_db_call
from coffee_shop.menu import ingredients_for
from coffee_shop.models import ReserveRequest
from coffee_shop.telemetry import configure_telemetry, instrument_fastapi

SERVICE_NAME = "inventory-service"
telemetry = configure_telemetry(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)
tracer = trace.get_tracer(SERVICE_NAME)

INITIAL_INVENTORY = [
    ("coffee_beans", 12000, "grams"),
    ("milk", 30000, "millilitres"),
    ("chocolate_syrup", 5000, "millilitres"),
    ("ice", 20000, "grams"),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool_with_retry()
    await app.state.pool.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            item TEXT PRIMARY KEY,
            quantity INTEGER NOT NULL CHECK (quantity >= 0),
            unit TEXT NOT NULL
        )
        """
    )
    await app.state.pool.executemany(
        "INSERT INTO inventory (item, quantity, unit) VALUES ($1, $2, $3) "
        "ON CONFLICT (item) DO NOTHING",
        INITIAL_INVENTORY,
    )
    yield
    await app.state.pool.close()
    telemetry.tracer_provider.shutdown()
    telemetry.meter_provider.shutdown()
    telemetry.logger_provider.shutdown()


app = FastAPI(title="Coffee Shop Inventory Service", version="0.2.0", lifespan=lifespan)
instrument_fastapi(app)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/reserve")
async def reserve_inventory(payload: ReserveRequest, request: Request):
    started = time.perf_counter()
    outcome = "failed"
    attributes = {
        "drink": payload.drink,
        "size": payload.size,
        "scenario": payload.scenario,
    }
    requirements = ingredients_for(payload.drink, payload.size)

    try:
        with tracer.start_as_current_span("inventory.reserve") as span:
            span.set_attribute("coffee.order_id", payload.order_id)
            span.set_attribute("coffee.drink", payload.drink)
            span.set_attribute("coffee.size", payload.size)
            span.set_attribute("coffee.ingredient_count", len(requirements))

            if payload.scenario == "slow_db":
                async def simulate_database_wait():
                    async with request.app.state.pool.acquire() as connection:
                        await connection.fetchval("SELECT pg_sleep(1.5)")

                await traced_db_call("SELECT", simulate_database_wait, table="pg_sleep")

            async def reserve_items():
                async with request.app.state.pool.acquire() as connection:
                    async with connection.transaction():
                        remaining = {}
                        for item, amount in requirements.items():
                            row = await connection.fetchrow(
                                "UPDATE inventory SET quantity = quantity - $2 "
                                "WHERE item = $1 AND quantity >= $2 RETURNING quantity, unit",
                                item,
                                amount,
                            )
                            if row is None:
                                raise HTTPException(
                                    status_code=409,
                                    detail=f"Insufficient inventory for {item}",
                                )
                            remaining[item] = {
                                "quantity": row["quantity"],
                                "unit": row["unit"],
                            }
                        return remaining

            remaining = await traced_db_call("UPDATE", reserve_items, table="inventory")
            outcome = "success"
            telemetry.metrics.inventory_reservations.add(
                1, {**attributes, "outcome": outcome}
            )
            logger.info(
                "Ingredients reserved",
                extra={
                    "order_id": payload.order_id,
                    "drink": payload.drink,
                    "ingredients": ",".join(requirements),
                },
            )
            span.set_attribute("coffee.inventory.result", "reserved")
            return {"reserved": True, "order_id": payload.order_id, "remaining": remaining}
    except HTTPException as exc:
        telemetry.metrics.inventory_reservations.add(
            1, {**attributes, "outcome": outcome}
        )
        logger.warning(
            "Inventory reservation rejected",
            extra={"order_id": payload.order_id, "reason": exc.detail},
        )
        raise
    except Exception as exc:
        telemetry.metrics.inventory_reservations.add(
            1, {**attributes, "outcome": outcome}
        )
        logger.exception(
            "Inventory reservation failed", extra={"order_id": payload.order_id}
        )
        raise HTTPException(status_code=500, detail="Inventory operation failed") from exc
    finally:
        telemetry.metrics.inventory_duration.record(
            time.perf_counter() - started, {**attributes, "outcome": outcome}
        )
