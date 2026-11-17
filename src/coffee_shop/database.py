"""Database helpers shared by the coffee shop services."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

import asyncpg
from opentelemetry import trace
from opentelemetry.trace import SpanKind

T = TypeVar("T")


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://coffee:coffee-local-only@postgres:5432/coffee_shop",
    )


async def create_pool_with_retry(*, attempts: int = 30) -> asyncpg.Pool:
    """Wait for PostgreSQL during local Compose startup."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await asyncpg.create_pool(database_url(), min_size=1, max_size=5)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(min(1 + attempt * 0.25, 3))
    raise RuntimeError("Could not connect to PostgreSQL after startup retries") from last_error


async def traced_db_call(
    operation: str,
    callback: Callable[[], Awaitable[T]],
    *,
    table: str,
) -> T:
    """Create a database client span around a database operation."""
    tracer = trace.get_tracer("coffee-shop.database")
    with tracer.start_as_current_span(
        f"postgresql.{operation.lower()}", kind=SpanKind.CLIENT
    ) as span:
        span.set_attribute("db.system.name", "postgresql")
        span.set_attribute("db.operation.name", operation.upper())
        span.set_attribute("db.collection.name", table)
        span.set_attribute("server.address", "postgres")
        return await callback()


async def record_order_status(
    pool: asyncpg.Pool,
    order_id: int,
    status: str,
    message: str,
) -> None:
    """Persist the current order status and append an immutable history entry."""
    tracer = trace.get_tracer("coffee-shop.order-lifecycle")
    with tracer.start_as_current_span("order.status.update") as span:
        span.set_attribute("coffee.order_id", order_id)
        span.set_attribute("coffee.order.status", status)

        async def persist_status() -> None:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "UPDATE orders SET status = $2, updated_at = NOW() WHERE id = $1",
                        order_id,
                        status,
                    )
                    await connection.execute(
                        "INSERT INTO order_status_history (order_id, status, message) "
                        "VALUES ($1, $2, $3)",
                        order_id,
                        status,
                        message,
                    )

        await traced_db_call("UPDATE", persist_status, table="orders")
