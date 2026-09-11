"""Your own order — edit the values below, then run:  python examples/my_order.py

Rules to remember:
- Money is ALWAYS a str or Decimal like "299.00" — never a bare number like 299.0
- Rates are percentages: Decimal("2.5") means 2.5%
- price_includes_tax=True  -> the price you typed already contains the tax
- price_includes_tax=False -> tax gets added on top
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orderengine import (
    Charge, Discount, DiscountKind, LineItem, Order, TaxComponent,
    compute_order, paise_to_decimal,
)

# ---- 1. EDIT YOUR ITEMS HERE -------------------------------------------
# Custom GST: any name and any rate works in `taxes`, e.g.
#   (TaxComponent("GST", Decimal("12")),)                                   flat 12%
#   (TaxComponent("CGST", Decimal("6")), TaxComponent("SGST", Decimal("6")))  split
#   (TaxComponent("GST", Decimal("12")), TaxComponent("CESS", Decimal("1")))  with cess
items = (
    LineItem(
        name="My first item",
        unit_price=Decimal("150.00"),
        quantity=2,
        taxes=(TaxComponent("CGST", Decimal("2.5")), TaxComponent("SGST", Decimal("2.5"))),
        price_includes_tax=False,
        discount=None,  # or Discount(DiscountKind.FIXED, Decimal("10.00"))
                        # or Discount(DiscountKind.PERCENT, Decimal("5"))
    ),
    LineItem(
        name="My second item",
        unit_price=Decimal("99.00"),
        quantity=1,
        taxes=(TaxComponent("GST", Decimal("18")),),
        price_includes_tax=True,   # 99.00 already contains the 18%
    ),
)

# ---- 2. EDIT ORDER-LEVEL DISCOUNT (or set to None) ---------------------
order_discount = Discount(DiscountKind.PERCENT, Decimal("10"))

# ---- 3. EDIT CHARGES (or use an empty tuple: ()) -----------------------
charges = (
    Charge(name="Delivery", amount=Decimal("30.00"),
           taxes=(TaxComponent("GST", Decimal("18")),)),
)

# ---- 4. COMPUTE AND PRINT (no need to edit below) ----------------------
bd = compute_order(Order(items=items, order_discount=order_discount, charges=charges))

rs = lambda p: f"{paise_to_decimal(p):>10}"
for line in bd.lines:
    print(f"{line.name} x{line.quantity}")
    print(f"  gross {rs(line.gross)}  item disc {rs(line.item_discount)}  order disc {rs(line.order_discount_alloc)}")
    taxes = "  ".join(f"{t.name}@{t.rate}%: {paise_to_decimal(t.amount)}" for t in line.taxes)
    print(f"  taxable base {rs(line.taxable_base)}   {taxes}")
    print(f"  line total {rs(line.line_total)}")
for c in bd.charges:
    taxes = "  ".join(f"{t.name}@{t.rate}%: {paise_to_decimal(t.amount)}" for t in c.taxes)
    print(f"{c.name}: base {rs(c.taxable_base)}   {taxes}   total {rs(c.total)}")
print("-" * 60)
print(f"items gross      {rs(bd.items_gross)}")
print(f"discount total   {rs(bd.discount_total)}")
for t in bd.tax_totals:
    print(f"  {t.name}@{t.rate}%   {rs(t.amount)}")
print(f"charges total    {rs(bd.charges_total)}")
print(f"GRAND TOTAL      {rs(bd.grand_total)}")
