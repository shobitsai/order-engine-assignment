"""The hard requirement, exercised in bulk.

Plain seeded ``random`` rather than hypothesis: zero dependencies, fully
deterministic, and a failure is reproducible from the seed alone. Each random
order is checked against every reconciliation invariant (I1–I9 in README).
"""

import random
from dataclasses import fields, replace
from decimal import Decimal

from orderengine import (
    Charge,
    Discount,
    DiscountKind,
    LineItem,
    Order,
    TaxComponent,
    compute_order,
)

RATES = [Decimal(r) for r in ("0", "2.5", "5", "9", "12", "18", "28")]
MONEY_FIELDS = {
    "gross", "item_discount", "order_discount_alloc", "taxable_base", "tax_total",
    "line_total", "amount", "total", "items_gross", "item_discount_total",
    "order_discount_total", "discount_total", "charges_total", "grand_total",
}


def rand_taxes(rng, prefix):
    rate = rng.choice(RATES)
    if rng.random() < 0.5:
        half = rate / 2
        return (TaxComponent(f"{prefix}A", half), TaxComponent(f"{prefix}B", half))
    return (TaxComponent(f"{prefix}A", rate),)


def rand_discount(rng, max_fixed_paise):
    roll = rng.random()
    if roll < 0.5:
        return None
    if roll < 0.75:
        return Discount(DiscountKind.PERCENT, Decimal(rng.randint(0, 100)))
    return Discount(DiscountKind.FIXED, Decimal(rng.randint(0, max_fixed_paise)).scaleb(-2))


def rand_order(rng):
    items = []
    for i in range(rng.randint(1, 6)):
        price_paise = rng.randint(0, 100_000)
        qty = rng.randint(1, 5)
        items.append(
            LineItem(
                name=f"item{i}",
                unit_price=Decimal(price_paise).scaleb(-2),
                quantity=qty,
                taxes=rand_taxes(rng, "T"),
                price_includes_tax=rng.random() < 0.5,
                discount=rand_discount(rng, price_paise * qty),
            )
        )
    charges = [
        Charge(
            name=f"charge{i}",
            amount=Decimal(rng.randint(0, 20_000)).scaleb(-2),
            taxes=rand_taxes(rng, "C") if rng.random() < 0.7 else (),
            amount_includes_tax=rng.random() < 0.5,
        )
        for i in range(rng.randint(0, 3))
    ]
    order = Order(items=tuple(items), charges=tuple(charges))
    # Order discount sized against the actual post-item-discount subtotal.
    if rng.random() < 0.5:
        base = compute_order(order)
        subtotal = base.items_gross - base.item_discount_total
        disc = (
            Discount(DiscountKind.PERCENT, Decimal(rng.randint(0, 100)))
            if rng.random() < 0.5
            else Discount(DiscountKind.FIXED, Decimal(rng.randint(0, subtotal)).scaleb(-2))
        )
        order = replace(order, order_discount=disc)
    return order


def check_invariants(order, bd):
    # I1: per-line and per-charge internal reconciliation
    for line in bd.lines:
        assert line.tax_total == sum(t.amount for t in line.taxes)
        assert line.taxable_base + line.tax_total == line.line_total
    for charge in bd.charges:
        assert charge.taxable_base + sum(t.amount for t in charge.taxes) == charge.total
    # I2: discount conservation
    assert sum(l.order_discount_alloc for l in bd.lines) == bd.order_discount_total
    assert bd.discount_total == bd.item_discount_total + bd.order_discount_total
    # I3: quoted-domain identity
    payables = [l.gross - l.item_discount - l.order_discount_alloc for l in bd.lines]
    assert bd.items_gross - bd.discount_total == sum(payables)
    # I4: per-component tax conservation
    expected: dict[tuple[str, Decimal], int] = {}
    for holder in (*bd.lines, *bd.charges):
        for t in holder.taxes:
            key = (t.name, t.rate)
            expected[key] = expected.get(key, 0) + t.amount
    assert {(t.name, t.rate): t.amount for t in bd.tax_totals} == expected
    assert bd.tax_total == sum(expected.values())
    # I5: grand total agrees when derived two independent ways
    grand_a = sum(l.line_total for l in bd.lines) + sum(c.total for c in bd.charges)
    grand_b = (
        sum(l.taxable_base for l in bd.lines)
        + sum(c.taxable_base for c in bd.charges)
        + bd.tax_total
    )
    assert bd.grand_total == grand_a == grand_b
    # I7: inclusive quotes honoured exactly (net of discounts)
    for item, line, payable in zip(order.items, bd.lines, payables):
        if item.price_includes_tax:
            assert line.line_total == payable
    # I9: non-negativity everywhere
    for line in bd.lines:
        assert min(line.gross, line.item_discount, line.order_discount_alloc,
                   line.taxable_base, line.tax_total, line.line_total) >= 0
        assert all(t.amount >= 0 for t in line.taxes)
    for charge in bd.charges:
        assert charge.taxable_base >= 0 and charge.total >= 0


def test_thousand_random_orders_reconcile():
    rng = random.Random(42)
    for i in range(1000):
        order = rand_order(rng)
        bd = compute_order(order)
        try:
            check_invariants(order, bd)
        except AssertionError:
            raise AssertionError(f"invariant failed for case {i}: {order!r}")


def _walk_money_fields(obj):
    if isinstance(obj, tuple):
        for element in obj:
            yield from _walk_money_fields(element)
    elif hasattr(obj, "__dataclass_fields__"):
        for f in fields(obj):
            value = getattr(obj, f.name)
            if f.name in MONEY_FIELDS:
                yield f.name, value
            else:
                yield from _walk_money_fields(value)


def test_every_output_money_field_is_int_and_results_deterministic():
    rng = random.Random(99)
    for _ in range(50):
        order = rand_order(rng)
        bd = compute_order(order)
        for name, value in _walk_money_fields(bd):
            assert type(value) is int, f"{name} is {type(value).__name__}, not int"
        assert compute_order(order) == bd  # I10: determinism, field for field


def test_metamorphic_zero_amount_charge_and_zero_rate_tax_change_nothing():
    rng = random.Random(7)
    for _ in range(100):
        order = rand_order(rng)
        before = compute_order(order).grand_total

        with_zero_charge = replace(
            order, charges=order.charges + (Charge("free", Decimal("0.00")),)
        )
        assert compute_order(with_zero_charge).grand_total == before

        first = order.items[0]
        padded = replace(first, taxes=first.taxes + (TaxComponent("ZERO", Decimal("0")),))
        with_zero_rate = replace(order, items=(padded,) + order.items[1:])
        assert compute_order(with_zero_rate).grand_total == before
