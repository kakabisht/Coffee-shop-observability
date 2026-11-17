"""Dependency-free checks for the synthetic profiling workloads."""

from coffee_shop.performance import allocate_temporary_memory, calculate_recipe


def test_recipe_is_deterministic() -> None:
    assert calculate_recipe(100) == calculate_recipe(100)


def test_recipe_returns_an_integer() -> None:
    assert isinstance(calculate_recipe(10), int)


def test_temporary_memory_allocation_is_bounded_and_held_by_caller() -> None:
    temporary = allocate_temporary_memory(2, 1024)
    assert len(temporary) == 2
    assert sum(len(block) for block in temporary) == 2048
