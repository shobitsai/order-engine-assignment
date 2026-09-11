"""The no-float boundary.

All money inside the engine is an ``int`` number of paise (1 rupee = 100 paise).
Integers make exactness trivially auditable: sums cannot drift, and any place
that *deliberately* drops precision must call :func:`round_paise`, which is the
single rounding primitive of the whole engine (HALF_UP).

External values enter through :func:`to_paise` (money) or :func:`to_decimal`
(rates / percentages). ``float`` and ``bool`` are rejected everywhere; ``int``
is additionally rejected for money because ``100`` is ambiguous (rupees or
paise?).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .errors import ValidationError

# Type alias used throughout: an exact number of paise.
Paise = int


def _as_decimal(value: object, *, field: str, allow_int: bool) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field}: bool is not a number")
    if isinstance(value, float):
        raise TypeError(
            f"{field}: float is not allowed for exact money/rate values; "
            f"pass Decimal or str (e.g. Decimal('12.34') or '12.34')"
        )
    if isinstance(value, int):
        if not allow_int:
            raise TypeError(
                f"{field}: int is ambiguous for money (rupees or paise?); "
                f"pass Decimal or str like '12.34'"
            )
        return Decimal(value)
    if isinstance(value, str):
        try:
            d = Decimal(value)
        except InvalidOperation as exc:
            raise ValidationError(f"{field}: {value!r} is not a valid number") from exc
    elif isinstance(value, Decimal):
        d = value
    else:
        raise TypeError(f"{field}: expected Decimal or str, got {type(value).__name__}")
    if not d.is_finite():
        raise ValidationError(f"{field}: must be a finite number, got {d}")
    return d


def to_decimal(value: object, *, field: str) -> Decimal:
    """Parse a rate/percentage. Accepts Decimal, str, or int; rejects float/bool."""
    return _as_decimal(value, field=field, allow_int=True)


def to_paise(value: object, *, field: str) -> Paise:
    """Parse an exact money value into integer paise.

    Accepts Decimal or str with at most 2 decimal places. Rejects float, bool
    and int, sub-paisa precision, and non-finite values.
    """
    d = _as_decimal(value, field=field, allow_int=False)
    shifted = d.scaleb(2)  # move the decimal point: 12.34 -> 1234
    if shifted != shifted.to_integral_value():
        raise ValidationError(
            f"{field}: {d} has sub-paisa precision; the smallest currency unit is 0.01"
        )
    return int(shifted)


def round_paise(value: Decimal) -> Paise:
    """Round a Decimal amount of paise to a whole paisa, HALF_UP.

    This is the ONLY rounding primitive in the engine. HALF_UP (0.5 rounds away
    from zero) matches common Indian invoicing practice and user expectation;
    the bankers'-rounding bias argument is irrelevant at invoice scale.
    """
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_decimal(amount: Paise) -> Decimal:
    """Format helper: 1234 -> Decimal('12.34'). Display only, never fed back in."""
    return Decimal(amount).scaleb(-2)
