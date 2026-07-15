# MG-1 Implementation Plan — materiality + the first validation campaign (the build contract, Steps 0–8)

> Executes `mg_1_decision_record.md` (OD-MG-1-A…H) once OQ-MG-1-1…7 are ratified. Exemplars: VW-1
> (the validation machinery + the R-07/EVT governance shape), `update_portfolio` (the EV-head-update
> verb), RD-3 (the parse-adoption ride-along form). **NO migration**; NO new permission/ENT; ONE
> audit-code mint (`MODEL.TIER_ASSIGN`); `audit/service.py` FROZEN; the OQ-W5C-5 closure-stamp
> checklist applies at close.

## Step 0 — Branch + pre-checks

`mg-1-impl` off `main` (post-planning-merge). Verify: alembic head `0040_var_estimate_age` (and it
must STILL be the head at close — the synthetic no-`0041` guard stays true); `make check` green;
the Grounding facts hold (`model.tier` String(20) nullable with no post-registration write path;
zero CHECKs on the model tables; `overdue` consumed at exactly one read site; the seam already
SELECTs the Model head).

## Step 1 — Vocabularies + the cadence policy (OD-A/D) — `model/models.py` + the policy doc

- `MODEL_TIERS = frozenset({"TIER_1", "TIER_2", "TIER_3"})`, `MATERIALITY_RATINGS` /
  `COMPLEXITY_RATINGS = frozenset({"HIGH", "MEDIUM", "LOW"})` — beside the validation vocab
  frozensets, same comment discipline. **Service-layer only, deliberately no DB CHECK** (the
  MG-01 genericity note at `models.py:11-13` — cite it).
- `derive_model_tier(materiality, complexity) -> str` — the ratified matrix as a pure function
  (TIER_1 = HIGH materiality; TIER_2 = MEDIUM materiality or LOW+HIGH-complexity; TIER_3 = rest),
  unit-tested over all 9 cells.
- `MODEL_TIER_REVIEW_MAX_DAYS = {"TIER_1": 365, "TIER_2": 730, "TIER_3": 1095}` — the comment MUST
  carry the honest sourcing (365 anchored EGIM MR §4.2 ¶90 + SS1/23 P4.5(b); **730/1095 HOUSE
  POLICY — no citable source exists**, the census's decisive negative fact) and the fail-safe rule
  (untiered ⇒ the TIER_1 bound — VW-1's ratified posture, continued).
- `07_model_governance/model_governance_independence_policy.md`: OD-032 + OD-033 → **CLOSED** (this
  ratification), the tier rubric + cadence table recorded with the same honest labels; a NEW
  use-before-validation section ADDED per OD-E/G (the policy doc contains NO existing exception
  text — the verifier's grep; `:30-34` is the OD-033 note): per-model + time-boxed in the demo
  tenant, the blanket default disclosed as the proportionality-anchored POC posture. The F3 text
  that DOES exist gets corrected where it lives: the RTM REQ-MDG-003 row, the CTRL-022 row, and
  the VW-1 record's posture notes (dated, additive).

## Step 2 — `assign_model_tier` (OD-B/C) — `model/service.py` + API

- New verb, the `update_portfolio` EV-head precedent: resolve the head tenant-scoped; human-only
  actor (the BR-15 mirror, same message discipline as `record_validation`); vocab-guard both
  ratings; derive tier; update `model.tier` + `record_version` bump; emit **`MODEL.TIER_ASSIGN`**
  with `before`/`after` + `{materiality_rating, complexity_rating, rationale}` in the payload
  (rationale: required, non-empty — an unexplained materiality judgment is not a judgment).
- **Idempotency/no-op**: re-assigning the identical ratings is a no-op (no version bump, no event)
  — the EV-update convention; a CHANGED assignment is a fresh event (the history lives in the
  hash-chained audit trail, which is where OQ-1's sub-fork (i) put it).
- API: `POST /models/{model_id}/tier`, gated on **`model.validate`** (reuse — `_require_validate`
  exists from VW-1). **CLOSE the 1L register-time write**: remove `RegisterModelIn.tier` + the
  passthrough (`api/models.py:52,125`) and the `register_model` `tier` kwarg. **Disclosed blast
  radius** (verifier): `test_model_registry.py:316` passes `tier=` and gets edited;
  `resolve_or_register_model` callers unaffected (none pass it — census). **The ratified API
  shape: a `tier` key in the register body is IGNORED-AND-NOT-STAMPED** (Pydantic's default for a
  removed field; no blanket `extra="forbid"`) — the load-bearing invariant is "the 1L cannot set
  tier", pinned by a test asserting the created head has `tier=NULL` despite `tier` in the body.
  The ORM column keeps its name; only the write paths move.
- EVT mint: the taxonomy row for `MODEL.TIER_ASSIGN` (the VW-1 `.VALIDATE` row as the template),
  citing this record as the mint authority. `audit/service.py` untouched (caller-side string).

## Step 3 — The cadence guard + the EXCEPTION type (OD-D/E) — `model/validation.py`

- `record_validation` gains: (a) the **cadence bound** — for approving outcomes,
  `next_review_due <= today + MODEL_TIER_REVIEW_MAX_DAYS[tier or "TIER_1"]` — **this costs
  ONE NEW head SELECT**: `record_validation`'s guard path resolves only the ModelVersion, never
  the head (the verifier killed the draft's "zero new queries" claim — true only at the BIND
  seam); refusal names the tier + the bound; (b)
  **`VALIDATION_TYPE_EXCEPTION = "EXCEPTION"`** added to `VALIDATION_TYPES`, with the two NEW
  fail-closed guards: an EXCEPTION requires **zero prior non-EXCEPTION rows** for the version
  (else 422 — a validated model revalidates, never excepts) and **no latest-REJECTED** (else 422 —
  the gate cannot be laundered); an EXCEPTION's outcome MUST be `APPROVED_WITH_CONDITIONS` (the
  conditions are the SR 26-2 §V controls + justification; the existing blur rule already forces
  `next_review_due` = the expiry).
- The docstring's citation block carries the OD-E split verbatim (SR 26-2 elements; SS1/23
  "temporary" + grant semantics) — the doctrine finder will check it against the extracts.

## Step 4 — The seam teeth (OD-F) — `model/service.py` + every run endpoint

- `assert_model_version_of`, after the REJECTED check: if `latest_validation` is an EXCEPTION row
  with `next_review_due < today` ⇒ raise new **`ExpiredModelExceptionError`** (message names the
  expiry + the re-grant path). Versions with NO rows keep binding (the disclosed default — the
  entire existing test corpus must stay green with ZERO test edits from this step).
- **Map the new error at every run endpoint** — the VW-1 HIGH lesson applied at design time: all
  9 risk + 3 perf except-tuples AND both `_ERROR_MAP`s → 422. End-to-end tests through ONE real
  risk AND ONE real perf endpoint (the VW-1 fold's exact shape).
- **Zero new PG-fixture grants** (the seam reads `model` + `model_validation`, both already
  granted since VW-1) — assert this claim in the plan review rather than discover it in CI.

## Step 5 — The campaign runner (OD-G) — `scripts/run_demo_campaign.py` + `irp_shared/demo/`

- A governed runner driving the REAL service layer against the **demo tenant** (a fixed uuid5
  label, NOT the synthetic tenant — AD-017 stays intact): (1) reference + market data (currencies,
  instruments, a marked book, CURRENCY factors + returns spanning the covariance window); (2) the
  2L `app_user` **named for the user** + tenant-local role wiring (the `test_model_endpoint.py:41-50`
  pattern); (3) register **ALL 16 model codes** (the verifier's HIGH: tier assignment and EXCEPTION
  filing both require a registered head/version — a 6-code runner cannot produce the 16-code end
  state; the non-flagship 10 register via their family registrars, no evidence chains needed);
  (4) the evidence chain, **per flagship model** — exposure → factor exposure → covariance →
  forecast series for EACH of plain/HS VaR (every dossier cites its OWN model's runs) → the PM-1
  return series → a **real BT-1 backtest run**; then the **marks → desmooth → PA-3 OLS estimate →
  promote** leg (REQUIRED for BT-2 — and it IS the estimate-seam ride-along's chain, built once,
  living in the demo tenant) → **total-v2 forecast series → a real BT-2 backtest run** → ES +
  ES-total runs over the same books (short honest series throughout; Kupiec-only, Basel zone
  correctly absent — each dossier states its N); (5) tier-assign all 16 codes per the ratified
  rubric; (6) file the 6 INITIAL validations from the dossiers + the 10 EXCEPTIONs (expiry per
  tier bound).
- **Idempotency**: check-first — a demo tenant with models refuses re-seeding (no partial re-runs;
  the no-op-sentinel lesson from RD-3, applied as refuse-not-skip).
- **The dossiers live in the plan** (below, Step 5.5) — the user's OQ-6 ratification covers them;
  the runner only transcribes.
- A PG-backed test executes the runner end-to-end and asserts the end state: 16 registered codes,
  6 with an INITIAL validation (outcomes as ratified), 10 with an unexpired EXCEPTION, every
  validation's evidence runs COMPLETED + in-tenant, `MODEL.TIER_ASSIGN` events = 16.

### Step 5.5 — The dossier map (ratified via OQ-MG-1-6)

| Code | Tier (M×C) | Outcome | The condition / key findings (from the REGISTERED limitations) |
|---|---|---|---|
| `risk.var.parametric` | TIER_1 (HIGH×MED) | **AWC** | CURRENCY-only universe + specific-risk=0 (**remediation = FL-1/MF-1; TRIGGERED re-validation at MF-1**); normality + 1-day recorded as accepted posture |
| `risk.var.historical` | TIER_1 (HIGH×MED) | **AWC** | Same CURRENCY-only condition; window-adequacy floor noted as governed |
| `risk.var.parametric_total` v2 | TIER_1 (HIGH×HIGH) | **AWC** | CURRENCY-only + the BT-2 smoothing doctrine READ RULE re-affirmed; the v1 ungated grandfather NOTED with VW-1's REJECT named as its sunset lever |
| `risk.var.parametric_es` | TIER_1 (HIGH×MED) | **AWC** | Rides the parametric condition verbatim (a σ-multiple is as honest as its σ); the non-reconciling-row limitation cited |
| `risk.var.parametric_es_total` | TIER_1 (HIGH×HIGH) | **AWC** | The total condition verbatim + the ES rider |
| `risk.var_backtest` | TIER_2 (MED×MED) | **APPROVED** | The doctrine limitations (two-sided appraisal pathology) are the model's own honesty text, not defects in it; evidence = its executed runs |
| The remaining 10 codes | per rubric (mostly TIER_2/3) | **EXCEPTION** | AWC shape; justification = POC sequencing; controls = the registered limitations + backtest monitoring where applicable; expiry = tier bound |

Every AWC's `next_review_due` ≤ the TIER_1 bound; every dossier discloses the person-level
non-independence line (Part 3 item 1) verbatim.

## Step 6 — Ride-alongs (OD-H)

- **The NaN fix**: `parse_strict_decimal` at `benchmark_relative_service.py:303` (identical call
  shape to the guarded `:257`); regression tests: bench-side NaN ⇒ pre-create 422 + zero orphan
  (`assert_no_running_orphan`; **NaN is the ONLY orphaning input — unparseable garbage is ALREADY
  a 422 today**, verifier-executed), bench-side Infinity ⇒ 422 (**the stated delta**: previously
  a correct post-create FAILED — the class change recorded, matching the portfolio side);
  the RD-3 skip-list entry + the Wave-5-close register both stamped PAID.
- **The estimate-seam test**: new `test_total_var_real_estimate_chain.py` (or a section in
  `test_var_total.py` — implementer's call, note it in 5.5): real marks → real desmooth → real
  PA-3 OLS estimate → promote → total-VaR consume; assert the decomposition against the RUN's own
  σ_e (recomputed independently from the estimate row, NOT hand-fixed); date-alignment + staleness
  + same-currency constraints per the census; TD-1 realism.
- **All FOURTEEN stale bootstrap limitation constants** updated (11 risk + 3 perf —
  verifier-counted; the two ES families already carry ES-1's corrected wording): "recorded,
  non-enforcing until a 2L validator records an outcome (VW-1)". Not just `VAR_LIMITATIONS`
  row (f) — the draft under-scoped its own sweep.

## Step 7 — Docs + register accounting

- Policy doc per Step 1; the taxonomy row (Step 2); `entitlement_sod_model.md` gains the
  tier-assign-is-2L note (no SoD row change — no new permission); RTM: REQ-MDG-002 → In-Progress
  (tiering shipped; the H-02 Tier-1 approval gate stays open), REQ-MDG-003 row updated (cadence
  closed, campaign executed); CTRL-022 text refreshed; `current_state.md` + roadmap row + amendment
  log **per the OQ-W5C-5 checklist, all six items, at the closeout**.

## Step 8 — Tests (beyond those named above)

- The 9-cell matrix; vocab refusals (bad rating, bad tier never writable); the human-only +
  rationale-required guards; idempotent re-assign no-op vs changed-assign event; the closed 1L
  write path (register with `tier` in the body ⇒ 422/ignored per the ratified shape, pinned).
- Cadence: bound enforced per tier; **untiered ⇒ TIER_1 bound** (the fail-safe pinned); boundary
  (due == today+365 passes, +366 refuses); REJECTED still refuses a `next_review_due` (unchanged).
- EXCEPTION: shape guards (must be AWC; expiry required); **the two laundering guards** (prior
  validation ⇒ refuse; latest-REJECTED ⇒ refuse) — adversarially, via the generic paths;
  expired-exception bind refusal end-to-end (risk + perf endpoints, 422 not 500); unexpired binds;
  no-rows-at-all still binds (the corpus-safety invariant — this test IS the fence).
- **The `MODEL.TIER_ASSIGN` payload shape** — `{materiality_rating, complexity_rating, rationale,
  before, after}` asserted on the emitted event (the audit payload is the ratings' ONLY durable
  home, so this assertion is load-bearing, not cosmetic).
- **The discharge path the refusal message advertises**: expired EXCEPTION → refused bind → a
  FRESH exception (or a real validation) → binds again.
- The campaign end-state test (Step 5); PG legs for the seam gate under RLS.

## Then

Full battery (`make check` + local-PG fresh AND dirty double-run + `alembic check` + the synthetic
no-`0041` guard + downgrade smoke) → **4-finder review** (adversarial on the seam gate + exception
guards; doctrine on the citation surface — the heaviest, every quote vs the census extracts;
campaign-content on dossiers-vs-registered-limitations; scope fence) → fold → push → PR → CI green
→ merge → **the OQ-W5C-5 closure checklist** → FL-1 planning.
