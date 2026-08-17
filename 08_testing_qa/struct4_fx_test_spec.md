# STRUCT-4 test spec — the three-currency book and its hand-derived oracles (REQ-PPM-010)

Status: ACTIVE (Wave 18, STRUCT-4). This is the MD-H1 derivation home for the STRUCT-4 goldens:
every literal below was worked BY HAND on this page before the code ran, and the tests assert
the literals — never a replay of the shipped formula (V-010-1). The unit-tier battery is
`packages/shared-python/tests/test_struct4_fx.py`; the demo-book twin is stage 27
(`irp_shared/demo/struct4_stage27.py`) asserting the SAME numbers on live PG.

## 1. The book

Three currencies (USD, EUR, GBP), one triangulated pair (GBP↔EUR has NO direct rate — only
GBP/USD and EUR/USD are published), and a node reporting in a currency its holdings are NOT
held in (REQ-PPM-010 as amended 2026-08-13):

| Node | Declares | Holds |
|---|---|---|
| FUND (root) | **EUR** | — (grouping) |
| SLEEVE-UK | **USD** | EQ-UK: 100 × 40.00 **GBP** · EQ-EU: 50 × 20.00 **EUR** |
| SLEEVE-CORE | (undeclared → inherits **EUR**) | EQ-US: 10 × 108.00 **USD** |

Published rates on the as-of date: **EUR/USD = 1.08** (1 EUR = 1.08 USD), **GBP/USD = 1.25**.
SLEEVE-UK's holdings currencies are {GBP, EUR}; its declared USD is in neither — the
foreign-reporting node the requirement demands.

## 2. Hand derivations

Conventions (fx_translation_v1.md §3): composite rate quantized to 12dp HALF_UP; money to 6dp
HALF_UP.

**The fund run (base = the root's declared EUR):**

- EQ-UK (GBP → EUR, TRIANGULATED through USD — no direct pair exists):
  legs = GBP→USD direct @ 1.25, then USD→EUR = reciprocal of EUR/USD @ 1.08.
  composite = 1.25 / 1.08 = 1.157407407407407… → **1.157407407407** (12dp; 13th digit 4, down).
  amount = 100 × 40.00 × 1.157407407407 = 4,629.6296296280 → **4,629.629630** (6dp; up).
- EQ-EU (EUR → EUR): identity, legs = []. amount = **1,000.000000**.
- EQ-US (USD → EUR): one reciprocal leg of EUR/USD @ 1.08.
  composite = 1/1.08 = 0.925925925925925… → **0.925925925926** (12dp; 13th digit 9, up).
  amount = 10 × 108.00 × 0.925925925926 = 1,080 × 0.925925925926 = 1,000.00000000008 →
  **1,000.000000**.

**SLEEVE-UK totals:**

- In the run base EUR: 4,629.629630 + 1,000.000000 = **5,629.629630 EUR**.
- The node-scoped run AT SLEEVE-UK (base = its declared USD — the acceptance read):
  EQ-UK: 100 × 40.00 × 1.25 = **5,000.000000** (direct, exact).
  EQ-EU: 50 × 20.00 × 1.08 = **1,080.000000** (direct, exact).
  Total = **6,080.000000 USD** ← THE ORACLE (`SLEEVE_UK_USD_ORACLE`).
- The rollup translation of the EUR total into the node's declared USD (the read-time path):
  5,629.629630 × 1.08 = 6,080.0000004 → **6,080.000000 USD** — the two paths agree on the
  literal; the 4×10⁻⁷ EUR-path dust dies in the 6dp quantize. This agreement is a property of
  THESE numbers, not a theorem — a different book may differ in the last decimal (double
  quantization), which is why the oracle pins the node-scoped run AND the translation must
  match it here.

**Fund total (EUR), demo book (stage 27):** 4,629.629630 + 1,000.000000 + 1,000.000000 =
**6,629.629630 EUR**.

### 2b. SLEEVE-ALBION (unit-tier book only — review fold C0/C12/C14)

The unit book adds a FOURTH node the demo book does not carry: SLEEVE-ALBION declares **GBP**
over one EUR holding (EQ-EU2: 10 × 50.00 EUR = 500.000000 EUR identity row) — the node whose
NODE-TOTAL translation itself TRIANGULATES, so the two-leg rollup branch and the node-scoped
triangulating consume both execute true:

- Translation EUR → GBP (no GBP/EUR pair in either direction): leg 1 = EUR→USD direct @ 1.08;
  leg 2 = USD→GBP = reciprocal of GBP/USD @ 1.25 (multiplier 1/1.25 = 0.8 exact).
  composite = 1.08 × 0.8 = **0.864** exactly → **0.864000000000** (12dp).
- Rollup at SLEEVE-ALBION (fund run, base EUR): total **500.000000 EUR** → translated
  500.000000 × 0.864 = **432.000000 GBP**; TWO legs; pivot STATED = **USD**.
- The node-scoped consume AT SLEEVE-ALBION (base resolves to its declared GBP): the EUR row
  converts EUR→GBP through USD — 10 × 50.00 × 0.864 = **432.000000 GBP**, two legs, stated
  pivot on the persisted bytes.
- **Unit-book fund total (EUR):** 6,629.629630 + 500.000000 = **7,129.629630 EUR**.

The HTTP fixture book (`test_exposure_endpoint.py::_declared_eur_book`) likewise carries a GBP
holding under its EUR fund so the triangulated row + stated pivot + `fx_pivot` wiring are
proven THROUGH the real endpoint (review fold C11): GBP→EUR = GBP→USD direct @ 1.25 then
USD→EUR reciprocal of EUR/USD @ 1.10.

**SLEEVE-CORE (inherits EUR = run base):** identity translation — 1,000.000000 EUR passes
through EXACTLY (the same-currency no-op regression clause: no lookup, no re-rounding, proven
on 6dp values that exceed every minor unit).

## 3. Non-vacuity (P18 clause 1)

Before ANY assertion about translated legs, the tests assert the count of rows with non-empty
`fx_legs` is **> 0** (fund run: 2 of 3 rows translate; the GBP row carries TWO legs with the
stated pivot USD). A single-currency book satisfying every FX clause vacuously is the exact
drift the 2026-08-13 PPM-010 amendment exists to stop.

## 4. The negative controls beside the goldens

- Undeclared root (build) / undeclared pinned chain (consume) → REFUSE, zero runs.
- Explicit `base_currency` contradicting a v3 node declaration → REFUSE (never override).
- Missing EUR leg for a declared-EUR sleeve on an all-USD book → build-time `FxRateNotFound`
  (the missing-rate refusal, FIRED).
- A v2 (pre-PPM-010) snapshot lacking the node-currency leg → the rollup reports
  `missing-fx:USD->GBP` with translated=None and NO exception (honesty, never retroactive
  refusal, never a fabricated 1.0).
- Legacy byte shape: a v2-pinned run's `fx_legs` carry NO `pivot` key (reproduction bytes
  unchanged); `derive_pivot` recovers USD at read time.
