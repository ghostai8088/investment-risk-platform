# P2-7 Implementation Plan — Benchmark price/level capture (build contract)

> Executes `p2_7_decision_record.md` (OD-P2-7-A…H) once OQ-P2-7-1…8 are ratified. The build template
> is P3-2's `factor_return` end-to-end (model → migration → binder → endpoints → tests), adapted to
> the existing ENT-009 `benchmark` header. **Planning implements nothing; implementation starts on
> separate explicit approval.**

## Step 0 — Pre-checks (no writes)
1. Verify migration head is `0028_var_historical` and `alembic check` is a no-op at start.
2. Verify ENT-052 is still the next free canonical id (grep the registry); verify `VENDOR_BENCHMARK`
   source constants + `resolve_benchmark` exist as recon found them.

## Step 1 — Models (`marketdata/models.py`) + vocab constants
3. `BenchmarkLevel(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base)` —
   mirror `FactorReturn` verbatim: `benchmark_id` GUID NOT-NULL FK → `benchmark.id` (indexed);
   `level_date: Date` NOT-NULL indexed (immutable logical key); `level_type: String(30)` NOT-NULL;
   `level_value: PreciseDecimal(20, 6)` NOT-NULL; `restatement_reason: String(255)` nullable;
   `supersedes_id` self-FK nullable; `record_version: Integer` default 1. Current-head partial-unique
   `uq_benchmark_level_current (tenant_id, benchmark_id, level_date, level_type) WHERE valid_to IS
   NULL AND system_to IS NULL` (postgresql_where + sqlite_where — the `uq_factor_return_current`
   shape). `__temporal_class__ = FULL_REPRODUCIBLE`. NOT append-only (no trigger, no ORM guard —
   content immutability is binder-enforced + tested, the factor/benchmark precedent).
4. `BenchmarkReturn(...)` — same mixins; `benchmark_id` FK; `return_date` (immutable logical key);
   `return_type: String(20)` default `SIMPLE`; `return_basis: String(20)` NOT-NULL;
   `return_value: PreciseDecimal(20, 12)` NOT-NULL (decimal fraction); `restatement_reason` /
   `supersedes_id` / `record_version`. Current-head partial-unique
   `uq_benchmark_return_current (tenant_id, benchmark_id, return_date, return_type, return_basis)
   WHERE valid_to IS NULL AND system_to IS NULL`.
5. Vocab constants (module-level, extend-by-value app constants — MG-01, no DB CHECK):
   `LEVEL_TYPE_PRICE_RETURN/TOTAL_RETURN/NET_TOTAL_RETURN`; `RETURN_BASIS_PRICE/TOTAL/NET_TOTAL`;
   reuse the existing `RETURN_TYPE_SIMPLE` (+ `LOG` reserved) from the factor module's home.

## Step 2 — Migration `0029_benchmark_series`
6. Mirror `0023_factor_return.py`: create both tables + the two partial-unique indexes + FK/date
   indexes; **symmetric tenant-scoped FORCE RLS** policies for both tables (the exact
   policy/grant shape `0023` used — NEVER hybrid; no `irp_prevent_mutation` entries). Downgrade =
   drop policies + tables (non-destructive to other tables; cycle `head→0028→head` in validation).
7. `alembic check` MUST be a no-op after models+migration land together; the per-suite migration
   head tests advance `0028` → `0029_benchmark_series`.

## Step 3 — Binder (`marketdata/benchmark_series.py`, NEW module)
8. Mirror `factor.py`'s structure; REUSE from `benchmark.py`: `BenchmarkActor`, `resolve_benchmark`,
   `ensure_vendor_source` (VENDOR_BENCHMARK — **no new source type**). New module-locals: exceptions
   (`BenchmarkSeriesValueError` → 422; `NoCurrentBenchmarkLevel` / `NoCurrentBenchmarkReturn` → the
   supersede/correct-without-head refusal), vocab validators (level_type / return_type /
   return_basis — binder-validated v1 vocab), **finiteness guards** for `level_value` AND
   `return_value` (reject NaN/±Inf pre-write — the P3-2 lesson) + a binder-side `level_value > 0`
   value check (an index level is positive by construction; fail-closed 422 before any write).
9. Per table, the FR protocol verbatim (ONE `now = utcnow()` per op; CLOSE-FIRST; prior-row CONTENT
   never mutated; `supersedes_id` linked; `record_version` incremented):
   `capture_benchmark_level` / `supersede_benchmark_level` / `correct_benchmark_level` (TR-08
   `restatement_reason` → `justification`) / `reconstruct_benchmark_level_as_of` (both axes) /
   `list_benchmark_levels` — and the six `_return` twins.
10. **DQ gates** (fail-closed, co-transactional; `(params, dataset)` Protocol UNTOUCHED); per-tenant
    resolve-or-register rules `benchmark.level_required_fields` + `benchmark.level_sanity`
    (RANGE min 0) and `benchmark.return_required_fields` + `benchmark.return_sanity` (RANGE min −1,
    the ENT-025 band). **Write the module's `_ensure_rule` race-safe from birth** — the P3-C2 OD-E
    savepoint pattern (`begin_nested()` + `except IntegrityError` re-SELECT), NOT the raced
    SELECT-then-INSERT the older binders still carry (their retrofit stays the separate recorded
    item). Verify the RANGE evaluator's boundary semantics against `dq/rules.py` and pin with a
    boundary test.
11. **Audit**: constants `MARKET_BENCHMARK_LEVEL_CREATE/_UPDATE/_CORRECTION` +
    `MARKET_BENCHMARK_RETURN_*` (caller-side strings; `audit/service.py` FROZEN). Single-row grain
    (the FACTOR_RETURN precedent): capture=1 CREATE; supersede=2 (UPDATE close-out + CREATE);
    correct=2 (UPDATE + CORRECTION). `before/after` = DC-2 metadata only
    (`benchmark_code/source/{level_date,level_type|return_date,return_type,return_basis}/
    record_version` — never the captured value payload... note: the factor precedent EXCLUDES the
    vendor-licensed value from audit metadata; keep values out). **No emit on read.** One ORIGIN
    edge per NEW physical version row (targets the level/return row id).
12. Export the new public names from `marketdata/__init__.py`.

## Step 4 — Endpoints (`api/marketdata.py`)
13. Under the existing benchmark router: `POST /benchmarks/{benchmark_id}/levels` (capture),
    `POST .../levels/supersede`, `POST .../levels/correct` — gated `marketdata.ingest`;
    `GET .../levels` (as-of params `valid_at`/`known_at` + list) — gated `marketdata.view`; and the
    `/returns` twins. Mirror the factor-return DTO/error-map shapes exactly (422 value/vocab; 404
    `BenchmarkNotVisible`; the no-current-head refusal mapped as the factor family maps it).
    Decimals serialized as strings byte-for-byte (never float).

## Step 5 — Registry/docs (same commit)
14. Canonical registry: mint the **ENT-052** row (Market Data grouping, after ENT-025's block) +
    update the ENT-009 Notes cell (deferral → "REALIZED in P2-7"); audit taxonomy `MARKET` row
    extension (the R-07 activation record, P3-2 wording); RTM REQ-PUB-003 advanced-NOT-closed;
    decision-record status stamps.

## Step 6 — Tests (unreduced)

> **Fixture realism (user standing rule, 2026-07-09):** representative fixture data must be
> economically plausible — index levels O(10²–10⁴), simple daily returns small decimal fractions,
> real business dates, weights in [0,1]. Deliberately EXTREME values (17-significant-digit precision
> probes, envelope breaches, NaN/±Inf guards) appear ONLY in boundary tests whose name/docstring
> says so — never as an "ordinary" fixture.
15. `test_benchmark_series.py` (SQLite): per table — capture/supersede/correct happy paths + the
    exact audit event sequences (types, actions, DC-2 payload keys, counts) + ORIGIN edge per
    version; both-axes reconstruct (incl. the correction-invisible-before-known_at proof); grain
    uniqueness; cross-tenant `resolve_benchmark` fail-closed; finiteness/positivity/band refusals
    (both binder + DQ layers, boundary-pinned); vocab refusals; prior-row content immutability;
    supersede/correct-without-head refusals; the savepoint race test (the P3-C2 pattern).
16. `test_benchmark_series_pg.py`: FORCE-RLS isolation through capture + reads under the
    NOBYPASSRLS `irp_app` role; no-context zero rows; the partial-unique enforced under PG; a
    17-significant-digit PreciseDecimal roundtrip.
17. `apps/backend/tests/test_benchmark_series_endpoints.py`: 401/403 (no principal / missing
    `marketdata.ingest` vs `.view`); 404 cross-tenant; 422 maps; decimal-verbatim responses.
18. Migration: head test updates; downgrade smoke `0029→0028→head` cycled with real exit codes.

## Validation gates (unreduced — OD-P2-7-H)
`make check` → full-PG suite (schema reset per the recorded recipe incl. the PUBLIC grant) →
`alembic check` no-op → downgrade smoke both directions → `make fe-check` (no FE changes; suite must
stay green) → diff fence (audit/service.py + entitlement/bootstrap.py untouched; no new permission;
exactly ONE new migration).

## Review
FULL 6-finder adversarial review (line-scan / governance-tenancy / cross-file / concurrency+precision
/ test-quality / plan-conformance+docs), findings folded, then HOLD for Tier-2 commit approval.

## Sizing
M. All templated: models+migration ≈ `0023`'s shape ×2 tables; binder ≈ `factor.py` minus the EV
half; endpoints ≈ the factor-return family ×2.
