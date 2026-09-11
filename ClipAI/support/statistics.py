from __future__ import annotations

import math
from collections.abc import Sequence


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return the nearest-rank percentile for a nonempty numeric sequence."""
    if not values:
        raise ValueError("values must not be empty")
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]
