"""Largest-remainder allocation (Hamilton method).

The single primitive used everywhere a rounded distribution must sum EXACTLY
to a fixed total: splitting an order-level discount across line items, and
splitting an inclusive line's tax pot across tax components.

Guarantees:
- ``sum(allocate(total, weights)) == total`` exactly, always.
- Each part differs from its exact proportional share by strictly less than 1.
- Deterministic: leftover paise go to the largest fractional remainders,
  ties broken by larger weight, then lower index.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from .errors import ValidationError
from .money import Paise


def allocate(total: Paise, weights: Sequence[int | Decimal]) -> list[Paise]:
    if total < 0:
        return [-part for part in allocate(-total, weights)]

    n = len(weights)
    if n == 0:
        if total != 0:
            raise ValidationError("cannot allocate a non-zero total over no weights")
        return []

    ws: list[Decimal] = []
    for i, w in enumerate(weights):
        if isinstance(w, bool) or not isinstance(w, (int, Decimal)):
            raise TypeError(f"allocation weight {i}: expected int or Decimal, got {type(w).__name__}")
        d = w if isinstance(w, Decimal) else Decimal(w)
        if d < 0:
            raise ValidationError(f"allocation weight {i} is negative: {d}")
        ws.append(d)

    weight_sum = sum(ws)
    if weight_sum == 0:
        if total != 0:
            raise ValidationError("cannot allocate a non-zero total when all weights are zero")
        return [0] * n

    # Exact proportional shares at full Decimal precision, floored; the handful
    # of leftover paise (< n) go one each to the largest fractional remainders.
    shares = [Decimal(total) * w / weight_sum for w in ws]
    parts = [int(share) for share in shares]  # truncation == floor (non-negative)
    leftover = total - sum(parts)
    assert 0 <= leftover <= n, "largest-remainder invariant broken"

    by_remainder = sorted(
        range(n), key=lambda i: (shares[i] - parts[i], ws[i], -i), reverse=True
    )
    for i in by_remainder[:leftover]:
        parts[i] += 1
    return parts
