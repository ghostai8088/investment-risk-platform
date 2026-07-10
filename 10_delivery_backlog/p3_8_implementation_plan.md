# P3-8 Implementation Plan — ex-post benchmark-relative performance (build contract)

> Executes ONLY after `p3_8_decision_record.md` OQ-P3-8-1…10 are ratified AND implementation is
> separately directed. Every step lands in ONE implementation commit (+ the ci.yml PG step in the
> SAME commit — the P3-7 standing lesson), delivered via the PR flow (branch protection binds
> everyone). Model/effort: Opus 4.8 / high. FULL ultrareview before the PR merges (OD-K).

## Step 0 — pre-checks
HEAD == origin/main; migration head `0031`; verify: `portfolio_return_result` row shape
(`DIETZ_PERIOD` rows + `TWR_LINKED`; 12dp values), `benchmark_return` columns + `RETURN_TYPE_SIMPLE`
/`BENCHMARK_RETURN_BASES` vocab, `benchmark.benchmark_currency`, `resolve_benchmark` tenant filter,
the scaffold signature, `PERF_RUN_TYPES` contents, both stale reservation comments (risk/events.py +
perf/events.py) queued for amendment.

## Step 1 — pure kernel `perf/benchmark_relative_kernel.py`
NO DB/IO. `compound_returns(returns) -> Decimal` (geometric `Π(1+r)−1`, Decimal-50, 12dp HALF_UP);
`active_series(portfolio, benchmark) -> list[Decimal]` (arithmetic `a_i`, equal lengths enforced);
`sample_stdev(values) -> Decimal` (n−1; raises on n<2; `Decimal.sqrt` at prec 50);
`information_ratio(mean, te)` (raises on te==0 — the caller omits the row). Own
`BenchmarkRelativeKernelError(ValueError)`. Hand goldens fixed in the plan: portfolio
`(0.03, −0.02, 0.01)` vs benchmark `(0.025, −0.015, 0.005)` → `a=(0.005, −0.005, 0.005)`,
`mean=0.001666666667`, `TE=0.005773502692` (n−1), `IR=mean/TE≈0.288675134595`;
`TD = 0.019494000000 − 0.014868312500` (each side compounded) — exact 12dp values verified at
implementation with an independent cross-check (TEST-only).

## Step 2 — registrar + methodology doc
`perf/bootstrap.py` gains `register_benchmark_relative_model` (code_version-only identity — the
PM-1/P3-7 shape): model `perf.benchmark_relative` v1, `methodology_ref =
05_analytics_methodologies/benchmark_relative_expost_v1.md`; assumptions (arithmetic active returns;
n−1 sample TE; geometric benchmark compounding over half-open sub-period windows; SIMPLE returns;
conditional TE/IR emission; unannualized) + limitations (captured-holdings propagation — the PM-1
OD-K carry; missing-day compounding hazard; gross-vs-basis caveat; single benchmark; UNVALIDATED).
Methodology doc with the Part-2 citations + the UCITS-conflation caveat.

## Step 3 — snapshot support
`PURPOSE_BENCHMARK_RELATIVE_INPUT` + `COMPONENT_KIND_PORTFOLIO_RETURN` +
`COMPONENT_KIND_BENCHMARK_RETURN` (models.py, both tuples); serializers:
`portfolio_return_content(row)` (full immutable column set — IA-row flavor) +
`benchmark_return_series_content(benchmark, rows)` (the FACTOR_RETURN header+rows flavor; rows
ordered by `return_date`; header identity + currency + basis in content); `service.py`:
`build_benchmark_relative_snapshot(session, *, acting_tenant, actor, portfolio_return_run_id,
benchmark_id, return_basis, as_of_valid_at/known_at)` pinning ALL `portfolio_return_result` rows of
the run (both metrics — the TWR_LINKED pin feeds the exact-linkage cross-check) + ONE benchmark
series component over `(first_boundary, last_boundary]` current-head rows (`type=SIMPLE`,
`basis=requested`); refusals BEFORE any write: no visible return rows, zero benchmark rows in-span,
duplicate anything, own error class `BenchmarkRelativeSnapshotError`; `_reresolve_content` branches
for both kinds + verify except-tuple; predicate ≤50 chars + ADDED to `_BINDING_PREDICATES`;
models-only function-local `perf.models` import (fence — the perf SERVICE never imported); exports.

## Step 4 — migration `0032_benchmark_relative` + ENT-054 model
`perf/models.py` gains `BenchmarkRelativeResult` + `METRIC_TYPE_ACTIVE_RETURN`/
`METRIC_TYPE_TRACKING_DIFFERENCE`/`METRIC_TYPE_TRACKING_ERROR`/`METRIC_TYPE_INFORMATION_RATIO`
(per OD-F: NOT-NULL FKs run/snapshot/model/portfolio/benchmark/portfolio_return_run;
`metric_value Numeric(20,12)`; evidence columns; grain UNIQUE `(run, metric_type, period_start)`);
ORM before_update/before_delete guard; `irp_shared/models.py` aggregator entry. Migration: table +
indexes + FKs + symmetric FORCE RLS + P0001 trigger (the 0031 template verbatim); head-bump sweep
`0031→0032` in every head assertion + the synthetic `0032→0033` guard.

## Step 5 — binder `perf/benchmark_relative_service.py`
`run_benchmark_relative(session, *, acting_tenant, actor, code_version, environment_id,
model_version_id, portfolio_return_run_id|snapshot_id, benchmark_id, return_basis)` on the scaffold,
`run_type='BENCHMARK_RELATIVE'`. Pre-create: prerequisites; `assert_model_version_of`
(`perf.benchmark_relative`); XOR input modes; pinned-content adjudication (parse both kinds;
TypeError-inclusive wrapper; DIETZ rows uniform portfolio/base/run; exact-linkage cross-check vs the
pinned TWR_LINKED; benchmark series uniform id/type/basis + currency==base gate; per-window ≥1
benchmark row; envelope checks); **tenant re-resolution of portfolio_return_run (run_type+COMPLETED)
+ benchmark + portfolio BEFORE FK stamping** (OD-H). Compute: per-period `r_b,i` compounding →
`a_i` rows → TD row → (n≥2) TE row → (TE>0) IR row; `abs(metric_value) ≥ 1E7` → FAILED gap;
aggregates at Decimal-50. Row/run resolvers + `list_benchmark_relatives` (tenant-predicated).
`PERF_RUN_TYPES` += the family. Exports.

## Step 6 — API + FE
`api/perf.py`: `POST /perf/models/benchmark-relative`, `POST /perf/benchmark-relative/runs`,
`GET /perf/benchmark-relative/runs/{id}`, `GET /perf/benchmark-relative/{id}` — gated the EXISTING
`perf.run`/`perf.view`; error map extended (own snapshot error → 409; input error → 422; the full
refusal set mapped — no raw 500 path); fixed-point serialization. FE: FAMILIES
`benchmark-relative` entry (perf permission family; own detail URL `/perf/benchmark-relative/runs/`)
+ RUN_TYPE_TO_FAMILY + row columns; RunsList source note.

## Step 7 — docs
Canonical registry ENT-054 mint + ENT-052 first-governed-consumer note + ENT-053 consumer note;
audit taxonomy PERF row addendum (`PERF.BENCHMARK_RELATIVE_CREATE` reserved); entitlement doc
perf.* REUSE row (the P3-3 precedent); backbone CAP-20.5 + REQ-PRF-002 + RTM row + REQ-PUB-003
consumer-proven note; BOTH stale reservation comments amended (OD-B); roadmap left for closeout.

## Step 8 — tests + CI (SAME commit)
`test_benchmark_relative.py` (SQLite): kernel goldens + independent cross-check; full-stack build +
consume paths; conditional emission (n=1 → no TE/IR; TE=0 → no IR); zero-benchmark-window,
currency-mismatch, basis-nonuniform, linkage-mismatch, foreign/unknown run+benchmark+portfolio,
duplicate-pin, magnitude-FAILED (REAL pin, no monkeypatch — the PM-1 lesson), TR-09 (benchmark
vendor CORRECTION after pin is invisible — the FIRST FR-series-supersede reproducibility proof in
perf), append-only, entitlement parity (recipient sets unchanged), zero-`PERF.*`-audit, migration
head, fence sync. `test_benchmark_relative_pg.py` (the _pg template: RLS visibility/no-context/
forged-tenant/trigger/hybrid-set/cross-tenant-snapshot/audit-chain) + **ci.yml step in the SAME
commit**. `test_perf_endpoint.py`-style endpoint suite. FE vitest additions. TD-1 realism (extremes
only in labeled boundary tests).

## Validation + review + PR
`make check` (incl. `ruff format --check` — the CI #136 lesson) + full-PG (fresh schema → `0032`
head; downgrade smoke `0032→0031→head` + full base round-trip) + fe-check + diff fence
(`audit/service.py` FROZEN; no BYPASSRLS/hybrid; no new permission). Then the FULL ultrareview →
fold → revalidate → push branch → **PR (CI green ON the PR)** → HOLD for the user's Tier-2 merge
approval. Closeout (roadmap DONE-mark + memory) after merge, via a second small PR.
