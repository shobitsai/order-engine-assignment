"""Interactive terminal UI for the order engine.

    python order_cli.py            build an order step by step, see the breakdown
    python order_cli.py --match    try the Part B catalog matcher interactively

Pure convenience for exploring the engine — all logic lives in src/orderengine.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from orderengine import (
    Charge,
    LineItem,
    Order,
    ValidationError,
    compute_order,
    paise_to_decimal,
    to_paise,
)
from orderengine.textio import format_breakdown, parse_discount, parse_taxes


def money(text: str) -> Decimal:
    """Parse '299.00' through the engine's own money rules."""
    return paise_to_decimal(to_paise(text, field="amount"))


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise ValidationError("quantity must be >= 1")
    return value


def ask(prompt: str, parser, default_text: str = ""):
    """Prompt until the input parses; blank uses the default."""
    suffix = f" [{default_text}]" if default_text else ""
    while True:
        try:
            raw = input(f"{prompt}{suffix}: ").strip().lstrip("﻿")  # BOM guard for piped input
        except EOFError:
            print()
            sys.exit(0)
        if not raw:
            raw = default_text
        try:
            return parser(raw)
        except (ValueError, TypeError) as exc:  # ValidationError is a ValueError
            print(f"  ! {exc}")


def yes_no(prompt: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            raw = input(f"{prompt} [{hint}]: ").strip().lower()
        except EOFError:
            print()
            sys.exit(0)
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  ! answer y or n")


def read_item(index: int) -> LineItem:
    print(f"\n--- item {index} ---")
    name = ask("name", lambda s: s if s else "Item", f"Item {index}")
    price = ask("unit price (e.g. 299.00)", money)
    qty = ask("quantity", positive_int, "1")
    taxes = ask(
        "taxes — any custom rate works ('12' = GST@12, 'CGST:6,SGST:6' or 'GST:12,CESS:1' = components, blank = none)",
        parse_taxes, "",
    )
    inclusive = yes_no("does the price already include tax?", default=False)
    discount = ask("item discount ('10%' or '15.00', blank = none)", parse_discount, "")
    return LineItem(
        name=name, unit_price=price, quantity=qty, taxes=taxes,
        price_includes_tax=inclusive, discount=discount,
    )


def read_charge(index: int) -> Charge:
    print(f"\n--- charge {index} ---")
    name = ask("name (e.g. Delivery)", lambda s: s or "Charge", f"Charge {index}")
    amount = ask("amount (e.g. 30.00)", money)
    taxes = ask(
        "taxes — any custom rate works ('18' = GST@18, 'CGST:9,SGST:9' = components, blank = none)",
        parse_taxes, "",
    )
    inclusive = yes_no("does the amount already include tax?", default=False)
    return Charge(name=name, amount=amount, taxes=taxes, amount_includes_tax=inclusive)


def build_order() -> None:
    print("Order engine — build an order (Ctrl+C to quit)\n")
    items = [read_item(1)]
    while yes_no("\nadd another item?", default=False):
        items.append(read_item(len(items) + 1))

    charges = []
    while yes_no("\nadd an additional charge (delivery, handling, ...)?", default=False):
        charges.append(read_charge(len(charges) + 1))

    order_discount = ask(
        "\norder-level discount ('10%' or '50.00', blank = none)", parse_discount, ""
    )

    try:
        breakdown = compute_order(
            Order(items=tuple(items), order_discount=order_discount, charges=tuple(charges))
        )
    except ValidationError as exc:
        print(f"\ninvalid order: {exc}")
        sys.exit(1)

    print("\n" + "=" * 64)
    print(format_breakdown(breakdown))


def match_loop() -> None:
    from orderengine.matching import CatalogMatcher

    catalog = json.loads((_ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    matcher = CatalogMatcher(catalog)
    print(f"Catalog matcher — {len(catalog)} entries. Type a reference, blank to quit.\n")
    while True:
        try:
            query = input("query: ").strip()
        except EOFError:
            break
        if not query:
            break
        result = matcher.match(query)
        if result is None:
            top = matcher.score_all(query)[:3]
            candidates = ", ".join(f"{e} ({s:.2f})" for e, s in top)
            print(f"  NO MATCH (abstained). closest: {candidates}\n")
        else:
            print(f"  -> {result.entry}   (score {result.score:.2f}, runner-up {result.runner_up:.2f})\n")


if __name__ == "__main__":
    if "--match" in sys.argv:
        match_loop()
    else:
        build_order()
