"""Shared request and response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Drink = Literal[
    "espresso",
    "americano",
    "cappuccino",
    "latte",
    "flat_white",
    "mocha",
    "iced_latte",
    "cold_brew",
]
CupSize = Literal["small", "medium", "large"]
Scenario = Literal["normal", "slow_io", "slow_cpu", "slow_db", "slow_memory"]
OrderStatus = Literal[
    "received",
    "checking_inventory",
    "ingredients_reserved",
    "preparing",
    "ready",
    "failed",
]


class OrderRequest(BaseModel):
    drink: Drink = "cappuccino"
    size: CupSize = "medium"
    scenario: Scenario = "normal"


class ReserveRequest(BaseModel):
    order_id: int
    drink: Drink
    size: CupSize
    scenario: Scenario = "normal"


class PrepareRequest(BaseModel):
    order_id: int
    drink: Drink
    size: CupSize
    scenario: Scenario = "normal"


class OrderCreatedResponse(BaseModel):
    order_id: int
    status: OrderStatus
    drink: Drink
    size: CupSize
    price: float
    message: str


class StatusHistoryEntry(BaseModel):
    status: OrderStatus
    message: str
    created_at: datetime


class OrderTrackingResponse(BaseModel):
    order_id: int
    status: OrderStatus
    drink: Drink
    size: CupSize
    price: float
    created_at: datetime
    updated_at: datetime
    history: list[StatusHistoryEntry] = Field(default_factory=list)
