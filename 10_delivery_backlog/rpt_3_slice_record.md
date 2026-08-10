# RPT-3 slice record — report generation from the UI

**Status:** BUILT + gated + AUDITED (the ratified P15 substitute; §6 records what it found —
it did NOT come back null).
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
`/perf/runs` listing now admits these rows) is pinned against a rolling-risk run the test MINTS —
*the first version of this assertion was vacuous and this sentence claimed otherwise; see §6.*

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
- `MUTATION_EXIT=0` — group `rpt-3`, **1/1 killed**, re-run against the final bytes. Note what
  the mutant now costs: removing `ROLLING_RISK` from the allowlist fails TWO tests (the listing
  arm and the unfiltered arm), where before the audit it failed one and the second passed
  vacuously
- No migration (head `0068`); route census unchanged at 305; **nothing minted**

## 3. Defects found, and by what

| # | Found by | What |
|---|---|---|
| 1 | **The planning cycle's pass 2, predicting it** | A LOW said mounting the form on the Reports screen would break RPT-2's stub router, since the screen would make three reads instead of one. It did exactly that. Fixed by ROUTING the stub honestly (not widening it) plus an `Array.isArray` guard at the wire boundary: a shape that is not what the contract promises must cost a LABEL, never the screen. |
| 2 | **My own negative control** | The 13-test proof suite passed on the first run — the shape a vacuous suite also has. Cross-contaminating the two refusal checklists was required to make the provenance test fail; it did, and was restored. |
| 3 | The generated contract | `/portfolios` and `/snapshots` return BARE ARRAYS while every listing beside them returns an `{items}` envelope. Assumed the envelope; the typecheck refused it. |

## 4. The ratified proof list, discharged

Proofs 1–7 are in `generateReport.test.tsx`, each test naming its number; **proof 8 is Python**
(`test_perf_endpoint.py` + mutant R-E1) and **proof 9 is a statement**, not a test. The first
version of this section said "all nine are implemented in `generateReport.test.tsx`" — an
overclaim the audit caught (LOW-2).

## 5. Deviations from the record

**One, and the first version of this section wrongly said "None" (audit MEDIUM-2).** OQ-RPT3-5's
ratified as-of DEFAULT — the date field pre-filled with the most recent snapshot date — was not
built. It is built now, so the deviation is closed rather than carried; what stands as the lesson
is that a slice record's "no deviations" line is worth exactly as much as the sweep behind it, and
mine had none.

## 6. The fresh-context audit (the ratified P15 substitute)

**It did NOT return a null result** — which is the most useful thing to record about it, because
the gate ratified it as a substitute for a different-engine review and its value was therefore
unknown. Two HIGHs, four MEDIUMs, five LOWs; the two HIGHs were both instances of the class the
audit was aimed at, and one of them is the worst kind:

1. **HIGH — a test of mine was VACUOUS, and I claimed it was pinned in two places.** Proof 8's
   third arm asserted `returned_types <= PERF_RUN_TYPES` — a SUBSET relation, which stays true
   when the returned set SHRINKS. The auditor probed it by execution and found the set was
   `[]`: the fixture's unfiltered listing had no rows at all, so the assertion was
   `set() <= …`, true unconditionally. Its own comment claimed it asserted "through the API
   rather than by re-reading the constant"; the only load-bearing line was a re-read of the
   constant. The commit message and §1 of this record both said the side effect was "pinned by
   its own assertion". It was not. The test now MINTS a rolling-risk run and requires the
   unfiltered listing to contain it — and removing the allowlist entry now fails TWO tests where
   it previously failed one.
2. **HIGH — proof 5's second half was dropped.** The record binds "the new report's
   `report_code` appears in the rendered rows"; the delivered test proved only that the callback
   fired. Pass 2 had rewritten that proof from `id` to `report_code` *specifically to make it
   implementable* — and the implementable half is the half that went missing. Now rendered
   through the real `Reports` screen, with the twin (absent before the act).
3. **MEDIUM — the ratified staleness binding did not exist.** The record binds the carry-(f)
   checklist line to a test that also asserts carry (f) is still OPEN in `rpt_2_slice_record.md`,
   "because a prose reminder would not have survived". No such test existed. Built, and
   negative-controlled by marking the carry PAID (it reddens with the right message).
4. MEDIUM — the as-of default (see §5); MEDIUM — the missing-portfolio-badge limitation was
   silently absent from the screen rather than stated; MEDIUM — proof 1 covered 2 of 4 families.
5. LOWs: the record contradicted itself on the zero case; this record overclaimed proof coverage;
   the SHARPE fence hardcoded a string instead of the constant; the double-click defence is
   redundant (either half can rot unnoticed — accepted, recorded); and a PRE-EXISTING cwd
   sensitivity in two fence tests unrelated to this slice (`router-fence`, `write-fence` fail when
   vitest is invoked from the repo root). The new staleness binding was written cwd-INSENSITIVE
   for that reason.

**What this says about the substitute**: a fresh context on the same engine found two ratified
proofs that were bound by name and not delivered, plus a vacuous assertion its author believed
was load-bearing. That is a real result, and it is still not evidence that it substitutes for a
DIFFERENT engine — it is evidence that it is worth running. Recorded as a same-engine audit's
findings, per the gate's binding condition.

## 6b. Carries

Unchanged from the record's §8 non-goals, each with its trigger. **SHARPE's absence from
`PERF_RUN_TYPES` is now a RECORDED drift** (trigger: the first SHARPE-consuming surface) rather
than the unrecorded drift it was when this slice started.
