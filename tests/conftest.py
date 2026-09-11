"""Shared builders so tests stay one screen tall."""

from decimal import Decimal

import pytest

from orderengine import Charge, Discount, DiscountKind, LineItem, Order, TaxComponent

DEFAULT_TAX_NAMES = ("CGST", "SGST", "CESS", "TAX4")


def paise(value: str) -> int:
    """'12.34' -> 1234, for readable expected values."""
    return int(Decimal(value).scaleb(2))


def make_taxes(rates=("2.5", "2.5"), names=None):
    names = names or DEFAULT_TAX_NAMES[: len(rates)]
    return tuple(TaxComponent(n, Decimal(r)) for n, r in zip(names, rates))


def make_item(
    price="100.00",
    qty=1,
    rates=("2.5", "2.5"),
    names=None,
    inclusive=False,
    disc=None,
    name="Item",
):
    return LineItem(
        name=name,
        unit_price=Decimal(price),
        quantity=qty,
        taxes=make_taxes(rates, names) if rates else (),
        price_includes_tax=inclusive,
        discount=disc,
    )


def make_charge(amount="30.00", rates=("18",), names=("GST",), inclusive=False, name="Delivery"):
    return Charge(
        name=name,
        amount=Decimal(amount),
        taxes=make_taxes(rates, names) if rates else (),
        amount_includes_tax=inclusive,
    )


def make_order(items=(), order_disc=None, charges=()):
    return Order(items=tuple(items), order_discount=order_disc, charges=tuple(charges))


def fixed(value: str) -> Discount:
    return Discount(DiscountKind.FIXED, Decimal(value))


def percent(value: str) -> Discount:
    return Discount(DiscountKind.PERCENT, Decimal(value))


@pytest.fixture
def simple_order():
    return make_order(items=[make_item()])
