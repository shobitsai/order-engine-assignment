from decimal import Decimal

from orderengine import compute_order

from conftest import fixed, make_charge, make_item, make_order, paise


def test_exclusive_taxable_charge():
    bd = compute_order(
        make_order(items=[make_item("100.00", rates=())], charges=[make_charge("30.00", rates=("18",))])
    )
    charge = bd.charges[0]
    assert charge.taxable_base == paise("30.00")
    assert charge.taxes[0].amount == paise("5.40")
    assert charge.total == paise("35.40")
    assert bd.charges_total == paise("35.40")
    totals = {(t.name, t.rate): t.amount for t in bd.tax_totals}
    assert totals[("GST", Decimal("18"))] == paise("5.40")
    assert bd.grand_total == paise("135.40")


def test_inclusive_charge_splits_like_an_inclusive_line():
    bd = compute_order(make_order(charges=[make_charge("118.00", rates=("18",), inclusive=True)]))
    charge = bd.charges[0]
    assert charge.taxable_base == paise("100.00")
    assert charge.taxes[0].amount == paise("18.00")
    assert charge.total == paise("118.00")


def test_order_discount_never_touches_charges():
    bd = compute_order(
        make_order(
            items=[make_item("100.00", rates=())],
            order_disc=fixed("10.00"),
            charges=[make_charge("30.00", rates=())],
        )
    )
    assert bd.lines[0].order_discount_alloc == paise("10.00")  # all of it on the item
    assert bd.charges[0].total == paise("30.00")               # charge untouched
    assert bd.grand_total == paise("120.00")


def test_charge_only_order():
    bd = compute_order(make_order(charges=[make_charge("50.00", rates=("5",))]))
    assert bd.items_gross == 0
    assert bd.grand_total == bd.charges_total == paise("52.50")
