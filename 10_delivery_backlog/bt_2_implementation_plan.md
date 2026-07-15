# BT-2 Implementation Plan — total-series backtest + σ_e estimate-age gate (the build contract, Steps 0–6)

> Executes `bt_2_decision_record.md` (OD-BT-2-A…G) once OQ-BT-2-1…6 are ratified. Mechanics are
> templated on BT-1 (the backtest lane) and PA-4 (the declared-parameter + additive-column
> precedents). ONE additive-column migration (`0040`); NO new permission/EVT; kernel UNTOUCHED;
> `audit/service.py` FROZEN.

## Step 0 — Branch + pre-checks

`bt-2-impl` off `main` (post-planning-merge). Verify: alembic head `0039_model_validation`;
`make check` green; the Grounding facts hold (METRIC_TYPES tuple, `VAR_HORIZON_DAYS = 1`,
`var_metric_type` String(30) unconstrained). Verify BT-1 deferral B's state: the registrars run on
`resolve_or_register_model`/`_version` savepoints since MD-H1 — record the discharge in Part 6.

## Step 1 — The vocabulary admit (OD-A)

`risk/events.py`: add `METRIC_TYPE_VAR_PARAMETRIC_TOTAL` to `METRIC_TYPES`; REWRITE the tuple
comment (its old text demands exactly this ratification — cite BT-2; keep the "do not extend
without a ratified slice" discipline for future methods, e.g. ES). Text-only hygiene: the binder
docstring two-method mentions (`var_backtest_service.py`), `models.py` column comments, the API
`var_metric_type` comment (`api/risk.py`).

## Step 2 — Migration `0040_var_estimate_age` + ORM (OD-D)

Additive nullable `var_result.estimate_age_days` (`sa.Integer`) — the 0038 `residual_variance`
precedent verbatim: additive column, NULL off the total family, identifiers ≤63 asserted, clean
`downgrade()` (drop column). ORM: `VarResult.estimate_age_days: Mapped[int | None]`. **Do NOT add
the key to `snapshot/serialize.py::var_result_content`** (the recorded false-drift landmine) — add
a test asserting the serializer's key set is unchanged.

## Step 3 — The total-model v2 + the age gate (OD-C)

- `risk/bootstrap.py`: `VAR_TOTAL_VERSION_LABEL` → `"v2"`; new
  `MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX = "max_estimate_age_days="` (pattern `[1-9][0-9]{0,4}`);
  `register_var_parametric_total_model` gains required `max_estimate_age_days: int` and declares
  it as the 5th assumption line; identity post-check extended (mismatch → 409
  `ModelVersionConflictError`, absent-on-resolved-row → 422). New
  `declared_max_estimate_age_days(session, version) -> int | None` with the OD-C parse spec:
  ABSENT → `None` (ungated — the v1 grandfather); present-but-MALFORMED or DUPLICATED →
  `WrongModelVersionError` fail-closed (do NOT use bare `sole_declared`, whose None-on-ambiguous
  would fail OPEN on a duplicate declaration — count the prefix matches explicitly). The
  generic-mint path needs no special handling: a generic `POST /models` version carries
  `status=None` and is refused at every bind by the existing status-REGISTERED backstop BEFORE
  any declared-parameter parse (verified at planning — there is no bypass to close).
- Methodology referent: mint `05_analytics_methodologies/var_parametric_total_v2.md` — the v1 body
  carried forward (immutability rule: v1 referent untouched) + the age-gate section (anchor
  definition, refusal semantics, the reproducibility argument) + the carried cross-family
  limitations. Registrar `methodology_ref` → the v2 doc.
- `risk/var_service.py`: in the total path, after `_parse_total_pins`: resolve each cited
  estimation run's pinned `input_snapshot_id` → tenant-scoped `dataset_snapshot` header read
  (`resolve_snapshot`; gone/cross-tenant ⇒ `VarInputError` refusal), `age_days =
  (parsed.window_end − header.as_of_valuation_date).days`; if
  `declared_max_estimate_age_days` is not None and `age_days > max` ⇒ `VarInputError`
  (pre-create 422, zero run) naming instrument + age + threshold. Echo `estimate_age_days =
  max(age_days across cited estimates)` onto the total `var_result` row (None when ungated v1? NO
  — compute + echo the age even when ungated, if the snapshot resolves; the echo is evidence, the
  gate is policy. If the pin predates the snapshot-id field or the header is gone on an ungated
  v1 path, echo None rather than refuse — gate-less v1 must not gain a new refusal).
- API (`api/risk.py`): `POST /risk/models/var-total` body gains required `max_estimate_age_days:
  int` (409/422 mappings unchanged — existing classes); the VaR row read gains nullable
  `estimate_age_days`.

## Step 4 — Doctrine + registry docs (OD-B/E/F)

- New registered-limitation lines in `VAR_BACKTEST_LIMITATIONS` (the two-sided pathology + the
  either-direction read-rule + the private-leg-share validity note) — new registrations carry
  them; existing immutable version rows recorded as not-appendable.
- `var_backtesting_v1.md`: **fork RESOLVED at planning (grounding-verified: the doc carries NO
  immutability self-declaration)** — add the dated additive "Scope amendment (BT-2)" section
  (three-method applicability + the OD-B doctrine + the BT-3 pointers).
- Label-collision cleanup (OD-F, FIVE sites): rename stale "BT-2"-as-Christoffersen references →
  "BT-3 candidate" in `risk/bootstrap.py` limitation #3, REQ-MKT-005 backbone+RTM text, the
  ENT-055 catalog row (also amend its "xor" clause to the three-method vocabulary),
  `var_backtesting_v1.md`'s Known-limitations line (inside the same amendment pass), and a
  cross-note in `bt_1_decision_record.md` (dated, additive — no rewriting of ratified history).
- Register accounting: REQ-MKT-001 total-series clause discharged; PA-4 Part-6 deferral 1
  discharged; the estimate-staleness register item ~~CLOSED~~ (an OVERCLAIM — corrected at the Wave-5 close; see the record's Part 6. VW-1 governance half + BT-2 mechanical
  half) — recorded in this record's Part 6 + the roadmap row at closeout.

## Step 5 — Tests (Step-8-of-BT-1 form; fixture realism per the standing rule)

- **The TOTAL golden lane** (mirror `test_build_path_historical_var_method`): the PA-4 chain
  (proxy weights + residual_stdev + declared appraisal_days) → total-VaR v2 runs at two window
  ends → backtest: `var_metric_type == "VAR_PARAMETRIC_TOTAL"` echo, verbatim `var_value` echo,
  exception/no-exception goldens (hand-derived, independent recompute), TR-09 consume-existing
  reproducibility, and the pure-dict adjudication battery gains: a TOTAL-only pin set PASSES; a
  mixed TOTAL+PARAMETRIC set REFUSES (the existing mixed-methods gate).
- **The age gate**: fresh-estimate passes; stale (age > declared max) refuses pre-create with
  zero run (`assert_no_running_orphan`); boundary age == max passes (strict >); **negative age
  (look-ahead: span end after window_end) passes with the negative age echoed — Part 3 item 5
  test-pinned**; gone/cross-tenant estimation-snapshot header refuses ON v2; **the v1
  gone-header branch echoes NULL and binds (no new refusal on the grandfather)**; v1-grandfather
  binds ungated with the age still ECHOED; echo = max across two instruments with different
  ages; **a zero-proxied-instrument total run echoes NULL (the empty-max edge)**;
  reproducibility — the SAME snapshot re-run yields byte-identical refusal/pass + echo (the
  AD-014 argument test-pinned).
- **Doctrine + registrar coverage**: a FRESH backtest registration carries the new doctrine
  limitation rows; the registrar's absent-on-resolved-row 422 post-check; off-domain Basel-zone
  omission asserted on a TOTAL run (Part 3 item 7); the API VaR-row read surfaces nullable
  `estimate_age_days`.
- **Serializer freeze**: `var_result_content` key set unchanged (the landmine test).
- **Registrar v2**: 409 on same-label different max-age; 422 off-pattern; v1 rows still resolve.
- **PG leg**: extend `test_var_total_pg.py` (age-gate refusal + echo under RLS; the grant lists
  already cover `dataset_snapshot` — verify per the VW-1 grant-leakage lesson) — confirm whether
  a new CI step is needed (existing suite files only ⇒ no `ci.yml` change; if a NEW file, wire it
  the SAME commit).
- Migration-head bumps (`0039` → `0040`) across the head-assertion tests + the synthetic guard
  (`0040` → `0041`).

## Step 6 — Docs + closeout obligations

Roadmap BT-2 row → DONE + amendment-log entry AT THE IMPL/CLOSEOUT PR (the recurring
missing-stamp lesson); this record's Status → CLOSED with merge hash; `current_state.md` banner
refresh; memory updates.

## Then

Full battery (`make check` + local-PG schema-reset AND dirty double-run + alembic check +
downgrade smoke 0040↔0039↔base) → 4-finder review (adversarial on the gate's reproducibility +
numeric on new goldens) → fold → push → hand the PR to the user → CI green → merge → closeout.
