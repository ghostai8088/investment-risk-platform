# Foundation Slice (Step 1E)

## Document Control

| Field | Value |
|---|---|
| Document ID | ARCH-FOUNDSLICE-001 |
| Version | 0.1 (Implemented) |
| Status | Accepted — first executable foundation slice |
| Owner | R-03 Backend Engineering AI (with R-05 Data Architect AI, R-07 Security Architect AI) |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | architecture_baseline.md, foundational_adrs.md, temporal_reproducibility_standard.md, audit_event_taxonomy.md, entitlement_sod_model.md, control_matrix_skeleton.md, ci_enforcement_overview.md |
| Supported Build Rules | BR-5, BR-6, BR-11, BR-12, BR-17, BR-18, BR-19 |

## 1. Purpose

The foundation slice turns the cross-cutting build rules into executable, tested code. It implements four thin but real
frameworks that every future domain module must bind to. It contains **no domain functionality** (no risk analytics, security
master, dashboards, or ingestion).

## 2. What was built

All framework code lives in `packages/shared-python/src/irp_shared/`; FastAPI wiring is in `apps/backend/src/irp_backend/deps.py`.

### 2.1 Persistence + temporal base (`irp_shared/db/`)
- `Base` (declarative, stable naming convention), `make_engine` / `make_session_factory`.
- Mixins: `PrimaryKeyMixin`, `TimestampMixin`, `TenantMixin` (BR-17), and the temporal-class mixins
  `FullReproducibleMixin` (FR), `ImmutableAppendOnlyMixin` (IA), `EffectiveDatedMixin` (EV) per AD-005 / BR-19.
- Portable `GUID` type (native UUID on PostgreSQL, `CHAR(36)` on SQLite).
- Every model declares `__temporal_class__`; a test enforces this (BR-19).

### 2.2 Audit framework (`irp_shared/audit/`)
- `audit_event` and `audit_checkpoint` tables (IA / append-only).
- `record_event` is the only sanctioned writer: it append-only inserts, assigns a per-tenant `sequence_no`, and computes the
  hash chain `previous_event_hash → event_payload_hash → event_hash` (SHA-256, BR-18).
- `verify_chain` recomputes hashes to detect tampering; `create_checkpoint` snapshots the latest sequence/hash (CP-01).
- Append-only is enforced two ways: ORM `before_update`/`before_delete` guards (any engine) and a PostgreSQL trigger (migration).

### 2.3 Entitlement framework (`irp_shared/entitlement/`)
- Tables: `app_user`, `role`, `permission`, `role_permission`, `user_role` (effective-dated grants).
- `has_permission` / `require_permission`: tenant-scoped, **deny-by-default** (BR-11, BR-17). Tenant mismatch is denied first.
- `grant_role` emits an `ENTITLEMENT.GRANT` audit event (BR-7).
- FastAPI `require_permission(code)` dependency gate in the backend (deny → 403, missing principal → 401).

### 2.4 Calculation-run framework (`irp_shared/calc/`)
- `calculation_run` table binding the reproducibility inputs (input snapshot, model version, assumption set, RNG seed, code
  version — placeholders until those domains exist), with `created_at` / `completed_at` and a `RunStatus` lifecycle.
- `create_run` and `update_run_status` emit `CALC.RUN_CREATE` / `CALC.RUN_STATUS_CHANGE` audit events (BR-6, BR-12).

## 3. Enforcement model (defense in depth)

| Concern | App layer | Database layer (PostgreSQL migration) |
|---|---|---|
| Tenant isolation (BR-17) | entitlement `tenant_id` checks | row-level security policies on every tenant-scoped table |
| Audit immutability (BR-12) | ORM append-only guards | `BEFORE UPDATE/DELETE` trigger raising an exception |
| Audit integrity (BR-18) | `verify_chain` recomputation | unique `(chain_id, sequence_no)` constraint |

## 4. Test/runtime database strategy (AD-011)

Unit tests run on in-memory SQLite for speed and zero external dependencies; runtime and the migration use PostgreSQL (AD-004).
PostgreSQL-specific enforcement (RLS, append-only trigger) is validated by the CI `migration` job, which applies and reverts
the foundation migration against a real Postgres service.

## 5. Known placeholders

- Identity is a dev header shim (`X-User-Id` / `X-Tenant-Id`); real OIDC/SSO is AD-007 (later step).
- Reproducibility foreign keys on `calculation_run` are nullable placeholders until those domains exist.
- Checkpoint `signature` is unused (signing/WORM is later-hardening, HARD-01/02).
- Per-chain concurrency control (advisory lock / serializable) for high-volume audit writes is a hardening item.
- Drift check between ORM models and the hand-authored migration is deferred to Step 1F (Alembic autogenerate `--check`).

## 6. Open Decisions

| ID | Open Decision |
|---|---|
| OD-051 | Confirm audit-write concurrency control for per-tenant chains at volume. |
| OD-052 | Add Alembic autogenerate drift check (models vs migration) in CI. |

## 7. Dependencies

- foundational_adrs.md (AD-004, AD-005, AD-006, AD-007, AD-008, AD-011, AD-012).
- audit_event_taxonomy.md (§4A hash chain), entitlement_sod_model.md (deny-by-default), temporal_reproducibility_standard.md (§2A classes).
