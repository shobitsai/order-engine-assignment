"""Human text in, human text out.

Shared by the optional UIs (order_cli.py, gui.py): shorthand parsers for taxes
and discounts, and a plain-text renderer for an OrderBreakdown. The engine
itself never depends on this module.
"""

from __future__ import annotations

from .errors import ValidationError
from .models import Discount, DiscountKind, OrderBreakdown, TaxComponent
from .money import paise_to_decimal, to_decimal, to_paise


def parse_taxes(text: str) -> tuple[TaxComponent, ...]:
    """Parse tax shorthand.

    ""                    -> no taxes
    "18"                  -> GST @ 18%
    "CGST:2.5,SGST:2.5"   -> two named components
    """
    text = text.strip()
    if not text:
        return ()
    if ":" not in text:
        return (TaxComponent("GST", to_decimal(text, field="tax rate")),)
    components = []
    for part in text.split(","):
        name, _, rate = part.strip().partition(":")
        if not name or not rate:
            raise ValidationError(
                f"bad tax shorthand {part.strip()!r}: use 'NAME:RATE' (e.g. CGST:2.5)"
            )
        components.append(TaxComponent(name.strip(), to_decimal(rate.strip(), field=f"{name} rate")))
    return tuple(components)


def parse_discount(text: str) -> Discount | None:
    """Parse discount shorthand: "" -> None, "10%" -> percent, "15.00" -> fixed."""
    text = text.strip()
    if not text:
        return None
    if text.endswith("%"):
        return Discount(DiscountKind.PERCENT, to_decimal(text[:-1].strip(), field="percent discount"))
    # Validate through the engine's own money rules (2dp max, finite, etc.).
    return Discount(DiscountKind.FIXED, paise_to_decimal(to_paise(text, field="fixed discount")))


def format_breakdown(bd: OrderBreakdown) -> str:
    """Render a breakdown as aligned plain text (same shape as examples/demo.py)."""

    def rs(paise: int) -> str:
        return f"{paise_to_decimal(paise):>12}"

    def tax_bits(taxes) -> str:
        return "  ".join(f"{t.name}@{t.rate}%: {paise_to_decimal(t.amount)}" for t in taxes) or "(no tax)"

    out: list[str] = []
    for line in bd.lines:
        out.append(f"{line.name} x{line.quantity}")
        out.append(
            f"  gross {rs(line.gross)}   item disc {rs(line.item_discount)}"
            f"   order disc {rs(line.order_discount_alloc)}"
        )
        out.append(f"  taxable base {rs(line.taxable_base)}   {tax_bits(line.taxes)}")
        out.append(f"  line total {rs(line.line_total)}")
    for charge in bd.charges:
        out.append(
            f"{charge.name}: base {rs(charge.taxable_base)}   {tax_bits(charge.taxes)}"
            f"   total {rs(charge.total)}"
        )
    out.append("-" * 64)
    out.append(f"items gross        {rs(bd.items_gross)}")
    out.append(f"item discounts     {rs(bd.item_discount_total)}")
    out.append(f"order discount     {rs(bd.order_discount_total)}")
    for t in bd.tax_totals:
        out.append(f"  {t.name}@{t.rate}%".ljust(19) + rs(t.amount))
    out.append(f"charges total      {rs(bd.charges_total)}")
    out.append(f"GRAND TOTAL        {rs(bd.grand_total)}")
    return "\n".join(out)
