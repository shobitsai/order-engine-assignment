from decimal import Decimal

import pytest

from orderengine import ValidationError, paise_to_decimal, round_paise, to_paise


def test_to_paise_accepts_decimal_and_str():
    assert to_paise(Decimal("12.34"), field="x") == 1234
    assert to_paise("12.34", field="x") == 1234
    assert to_paise("0", field="x") == 0
    assert to_paise("100", field="x") == 10000
    assert paise_to_decimal(1234) == Decimal("12.34")


@pytest.mark.parametrize("bad", [12.34, 0.1, True, False])
def test_to_paise_rejects_float_and_bool(bad):
    with pytest.raises(TypeError) as excinfo:
        to_paise(bad, field="unit_price")
    assert "unit_price" in str(excinfo.value)


def test_to_paise_rejects_int_as_ambiguous():
    with pytest.raises(TypeError, match="ambiguous"):
        to_paise(100, field="x")


@pytest.mark.parametrize("bad", ["1.005", Decimal("0.001"), Decimal("9.999")])
def test_to_paise_rejects_sub_paisa_precision(bad):
    with pytest.raises(ValidationError, match="sub-paisa"):
        to_paise(bad, field="x")


@pytest.mark.parametrize("bad", ["NaN", Decimal("NaN"), Decimal("Infinity"), "abc", ""])
def test_to_paise_rejects_non_finite_and_garbage(bad):
    with pytest.raises(ValidationError):
        to_paise(bad, field="x")


def test_round_paise_half_up_boundaries():
    assert round_paise(Decimal("2.5")) == 3      # .5 rounds up, not to even
    assert round_paise(Decimal("3.5")) == 4
    assert round_paise(Decimal("2.4999")) == 2
    assert round_paise(Decimal("-0.5")) == -1    # HALF_UP = away from zero
    assert round_paise(Decimal("0")) == 0
