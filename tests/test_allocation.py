import random
from decimal import Decimal

import pytest

from orderengine import ValidationError, allocate


def test_pinned_tie_breaking_lowest_index_wins():
    # Equal remainders, equal weights: the leftover paisa goes to index 0.
    assert allocate(100, [1, 1, 1]) == [34, 33, 33]


def test_awkward_split_sums_exactly():
    assert allocate(7, [3, 3, 3]) == [3, 2, 2]
    assert sum(allocate(7, [3, 3, 3])) == 7


def test_zero_total_and_single_weight():
    assert allocate(0, [5, 5]) == [0, 0]
    assert allocate(1234, [7]) == [1234]
    assert allocate(0, []) == []


def test_zero_weights_with_positive_total_rejected():
    with pytest.raises(ValidationError):
        allocate(10, [0, 0])
    with pytest.raises(ValidationError):
        allocate(10, [])


def test_decimal_rate_weights():
    # An inclusive tax pot of 15.25 split across CGST/SGST at 2.5% each.
    assert allocate(1525, [Decimal("2.5"), Decimal("2.5")]) == [763, 762]


def test_zero_weight_line_never_receives():
    parts = allocate(100, [0, 1, 1])
    assert parts[0] == 0
    assert sum(parts) == 100


def test_property_sum_exact_and_each_part_within_one_of_ideal():
    rng = random.Random(42)
    for _ in range(500):
        n = rng.randint(1, 8)
        weights = [rng.randint(0, 10_000) for _ in range(n)]
        if sum(weights) == 0:
            weights[0] = 1
        total = rng.randint(0, 10_000_000)
        parts = allocate(total, weights)
        assert sum(parts) == total  # the hard requirement
        weight_sum = sum(weights)
        for part, weight in zip(parts, weights):
            ideal = Decimal(total) * weight / weight_sum
            assert abs(Decimal(part) - ideal) < 1
