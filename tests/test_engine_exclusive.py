from decimal import Decimal

from orderengine import compute_order

from conftest import make_item, make_order, paise


def test_clean_case_split_gst():
    # 100.00 @ CGST 2.5% + SGST 2.5% -> 2.50 + 2.50, total 105.00
    bd = compute_order(make_order(items=[make_item("100.00", rates=("2.5", "2.5"))]))
    line = bd.lines[0]
    assert line.taxable_base == paise("100.00")
    assert [t.amount for t in line.taxes] == [paise("2.50"), paise("2.50")]
    assert line.line_total == paise("105.00")
    assert bd.grand_total == paise("105.00")


def test_per_component_rounding_is_the_primitive_not_a_combined_rate():
    # DECISION 1 pinned: base 10.10 @ 2.5+2.5 -> 0.25 + 0.25 = 0.50.
    # A combined 5% rate would give round(0.505) = 0.51 — we never do that.
    bd = compute_order(make_order(items=[make_item("10.10", rates=("2.5", "2.5"))]))
    line = bd.lines[0]
    assert [t.amount for t in line.taxes] == [paise("0.25"), paise("0.25")]
    assert line.tax_total == paise("0.50")
    assert line.taxable_base + line.tax_total == line.line_total  # I1 still holds


def test_half_up_direction():
    # 10.00 @ 0.25% = 0.025 -> rounds UP to 0.03
    bd = compute_order(make_order(items=[make_item("10.00", rates=("0.25",))]))
    assert bd.lines[0].taxes[0].amount == paise("0.03")


def test_zero_rate_component_appears_with_zero_amount():
    bd = compute_order(make_order(items=[make_item("50.00", rates=("5", "0"))]))
    line = bd.lines[0]
    assert line.taxes[1].amount == 0
    assert any(t.rate == Decimal("0") for t in bd.tax_totals)


def test_quantity_multiplies_exactly_before_any_rounding():
    # 3 x 33.33 -> gross 99.99 exactly; tax rounds once on the line, not per unit.
    bd = compute_order(make_order(items=[make_item("33.33", qty=3, rates=("18",))]))
    line = bd.lines[0]
    assert line.gross == paise("99.99")
    assert line.taxes[0].amount == paise("18.00")  # 17.9982 -> 18.00


def test_tax_totals_group_by_name_and_rate():
    items = [
        make_item("100.00", rates=("2.5", "2.5"), name="A"),
        make_item("50.00", rates=("2.5", "2.5"), name="B"),
        make_item("10.00", rates=("6",), names=("CGST",), name="C"),  # same name, new rate
    ]
    bd = compute_order(make_order(items=items))
    totals = {(t.name, t.rate): t.amount for t in bd.tax_totals}
    assert totals[("CGST", Decimal("2.5"))] == paise("2.50") + paise("1.25")
    assert totals[("SGST", Decimal("2.5"))] == paise("2.50") + paise("1.25")
    assert totals[("CGST", Decimal("6"))] == paise("0.60")  # separate row, same name
    assert bd.tax_total == sum(totals.values())
