"""Input and output data model.

Inputs are frozen dataclasses that validate and normalise at construction time:
an invalid order cannot exist. Money enters as Decimal or str (never float —
see money.py) and is stored as a Decimal quantised to 2 places.

Outputs are frozen dataclasses in which every money field is an ``int`` number
of paise, so order-level figures are plain integer sums of line-level figures.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal

from .errors import ValidationError
from .money import Paise, paise_to_decimal, to_decimal, to_paise


def _require_name(value: object, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{what} must be a non-empty string")


def _normalised_money(value: object, *, field_name: str) -> Decimal:
    """Validate a money input and return it as a Decimal with exactly 2 dp."""
    return paise_to_decimal(to_paise(value, field=field_name))


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TaxComponent:
    """One named tax component, e.g. TaxComponent('CGST', Decimal('2.5'))."""

    name: str
    rate: Decimal  # percentage; accepts Decimal, str or int at construction

    def __post_init__(self) -> None:
        _require_name(self.name, "TaxComponent.name")
        rate = to_decimal(self.rate, field=f"tax {self.name!r} rate")
        if rate < 0:
            raise ValidationError(f"tax {self.name!r} rate must be >= 0, got {rate}")
        object.__setattr__(self, "rate", rate)


class DiscountKind(enum.Enum):
    FIXED = "fixed"      # value is a money amount
    PERCENT = "percent"  # value is a percentage in [0, 100]


@dataclass(frozen=True, slots=True)
class Discount:
    kind: DiscountKind
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DiscountKind):
            raise ValidationError(f"Discount.kind must be a DiscountKind, got {self.kind!r}")
        if self.kind is DiscountKind.FIXED:
            value = _normalised_money(self.value, field_name="fixed discount value")
            if value < 0:
                raise ValidationError(f"fixed discount must be >= 0, got {value}")
        else:
            value = to_decimal(self.value, field="percent discount value")
            if not (0 <= value <= 100):
                raise ValidationError(f"percent discount must be in [0, 100], got {value}")
        object.__setattr__(self, "value", value)


def _validated_taxes(taxes: object, *, owner: str) -> tuple[TaxComponent, ...]:
    taxes = tuple(taxes)  # type: ignore[arg-type]
    seen: set[str] = set()
    for component in taxes:
        if not isinstance(component, TaxComponent):
            raise ValidationError(f"{owner}: taxes must be TaxComponent instances")
        if component.name in seen:
            # A repeated name within one item would make per-component
            # aggregation ambiguous; two lines may share a name freely.
            raise ValidationError(f"{owner}: duplicate tax component name {component.name!r}")
        seen.add(component.name)
    return taxes


def _validated_discount(discount: object, *, owner: str) -> Discount | None:
    if discount is not None and not isinstance(discount, Discount):
        raise ValidationError(f"{owner}: discount must be a Discount or None")
    return discount


@dataclass(frozen=True, slots=True)
class LineItem:
    name: str
    unit_price: Decimal            # Decimal or str at construction; >= 0, 2 dp
    quantity: int                  # >= 1
    taxes: tuple[TaxComponent, ...] = ()
    price_includes_tax: bool = False
    discount: Discount | None = None

    def __post_init__(self) -> None:
        _require_name(self.name, "LineItem.name")
        price = _normalised_money(self.unit_price, field_name=f"item {self.name!r} unit_price")
        if price < 0:
            raise ValidationError(f"item {self.name!r}: unit_price must be >= 0, got {price}")
        object.__setattr__(self, "unit_price", price)
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValidationError(f"item {self.name!r}: quantity must be an int")
        if self.quantity < 1:
            raise ValidationError(f"item {self.name!r}: quantity must be >= 1, got {self.quantity}")
        object.__setattr__(self, "taxes", _validated_taxes(self.taxes, owner=f"item {self.name!r}"))
        if not isinstance(self.price_includes_tax, bool):
            raise ValidationError(f"item {self.name!r}: price_includes_tax must be a bool")
        object.__setattr__(
            self, "discount", _validated_discount(self.discount, owner=f"item {self.name!r}")
        )


@dataclass(frozen=True, slots=True)
class Charge:
    """An order-level additional charge (delivery, handling, ...), independently taxable."""

    name: str
    amount: Decimal
    taxes: tuple[TaxComponent, ...] = ()
    amount_includes_tax: bool = False

    def __post_init__(self) -> None:
        _require_name(self.name, "Charge.name")
        amount = _normalised_money(self.amount, field_name=f"charge {self.name!r} amount")
        if amount < 0:
            raise ValidationError(f"charge {self.name!r}: amount must be >= 0, got {amount}")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "taxes", _validated_taxes(self.taxes, owner=f"charge {self.name!r}"))
        if not isinstance(self.amount_includes_tax, bool):
            raise ValidationError(f"charge {self.name!r}: amount_includes_tax must be a bool")


@dataclass(frozen=True, slots=True)
class Order:
    items: tuple[LineItem, ...] = ()
    order_discount: Discount | None = None
    charges: tuple[Charge, ...] = ()

    def __post_init__(self) -> None:
        items = tuple(self.items)
        for item in items:
            if not isinstance(item, LineItem):
                raise ValidationError("Order.items must contain LineItem instances")
        object.__setattr__(self, "items", items)
        charges = tuple(self.charges)
        for charge in charges:
            if not isinstance(charge, Charge):
                raise ValidationError("Order.charges must contain Charge instances")
        object.__setattr__(self, "charges", charges)
        object.__setattr__(
            self, "order_discount", _validated_discount(self.order_discount, owner="order")
        )


# ---------------------------------------------------------------------------
# Outputs — every money field is an int number of paise
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TaxLine:
    name: str
    rate: Decimal
    amount: Paise


@dataclass(frozen=True, slots=True)
class LineBreakdown:
    name: str
    quantity: int
    gross: Paise                 # unit_price * quantity, in the line's quoted basis
    item_discount: Paise
    order_discount_alloc: Paise  # this line's share of the order-level discount pot
    taxable_base: Paise          # post-discount, pre-tax
    taxes: tuple[TaxLine, ...]
    tax_total: Paise             # == sum of component amounts, by definition
    line_total: Paise            # taxable_base + tax_total


@dataclass(frozen=True, slots=True)
class ChargeBreakdown:
    name: str
    taxable_base: Paise
    taxes: tuple[TaxLine, ...]
    total: Paise                 # taxable_base + tax


@dataclass(frozen=True, slots=True)
class OrderBreakdown:
    lines: tuple[LineBreakdown, ...]
    charges: tuple[ChargeBreakdown, ...]
    items_gross: Paise            # sum of line gross amounts (quoted basis)
    item_discount_total: Paise
    order_discount_total: Paise   # the pot; == sum of per-line allocations
    discount_total: Paise
    tax_totals: tuple[TaxLine, ...]  # grouped by (name, rate) across lines AND charges
    tax_total: Paise
    charges_total: Paise          # sum of charge totals (base + tax)
    grand_total: Paise
