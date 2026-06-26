# Next Actions

> **As of 2026-06-26.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** → **P1C closeout / P2 readiness review** (`7070dff`, #62) → **P2-0 decision record + plan**
(`2d19992`, #63) → **P2-1 `dataset_snapshot` implementation plan** (`d7be981`, #64) → **P2 governance ratification** (`63be23a`,
#65; 7-lens, 7× approve) → **P2 ratification closeout memory** (`d45a31b`, #66) → **P2-1 `dataset_snapshot` IMPLEMENTATION**
(`3629baa`, CI-green run #67; **8-lens review, 6 in-scope folds**): the AD-014 reproducible input-snapshot primitive (ENT-049/050)
REALIZED — IA true-append-only (P0001 trigger + ORM guard, migration `0016_dataset_snapshot`); physical-version pin +
`captured_content` + SHA-256 `content_hash` + `manifest_hash`; `build_snapshot` binder; narrow internal lineage writer;
caller-side completeness DQ gate; `SNAPSHOT.CREATE` (EVT-190) activated; `snapshot.view`/`.create` minted (data_steward maker;
auditor_3l excluded); `POST /snapshots` + `GET /{id}` + `GET /{id}/verify`; symmetric RLS; cross-tenant binding-integrity
invariant; **NO exposure number, NO `calculation_run` wiring**. `migration_head` `0015_valuation` → `0016_dataset_snapshot`.
`audit/service.py` FROZEN. **P2-1 is COMPLETE and CI-green.**

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2-1 closeout; no code) — commit on explicit approval.

**NEXT — P2-2 PLANNING ONLY (on explicit approval):** author the **P2-2 FX-rate decision record + implementation plan**. **Plan
ONLY** — NO FX code, NO currency-conversion analytics unless explicitly approved, NO exposure number, NO `calculation_run`
wiring, NO price/curve/benchmark, NO P3+. FX implementation is a **separate later approval**.

## Exact next prompt to run (when the user is ready for P2-2 planning)
> "Begin P2-2 planning only: the FX-rate decision record + implementation plan. Plan EXACTLY the P2-2 FX subphase per the
> ratified P2 sequencing (`p2_implementation_plan.md`) + QS-07/08/09 + OD-030 + OD-P2-E: an `fx_rate` entity classified **FR**
> (bitemporal; a risk-driving market input, reconstructable as-of on both axes); **explicit currency-pair direction** (base/quote
> unambiguous, no implicit inversion); **MID** rate (no bid/ask spread at P2-2); a **configurable base currency** (USD default)
> + **triangulation-through-base IF ratified** (a deterministic lookup, not analytics); symmetric tenant-scoped RLS (never
> hybrid); the rate is bound to a future `calculation_run` (P2-3, not P2-2). STRICT EXCLUSIONS: NO FX code (planning only); NO
> currency-conversion analytics unless explicitly approved; NO exposure / `exposure_aggregate` / `calculation_run` wiring; NO
> price/curve/benchmark/market-data ingestion; NO risk/VaR/ES; NO P2-3+/P3+. N-lens UltraCode planning workflow; produce the
> decision record + implementation plan markdown under `10_delivery_backlog/`. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, review, implementation, and commit are distinct approvals.
- **Do not start FX implementation** (or any later P2 subphase — P2-3 exposure, P2-4..6) until the **P2-2 plan is approved** and,
  for FX, its implementation separately approved. P1B-5 stays conditional/deferred; the P3+ boundaries stay closed unless
  explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** + **Snapshot symmetric-RLS + append-only** all
  shipped) + `alembic check` drift + downgrade smoke, Documentation check, Secret scan. **P2-1 landed the first new step since
  Valuation**: the **Snapshot symmetric-RLS + append-only** CI step + migration `0016_dataset_snapshot` (head `0015_valuation` →
  `0016_dataset_snapshot`). **HEAD `3629baa` = run #67 (id 28251757848) = success** (all 5 jobs).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C/P2-1). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P2-2 PLANNING** is fine **on explicit approval** (author the FX decision record + plan only); but do
  NOT pull in **FX implementation**, **P2-3/exposure or `calculation_run` wiring**, **currency-conversion analytics**,
  **market-data ingestion**, **risk/VaR/ES**, reporting/dashboards, real SSO, ABAC enforcement, or any P2-3+/P3+ work — separate,
  later, planned slices.
- **No official derived number yet** — P2-1's snapshot computes nothing; the first governed derived output (exposure) is
  **P2-3**, snapshot+run-gated (AD-014). Refuse any attempt to produce an `exposure_aggregate` or wire `calculation_run` before
  P2-3, or to write currency-conversion analytics in P2-2 (FX is captured rates + a ratified lookup, not analytics).
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
