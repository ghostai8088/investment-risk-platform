# API-1b Implementation Plan — the flagship VaR / active-risk entity reads (Wave-10 slice 1)

Companion to `api_1b_decision_record.md` (RATIFIED 2026-07-21; OQ-API-1b-1 = A honest-NULL; the rest as
recommended). One commit per step; each mirrors a shipped exemplar. NO new governed number / model
code / permission / role / ENT / snapshot purpose; `audit/service.py` FROZEN; the closed 5-table
hybrid set untouched; TR-09 + the run-id reads unmoved; NO FE change. Demo counts UNCHANGED
(17/20/35/101).

## Step 1 — Migration `0046` + the model column
- `CalculationRun` (`calc/models.py`): add `scope_portfolio_id: Mapped[str | None] = mapped_column(GUID, nullable=True)` (place with the reproducibility bindings; docstring: "the ROOT portfolio a run was scoped to — a within-tenant scope label stamped at creation, NOT a security boundary; NULL = root not recorded / honestly unresolvable").
- `migrations/versions/0046_run_scope_portfolio.py` — `down_revision="0045_pacing_projection"`. Mirror `0018_exposure_aggregate.py` (the `environment_id` add): `op.add_column("calculation_run", sa.Column("scope_portfolio_id", GUID(), nullable=True))` + `op.create_index("ix_calculation_run_scope_portfolio_id", "calculation_run", ["scope_portfolio_id"])`; downgrade = `drop_index` then `drop_column`. NO RLS/grant/trigger change. Include the in-file `_IDENTIFIERS` assert list (the `0045` pattern) covering the migration id + index name (both ≤63).
- Verify: `alembic upgrade head` on a fresh DB; `alembic check` clean; `alembic downgrade -1` + re-upgrade smoke.

## Step 2 — Thread `scope_portfolio_id` through the run-creation choke point
- `create_run` (`calc/service.py:13`): add `scope_portfolio_id: str | None = None` param; set it on the `CalculationRun(...)`. Exactly the `environment_id` handling (stamp-at-creation, never mutated).
- `execute_governed_run` (`calc/scaffold.py:58`): add the same param; pass it to `create_run` (`:84`). Default `None` keeps every current caller byte-behaviour-identical until Step 3 opts in.
- Verify: `make check` (no behavioural change yet — the column is NULL everywhere).

## Step 3 — Stamp at each binder (the copy-forward chain)
Thread the value into each binder's `execute_governed_run` call:
- `run_exposure` (`exposure/service.py`): pass `scope_portfolio_id=portfolio_id` on the build path (the direct arg, the subtree ROOT); `None` on the snapshot-consume path (honest-NULL, OQ-API-1b-1).
- `run_factor_exposure` (`risk/factor_service.py`): pass `scope_portfolio_id=exposure_run.scope_portfolio_id` from the resolved upstream run (`resolve_exposure_run`, `:596`) on the build path; `None` on snapshot-consume.
- `run_var` / `run_var_historical` / `run_active_risk` (`var_service.py:800` / `var_hs_service.py:401` / `active_risk_service.py:594`): pass `scope_portfolio_id=pinned_exposure_run.scope_portfolio_id` — the pinned FACTOR_EXPOSURE run is re-resolved OUTSIDE the build/snapshot branch (verifier CLAIM 1), so this stamps in BOTH paths, propagating NULL faithfully when an ancestor was snapshot-fed.
- Verify: a focused unit test per binder asserting the stamp (build → root; snapshot-fed ancestor → NULL). `make check`.

## Step 4 — The Class-C reads (no read-helper change)
In `risk/service.py` (the family's read home), four functions via `calc/reads.list_governed_results` + `latest_run_rows`:
- `list_var_results(session, *, acting_tenant, portfolio_id, metric_type=None, as_of=None)` → `filters=[(CalculationRun.scope_portfolio_id, portfolio_id), (VarResult.metric_type, metric_type)]`, `run_type=RUN_TYPE_VAR`, `order_by=VarResult.metric_type`.
- `latest_var_for_portfolio(...)` → `latest_run_rows(list_var_results(...))`.
- `list_active_risk_results(session, *, acting_tenant, portfolio_id, benchmark_id=None, as_of=None)` → `filters=[(CalculationRun.scope_portfolio_id, portfolio_id), (ActiveRiskResult.benchmark_id, benchmark_id)]`, `run_type=RUN_TYPE_ACTIVE_RISK`.
- `latest_active_risk_for_portfolio(...)`.
- Verify: unit tests — foreign/NULL-scope id → `[]`; newer-run-wins; `metric_type`/`benchmark_id` filters bite.

## Step 5 — The endpoints + OpenAPI regen
- `api/risk.py`: `GET /vars?portfolio_id&metric_type?&as_of?` + `GET /vars/latest?…`; `GET /active-risk?portfolio_id&benchmark_id?&as_of?` + `GET /active-risk/latest?…`; all gated `risk.view`. **Declare `/vars/latest` and `/active-risk/latest` BEFORE the existing `/vars/{var_id}` (`:1641`) and `/active-risk/{active_risk_id}` (`:2047`)** (the covariance-latest shadowing lesson). Reuse the existing Row DTOs.
- Regenerate the committed contract: `python scripts/dump_openapi.py` + `npm run -w apps/frontend gen:types`; commit `openapi.json` + generated types (the SSO-1 lesson — a new route stales the drift-check otherwise).
- Verify: `make gen-api-check` clean; endpoint tests mirroring `test_active_risk_endpoint.py` (the portfolio→exposure→covariance→run `ctx` fixture) + the `/latest` assertion shape from `test_covariance_endpoint.py::test_api1_covariance_latest_read` (empty→`[]`, `/latest` not shadowed, newer-run-wins, stranger→403).

## Step 6 — Demo read assertions (NO new stage; counts UNCHANGED)
- Extend `apps/backend/tests/test_demo_stage9z_api1_reads_pg.py`: add `latest_var_for_portfolio(...)` and `latest_active_risk_for_portfolio(..., portfolio_id=demo_global)` assertions (`> 0`), mirroring the existing `latest_factor_exposure` assertion (`:159`). The existing demo runs stamp `scope_portfolio_id` on the fresh CI re-seed, so the reads render non-empty. **Do NOT add runs** — the `20/35/101` + `ACTIVE_RISK==1` count pins (`:114/:120/:126/:139`) must hold.

## Step 7 — CI rider 1: the `pip-audit` gate (OQ-W9C-4 / OQ-API-1b-4)
- `.github/workflows/ci.yml` `backend` job: add a hard step after the dep install (`:23`) — `pip-audit -r requirements-dev.txt` (mirrors the `npm audit --omit=dev --audit-level=moderate` posture, `:44`). Add `pip-audit` to `requirements-dev.txt`.
- Run it once locally; record the result in the closeout. If a genuine, dev-only/accepted advisory surfaces (the `@redocly` precedent), add an explicit **commented** `--ignore-vuln <ID>` allowlist with the disclosure — otherwise leave it strict (fail-on-any).

## Step 8 — CI rider 2: the closure-discipline docs-check (OQ-W9C-5 / OQ-API-1b-5)
- Extend `scripts/check_docs.py` (stdlib-only) with the **filename-keyed, row-anchored** rule (verifier CLAIM 6): (1) slice-id from `(.+)_decision_record\.md`, normalized (`_`↔`-`, upper); (2) build `{slice_id: done}` by scanning each `delivery_roadmap.md` line for its leading bold title token AND `✅ **DONE**` **in that same line**; (3) fail iff a record's `| **Status** |` cell contains `"DRAFT for ratification"` AND its filename-slice maps `done=True`. The `docs-check` job (`ci.yml:469`) already runs `check_docs.py` — no new job.
- Verify: the check PASSES on the current tree (API-1b's record is DRAFT-until-this-slice-merges but its roadmap row is not yet DONE; every shipped slice's record is CLOSED) — run `python scripts/check_docs.py` locally; add a unit test with a synthetic shipped-but-DRAFT record proving it FAILS, and the "slice-id in another row's prose" case proving it does NOT.

## Step 9 — Full gate + review
- `make check`; fresh-schema full-PG battery with `0046` in the CI order + the new endpoint/demo PG tests; `alembic check` + downgrade/upgrade smoke; `make gen-api-check` clean; `make fe-check` (unchanged, but the regen must not have moved the bundle). Run `pip-audit` + `check_docs.py` as CI will.
- 4-finder adversarial review (it touches a migration + the write path): lenses = write-path correctness (the copy-forward + NULL propagation), doctrine/security (frozen fence, RLS, no mint), read correctness + shadowing, and the two CI riders' mechanics.
- Closeout: **stamp THIS record CLOSED** (the API-1 miss OQ-W9C-5 exists to prevent — and the new check will enforce), roadmap Part 2.13 slice-1 row → DONE with PR#/CI#, `current_state` banner, memory.
