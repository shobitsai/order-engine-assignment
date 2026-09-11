import pytest

from orderengine import ValidationError, compute_order

from conftest import fixed, make_item, make_order, paise, percent


def test_item_percent_discount_rounds_half_up_once_per_line():
    # 10% of 33.35 = 3.335 -> 3.34
    bd = compute_order(make_order(items=[make_item("33.35", rates=(), disc=percent("10"))]))
    assert bd.lines[0].item_discount == paise("3.34")


def test_item_fixed_discount_reduces_base_before_tax():
    # DECISION 3 pinned: tax is computed on the discounted base.
    bd = compute_order(
        make_order(items=[make_item("100.00", rates=("5",), disc=fixed("20.00"))])
    )
    line = bd.lines[0]
    assert line.taxable_base == paise("80.00")
    assert line.tax_total == paise("4.00")  # 5% of 80, not of 100
    assert line.line_total == paise("84.00")


def test_hundred_percent_discount_zeroes_everything():
    bd = compute_order(
        make_order(items=[make_item("99.99", rates=("2.5", "2.5"), disc=percent("100"))])
    )
    line = bd.lines[0]
    assert line.item_discount == paise("99.99")
    assert line.taxable_base == 0
    assert all(t.amount == 0 for t in line.taxes)
    assert line.line_total == 0
    assert bd.grand_total == 0


def test_item_fixed_discount_exceeding_gross_is_rejected():
    with pytest.raises(ValidationError, match="exceeds"):
        compute_order(make_order(items=[make_item("10.00", disc=fixed("10.01"))]))


def test_order_fixed_discount_allocated_by_largest_remainder():
    # Pot 10.00 over nets 10/20/30: ideals 1.6667/3.3333/5.00 -> 1.67/3.33/5.00
    items = [
        make_item("10.00", rates=(), name="A"),
        make_item("20.00", rates=(), name="B"),
        make_item("30.00", rates=(), name="C"),
    ]
    bd = compute_order(make_order(items=items, order_disc=fixed("10.00")))
    allocs = [line.order_discount_alloc for line in bd.lines]
    assert allocs == [paise("1.67"), paise("3.33"), paise("5.00")]
    assert sum(allocs) == bd.order_discount_total == paise("10.00")  # I2
    assert bd.grand_total == paise("50.00")


def test_order_percent_discount_pot_rounded_once_then_allocated():
    # 10% of (33.35 + 66.65) -> pot exactly 10.00; per-line ideals 3.335/6.665
    # tie on remainders 0.5/0.5 -> larger weight (line B) takes the extra paisa.
    items = [make_item("33.35", rates=(), name="A"), make_item("66.65", rates=(), name="B")]
    bd = compute_order(make_order(items=items, order_disc=percent("10")))
    allocs = [line.order_discount_alloc for line in bd.lines]
    assert allocs == [paise("3.33"), paise("6.67")]
    # I3: quoted-domain identity
    payable = sum(l.gross - l.item_discount - l.order_discount_alloc for l in bd.lines)
    assert bd.items_gross - bd.discount_total == payable == paise("90.00")


def test_zero_net_line_absorbs_no_order_discount():
    items = [
        make_item("50.00", rates=(), disc=percent("100"), name="Freebie"),
        make_item("50.00", rates=(), name="Paid"),
    ]
    bd = compute_order(make_order(items=items, order_disc=fixed("5.00")))
    assert bd.lines[0].order_discount_alloc == 0
    assert bd.lines[1].order_discount_alloc == paise("5.00")


def test_impossible_order_discounts_are_rejected():
    with pytest.raises(ValidationError, match="exceeds"):
        compute_order(make_order(items=[make_item("10.00")], order_disc=fixed("10.01")))
    with pytest.raises(ValidationError, match="percent"):
        percent("100.01")
    with pytest.raises(ValidationError, match=">= 0|percent"):
        percent("-1")


def test_inclusive_line_with_discounts_still_honours_the_quote():
    # DECISION 3 refinement pinned: discounts on an inclusive line apply in the
    # inclusive domain, so the customer pays exactly quoted - discounts.
    bd = compute_order(
        make_order(items=[make_item("118.00", rates=("18",), inclusive=True, disc=fixed("18.00"))])
    )
    line = bd.lines[0]
    assert line.line_total == paise("100.00")  # 118 - 18, to the paisa
    assert line.taxable_base == paise("84.75")  # split of the DISCOUNTED amount
    assert line.tax_total == paise("15.25")
    assert bd.grand_total == paise("100.00")


def test_order_discount_across_mixed_inclusive_exclusive_lines_reconciles():
    items = [
        make_item("118.00", rates=("9", "9"), inclusive=True, name="Incl"),
        make_item("100.00", rates=("9", "9"), name="Excl"),
    ]
    bd = compute_order(make_order(items=items, order_disc=percent("7.5")))
    assert sum(l.order_discount_alloc for l in bd.lines) == bd.order_discount_total
    incl = bd.lines[0]
    assert incl.line_total == incl.gross - incl.order_discount_alloc  # I7 with discount
    assert bd.grand_total == sum(l.line_total for l in bd.lines)
