"""Tests for the public coffee menu and inventory recipes."""

from coffee_shop.menu import MENU, ingredients_for, menu_response, price_for


def test_menu_has_eight_coffees() -> None:
    assert len(menu_response()) == 8
    assert {item["id"] for item in menu_response()} == set(MENU)


def test_every_menu_item_has_a_price_and_recipe() -> None:
    for drink in MENU:
        assert price_for(drink, "medium") > 0
        assert ingredients_for(drink, "medium")["coffee_beans"] > 0


def test_size_changes_price_and_ingredient_quantities() -> None:
    assert price_for("latte", "large") > price_for("latte", "medium")
    assert ingredients_for("latte", "large")["milk"] > ingredients_for("latte", "small")["milk"]


def test_black_coffee_does_not_reserve_milk() -> None:
    assert "milk" not in ingredients_for("americano", "medium")
    assert "milk" not in ingredients_for("cold_brew", "medium")
