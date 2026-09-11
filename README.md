# Order charge & tax engine

A Python 3.11+ module that computes a fully reconciled order breakdown (Part A) and a
free-text catalog matcher that knows when *not* to answer (Part B). No runtime
dependencies; `pytest` is the only test dependency.

## Run

```bash
pip install pytest        # the only dependency, test-only
python -m pytest          # runs all 80 tests (Part A + Part B)
python examples/demo.py   # worked example: mixed inclusive/exclusive order, discounts, charges
python evaluate_matcher.py               # Part B metrics + threshold sweep
```

### Try it interactively

```bash
python gui.py             # sleek two-tab GUI (tkinter, stdlib): order builder + live matcher
python order_cli.py       # terminal wizard: build an order step by step
python order_cli.py --match   # terminal loop for the Part B matcher
python examples/my_order.py   # editable script template, if you prefer code
```

The UIs are thin shells over the same API (`orderengine/textio.py` holds their shared
parsing/formatting); all calculation logic lives in the engine and is covered by the tests.
Taxes are not limited to the presets: the GUI dropdowns have a **Custom GST…** option
that opens a small form — one row per component, name + rate, add as many as needed.
The CLI and scripts take the equivalent shorthand (`12`, `CGST:6,SGST:6`, `GST:12,CESS:1`) —
any component names, any rates.

Public API: `orderengine.compute_order(Order) -> OrderBreakdown` (see `examples/demo.py`).
All money enters as `Decimal` or `str`; **`float`, `bool` and `int` are rejected** (int is
ambiguous — rupees or paise?). Every money field in the output is an `int` number of paise,
so exactness is auditable: order totals are plain integer sums of line-level figures.

## The three open decisions

**1. Rounding — per line, per tax component, HALF_UP.** `round_paise()` in `money.py` is the
*only* rounding primitive. A line's total tax is *defined* as the sum of its rounded
components; a combined rate is never computed (CGST 2.5% + SGST 2.5% on ₹10.10 gives
0.25 + 0.25 = 0.50, where a flat 5% would give 0.51 — pinned in
`test_engine_exclusive.py`). HALF_UP matches common Indian invoicing practice and user
expectation; ROUND_HALF_EVEN was considered and rejected — its anti-bias property is
irrelevant at invoice scale and it surprises humans. When a rounded distribution must sum
to a fixed total (order discount across lines, an inclusive tax pot across components),
the **largest remainder method** (`allocation.py`) distributes the leftover paise:
`sum(parts) == total` always, each part within 1 paisa of its exact share, deterministic
tie-breaking (largest fractional remainder → larger weight → lower index).

**2. Inclusive tax — divide, round, subtract.** `base = round(amount × 100 / (100 + Σrates))`,
then `tax = amount − base` **exactly by subtraction**: the base absorbs the rounding, so a
quoted inclusive price is honoured to the paisa, always (₹100 incl. 18% → 84.75 + 15.25).
Multi-component taxes split the tax pot by rate via largest remainder. When the result
isn't a clean number of paise, the rounding lands in the base, never in what the customer
pays — partners reconcile against the charged amount, and `base + taxes == amount` holds
by construction.

**3. Discounts — before tax, and the pot is rounded once.** Discounts reduce the taxable
base; tax is computed on the discounted amount (standard GST treatment — tax follows the
consideration actually paid). The order-level discount is rounded **once** into an integer
pot, then allocated across items (never charges) by largest remainder, weighted by each
line's post-item-discount amount — so per-line figures sum to the order figure by
construction, not adjustment. *Refinement the spec's tensions force:* on a tax-**inclusive**
line, the discount applies in the inclusive domain and the discounted amount is then split.
This keeps both promises at once: the customer pays exactly `quoted − discounts`
(₹118 incl. 18% with ₹18 off → pays exactly ₹100.00), and the discount still reduces base
and tax proportionally. Discounting the pre-tax base instead would let the paid total
drift ±1 paisa from the quote — a clearly wrong answer for a price the customer saw.

**Reconciliation guarantee.** The pipeline (`engine.py`) drops precision in exactly four
marked places, each immediately reconciled by subtraction or largest-remainder allocation;
aggregation is pure integer summation. `test_reconciliation_property.py` throws 1,000
seeded random orders (mixed inclusive/exclusive, split rates, both discount kinds, taxed
charges) at nine invariants, including the grand total derived two independent ways.

## Assumptions (beyond the three decisions)

- Additional charges are never reduced by the order-level discount, and are taxed
  independently (each may be inclusive or exclusive, like a line).
- Impossible inputs **error, never clamp**: a discount exceeding its base, percent > 100,
  negative amounts, sub-paisa money (`₹1.005`), quantity < 1, duplicate tax-component
  names within one item. Bad *types* raise `TypeError`; bad *values* raise `ValidationError`.
- Order-level `tax_totals` group by `(name, rate)`: CGST@2.5 and CGST@6 stay separate rows.
- Zero-price items, zero-rate taxes, empty orders and charge-only orders are all valid.
- Quantity multiplies the unit price *before* any rounding (3 × ₹33.33 = ₹99.99 exactly).

## Part B — free-text matching

`CatalogMatcher` (stdlib only) scores `0.5 × soft-token-F1 + 0.5 × SequenceMatcher` over
normalised text (casefold, accents stripped, quantities like "2 x" dropped, word order
ignored). **When not to answer:** it abstains when the best score < 0.70 (likely
out-of-catalog), or when the top two scores are within 0.08 of each other (ambiguous —
"paneer" matches seven dishes) unless the best is ≥ 0.95 (a verbatim "chicken tikka" must
not be blocked by the existence of "Chicken Tikka Masala").

**Measurement:** `python evaluate_matcher.py` runs 52 labeled cases (typos,
abbreviations, reorderings, quantity noise, ambiguous stubs, out-of-catalog queries)
and prints precision (0.97), coverage (1.00), false-answer rate, and a
**threshold × margin sweep grid** — the defaults were picked from that grid, not by feel.
Known failure mode, kept deliberately visible: "chicken burger" → "Butter Chicken" (0.85);
eliminating it costs 20 points of coverage (see the 0.85 sweep row). **With real usage
data** I would log `(query, result, accepted/corrected)` from production, grow the eval set
from real corrections, re-run the sweep per release, and let confirmed pairs become an
alias table that short-circuits scoring.

## Edge cases: handled vs. knowingly left

Handled: everything under Assumptions, plus 1-paisa inclusive amounts (₹0.01 incl. 18% →
base 0.01, tax 0), 100%-discounted lines absorbing none of the order discount, HALF_UP at
exact .5 boundaries, tie-breaking in allocation (pinned tests).
Knowingly left: multi-currency; negative lines/refunds (allocation already supports
negative totals, but returns need their own semantics); compounding taxes (tax-on-tax,
e.g. cess on GST — the model taxes each component on the same base); rupee-level rounding
of the final invoice total (GST §170 style) — trivially added as a display step, kept out
of the core so the engine stays exact.

## With more time

Order-level serialisation (`to_dict`/JSON) for the transmit path; a `hypothesis` suite in
addition to the seeded loops; refund/credit-note flows; charge-level discounts; a benchmark
on the matcher at 10k+ catalog size (current one is O(catalog) per query, fine for hundreds).

## Questions I would have asked

Should the partner-facing grand total be rounded to the rupee (GST §170)? Do discounts
apply to delivery/handling charges anywhere? Are tax rates ever compounded on other taxes?
For inclusive prices with discounts, is "customer pays exactly quoted − discount" the
agreed contract (I assumed yes)? What does the partner reconcile against — line totals,
tax-head totals, or both (I made both exact)?
