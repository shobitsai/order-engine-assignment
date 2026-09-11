"""A small tkinter GUI for exploring the engine:  python gui.py

Tab 1 builds an order (items, discounts, charges) and shows the reconciled
breakdown; tab 2 drives the Part B catalog matcher live. Stdlib only — pure
convenience for exploring; all logic lives in src/orderengine.

`python gui.py --smoke` builds the UI, computes a sample order, and exits —
used to verify the GUI wires up without needing a human.
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from orderengine import Charge, LineItem, Order, ValidationError, compute_order
from orderengine.matching import CatalogMatcher
from orderengine.textio import format_breakdown, parse_discount, parse_taxes

TAX_PRESETS = {
    "No tax": "",
    "GST 5% (CGST+SGST)": "CGST:2.5,SGST:2.5",
    "GST 12% (CGST+SGST)": "CGST:6,SGST:6",
    "GST 18% (CGST+SGST)": "CGST:9,SGST:9",
    "GST 28% (CGST+SGST)": "CGST:14,SGST:14",
    "IGST 18%": "IGST:18",
}
CUSTOM_LABEL = "Custom GST…"
TAX_CHOICES = list(TAX_PRESETS) + [CUSTOM_LABEL]

BG = "#f4f5f7"
HEADER_BG = "#1f2937"
ACCENT = "#2563eb"


def resolve_taxes(text: str):
    """Preset label -> its shorthand; anything else is parsed as shorthand itself."""
    if text.strip() == CUSTOM_LABEL:
        raise ValidationError("pick 'Custom GST…' again and enter a rate, e.g. '12' or 'CGST:6,SGST:6'")
    return parse_taxes(TAX_PRESETS.get(text, text))


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Order Engine")
        root.geometry("1024x680")
        root.configure(bg=BG)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=BG, font=("Segoe UI", 10))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.configure("TLabelframe", background=BG, padding=10)
        style.configure("TLabelframe.Label", background=BG, font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        header = tk.Frame(root, bg=HEADER_BG)
        header.pack(fill="x")
        tk.Label(header, text="Order charge & tax engine", bg=HEADER_BG, fg="white",
                 font=("Segoe UI", 15, "bold"), pady=12, padx=16).pack(side="left")
        tk.Label(header, text="exact to the paisa, reconciled by construction",
                 bg=HEADER_BG, fg="#9ca3af", font=("Segoe UI", 10), padx=8).pack(
                 side="left", pady=(6, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_order_tab(notebook)
        self._build_matcher_tab(notebook)

        self.items: list[LineItem] = []
        self.charges: list[Charge] = []

    # ------------------------------------------------------------------ tab 1
    def _build_order_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="  Order builder  ")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y", padx=(4, 8), pady=4)
        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True, pady=4)

        # --- add item form
        item_box = ttk.Labelframe(left, text="Add item")
        item_box.pack(fill="x")
        self.item_name = self._entry(item_box, "Name", 0, "Chicken Biryani")
        self.item_price = self._entry(item_box, "Unit price", 1, "299.00")
        self.item_qty = self._entry(item_box, "Quantity", 2, "1")
        ttk.Label(item_box, text="Taxes").grid(row=3, column=0, sticky="w", pady=2)
        self.item_taxes = ttk.Combobox(item_box, values=TAX_CHOICES, width=22)
        self.item_taxes.set("GST 5% (CGST+SGST)")
        self.item_taxes.grid(row=3, column=1, sticky="we", pady=2)
        self.item_taxes.bind("<<ComboboxSelected>>", lambda _e: self._maybe_custom_tax(self.item_taxes))
        self.item_incl = tk.BooleanVar()
        ttk.Checkbutton(item_box, text="price already includes tax",
                        variable=self.item_incl).grid(row=4, column=0, columnspan=2, sticky="w")
        self.item_disc = self._entry(item_box, "Discount ('10%' / '15.00')", 5, "")
        ttk.Button(item_box, text="Add item", command=self.add_item).grid(
            row=6, column=0, columnspan=2, sticky="we", pady=(6, 2))

        # --- add charge form
        charge_box = ttk.Labelframe(left, text="Add charge (delivery, handling, ...)")
        charge_box.pack(fill="x", pady=(10, 0))
        self.charge_name = self._entry(charge_box, "Name", 0, "Delivery")
        self.charge_amount = self._entry(charge_box, "Amount", 1, "30.00")
        ttk.Label(charge_box, text="Taxes").grid(row=2, column=0, sticky="w", pady=2)
        self.charge_taxes = ttk.Combobox(charge_box, values=TAX_CHOICES, width=22)
        self.charge_taxes.set("GST 18% (CGST+SGST)")
        self.charge_taxes.grid(row=2, column=1, sticky="we", pady=2)
        self.charge_taxes.bind("<<ComboboxSelected>>", lambda _e: self._maybe_custom_tax(self.charge_taxes))
        self.charge_incl = tk.BooleanVar()
        ttk.Checkbutton(charge_box, text="amount already includes tax",
                        variable=self.charge_incl).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(charge_box, text="Add charge", command=self.add_charge).grid(
            row=4, column=0, columnspan=2, sticky="we", pady=(6, 2))

        # --- order discount + compute
        order_box = ttk.Labelframe(left, text="Order")
        order_box.pack(fill="x", pady=(10, 0))
        self.order_disc = self._entry(order_box, "Order discount ('10%' / '50.00')", 0, "")
        ttk.Button(order_box, text="Remove selected row", command=self.remove_selected).grid(
            row=1, column=0, columnspan=2, sticky="we", pady=(6, 2))
        ttk.Button(order_box, text="Compute breakdown", style="Accent.TButton",
                   command=self.compute).grid(row=2, column=0, columnspan=2, sticky="we", pady=2)
        ttk.Button(order_box, text="Clear order", command=self.clear_order).grid(
            row=3, column=0, columnspan=2, sticky="we", pady=2)

        # --- right side: current order table + breakdown
        columns = ("what", "price", "qty", "taxes", "incl", "disc")
        self.tree = ttk.Treeview(right, columns=columns, show="headings", height=7)
        widths = {"what": 170, "price": 80, "qty": 45, "taxes": 170, "incl": 60, "disc": 80}
        for col, title in zip(columns, ("Item / charge", "Price", "Qty", "Taxes", "Incl?", "Disc")):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="x")

        self.output = tk.Text(right, font=("Consolas", 10), bg="white", relief="flat",
                              padx=12, pady=10, state="disabled")
        self.output.pack(fill="both", expand=True, pady=(8, 0))
        self._set_output("Add items on the left, then press 'Compute breakdown'.")

    def _maybe_custom_tax(self, combo: ttk.Combobox) -> None:
        """When 'Custom GST…' is picked, open the name/rate form and keep the result in the box."""
        if combo.get() != CUSTOM_LABEL:
            return
        shorthand = self._custom_tax_dialog()
        combo.set(shorthand if shorthand else "No tax")

    def _custom_tax_dialog(self) -> str | None:
        """Structured input: one row per tax component (name + rate %). Returns
        the components as 'NAME:RATE,...' shorthand (what resolve_taxes expects),
        or None if cancelled."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Custom GST")
        dlg.configure(bg=BG, padx=14, pady=12)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry(f"+{self.root.winfo_rootx() + 140}+{self.root.winfo_rooty() + 140}")

        ttk.Label(dlg, text="Tax components", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(dlg, text="Name").grid(row=1, column=0, sticky="w")
        ttk.Label(dlg, text="Rate %").grid(row=1, column=1, sticky="w")

        rows: list[tuple[ttk.Entry, ttk.Entry]] = []

        def add_row(name: str = "", rate: str = "") -> None:
            r = 2 + len(rows)
            name_entry = ttk.Entry(dlg, width=14)
            name_entry.insert(0, name)
            name_entry.grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
            rate_entry = ttk.Entry(dlg, width=8)
            rate_entry.insert(0, rate)
            rate_entry.grid(row=r, column=1, sticky="w", pady=2)
            rows.append((name_entry, rate_entry))
            button_bar.grid(row=r + 1, column=0, columnspan=3, sticky="we", pady=(10, 0))

        result: dict[str, str | None] = {"value": None}

        def on_ok() -> None:
            pairs = [
                (n.get().strip(), r.get().strip())
                for n, r in rows
                if n.get().strip() or r.get().strip()
            ]
            if not pairs:
                messagebox.showerror("Custom GST", "Add at least one component (name and rate).", parent=dlg)
                return
            for name, rate in pairs:
                if not name or not rate:
                    messagebox.showerror("Custom GST", "Every component needs both a name and a rate.", parent=dlg)
                    return
                if ":" in name or "," in name or "," in rate:
                    messagebox.showerror("Custom GST", "Names and rates must not contain ':' or ','.", parent=dlg)
                    return
            shorthand = ",".join(f"{name}:{rate}" for name, rate in pairs)
            try:
                parse_taxes(shorthand)  # engine-side validation (rate >= 0, numeric, ...)
            except (ValueError, TypeError) as exc:
                messagebox.showerror("Custom GST", str(exc), parent=dlg)
                return
            result["value"] = shorthand
            dlg.destroy()

        button_bar = ttk.Frame(dlg)
        ttk.Button(button_bar, text="+ Add component", command=add_row).pack(side="left")
        ttk.Button(button_bar, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(button_bar, text="OK", style="Accent.TButton", command=on_ok).pack(
            side="right", padx=(0, 6))

        add_row("CGST", "")
        add_row("SGST", "")
        rows[0][1].focus_set()
        dlg.bind("<Return>", lambda _e: on_ok())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.grab_set()
        dlg.wait_window()
        return result["value"]

    def _entry(self, parent, label, row, default=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(parent, width=24)
        entry.insert(0, default)
        entry.grid(row=row, column=1, sticky="we", pady=2)
        return entry

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def add_item(self) -> None:
        try:
            item = LineItem(
                name=self.item_name.get().strip() or f"Item {len(self.items) + 1}",
                unit_price=self.item_price.get().strip(),
                quantity=int(self.item_qty.get().strip() or "1"),
                taxes=resolve_taxes(self.item_taxes.get()),
                price_includes_tax=self.item_incl.get(),
                discount=parse_discount(self.item_disc.get()),
            )
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid item", str(exc))
            return
        self.items.append(item)
        self.tree.insert("", "end", values=(
            item.name, item.unit_price, item.quantity, self.item_taxes.get(),
            "yes" if item.price_includes_tax else "no", self.item_disc.get() or "-",
        ), tags=("item", str(len(self.items) - 1)))

    def add_charge(self) -> None:
        try:
            charge = Charge(
                name=self.charge_name.get().strip() or f"Charge {len(self.charges) + 1}",
                amount=self.charge_amount.get().strip(),
                taxes=resolve_taxes(self.charge_taxes.get()),
                amount_includes_tax=self.charge_incl.get(),
            )
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid charge", str(exc))
            return
        self.charges.append(charge)
        self.tree.insert("", "end", values=(
            f"[charge] {charge.name}", charge.amount, "-", self.charge_taxes.get(),
            "yes" if charge.amount_includes_tax else "no", "-",
        ), tags=("charge", str(len(self.charges) - 1)))

    def remove_selected(self) -> None:
        for row in self.tree.selection():
            kind, index = self.tree.item(row, "tags")
            (self.items if kind == "item" else self.charges).pop(int(index))
            self.tree.delete(row)
        self._retag()

    def _retag(self) -> None:
        counts = {"item": 0, "charge": 0}
        for row in self.tree.get_children():
            kind, _ = self.tree.item(row, "tags")
            self.tree.item(row, tags=(kind, str(counts[kind])))
            counts[kind] += 1

    def clear_order(self) -> None:
        self.items.clear()
        self.charges.clear()
        self.tree.delete(*self.tree.get_children())
        self._set_output("Order cleared.")

    def compute(self) -> None:
        try:
            order = Order(
                items=tuple(self.items),
                order_discount=parse_discount(self.order_disc.get()),
                charges=tuple(self.charges),
            )
            breakdown = compute_order(order)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid order", str(exc))
            return
        self._set_output(format_breakdown(breakdown))

    # ------------------------------------------------------------------ tab 2
    def _build_matcher_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="  Catalog matcher  ")
        catalog = json.loads((_ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
        self.matcher = CatalogMatcher(catalog)

        top = ttk.Frame(tab)
        top.pack(fill="x", padx=8, pady=10)
        ttk.Label(top, text=f"Type a messy reference ({len(catalog)} catalog entries):").pack(anchor="w")
        row = ttk.Frame(top)
        row.pack(fill="x", pady=4)
        style = ttk.Style(self.root)
        style.configure("Placeholder.TEntry", foreground="#9ca3af")
        self._placeholder = "type something with a typo — e.g. chcken bryani"
        self._placeholder_on = True
        self.query = ttk.Entry(row, font=("Segoe UI", 12), style="Placeholder.TEntry")
        self.query.insert(0, self._placeholder)
        self.query.pack(side="left", fill="x", expand=True)
        self.query.bind("<FocusIn>", self._clear_placeholder)
        self.query.bind("<FocusOut>", self._restore_placeholder)
        self.query.bind("<Return>", lambda _e: self.run_match())
        ttk.Button(row, text="Match", style="Accent.TButton",
                   command=self.run_match).pack(side="left", padx=(8, 0))

        self.match_result = tk.Label(tab, text="", font=("Segoe UI", 14, "bold"),
                                     bg=BG, anchor="w")
        self.match_result.pack(fill="x", padx=8)
        self.match_detail = tk.Label(tab, text="", font=("Segoe UI", 10), bg=BG,
                                     fg="#6b7280", anchor="w")
        self.match_detail.pack(fill="x", padx=8)

        self.scores = ttk.Treeview(tab, columns=("entry", "score"), show="headings", height=6)
        self.scores.heading("entry", text="Candidate")
        self.scores.heading("score", text="Score")
        self.scores.column("entry", width=300)
        self.scores.column("score", width=80, anchor="center")
        self.scores.pack(padx=8, pady=10, anchor="w")

    def _clear_placeholder(self, _event=None) -> None:
        if self._placeholder_on:
            self.query.delete(0, "end")
            self.query.configure(style="TEntry")
            self._placeholder_on = False

    def _restore_placeholder(self, _event=None) -> None:
        if not self.query.get().strip():
            self.query.delete(0, "end")
            self.query.insert(0, self._placeholder)
            self.query.configure(style="Placeholder.TEntry")
            self._placeholder_on = True

    def run_match(self) -> None:
        if self._placeholder_on:
            return  # nothing typed yet — the grey hint is not a query
        query = self.query.get()
        result = self.matcher.match(query)
        self.scores.delete(*self.scores.get_children())
        for entry, score in self.matcher.score_all(query)[:5]:
            self.scores.insert("", "end", values=(entry, f"{score:.3f}"))
        if result is None:
            self.match_result.configure(text="NO MATCH — abstained", fg="#b91c1c")
            self.match_detail.configure(
                text="below the confidence threshold, or ambiguous between near-equal candidates")
        else:
            self.match_result.configure(text=result.entry, fg="#166534")
            self.match_detail.configure(
                text=f"score {result.score:.3f}  ·  runner-up {result.runner_up:.3f}  ·  "
                     f"margin {result.score - result.runner_up:.3f}")


def smoke_test() -> None:
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app.item_name.delete(0, "end"); app.item_name.insert(0, "Chicken Biryani")
    app.add_item()
    # custom tax shorthand typed straight into the combobox
    app.item_name.delete(0, "end"); app.item_name.insert(0, "Special Thali")
    app.item_taxes.set("GST:12,CESS:1")
    app.add_item()
    app.add_charge()
    app.order_disc.insert(0, "10%")
    app.compute()
    text = app.output.get("1.0", "end")
    assert "GRAND TOTAL" in text, text
    assert "CESS@1%" in text, text
    app._clear_placeholder()
    app.query.insert(0, "chiken biryani")
    app.run_match()
    assert app.match_result.cget("text") == "Chicken Biryani"
    root.update()
    root.destroy()
    print("smoke ok")


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke_test()
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
