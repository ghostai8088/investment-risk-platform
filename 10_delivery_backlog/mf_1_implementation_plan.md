# MF-1 Implementation Plan — multi-family factor exposure end-to-end

> Executes `mf_1_decision_record.md` (OD-MF-1-A…F) on ratification of OQ-MF-1-1…6. Branch `mf-1-impl`.
> **NO migration** (head stays `0040`); NO new permission/EVT/canonical id/model CODE; NO API or FE change;
> `audit/service.py` FROZEN. The slice is: one demo-extension module + its chain + validation records + tests
> + three hygiene folds + docs.

## Step 0 — Fences (verify before writing code)

- `alembic heads` = `0040_var_estimate_age`; re-verify at the end (`alembic check`, no new revision).
- The base campaign files stay byte-untouched: `demo/campaign.py`, the 16-code `TIER_DOSSIERS` lock, every
  existing test in `test_demo_campaign_pg.py`. The extension is a NEW module.
- Scenario gates (`risk/scenario.py:152`, `scenario_service.py:159`) and the active-risk whitelist: untouched
  (their probes must pass unmodified).
- Legacy demo instruments (the PE fund + two campaign equities): zero new `proxy_mapping` rows minted against
  them (the OD-A mixed-family fence — probe-pinned in Step 6).

## Step 1 — The extension module (`packages/shared-python/src/irp_shared/demo/multifamily.py`)

- Entry: `run_demo_multifamily_extension(session) -> MultifamilyExtensionSummary` (frozen dataclass echoing
  seeded/ran/filed counts, the campaign summary's shape). Thin CLI shim `scripts/run_demo_multifamily.py`
  (the 66-line campaign shim's shape; `DATABASE_URL`; prints the summary).
- **Guards, both refuse-not-skip and fail-closed:**
  - Base-campaign-present: refuse if the demo tenant holds no `Model` rows (`DemoMultifamilyPrereqError` —
    the extension extends the living tenant, never bootstraps).
  - Own-footprint: refuse if `risk.factor_exposure.loadings` is already registered in the tenant
    (`DemoMultifamilyAlreadySeededError` — the double-run probe pins this).
- Deterministic ids via the campaign's `demo_id` uuid5 helper, new `mf1:` prefixes (re-seedable after a schema
  reset, the documented product feature).
- All writes through the REAL service layer (capture/register/run/validate services) — the campaign discipline;
  no direct ORM inserts for governed content.

## Step 2 — Registrations + tiers (OD-B)

- `register_factor_exposure_loadings_model(...)` in the demo tenant — the 17th code (`code_version` =
  `"demo-mf1"`); registrar rides `model.inventory.register` (reused).
- A distinct `perf.return.desmoothed_geltner` version with declared `alpha="1"` (`code_version="demo-mf1"`;
  the campaign's α=0.4 version untouched — α is version identity, OD-PA-1-E; the FL-1 test's exact shape).
- Tier assignments by the seeded 2L principal (`model.validate`): the loadings model per its dossier ratings
  (expect TIER_2: materiality MEDIUM at seeding — a new sleeve, not the flagship book; complexity MEDIUM);
  recorded in the MF-1 dossier section. The α=1 version needs no tier action (tier is MODEL-grain;
  `perf.return.desmoothed_geltner` is already tiered).

## Step 3 — The book (OD-A; all values TD-1-plausible, single currency = the tenant base)

- 3 NEW instruments: `MF1-EQ-A`, `MF1-EQ-B` (public equities), `MF1-CR-A` (corporate-bond/credit position);
  1 NEW portfolio ("multi-asset sleeve") with positions in all three. **No FX leg**: every mark in the base
  currency (the exposure run is FX-uniform by construction; FX seeding stays out of the slice).
- 3 NEW factors (DAILY): `MARKET` family broad-equity index, `RATES` family rates index, `CREDIT_SPREAD`
  family credit index — the Sharpe-1992 asset-class set under the FL-1 FRTB names. **~40 CALENDAR-daily
  SIMPLE returns each** (the campaign precedent — the OLS per-period coverage gate has no zero-fill, so
  every mark-to-mark period must contain candidate-factor returns; calendar-daily seeding makes alignment
  unconditional), seeded FIRST as plausible index paths.
- ~12 daily marks per instrument, GENERATED from a declared true-loading structure over the seeded factor
  returns + small idiosyncratic noise (documented in the module: the numeric finder re-derives the OLS from
  the same inputs): EQ-A ≈ {MARKET 0.9}, EQ-B ≈ {MARKET 0.7, RATES −0.2}, CR-A ≈ {RATES 0.6,
  CREDIT_SPREAD 0.8}. Marks stay positive and plausible (TD-1 bands). The Σw_f per instrument is disclosed
  where it matters: the total-family residual leg scales by MV·Σw_f (OD-C's recorded disclosure).
- The exposure run passes **`base_currency` explicitly** (the campaign precedent — no tenant-level base
  exists); every mark is in that one currency, so no FX rows are seeded and the identity-conversion path
  pins zero FX legs.
- Window arithmetic (verified by the pre-ratification pass against the demo-mg1 declared parameters):
  12 marks ⇒ 11 observed ⇒ 10 α=1 periods; **k=3 ⇒ OLS floor `max(4, 5)` = 5** — 10 clears it; the
  demo-mg1 covariance window is 30 and the HS window is 21 @ c=0.95 — the ~40-return span covers both.

## Step 4 — The estimation chain (OD-C, per instrument; all through shipped services)

1. α=1 `DESMOOTHED_RETURN` run over the instrument's marks (the FL-1 identity detour, disclosed in the
   dossier prose).
2. `run_proxy_weight_estimate` — target = the desmoothed window; **candidates = the FULL three-factor set
   (k=3, the Sharpe-1992 shape OD-C ratifies)** — near-zero betas on unloaded factors are honest output;
   the std errors + R² stay first-class on the estimate rows.
3. `promote_proxy_weight_estimate` per (instrument, factor) coefficient — **the analyst promotes the
   STRUCTURAL coefficients only** (EQ-A: MARKET; EQ-B: MARKET + RATES; CR-A: RATES + CREDIT_SPREAD — the
   PA-3 deliberate-per-coefficient design used as designed; the near-zero coefficients stay recorded,
   unpromoted) → REGRESSION-method `proxy_mapping` head rows, all citing that instrument's ONE estimate run
   (the shape the total-VaR single-cited-run gate requires). Every sleeve atom is loaded ⇒ the coverage
   gate passes by construction.

## Step 5 — The run chain (OD-C; one COMPLETED run each, bound to the demo-mg1 flagship versions)

1. `run_exposure` over the sleeve (exact-date marks; no FX gaps by construction).
2. The **loadings-family factor-exposure run**: bind the Step-2 loadings model; snapshot via the
   `loadings_family` builder mode (predicate `v1:exposure-run-atoms+factor-list+loading-rows`); factor list =
   the three-factor set.
3. `run_covariance` over the three factors (the demo-mg1 covariance version's declared window).
4. Five governed numbers, one run each, **bound to the exact `demo-mg1` versions carrying the AWCs**:
   `risk.var.parametric`, `risk.var.historical`, `risk.var.parametric_total` (the REGRESSION-cited residual
   leg pays real residual variance for all three instruments; estimate ages fresh ⇒ the BT-2 gate passes),
   `risk.var.parametric_es`, `risk.var.parametric_es_total`.
5. Assert every run COMPLETED before Step 6 files anything. The extension is **single-commit** (services
   flush; the CLI shim commits ONCE at the end — the campaign's exact shape), so a mid-chain failure rolls
   back WHOLE and the tenant stays clean and re-runnable; the Step-1 footprint guard is the belt-and-braces
   for any caller that commits early (registrations run first, so any partial commit contains the loadings
   model and the probe fires).

## Step 6 — The validation records (OD-D; dossier texts in `demo/dossiers.py`, new MF-1 section)

- **5 × TRIGGERED + APPROVED_WITH_CONDITIONS**, one per flagship, against the SAME `demo-mg1`
  `model_version_id`s: conditions = **FRESHLY DRAFTED per model in the dossiers MF-1 table (the OQ-3
  ratified text)** — the explicit re-scoped specific-risk clause (full for parametric/HS/ES; the
  non-proxied/MANUAL-atoms residue for total/ES-total) + the surviving riders re-drafted standalone
  (historical's window floor and total's BT-2 read rule + v1 grandfather near-verbatim; parametric's
  normality posture, the ES non-reconciling row, and the ES-total cross-reference re-written), ZERO
  occurrences of 'FL-1' anywhere in the new records; findings = closure prose + surviving
  registered-limitation keys (fail-loud resolution, the campaign mechanism) WITH the frozen-wording
  disclosure ("the limitation text predates the multi-family widening — read 'CURRENCY-family' as the
  bound factor set"); evidence = the Step-5 run for that model (CALCULATION_RUN) + one DOCUMENT row
  referencing `10_delivery_backlog/mf_1_decision_record.md`; `next_review_due` = **filing-day + 365**
  (the TIER_1 ceiling is write-time strict-`>` vs `utcnow` — never a fixed calendar date); scope_summary
  names the multi-family closure.
- **1 × INITIAL + AWC for the loadings model** (`demo-mf1` version): findings from its TWO registered
  limitation rows (the unmodeled loaded-atom residual; the price-return-betas + short-window-noise row —
  keys resolved fail-loud against the actual row texts), plus the MV·Σw residual-scaling disclosure;
  evidence = the loadings exposure run + the through-VaR run; conditions = the residual/estimation posture
  (no 'FL-1' token); **`next_review_due` = filing-day + 365** (within the TIER_2 730 ceiling — the Step-2
  tier assignment MUST land before this record; the ordering dependency is load-bearing).
- **1 × time-boxed EXCEPTION for the α=1 `demo-mf1` desmoothing version** (validation is VERSION-grain;
  the α=0.4 version's exception does not cover it) — the campaign's `EXCEPTION_CONDITIONS` shape, expiry =
  filing-day + the model's tier ceiling; no 'FL-1' token by construction.
- Recorded by the seeded 2L principal (the human-only actor guard; the `model.validate` claim rests on the
  principal's seeded role — the permission check is API-layer, and the extension drives the service
  directly, the campaign's recorded pattern).

## Step 7 — Tests (new `packages/shared-python/tests/test_demo_multifamily_pg.py`) + CI

- Prereq refusal (empty tenant) + **double-run refuse-not-skip probe** (the extension after itself).
- Post-extension pins: **17 codes**; every Step-5 run COMPLETED; the loadings run's family/predicate; a
  spot-golden on one hand-derivable number (the loadings projection row for EQ-A, from the declared inputs).
- **The grep flip, both directions on the CONDITIONS surface (OQ-6):** the LATEST validation per flagship
  version carries zero 'FL-1' in `conditions`; a tenant-wide conditions grep finds the token in exactly the
  5 HISTORICAL AWC rows (append-only visibility pinned); every NEW record's conditions/scope/findings avoid
  the token (asserted). The 3 historical `scope_summary` occurrences (the constant-series note) are recorded
  and excluded from the pinned surface.
- **The mixed-family fence probe:** legacy instruments carry zero non-CURRENCY `proxy_mapping` head rows;
  the legacy proxy-family exposure run still binds (the PA-2 family stays runnable).
- **The coverage-gate probe:** a THROWAWAY portfolio with one unloaded instrument refuses the loadings run
  (the refusal text pinned) — the sleeve itself never trips it.
- Base-only invariance: the existing `test_demo_campaign_pg.py` passes unmodified on a FRESH-SCHEMA
  base-only tenant (its tolerate-living-tenant mode and the dirty-schema double-run retire at MF-1 —
  record Part 3 item 12; the campaign suite stays byte-untouched).
- **ci.yml: add the new PG suite step, pinned AFTER the campaign step and BEFORE the downgrade smoke**
  (the ordering is load-bearing — all PG suites share one DB, and the campaign pins are false on an
  extended tenant; also the recurring PA-4/P3-7 add-the-step miss-class, named so it cannot be forgotten).
  The suite runs on the OWNER engine (the campaign suite's recorded pattern for whole-surface writers —
  `test_demo_campaign_pg.py:3-7`; the per-suite `irp_app` grant-list pattern does not fit this footprint).

## Step 8 — Hygiene folds + docs (OD-F)

- `marketdata/proxy_mapping.py:342-345` + `risk/proxy_weight_service.py` (~:202-203 AND the module
  docstring's two further stale lines at :28/:34): stale CURRENCY-only docstrings corrected to name the
  FL-1 `LOADING_FACTOR_FAMILIES` widening. The registrar limitation CONSTANTS (`risk/bootstrap.py:665-667`
  + the HS analogue) are NOT edited — behavioral for new registrations; disclosed + recorded per record
  Part 3 item 11.
- `snapshot/service.py` `_BINDING_PREDICATES`: add `FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE` to the
  import-time length assert (completeness; the constant passes today).
- `factor_exposure_loadings_v1.md` Known limitations: dated MF-1 amendment — the demo-tenant CURRENCY-only
  item closes (the condition premise no longer holds; the TRIGGERED records are the closure).
- `mg_1_decision_record.md`: NO edit (append-only history); the closure is recorded HERE and in the roadmap
  row at closeout.
- Closeout (OQ-W5C-5 checklist, ALL items): record Status → CLOSED **including the record's own Part-6
  tail (the "pending PR merge" line — the site missed twice historically)** + roadmap Part 2.9 row +
  amendment-log entry + current_state banner + memory. Then the **Wave-6 close review** (the OD-E re-tee
  on its agenda).

## Battery (merge preconditions)

`make check`; full local-PG fresh (schema reset WITH the PUBLIC grant — the recurring gotcha) including the
new suite; the extension double-run probe; `alembic check` (no new revision); downgrade smoke unchanged;
CI-watch-to-green including the new PG step. 4-finder review per OD-F folded before merge.
