# Next Actions

> **As of 2026-06-27.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** → P2-0/P2-1 planning + ratification → **P2-1 `dataset_snapshot`** (`3629baa`, #67) → **P2-2
`fx_rate`** (`c257e5c`, #70) → **P2-2 closeout memory** (`adf4ac5`, #71) → **P2-3 plan** (`d10c766`, #72; 8-lens, 10 folds; the five
OQ-P2-3 sign-offs) → **P2-3 governance ratification** (`851f976`, #73; AD-018; RATIFIED-IN-PLANNING) → **P2-3 `calculation_run`
wiring + basic exposure IMPLEMENTATION** (`da178fc`, CI-green run #74; **8-lens review — 5 approve / 3 approve_with_changes / 0
block; 2 in-scope folds**): the platform's **first governed derived number** REALIZED — `exposure_aggregate` (ENT-014, **IA TRUE
append-only**); the `irp_shared/exposure/` package + `api/exposure.py`; migration `0018_exposure_aggregate` + the additive
`calculation_run.environment_id`; **run-bound + snapshot-gated**; **signed market value v1** (`signed qty × captured mark × effective
captured FX`; `exposure_amount` Numeric(28,6) HALF_UP); grain `(portfolio, instrument, base)`; **effective composite `fx_rate`** +
**`fx_legs`** (leg evidence, not a hard FK); `COMPONENT_KIND_FX` minted + `build_snapshot` FX-pinning + pure `compose_effective_rate`
(no live read; reproducible under FX correction); `CALC.RUN_CREATE`/`STATUS_CHANGE` reuse + the additive `update_run_status(outcome=)`
(**NO `EXPOSURE.AGGREGATE_CREATE`**); **pre-create-refusal / post-create-FAILED** failure model; lineage `snapshot --DEPENDS_ON-->
run --ORIGIN--> result` (`run_id` stamped); `exposure.view`/`.aggregate.run` wired (**auditor_3l in view**); symmetric RLS; the new
Exposure symmetric-RLS CI step. **NO risk (MARKET_VALUE only).** `migration_head` `0017_fx_rate` → `0018_exposure_aggregate`.
`audit/service.py` FROZEN. **P2-3 is COMPLETE and CI-green. No visible UI change** (enables future exposure-result + calc-run-evidence UI).

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2-3 closeout; no code) — commit on explicit approval.

**NEXT — P2-4 PLANNING ONLY (on explicit approval):** author the **P2-4 decision record + implementation plan** for **captured price
history** (the next market-data entity after `fx_rate`; **FR / bitemporal**, joining `irp_shared/marketdata` additively). **Captured
prices ONLY** — NO pricing model, NO valuation model, NO factor model, NO risk calculation, NO market-data feed-ingestion pipeline
unless explicitly planned. **Plan ONLY** — NO price-history code, NO risk, NO P3+. Implementation is a **separate later approval**.

## Exact next prompt to run (when the user is ready for P2-4 planning)
> "Begin P2-4 planning only: the captured price history decision record + implementation plan. Plan EXACTLY the P2-4 subphase per
> the ratified P2 sequencing (`p2_implementation_plan.md`): a **captured price-history** market-data entity (the next after
> `fx_rate`/ENT-024), **FR / bitemporal** (the P2-2 `fx_rate` / P1C-4 `valuation` protocol verbatim — capture / effective-dated
> supersede / as-known correction / reconstruct-as-of on both axes), joining the `irp_shared/marketdata` package additively;
> symmetric tenant-scoped RLS (per-tenant vendor-licensed; NEVER hybrid; closed 5-table hybrid set unchanged); a `MARKET.*` audit
> family member; VENDOR `data_source` ORIGIN lineage; a fail-closed DQ gate (reuse the `RANGE`/required-field evaluators). STRICT
> EXCLUSIONS: NO price-history code (planning only); NO pricing model / valuation model / factor model; NO risk / VaR / ES /
> sensitivities / scenario; NO market-data feed-ingestion pipeline unless explicitly planned; NO curves (P2-5) / benchmarks (P2-6) /
> P3+. N-lens UltraCode planning workflow; produce the decision record + implementation plan markdown under `10_delivery_backlog/`.
> Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, review, implementation, and commit are distinct approvals.
- **Do not start price-history implementation** (or any later P2 subphase — P2-5 curves / P2-6 benchmark) until the **P2-4 plan is
  approved** and its implementation separately approved. P1B-5 stays conditional/deferred; the P3+ boundaries stay closed unless
  explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** + **Snapshot symmetric-RLS + append-only** +
  **FX rate symmetric-RLS + hybrid-currency** + **Exposure symmetric-RLS + append-only** all shipped) + `alembic check` drift +
  downgrade smoke, Documentation check, Secret scan. **P2-3 added the Exposure symmetric-RLS step** + migration
  `0018_exposure_aggregate` (head `0017_fx_rate` → `0018_exposure_aggregate`; + the additive `calculation_run.environment_id`).
  **HEAD `da178fc` = run #74 = success** (all 5 jobs).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C/P2). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P2-4 PLANNING** is fine **on explicit approval** (author the captured-price-history decision record + plan
  only); but do NOT pull in **price-history implementation**, **a pricing/valuation/factor model**, **risk/VaR/ES/factor/
  sensitivities/scenario**, a market-data feed-ingestion pipeline (unless explicitly planned), reporting/dashboards, real SSO, ABAC
  enforcement, or any P2-5+/P3+ work — separate, later, planned slices.
- **The first governed derived number is REALIZED** — `exposure_aggregate` (ENT-014) is the snapshot+run-gated exposure (AD-014/
  FW-RUN/TR-15), shipped at P2-3 (`da178fc`). Any FURTHER derived output (risk/factor/scenario) stays P3+; refuse to pull it forward.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
