# Next Actions

> **As of 2026-06-29.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** → P2-1 `dataset_snapshot` (`3629baa`, #67) → P2-2 `fx_rate` (`c257e5c`, #70) → P2-3 `calculation_run`
+ basic exposure (`da178fc`, #74; the first governed derived number, `exposure_aggregate`/ENT-014) → **P2-4 captured price history**
(`2b63b76`, #77; `price_point`/ENT-020) → **P2-4 closeout memory** (`419db9d`, #78) → **P2-5 plan** (`326ad94`, #79; 8-lens, 8 folds;
the ten OQ-P2-5 sign-offs) → **P2-5 captured yield/spread curves IMPLEMENTATION** (`49ca3bd`, CI-green run #80; **8-lens review — 7
approve / 1 approve_with_changes / 0 block; 1 material + 3 low folds**): the unified **`curve` (FR header, ENT-021) + `curve_point`
(IA append-only version-pinned nodes)** REALIZED — the `fx_rate`/`price_point` FR protocol + the `dataset_snapshot`/`component`
header+detail split; the `marketdata/curve.py` binder (`capture_curve`/`supersede_curve`/`correct_curve`/`reconstruct_curve_as_of`/
`resolve_curve`/`list_curve_points`); migration `0020_curves` (curve FR symmetric RLS NOT append-only; `curve_point` IA append-only —
`APPEND_ONLY_TABLES` + the P0001 trigger + ORM guard). **ENT-023 `credit_spread` realized BY VALUE** (`curve_type=CREDIT_SPREAD` +
`reference_key` over the same tables; the genericity principle). **6-part current-head key** `(tenant_id, curve_type, currency_code,
reference_key, curve_date, curve_source)` + promoted key cols **NOT NULL**; `curve_point` UNIQUE `(curve_id, value_type, tenor_days)`;
`curve_date` a **separate immutable logical key**; `curve_type` **{TREASURY, GOVT, SWAP, OIS, CREDIT_SPREAD}**; `value_type`
**{ZERO_RATE, PAR_RATE, DISCOUNT_FACTOR, SPREAD}**; `point_value` **Numeric(20,12)** (canonical decimal); `tenor_label` + normalized
`tenor_days`; `reference_key` opaque (NOT an FK) + the `curve_type`↔`reference_key` invariant; `interpolation_method` an inert label;
**`MARKET.CURVE_CREATE`/`UPDATE`/`CORRECTION`** caller-side (ONE event per curve); **`VENDOR_CURVE` ORIGIN lineage** per physical
version; reuse `marketdata.view`/`.ingest` (**NO new permission**); **value-type-conditional `RANGE` DQ** (DF strictly-positive;
rates/spreads `[-1,1]`); symmetric RLS on **both** tables; **snapshot readiness-only** (NO `COMPONENT_KIND_CURVE`); the new Curve
symmetric-RLS CI step. **NO curve construction/interpolation/bootstrapping/duration/key-rate/pricing/risk; NO `calculation_run`/
`exposure_aggregate`/`dataset_snapshot`/`fx_rate`/`price_point` change.** `migration_head` `0019_price_point` → `0020_curves`.
`audit/service.py` FROZEN. **REQ-PUB-002 + REQ-PUB-003 → In-Progress (partial)** (curve-values-reproduce + spread-coverage legs;
vol-surface/interpolation-test/rating/benchmark deferred). **P2-5 is COMPLETE and CI-green. No visible UI change** (enables future
curve / market-data-readiness UI).

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2-5 closeout; no code) — commit on explicit approval.

**NEXT — P2-6 PLANNING ONLY (on explicit approval):** author the **P2-6 decision record + implementation plan** for **captured
benchmark/index data** (the next market-data entity after `curve`; benchmark metadata + constituents + levels/returns if scoped as
**captured** data; a header + detail design if appropriate; **FR / bitemporal where appropriate**, joining `irp_shared/marketdata`
additively). **Captured benchmark data ONLY** — NO performance attribution, NO factor model, NO risk calculation, NO returns
analytics. **Plan ONLY** — NO benchmark code, NO risk, NO P3+. Implementation is a **separate later approval**.

## Exact next prompt to run (when the user is ready for P2-6 planning)
> "Begin P2-6 planning only: the captured benchmark/index data decision record + implementation plan. Plan EXACTLY the P2-6 subphase
> per the ratified P2 sequencing (`p2_implementation_plan.md`): a **captured benchmark/index** market-data entity (the next after
> `curve`/ENT-021), realizing the benchmark portion of REQ-PUB-003 (`benchmark`); benchmark metadata + constituents + levels/returns
> IF scoped as **captured** data; **FR / bitemporal where appropriate** (the `fx_rate` / `price_point` / `curve` protocol precedent —
> capture / supersede / correct / reconstruct-as-of), a header + detail design if appropriate; joining `irp_shared/marketdata`
> additively; symmetric tenant-scoped RLS (per-tenant vendor-licensed; NEVER hybrid; closed 5-table hybrid set unchanged); a
> `MARKET.*` audit family member; VENDOR `data_source` ORIGIN lineage; a fail-closed DQ gate (reuse the `RANGE`/required-field
> evaluators); snapshot integration readiness-only unless a calc needs it. STRICT EXCLUSIONS: NO benchmark code (planning only); NO
> performance attribution; NO factor model; NO risk / VaR / ES / sensitivities / scenario; NO returns analytics; NO P3+. N-lens
> UltraCode planning workflow; produce the decision record + implementation plan markdown under `10_delivery_backlog/`. Do not commit
> until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, review, implementation, and commit are distinct approvals.
- **Do not start benchmark implementation** until the **P2-6 plan is approved** and its implementation separately approved. P1B-5
  stays conditional/deferred; the P3+ boundaries stay closed unless explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** + **Snapshot symmetric-RLS + append-only** +
  **FX rate symmetric-RLS + hybrid-currency** + **Exposure symmetric-RLS + append-only** + **Price-point symmetric-RLS + FR-bitemporal**
  + **Curve symmetric-RLS + FR/append-only** all shipped) + `alembic check` drift + downgrade smoke, Documentation check, Secret scan.
  **P2-5 added the Curve symmetric-RLS step** + migration `0020_curves` (head `0019_price_point` → `0020_curves`; the `curve` FR
  header + `curve_point` IA append-only nodes). **HEAD `49ca3bd` = run #80 = success** (all 5 jobs).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C/P2). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P2-6 PLANNING** is fine **on explicit approval** (author the captured benchmark/index decision record + plan
  only); but do NOT pull in **benchmark implementation**, **performance attribution**, **a factor model**, **risk/VaR/ES/factor/
  sensitivities/scenario**, **returns analytics**, reporting/dashboards, real SSO, ABAC enforcement, or any P3+ work — separate,
  later, planned slices.
- **The third market-data entity is REALIZED** — `curve` + `curve_point` (ENT-021/023) is captured FR/bitemporal vendor yield/spread
  curve data, shipped at P2-5 (`49ca3bd`); after `fx_rate` (P2-2), `price_point` (P2-4), and the first governed derived number
  `exposure_aggregate` (ENT-014, P2-3). Any FURTHER derived output (risk/factor/scenario/attribution) or computed market data (curve
  construction, interpolation, duration) stays its own planned slice / P3+; refuse to pull it forward.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
