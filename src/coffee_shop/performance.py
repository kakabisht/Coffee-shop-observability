"""Bounded synthetic workloads used to demonstrate profiling."""


def calculate_recipe(iterations: int) -> int:
    """Run deterministic pure-Python CPU work for a profiling exercise."""
    result = 0
    for value in range(iterations):
        result = (result + (value * value) % 97) % 1_000_003
    return result


def allocate_temporary_memory(
    block_count: int = 2048, block_size: int = 4096
) -> list[bytearray]:
    """Return a bounded allocation that the caller can hold during profiling."""
    return [bytearray(block_size) for _ in range(block_count)]
