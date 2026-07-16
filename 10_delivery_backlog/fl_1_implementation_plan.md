# FL-1 Implementation Plan — the loadings substrate + the fractional exposure family (the build contract, Steps 0–8)

> Executes `fl_1_decision_record.md` (OD-FL-1-A…F) once OQ-FL-1-1…6 are ratified. Exemplars: PA-2
> (a new family through the SAME binder with a symmetric binding predicate — the closest shape),
> PA-3 (the OLS estimate→promote loop being repointed), ES-1 (`_resolve_var_family` = the dispatch
> registry-map precedent; the probe-move pattern; the invariance regressions). **NO migration**;
> NO new permission/EVT/ENT; `audit/service.py` FROZEN; **the demo tenant untouched**; the
> OQ-W5C-5 closure checklist at close. Finder agents pinned to Opus (the MG-1 budget lesson).

## Step 0 — Branch + pre-checks

`fl-1-impl` off `main` (post-planning-merge). Verify the Grounding facts hold: the `loading` column
`Numeric(20,12)` NOT NULL on `factor_exposure_result`; `private_instrument_id` in the pin
serializer's key set; `build_factor_index`'s NULL-currency raise; the active-risk allocation-only
whitelist; zero CHECKs on `factor.factor_family`; snapshot `component_kind` unconstrained (no
CHECK — load-bearing for the zero-migration pin reuse); the FIFTH gate present at
`scenario_service.py:159`; head `0040`.

## Step 1 — The vocab + the aliases (OD-A) — `marketdata/models.py`

- `FACTOR_FAMILY_RATES = "RATES"`, `FACTOR_FAMILY_CREDIT_SPREAD = "CREDIT_SPREAD"`,
  `FACTOR_FAMILY_COMMODITY = "COMMODITY"` added to `FACTOR_FAMILIES` (one tuple, zero migration).
  The comment block carries the FRTB mapping VERBATIM (MAR33.14's five classes) + the two aliases
  (**CURRENCY ≡ FX; MARKET ≡ equity-class — by declaration, recorded, revisited if a genuine
  cross-asset market factor ever arrives**) + the deliberate MAR21-7-class non-adoption note.
- The factor-taxonomy doc (`04_data_model/` or the marketdata methodology page — wherever the
  family vocabulary is documented) gains the same mapping table with the MAR33.12 Table-2
  liquidity-horizon floors carried as per-class reference constants (prose, not code — MF-1's
  later use).

## Step 2 — The gate relaxations + probe moves (OD-E)

- `proxy_mapping.py:356`: `!= CURRENCY` → membership in `PROXY_FACTOR_FAMILIES` (CURRENCY +
  MARKET + RATES + CREDIT_SPREAD + COMMODITY + the Barra four; `OTHER`/unknown still refused).
- `proxy_weight_service.py:266`: same allow-list (the regression's candidate factors).
- `factor_service.py:96/227`: `SUPPORTED_FACTOR_FAMILIES` widens **for the loadings family's
  pinned factors only** — the allocation/indicator path keeps its CURRENCY-only structural
  requirement (`build_factor_index` needs a currency partition; its gate and error text are
  untouched). Mechanically: the family check moves from a global pin-gate to a per-family gate
  applied after dispatch (the loadings family admits the allow-list; allocation admits CURRENCY).
- `scenario.py:152` AND its run-binder twin `scenario_service.py:159` (the verifier pass's fifth
  gate): **BOTH UNTOUCHED** (OD-E — recorded, not relaxed; the two-gate inventory recorded for
  MF-1). The allow-list constants (`PROXY_FACTOR_FAMILIES` + the widened `SUPPORTED_FACTOR_FAMILIES`)
  MUST carry identical contents — OD-E's requirement; assert it in a test if they are separate
  constants.
- **The three probe moves** (the ES-1 pattern, done IN THIS STEP not discovered in the battery):
  `test_factor_exposure.py:~1105` (STYLE probe → `OTHER` — STYLE would also still refuse
  structurally on the allocation path, but the probe pins the FAMILY gate, so it moves),
  `test_proxy_mapping.py:~372` (STYLE → `OTHER`), `test_proxy_weight.py:386` (MARKET → `OTHER`);
  `test_scenario.py:~374` UNCHANGED — its gate stays. Each move keeps the refusal pinned against a
  still-refused value.

## Step 3 — The estimation repoint (OD-B) — the α=1 detour

- α is a FREE declared identity parameter with domain `(0, 1]` (`desmoothing_service.py:14`,
  `bootstrap.py:327`) — NOT an enumerated vocabulary, so α=1 is already admissible and the kernel
  treats it as the property-tested identity boundary (`desmoothing_kernel.py:14`). No vocabulary
  work exists (the verifier pass mooted the earlier contingency); register the α=1 model_version
  and verify the identity end to end.
- The public-instrument chain, end to end: marks (create_valuation series) → desmooth run at
  α=1 (identity — the referent discloses the semantic stretch) → PA-3 OLS estimate over the
  widened candidate-family set → `promote_proxy_weight_estimate` into the widened ENT-019.
  ONE integration test drives it for a public equity over MARKET + a second family, asserting the
  promoted loadings equal the OLS betas read back from the estimate rows (the estimate-seam test's
  shape, reused). Arithmetic honesty (the verifier pass): 9 marks ⇒ 8 observed ⇒ **7 desmoothed
  periods** reach the OLS (the α=1 run consumes its seed) — k ≤ 5 headroom, the test uses k=2. The
  demo's shipped desmooth chain covers only the private fund, so this chain is a NEW instantiation
  of the shipped services. Fixtures TD-1-realistic: plausible marks, orderly
  mark→desmooth→OLS→run dates (the MG-1 date-ordering fold class).
- The PA-3 referent gains a dated additive section: public-instrument use, the α=1 disclosure,
  price-return betas, unconstrained-OLS-vs-classic-RBSA (carried forward), std errors first-class.
  **`desmoothing_geltner_v1.md` gains the SAME dated applicability note** — its Purpose currently
  scopes v1 to appraisal-based private assets, and the public-marks α=1 use must be disclosed there
  too or the doc set self-contradicts (the verifier pass's doctrine MEDIUM).

## Step 4 — The loadings family (OD-D) — binder + kernel + predicate

- `bootstrap.py`: `FACTOR_EXPOSURE_LOADINGS_MODEL_CODE = "risk.factor_exposure.loadings"`, v1
  registrar (the proxy registrar's shape; `model.inventory.register` reused), methodology ref →
  the new `factor_exposure_loadings_v1.md`; assumptions carry the projection semantics + the
  allow-listed families; limitations carry the projection-not-partition row (the proxy family's
  language), price-return betas, and the active-risk refusal.
- **The dispatch registry map** (ratified in OD-D): `run_factor_exposure`'s two-arm try/except →
  a `_resolve_exposure_family` over the three codes (the ES-1 `_resolve_var_family` shape,
  including the first-error-wins message discipline). The allocation + proxy paths' behavior is
  byte-identical (invariance regressions in Step 7).
- The snapshot builder: `build_factor_exposure_snapshot` gains the loadings mode — pins EXPOSURE +
  FACTOR + `COMPONENT_KIND_PROXY_MAPPING` rows (the widened ENT-019 IS the loadings source; the
  pin serializer is UNTOUCHED — `private_instrument_id` stays the key) under the new predicate
  `"v1:exposure-run-atoms+factor-list+loading-rows"`, with the symmetric both-ways refusal
  extended to a 3×3: each family refuses the other two predicates (the PA-2 gate generalized).
- The compute path: the proxy `_build_rows` generalized — per pinned (instrument, factor, loading):
  `exposure_amount = quantize_HALF_UP(loading × atom_total(instrument), 6)`, `loading` echoed at
  12dp, multiple rows per instrument, sign preserved. The 4-tuple grain absorbs it (no migration).
- **The coverage gate + the carried PA-2 guard (OD-D — the verifier pass's HIGH, ratified via
  OQ-4)**: adjudication REFUSES fail-closed (i) any pinned atom with ZERO loading rows — no
  indicator fallback, no silent zero (a dropped atom would silently under-count VaR) — and (ii)
  any loading row whose factor is NOT in the run's pinned factor list (PA-2's OD-B guard carried
  into the third family). Both refusals get the exact-reason-format treatment on BOTH entry paths.

## Step 5 — The FE drift trio (OD-F) — `apps/frontend`

- `types.ts`: the `PROXY_WEIGHT_ESTIMATE` family — all FOUR additions (FAMILIES,
  RUN_TYPE_TO_FAMILY, runDetailUrl → `/risk/proxy-weight-estimates/runs/{id}`, FAMILY_ROW_COLUMNS:
  `metric_type, instrument_id, factor_id, metric_value, std_error, n_observations, residual_stdev,
  series_currency` — the heterogeneous WEIGHT/INTERCEPT/ESTIMATION_SUMMARY rows share them).
  Verifier-pass correction: the exhaustiveness net (`types.test.ts` + the `Record<Family,…>` type)
  FORCES only FAMILY_ROW_COLUMNS — RUN_TYPE_TO_FAMILY and runDetailUrl are deliberate edits with
  their own explicit NEW tests (check first whether runDetailUrl's default fallthrough already
  yields the right URL).
- `FAMILY_ROW_COLUMNS.vars` += `residual_variance`, `estimate_age_days`, `model_version_id`.
- **The ES honesty fix**: per-row metric_type-aware cell rendering in RunDetail — when
  `row.metric_type === "ES_PARAMETRIC"`, the `z_score` cell renders annotated
  (`{value} (echo — not the ES multiplier)`) so the three adjacent columns stop inviting
  `z×σ = var_value`. Plus the missing FE test: an ES_PARAMETRIC row fixture asserting the
  annotation renders and a VAR_PARAMETRIC row stays clean. (The `es_multiplier`-on-DTO backend
  change is the recorded v2 — NOT smuggled in here.)
- FE suite green locally (`npm run -w apps/frontend test/lint/typecheck`) — CI already gates it.

## Step 6 — Docs + register accounting

- NEW `05_analytics_methodologies/factor_exposure_loadings_v1.md`: the projection formula + its
  replaced identity (vs the allocation family's ε=0 partition — stated side by side); the loadings
  source (the widened ENT-019 + the estimate→promote provenance); the FRTB family mapping; the
  limitations (Part 3 items 1–5 transcribed). Self-declared immutable.
- The ENT-019 catalog row: **WIDENED AT FL-1** (instrument→factor mapping; the `private_instrument_id`
  name-debt note verbatim from OD-C; ENT-058 the paper-minted v2, RESERVED — the next free id
  becomes ENT-059).
- The `proxy_mapping` ORM comment (`marketdata/models.py`) gains the misnomer note verbatim from
  OD-C — the catalog row + referent alone were not enough (the verifier pass's M5; OD-C names all
  THREE homes).
- RTM: REQ-MKT-003 row notes the projection family (the ε=0 acceptance scoped to allocation —
  already its shipped shape since PA-2, restated); the multi-family REQ rows advance to
  In-Progress-substrate.
- `wave_5_close_review.md` register: the FE drift trio → PAID (dated note).
- The scenario gate's non-relaxation recorded where scenario's docs live (a dated one-liner).

## Step 7 — Tests (beyond those named above)

- **Invariance regressions** (the ES-1 pattern): an existing allocation golden AND a proxy golden
  byte-identical after the dispatch refactor + gate rework.
- The loadings-family goldens: hand-derived `loading × atom` over a 2-factor public instrument
  (fractional, signed, multi-row); the projection non-identity pinned NON-VACUOUSLY
  (`Σ exposure ≠ Σ atoms` on a fixture where loadings don't sum to 1, with the exact expected sum
  asserted); grain uniqueness; determinism/ordering.
- The 3×3 predicate symmetry (each family × each foreign predicate refuses — 6 refusal cases).
- **A loadings run driven THROUGH VaR** (the PA-2 precedent — the verifier pass's M1): a
  hand-derived golden over CURRENCY factors (inside the demo fence) — fractional multi-factor
  loadings in, the exact VaR out.
- **The coverage-gate refusals** (OD-D): a pinned atom with zero loading rows refuses; a loading
  row with an unpinned factor refuses (exact reason formats pinned, both entry paths).
- **The fifth gate pinned**: a scenario run over a non-CURRENCY exposure run refuses at
  `scenario_service.py:159` — the run-binder gate gains its own probe (it currently has none).
- Registrar identity/409/vocab refusals; the allow-list gates (per-gate: an admitted family
  passes, `OTHER` refuses, the moved probes stay red).
- The end-to-end public-instrument chain test (Step 3) + a PG leg (the loadings family under RLS;
  fixture grants re-checked per the VW-1 lesson — the loadings family reads only already-granted
  tables: `proxy_mapping`, `factor`, exposure/model tables).
- Active-risk still refuses a loadings-family exposure run (the whitelist pinned against the NEW
  code — currently it's pinned against proxy only, extend the test).
- FE: FAMILY_ROW_COLUMNS exhaustiveness rides the existing `types.test.ts`; NEW explicit tests for
  RUN_TYPE_TO_FAMILY + runDetailUrl (NOT forced by the net — the verifier-pass correction); the
  ES-row annotation test; the estimate-family row rendering.

## Step 8 — Then

Full battery (`make check` + FE suite + local-PG fresh AND dirty double-run + `alembic check` +
the no-`0041` guard + downgrade smoke + the TD-1 realism sweep over every new fixture). **CI-PG
disposition (explicit — the recurring-miss class): the loadings PG leg rides the EXISTING
`test_factor_exposure_pg.py` ci.yml step; any NEW `*_pg.py` file gets its own ci.yml
migration-job step.** → **4-finder review, finders on Opus** (adversarial: the
3×3 predicate gates + the allow-lists + can a loadings row double-count into VaR; numeric: the
projection goldens + the α=1 identity; doctrine: the FRTB/RBSA/alias citation surface; scope +
tests) → fold → push → PR → CI green → merge → **the OQ-W5C-5 closure checklist** → MF-1 planning.
