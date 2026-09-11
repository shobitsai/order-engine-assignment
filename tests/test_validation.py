import dataclasses
from decimal import Decimal

import pytest

from orderengine import (
    Charge,
    Discount,
    DiscountKind,
    LineItem,
    Order,
    TaxComponent,
    ValidationError,
    compute_order,
)

from conftest import fixed, make_item, make_order, percent


@pytest.mark.parametrize(
    "build",
    [
        lambda: LineItem("A", Decimal("-1.00"), 1),
        lambda: Charge("Delivery", Decimal("-5.00")),
        lambda: TaxComponent("CGST", Decimal("-1")),
        lambda: Discount(DiscountKind.FIXED, Decimal("-2.00")),
        lambda: Discount(DiscountKind.PERCENT, Decimal("101")),
    ],
    ids=["negative-price", "negative-charge", "negative-rate", "negative-discount", "percent>100"],
)
def test_negative_and_out_of_range_inputs_rejected(build):
    with pytest.raises(ValidationError):
        build()


@pytest.mark.parametrize("qty", [0, -1, True, 2.0, "2"])
def test_bad_quantities_rejected(qty):
    with pytest.raises(ValidationError):
        LineItem("A", Decimal("1.00"), qty)


@pytest.mark.parametrize(
    "build",
    [
        lambda: LineItem("A", 10.5, 1),
        lambda: TaxComponent("CGST", 2.5),
        lambda: Discount(DiscountKind.PERCENT, 10.0),
        lambda: Charge("D", 5.0),
    ],
    ids=["price", "rate", "discount", "charge"],
)
def test_float_anywhere_is_a_type_error(build):
    with pytest.raises(TypeError):
        build()


def test_duplicate_tax_component_names_within_one_item_rejected():
    taxes = (TaxComponent("CGST", Decimal("2.5")), TaxComponent("CGST", Decimal("6")))
    with pytest.raises(ValidationError, match="duplicate"):
        LineItem("A", Decimal("10.00"), 1, taxes=taxes)
    with pytest.raises(ValidationError, match="duplicate"):
        Charge("Delivery", Decimal("10.00"), taxes=taxes)


def test_empty_order_computes_to_all_zeros():
    bd = compute_order(Order())
    assert bd.grand_total == 0
    assert bd.tax_totals == ()
    assert bd.lines == () and bd.charges == ()


def test_discounts_against_zero_subtotal():
    # Percent of zero is fine (pot 0); a positive fixed discount is impossible.
    bd = compute_order(make_order(items=[make_item("0.00")], order_disc=percent("50")))
    assert bd.order_discount_total == 0
    with pytest.raises(ValidationError, match="exceeds"):
        compute_order(make_order(items=[make_item("0.00")], order_disc=fixed("0.01")))


def test_inputs_are_frozen():
    item = make_item()
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.unit_price = Decimal("1.00")
    order = make_order(items=[item])
    with pytest.raises(dataclasses.FrozenInstanceError):
        order.items = ()
