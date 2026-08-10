# RPT-3 slice record — report generation from the UI

**Status:** BUILT + gated; awaiting the ratified P15 substitute (a fresh-context Opus audit).
**Wave 17, slice 3.** Branch `rpt-3-impl`. Design authority: `rpt_3_decision_record.md`
(RATIFIED 2026-08-10, four decision points, all as recommended; merged as PR #199 = `341e3e0`).

## 1. What shipped

### OQ-RPT3-0=A — `ROLLING_RISK` joins `PERF_RUN_TYPES`

The slice's only backend change, and it closed a real hole rather than adding a feature: the
report can BIND a `rolling_risk` run, but `/perf/runs` fail-closed on that run type, so no operator
could find one. The allowlist predated the family and grew by hand; ROLLING_RISK and SHARPE
arrived later and neither was added. Nothing noticed because nothing had asked.

Both arms are proven, and the negative one is load-bearing: **SHARPE is still refused with a 422**.
It was deliberately not added — nothing consumes sharpe runs, and widening a listing on symmetry
alone is how a closed set decays into a habit. The extension's SIDE EFFECT (the unfiltered
`/perf/runs` listing now admits these rows) is pinned by its own assertion rather than left to be
discovered — three verifier lenses flagged that the planning draft had not said so.

### OQ-RPT3-1/2/3/4/5 — the generate flow at `/ops/reports`

`GenerateReport.tsx`, mounted on the screen that lists and renders what it mints (the
`/ops/reproduction` precedent). A checkbox per report family, each arming a dropdown of that
family's COMPLETED runs from its OWN typed listing; labels carry the run's snapshot
`as_of_valuation_date` via a client-side join, and a run dated off the chosen report date is
**badged and still offered** — the server is the validator, and the badge is what makes its
refusal unsurprising instead of mysterious.

**Refusals render per WIRE CASE, three of them.** The route answers a bad portfolio with
`404 "portfolio not found"` before any service call; every service refusal arrives as one of two
constants. RPT-2 chose those constants deliberately (a service message can embed identifiers) and
this slice does not reopen that fence — so the screen renders the constant plus a cause checklist
for THAT class, saying plainly that the server does not disclose which applied. The two classes
get DIFFERENT checklists, which is the fix for the review's BLOCKING: every input-class cause is
impossible under a provenance refusal, and a list of impossible causes reads authoritative while
pointing at nothing.

**Carry (d) answered with visibility, not idempotency**: the form shows how many reports already
exist for the chosen book and date. At the listing's 500-row page bound the count is declared
**UNDETERMINED** rather than rendered as "500+" — the listing is `as_of_date` DESC with no date
filter, so a full page bounds nothing about an older date, and "500+ for this date" would have
been a wrong LARGE number replacing the wrong small one the control exists to avoid.

**Carry (f) is SURFACED, not paid**: the input-class checklist names the unscoped-VaR limitation in
the operator's own terms, and a test asserts that line — the surfacing is a proof, not an
intention. The carry's trigger (upstream scope propagation) is untouched.

## 2. Gates (P14)

- `CHECK_ALL_EXIT=0` — 2,732 unit / 254 FE
- `PG_PYTEST_EXIT=0` — 3,351 passed, zero FAILED/ERROR, fresh schema + `alembic upgrade head`
- `MUTATION_EXIT=0` — group `rpt-3`, **1/1 killed**, re-run against the final bytes
- No migration (head `0068`); route census unchanged at 305; **nothing minted**

## 3. Defects found, and by what

| # | Found by | What |
|---|---|---|
| 1 | **The planning cycle's pass 2, predicting it** | A LOW said mounting the form on the Reports screen would break RPT-2's stub router, since the screen would make three reads instead of one. It did exactly that. Fixed by ROUTING the stub honestly (not widening it) plus an `Array.isArray` guard at the wire boundary: a shape that is not what the contract promises must cost a LABEL, never the screen. |
| 2 | **My own negative control** | The 13-test proof suite passed on the first run — the shape a vacuous suite also has. Cross-contaminating the two refusal checklists was required to make the provenance test fail; it did, and was restored. |
| 3 | The generated contract | `/portfolios` and `/snapshots` return BARE ARRAYS while every listing beside them returns an `{items}` envelope. Assumed the envelope; the typecheck refused it. |

## 4. The ratified proof list, discharged

All nine §3 proofs are implemented in `generateReport.test.tsx`, each test naming its proof number
— the checklist the audit diffs against, written that way because REPRO-2 part 2 shipped with two
§3-bound UI proofs quietly undelivered and its review caught them one part later.

## 5. Deviations from the record

None in the built scope.

## 6. Carries

Unchanged from the record's §8 non-goals, each with its trigger. **SHARPE's absence from
`PERF_RUN_TYPES` is now a RECORDED drift** (trigger: the first SHARPE-consuming surface) rather
than the unrecorded drift it was when this slice started.
