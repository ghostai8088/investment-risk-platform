# ES-1 Implementation Plan — the parametric Expected Shortfall leg (the build contract, Steps 0–7)

> Executes `es_1_decision_record.md` (OD-ES-1-A…G) once OQ-ES-1-1…7 are ratified **and BT-2 has
> merged**. Every step mirrors a shipped exemplar — PA-4 (a new model code dispatched through the
> SAME binder) is the structural template throughout. **NO migration**; NO permission/EVT/ENT mint;
> `audit/service.py` FROZEN; **no shipped NUMBER moves** (not "no shipped behaviour changes" — OD-E
> widens four families' registrable vocabulary and moves two shipped test probes; see Step 1).
>
> **RATIFIED 2026-07-15, OQ-ES-1-4 = sub-fork (i): widen the shared `VAR_Z_SCORES`.** The (ii)
> ES-only-table alternate is dead — every step below is now unconditional.
> Folded after the 3-verifier planning pass (record Part 5): 2 HIGH + 8 MEDIUM + 6 LOW.

## Step 0 — Branch + pre-checks (the stacking matters)

**BT-2 must be on `main` first.** `git rebase origin/main` this branch (it was cut from
`bt-2-impl`), then `es-1-impl` off it. Verify: alembic head `0040_var_estimate_age`; `make check`
green; the Grounding facts still hold (`ES_PARAMETRIC` reserved and in NO vocabulary tuple;
`var_value` NOT NULL; `uq_var_result_run_grain` = `(calculation_run_id, metric_type)`;
`METRIC_TYPES`'s only consumer is the backtest gate; **`ck_var_result_parametric_not_null` still
live and still ORM-invisible** — `0028_var_historical.py:43-48`, the record's Grounding correction).

## Step 1 — The constants (OD-A/B/E) — `risk/bootstrap.py`

- **`VAR_Z_SCORES` gains `"0.9750": "1.959963984540"`** (OQ-4 sub-fork (i), ratified). One shared
  table stays the design; no second z table is minted.
- **Blast radius — NOT "no change"** (the record's OD-E ⑴; both confirmed by execution):
  `VAR_Z_SCORES` is ONE table gating `risk.var.parametric`, `parametric_total` v1+v2 **and**
  `risk.var.historical`. **0.975 is the off-vocabulary probe two shipped tests use** — move both to
  `0.98` (free repo-wide) IN THIS STEP, don't discover them in the battery:
  `packages/shared-python/tests/test_var.py:363` (`raises(ValueError)`, else
  `ModelVersionConflictError` escapes) and `apps/backend/tests/test_var_endpoint.py:334`
  (`422`, else `409`). No test asserts the `sorted(VAR_Z_SCORES)` error text (verified — 6 sites,
  all safe).
- NEW `VAR_ES_MULTIPLIERS: dict[str, str]` mirroring `VAR_Z_SCORES`'s comment discipline verbatim:
  `0.9500 → 2.062712807507`, `0.9750 → 2.337802792201`, `0.9900 → 2.665214220346`. The comment MUST
  state the convention (`k_c = φ(Φ⁻¹(c))/(1−c)`, `c` = CONFIDENCE, zero-mean, loss-positive) — the
  recorded seam's under-specification is the defect this slice exists to close — and must NOT repeat
  the draft's "±1.4e-8" provenance (OD-B: the digits are pinned by Step 7's byte-exact test).
- `_CONFIDENCE_PATTERN` (`bootstrap.py:531` = `0\.[0-9]{1,6}`) admits `0.9750`, and the co-guard
  `len(text) > 6` at `:594`/`:796` does not bite (`len("0.9750") == 6`). Verified — no change needed.

## Step 2 — The kernel (OD-A) — `risk/es_kernel.py` (new, pure)

`compute_parametric_es(sigma: Decimal, *, es_multiplier: Decimal) -> Decimal` — deliberately
trivial (`es = k · σ`), which is the point: the tail arithmetic lives in the REGISTERED constant,
not in code. Follow `var_total_kernel`'s structural template (raw prec-50 out, binder quantizes,
one slugged error class). Guards: `sigma < 0` and `es_multiplier <= 0` refuse. Module docstring
states the convention + "NO quantile function, NO runtime normal function of any kind".

## Step 3 — The two registrars (OD-C/D) — `risk/bootstrap.py`

Mirror `register_var_parametric_total_model` (the closest exemplar):
- `ES_MODEL_CODE = "risk.var.parametric_es"`, v1, `var_parametric_es_v1.md`; declared identity =
  `(code_version, confidence_level, horizon_days, z)` reusing `declared_var_parameters` VERBATIM +
  a declared `es_multiplier=` assumption line whose value must equal `VAR_ES_MULTIPLIERS[c]`
  (identity, fail-closed at bind: a generically-minted version cannot declare a k that does not
  match its c — the `declared_appraisal_days` floor precedent).
- `ES_TOTAL_MODEL_CODE = "risk.var.parametric_es_total"`, v1, `var_parametric_es_v1.md`; identity
  additionally carries `appraisal_days` + `max_estimate_age_days` (reuse `declared_appraisal_days`
  verbatim). **`max_estimate_age_days` is fail-closed BY CONSTRUCTION on this code** — do NOT reuse
  `declared_max_estimate_age_days` bare: its absent-branch returns `None` = **ungated**, which is
  right for BT-2's grandfathered total-v1 and wrong here. No legitimate ungated ES-total version can
  ever exist (the code is born with the declaration), so an absent declaration must **refuse**, not
  bind ungated. Today that case is unreachable anyway — the generic mint is caught by the
  status-REGISTERED backstop (`model/service.py:394-399`) — so this costs nothing and makes the
  record's Part 3 item 6 true by construction rather than by an inherited backstop.
- Assumptions/limitations: the ES convention; the zero-mean/1-day carry; **the coherence statement
  written per the record's Part 2 correction** (robustness-if-normality-fails, NOT "VaR is
  incoherent"); the no-ES-backtest line justified by FRTB precedent (NOT non-elicitability); the
  ES-total leg additionally carries BT-2's smoothing-doctrine carry line.

## Step 4 — The binder branches (OD-C/D) — `risk/var_service.py`

Extend the dispatch (currently plain → total on `WrongModelVersionError`) to a third/fourth try:
plain → total → es → es_total. A four-deep try/except chain is past the clean-code bar, so extract
`_resolve_var_family(session, model_version_id, tenant) -> (version, family)` returning an enum-ish
family string — **ratified in OD-G**, not a Part-5.5 deviation (a fork the plan offers itself would
never fire the 5.5 trigger). Guarded by Step 7's byte-exact plain/total regression golden. Then:
- ES branch: reuse the ENTIRE existing adjudication (`_adjudicate_pins`), snapshot bind, provenance
  re-resolution; compute `σ` exactly as the plain path does, then `es = k·σ`; emit ONE row,
  `metric_type=METRIC_TYPE_ES_PARAMETRIC` (rename the `_RESERVED` constant — it is no longer
  reserved), `var_value=es`, `sigma=σ`, `z_score=z`, `residual_variance`/`estimate_age_days` NULL.
  **`z_score` is non-negotiable, not stylistic**: the live `ck_var_result_parametric_not_null` CHECK
  forces `z_score`+`sigma`+`covariance_run_id` non-NULL on every non-`VAR_HISTORICAL` row, and it is
  ORM-invisible ⇒ a NULLed `z_score` would pass the whole SQLite battery and fail only in PG.
- ES-total branch: the total path's σ_total (PA-4 machinery + BT-2's `_estimate_age_days` gate,
  both reused verbatim), then `es = k·σ_total`; `residual_variance` + `estimate_age_days` populated
  exactly as the total path does.
- The magnitude gate (`_MAX_RESULT_ABS = 1E22`, `var_service.py:113`, gated `:743`/`:796`) must run
  on **`es`, not on the σ or the VaR** — the concrete failure mode is an implementer gating
  `z·σ` while storing `k·σ`. Since `k_c > z_c` always, the band where **ES trips but VaR passes** is
  always non-empty and is wide, not a knife-edge (verifier-computed: `σ ∈ [4.85e21, 6.08e21)` at
  c=0.95 — 20% of the envelope; `[3.75e21, 4.30e21)` at c=0.99 — 13%). An ES landing there without
  the gate is a real PG-overflow 500, which is exactly what `:743`'s comment says the gate exists to
  prevent. **Inherit `:796`'s recorded discipline verbatim**: the gate is deliberately evaluated
  under the default prec-28 context so `abs()` rounds the prec-50 raw UP into the bound, closing the
  `[1E22−5E-7, 1E22)` window. **Test this boundary explicitly** (committed FAILED run, not a 500).
- The snapshot-predicate symmetry refusals must extend to the ES families (an ES-total model over a
  plain-predicate snapshot refuses, and vice versa) — mirror `:614-631`.

## Step 5 — API (OD-C/D) — `apps/backend/src/irp_backend/api/risk.py`

Two register endpoints mirroring `register_var_parametric_total` (`POST /risk/models/var-es`,
`/risk/models/var-es-total`). **`POST /risk/vars/runs` is UNCHANGED** — the binder dispatches on
the bound model. `VarRowOut` is UNCHANGED (the ES number rides `var_value`; `metric_type` is the
discriminator) — add a comment saying so. Error maps: existing classes only.

## Step 6 — Docs (OD-G) + the register accounting

- NEW `05_analytics_methodologies/var_parametric_es_v1.md` (both ES families): the formula WITH its
  convention block; the `k_c` table + how the constants were verified; the TCE guard (OD-A) so a
  future HS-ES leg inherits the right estimator; the coherence section carrying **both** Part-2
  corrections verbatim; the no-backtest justification (FRTB precedent, not non-elicitability); the
  ES-total leg's inherited BT-2 doctrine. Self-declare it immutable (the house pattern).
- **Do NOT edit** `var_parametric_v1.md` / `var_parametric_total_v1.md` / `_v2.md` (self-declared
  immutable) — **two** staleness classes, both discharged via the RTM/catalog + this record (the
  BT-2 precedent): their "ES deferred" lines, and `var_parametric_v1.md:46-47`'s enumerated z-table,
  which OD-E ⑶ makes under-enumerate its own family (a live consequence of the ratified sub-fork (i),
  not a hypothetical). (`..._total_v1.md:109` / `_v2.md:144` carry only the generic "z_α is a REGISTERED
  constant" line and `var_historical_v1.md` enumerates nothing — both verified clean, stay true.)
- **Vocabulary-drift sweep** (the PA-4 "doc/code mirror-drift" fold class; four
  sites assert the 2-entry vocabulary and go stale at Step 1): `bootstrap.py:587`
  (`register_var_model` docstring, "{0.95, 0.99}"), `bootstrap.py:759` (`_hs_window_floor`
  docstring, "BOTH v1 vocabulary confidences" — now three), and `api/risk.py:1063` + `:1195`
  ("(v1 vocabulary {0.95, 0.99}) — OD-P3-5-D").
- ENT-027 catalog row: `ES_PARAMETRIC` **reserved → REALIZED** (the 5th realization, no new id);
  note NO migration.
- RTM/backbone REQ-MKT-001: the ES leg DISCHARGED (historical/MC stay open; the REQ does not
  close). PA-4 Part-6 deferral 3: the ES-total-analogue half DISCHARGED, shrinkage/EWMA/
  calendar-aware still open.
- `risk/events.py`: rename `METRIC_TYPE_ES_PARAMETRIC_RESERVED` → `METRIC_TYPE_ES_PARAMETRIC`
  (verified trivial: one definition site at `:95`, zero consumers, not exported); update the
  P3-5-era reservation comment to a realization note; **leave ES OUT of `METRIC_TYPES`** and say why
  (OD-F) — the tuple's own BT-2 discipline clause demands a ratified slice to add a method, and
  ES-1 ratifies NOT adding it.
- `var_backtest_service.py:282` — the refusal message reads `unknown VaR metric_type {…!r}`. After
  ES-1, `ES_PARAMETRIC` is **known and deliberately excluded** (OD-F), so "unknown" would send a
  validator hunting a vocabulary bug instead of reading the ratified scope-out. Distinguish the two
  cases in the message.

## Step 7 — Tests + the BT-2 trigger

- **The constants are the subject** — and the draft's check could not pin them (verifier-confirmed,
  a MEDIUM fold). Feeding `z` in from `VAR_Z_SCORES` (already 12dp-rounded) injects
  `dk = −z·φ(z)·δz/(1−c)` ⇒ a **2.03e-12 noise floor at c=0.95, twice the 1e-12 quantum the test
  guards**. A single-digit typo in `k_0.99`'s last dp survives every tolerance that the true
  constant passes — *no tolerance works*, and the error is observable in stored output (`σ·1e-12` =
  one 6dp quantum at σ≈1e6, a scale this repo's own fixtures reach). **Copy the exemplar properly**
  (`test_var.py:300-314` derives z by its own bisection): invert Φ **in-test** by bisection on
  `math.erf`/`Decimal`, then assert **byte-exact, no tolerance** —
  `Decimal(VAR_ES_MULTIPLIERS[c]) == k_derived.quantize(Decimal("1E-12"), ROUND_HALF_UP)`. Add the
  **tail-integration leg** OD-B promises (`∫_{Φ⁻¹(c)}^∞ z·φ(z)dz / (1−c)`, no closed form) so the
  battery checks the *formula*, not just the transcription — two independent legs, like the z test.
  The z leg needs no new test: `0.9750` auto-passes the existing loop over `VAR_Z_SCORES`.
- **The invariant, at the level where it is actually exact** (OD-E ⑵ — the draft's row-level
  `== 1.004923991931` **cannot pass at any σ**: 0 hits in a 200,000-σ scan, because the two rows are
  quantized independently and the residuals don't cancel; `test_var.py:211-214` already learned this
  for the VaR leg). Split it: **(a) a constants-level unit test, no fixture at all** —
  `quantize(Decimal(VAR_ES_MULTIPLIERS["0.9750"]) / Decimal(VAR_Z_SCORES["0.9900"]), 1E-12)
  == Decimal("1.004923991931")` (verified to pass; this is what "pins the constants, not a fixture"
  always meant); **(b)** row-level, a **derived** bound per the PA-4 tolerance precedent —
  `|ES_q/VaR_q − k/z| ≤ (q/2)·(1 + k/z)/VaR_q`, `q = 1E-6` (verified: 3–6× headroom across σ ∈
  [7, 1e6]). Never a bare `==` on the ratio.
- End-to-end goldens: ES over the `test_var.py` chain (hand-derived `k·σ_p`, independently
  recomputed); ES-total over the PA-4 chain (`k·σ_total`, + `residual_variance`/`estimate_age_days`
  echoed); **`ES > VaR` for σ_p > 0** — strictly `ES ≥ VaR` with equality iff σ_p = 0: the repo
  ships fully-offsetting books (`test_var.py:236`, `:256` assert `sigma == var_value == 0.000000`),
  and any σ_p ≲ 2e-7 also ties at 6dp. Pin the σ_p = 0 tie as its own case.
- **The plain/total INVARIANCE regression** (the PA-4 precedent; guards OD-G's central claim now
  that the dispatch is refactored): an existing plain and an existing total golden are **byte-exact
  unmoved** after the binder gains two branches.
- **The convention golden** (OD-A, free and genuinely portfolio-independent): `ES_c = VaR_99` at
  `c = 0.974232` — this pins the CONFIDENCE-vs-tail-probability reading directly, which nothing else
  does; the `k·σ` goldens would all still pass if the convention comment silently flipped.
- Refusals: off-vocabulary confidence — **the probe is now `0.98`, not `0.975`** (Step 1); a declared
  `es_multiplier` that does not match its declared `c` (the identity gate); the ES-total
  **absent-declaration refusal** (Step 3, fail-closed by construction); the predicate-symmetry
  refusals; the magnitude boundary (`k·σ` over the envelope ⇒ committed FAILED, not a 500); the
  ES-total staleness gate still bites (BT-2's gate reused).
- **Authz on the two new endpoints** (OD-G rests on "no new permission — `risk.run`/`risk.view`
  reused" with nothing behind it): the per-family shipped precedent is
  `test_var_endpoint.py:343 test_deny_by_default_and_view_only_cannot_run` — mirror it for both.
- **The backtest fence**: a `var_backtest` run over an ES run REFUSES (`ES_PARAMETRIC` ∉
  `METRIC_TYPES`) — pin it, since OD-F is a deliberate omission and a future maintainer must not
  "complete the vocabulary".
- **Pay BT-2's fired trigger — BOTH halves.** Its recorded gap is *"no PG leg for the age column
  **and no API assertion of `estimate_age_days`**"*; the draft paid only the first. Extend
  `test_var_total_pg.py` with the `estimate_age_days` PG leg **and** add the API-read assertion.
- **The ES rows' own PG leg is not optional this slice** — `ck_var_result_parametric_not_null` is
  ORM-invisible, so an ES row's CHECK compliance is provable *only* in PG. Include an ES and an
  ES-total row round-trip under RLS. No new CI step if no new file; if a new `*_pg.py` lands, wire
  it the SAME commit (the recurring lesson). Per the VW-1 grant-leakage lesson, verify the fixture
  grant lists cover every table these suites touch — CI runs the PG files one per step.
- Migration-head tests: **unchanged at `0040`** — the no-new-migration claim is pinned by the
  synthetic guard (still asserting no-`0041`), **not** by `alembic check`, which only detects
  ORM↔schema drift and would not notice a stray revision file.

## Then

Full battery (`make check` + local-PG schema-reset AND dirty double-run + `alembic check` showing no
drift + the synthetic guard showing no new revision + downgrade smoke) → 4-finder review (numeric on
`k_c` + the invariant;
adversarial on the vocabulary extension's blast radius; doctrine on the two Part-2 corrections
surviving into the shipped referent; scope fence) → fold → push → hand the PR to the user → CI
green → merge → closeout (roadmap row + amendment log **in the impl/closeout PR** — the recurring
lesson) → **the Wave-5 close review** (ES-1 is the last slice).
