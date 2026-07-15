# VW-1 Implementation Plan — model-validation workflow (the 8-step build contract)

> Executes `vw_1_decision_record.md` (OD-VW-1-A…H) once OQ-VW-1-1…7 are ratified. Every step
> mirrors a shipped exemplar; no novel machinery. NO governed number, NO snapshot/run binding,
> NO binder-compute change; ONE new permission (R-07), ONE activated audit code, migration
> `0039`. `audit/service.py` FROZEN.

## Step 0 — Branch + pre-checks

`vw-1-impl` off `main` (post-planning-merge HEAD). Verify: `alembic` head `0038_var_residual_variance`;
`make check` green; the ENT-037/EVT-050/REQ-MDG grounding facts still hold at HEAD.

## Step 1 — ORM: `model/models.py` additions (exemplar: the existing registry trio)

- Vocab constants: `VALIDATION_TYPE_INITIAL/PERIODIC/TRIGGERED` + `VALIDATION_TYPES`;
  `VALIDATION_OUTCOME_APPROVED/APPROVED_WITH_CONDITIONS/REJECTED` + `VALIDATION_OUTCOMES`;
  `FINDING_SEVERITIES = HIGH/MEDIUM/LOW`; `EVIDENCE_TYPE_CALCULATION_RUN/DOCUMENT` — all
  controlled-vocab strings, no enum/CHECK (MG-01 genericity).
- `ModelValidation` (IA: `PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin`):
  `model_version_id GUID FK(model_version.id) NOT NULL` indexed; `validation_type String(20) NN`;
  `outcome String(30) NN`; `conditions String(2000) NULL`; `scope_summary String(2000) NN`;
  `report_ref String(500) NULL`; `next_review_due Date NULL`; `validated_by String(255) NN`.
  Composite index `(tenant_id, model_version_id, system_from)` for the latest-read.
- `ModelValidationFinding` (IA): `validation_id GUID FK NN` indexed; `finding_text String(2000) NN`;
  `severity String(20) NULL`; `authored_by String(255) NULL`.
- `ModelValidationEvidence` (IA): `validation_id GUID FK NN` indexed; `evidence_type String(30) NN`;
  `run_id GUID FK(calculation_run.run_id) NULL` (the PA-3 `source_calculation_run_id` precedent);
  `reference String(500) NULL`.
- Extend the existing `before_update`/`before_delete` `AppendOnlyViolation` listener set to the
  three new classes. Deprecation comment on `Model.validation_status` (OD-H: neither written nor
  read; ENT-037 is version-grain truth).

## Step 2 — Migration `0039_model_validation` (exemplar: `0005` + `0034`)

Three tables; FORCE RLS + `tenant_isolation_*` policies (USING + WITH CHECK on
`app.current_tenant`); `*_append_only` BEFORE UPDATE OR DELETE triggers via `irp_prevent_mutation()`;
**every identifier explicitly named and ≤63 chars, asserted at import** (the P3-8/BT-1 lesson
made structural at PA-0; house style in every migration 0032→0038). Measured: the convention
defaults for the `validation_id` child FKs land at 58/59 chars — legal but uncomfortably close
to the cap, and a `model_validation_id`-style child column name (the `model_version_id` sibling
convention) would hit 64 — which is WHY the child FK column is named `validation_id` and the
identifiers are explicit (e.g. `fk_mv_finding_validation`, `fk_mv_evidence_validation`,
`fk_mv_evidence_run`, `ix_model_validation_latest`). Clean `downgrade()`; local downgrade-base
smoke cycles it.

## Step 3 — Service: new `model/validation.py` (exemplar: `marketdata/proxy_mapping.py` binder guards)

- `ModelValidationActor` dataclass (the BR-16 actor rails); `ModelValidationValueError` (→422),
  `ModelValidationNotVisible` (→404-indistinguishable).
- `record_validation(session, *, model_version_id, acting_tenant, actor, validation_type,
  outcome, scope_summary, conditions=None, report_ref=None, next_review_due=None, findings=(),
  evidence=(), now=None)`:
  - guards BEFORE any write (fail-closed): vocab checks; the conditions blur guard
    (`conditions` required iff APPROVED_WITH_CONDITIONS, refused otherwise — PA-3 pattern);
    `next_review_due` required unless REJECTED (OD-D); **actor guard `actor_type == "user"`**
    (OD-F); model_version re-resolved tenant-visible (P3-5 FK guard) and required
    `status == "REGISTERED"`; every CALCULATION_RUN evidence `run_id` re-resolved
    tenant-visible + COMPLETED (`calc/runs.py` helper reuse); DOCUMENT evidence requires
    `reference`, CALCULATION_RUN requires `run_id` (blur guard both directions).
  - the `next_review_due` guard is SYMMETRIC (OD-A): required for APPROVED /
    APPROVED_WITH_CONDITIONS, refused for REJECTED.
  - ONE `now = utcnow()` (the injectable `now` also stamps `system_from`, so tests can pin
    recency deterministically); write record + findings + evidence rows; emit
    **`MODEL.VALIDATE`** (caller-side constant, one event per record, `after_value =
    {model_version_id, outcome, validation_type, finding_count, evidence_count,
    next_review_due}` — DC-2 metadata only). No lineage edge, no DQ rule (OD-G,
    registry-sibling convention).
- Readers: `latest_validation(session, model_version_id, acting_tenant)`;
  `list_validations(...)` — BOTH ordered `(system_from DESC, id DESC)`: the `id` leg is an
  arbitrary-but-DETERMINISTIC tiebreaker so same-timestamp records (possible under an injected
  clock) cannot make the gate's "latest" read ordering-dependent.

## Step 4 — The gate: `model/service.py::assert_model_version_of` (OD-B)

After the existing REGISTERED + model-code checks: read the latest `model_validation` outcome
for the version (one indexed point query); `REJECTED` → new `RejectedModelVersionError`
("model_version … latest validation outcome is REJECTED — use refused (CTRL-022)") → 422 at
every family's API mapping. NO other outcome changes behavior. This single seam covers all
**12 model-bound binder files / 14 call sites** (grep-verified at HEAD: `risk/service.py:220`,
`active_risk_service.py:519`, `covariance_service.py:297`, `var_service.py:476+484`,
`proxy_weight_service.py:364`, `scenario_service.py:270`, `factor_service.py:418+426`,
`var_hs_service.py:291`, **`var_backtest_service.py:435`** — NOTE: a `grep -v test` census
silently drops this file because its NAME contains "test"; the original census made exactly
that error — `perf/return_service.py:474`, `perf/benchmark_relative_service.py:397`,
`perf/desmoothing_service.py:254`); the model-less exposure binder is untouched. Semantics
note: a REJECTED **VaR** model blocks NEW VaR runs, but its already-COMPLETED runs remain
backtestable (the backtest gate checks the BACKTEST model's own validation status, not the
target VaR model's) — the re-validation evidence loop stays alive by construction.

## Step 5 — API: `apps/backend/src/irp_backend/api/models.py` (exemplar: the existing 3 endpoints)

- `POST /models/{model_id}/versions/{version_id}/validations` — gated NEW `model.validate`;
  request/response models; 422 vocab/blur/actor refusals; indistinguishable 404 cross-tenant.
- `GET /models/{model_id}/versions/{version_id}/validations` — gated `model.inventory.view`.
- `GET /models/{model_id}` detail: per-version `latest_validation {outcome, validated_at,
  next_review_due, overdue}` (overdue = `next_review_due < today`, computed at read).
- Error mappings: `RejectedModelVersionError` → 422 wherever family run endpoints map
  registry errors today.

## Step 6 — Entitlement mint (R-07; exemplar: the PM-1 `perf.*` mint)

`entitlement/bootstrap.py`: append `("model.validate", "Record a model validation (2L independent)")`;
grant `risk_manager_2l` + `platform_admin` ONLY, rationale comments citing SOD-03/MG-04 (the 1L
register / 2L validate split); parity test `test_model_validate_permission_grants_as_ratified`
pinning the exact holder set (and that `risk_analyst_1l`/`data_steward` do NOT hold it).

## Step 7 — Docs (OD-H registry obligations, same commit)

Canonical model ENT-037 → REALIZED-IN-VW-1; RTM/backbone REQ-MDG-003 → In-Progress; control
matrix CTRL-022 → Operational (evidence: ENT-037 rows); audit taxonomy MODEL row → "`.VALIDATE`
activated in VW-1" (the taxonomy row IS the activation record); `entitlement_sod_model.md` mint
record; `model_governance_independence_policy.md` cross-note (MG-04 role-level, MG-07 human-only
guard, OD-033 open); roadmap: staleness-item split disposition (decision record Part 3 item 7);
`phase_status.md`/`current_state.md`/`next_actions.md` refresh at closeout.

## Step 8 — Tests + `ci.yml` (SAME commit — the PA-4 recurring-lesson)

- Unit (SQLite): vocab/blur/actor-guard refusals (each one pinned — incl. the SYMMETRIC
  `next_review_due` guard both directions AND the non-REGISTERED-version refusal); latest-wins
  recency; REJECTED gate blocks a new run in ONE risk family + ONE perf family (and a
  subsequent APPROVED record un-blocks — recency semantics proven); APPROVED_WITH_CONDITIONS +
  UNVALIDATED keep running; evidence run re-resolution refusals (cross-tenant, non-COMPLETED);
  **`MODEL.VALIDATE` emission asserted** (exactly one event per record, `after_value` shape
  pinned; same test asserts ZERO lineage edges and ZERO DQ rows from the write — the OD-G
  conventions test-pinned, the taxonomy's "zero RISK.* events" precedent); API endpoint tests
  incl. overdue flag + the indistinguishable-404 cross-tenant read; append-only ORM guard on
  all three tables; migration head test updated to `0039`.
- PG (`test_model_validation_pg.py`, exemplar `test_model_registry_pg.py`): FORCE-RLS isolation
  under `irp_app`, cross-tenant invisibility, P0001 append-only triggers on all three tables,
  RLS-vs-FK guard (a cross-tenant model_version_id refused before stamping).
- **`ci.yml`: add the new PG suite step explicitly** (the lesson: a missing CI PG step has now
  been caught at three separate slices).
- Fixture realism per `test_data_realism.md` (plausible scope summaries/findings; no absurd
  dates outside labeled boundary tests).

## Then

Full battery (`make check` + local-PG schema-reset AND dirty-schema double-run + alembic
check/downgrade smoke) → 4-finder review (one adversarial on the OD-B gate) → fold → commit →
push → PR → CI green → merge (per the extended autonomy grant; if the PR classifier blocks
again, hand the compare link to the user) → decision record Parts 5.5/6 + closeout docs refresh.
