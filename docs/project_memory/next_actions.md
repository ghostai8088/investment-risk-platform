# Next Actions

> **As of 2026-06-28.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** → P2-0/P2-1 → **P2-1 `dataset_snapshot`** (`3629baa`, #67) → **P2-2 `fx_rate`** (`c257e5c`, #70) →
**P2-3 plan** (`d10c766`, #72) → **P2-3 governance ratification** (`851f976`, #73; AD-018) → **P2-3 `calculation_run` wiring + basic
exposure** (`da178fc`, #74; the first governed derived number, `exposure_aggregate`/ENT-014) → **P2-3 closeout memory** (`0b12d85`,
#75) → **P2-4 plan** (`b73e65f`, #76; 8-lens, 4 folds; the six OQ-P2-4 sign-offs) → **P2-4 captured price history IMPLEMENTATION**
(`2b63b76`, CI-green run #77; **8-lens review — 7 approve / 1 approve_with_changes / 0 block; 1 in-scope fold**): `price_point`
(ENT-020, **FR / bitemporal**) REALIZED — the platform's **second market-data entity** (the `fx_rate` protocol verbatim); the
`marketdata/price.py` binder (`capture_price` / `supersede_price` / `correct_price` / `reconstruct_price_as_of` / `resolve_price`) +
the `PricePoint` model; migration `0019_price_point` (symmetric RLS, **NOT append-only**); the **6-part current-head key**
`(tenant_id, instrument_id, price_date, price_type, currency_code, price_source)` with **`price_source` IN the key** (multi-vendor
coexistence) + the promoted key columns DB-level **NOT NULL**; `price_date` a **separate immutable logical key**; `price`
**Numeric(20,6)**; `price_type` **{CLOSE, MID, NAV}**; **RAW vendor prices only** (no adjustment engine); captured `currency_code`,
**NO conversion**; `instrument_id` NOT-NULL FK via `resolve_instrument`; **`MARKET.PRICE_CREATE`/`UPDATE`/`CORRECTION`** caller-side;
**`VENDOR_PRICE` ORIGIN lineage** per physical version; reuse `marketdata.view`/`.ingest` (**NO new permission**); required-field +
strictly-positive `RANGE` DQ gate; symmetric RLS; **snapshot readiness-only** (NO `COMPONENT_KIND_PRICE`); the new Price-point
symmetric-RLS CI step. **NO pricing model, NO conversion, NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/FX change.**
`migration_head` `0018_exposure_aggregate` → `0019_price_point`. `audit/service.py` FROZEN. **REQ-PUB-001 → In-Progress (partial)**
(the as-of leg; staleness/QS-16 deferred). **P2-4 is COMPLETE and CI-green. No visible UI change** (enables future price-history /
market-data-readiness UI).

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2-4 closeout; no code) — commit on explicit approval.

**NEXT — P2-5 PLANNING ONLY (on explicit approval):** author the **P2-5 decision record + implementation plan** for **captured
yield/spread curves** (the next market-data entity after `price_point`; **FR / bitemporal**, joining `irp_shared/marketdata`
additively; a **curve header + curve point** design if appropriate). **Captured curves ONLY** — NO duration calculation, NO pricing
model, NO factor model, NO risk calculation, NO interpolation/bootstrapping engine unless explicitly planned. **Plan ONLY** — NO
curve code, NO risk, NO P3+. Implementation is a **separate later approval**.

## Exact next prompt to run (when the user is ready for P2-5 planning)
> "Begin P2-5 planning only: the captured yield/spread curves decision record + implementation plan. Plan EXACTLY the P2-5 subphase
> per the ratified P2 sequencing (`p2_implementation_plan.md`): a **captured curve** market-data entity (the next after
> `price_point`/ENT-020), **FR / bitemporal** (the `fx_rate` / `price_point` / `valuation` protocol verbatim — capture /
> effective-dated supersede / as-known correction / reconstruct-as-of on both axes), joining the `irp_shared/marketdata` package
> additively; a **curve header + curve point** design if appropriate; symmetric tenant-scoped RLS (per-tenant vendor-licensed; NEVER
> hybrid; closed 5-table hybrid set unchanged); a `MARKET.*` audit family member; VENDOR `data_source` ORIGIN lineage; a fail-closed
> DQ gate (reuse the `RANGE`/required-field evaluators); snapshot integration readiness-only unless a calc needs it. STRICT
> EXCLUSIONS: NO curve code (planning only); NO duration calculation; NO pricing model / valuation model / factor model; NO risk /
> VaR / ES / sensitivities / scenario; NO interpolation/bootstrapping engine unless explicitly planned; NO benchmarks (P2-6) / P3+.
> N-lens UltraCode planning workflow; produce the decision record + implementation plan markdown under `10_delivery_backlog/`. Do
> not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, review, implementation, and commit are distinct approvals.
- **Do not start curve implementation** (or any later P2 subphase — P2-6 benchmark) until the **P2-5 plan is approved** and its
  implementation separately approved. P1B-5 stays conditional/deferred; the P3+ boundaries stay closed unless explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** + **Snapshot symmetric-RLS + append-only** +
  **FX rate symmetric-RLS + hybrid-currency** + **Exposure symmetric-RLS + append-only** + **Price-point symmetric-RLS + FR-bitemporal**
  all shipped) + `alembic check` drift + downgrade smoke, Documentation check, Secret scan. **P2-4 added the Price-point symmetric-RLS
  step** + migration `0019_price_point` (head `0018_exposure_aggregate` → `0019_price_point`; the `price_point` FR table).
  **HEAD `2b63b76` = run #77 = success** (all 5 jobs).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C/P2). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P2-5 PLANNING** is fine **on explicit approval** (author the captured yield/spread-curves decision record +
  plan only); but do NOT pull in **curve implementation**, **a duration/pricing/valuation/factor model**, **risk/VaR/ES/factor/
  sensitivities/scenario**, an interpolation/bootstrapping engine (unless explicitly planned), benchmarks (P2-6), reporting/dashboards,
  real SSO, ABAC enforcement, or any P3+ work — separate, later, planned slices.
- **The second market-data entity is REALIZED** — `price_point` (ENT-020) is captured FR/bitemporal vendor price history, shipped at
  P2-4 (`2b63b76`); the first governed derived number `exposure_aggregate` (ENT-014) shipped at P2-3 (`da178fc`). Any FURTHER derived
  output (risk/factor/scenario) or computed market data (curve construction, duration) stays its own planned slice / P3+; refuse to
  pull it forward.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
