import random
from decimal import Decimal

from orderengine import compute_order

from conftest import make_item, make_order, paise


def test_clean_back_calculation():
    # 105.00 inclusive of 5% -> base 100.00, tax 5.00
    bd = compute_order(make_order(items=[make_item("105.00", rates=("5",), inclusive=True)]))
    line = bd.lines[0]
    assert line.taxable_base == paise("100.00")
    assert line.taxes[0].amount == paise("5.00")
    assert line.line_total == paise("105.00")


def test_ugly_back_calculation_base_absorbs_rounding():
    # DECISION 2 pinned: 100.00 incl 18% -> base = round(84.7457...) = 84.75,
    # tax = 100.00 - 84.75 = 15.25 EXACT by subtraction. Quote honoured.
    bd = compute_order(make_order(items=[make_item("100.00", rates=("18",), inclusive=True)]))
    line = bd.lines[0]
    assert line.taxable_base == paise("84.75")
    assert line.tax_total == paise("15.25")
    assert line.line_total == paise("100.00")


def test_odd_tax_pot_split_across_components():
    # pot 15.25 over CGST 9% + SGST 9% -> 7.63 + 7.62, sums to the pot.
    bd = compute_order(make_order(items=[make_item("100.00", rates=("9", "9"), inclusive=True)]))
    line = bd.lines[0]
    assert [t.amount for t in line.taxes] == [paise("7.63"), paise("7.62")]
    assert line.tax_total == paise("15.25")
    assert line.line_total == paise("100.00")


def test_inclusive_with_no_taxes_is_identity():
    bd = compute_order(make_order(items=[make_item("42.00", rates=(), inclusive=True)]))
    line = bd.lines[0]
    assert line.taxable_base == paise("42.00")
    assert line.tax_total == 0
    assert line.line_total == paise("42.00")


def test_one_paisa_inclusive_amount():
    # 0.01 incl 18%: base = round(0.847...) = 0.01, tax pot = 0. Documented edge.
    bd = compute_order(make_order(items=[make_item("0.01", rates=("18",), inclusive=True)]))
    line = bd.lines[0]
    assert line.taxable_base == 1
    assert line.tax_total == 0
    assert line.line_total == 1


def test_inclusive_quote_always_honoured_exactly():
    # I7 over a grid of awkward amounts and rates: what you quote is what is paid.
    rng = random.Random(7)
    rates = [Decimal(r) for r in ("0.1", "2.5", "5", "12", "18", "28")]
    for _ in range(200):
        amount_paise = rng.randint(1, 1_000_000)
        amount = Decimal(amount_paise).scaleb(-2)
        rate = rng.choice(rates)
        split = rng.random() < 0.5
        item_rates = (str(rate / 2), str(rate / 2)) if split else (str(rate),)
        bd = compute_order(make_order(items=[make_item(str(amount), rates=item_rates, inclusive=True)]))
        line = bd.lines[0]
        assert line.line_total == amount_paise
        assert line.taxable_base + sum(t.amount for t in line.taxes) == amount_paise
