"""A worked example: python examples/demo.py

A two-item order (one tax-inclusive, one tax-exclusive), an item discount,
an order-level percentage discount, and a taxed delivery charge.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orderengine import (
    Charge,
    Discount,
    DiscountKind,
    LineItem,
    Order,
    TaxComponent,
    compute_order,
    paise_to_decimal,
)

GST_5 = (TaxComponent("CGST", Decimal("2.5")), TaxComponent("SGST", Decimal("2.5")))
GST_18 = (TaxComponent("CGST", Decimal("9")), TaxComponent("SGST", Decimal("9")))

order = Order(
    items=(
        LineItem(
            name="Chicken Biryani",
            unit_price=Decimal("299.00"),  # menu price, tax-inclusive
            quantity=2,
            taxes=GST_5,
            price_includes_tax=True,
        ),
        LineItem(
            name="Paneer Tikka",
            unit_price=Decimal("240.00"),  # pre-tax
            quantity=1,
            taxes=GST_5,
            discount=Discount(DiscountKind.FIXED, Decimal("40.00")),
        ),
    ),
    order_discount=Discount(DiscountKind.PERCENT, Decimal("10")),
    charges=(Charge(name="Delivery", amount=Decimal("30.00"), taxes=GST_18),),
)

bd = compute_order(order)

def rs(paise: int) -> str:
    return f"{paise_to_decimal(paise):>10}"

for line in bd.lines:
    print(f"{line.name} x{line.quantity}")
    print(f"  gross {rs(line.gross)}   item disc {rs(line.item_discount)}   "
          f"order disc {rs(line.order_discount_alloc)}")
    taxes = "  ".join(f"{t.name}@{t.rate}%: {paise_to_decimal(t.amount)}" for t in line.taxes)
    print(f"  taxable base {rs(line.taxable_base)}   {taxes}")
    print(f"  line total {rs(line.line_total)}")
for charge in bd.charges:
    taxes = "  ".join(f"{t.name}@{t.rate}%: {paise_to_decimal(t.amount)}" for t in charge.taxes)
    print(f"{charge.name}: base {rs(charge.taxable_base)}   {taxes}   total {rs(charge.total)}")

print("-" * 60)
print(f"items gross      {rs(bd.items_gross)}")
print(f"discount total   {rs(bd.discount_total)}")
for t in bd.tax_totals:
    print(f"  {t.name}@{t.rate}%      {rs(t.amount)}")
print(f"charges total    {rs(bd.charges_total)}")
print(f"GRAND TOTAL      {rs(bd.grand_total)}")

# The reconciliation identity, spelled out:
lines_sum = sum(l.line_total for l in bd.lines)
assert lines_sum + bd.charges_total == bd.grand_total
print("\nreconciles: sum(line totals) + charges ==", paise_to_decimal(bd.grand_total))
