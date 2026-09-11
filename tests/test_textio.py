from decimal import Decimal

import pytest

from orderengine import DiscountKind, ValidationError, compute_order
from orderengine.textio import format_breakdown, parse_discount, parse_taxes

from conftest import make_item, make_order


def test_parse_taxes_shorthand():
    assert parse_taxes("") == ()
    (gst,) = parse_taxes("18")
    assert (gst.name, gst.rate) == ("GST", Decimal("18"))
    cgst, sgst = parse_taxes("CGST:2.5, SGST:2.5")
    assert (cgst.name, cgst.rate) == ("CGST", Decimal("2.5"))
    assert (sgst.name, sgst.rate) == ("SGST", Decimal("2.5"))


def test_parse_taxes_bad_input():
    with pytest.raises(ValidationError):
        parse_taxes("CGST:")
    with pytest.raises(ValidationError):
        parse_taxes("abc")


def test_parse_discount_shorthand():
    assert parse_discount("") is None
    disc = parse_discount("10%")
    assert (disc.kind, disc.value) == (DiscountKind.PERCENT, Decimal("10"))
    disc = parse_discount("15.00")
    assert (disc.kind, disc.value) == (DiscountKind.FIXED, Decimal("15.00"))
    with pytest.raises(ValidationError):
        parse_discount("1.005")  # sub-paisa fixed discount


def test_format_breakdown_contains_reconciled_totals():
    bd = compute_order(make_order(items=[make_item("100.00", rates=("2.5", "2.5"))]))
    text = format_breakdown(bd)
    assert "GRAND TOTAL" in text and "105.00" in text
    assert "CGST@2.5%: 2.50" in text
