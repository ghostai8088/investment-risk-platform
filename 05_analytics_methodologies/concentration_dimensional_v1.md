# Methodology — Dimensional Concentration (share / CR-N / HHI) v1

**Model code** `concentration.dimensional` · **version label** `v1` · **entity** ENT-069 `concentration_result` · **migration** `0057` · **slice** CON-1 (Wave-14 slice 1; the 23rd governed family)

> **Written at RPT-1 (2026-08-05).** `CONCENTRATION_METHODOLOGY_REF` previously carried the prose
> string `"docs: CON-1 decision record Parts 1-2 (OQ-CON-1-1..28)"` — a pointer a reader cannot
> follow and a report cannot render, against a ratified standard (OD-P3-0-C) requiring a methodology
> doc before any risk method ships. This document replaces that string; the ref now resolves, and
> the `test_methodology_refs.py` census makes the property enforced rather than remembered. Content
> is reconstructed from the registered `model_assumption` / `model_limitation` rows in
> `concentration/bootstrap.py`, the governed source of truth.

## Purpose & applicability

How concentrated a book is along a **declared classification dimension** — by sector, by issuer, by
country, by any dimension the classification machinery (REF-1) carries. Three shapes of the same
question: the **share** of the largest bucket, the combined share of the top **N** (CR-5), and the
**Herfindahl–Hirschman Index** over classified buckets.

Applies to any book with a COMPLETED exposure run and current-head classification assignments on the
chosen dimension, where classifiable coverage meets the declared floor.

It is deliberately **not** a regulatory ratio — see *Known limitations*, which is the load-bearing
section of this document.

## Inputs & data policy

- **One COMPLETED `EXPOSURE_AGGREGATE` run** — its subtree defines scope.
- **Current-head classification assignments** on the declared dimension (ENT-068), resolved
  **as-of BUILD** and pinned as `CLASSIFICATION` snapshot components, with the scheme itself pinned
  as a `CLASSIFICATION_SCHEME` component.

The computation reads **pinned content only** (AD-014 / TR-09). Upstream run and portfolio ids are
re-resolved under the acting tenant before being stamped into hard FKs (the P3-5 cross-tenant-FK
guard). A snapshot mixing live scheme VERSIONS is refused pre-build.

## Formulas & numerical standards

Let `long` = atoms with signed `exposure_amount > 0` (**VALUE SIGN**, not position direction), and
`total_long = Σ long`.

**1 — Bucket share.**
```
share_invested_long(bucket) = bucket_long / total_long
```

**2 — CR-N.** The sum of the `N` largest **classified** bucket shares (`N = 5` in v1).

**3 — HHI.** `Σ share_b²` over **classified** buckets, on the FRACTION scale.

**4 — Residual treatment (the load-bearing rule).** `UNCLASSIFIED` and `UNCLASSIFIABLE` residuals
stay **IN the denominator** and **OUT of rankings and HHI**. Including them in rankings would invent
a "bucket" nobody assigned; excluding them from the denominator would inflate every share.

**5 — Classifiable coverage.**
```
coverage = classified / (classified + UNCLASSIFIED)
```
gated by the declared floor; a run below it **refuses**.

**6 — Numerical standard.** All ratios are taken from **UNROUNDED** values, then quantized
`HALF_UP` to **6 decimal places**. Quantizing before ratio-taking would let rounding accumulate into
the concentration measures.

## Assumptions

Registered as `model_assumption` rows; v1 admits **exactly** these values, and a differing
declaration is refused rather than silently accepted:

| Assumption | v1 value |
|---|---|
| `concentration.denominator_basis` | `INVESTED_LONG` |
| `concentration.long_predicate` | `VALUE_SIGN` |
| `concentration.scope` | `EXPOSURE_RUN_SUBTREE` |
| `concentration.classification_as_of` | `BUILD` |
| `concentration.cr_n` | `5` |
| `concentration.hhi_scale` | `FRACTION` |
| `concentration.coverage_floor` | declared per version (6dp canonical) |

The `denominator_basis` vocabulary is enforced at the **database** by a CHECK constraint
(migration `0062`), not only in code.

## Validation / reproduction tests

- `test_concentration_kernel.py` — the arithmetic, the residual rule, the coverage gate.
- `test_concentration_pg.py` — grain, RLS, append-only, pin-drift.
- `test_limit_registry.py` — the ten concentration metrics registered FRACTION/no-benchmark.
- `test_methodology_refs.py` — the census enforcing this document's existence and sections.
- Demo stage 19 walks the family on the PG battery; stage 20 exercises LIM-2's limits over it.

## Governed-number contract

Every row binds `dataset_snapshot` + `calculation_run` + a registered `model_version`, is **IA
append-only**, and carries symmetric per-tenant FORCE RLS. `denominator_basis` is stamped **on the
row** so a limit evaluated against it can require a matching basis — an evaluation-time match written
against the row, not against the code's current default.

## Known limitations

Registered as `model_limitation` rows (verbatim in `concentration/bootstrap.py`) — **and this is the
section a report must render**:

1. **`share_invested_long` is NOT the UCITS Art. 52, IRC 851(b)(3), Solvency II or BCBS ratio.** No
   denominator those regimes require is computable on this schema. Regulatory-shaped limits are
   **refused** until LIM-2's basis machinery exists.
2. Classification is **as-of-BUILD** (a backdated exposure run buckets by build-time heads); the
   long/short decomposition is by **VALUE SIGN**; **HHI is downward-biased by coverage** on
   partially-covered books (bounded by the declared `coverage_floor`); and a refused-run streak
   leaves any future limit evaluating the **last COMPLETED** run — staleness routed to `limit_health`
   at LIM-2.

## External benchmarks

- **[V] Herfindahl–Hirschman Index** — the standard `Σ s²` definition; the FRACTION-scale choice
  (rather than the US DOJ/FTC 0–10,000 integer scale) is declared as an assumption, not assumed.
  *Verified against the published definition.*
- **[C] UCITS Art. 52 / IRC §851(b)(3) / Solvency II / BCBS** — cited **only to disclaim**: each is
  named in the limitations as a ratio this number is *not*. No computation here follows them.
- **[U] CR-5 as the concentration-ratio cut** — `N = 5` is conventional in industry reporting and is
  **uncited** as a regulatory or academic requirement; it is a declared parameter precisely because
  no authority fixes it.
