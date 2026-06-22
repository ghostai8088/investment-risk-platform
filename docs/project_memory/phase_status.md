# Phase Status

> **As of 2026-06-22.** Per-phase status, commits, CI, deliverables, placeholders. Commit hashes are the
> implementation commit (plan/fix commits noted). Re-verify HEAD + CI at session start (`current_state.md`).

| Phase | Status | Impl commit | CI | Key deliverables | Known placeholders carried forward |
|---|---|---|---|---|---|
| **P0.5** Hygiene & foundation | DONE | scaffold `4f93a33` (+ `1caae23`, audit fixes `a70caa6`/`e7fc61a`) | green | Monorepo; frozen audit framework + hash chain; RLS foundation (mig `0001`); entitlement seed; CI (lint/type/test + PG migration job + secret-scan + docs-check) | dev SSO header shim (not a boundary); WORM/anchoring deferred (HARD-01/02) |
| **P1A-0** Tenant context / RLS | DONE | `7cdc2f9` (plan `4bc68c6`, decisions `c975450`) | green | `set_config` tenant context; FORCE RLS USING+WITH CHECK; constrained `irp_app` test role; `irp_ops` BYPASSRLS role (mig `0003`) | header shim (DR-P1A0-3); `SECURITY.RLS_DENIED` eventing deferred (DR-P1A0-4) |
| **P1A-1** Data source + lineage | DONE | `96a1564` (plan `3ff3213`; CI fixes `7a700f0`/`72b889f`; hardening `97c2b1d`) | green | `data_source` (EV) + `lineage_edge` (IA, mig `0004`); `record_lineage`/`assert_has_lineage`; `DATA.SOURCE_REGISTER/UPDATE` | no lineage query/graph/field-level (REQ-LIN-002/P7); `run_id` logical (non-FK) |
| **P1A-2** Model registry | DONE | `c9be657` (plan `4be45f5`) | green | `model` (EV) + `model_version`/assumption/limitation (IA, mig `0005`); inventory + BR-3 gate; `MODEL.REGISTER/VERSION` | DR-P1-3 maker-checker hooks non-enforcing; tier/validation reserved (REQ-MDG-002/003/P7); `calculation_run.model_version_id` nullable until P2 |
| **P1A-3** Data quality | DONE | `cc472be` (plan `5da67be`) | green | `data_quality_rule` (EV) + `data_quality_result` (IA, mig `0006`); 2 generic evaluators; no-silent-failure; `run_quality_check`/`assert_passed_quality_checks`; `DATA.VALIDATE` + `DATA.DQ_RULE_DEFINE/UPDATE` | generic rules only (no domain DQ); reconciliation/override (REQ-DQR-002/003/P7); `ingestion_batch_id` placeholder (filled at P1A-4) |
| **P1A-4** Generic ingestion staging | DONE | `c781bb8` (plan `563b6cf`; PG fix `0282359`) | green (run 27965086115) | `ingestion_batch` (IA status-mutable) + `ingestion_staged_record` (IA immutable, mig `0007`); CSV anti-corruption; composes lineage+DQ+audit; durable-evidence-on-reject; `POST /ingest/upload` + batch reads; activates `DATA.INGEST` | `scan_status` AV no-op (OD-042); in-DB JSON staging (AD-004 deferred); **canonical mapping deferred to P1B/P1C**; CSV-only (XLSX later); adapters REQ-INT-002/003/P9 |
| **P1A closeout / P1B readiness** | DONE | `69afedf` | green (run 27967643576) | Closeout doc + 12-rail inventory + P1B readiness + OD-P1B-A…J framing (`10_delivery_backlog/p1a_closeout_p1b_readiness.md`) | — |
| **P1B-0** Decision record + plan | DONE (committed) | `dbed93e` (`10_delivery_backlog/p1b0_decision_record.md`, `p1b_implementation_plan.md`) | green (run 27969793585) | OD-P1B-A…J resolved (8-field each); P1B-1…5 sub-slice plan (13-field each); 7-lens reviewed (18 fixes applied, no blocks) | AD-013-R1, REQ-SMR-005, REFERENCE.* codes, entitlement additions = **proposed, not yet ratified/minted** |
| **P1B-1+** Reference-data implementation | NOT STARTED (BLOCKED) | — | — | — | blocked on P1B-0 ratifications + explicit direction |
| **P1C / P2+** Domain analytics, market/private, risk, reporting | NOT STARTED | — | — | — | must not be pulled forward |

## Milestones
- **P1A milestone: CLOSED** — all five rails (P1A-0…P1A-4) committed and CI-green.
- **P1B milestone: planning committed (P1B-0 = `dbed93e`, CI-green)** — implementation blocked pending ratifications + direction.

## CI job shape (the `migration` Postgres job, all green at HEAD)
`alembic upgrade head` → `alembic check` (drift) → audit concurrency → tenant-context RLS → lineage RLS →
model-registry RLS → data-quality RLS → **ingestion RLS + append-only** → downgrade base. Plus Backend
(ruff format/lint, mypy, pytest), Frontend, Documentation check, Secret scan.
