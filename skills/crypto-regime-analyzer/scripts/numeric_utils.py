"""Numerically stable helpers and domain limits for market-data calculations."""

import math

# Wide fail-closed bound. Real 8h funding is orders of magnitude smaller,
# while values outside this range can overflow annualization despite being
# finite IEEE-754 inputs.
MAX_ABS_FUNDING_RATE = 1.0


def scaled_mean(values: list[float]) -> float:
    """Return a finite mean without overflowing while summing finite values."""
    if not values:
        raise ValueError("scaled_mean requires at least one value")
    scale = max(abs(value) for value in values)
    if scale == 0:
        return 0.0
    return scale * (math.fsum(value / scale for value in values) / len(values))
