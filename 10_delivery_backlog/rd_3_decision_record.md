# RD-3 Decision Record — verify-path hardening + guard/parse adoption sweep (Wave-5 slice 1)

> **Status: RATIFIED 2026-07-14** (OQ-RD-3-1…5 all approved as recommended). The Wave-5 early hygiene slice ratified at
> the Wave-4 close (OQ-W4C-3): the three TIPPED register items + the PG seed-collision test-infra
> ride-along. NO migration, NO governed number, NO new permission/audit code. The RD-1/RD-2
> precedent form: census-verified scope, byte-preserving where behavior is not the defect, every
> deviation recorded.

## Part 1 — Problem (the census, verified 2026-07-14 at `main` `db00173`)

**(a) The snapshot verify path can 500 instead of reporting drift/refusal — and the exposed class
GREW in Wave 4 (P3-8 deferral, trigger fired twice).** Two defect shapes in
`snapshot/service.py`:

1. **Missing except-tuple entries (gone-row 500s):** `verify_snapshot`'s except tuple catches the
   `*NotVisible`/`*SnapshotError` classes for most branches, but NOT
   `ScenarioSnapshotError` (raised by `_resolve_scenario_shock_row` — the SCENARIO branch) and NOT
   `ProxyWeightSnapshotError` (raised by `_resolve_desmoothed_return_row` — the DESMOOTHED_RETURN
   branch). A deleted/cross-tenant scenario-shock or desmoothed-return pin is an unhandled 500
   today, where every sibling class reports the component as DRIFTED. (`VarTotalSnapshotError`
   subclasses `VarSnapshotError` — covered; `_resolve_proxy_mapping_row` raises
   `FactorExposureSnapshotError` — covered.)
2. **Malformed-pinned-content 500s:** `_reresolve_content`'s series/composite branches parse
   `captured_content` (`json.loads` + keyed access: `pinned["rows"]`, `pinned["benchmark_id"]`,
   `pinned["scenario_definition_id"]`) with NO malformed-content wrapper — a truncated/tampered/
   non-object pin raises KeyError/ValueError/TypeError as a raw 500. The binders solved this exact
   class in P3-C3 (the uniform `(KeyError, TypeError, ValueError, ArithmeticError)` → governed-
   refusal wrapper); the verify path never got it.

**(b) The PA-1 D-2 instrument-guard fold (next-touch fired at PA-3, unpaid).**
`marketdata/proxy_mapping.py:_resolve_instrument_id` is a hand-rolled body byte-equivalent in
predicate to `reference/guards.assert_instrument_in_tenant(error=…)` (both: explicit-tenant
`select(Instrument.id)`, refuse on None). One call site. Delta: the guard returns None (caller
keeps using `str(instrument_id)`) and its message reads "instrument … is not visible…" vs the
local "private instrument … is not visible…" — a message normalization, the RD-2 OQ-3 precedent.
**NOT foldable:** `reference/instrument.py:resolve_instrument` — a resolver returning the full row
(consumed by terms/identifier binders), not a None-returning guard; recorded here so the register
item closes honestly with a half-fold + this note.

**(c) MD-H1 deferral C — annex adoption breadth (self-declared "wave-close candidate; mechanical,
zero behavior change" — due now).** Census today: the PG GUC re-arm fixture
(`persistent_tenant_context`) is adopted in **1 of 39** `*_pg.py` suites;
`calc/parse.parse_strict_decimal` is adopted in **4** services (desmoothing, proxy_weight,
scenario, var_backtest) while **~23 raw `Decimal(...)` parse sites** over pinned/declared content
remain across 10 binder/bootstrap files (most already sit INSIDE the P3-C3 malformed-pin
wrappers, so adoption there is refusal-class/message consistency, not a behavior fix).

**(d) Ride-along — the PG cross-module seed collision (test-infra; sole record = PA-4 Part 6.4).**
`test_data_quality_pg` / `test_lineage_pg` / `test_synthetic_pg` collide when the full suite runs
in ONE session against an unreset DB: the synthetic seeder inserts deterministic `uuid5` ids
(deliberate product behavior — `synthetic/ids.py` docstring) and the DQ/lineage suites seed fixed
SYSTEM-tenant codes (`GLOBAL_OK`, vendor source codes) non-idempotently. Isolated runs green; CI
green (per-file steps). Local full-suite runs intermittently red — exactly the noise that masks
real regressions.

## Part 2 — Decision (OD-RD-3-A…E)

- **OD-RD-3-A — verify-path semantics: malformed or unresolvable pinned content = DRIFT, never a
  500.** Grow `verify_snapshot`'s except tuple with the two missing classes AND wrap the
  `_reresolve_content` call with the P3-C3 malformed-content tuple
  `(KeyError, TypeError, ValueError, ArithmeticError)` → the component reports DRIFTED. Rationale:
  verify's contract is "does the pinned content still reproduce?" — content that cannot even be
  parsed has definitionally failed reproduction; a 500 hides tamper evidence. `verify_snapshot`
  stays no-emit (OD-023) and read-only; `SnapshotNotFound` on the header stays a raise (the
  caller asked about a snapshot that isn't theirs — not drift).
- **OD-RD-3-B — the proxy_mapping guard fold:** `_resolve_instrument_id` → delegate to
  `assert_instrument_in_tenant(error=ProxyMappingValueError)`; the call site keeps
  `str(instrument_id)`. Message normalizes to the guard's ("instrument …" not "private
  instrument …") — ratified here, the RD-2 OQ-3 precedent. The `resolve_instrument` variant is
  recorded NOT-foldable (Part 1b); the PA-1 D-2 register item closes with this half + that note.
- **OD-RD-3-C — MD-H1-C adoption is CONSISTENCY-scoped, not semantics-scoped:** adopt
  `parse_strict_decimal` ONLY at sites where the strict parse is provably semantics-identical
  (already inside a malformed-pin wrapper, or parsing registration-validated text); any site
  where it would CHANGE behavior is SKIPPED AND LISTED in Part 5 (no silent semantic drift from a
  hygiene slice). The GUC re-arm fixture is adopted in the PG suites that re-use a session across
  commits (enumerated at implementation; suites that never commit mid-test don't need it — the
  count is evidence, not the goal).
- **OD-RD-3-D — seed idempotency, not id-salting:** fix (d) by making the seeds idempotent
  (exists-check / `db/integrity.resolve_or_insert` in the synthetic builder's row inserts and the
  DQ/lineage test fixtures' SYSTEM-tenant seeds). The deterministic `uuid5` ids are a documented
  product FEATURE and stay; salting them would break the seeder's contract. Seeding twice becomes
  a no-op — which also makes local re-runs against a dirty schema deterministic.
- **OD-RD-3-E — scope fence:** NO migration; NO governed-number/binder behavior change (the
  verify path is a READ surface; binder compute paths untouched); `audit/service.py` FROZEN;
  test-and-shared-code only. Full battery + local-PG + CI-watch-to-green; proportionate review
  (the RD-2 form: 4 finders, at least one adversarial on the OD-A semantics change).

## Part 3 — Implementation steps

1. **(a)** Grow the `verify_snapshot` except tuple (+`ScenarioSnapshotError`,
   `+ProxyWeightSnapshotError`) and add the malformed-content wrapper around
   `_reresolve_content`; tests: a tampered `captured_content` (truncated JSON, non-object, missing
   key) per composite branch → `ok=False` + the component in `drifted_components`, no raise; a
   gone scenario-shock row and a gone desmoothed-return row → drift not 500.
2. **(b)** The guard fold + message normalization; the existing proxy-mapping refusal tests keep
   passing with the normalized message asserted.
3. **(c)** Enumerate + adopt: `parse_strict_decimal` at the semantics-identical sites (per-site
   verification note in the PR); the re-arm fixture into the committing PG suites. Zero behavior
   change expected — the battery must show zero golden/refusal-message diffs outside (b)'s
   ratified message.
4. **(d)** Idempotent seeds (synthetic builder + the two test fixtures); prove: full PG suite
   twice against ONE unreset schema → green both times (the collision's reproduction becomes the
   regression test).
5. `make check` + full local-PG (schema-reset AND dirty-schema double-run) + review + fold +
   CI-watch-to-green + PR + merge under the extended grant; Part 5 dispositions.

## Part 4 — Open questions for ratification

- **OQ-RD-3-1 — OD-A: malformed/unresolvable pinned content reports as DRIFT (ok=False) rather
  than raising.** *Recommend APPROVE — verify's contract is reproduction; unparseable content is
  failed reproduction and a 500 hides tamper evidence. The alternative (a new
  MalformedPinError raise) makes every verify caller handle a new class for zero information
  gain.*
- **OQ-RD-3-2 — OD-B incl. the message normalization** ("private instrument …" → "instrument …").
  *Recommend APPROVE — the RD-2 OQ-3 precedent; one message, one call site, tests updated.*
- **OQ-RD-3-3 — OD-C's consistency-scoped adoption with a skip-and-list rule.** *Recommend
  APPROVE — MD-H1-C promised "zero behavior change"; the skip-list keeps that promise auditable.*
- **OQ-RD-3-4 — OD-D seed idempotency (exists-check/resolve_or_insert), ids unchanged.**
  *Recommend APPROVE — fixes the collision at its cause; the double-run-green proof becomes a
  standing local-validation capability.*
- **OQ-RD-3-5 — the scope fence (OD-E): no migration, no binder-compute change, proportionate
  4-finder review.** *Recommend APPROVE.*

## Part 5 — Review dispositions + closure

*(written at fold/close per the house pattern)*
