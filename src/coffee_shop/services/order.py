"""Order API: serves the customer UI and coordinates the order lifecycle."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from coffee_shop.database import create_pool_with_retry, record_order_status, traced_db_call
from coffee_shop.menu import menu_response, price_for
from coffee_shop.models import (
    OrderCreatedResponse,
    OrderRequest,
    OrderTrackingResponse,
    StatusHistoryEntry,
)
from coffee_shop.telemetry import configure_telemetry, instrument_fastapi

SERVICE_NAME = "order-api"
telemetry = configure_telemetry(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)
tracer = trace.get_tracer(SERVICE_NAME)

INVENTORY_URL = "http://inventory:8000"
BARISTA_URL = "http://barista:8000"
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

STATUS_MESSAGES = {
    "received": "We received your order.",
    "checking_inventory": "The team is checking your ingredients.",
    "ingredients_reserved": "Your ingredients are ready for the barista.",
    "preparing": "Your coffee is being prepared.",
    "ready": "Your coffee is ready for pickup. Enjoy!",
    "failed": "We couldn't complete your order. Please ask a barista for help.",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool_with_retry()
    await app.state.pool.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id BIGSERIAL PRIMARY KEY,
            drink TEXT NOT NULL,
            size TEXT NOT NULL,
            scenario TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL,
            price NUMERIC(8, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Additive migration for databases created by the previous starter version.
    await app.state.pool.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC(8, 2) NOT NULL DEFAULT 0"
    )
    await app.state.pool.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    await app.state.pool.execute(
        """
        CREATE TABLE IF NOT EXISTS order_status_history (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await app.state.pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_order_status_history_order_id "
        "ON order_status_history(order_id, created_at)"
    )
    app.state.http = httpx.AsyncClient(timeout=12.0)
    yield
    await app.state.http.aclose()
    await app.state.pool.close()
    telemetry.tracer_provider.shutdown()
    telemetry.meter_provider.shutdown()
    telemetry.logger_provider.shutdown()


app = FastAPI(title="The Daily Grind | Coffee Shop API", version="0.2.0", lifespan=lifespan)
instrument_fastapi(app)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/menu")
async def get_menu():
    return {"items": menu_response(), "sizes": ["small", "medium", "large"]}


@app.get("/config")
async def get_public_config():
    """Expose only customer-UI feature flags, never backend credentials."""
    return {"demo_scenarios_enabled": os.getenv("ENABLE_DEMO_SCENARIOS", "false").lower() == "true"}


async def process_order(order_id: int, payload: OrderRequest, pool, http: httpx.AsyncClient) -> None:
    """Run the order workflow after the API has returned the order ID."""
    started = time.perf_counter()
    attributes = {
        "coffee.drink": payload.drink,
        "coffee.size": payload.size,
        "coffee.scenario": payload.scenario,
        "coffee.order_id": order_id,
    }
    outcome = "failed"

    try:
        with tracer.start_as_current_span("order.process") as span:
            span.set_attributes(attributes)

            await record_order_status(
                pool, order_id, "checking_inventory", STATUS_MESSAGES["checking_inventory"]
            )
            telemetry.metrics.order_status_changes.add(
                1, {"status": "checking_inventory", "drink": payload.drink}
            )
            logger.info(
                "Checking inventory for order",
                extra={"order_id": order_id, "drink": payload.drink},
            )

            inventory_response = await http.post(
                f"{INVENTORY_URL}/reserve",
                json={
                    "order_id": order_id,
                    "drink": payload.drink,
                    "size": payload.size,
                    "scenario": payload.scenario,
                },
            )
            inventory_response.raise_for_status()

            await record_order_status(
                pool, order_id, "ingredients_reserved", STATUS_MESSAGES["ingredients_reserved"]
            )
            telemetry.metrics.order_status_changes.add(
                1, {"status": "ingredients_reserved", "drink": payload.drink}
            )

            await record_order_status(pool, order_id, "preparing", STATUS_MESSAGES["preparing"])
            telemetry.metrics.order_status_changes.add(
                1, {"status": "preparing", "drink": payload.drink}
            )
            logger.info(
                "Barista started preparing order",
                extra={"order_id": order_id, "drink": payload.drink},
            )

            preparation_response = await http.post(
                f"{BARISTA_URL}/prepare",
                json={
                    "order_id": order_id,
                    "drink": payload.drink,
                    "size": payload.size,
                    "scenario": payload.scenario,
                },
            )
            preparation_response.raise_for_status()

            await record_order_status(pool, order_id, "ready", STATUS_MESSAGES["ready"])
            telemetry.metrics.order_status_changes.add(
                1, {"status": "ready", "drink": payload.drink}
            )
            outcome = "success"
            span.set_status(Status(StatusCode.OK))
            logger.info(
                "Order ready for pickup",
                extra={"order_id": order_id, "drink": payload.drink, "size": payload.size},
            )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        logger.error(
            "Order workflow failed in a downstream service",
            extra={"order_id": order_id, "status_code": exc.response.status_code, "detail": detail},
        )
        await record_order_status(pool, order_id, "failed", STATUS_MESSAGES["failed"])
        telemetry.metrics.order_status_changes.add(
            1, {"status": "failed", "drink": payload.drink}
        )
    except Exception:
        logger.exception("Order workflow failed", extra={"order_id": order_id})
        try:
            await record_order_status(pool, order_id, "failed", STATUS_MESSAGES["failed"])
            telemetry.metrics.order_status_changes.add(
                1, {"status": "failed", "drink": payload.drink}
            )
        except Exception:
            logger.exception("Could not persist failed order status", extra={"order_id": order_id})
    finally:
        telemetry.metrics.order_duration.record(
            time.perf_counter() - started,
            {"drink": payload.drink, "size": payload.size, "scenario": payload.scenario, "outcome": outcome},
        )


@app.post("/orders", response_model=OrderCreatedResponse, status_code=202)
async def create_order(
    payload: OrderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Create an order, return its ID, and continue preparation in the background."""
    if payload.scenario != "normal" and os.getenv("ENABLE_DEMO_SCENARIOS", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Demo scenarios are disabled.")

    order_price = price_for(payload.drink, payload.size)
    attributes = {
        "drink": payload.drink,
        "size": payload.size,
        "scenario": payload.scenario,
    }

    with tracer.start_as_current_span("order.create") as span:
        span.set_attributes(
            {
                "coffee.drink": payload.drink,
                "coffee.size": payload.size,
                "coffee.scenario": payload.scenario,
                "coffee.price": float(order_price),
            }
        )

        async def insert_order():
            return await request.app.state.pool.fetchrow(
                "INSERT INTO orders (drink, size, scenario, status, price) "
                "VALUES ($1, $2, $3, 'received', $4) RETURNING id, created_at",
                payload.drink,
                payload.size,
                payload.scenario,
                order_price,
            )

        record = await traced_db_call("INSERT", insert_order, table="orders")
        order_id = int(record["id"])
        span.set_attribute("coffee.order_id", order_id)

        await request.app.state.pool.execute(
            "INSERT INTO order_status_history (order_id, status, message) VALUES ($1, 'received', $2)",
            order_id,
            STATUS_MESSAGES["received"],
        )
        telemetry.metrics.orders_created.add(1, {**attributes, "outcome": "accepted"})
        telemetry.metrics.order_status_changes.add(
            1, {"status": "received", "drink": payload.drink}
        )
        logger.info(
            "Order received",
            extra={"order_id": order_id, **attributes, "price": float(order_price)},
        )

    background_tasks.add_task(
        process_order,
        order_id,
        payload,
        request.app.state.pool,
        request.app.state.http,
    )

    return OrderCreatedResponse(
        order_id=order_id,
        status="received",
        drink=payload.drink,
        size=payload.size,
        price=float(order_price),
        message="Your order is in. Follow its progress below.",
    )


@app.get("/orders/{order_id}", response_model=OrderTrackingResponse)
async def get_order(order_id: int, request: Request):
    """Return the current order state and its customer-visible status history."""
    async def fetch_order():
        return await request.app.state.pool.fetchrow(
            "SELECT id, drink, size, status, price, created_at, updated_at "
            "FROM orders WHERE id = $1",
            order_id,
        )

    order = await traced_db_call("SELECT", fetch_order, table="orders")
    if order is None:
        raise HTTPException(status_code=404, detail="We couldn't find that order.")

    async def fetch_history():
        return await request.app.state.pool.fetch(
            "SELECT status, message, created_at FROM order_status_history "
            "WHERE order_id = $1 ORDER BY created_at ASC, id ASC",
            order_id,
        )

    history_rows = await traced_db_call(
        "SELECT", fetch_history, table="order_status_history"
    )
    return OrderTrackingResponse(
        order_id=int(order["id"]),
        status=order["status"],
        drink=order["drink"],
        size=order["size"],
        price=float(order["price"]),
        created_at=order["created_at"],
        updated_at=order["updated_at"],
        history=[
            StatusHistoryEntry(
                status=row["status"], message=row["message"], created_at=row["created_at"]
            )
            for row in history_rows
        ],
    )


# Serve the customer-facing UI from the same origin as the API.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
