# P3-6 Decision Record — stress/scenario analytics (Wave-2 slice 5, the LAST Wave-2 slice)

> **Status: RATIFIED 2026-07-12** — OQ-P3-6-1…6 approved as recommended (user: "Approved").
> Drafted 2026-07-12 against HEAD `b90481f` (MD-H1 fully closed, PR #11). P3-6 was moved from Wave 1
> to Wave-2 slot 5 **pre-authorized** at the Wave-1 close; the close review noted it "may defer
> again — an expected outcome, not a failure," and the user directed planning 2026-07-12
> ("Proceed"). Scope: realize **ENT-029 `scenario_definition`** (versioned saved assumptions, BR-8)
> + **ENT-030 `scenario_result`** (run-tracked scenario outputs — the `stress_result` mapping
> pre-ratified at P3-0, OQ-P3-0-9: NO new ENT mint) as the platform's **TENTH governed number**:
> deterministic factor-shock scenario P&L. REQ-MKT-004 (market stress, RTM-P5 — pulled forward by
> the ratified roadmap) moves Draft → In-Progress. Implementation gated separately.

## Part 1 — Decisions at a glance (OD-P3-6-A…K)

| # | Decision | Choice (recommended) |
|---|---|---|
| OD-P3-6-A | **v1 method (the headline call).** | **Deterministic linear factor-shock scenario P&L** over the pinned per-factor exposures of ONE COMPLETED `FACTOR_EXPOSURE` run: `pnl_i = exposure_i × shock_i` per factor, `total = Σ pnl_i` — the SAME linear factor substrate (`dV = Σ x_i·r_i`) every shipped risk number uses (parametric VaR, HS VaR where each historical date IS a scenario, active risk). **NO instrument revaluation, NO convexity/gamma, NO cross-asset propagation, NO correlation-adjusted shock expansion** — each is a recorded v2+ (Part 3). The scenario IS the shock vector; the math is one multiplication per factor — the slice's substance is the GOVERNANCE of saved, versioned scenario assumptions (BR-8), not novel math. |
| OD-P3-6-B | ENT-029 realization shape | **EV header + FR bitemporal shock set** — the ENT-009 `benchmark` + `benchmark_constituent` precedent exactly. `scenario_definition` (EV, pre-ratified at OD-P3-0-M): `code` (per-tenant unique), `name`, `description`, `scenario_type` (binder-enforced vocab: `HYPOTHETICAL`/`HISTORICAL`/`REGULATORY` — a PROVENANCE label, non-load-bearing), `record_version`; updates in place with `REFERENCE.UPDATE` (the factor EV protocol). `scenario_shock` (FR bitemporal, subject to OQ-1): grain one OPEN row per `(scenario_definition_id, factor_id)`; `shock_value` signed `PreciseDecimal(20,12)` (a RETURN fraction, e.g. `-0.10` = −10%); `shock_type` vocab `RETURN` (v1; `ABSOLUTE_BPS` reserved for future non-return factor families); capture/supersede/correct/reconstruct via the membership FR protocol — **the MD-H1 window-coherence guard and race-safe DQ registration apply from birth**. An EMPTY shock set is refused at capture (a scenario that shocks nothing is meaningless — the MD-H1 design-checklist empty-input rule). |
| OD-P3-6-C | ENT-030 realization shape | `scenario_result` — **IA TRUE append-only** (pre-ratified OD-P3-0-M), run-bound + snapshot-gated + model-bound (the full governed-number contract). Grain `(calculation_run_id, metric_type, factor_id)` with `factor_id` NULL exactly once per run (the TOTAL row): per-factor **`SCENARIO_PNL`** rows + one **`SCENARIO_PNL_TOTAL`**. Each per-factor row ECHOES its `shock_value` and `exposure_amount` (the consumed inputs — echo-gated, P3-8 lesson), so the arithmetic is auditable row-by-row. `pnl` at `Numeric(28,6)` base currency (the money scale); `base_currency` carried. Contributions sum to the total EXACTLY by construction (quantize once per row, sum the quantized rows — declared convention). |
| OD-P3-6-D | Model registration | Registered **`risk.scenario.factor_shock` v1** — `code_version`-only identity (**no free numeric request parameter**: the shocks live in the PINNED scenario content, versioned + audited THERE, not in the model — the model is the application rule). Registered via the MD-H1 race-safe `resolve_or_register_*` helpers. Assumptions: linear first-order P&L; RETURN shocks on the CURRENCY factor family; unnamed-factor semantics (OD-G); quantization convention. Limitations: linearity; single-family scope; no revaluation; declared-shock provenance (OD-H); `validation_status` UNVALIDATED until P7. |
| OD-P3-6-E | Permissions + audit | Run family **`SCENARIO`** reusing **`risk.run`/`risk.view` — NO mint** (the BT-1/P3-5 precedent; a scenario run is a risk calculation). Scenario-DEFINITION writes also under `risk.run` (OQ-2): defining a saved scenario is the risk-analyst persona's action; a dedicated `scenario.manage` is a recorded P6/ABAC deferral. Definition/shock writes audit as **`REFERENCE.*`** (the factor/benchmark EV-definition precedent — a scenario definition is versioned reference data) + `MARKET.`-style per-op grain does NOT apply (no vendor capture). `RISK.SCENARIO_CREATE` **reserved-not-emitted at EVT-220** (the standing six-family pattern; result rows are run-tracked + lineaged; zero `RISK.*` events, test-asserted). `audit/service.py` stays FROZEN. |
| OD-P3-6-F | Snapshot + reproducibility | New purpose **`SCENARIO_INPUT`** pinning: `COMPONENT_KIND_FACTOR_EXPOSURE` (REUSED — the exposure rows consumed) + a NEW **`COMPONENT_KIND_SCENARIO`** (the definition header + the OPEN shock set content, hashed — so a later shock supersede CANNOT move a historical run, TR-09; AD-014 pinned-content-only reads at execution). Both TR-09 sides tested: a post-run shock supersede does not move the result; a re-run against the same pins reproduces byte-identically. |
| OD-P3-6-G | Partial-coverage semantics | An exposed factor the scenario does NOT name ⇒ **shock 0 by scenario semantics** (subject to OQ-3): a deterministic scenario is a COMPLETE specification of what moves — "unnamed = unchanged" is the standard reading, NOT statistical imputation (the covariance fail-closed rule governs ESTIMATION gaps, which this is not). Honesty rails: every exposed factor gets a result row (shock echoed, 0 included); the TOTAL row carries `n_factors_exposed` / `n_factors_shocked` / `n_shocks_unmatched` (shocks naming factors the portfolio isn't exposed to — applied to nothing, recorded loudly). |
| OD-P3-6-H | Scenario provenance (v1 boundary) | v1 shocks are **DECLARED values** whatever their provenance — hand-authored hypothetical, offline-derived from a historical episode, or regulatory-prescribed (the declared-not-computed precedent: VAR z-scores, Kupiec criticals, PA-1's α). **In-platform historical-window replay** (shocks computed FROM the captured `factor_return` series over a named window) is a recorded **v2** — it is a COMPUTED scenario needing window/compounding conventions. **Worst-case / plausibility-constrained scenario search** (Studer; Breuer et al.) is a recorded **v3** research direction. |
| OD-P3-6-I | Migration + tenancy | Migration **`0035_scenario`**: `scenario_definition` (EV) + `scenario_shock` (FR) + `scenario_result` (IA, `APPEND_ONLY_TABLES` + P0001 trigger + ORM guard). All three symmetric FORCE RLS (NEVER hybrid). `scenario_result.factor_id` deliberately NOT a hard FK (the pinned components are authoritative — the covariance/factor-exposure precedent); `scenario_shock.factor_id` IS a hard FK (a live definition references live factors — the proxy_mapping precedent). The MD-H1 identifier sweeps (literal + built `tenant_isolation_` names) cover the migration automatically; new CI PG RLS step added. |
| OD-P3-6-J | Review + flow | **FULL 4-finder governed-number battery** (it IS the tenth governed number) + rule-6 external research (Part 2). API ships in-slice (5 definition endpoints + run + list — the P2-7/PA-0 precedent). Fixtures follow TD-1 realism; every full-stack golden ships its derivation (the MD-H1 golden rule); the MD-H1 design-completeness checklist runs at design time (empty shock set refused; both TR-09 sides; scenario_type vocab ENFORCED in the binder, not doc-stated; no RUNNING orphan on any refusal). PR flow; Claude pushes, USER merges. |
| OD-P3-6-K | Requirements traceability | **REQ-MKT-004 Draft → In-Progress** (RTM-P5 pulled forward — P3-6 was pre-authorized from Wave 1 at the ratified close; the RTM row gains the standard governed-number note). CAP-9 (stress) becomes partially executable; CTRL-002/018 apply as on every governed number. The REQ does NOT close in v1 (linearity + single-family scope are named gaps). |

## Part 2 — External benchmark research (roadmap Part 4 rule 6; sources checked 2026-07-12)

- **BCBS, "Stress testing principles" (2018)** — the supervisory baseline: stress frameworks need
  clear governance, DOCUMENTED scenario definitions, and repeatable infrastructure. P3-6's whole
  design (versioned definitions, pinned execution, auditable per-factor rows) is that governance
  layer; the math is deliberately minimal. High confidence.
- **Basel FRTB / MAR (BCBS d457, already cited at VAR-HS-1)** — the standardised approach applies
  PRESCRIBED shocks to SENSITIVITIES per risk class: regulatory precedent for "declared shock vector
  × linear exposure" as a legitimate, supervisory-grade calculation shape (v1's exact form).
  High confidence.
- **Federal Reserve CCAR/DFAST + EBA EU-wide stress testing** — supervisor-PUBLISHED scenario
  definitions applied bank-side: the `REGULATORY` scenario_type + declared-shock provenance mirrors
  this split (the scenario author need not be the platform). High confidence at this generic level.
- **Studer (1997), "Maximum loss" (ETH Zürich)** and **Breuer, Jandačka, Rheinberger & Summer
  (2009), "How to find plausible, severe and useful stress scenarios" (Int. J. Central Banking)** —
  the systematic-search literature: worst-case scenarios under a plausibility (Mahalanobis) bound.
  Recorded v3 — a COMPUTED scenario generator needing its own model governance. Moderate-to-high
  confidence in the citations; the substance (plausibility-constrained maximum loss over an
  ellipsoid) is standard and does not depend on the exact bibliographic details.
- **Historical-replay practice** (industry-standard 1987/2008/2020 episode replays) — the named v2:
  in-platform window-derived shocks from the captured `factor_return` series. No single citation —
  ubiquitous practice; recorded as such.

## Part 3 — Limitations carried forward + out of scope (recorded)

- **Linear first-order P&L only** — no revaluation, convexity, gamma, or path dependence; a large
  shock on a nonlinear book is understated/overstated with no warning beyond the model limitation.
- **CURRENCY factor family only** (the platform-wide v1 scope — enforced at the shock binder per
  the PA-0 fold precedent, not doc-stated).
- **No in-platform historical replay (v2), no scenario search (v3), no reverse stress testing, no
  ES/expected-shortfall integration, no multi-period/propagated scenarios.**
- **No scenario approval workflow** — `scenario_type=REGULATORY` is a label, not an attestation;
  maker-checker on definitions is P7 (the model-validation workflow precedent).
- The captured-holdings-book limitation propagates (exposures inherit it from the exposure run).

## Part 4 — Open decisions (OQ-P3-6-1…6) — pending ratification

| # | Question | Recommendation |
|---|---|---|
| OQ-P3-6-1 | `scenario_shock` temporal class: FR bitemporal vs EV replace-in-place? | **FR bitemporal** — BR-8 says VERSIONED assumptions; the benchmark-membership protocol is proven, gives as-of reconstruction + the MD-H1 guard for free, and shock history is exactly what an auditor asks for ("what did this scenario say last quarter?"). |
| OQ-P3-6-2 | Definition-write permission: reuse `risk.run` vs `marketdata.ingest` vs mint `scenario.manage`? | **Reuse `risk.run`** — the defining persona IS the running persona (risk analyst); a scenario is not vendor market data (ingest would be a category error); a dedicated permission fails the R-07 mint bar today (recorded P6/ABAC deferral). |
| OQ-P3-6-3 | Exposed-but-unshocked factors: zero-fill by scenario semantics vs fail-closed? | **Zero-fill with loud rails** (per-row shock echo incl. the zeros + the three coverage counts on the TOTAL row) — "unnamed = unchanged" is what a deterministic scenario MEANS; fail-closed would make every real partial scenario unusable. |
| OQ-P3-6-4 | Run-type name: `SCENARIO` vs `STRESS`? | **`SCENARIO`** — matches the canonical entity names (scenario_definition/scenario_result); "stress" is a scenario SEVERITY connotation, not a different calculation. |
| OQ-P3-6-5 | Result rows for a factor with zero exposure but a defined shock? | **No row** (no exposure ⇒ no P&L; the shock is counted in `n_shocks_unmatched` on the TOTAL row) — rows assert consumed inputs, and nothing was consumed. |
| OQ-P3-6-6 | Sizing check: is v1 (declared shocks, linear) too thin for the LAST Wave-2 slice? | **Ship it as scoped** — the slice's value is the ENT-029/030 governance substrate (the roadmap's stated intent); v2 replay lands on top without schema change (the capture-first lesson from PA-0). Deferring AGAIN at the wave close remains legitimate if the close review prefers. |

## Part 5 — Implementation readiness gate

Ratify OQ-P3-6-1…6, then `p3_6_implementation_plan.md` sequences the build. Model/effort for
implementation: **Opus 4.8 · High** — the exemplar chain (P3-5/BT-1 shapes) covers every element;
the only novel surface is the definition/shock binder pair, which reuses the benchmark
header+membership protocol. Full 4-finder review at the end.

## Part 6 — Review dispositions + closure

**Review (OD-P3-6-J) — appended 2026-07-12.** A FULL 4-finder local max-effort review (kernel/
adjudication correctness; governance/temporal/RLS/snapshot; API/entitlement/cross-file/FE; cleanup/
conventions/sweep) over the complete 4804-line PR-scope diff, in lieu of the cloud ultrareview
(Claude cannot launch it). All hard invariants verified intact by the cleanup finder: symmetric
FORCE RLS ×3 (never hybrid), append-only trigger on `scenario_result` ONLY, `audit/service.py`
UNTOUCHED, `RISK.SCENARIO_CREATE` reserved-not-emitted, no new permission (reuses `risk.run`/
`risk.view`), no BYPASSRLS, snapshot+run+model binding present, shock pin precision matches the
`Numeric(20,12)` column. **10 findings; 7 folded, 3 deferred:**

1. **HIGH (correctness) — per-factor P&L quantize could detonate before the magnitude gate.** In
   `_compute`, `pnl = (exposure × shock).quantize(6dp)` ran BEFORE the `_MAX_RESULT_ABS` check;
   `Decimal.quantize` raises `InvalidOperation` once the result needs > 28 significant digits, and a
   below-gate exposure (< 1E21) times a `Numeric(20,12)` shock (< 1E8) can reach ~1E29 — so the
   unguarded quantize escaped as a raw 500 AFTER the run was RUNNING, defeating the very gate meant
   to yield a clean post-create FAILED (the BT-1/P3-8 echo-overflow class). **Folded:** gate the RAW
   product (Decimal multiply only rounds, never raises) BEFORE quantizing; a below-1E21 product then
   quantizes within precision. New boundary test `test_magnitude_overflow_is_committed_failed_not_raised`
   (exposure 1E15 × shock 1E7 = 1E22) proves the committed-FAILED path.
2. **HIGH (governance) — `verify_snapshot` had no SCENARIO branch, so every scenario snapshot
   reported drift.** `_reresolve_content` lacked a `COMPONENT_KIND_SCENARIO` case, so a pristine
   `SCENARIO_INPUT` snapshot fell through to `portfolio_content(resolve_portfolio(shock.id))` →
   `PortfolioNotVisible` → always `ok=False`. The AD-014 reproducibility/tamper check for the tenth
   governed number was inoperative. (The run itself was unaffected — it reads captured content
   directly.) **Folded:** added the branch (re-reads the shock FR row + its definition, TR-09-byte-
   stable) + `_resolve_scenario_shock_row`; new test `test_scenario_snapshot_verifies_and_survives_supersede`
   asserts `ok=True` on a pristine snapshot AND after a post-pin shock supersede.
3. **MED (governance) — pin `target_entity_type` mismatch.** `build_scenario_snapshot` pinned each
   `scenario_shock` row with `target_entity_type='scenario_definition'` while `target_entity_id` was
   the shock id — a type/id mismatch corrupting the provenance/lineage graph and precluding a correct
   reresolve branch. **Folded:** corrected to `'scenario_shock'` (the `benchmark_constituent` per-row
   precedent), which also unblocked finding 2's branch.
4. **MED (governance) — documented hard FK on `scenario_result.scenario_definition_id` did not
   exist.** The canonical doc (Step 9) asserted a hard FK, but the migration/ORM carried a bare GUID
   (no referential backstop, inconsistent with the var_backtest single-pointer precedent). **Folded:**
   added the FK + index to migration `0035` (+ `_IDENTIFIERS`) and the ORM `ForeignKey` (the EV id is
   stable across in-place re-versions, so the FK is always satisfiable; downgrade order already drops
   result→shock→definition). Doc is now accurate; PG-verified the constraint exists.
5. **MED (API) — a shock value beyond the column's capacity returned 500, not 422.** `_validate_shock_value`
   claimed "NO RANGE," but `shock_value` is `Numeric(20,12)` (8 integer digits); `|value| >= 1E8`
   overflowed at flush as a PG `DataError` (a NON-`IntegrityError` the write handler cannot map) → an
   opaque 500. **Folded:** the binder now refuses `|value| >= 1E8` as a governed 422 BEFORE the write
   (`_SHOCK_VALUE_ABS_MAX`); SQLite unit + endpoint 422 tests added.
6. **LOW (API) — misleading 409 detail on a duplicate scenario CODE.** The shared `_raise_scenario_write`
   emitted the shock-worded detail ("a current open shock already exists…") for a duplicate-definition-
   code collision (status 409 was correct; the message misdescribed the conflict). **Folded:** the raiser
   now discriminates by the colliding constraint (definition-code vs shock vs generic); endpoint test
   asserts the definition-worded detail.
7. **LOW (cleanup) — `_list_scenario_shocks` duplicated the binder's open-shock query.** The snapshot
   builder re-implemented `risk.scenario.list_scenario_shocks` verbatim (a self-documented "reader
   twin"), risking silent divergence between the pinned set and the live `/scenarios/{id}/shocks`
   list. **Folded:** deleted the local copy; the builder now calls the shared binder function (the
   function-local import carries no new cycle).

**Deferred (3 — recorded, not silently dropped):**

- **D-1 (cleanup) — extract the `resolve_*_run` / `_resolve_run` family to one shared helper.**
  `scenario_service._resolve_run` (COMPLETED-run pre-FK guard) and `resolve_scenario_run` (family
  read) are near-verbatim copies of the var_backtest/active_risk equivalents, differing only in the
  run-type constant + exception class. The clean form is a shared `calc/` helper taking an injectable
  `error=`/`not_visible=` (the `assert_portfolio_in_tenant(error=…)` precedent already in this diff).
- **D-2 (altitude) — generalize the FR-bitemporal membership protocol.** `risk/scenario.py`'s
  capture/supersede/correct/reconstruct skeleton (incl. the MD-H1 window-coherence guard) is a second
  full instance of `marketdata/proxy_mapping.py`'s; a parameterized FR-membership helper (by model,
  source constants, event family, summary fn) would collapse both.
- **Rationale for deferring D-1/D-2:** both are cross-slice extractions spanning 2–3 already-merged
  slices (proxy_mapping / var_backtest / active_risk); the P3-8 precedent shipped cross-cutting dedup
  as its OWN focused closeout pass rather than folding it into a feature PR, keeping the governed-
  number PR reviewable and not re-opening merged slices' validation surface. Recommend a dedicated
  **`RD-1` dedup slice** collapsing the `resolve_*_run` family (D-1) and the FR-membership protocol
  (D-2, larger — a design-scale extraction) across ALL families at once. The clean-code standing bar
  leans toward folding; this is a scope/altitude call for the user at the gate, not a file-ownership
  dodge.

**Post-fold validation (2026-07-12):** `make check` 1269 passed / 266 skipped (+4 new tests) +
secret-scan + docs-check; local-PG clean-schema 266 PG green; `alembic check` no drift; new FK
present; downgrade-base smoke clean + restore clean.

*(Final commit/PR refs appended at closeout.)*
