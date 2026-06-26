# Next Actions

> **As of 2026-06-26.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** (P1C-1…P1C-6 delivered) → **P1C-6 memory** (`9584ba4`, #61) → **P1C closeout / P2 readiness
review** (`7070dff`, #62; 8-lens — reproducibility-first sequencing) → **P2-0 decision record + P2 implementation plan**
(`2d19992`, #63; 8-lens, 0 block — OD-P2-A…L; subphases **P2-1 snapshot → P2-2 FX → P2-3 calculation_run+exposure → P2-4 price
→ P2-5 curves → P2-6 benchmark**) → **P2-1 `dataset_snapshot` implementation plan** (`d7be981`, #64; 8-lens, 0 block — the
AD-014 reproducibility-primitive build plan) → **P2 `dataset_snapshot` governance ratification** (`63be23a`, CI-green run #65;
**7-lens, 7× approve, 0 block**): ENT-049/050 + SNAPSHOT.CREATE (EVT-190 reserved) + snapshot.* (reserved) + AD-004-R1 +
REQ-PPM-004→In-Progress, recorded into the source-of-truth — **RESERVED/PLANNED, NO code** (`audit/service.py` FROZEN;
`bootstrap.py` unchanged; migration head `0015_valuation`; no `snapshot` package). **P2 planning + governance ratification are
COMPLETE.**

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2 closeout; no code) — commit on explicit approval.

**NEXT — P2-1 IMPLEMENTATION ONLY (on explicit approval):** build the **`dataset_snapshot` reproducibility primitive** per
`10_delivery_backlog/p2_1_dataset_snapshot_implementation_plan.md` §24. **Build the snapshot primitive ONLY** — NO exposure
number, NO `calculation_run` wiring (readiness only; binding → P2-3), NO P2-2/FX, NO market data, NO P3+.

## Exact next prompt to run (when the user is ready for P2-1 implementation)
> "Begin P2-1 implementation only: the `dataset_snapshot` reproducible input snapshot. Implement EXACTLY the committed plan
> `10_delivery_backlog/p2_1_dataset_snapshot_implementation_plan.md` (§24 kickoff): the `irp_shared/snapshot/` package +
> migration `0016_dataset_snapshot` with `dataset_snapshot` (header) + `dataset_snapshot_component` (per-input physical-version
> pin), both **IA TRUE append-only** (in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger + ORM guard); the
> value-capturing `build_snapshot` binder via the set-returning enumerators (`reconstruct_subtree_holdings_as_of` +
> `attach_marks_as_of`), pinning the physical version + `captured_content` + an app-side SHA-256 canonical hash (excluding
> `valid_to`/`system_to`); the **cross-tenant binding-integrity invariant** (resolve only under the acting tenant's RLS;
> foreign proprietary id → fail closed, no snapshot); the **narrow internal lineage writer** (local Core Table; no import
> cycle); the **caller-side completeness DQ gate** (reuse `run_quality_check`/`DATA.VALIDATE`, Protocol untouched; gap → fail
> closed); activate `SNAPSHOT.CREATE` (EVT-190 block already reserved) caller-side (`audit/service.py` FROZEN) + mint
> `snapshot.view`/`.create` (data_steward maker; auditor_3l excluded; parity test); `api/snapshots.py` (create/read/verify);
> the §17 test matrix (mutation/reproducibility, EV drift, completeness fail-closed, PG FORCE-RLS + cross-tenant negative,
> append-only SQLite+PG, lineage, audit, scope fences; SYNTHETIC-tenant fixtures). STRICT EXCLUSIONS: NO exposure /
> `exposure_aggregate` / `calculation_run` wiring / `environment_id`; NO FX/price/curve/benchmark/market-data; NO risk/VaR/ES;
> NO P2-2+/P3+. 8-lens UltraCode review; `make check` + PG green. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, review, ratification, implementation, and commit are distinct approvals.
- **Do not start any later P2 subphase** (P2-2 FX, P2-3 exposure, P2-4..6) until P2-1 is built + its own plan approved. P1B-5
  stays conditional/deferred; the P3+ boundaries stay closed unless explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** all shipped) + downgrade smoke, Documentation
  check, Secret scan. The **entire P2 planning + ratification phase added NO migration/RLS step** (all planning/governance
  docs; head stays `0015_valuation`) — **P2-1 implementation lands the first new step**: a **Snapshot symmetric-RLS** CI step +
  migration `0016_dataset_snapshot` (the structural proof a table was persisted). **HEAD `63be23a` = run #65 (id 28245890604)
  = success** (docs-only ratification).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P2-1 implementation** is fine **on explicit approval** (build the snapshot primitive only); but do
  NOT pull in **P2-2/FX**, **P2-3/exposure or `calculation_run` wiring**, **market-data ingestion**, **risk/VaR/ES**,
  reporting/dashboards, real SSO, ABAC enforcement, or any P2-2+/P3+ work — separate, later, planned slices.
- **No official derived number in P2-1** — the snapshot computes nothing; the first governed derived output (exposure) is
  P2-3, snapshot+run-gated (AD-014). Refuse any attempt to produce an `exposure_aggregate` or wire `calculation_run` in P2-1.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
