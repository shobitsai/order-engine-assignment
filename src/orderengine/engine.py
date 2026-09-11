"""The calculation pipeline.

Precision is dropped in exactly four places, each marked [ROUND] or [ALLOC]
below, and each immediately reconciled (by exact subtraction or by
largest-remainder allocation). Everything else is exact integer arithmetic,
so order-level totals reconcile BY CONSTRUCTION, never by adjustment.

Pipeline for compute_order():
  1. line gross      = unit_price_paise * quantity            (exact)
  2. item discount                                            [ROUND once per line, percent only]
  3. order discount pot                                       [ROUND once], then
     per-line shares via largest remainder                    [ALLOC]
  4. per-line tax:
       exclusive: each component rounded on the discounted base  [ROUND per component]
       inclusive: base = divide-and-round, tax pot = payable - base (exact),
                  pot split across components                    [ROUND base] + [ALLOC]
  5. charges: step 4 with no discounts
  6. aggregation: pure integer sums
"""

from __future__ import annotations

from decimal import Decimal

from .allocation import allocate
from .errors import ValidationError
from .models import (
    Charge,
    ChargeBreakdown,
    Discount,
    DiscountKind,
    LineBreakdown,
    LineItem,
    Order,
    OrderBreakdown,
    TaxComponent,
    TaxLine,
)
from .money import Paise, round_paise, to_paise

_HUNDRED = Decimal(100)


def _discount_amount(discount: Discount | None, base: Paise, *, owner: str) -> Paise:
    """Money value of a discount against an integer base. No silent clamping."""
    if discount is None:
        return 0
    if discount.kind is DiscountKind.FIXED:
        amount = to_paise(discount.value, field=f"{owner} fixed discount")
    else:
        # [ROUND] one HALF_UP per discount application.
        amount = round_paise(Decimal(base) * discount.value / _HUNDRED)
    if amount > base:
        raise ValidationError(
            f"{owner}: discount ({amount} paise) exceeds the amount it applies to ({base} paise)"
        )
    return amount


def _exclusive_taxes(base: Paise, taxes: tuple[TaxComponent, ...]) -> tuple[TaxLine, ...]:
    """Tax-exclusive: each component is rounded independently on the same base.

    [ROUND per line, per component] — this is the engine's rounding unit.
    The line's total tax is *defined* as the sum of these rounded components;
    a combined rate is never computed, so there is nothing to reconcile.
    """
    return tuple(
        TaxLine(t.name, t.rate, round_paise(Decimal(base) * t.rate / _HUNDRED)) for t in taxes
    )


def _split_inclusive(
    amount: Paise, taxes: tuple[TaxComponent, ...]
) -> tuple[Paise, tuple[TaxLine, ...]]:
    """Split a tax-inclusive amount into (base, tax components).

    base = round(amount * 100 / (100 + total_rate))   [ROUND]
    pot  = amount - base                              exact by subtraction
    The base absorbs the rounding, so base + taxes == amount to the paisa.
    The pot is split across components by rate via largest remainder [ALLOC].
    """
    total_rate = sum((t.rate for t in taxes), Decimal(0))
    if total_rate == 0:
        return amount, tuple(TaxLine(t.name, t.rate, 0) for t in taxes)
    base = round_paise(Decimal(amount) * _HUNDRED / (_HUNDRED + total_rate))
    pot = amount - base
    parts = allocate(pot, [t.rate for t in taxes])
    return base, tuple(TaxLine(t.name, t.rate, p) for t, p in zip(taxes, parts))


def _charge_breakdown(charge: Charge) -> ChargeBreakdown:
    amount = to_paise(charge.amount, field=f"charge {charge.name!r} amount")
    if charge.amount_includes_tax:
        base, tax_lines = _split_inclusive(amount, charge.taxes)
    else:
        base = amount
        tax_lines = _exclusive_taxes(base, charge.taxes)
    total = base + sum(t.amount for t in tax_lines)
    return ChargeBreakdown(name=charge.name, taxable_base=base, taxes=tax_lines, total=total)


def compute_order(order: Order) -> OrderBreakdown:
    if not isinstance(order, Order):
        raise ValidationError(f"compute_order expects an Order, got {type(order).__name__}")
    items = order.items

    # -- Steps 1 & 2: line gross (exact integer multiply) and item discounts.
    grosses: list[Paise] = []
    item_discounts: list[Paise] = []
    nets: list[Paise] = []  # quoted-basis amount after item discount
    for item in items:
        gross = to_paise(item.unit_price, field=f"item {item.name!r} unit_price") * item.quantity
        disc = _discount_amount(item.discount, gross, owner=f"item {item.name!r}")
        grosses.append(gross)
        item_discounts.append(disc)
        nets.append(gross - disc)

    # -- Step 3: order-level discount. The pot is rounded ONCE, then the integer
    #    pot is distributed across items (never charges) by largest remainder,
    #    weighted by post-item-discount nets, so shares sum to the pot exactly.
    items_net = sum(nets)
    pot = _discount_amount(order.order_discount, items_net, owner="order")
    allocations = allocate(pot, nets)
    payables = [net - alloc for net, alloc in zip(nets, allocations)]

    # -- Step 4: per-line tax on the fully discounted amount.
    lines: list[LineBreakdown] = []
    for item, gross, disc, alloc, payable in zip(
        items, grosses, item_discounts, allocations, payables
    ):
        assert payable >= 0, "allocation must never exceed a line's net"
        if item.price_includes_tax:
            # The discounted inclusive amount is what the customer pays; split it.
            base, tax_lines = _split_inclusive(payable, item.taxes)
        else:
            base = payable
            tax_lines = _exclusive_taxes(base, item.taxes)
        tax_total = sum(t.amount for t in tax_lines)
        line_total = base + tax_total
        if item.price_includes_tax:
            assert line_total == payable, "inclusive quote must be honoured exactly"
        lines.append(
            LineBreakdown(
                name=item.name,
                quantity=item.quantity,
                gross=gross,
                item_discount=disc,
                order_discount_alloc=alloc,
                taxable_base=base,
                taxes=tax_lines,
                tax_total=tax_total,
                line_total=line_total,
            )
        )

    # -- Step 5: additional charges (never discounted).
    charge_breakdowns = tuple(_charge_breakdown(c) for c in order.charges)

    # -- Step 6: aggregation. Pure integer sums over already-final numbers.
    tax_totals: dict[tuple[str, Decimal], Paise] = {}
    for holder in (*lines, *charge_breakdowns):
        for t in holder.taxes:
            key = (t.name, t.rate)
            tax_totals[key] = tax_totals.get(key, 0) + t.amount

    items_gross = sum(grosses)
    item_discount_total = sum(item_discounts)
    order_discount_total = sum(allocations)
    charges_total = sum(c.total for c in charge_breakdowns)
    grand_total = sum(line.line_total for line in lines) + charges_total

    assert order_discount_total == pot, "discount pot must be conserved"
    assert items_gross - item_discount_total - order_discount_total == sum(payables)

    return OrderBreakdown(
        lines=tuple(lines),
        charges=charge_breakdowns,
        items_gross=items_gross,
        item_discount_total=item_discount_total,
        order_discount_total=order_discount_total,
        discount_total=item_discount_total + order_discount_total,
        tax_totals=tuple(
            TaxLine(name, rate, amount) for (name, rate), amount in tax_totals.items()
        ),
        tax_total=sum(tax_totals.values()),
        charges_total=charges_total,
        grand_total=grand_total,
    )
