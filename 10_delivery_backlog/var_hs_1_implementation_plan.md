# VAR-HS-1 Implementation Plan — Historical-Simulation VaR

> Build contract for VAR-HS-1 (decisions: `var_hs_1_decision_record.md`, OD-VHS-A…G; gated on OQ-VAR-HS-1-1…7).
> Mirrors the P3-5 parametric shape end-to-end; the deltas are the kernel (empirical quantile instead of
> √(xᵀΣx)·z), the model family, and the additive migration. Planned against HEAD `afed75c`.

## Steps
1. **Migration `0028_var_historical`** (additive): `ALTER COLUMN z_score DROP NOT NULL`, same for `sigma`
   (verify actual nullability first — if already nullable, the migration shrinks accordingly); no new
   table/RLS/trigger change; head flips 0027→0028 (test-glob + head assertions updated, the established list).
2. **Registrar** (`risk/bootstrap.py`): `register_historical_var_model` — family `risk.var.historical` v1;
   declared assumptions `confidence_level` (vocab parity), `horizon_days` (=1 verbatim), `window_observations`
   (strict ASCII digits), `quantile_convention` (v1 literal `LOWER_ORDER_STATISTIC`); idempotent same-declaration
   return; 409 conflicts; non-REGISTERED twin refusal (the P3-C1 contract ×5th registrar).
3. **Kernel** (`risk/var_hs_kernel.py`): pure `Decimal` — scenario P&Ls `xᵀ·r_t` over the pinned window;
   order-statistic selection `k = ceil(N·(1−c))`; loss sign convention identical to parametric
   (`var_value ≥ 0` for a long-loss quantile; sign handling stated in the methodology doc); magnitude gate
   (Numeric(28,6) envelope ⇒ committed FAILED, never a PG overflow).
4. **Binder** (`risk/var_hs_service.py` or an extension of `var_service.py` — implementation picks the smaller
   diff and records it): `run_var_historical` with build-in-request AND consume-snapshot paths; pins = the
   FACTOR_EXPOSURE run's IA rows + per-date factor-return pins (the P3-4/P3-5 machinery); pre-create adjudication
   (coverage: exposure factors ⊆ window factors per date, common-date alignment fail-closed, no imputation;
   uniform base currency; duplicate/canonical-order refusals; both-modes ambiguity refusal); window floor
   OD-VHS-E; own-tenant re-resolution of the two provenance run FKs; the P3-C1 `execute_governed_run` scaffold;
   `metric_type='VAR_HISTORICAL'`.
5. **Endpoints** (`api/risk.py`): POST `/risk/models/var-historical`, POST `/risk/vars-historical/runs`,
   GET run, GET row — the parametric error-map/DTO pattern (decimals as strings; `failure_reason` surfaced).
   FE-1 requires NO change (same VAR run family appears in the list; the detail's VaR columns render, with
   z/sigma cells showing "—" for hist-sim rows — verify, don't assume).
6. **Methodology doc** `05_analytics_methodologies/var_historical_v1.md`: method, assumptions/limitations
   FIRST-CLASS (slow volatility reaction vs FHS; equal weighting; specific-risk = 0; discrete quantile), the
   Part-2 benchmark citations, the v2 roadmap (FHS/BRW/ES/backtesting).
7. **Tests** (the house bar): kernel exactness with hand-computed references (a 4-obs and a 100-obs window with
   KNOWN order statistics — dual-path: kernel AND the governed consume path); adjudication refusals ×each gate;
   window-floor refusals; model-identity (families cannot cross-bind — parametric mv on a hist-sim run refused
   and vice versa); declared-parameter strict-parse refusals; endpoint round-trips + FAILED persistence;
   PG suite `test_var_hs_pg.py` (RLS isolation, append-only, FAILED-on-PG) + its ci.yml step; migration
   head/chain updates; FE detail rendering check for null z/sigma (frontend test if any change proves needed).
8. **Validation gates (unreduced):** make check; full-PG suite with clean schema reset (incl. downgrade smoke
   across 0028); frontend suite (expected untouched); the 6-finder adversarial review (methodology slice = full
   review, incl. a numeric/quant finder verifying the order-statistic math and the coverage adjudication);
   fold → HOLD Tier-2 commit approval.

## Definition of done
Hist-sim VaR runs end-to-end on both paths with exact-decimal reproducibility; hand references proven dual-path;
all refusal gates tested; `var_result` carries both methods side-by-side with correct null semantics; the FE-1
view shows hist-sim runs without modification; migration 0028 up/down clean; methodology doc cites its benchmarks;
zero new permissions; `audit/service.py` untouched.
