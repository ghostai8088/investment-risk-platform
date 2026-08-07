# Methodology — Liquidity Tier Distribution (illiquid / highly-liquid share) v1

**Model code** `risk.liquidity_tiers` · **version label** `v1` · **entity** ENT-071 `liquidity_result` · **migration** `0061` · **slice** LQ-1 (Wave-14 slice 6; the 24th governed family)

> **Written at RPT-1 (2026-08-05).** `LIQUIDITY_METHODOLOGY_REF` previously carried the prose string
> `"docs: LQ-1 decision record Parts 1-2 (OQ-LQ-1-1..20)"`. This document replaces it so the
> reference resolves and a report can render it; `test_methodology_refs.py` enforces that property
> for all 27 registered references. Content is reconstructed from the registered `model_assumption`
> / `model_limitation` rows in `liquidity/bootstrap.py`, the governed source of truth.

## Purpose & applicability

What share of a book sits in each liquidity category, and in particular **how much is illiquid**.
The tiers themselves are **captured judgments** — a steward records an assessment against the SEC
Rule 22e-4(b)(1)(ii) four-category ladder; the platform never derives one. This model takes those
recorded judgments, weights them by exposure, and produces a governed distribution.

Applies to a book with a COMPLETED exposure run whose instruments carry current-head
`LIQUIDITY_TIER` assignments under a single live scheme version, where classifiable coverage meets
the declared floor and the tier heads are no older than the declared maximum age.

**The name is the control.** The metric is `illiquid_share_invested_long`, not `pct_illiquid`,
because a number called `pct_illiquid` invites exactly the regulatory reading the *Known
limitations* section refuses.

## Inputs & data policy

- **One COMPLETED `EXPOSURE_AGGREGATE` run** — its subtree defines scope.
- **Current-head `LIQUIDITY_TIER` classification assignments** (ENT-068) under one live scheme
  version, resolved **as-of BUILD**, pinned as `CLASSIFICATION` components with the ladder pinned as
  a `CLASSIFICATION_SCHEME` component.

Reads **pinned content only** (AD-014 / TR-09). The snapshot builder refuses pre-build on: a scheme
of the wrong dimension, mixed live scheme **VERSIONS** over the live book, mixed classification
**basis**, and an exposure run with no visible atoms — each refusal executed by a test that makes it
FIRE (`test_liquidity_snapshot.py`), each asserting nothing was persisted.

**Staleness** is read from the pinned component's `pinned_system_from` column, not from a JSON key,
and a ladder older than `liquidity.tier_max_age_days` **refuses the run** rather than pinning a stale
assessment.

## Formulas & numerical standards

Let `long` = atoms with signed `exposure_amount > 0` (**VALUE SIGN**), `total_long = Σ long`.

**1 — The headline number.**
```
illiquid_share_invested_long = ILLIQUID_long / total_long
```

**2 — The bucket vector.** One share per ladder category, plus a `__UNCLASSIFIED__` residual. An
instrument with **no** current-head tier is UNCLASSIFIED and stays **IN the denominator** and **IN
the classifiable-coverage test** — it is a gap in the book, not a property of the instrument. There
is deliberately **no UNCLASSIFIABLE bucket**: unlike CON-1's issuer dimension, every instrument
*can* carry a tier.

**3 — Coverage.** `coverage_ratio = tiered_long / total_long`, with `coverage_classifiable` carrying
the tiered **AMOUNT** (money, not a second ratio — the ratio is already `coverage_ratio`). A run
below the declared floor **refuses**.

**4 — Numerical standard.** Shares taken from **UNROUNDED** ratios, then quantized `HALF_UP` to **6
decimal places**.

## Assumptions

Registered as `model_assumption` rows; v1 admits **exactly** these values:

| Assumption | v1 value |
|---|---|
| `liquidity.denominator_basis` | `INVESTED_LONG` |
| `liquidity.long_predicate` | `VALUE_SIGN` |
| `liquidity.scope` | `EXPOSURE_RUN_SUBTREE` |
| `liquidity.tier_as_of` | `BUILD` |
| `liquidity.tier_vocabulary` | `SEC_22E4:` + the four ladder codes |
| `liquidity.illiquid_partition` | `ILLIQUID` (a **set of one**, declared not hard-coded) |
| `liquidity.coverage_floor` | declared per version (6dp canonical) |
| `liquidity.tier_max_age_days` | declared per version |

`illiquid_partition` is declared as a single-member set rather than hard-coded so a future ladder
(e.g. AIFMD's seven day-buckets) declares a genuinely different partition and is **refused against
v1** rather than silently accepted.

## Validation / reproduction tests

- `test_liquidity_kernel.py` — the arithmetic, the LONG boundary (a zero-amount atom is not long),
  `coverage_classifiable` as an amount rather than a second ratio, the untiered-in-denominator rule.
- `test_liquidity_snapshot.py` — the four pre-build refusals, each made to FIRE, each asserting
  nothing persisted.
- `test_liquidity_pg.py` — RLS, append-only, grain.
- `test_model_registry.py` — the P8 census (LQ-1's BLOCKING was being the only one of 24 families
  missing `assert_model_version_of`; the census exists so that class cannot recur).
- Demo stage 23 walks the family on the PG battery.

## Governed-number contract

Every row binds `dataset_snapshot` + `calculation_run` + a registered `model_version` (all three FKs
NOT NULL at the database), is **IA append-only**, symmetric per-tenant FORCE RLS. The captured half —
the tier assignments — mints **no entity**; it rides REF-1's classification rail.

## Known limitations

Registered as `model_limitation` rows and **rendered on the run-detail surface** (OQ-LQ-1-8: a
limitation no screen renders is not a control). Verbatim in `liquidity/bootstrap.py`:

1. **This is NOT the SEC Rule 22e-4 15% test.** The rule's ratio is against **NET ASSETS**
   (17 CFR 270.22e-4(b)(1)(iv)); this denominator is the invested-long book, which excludes cash,
   receivables and any asset carrying no exposure row, and includes no liabilities. The reported
   share may **OVERSTATE or UNDERSTATE** the regulatory ratio depending on the book's cash, leverage
   and short exposure, and **the direction is not determinable** without a net-assets figure. Limits
   are refused against this family until a NAV entity exists.
2. Tier assignment is **INSTRUMENT-grain** and therefore does not reflect the fund-specific
   **position-size** determination 22e-4(b)(1)(ii)(B) requires. Two funds holding the same security
   at very different sizes receive the same tier here.
3. Tiers are **captured judgments, not computed**. Heads are resolved as-of BUILD, so a backdated
   exposure run is tiered by build-time heads; heads older than the declared max age refuse the run.
4. The highly-liquid coverage figure is **the ladder's first category only**. It is NOT
   22e-4(b)(1)(iii)'s highly liquid investment minimum, which is net-assets-denominated and carries
   board-approval, review and shortfall-reporting obligations this platform does not implement.

## External benchmarks

- **[V] 17 CFR 270.22e-4** — fetched from the govinfo XML at LQ-1 and read in full.
  **(b)(1)(ii)** names the four categories this ladder uses; **(b)(1)(ii)(B)** makes position size a
  mandatory classification input (hence limitation 2); **(b)(1)(iv)** is the 15%-of-net-assets limit
  (hence limitation 1); **(a)(8)** defines illiquid *"as determined pursuant to the provisions of
  paragraph (b)(1)(ii)"*. *Verified against the primary source — an earlier draft's ellipsis had
  deleted the (a)(8) clause that refuted its own argument.*
- **[C] AIFMD liquidity bucketing** — cited only as the motivating example for why
  `illiquid_partition` is a declared set rather than a constant. Nothing here implements it.
- **[U] The choice of the invested-long denominator** — defensible as the only basis computable on
  this schema, but **uncited**: no authority prescribes it, which is exactly why the metric carries
  the basis in its name and the limitation states the error direction is indeterminate.
