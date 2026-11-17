"""Coffee menu, prices, and ingredient requirements for the demo shop."""

from __future__ import annotations

from decimal import Decimal

MENU: dict[str, dict[str, object]] = {
    "espresso": {
        "name": "Espresso",
        "description": "A short, rich shot with a smooth crema.",
        "category": "Classics",
        "price": Decimal("2.80"),
        "ingredients": {"coffee_beans": 18},
    },
    "americano": {
        "name": "Americano",
        "description": "Espresso softened with hot water.",
        "category": "Classics",
        "price": Decimal("3.20"),
        "ingredients": {"coffee_beans": 18},
    },
    "cappuccino": {
        "name": "Cappuccino",
        "description": "Espresso, steamed milk, and a cloud of foam.",
        "category": "Milk coffee",
        "price": Decimal("4.20"),
        "ingredients": {"coffee_beans": 18, "milk": 120},
    },
    "latte": {
        "name": "Caffè latte",
        "description": "A mellow espresso with plenty of steamed milk.",
        "category": "Milk coffee",
        "price": Decimal("4.50"),
        "ingredients": {"coffee_beans": 18, "milk": 180},
    },
    "flat_white": {
        "name": "Flat white",
        "description": "A double espresso with silky microfoam.",
        "category": "Milk coffee",
        "price": Decimal("4.60"),
        "ingredients": {"coffee_beans": 20, "milk": 140},
    },
    "mocha": {
        "name": "Mocha",
        "description": "Espresso, chocolate, and steamed milk.",
        "category": "Specialty",
        "price": Decimal("5.10"),
        "ingredients": {"coffee_beans": 18, "milk": 150, "chocolate_syrup": 25},
    },
    "iced_latte": {
        "name": "Iced latte",
        "description": "Espresso and cold milk poured over ice.",
        "category": "Cold coffee",
        "price": Decimal("4.80"),
        "ingredients": {"coffee_beans": 18, "milk": 150, "ice": 120},
    },
    "cold_brew": {
        "name": "Cold brew",
        "description": "Slow-steeped coffee served chilled and smooth.",
        "category": "Cold coffee",
        "price": Decimal("4.40"),
        "ingredients": {"coffee_beans": 25, "ice": 100},
    },
}

SIZE_MULTIPLIERS = {"small": Decimal("0.80"), "medium": Decimal("1.00"), "large": Decimal("1.25")}


def menu_response() -> list[dict[str, object]]:
    """Return a JSON-safe menu for the customer UI."""
    return [
        {
            "id": drink_id,
            "name": str(item["name"]),
            "description": str(item["description"]),
            "category": str(item["category"]),
            "price": float(item["price"]),
        }
        for drink_id, item in MENU.items()
    ]


def price_for(drink: str, size: str) -> Decimal:
    """Calculate the menu price for a drink and cup size."""
    base_price = MENU[drink]["price"]
    assert isinstance(base_price, Decimal)
    return (base_price * SIZE_MULTIPLIERS[size]).quantize(Decimal("0.01"))


def ingredients_for(drink: str, size: str) -> dict[str, int]:
    """Return size-adjusted ingredient quantities for an order."""
    recipe = MENU[drink]["ingredients"]
    assert isinstance(recipe, dict)
    multiplier = SIZE_MULTIPLIERS[size]
    return {name: int(Decimal(amount) * multiplier) for name, amount in recipe.items()}
