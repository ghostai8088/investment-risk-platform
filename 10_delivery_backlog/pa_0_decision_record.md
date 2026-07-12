# PA-0 Decision Record — private-asset foundations (Wave-2 slice 4)

> **Status: RATIFIED 2026-07-11** — OQ-PA-0-1…8 approved as recommended (user: "Approved").
> Drafted 2026-07-11 against HEAD `df92a9c`
> (BT-1 fully closed). Scope: the thesis-destination's FIRST slice (`01_product_strategy/
> differentiation_thesis.md` §2.1) — realize **ENT-019 `proxy_mapping`** (private instrument →
> public risk-factor proxy weights, captured input) + a documented private-asset `asset_class`
> convention + the **desmoothing/proxy methodology decision** (which model family a FOLLOW-ON
> governed-number slice, provisionally named **PA-1**, will implement). NO governed calculation in
> THIS slice — captured input only, the P2-7 precedent. Implementation gated separately.

## Part 1 — Decisions at a glance (OD-PA-0-A…J)

| # | Decision | Choice (recommended) |
|---|---|---|
| OD-PA-0-A | **Capture-first split (the headline call).** | PA-0 ships ONLY captured-input foundations: ENT-019 `proxy_mapping` + the asset-class convention + this decision record's desmoothing-model choice (on paper, for a LATER slice to implement). NO `calculation_run`/`model_version`/snapshot/desmoothed governed number in PA-0 — mirrors the P2-7 → P3-7 precedent (P2-7 captured `benchmark_return`; P3-7 consumed it two slices later). The roadmap itself flagged this ("Its planning may split capture-first"). |
| OD-PA-0-B | Private-asset representation | **NO new Instrument/Position/Valuation schema.** A private asset IS an `instrument` (asset_class ∈ a documented, non-enforced convention: `PRIVATE_EQUITY` / `PRIVATE_CREDIT` / `REAL_ESTATE` / `INFRASTRUCTURE` / `VENTURE_CAPITAL` — `asset_class` is already a free String(50), no CHECK); its periodic appraised NAV/unit mark IS a `valuation` row (the SAME captured-mark infrastructure every instrument uses — quarterly cadence is a convention, not a schema constraint). This is the whole "appraisal/NAV series" leg of the roadmap wording — **already built**, nothing to capture that doesn't exist. |
| OD-PA-0-C | `proxy_mapping` shape | **FR bitemporal** (the `benchmark_return`/`factor_return` precedent — a governed number will later snapshot-pin it): grain `(tenant, private_instrument_id, factor_id, valid_from)`; columns `weight` (signed Decimal, the loading on that public factor) + `mapping_method` (a recorded free-text/controlled label: e.g. `MANUAL`/`PEER_GROUP`/`REGRESSION` — HOW the weight was derived; v1 = captured, not computed). **Multiple rows per instrument** (a blended proxy across several public factors is normal — e.g. a buyout fund proxied by an equity factor + a credit-spread factor). Effective-dated (not append-only): a proxy weight is a judgment call that gets revisited — supersede mints a new FR version, never an UPDATE (the P2-7/benchmark precedent). |
| OD-PA-0-D | Weights sum to 1? | **NOT enforced.** A partial proxy (weights summing to <1, the residual left as unmodeled idiosyncratic/private risk) is a legitimate, common choice — forcing a sum-to-1 constraint would silently misrepresent under-proxied assets as fully explained. The residual-risk gap is a recorded first-class limitation, not a computed number in v1. |
| OD-PA-0-E | Permission | **REUSE `marketdata.view`/`marketdata.ingest`** (the factor/benchmark precedent — P2-2/P2-7 both reused this pair for a new captured-input entity). NO new permission mint. |
| OD-PA-0-F | Capital calls / distributions / commitments | **OUT OF SCOPE for PA-0** — not in the roadmap's 3-item PA-0 deliverable list. `transaction.txn_type` is already an unconstrained plain string (zero-migration to add `CAPITAL_CALL`/`DISTRIBUTION` later), and PM-1 already recorded money-weighted return/IRR as deferred to "PA-0" in its limitations — that deferral is hereby REDIRECTED to **PA-1** (the same slice that will consume capital-call cash flows for IRR, since money-weighted return needs exactly that cash-flow shape). Recorded here so the PM-1 deferral doesn't silently vanish. |
| OD-PA-0-G | Desmoothing model family (v1 choice, for PA-1) | **Geltner (1991/1993) first-order autoregressive unsmoothing** as the v1 declared model: observed appraisal return `r_a,t = α·r_t + (1−α)·r_a,t−1` inverted to `r_t = (r_a,t − (1−α)·r_a,t−1) / α`, with `α` (the "speed of adjustment", 0 < α ≤ 1) a DECLARED parameter (estimated offline from the autocorrelation of the captured NAV series — NOT a runtime regression in v1, the VAR-z-score / Kupiec-critical precedent of declared-not-computed constants). Simplest, most-cited, closed-form; Getmansky-Lo-Makarov (multi-lag MA(q)) and the dynamic/time-varying-beta family are RECORDED v2 declared variants, not built in v1. |
| OD-PA-0-H | Proxy mapping projects onto WHICH factor family | **CURRENCY-family factors only in v1** (the same factor family every governed number to date consumes — factor_exposure/covariance/VaR/active-risk all key off `factor_family='CURRENCY'`). A style/sector/rate factor family for private assets is a recorded v2 extension, not a v1 gap — it mirrors the platform's existing single-family scope everywhere else. |
| OD-PA-0-I | Rule-6 external research | Geltner 1991/1993 (real estate appraisal-smoothing, the single-lag AR(1) unsmoothing filter — well-established, high confidence); Getmansky, Lo & Makarov 2004 (*J. Financial Economics* 74(3), the hedge-fund/illiquid-asset MA(q) generalization, θ-weighted with Σθ=1); **Okunev-White — CITATION UNVERIFIED, flagged for confirmation before PA-1 methodology sign-off** (the substance recorded is a dynamic/time-varying-exposure desmoothing approach, contrasted with Geltner's static single lag; I do not have high confidence in the exact paper title/year and will NOT assert one I haven't verified — this is an honesty flag, not a design gap, since PA-0 doesn't implement any of the three). |
| OD-PA-0-J | Review + flow | Given the SMALL blast radius (one new FR table, captured-input only, no calculation/permission/audit-mint), a lighter local review (not the full 4-finder governed-number battery) is proportionate — the P2-7 precedent (a 6-finder pass, but P2-7 shipped TWO tables + DQ gates; PA-0 ships one). Unreduced local gates still apply in full (`make check` incl. `ruff format --check`, full local-PG + downgrade smoke, fe-check if any FE surface is touched). PR flow; Claude pushes, USER merges. |

## Part 2 — External benchmark research (roadmap Part 4 rule 6; sources checked 2026-07-11)

- **Geltner, D. (1991)**, "Smoothing in Appraisal-Based Returns", *Journal of Real Estate Finance
  and Economics* 4(3); **Geltner, D. (1993)**, "Estimating Market Values from Appraised Values
  without Assuming an Efficient Market", *Journal of Real Estate Research* 8(3). The foundational
  appraisal-smoothing model: observed (appraisal-based) returns are a weighted blend of the true
  (unobserved) current-period return and the PRIOR appraisal-based return — `r_a,t = α·r_t +
  (1−α)·r_a,t−1`. Inverting recovers the desmoothed/"true" return series; `α` (interpreted as the
  fraction of true information incorporated per period) is typically estimated from the
  first-order autocorrelation of the observed series. This is the most widely cited desmoothing
  filter in the real-estate/private-market literature and the natural v1 starting point (closed
  form, one declared parameter).
- **Getmansky, M., Lo, A. W., & Makarov, I. (2004)**, "An econometric model of serial correlation
  and illiquidity in hedge fund returns", *Journal of Financial Economics* 74(3), pp. 529-609.
  Generalizes the single-lag Geltner filter to a `k`-lag moving-average smoothing profile:
  `R_t^observed = θ_0·R_t + θ_1·R_{t-1} + ... + θ_k·R_{t-k}`, with `Σθ_j = 1`, `θ_j ≥ 0`; recovers
  true returns via the MA-profile inversion and produces a smoothing-adjusted ("unsmoothed")
  volatility estimate — the standard reference for hedge-fund and other illiquid-strategy return
  smoothing, and the natural v2 extension once a single lag proves insufficient.
- **Okunev-White** — the substance I intend to record is a DYNAMIC / time-varying exposure
  (switching-regression or Kalman-filter-style) desmoothing approach, contrasted with Geltner's
  STATIC single-lag coefficient — relevant because Okunev-White is the name already carried in this
  repo's ratified Wave-2 roadmap entry (`delivery_roadmap.md` Part 2.5, PA-0 row) from an earlier
  planning pass. **I do not have high enough confidence in the exact paper (title/year/venue) to
  cite it precisely here, and I am NOT going to assert a citation I haven't verified.** Flagged
  explicitly for the user or a literature check before PA-1's methodology document is written —
  this is an honesty gap in sourcing, not a scope gap in PA-0 (PA-0 implements none of the three
  models; it only records the v1/v2 disposition for PA-1 to build against).

## Part 3 — Limitations carried forward + out of scope (recorded)

1. **No desmoothing calculation ships in PA-0.** The captured NAV/appraisal series (via existing
   `valuation` rows) is real from PA-0 onward; the unsmoothing TRANSFORM is PA-1's governed number.
2. **No capital-call/distribution/commitment tracking or money-weighted return/IRR** — redirected
   from PM-1's deferral to PA-1 (OD-F).
3. **Proxy weights are CAPTURED (a governance judgment call), not COMPUTED** (no regression engine
   in v1) — `mapping_method` records provenance; a regression-derived weight is a v2 extension.
4. **No sum-to-1 enforcement** — partial proxies are honest, not a defect (OD-D).
5. **CURRENCY-family factors only** (OD-H) — the platform's existing single-family scope, not a
   private-asset-specific gap.
6. **Okunev-White citation unverified** (OD-I) — recorded honestly, to be resolved before PA-1.

## Part 4 — Open decisions (OQ-PA-0-1…8) — pending ratification

- **OQ-1** — The capture-first split itself: PA-0 = captured foundations only, no governed number. *(Recommended: yes — OD-A.)*
- **OQ-2** — No new Instrument/Position/Valuation schema; a private asset is an ordinary instrument with a documented `asset_class` convention. *(Recommended: yes — OD-B.)*
- **OQ-3** — `proxy_mapping` FR bitemporal, multi-row-per-instrument, effective-dated. *(Recommended: yes — OD-C.)*
- **OQ-4** — No sum-to-1 enforcement on proxy weights. *(Recommended: yes — OD-D.)*
- **OQ-5** — REUSE `marketdata.view`/`marketdata.ingest` — no new permission. *(Recommended: yes — OD-E.)*
- **OQ-6** — Capital calls/distributions/IRR explicitly redirected to PA-1, not PA-0. *(Recommended: yes — OD-F.)*
- **OQ-7** — Geltner AR(1) as PA-1's v1 desmoothing model (recorded now, built later); Getmansky-Lo-Makarov + the dynamic-beta family as recorded v2s. *(Recommended: yes — OD-G.)*
- **OQ-8** — Review mode: a proportionate lighter local review (not the full 4-finder governed-number battery), given the small blast radius (one FR table, captured input only). *(Recommended: yes — OD-J; the user's call at implementation time — either satisfies proportionate diligence.)*

## Part 5 — Implementation readiness gate

Implementation starts ONLY on explicit direction after OQ ratification, against
`pa_0_implementation_plan.md` (a build contract scoped to the capture-first slice: migration +
capture/supersede/reconstruct functions + methodology-adjacent docs — NO binder, NO snapshot
builder, NO calculation_run, since there is no governed number in this slice). Model/effort
recommendation for the implementation: **Opus 4.8 / high** — templated on the P2-7 FR-capture
exemplar (`benchmark_level`/`benchmark_return`), not novel design; the honest external-research gap
(OD-I) means PA-1's eventual methodology work is the genuinely novel slice, not this one.

## Part 6 — Review dispositions + closure (appended at closeout, 2026-07-11)

**CLOSED.** Planning `07e5d6a` merged via **PR #7** (`7a422aa`); implementation `c9d41a7` merged via
**PR #8** (`ad3d3fe`), CI green — merged in the correct order (planning first) after the
implementation branch was rebased onto the merged planning docs. Migration `0034`; validation:
`make check` 1191 / local PG 7/7 / downgrade smoke 0034↔0033 / fe-check 52 (no FE surface added —
the captured-input precedent).

**Review (OQ-8):** a PROPORTIONATE 2-finder local review (service+FR-protocol+persistence;
API+docs-sync+conventions) — right-sized for a captured-input slice, per the ratified OQ. All hard
invariants verified intact (frozen `audit/service.py` + `entitlement/bootstrap.py` untouched; the
`MARKET.PROXY_MAPPING_*` codes are caller-side constants, never an audit-service mint; no
BYPASSRLS; the scope fence AST-verified — no `calc`/`model`/`snapshot` import). **No HIGH bugs;
4 folds + 2 deferrals:**

1. **Fold — CORRECTION audit `action` convention.** The correction event carried
   `action="update"` where all five sibling FR-correction emitters (fx/price/curve/benchmark/
   factor) use `action="correct"` — an `action == "correct"` audit query would silently omit every
   proxy restatement. Fixed + the grain test now pins the action.
2. **Fold — the CURRENCY-family v1 scope (OD-PA-0-H) was doc-stated but UNGATED.** A non-CURRENCY
   factor (e.g. a STYLE factor) was silently accepted at capture. Now ENFORCED fail-closed in
   `_resolve_factor_id` (a style/sector/rate proxy family is a recorded v2 extension) + a refusal
   test; the ENT-019 registry row updated to say "ENFORCED".
3. **Fold — asymmetric correction audit payload.** `before_value` carried the old weight but
   `after_value` omitted the new one; an auditor could not answer "corrected to WHAT?" from the
   event alone. Now symmetric (a single scalar, not the bulk payload the DC-2 rule guards).
4. **Fold — dead `order_by` in `reconstruct_proxy_mapping_as_of`.** Paired with
   `scalar_one_or_none()` the ordering could never act (raises on >1), and it diverged from the
   `reconstruct_factor_return_as_of` precedent, implying a pick-latest semantic the code cannot
   deliver. Removed; a comment pins the fail-loud invariant.

**Deferred, with recorded reasons (both precedent-consistent, NOT PA-0 regressions):**
- **A — supersede does not guard `effective_at < prior.valid_from`.** A backdated revision below
  the original capture instant would invert the prior version's valid window and shadow it from
  reconstruction. IDENTICAL to the unguarded `factor_return`/`benchmark_return` supersede —
  guarding only proxy_mapping would break family parity. Trigger: a family-wide FR
  window-coherence guard pass (all six FR series at once), or the first observed backdating
  incident.
- **B — a duplicate-open-head capture returns HTTP 500, not 409.** `POST /proxy-mappings` twice
  for the same (instrument, factor) trips the partial-unique index as an uncaught
  `IntegrityError`. Shared by EVERY captured-entity capture endpoint in the marketdata family — a
  cross-cutting `IntegrityError → 409` mapping pass, not a one-entity patch. Trigger: the next
  marketdata-family hardening slice (natural companion to the BT-1 Part-6 deferral B, the
  registrar-concurrency race).

**Bugs caught mid-build (before the review, worth the record):** a `Decimal` in the audit
`before_value` crashed JSON serialization at flush (`_json_safe` extended to stringify Decimal —
the correction path was the only emitter passing a raw Decimal); the PG supersede test read zero
rows post-commit because the RLS GUC is transaction-scoped (`SET LOCAL`) — re-arm after commit.

**Standing items for PA-1 (carried from Parts 1-4, unchanged):** the Geltner AR(1) v1 desmoothing
model (declared-α); the **Okunev-White citation remains UNVERIFIED** (OD-PA-0-I — must be resolved
before PA-1's methodology doc); capital calls/distributions/money-weighted IRR (OD-PA-0-F);
regression-derived weights (v2).

**[RESOLUTION, 2026-07-12 — the OD-PA-0-I flag is DISCHARGED at PA-1 planning:** Okunev-White
VERIFIED as Okunev & White (Oct 2003), "Hedge Fund Risk Factors and Value at Risk of Credit Trading
Strategies", SSRN 460641 (published: Loudon, Okunev & White, *J. Fixed Income* 16(2), 2006). The
tentative substance recorded above ("dynamic/time-varying-exposure, Kalman-style") was **incorrect**
— the method is an ITERATIVE HIGHER-ORDER extension of the Geltner filter. See
`pa_1_decision_record.md` OD-PA-1-J for the corrected v2 register; the flag worked as designed (the
unverified claim was quarantined and never entered a methodology doc).**]**
