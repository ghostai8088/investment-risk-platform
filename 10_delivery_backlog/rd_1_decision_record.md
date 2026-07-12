# RD-1 Decision Record — run-resolver dedup (Wave-3 slice 1)

> **Status: implemented 2026-07-12** (RATIFIED at the Wave-2 close, OQ-W2C-3). A hygiene/dedup slice —
> NO migration, NO permission/audit/methodology, NO behavior change. Pays the TIPPED `resolve_*_run`
> helper family recorded at the P3-6 review (Part 6, D-1). Delivered under the delivery-autonomy grant
> (Claude self-drives; USER merges the PR).

## Part 1 — Problem

Every governed-number family resolved a `calculation_run` by id with the SAME query — an explicit
`tenant + run_type` predicate (fail-closed; RLS is the belt, the explicit predicate the braces),
surfacing a committed FAILED run rather than hiding it. That body had accumulated to **ten
near-verbatim copies**:
- **8 `resolve_*_run` READ resolvers** (risk: var, active_risk, covariance, factor_exposure,
  scenario, var_backtest; perf: portfolio_return, benchmark_relative) — each raising its own
  `*RunNotVisible(str(run_id))`, differing ONLY in the `run_type` constant + the exception class;
- **2 `_resolve_run` CONSUMED-run guards** (var_backtest, scenario) — the same query plus a COMPLETED
  assertion before an id is stamped into a hard-FK column (PG FK checks bypass RLS — the P3-5
  finding), differing ONLY in the input-error class.

This meets the **P3-4-R0 3rd-consumer tipping rule** (the read resolver is at 8; the guard at 2 but
identical). Deferred at the P3-6 review pending the Wave-2 close; the clean-code standing bar +
the tipping rule both fire.

## Part 2 — Decision

- **OD-RD-1-A — one shared module `calc/runs.py` with two helpers:** `resolve_run_of_type(session,
  run_id, *, acting_tenant, run_type, not_visible)` (the READ path; `not_visible` is an injectable
  `Callable[[str], Exception]` — each family passes its own `*RunNotVisible` class) and
  `resolve_completed_run_of_type(..., label, error)` (builds on the first, adds the COMPLETED check;
  `error` is the injectable input-error class). The `error=`-injection precedent is
  `assert_portfolio_in_tenant(error=…)`, already in the tree.
- **OD-RD-1-B — keep each family's public wrapper + its own exception type.** The `resolve_*_run`
  functions are exported and the API error-maps depend on the SPECIFIC classes; each becomes a
  thin wrapper delegating to the shared helper (name, signature, exception, docstring preserved).
  ZERO behavior change — the SQL and the raised classes/messages are byte-identical to before.
- **OD-RD-1-C — scope = the whole family, not just the 3 named at P3-6.** All 8 reads + both guards
  collapse; leaving 5 identical copies would be incoherent for a dedup slice.
- **OD-RD-1-D — the FR-membership protocol generalization (P3-6 D-2) stays DEFERRED.** It is a
  design-scale extraction (a parameterized bitemporal engine over `proxy_mapping` + `scenario_shock`,
  2 instances) — a different order of work than this mechanical resolver collapse; its trigger is a
  3rd FR-membership entity.

## Part 3 — Verification

Behavior-preserving refactor + a new direct unit test of the shared contract (`test_calc_runs.py`:
the tenant/run_type predicate, the injectable classes, the COMPLETED branch, FAILED-run surfacing).
The 10 wrappers stay fully exercised by their family suites. `make check` 1269→**1272** passed
(+3 new) / 266 skipped; local-PG **266** green on a clean schema; net **−30** lines across 8 service
files + the one small shared module. NO migration → no drift/downgrade delta.
