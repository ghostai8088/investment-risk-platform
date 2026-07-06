# P3-2 Closeout / P3-3 Readiness — Resume Here

**Status as of CI #89 (green).** Authoritative provenance = commit hash + CI run, not dates.

## Where the project is
- **HEAD / GitHub `main` = `402cb12`**, CI #89 **green** (Python 3.12 runners).
- **Migration head = `0023_factor_return`.**
- Commit chain (all now pushed + CI-green):
  - `1a8b2a4` P3-1 analytic sensitivities **plan**
  - `e8e2e59` P3-1 **impl** (ENT-028 `sensitivity_result`, migration `0022_sensitivity`)
  - `5466a09` P3-2 factor-return input **plan**
  - `402cb12` P3-2 **impl** (ENT-025 `factor` EV + `factor_return` FR, migration `0023_factor_return`)
- **Phases done:** P3-0 (risk/factor analytics planning), P3-1 (analytic sensitivities), P3-2 (factor-return inputs).
- **Next slice: P3-3 — Factor-exposure engine.**

## P3-2 in one paragraph (just shipped)
Net-new `factor` EV definition (identity `(tenant, factor_code, factor_source)`, `REFERENCE.*` audited) + `factor_return` FR bitemporal captured series (grain `(tenant, factor_id, return_date, return_type)`, `MARKET.FACTOR_RETURN_*` audited). Captured **INPUT** only — no `calculation_run`/`model_version`/snapshot pin. Symmetric tenant RLS (never hybrid); NEITHER table append-only. VENDOR_FACTOR ORIGIN lineage. Reuses `marketdata.view`/`.ingest` (no `factor.*` perm). Binder-side finiteness guard + `>-1` DQ range. 8 endpoints; 39 factor tests. Validated green on Python 3.12 + 3.14 + full PG; CI #89 green.

## FIRST TASKS on resume (housekeeping — fold into the P3-3 planning commit)
1. **Refresh `docs/project_memory/{current_state,next_actions,phase_status}.md`** — they are STALE (frozen at "P2 done / P3 readiness next"). Update to: P3-0/P3-1/P3-2 DONE, head `0023_factor_return`, CI #89, next = P3-3.
2. **Drop the stale degraded-mode qualifiers** in the 5 governance docs (added while push/CI were blocked): the "…LOCAL-ONLY … commit + push/CI PENDING, NOT remote-CI-green" clauses → "committed `402cb12`, CI #89 green." Files: `04_data_model/canonical_data_model_standard.md` (ENT-025 row), `04_data_model/audit_event_taxonomy.md` (REFERENCE + MARKET rows), `04_data_model/temporal_reproducibility_standard.md` (P3-2 note), `06_security/entitlement_sod_model.md` (market-data row), `09_compliance_controls/control_matrix_skeleton.md` (P3-2 block).

## The ratified methodology (follow this exactly)
- **Planning-first, commit-only-on-explicit-approval.** Per-slice cadence, each step a SEPARATE explicit approval:
  plan → commit-plan → implement (single-threaded) → adversarial review → fold in-scope findings → `make check` + full PG validation → commit → **watch CI green** → closeout.
- **Adversarial review discipline:** review the slice through 8 lenses (bitemporal/correctness, tenant-RLS/security, audit, lineage, DQ/numeric, API/contract, scope-fence, migration/docs-consistency); each material finding independently verified before folding; fold only in-scope findings. (In Claude Code this was a multi-agent Workflow; in Copilot, do a disciplined single-pass version of the same.)
- **Flag misaligned prompts before acting** — check any instruction against this framework; call out drift first.

## Architectural invariants (do not violate)
- **`packages/shared-python/src/irp_shared/audit/service.py` is FROZEN** — never modify; emit via caller-side constants.
- **No BYPASSRLS; no SYSTEM_TENANT hybrid path** beyond the closed 5-table hybrid set (`currency, calendar, calendar_holiday, rating_scale, rating_grade`). Proprietary data = **symmetric** RLS (`USING == WITH CHECK == own-tenant`) + FORCE.
- **No secrets in source (BR-10).** No domain endpoint without entitlement (BR-11) + audit (BR-12) + lineage (BR-13) binding.
- **Two data patterns — pick correctly:**
  - **Captured INPUT** (fx_rate, price_point, curve, benchmark, factor): `REFERENCE.*` (EV def) / `MARKET.*` (FR series); VENDOR_* ORIGIN lineage; reuse `marketdata.view/.ingest`; DQ fail-closed co-transactional; **NO** run/model/snapshot. EV+FR captured tables are **NOT** append-only.
  - **Governed DERIVED number** (exposure_aggregate, sensitivity_result, and **P3-3 onward**): bind `dataset_snapshot` + `calculation_run` + (where a model applies) a **registered `model_version_id`** via `assert_registered_model_version` (CTRL-003); `code_version` + `environment_id` present; **IA TRUE append-only** (`irp_prevent_mutation` P0001 trigger + ORM guard); `RISK.*` (EVT-220) audit; `risk.view`/`risk.run` entitlement; a `05_analytics_methodologies/` methodology doc + `methodology_ref` mandatory; reproducible under input correction; failure model = pre-create-refusal (zero rows/audit) / post-create-FAILED (committed FAILED run, zero results).

## P3-3 scope (from `10_delivery_backlog/p3_implementation_plan.md`, Part 2)
**Factor-exposure engine** — factor exposures of positions (REQ-MKT-003; contributions sum to total within ε). Entity `factor_exposure` (ENT-028 family OR a net-new canonical id minted via the Part-3 process). **This is a governed derived risk number** → the full derived-number contract above applies (run + snapshot + **mandatory** `model_version` + methodology doc). It is the **P3-1 `sensitivity_result` exemplar, NOT the P3-2 captured-input pattern.** Consumes P3-2 factor returns + positions; likely needs a `COMPONENT_KIND_FACTOR` snapshot pin (mint additively). Sequencing (OD-P3-0-A/B): numbering is a recommendation, not a strict chain.

## Read these before planning P3-3 (authoritative, in-repo)
- `10_delivery_backlog/p3_implementation_plan.md` (the P3-1…P3-7 roadmap + cross-cutting contracts, Parts 3–4)
- `10_delivery_backlog/p3_0_decision_record.md` (OD-P3-0-A…N — the ratified P3 decisions)
- `10_delivery_backlog/p3_1_decision_record.md` + `p3_1_sensitivities_implementation_plan.md` (the derived-number exemplar to mirror)
- `10_delivery_backlog/p3_2_decision_record.md` + `p3_2_factor_return_inputs_implementation_plan.md` (P3-2 contract)
- `04_data_model/{canonical_data_model_standard,audit_event_taxonomy,temporal_reproducibility_standard}.md`, `06_security/entitlement_sod_model.md`, `09_compliance_controls/control_matrix_skeleton.md`, `05_analytics_methodologies/`
- `CLAUDE.md` (repo instructions)

## Environment (already stood up on this machine)
`make setup` (venv + editable installs) · `docker compose up -d db` (postgres:16) · `export DATABASE_URL=postgresql+psycopg://irp:change-me-locally@localhost:5432/irp` + `IRP_TEST_DATABASE_URL=$DATABASE_URL` · `alembic upgrade head` (→ `0023_factor_return`) · `make check` (green).
**Gotcha:** don't re-run the full pytest twice against the same DB without resetting the schema — `data_quality_pg`/`lineage_pg`/`synthetic_pg` self-seed a `GLOBAL_OK` system-tenant row and don't tear it down (spurious ~2 fail/4 error on a second run). Reset: `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp;` then `alembic upgrade head`.
