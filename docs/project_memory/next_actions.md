# Next Actions

> **As of 2026-06-26.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** → P2-0/P2-1 planning + governance ratification → **P2-1 `dataset_snapshot` IMPLEMENTATION**
(`3629baa`, #67) → **P2-1 closeout memory** (`85ff5b2`, #68) → **P2-2 `fx_rate` implementation plan** (`6020b03`, #69; 8-lens, 6
in-scope folds) → **P2-2 `fx_rate` IMPLEMENTATION** (`c257e5c`, CI-green run #70; **8-lens review — 6 approve / 2
approve_with_changes / 0 block; 1 in-scope fold**): captured FX market data (ENT-024, **FR**) REALIZED — the `valuation` protocol
verbatim (capture/supersede/correct/`reconstruct_fx_rate_as_of`; NOT append-only); `irp_shared/marketdata/` package; migration
`0017_fx_rate` (symmetric RLS); explicit base/quote direction (`rate` = 1 base = rate quote); MID-only v1; `Numeric(28,12)`;
`rate_date` a separate immutable logical key (5-part current-head key); pure published-rate `convert` (direct/reciprocal/
triangulation-through-base USD-default; exact-date v1; fail-closed); hybrid-aware `resolve_currency` (own OR SYSTEM);
`marketdata.view`/`.ingest` minted; `MARKET.FX_*` (EVT-200) activated; VENDOR `data_source` ORIGIN lineage; new generic `RANGE`
DQ evaluator (additive); **NO exposure number, NO `calculation_run` wiring, NO `dataset_snapshot` change**. `migration_head`
`0016_dataset_snapshot` → `0017_fx_rate`. `audit/service.py` FROZEN. **P2-2 is COMPLETE and CI-green. No visible UI change.**

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2-2 closeout; no code) — commit on explicit approval.

**NEXT — P2-3 PLANNING ONLY (on explicit approval):** author the **P2-3 decision record + implementation plan** for
`calculation_run` wiring + basic exposure. **Plan ONLY** — NO exposure/calc-run code, NO risk, NO P3+. Implementation is a
**separate later approval**.

## Exact next prompt to run (when the user is ready for P2-3 planning)
> "Begin P2-3 planning only: the `calculation_run` wiring + basic exposure decision record + implementation plan. Plan EXACTLY
> the P2-3 subphase per the ratified P2 sequencing (`p2_implementation_plan.md`) + OD-P2-C/F + AD-014 + FW-RUN §5/TR-15: wire the
> shipped `calculation_run` (ENT-026, IA status-mutable, reuse `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`) + the **additive
> `environment_id`** column; produce `exposure_aggregate` (ENT-014, **IA, in `APPEND_ONLY_TABLES`**, derived, run-tracked) — the
> **first governed derived number** = Σ(signed quantity × captured mark_value) FX-converted, **consuming the P2-1
> `dataset_snapshot`** (P2-3 mints `COMPONENT_KIND_FX` + extends the binder to pin FX) **+ the P2-2 `fx_rate`** (convert);
> `code_version` is the reproducibility anchor (model_version N/A-with-rationale); a snapshot + a **complete** run-bind are
> REQUIRED before any official derived output (the full negative test: any-missing-item → raises + ZERO exposure rows + no orphan
> run). STRICT EXCLUSIONS: NO exposure/calc-run code (planning only); NO risk / VaR / ES / factor / sensitivities / scenario /
> pricing / valuation model; NO P3+; the exposure scope-fence is VOCABULARY/IMPORT (ast.Mult permitted). N-lens UltraCode
> planning workflow; produce the decision record + implementation plan markdown under `10_delivery_backlog/`. Do not commit until
> I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, review, implementation, and commit are distinct approvals.
- **Do not start exposure/`calculation_run` implementation** (or any later P2 subphase — P2-4..6) until the **P2-3 plan is
  approved** and its implementation separately approved. P1B-5 stays conditional/deferred; the P3+ boundaries stay closed unless
  explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** + **Snapshot symmetric-RLS + append-only** +
  **FX rate symmetric-RLS + hybrid-currency** all shipped) + `alembic check` drift + downgrade smoke, Documentation check, Secret
  scan. **P2-2 added the FX symmetric-RLS step** + migration `0017_fx_rate` (head `0016_dataset_snapshot` → `0017_fx_rate`).
  **HEAD `c257e5c` = run #70 (id 28258782538) = success** (all 5 jobs).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C/P2). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P2-3 PLANNING** is fine **on explicit approval** (author the exposure/calc-run decision record + plan
  only); but do NOT pull in **exposure/`calculation_run` implementation**, **`exposure_aggregate`**, **risk/VaR/ES/factor/
  sensitivities/scenario**, pricing/valuation models, reporting/dashboards, real SSO, ABAC enforcement, or any P2-4+/P3+ work —
  separate, later, planned slices.
- **No official derived number yet** — P2-1's snapshot + P2-2's FX compute no governed derived output; the first one (exposure) is
  **P2-3**, snapshot+run-gated (AD-014/FW-RUN/TR-15). Refuse any attempt to produce an `exposure_aggregate` or wire
  `calculation_run` before the P2-3 plan is approved.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
