# FX translation conventions v1 (STRUCT-4, REQ-PPM-010 / DP-14)

Status: ACTIVE (Wave 18, STRUCT-4). Scope: the conventions the reporting-currency translation
executes — the triangulation pivot, reciprocal legs, and rounding — entered per the ratified
DP-14 discipline (roadmap Part 4 rule 6a): **every convention cites its governing text as a
verbatim quote with a locator**, and the review's citation lane reads ONLY the cited sources.
No convention below rests on model recall.

The executing code: `irp_shared/marketdata/legs.py` (`_resolve_path`, `compose_effective_rate`,
`serialize_legs`, `derive_pivot`), `irp_shared/marketdata/convert.py` (`convert`, the same path
order duplicated by design), `irp_shared/exposure/service.py` (`_emit_row`, `rollup_exposure`).

## 1. Triangulation through a defined pivot

> "Cross rates are derived by triangulation through a defined base currency; direction (quote
> convention) is explicit."
> — `05_analytics_methodologies/numerical_quant_standards.md`, §3, row **QS-08**.

The defined pivot is the platform base (USD today), configurable per QS-07's companion row:

> "| FX base currency | **USD** as platform base/reporting currency | Configurable per
> tenant/portfolio (QS-07) |"
> — `05_analytics_methodologies/numerical_quant_standards.md`, §2A Ratified Defaults table
> (line 33).

Path order (shipped since P2-2, OD-030): identity → direct → reciprocal →
triangulation-through-pivot, at most TWO legs; a missing leg fails closed (`FxRateNotFound` at
resolution; a `missing-fx:` gap at compute) — never interpolation, never a silent 1.0.

**DP-12 (ratified 2026-08-15):** the pivot of a two-leg path is STATED in new rows' `fx_legs`
(a `"pivot"` key on each leg dict) and DERIVED at read time for shipped rows (the currency the
travel direction passes through). Shipped pinned bytes are never rewritten — `fx_legs` is a
byte-compared reproduction field, so pivot-stating keys to the snapshot's own
`binding_predicate_version` marker (`v3:…+node-fx`), never to code age.

## 2. Reciprocal legs

> "`rate` = \"1 base = rate quote\" (QS-08)"
> — `04_data_model/canonical_data_model_standard.md`, ENT-024 row (line 106).

A reciprocal leg is a read-time inversion of a published rate: when only the `b/q` row exists,
the `q → b` hop multiplies by `1/rate`. The persisted leg evidence stores the PUBLISHED row's
own orientation (`base_currency`/`quote_currency` as published) with `direction: "reciprocal"`;
the inversion lives ONLY in the direction + multiplier, so the stored bytes remain a faithful
reference to the published row (`fx_rate_id` provenance). A reader rendering the path must
invert the pair for travel display — the RunDetail drill-in does.

## 3. Rounding (the minor-unit question)

> "Rounding convention is explicit per context (default: round-half-to-even / banker's rounding
> for aggregation); documented per methodology. **Registered exception:** deterministic
> **canonical serialization / `quantize` uses `ROUND_HALF_UP`** (the snapshot + derived-result
> reproducibility path — e.g. P2-3 `exposure_amount` and the effective composite `fx_rate`), so
> a stored value re-computes exactly from its stored, rounded inputs (supports TR-13)."
> — `05_analytics_methodologies/numerical_quant_standards.md`, §2, row **QS-04**.

> "[…] The **effective composite rate** produced by a triangulated/reciprocal path is itself a
> governed numeric value: the **multiplicative composite** of its legs,
> `ROUND_HALF_UP`-quantized to its declared scale, **version-pinned to the run** via the
> snapshot-captured FX components …"
> — `05_analytics_methodologies/numerical_quant_standards.md`, §3, row **QS-09**.

The declared scales: the composite rate quantizes to **12 decimal places** and money amounts to
**6 decimal places**, both `ROUND_HALF_UP` (`_FX_QUANTUM`/`_MONEY_QUANTUM`,
`irp_shared/exposure/service.py`). The STRUCT-4 node-total translation reuses exactly these:
`translated = quantize6(total × quantize12(composite))`.

**ISO-4217 minor units are deliberately NOT a rounding input.** Currency identity is ISO 4217
per the data-model standard:

> "Monetary amounts stored as decimal with explicit `*_currency` (ISO 4217) — never binary
> float (QS standards)."
> — `04_data_model/canonical_data_model_standard.md`, §2 Naming & Modeling Standards
> (DM-N), row **DM-N-04** (line 30).

`currency.minor_units` (ENT-005) is INERT reference data — no shipped compute consults it, and
introducing minor-unit rounding would CHANGE persisted governed numbers (the 6dp money scale is
the ratified convention above). REQ-PPM-010's same-currency regression guard depends on this:
the identity path returns the amount untouched at full precision, asserted on a value carrying
more decimals than any currency's minor unit (`test_struct4_fx.py::
test_same_currency_noop_is_exact_on_the_composed_path`, plus the rollup identity pass-through).

## 4. Reporting-currency declaration (DP-11, for completeness)

The translation target is the node's DECLARED reporting currency: its own
`portfolio.base_currency_code`, else the nearest declared ancestor's; nothing declared up the
chain REFUSES (`UndeclaredReportingCurrencyError`) — the pre-STRUCT-4 silent-USD tail is dead
on both the build and consume paths. Migration `0073` backfilled `'USD'` onto every
previously-undeclared ROOT (the semantics those books already computed under, now stated);
a NULL on a non-root node means INHERIT. Snapshot FX-completeness (v3 builds) pins legs for
every conversion target in `{run base} ∪ {resolved node reporting currencies in scope}`, so a
node read translates from pins alone (AD-014 — no live rate ever enters a governed read).

Two declared narrowings (review folds, pinned by tests):

- **The override-conflict refusal fires on v3 artifacts only** (`test_v2_node_scoped_conflicting_
  base_still_completes`). Migration 0073 backfilled `'USD'` onto every previously-undeclared
  root, so firing the check against v2-era artifacts would make legacy explicit-base runs'
  reproductions refusable — new strictness keys to the artifact's own version marker (the
  STRUCT-3 lesson). The refusal is SYMMETRIC where it applies: a v3 BUILD with an explicit base
  contradicting a declared scope refuses too (`test_build_path_conflicting_base_refuses_
  symmetrically`) — the permissive alternative mints runs whose own CTRL-018 reproduction the
  consume-path check would refuse.
- **Pinned resolution is bounded by the pin.** A scope root inheriting its currency from an
  ancestor ABOVE the pinned subtree resolves at BUILD time (live walk) but not from the pin, so
  such a run's own rollup honestly reports no declared reporting currency rather than guessing
  — the pin cannot answer what it never saw. Reproduction is unaffected (the adapters pass the
  stored base).
