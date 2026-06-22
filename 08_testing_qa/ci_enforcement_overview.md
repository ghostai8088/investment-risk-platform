# CI Enforcement Overview

## Document Control

| Field | Value |
|---|---|
| Document ID | TESTQA-CIENFORCE-001 |
| Version | 0.1 (Draft) |
| Status | Accepted as Step 1D scaffold description |
| Owner | R-12 DevOps/SRE AI |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | build_rules.md, control_matrix_skeleton.md, automation_hooks.md, README.md, docs/developer_setup.md |
| Supported Build Rules | BR-1, BR-10, BR-12, BR-15, BR-16 |

## 1. Purpose

Describe how the Step 1D engineering scaffold enforces the ratified standards from the first commit. CI (`.github/workflows/ci.yml`)
runs four jobs; any failing step fails its job and blocks the merge (BR-1: no feature complete without tests; enforcement gate).

## 2. CI jobs → checks → build rules

| CI Job | Steps | Enforces | Maps to control |
|---|---|---|---|
| `backend` | ruff format --check, ruff check, mypy, pytest (foundation + P0.5 tests) | BR-1, BR-11, BR-12, BR-17, BR-18, BR-19 | CTRL-001, CTRL-005, CTRL-011, CTRL-016, CTRL-017, CTRL-026 |
| `frontend` | **npm ci** (reproducible from lockfile), eslint, tsc, vitest, vite build | BR-1, reproducible UI build | CTRL-001 |
| `migration` | alembic upgrade head → **alembic check (drift)** → **audit-write concurrency test (PG)** → **tenant-context RLS tests (PG)** → **lineage RLS tests (PG, P1A-1)** → **model registry RLS tests (PG, P1A-2)** → **data-quality RLS tests (PG, P1A-3)** → downgrade base | DB schema, RLS tenant isolation end-to-end (BR-17), append-only triggers + concurrency (BR-12/18), lineage/model + data-quality `data_quality_rule`/`data_quality_result` isolation + fail-closed + append-only under the constrained `irp_app` role, drift (OD-052) | CTRL-003, CTRL-005, CTRL-006, CTRL-011, CTRL-013, CTRL-014, CTRL-027, CTRL-029, CTRL-026, CTRL-033 |
| `secret-scan` | scripts/secret_scan.py (gitleaks later) | BR-10 (no secrets in source) | CTRL-010 |
| `docs-check` | scripts/check_docs.py | documentation present & doc-control headers | CTRL-002, CTRL-004 |

As of Step 1E the foundation-slice tests make the audit hash-chain, append-only immutability, deny-by-default entitlement,
tenant isolation, and temporal-class declaration into **executable controls** (see `03_architecture/foundation_slice.md`).
**P0.5** adds: reproducible frontend builds (`npm ci` from a committed lockfile), a schema-drift gate (`alembic check`),
per-tenant audit-write concurrency (advisory locks, proved gapless under N-thread contention in the migration job), an
audit-chain verification ops CLI (`python -m irp_worker.audit_verify`), and an entitlement bootstrap seed (baseline permission
catalog + role templates). **P1A-0** makes tenant isolation **end-to-end**: per-session `set_config('app.current_tenant', …, true)`
(AD-016) with a pool check-in `RESET`, exercised by PG-gated tests (context set/auto-clear, recycle safety, missing-context
fail-closed, tenant-mismatch denied, worker path, BYPASSRLS ops read), plus the BYPASSRLS ops role (AD-015) for cross-tenant
verification only. **P1A-1** builds the lineage skeleton (REQ-LIN-001): `data_source` (EV) + `lineage_edge` (IA) with the
`record_lineage`/`assert_has_lineage` BX-LIN contract and `GET /lineage/edges/{id}`, making **CTRL-006/CTRL-013** executable at
skeleton level — new PG-gated tests prove tenant isolation, no-context fail-closed (SQLSTATE 42501), cross-tenant write/reference
rejection, DB append-only, and ops-role-no-grant under the constrained `irp_app` role. **P1A-2** builds the model registry
skeleton (REQ-MDG-001): `model` (EV) + `model_version`/`model_assumption`/`model_limitation` (IA) with `register_model` +
`assert_registered_model_version` (the BR-3 inventory-before-use gate) and gated `POST /models` + read endpoints, making
**CTRL-003/CTRL-014** executable at skeleton level — reusing the existing `MODEL.REGISTER`/`MODEL.VERSION` codes and
`model.inventory.register`/`view` permissions (no new vocabulary). PG-gated tests add model-table isolation, no-context fail-closed,
cross-tenant parent-reference rejection, IA append-only (with an EV negative-control on the mutable `model` head), and
ops-role-no-grant. Governance fields (tier/validation_status/approved_use) are non-enforcing placeholders — an AC-11 test proves a
Tier-1 UNVALIDATED model registers/binds with no gate (validation/approval is P7). **P1A-3** builds the data-quality skeleton
(REQ-DQR-001): `data_quality_rule` (EV) + `data_quality_result` (IA) with a pluggable `DQRule.evaluate()` engine (2 generic rules:
`not_null`, `allowed_values`), `run_quality_check`, and the `assert_passed_quality_checks()` gate a future ingestion (P1A-4) calls,
making **CTRL-027/CTRL-029** executable at skeleton level — reusing `DATA.VALIDATE` and `dq.rule.manage`/`dq.result.view` (no new
permission, no role change). The headline **no-silent-failure** tests prove a failing rule persists a flagged result, `severity=ERROR`
raises, `WARNING` flags-only, and an evaluator error propagates and is audited `outcome='failure'` (QS-06/15/16, BR-14). PG-gated
tests add the two `data_quality_*` tables' isolation, no-context fail-closed, cross-tenant rule-reference rejection, IA append-only
(P0001 trigger, with an EV negative-control on the mutable rule head), and ops-role-no-grant.

## 3. Current placeholders (to be replaced as the platform is built)

- **secret-scan** is a lightweight regex script; replace with the full gitleaks engine (threat model THR-23).
- **docs-check** verifies README presence and Document Control headers; extend to code-change → required-doc-change checks
  (automation_hooks: documentation-consistency hook).
- **Identity** is a dev header shim, not SSO (AD-007); the entitlement gate is real but the principal source is a placeholder.
- **Lineage and model-inventory enforcement checks** are not active yet — they activate when those frameworks/domains are
  built (BR-3, BR-13). No governed surface bypasses audit/entitlement; the foundation simply has no domain surfaces yet.

## 4. Local equivalents

`make check` (backend) and `make fe-check` (frontend) run the same checks locally. See `docs/developer_setup.md`.

## 5. Open Decisions

| ID | Open Decision |
|---|---|
| OD-049 | Choose the production secret-scanning engine and wire it into the `secret-scan` job (gitleaks vs alternative). |
| OD-050 | Add branch protection / required-status-checks configuration once the GitHub repository exists. |

## 6. Dependencies

- build_rules.md (BR-1 … BR-19), control_matrix_skeleton.md (CTRL mapping), automation_hooks.md (hook intent).
