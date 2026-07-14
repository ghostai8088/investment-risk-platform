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

**Implemented** (working tree, pre-PR): `snapshot/service.py` (OD-A), `marketdata/proxy_mapping.py`
(OD-B), `perf/benchmark_relative_service.py` + `perf/return_service.py` + `risk/var_service.py` +
`risk/var_hs_service.py` (OD-C, 7 sites), `synthetic/builder.py` + `tests/test_lineage_pg.py` +
`tests/test_data_quality_pg.py` (OD-D). NO migration; `audit/service.py` untouched; `alembic
check`/`downgrade base`/`upgrade head` all clean. `make check` (1370+ new tests) and full local-PG
(schema-reset run green; **dirty-schema double-run green** — the OD-D regression proof) both pass.

**Review: 4 finders (proportionate form), one explicitly adversarial on OD-A per OQ-RD-3-5.**
Findings and dispositions:

1. **HIGH (finder 1 + finder 2, independently converged) — the OD-A except-tuple was scoped to
   the whole `_reresolve_content` dispatch (19 branches), not just the 4 that parse
   `captured_content`.** As first implemented, `KeyError/TypeError/ValueError/ArithmeticError`
   wrapped the ENTIRE re-resolution call, so a future live-data serialization bug in any of the
   other 15 branches (e.g. an `_norm_decimal` `InvalidOperation`/`ArithmeticError` on a
   corrupted-but-real row, a `TypeError` from a bad sort key) would be silently reported as
   "drift" instead of crashing loudly in dev/CI — precisely the failure mode OD-A was written to
   eliminate for malformed PINS, relocated onto live data instead. **FIXED**: introduced a scoped
   `MalformedPinError` + two helpers (`_parsed_pin`, `_pinned_row_ids`) that BENCHMARK_RETURN /
   FACTOR_RETURN / BENCHMARK / SCENARIO now route through; `verify_snapshot`'s except-tuple now
   catches only `MalformedPinError`, not the four raw builtin types. The other 15 branches raise
   loudly again on any non-`*NotVisible`/`*SnapshotError` failure, exactly as before this slice.
2. **HIGH (finder 3) — OD-B's message-normalization claim was untested.** `test_proxy_mapping.py`
   was unmodified even though Part 3 step 2 promised "the existing... tests keep passing with the
   normalized message asserted." **FIXED**: `test_foreign_instrument_and_factor_refused` now
   asserts `match=r"^instrument .* is not visible"` on the foreign-instrument refusal.
3. **HIGH (finder 3) — OD-D's DQ/lineage `GLOBAL_OK` idempotency had no CI-exercised double-call
   test** (unlike the synthetic-seed fix, which got `test_reseed_is_a_no_op`); the
   `resolve_or_insert` "already exists" branch was only provably exercised by a MANUAL local
   double-run, not a durable regression test. **FIXED**: both
   `test_system_tenant_source_writable_only_under_system_context` (lineage) and
   `test_system_tenant_rule_writable_only_under_system_context` (data_quality) now call
   `resolve_or_insert` a SECOND time in the same test against the just-committed row and assert
   the returned id is unchanged (no re-insert).
4. **MEDIUM (finder 3) — OD-A malformed-pin coverage was 2 of 4 composite branches, and only 2 of
   the 3 named malformed shapes** (truncated-JSON, missing-key; "non-object" untested — meaning
   `TypeError` in the except-tuple had zero test evidence). **FIXED**: added
   `test_verify_reports_drift_on_non_object_scenario_pin` (a JSON-array pin →
   `TypeError`) and `test_verify_reports_drift_on_malformed_benchmark_return_pin` (missing `rows`
   key on BENCHMARK_RETURN, the fourth composite branch). BENCHMARK (the constituent-membership
   branch, which also exercises the `benchmark_cache` hit/miss path) remains untested by a
   malformed-pin case specifically — recorded here as a residual, LOW-severity gap: it shares the
   identical `_parsed_pin(comp, "benchmark_id")` code path already proven by BENCHMARK_RETURN and
   FACTOR_RETURN, so the marginal risk is low, but it is not itself covered. Trigger: fold at the
   next slice that touches active-risk/benchmark snapshot tests, or on user request.
5. **MEDIUM (finder 3) — no durable skip-list existed for the OD-C parse_strict_decimal census.**
   The full per-site disposition (22 raw `Decimal(...)` sites census'd in Part 1c) is recorded
   here, closing the "SKIPPED AND LISTED" requirement (OD-RD-3-C):
   - **ADOPTED (7 sites, 4 files)** — `perf/benchmark_relative_service.py:253,264` (DIETZ
     `return_value`, `twr_linked`), `perf/return_service.py:278,349` (`exposure_amount`,
     `gross_amount`), `risk/var_service.py:284,406` (the second `exposure_amount` loop,
     `residual_stdev`), `risk/var_hs_service.py:213` (`return_value`). Each already sits inside a
     `(KeyError, TypeError, ValueError, ArithmeticError)` malformed-pin wrapper AND is followed
     immediately by an ordered/range check that already turns a silently-parsed NaN/Infinity into
     a refusal today — the swap changes only garbage-input MESSAGE TEXT (verified empirically: the
     full non-PG suite is green with zero other test diffs), never a legal input's parsed value.
   - **SKIPPED — message-pinned by an existing test** (adopting would have broken a passing
     assertion, i.e. would NOT have been zero-behavior-change): `risk/var_service.py:231`
     (`exposure_amount`, first loop — `test_p3c3_null_or_long_base_currency_and_malformed_pin_
     refused`), `risk/var_service.py:272` (`covariance_value` —
     `test_adjudication_magnitude_and_malformed_content_probes`), `risk/active_risk_service.py:
     245,357,399` (`covariance_value`/`exposure_amount`/`weight`, all three —
     `test_malformed_null_field_is_422_not_typeerror` loops over all three asserting the generic
     wrapper message), `risk/var_hs_service.py:174` (`exposure_amount` —
     `test_adjudication_gate_probes`).
   - **SKIPPED — registration-validated, not attacker/tamper-reachable text**:
     `perf/bootstrap.py:331,1064` (`alpha`, gated by the `_DESMOOTHING_ALPHA_PATTERN` regex before
     parse), `risk/bootstrap.py:761,763` (`confidence_key`/`floor`, only reached after a fixed-
     vocabulary `VAR_Z_SCORES` membership check).
   - **SKIPPED — no malformed-pin wrapper present at all (out of scope; a DIFFERENT hardening
     item, not this slice's)**: `exposure/service.py:140`, `risk/service.py:144`,
     `risk/covariance_service.py:198` (this file has no except clauses at all).
   - **SKIPPED — a genuine latent bug found during the census, NOT fixed here (scope fence: no
     silent behavior change from a hygiene slice)**: `perf/benchmark_relative_service.py:292`
     (bench-row `return_value`) — a NaN/Infinity value reaches the `abs(v) >=
     _MAX_RESULT_ABS` gate UNGUARDED by the function's own malformed-pin wrapper (it's outside the
     `except BenchmarkRelativeKernelError` block that wraps the rest of `_compute`), so it
     currently raises a raw `InvalidOperation` 500 — the exact BT-1 defect class. Adopting
     `parse_strict_decimal` here would SILENTLY FIX it, which is a real behavior change forbidden
     by OD-RD-3-C's scope fence. **Recorded as a new deferred finding, trigger-based**: fold at
     the next slice touching `perf/benchmark_relative_service.py`, or promote to its own
     carry-in if a hand-minted NaN pin is ever observed in the wild.
   - **SKIPPED — no family error class in scope to pass as `error=`**: `risk/kernel.py:67` (a pure
     kernel function, no DB/binder context).
   - GUC re-arm fixture (`persistent_tenant_context`) adoption: census of all 37 `*_pg.py` suites
     found exactly one test with >1 `session.commit()` per test function
     (`test_reference_instruments_pg.py::test_instrument_terms_not_append_only`), and it already
     correctly re-calls `set_tenant_context` after each commit — genuinely no file beyond the
     already-adopted `test_proxy_mapping_pg.py` qualifies. No adoption forced for its own sake.
6. **MEDIUM (finder 4) — OD-D's synthetic-seed fix diverges from Part 2's literal text.** OD-RD-3-D
   said idempotency should be "in the synthetic builder's row inserts" (implying per-row
   `resolve_or_insert`, mirroring the DQ/lineage fixtures). The actual implementation is a
   whole-seed short-circuit instead: `build_synthetic_dataset` checks whether its FIRST row (the
   `SYNTH-BOND-A` instrument, keyed by its deterministic uuid5 id) already exists and, if so,
   returns a fixed cached `_SUMMARY` without re-running any of the ~25 binder calls. **Ratified
   here as the correct implementation, not a defect**: per-row idempotency was rejected because
   several of the seed's binder calls are `supersede_position`/`correct_position`/
   `correct_valuation` — re-running THOSE idempotently would require reasoning through what a
   second supersede/correct means (mint a third version? no-op? which one wins?), a materially
   harder and riskier change than a hygiene slice should make. The whole-seed guard is simpler,
   provably safe under every current caller (both call `session.commit()` only once, after the
   function returns — verified by finder 1), and satisfies OD-RD-3-D's actual requirement ("seeding
   twice becomes a no-op") without touching the ~25 individual binder call sites. Proven by the new
   `test_reseed_is_a_no_op` (a genuine second-call-in-one-test regression test, not just a manual
   local double-run).
7. **No findings from finder 4 on scope-fence compliance** beyond item 6 above: zero migration,
   `audit/service.py` diff empty, `parse_strict_decimal` adoption sites are refusal-path-only (no
   legal input's computed VALUE changes), verify path stays no-emit (OD-023), `_resolve_instrument_id`'s
   guard-fold is a provably-equivalent predicate swap, `build_synthetic_dataset` has no
   production/non-test caller anywhere in the repo, all 11 changed files are test-or-shared-code,
   and no new audit/permission/role constant appears anywhere in the diff.

**All ratified OQs (RD-3-1..5) stand as approved** — the finding-driven fixes above tightened the
implementation to match the ratified intent more precisely; none required re-opening a Tier-3
decision. Deferred (trigger-based, not blocking this slice's close): the BENCHMARK malformed-pin
test gap (item 4) and the `benchmark_relative_service.py:292` latent NaN-detonation bug found
during the OD-C census (item 5) — both carried to the deferral register at the next wave-adjacent
review.

**RD-3 CLOSED** pending PR merge + CI green (tracked at implementation; commit hash recorded in
delivery-roadmap-state memory at close).
