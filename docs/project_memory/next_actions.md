# Next Actions

> **As of 2026-06-29.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **FULL P1C block** → P2-1 `dataset_snapshot` (`3629baa`, #67) → P2-2 `fx_rate` (`c257e5c`, #70) → P2-3 `calculation_run`
+ basic exposure (`da178fc`, #74; the first governed derived number, `exposure_aggregate`/ENT-014) → P2-4 `price_point` (`2b63b76`,
#77) → P2-5 `curve`+`curve_point` (`49ca3bd`, #80) → **P2-5 closeout memory** (`0c5c068`, #81) → **P2-6 plan** (`8d2782f`, #82;
8-lens, 2 HIGH + 1 MED + 21 LOW folds; the eleven OQ-P2-6 sign-offs + Option A) → **operating-rules** (`1e0dc08`, #83; provenance/dates
+ local-PG-container standing rules) → **P2-6 captured benchmark/index data IMPLEMENTATION** (`b6284a4`, CI-green run #84; **8-lens
review — 4 approve / 4 approve_with_changes / 0 block; every finding folded, incl. a real read-endpoint 500→404 fail-closed-status
bug + 5 added tests**): **`benchmark` (ENT-009, EV definition) + `benchmark_constituent` (FR/bitemporal membership)** REALIZED — the
`marketdata/benchmark.py` binder (`capture_benchmark`/`update_benchmark`/`resolve_benchmark`/`list_benchmarks` + `capture_membership`/
`supersede_membership`/`correct_membership`/`reconstruct_membership_as_of`) + the `Benchmark` + `BenchmarkConstituent` models;
migration `0021_benchmark` (**NEITHER table append-only** — EV in-place + FR close-out; no P0001 trigger). Identity
`(tenant, benchmark_code, benchmark_source)`; constituent 4-part current-head key `(tenant, benchmark_id, instrument_id,
effective_date)` + promoted key cols **NOT NULL**; `effective_date` a **separate immutable logical key**; `weight` **Numeric(20,12)**
(`RANGE [0,1]`); `instrument_id` NOT-NULL FK via `resolve_instrument`; membership captured/superseded/corrected **as a set** per
`(benchmark, effective_date)`. **RATIFIED AUDIT SPLIT (OQ-P2-6-11 Option A):** `REFERENCE.CREATE`/`REFERENCE.UPDATE` for the EV
definition; `MARKET.BENCHMARK_CONSTITUENT_CREATE`/`_UPDATE`/`_CORRECTION` (EVT-200; set-grained, one-event-per-set) for the FR
membership; the definition is NOT moved into `MARKET.*`. **`VENDOR_BENCHMARK` ORIGIN lineage** (benchmark-targeted; no `effective_date`
on the edge); reuse `marketdata.view`/`.ingest` (**NO new permission**); required-field + weight `RANGE [0,1]` DQ (Protocol
untouched); symmetric RLS on **both** tables; **snapshot readiness-only** (NO `COMPONENT_KIND_BENCHMARK`). **`benchmark_level` +
`benchmark_return` DEFERRED** (a net-new canonical ENT id NOT minted). **NO performance/attribution/active-return/active-risk/
tracking-error/factor/covariance/VaR/ES/reporting; NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/`fx_rate`/
`price_point`/`curve` change.** `migration_head` `0020_curves` → `0021_benchmark`. `audit/service.py` FROZEN. **REQ-PUB-003 benchmark
leg advanced** (stays In-Progress partial; rating + levels/returns + the full Coverage test deferred). **P2-6 is COMPLETE and
CI-green. No visible UI change.**

**THE FULL P2 CAPTURED MARKET-DATA / REPRODUCIBILITY FOUNDATION IS COMPLETE and CI-green** — P2-1 `dataset_snapshot` (`3629baa`) /
P2-2 `fx_rate` (`c257e5c`) / P2-3 `calculation_run`+`exposure_aggregate` (`da178fc`) / P2-4 `price_point` (`2b63b76`) / P2-5
`curve`+`curve_point` (`49ca3bd`) / P2-6 `benchmark`+`benchmark_constituent` (`b6284a4`). The reproducibility primitive + the captured
market-data inputs (FX, prices, curves, benchmarks) + the first governed derived number (exposure) are all realized. **NO risk
analytics yet** (P3).

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P2-6 closeout; no code) — commit on explicit approval.

**NEXT — P2 CLOSEOUT / P3 READINESS REVIEW (on explicit approval):** assess whether the P2 captured market-data foundation is
sufficient for **P3 (factor model / market-risk) PLANNING**. Focus: factor-model + market-risk readiness; data-history requirements
for factor/risk models; model registry / `model_version` integration; `calculation_run` + `dataset_snapshot` governance for risk
OUTPUTS (the first governed risk numbers — `risk_result`/`sensitivity`); risk methodology documentation requirements. **READINESS
REVIEW ONLY** — NO P3 code, NO risk calculation. P3 PLANNING is a **separate later approval**; P3 implementation a further separate
approval.

## Exact next prompt to run (when the user is ready for the P2 closeout / P3 readiness review)
> "Begin the P2 closeout / P3 readiness review (assessment only — no code). The full P2 captured market-data foundation is delivered
> (P2-1 dataset_snapshot, P2-2 fx_rate, P2-3 calculation_run+exposure, P2-4 price_point, P2-5 curve+curve_point, P2-6
> benchmark+benchmark_constituent; migration head 0021_benchmark; CI-green). Assess P3 (factor model / market-risk) readiness:
> (1) whether the captured market-data foundation (FX / prices / curves / benchmarks) + the reproducibility primitive
> (dataset_snapshot) + calculation_run are sufficient inputs for P3 risk PLANNING; (2) data-history requirements for factor/risk
> models (time-series depth/coverage); (3) model registry / model_version integration (risk OUTPUTS bind a model_version, unlike the
> deterministic P2-3 exposure rollup); (4) calculation_run + dataset_snapshot governance for the first governed RISK numbers
> (risk_result ENT-027 / sensitivity ENT-028 binding a run + snapshot + model_version + seed; reproducibility under correction);
> (5) risk methodology documentation + model-inventory requirements (REQ-MKT-001 acceptance). Produce a readiness-review note /
> P3-0 decision-record scaffold under 10_delivery_backlog/. STRICT EXCLUSIONS: NO P3 code; NO factor/covariance/VaR/ES/sensitivity/
> stress/scenario build; NO risk calculation; NO benchmark_level/benchmark_return; NO frontend; NO migration. Readiness review only;
> P3 PLANNING is a separate later approval. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — readiness-review, plan, review, implementation, and commit are distinct approvals.
- **Do not start P3 implementation** until **P3 PLANNING is approved** and its implementation separately approved. The P2 closeout /
  P3 readiness review is the next gate (assessment only). P1B-5 stays conditional/deferred; the P3+ boundaries stay closed unless
  explicitly reopened. `benchmark_level`/`benchmark_return` stay deferred (a net-new canonical ENT id).

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** + **Snapshot symmetric-RLS + append-only** +
  **FX rate symmetric-RLS + hybrid-currency** + **Exposure symmetric-RLS + append-only** + **Price-point symmetric-RLS + FR-bitemporal**
  + **Curve symmetric-RLS + FR/append-only** + **Benchmark symmetric-RLS + EV/FR (neither append-only)** all shipped) + `alembic check`
  drift + downgrade smoke, Documentation check, Secret scan. **P2-6 added the benchmark suite** (no new explicit CI step — the migration
  job auto-covers `0021_benchmark`) + migration `0021_benchmark` (head `0020_curves` → `0021_benchmark`; the `benchmark` EV definition
  + `benchmark_constituent` FR membership, NEITHER append-only). **HEAD `b6284a4` = run #84 = success** (all 5 jobs).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C/P2). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start the **P2 closeout / P3 readiness review** is fine **on explicit approval** (assessment / readiness note only);
  but do NOT pull in **P3 implementation**, **a factor model**, **risk/VaR/ES/sensitivities/scenario/stress**, **performance
  attribution / active return / active risk / tracking error**, `benchmark_level`/`benchmark_return`, reporting/dashboards, real SSO,
  ABAC enforcement, or any P3+ work — separate, later, planned slices.
- **The FULL P2 captured market-data foundation is REALIZED** — `benchmark` + `benchmark_constituent` (ENT-009) is captured benchmark/
  index data, shipped at P2-6 (`b6284a4`); after `fx_rate` (P2-2), `price_point` (P2-4), `curve`+`curve_point` (P2-5), and the first
  governed derived number `exposure_aggregate` (ENT-014, P2-3). Any FURTHER derived output (risk/factor/scenario/attribution/
  tracking-error) or computed market data stays its own planned slice / P3+; refuse to pull it forward.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint, or any new
  audit code / permission / role / migration without R-07.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
