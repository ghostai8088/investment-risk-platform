# TD-1 Decision Record — Test-data realism audit + remediation (Wave-1 hygiene insertion)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-TD-1-1…6 approved by the user (2026-07-09, after a plain-language decision briefing); implementation is a SEPARATE approval |
| Date | 2026-07-09 |
| Basis | User standing rule (2026-07-09): all dummy/fixture data must be economically plausible by default; deliberately extreme values only in clearly-labeled boundary/adversarial tests. User directed a **full hygiene slice now** to retrospectively audit + remediate existing fixture data (chosen over "recon-only" / "fold into Wave-1 close" / "going-forward only"). A Wave-1 **insertion** ahead of P2-7 implementation (roadmap Part 4 rule 3 — hygiene insertion, ratify before starting). |
| Grounding (recon, read-only, 2026-07-09) | ~98 test files; **~34 carry economic-value fixtures** (returns/fx/prices/levels/marks/quantities/weights/cost_basis/covariance+VaR inputs). Spot-check CONFIRMS a real, mixed problem: `test_factor.py:350` `Decimal("-1.5")` is a LEGITIMATE labeled boundary (`pytest.raises(DataQualityError)`, below the −1 band) — stays; `test_factor.py:306` `Decimal("9.9")` (=990%) is an ORDINARY correction fixture — implausible; `test_var.py:805` `0.90` + `test_covariance.py:482` `0.88`/`0.99` are implausible returns **deliberately chosen to force a distinguishable covariance/VaR delta** (comment-documented) yet **unlabeled** and **assertion-load-bearing**. So the fix is NOT a find-replace: many implausible values are load-bearing (golden assertions or signal-forcing). |
| Sign-off | **PENDING — OQ-TD-1-1…6 below** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-TD-1-A** | slice character | A **test-and-fixture hygiene slice**: changes are confined to test files, seed/synthetic scripts, and API/doc examples. **NO production code, NO schema/migration, NO governed-number/model/permission/audit change** (the diff fence forbids all of those). Behavior-preserving on the SUITE: every touched test stays green — where a fixture value drives an assertion, the expected output is RE-DERIVED in the same change (never a silently-loosened assert). |
| **OD-TD-1-B** | scope (IN) | Every **economic-value** fixture literal: captured-market values (fx `rate`, `price`, curve `point_value`, benchmark `weight`/levels/returns, `factor_return`), holdings (`quantity`, `cost_basis`, `mark_value`), derived-number INPUTS + asserted OUTPUTS where the input's magnitude is chosen freely (exposure amounts, covariance inputs, VaR inputs), and any surfaced example (endpoint-test request bodies, doc snippets). Dates already real are in-scope only if implausible (e.g. weekends used as "trading days" where it matters). |
| **OD-TD-1-C** | scope (OUT / untouched) | **Plumbing** (tenant/actor/GUID ids, `code_version`, `environment_id`, opaque labels) — realism is meaningless, DO NOT churn. **Deliberately-extreme values that are ALREADY correctly labeled** (17-sig-digit precision probes, column-envelope breaches, non-PSD matrices, NaN/±Inf guards, below/above-band DQ-rejection fixtures inside `pytest.raises`) — these are load-bearing and STAY unchanged (the standing rule explicitly protects them). |
| **OD-TD-1-D** | the classification method (the core of the slice) | Each economic-value fixture site is classified into exactly one of THREE buckets, and remediated per bucket: **(1) ORDINARY** — a representative value with no special role ⇒ set to a plausible value (per the OD-E per-domain bands); if it feeds an assertion, re-derive the expected. **(2) BOUNDARY/ADVERSARIAL** — an intentionally extreme value testing a guard/limit ⇒ KEEP the value, but ensure it is CLEARLY labeled (a `pytest.raises`, or a name/docstring/inline comment stating it is a boundary probe). **(3) SIGNAL-FORCING** — an implausible value chosen only to make an output *distinguishable* (the `0.90`/`0.88` covariance-delta case) ⇒ FIRST try a plausible value that still yields a distinguishable output (re-derive the expected); only if realism genuinely destroys the signal, KEEP it and RELABEL it as an explicit sensitivity fixture with a comment saying why an exaggerated value is used. Bucket (3)→plausible is preferred; (3)→relabel is the escape hatch, not the default. |
| **OD-TD-1-E** | per-domain plausibility bands | Documented reference bands (the DQ sanity bands are the hard floor; these are the *plausibility* target): FX rate O(0.5–200) by pair; index level O(10²–10⁴); equity/bond price O(1–10⁴); simple DAILY return small fraction (target abs(r) ≲ 0.05, hard band > −1); weights [0,1] summing sensibly per set; mark/quantity/cost_basis at realistic instrument scales; covariance inputs → daily-return-scale so variances land O(1e-4). Bands live in the plan (not enforced in code — a reviewer/finder guideline, not a new gate). |
| **OD-TD-1-F** | proportionate review + gates | **FULL 6-finder review** (breadth: ~34 files, and the re-derived-assertion risk is real — a wrong re-derivation ships a green-but-wrong test). Unreduced validation: `make check` + full-PG + `make fe-check` + diff fence (assert ZERO production-code / migration / schema / permission / audit changes — a test-and-example-only diff). |

## Part 2 — Rationale highlights

### Why a classify-then-fix method, not a sweep
The recon proves a blind "realistic value" find-replace would (a) break golden assertions that pin computed
outputs of the fixture inputs, and (b) weaken tests whose whole point is a distinguishable delta produced by an
exaggerated input. The value of the slice is *catching units/scale bugs and improving fixtures as documentation* —
achieved only if each site is judged, not mass-edited. Bucket (2)/(3) protect the tests that are *supposed* to use
extreme data; bucket (1) is where the real cleanup lives.

### Honest sizing (objective note)
"Full" is genuinely large: hundreds of literals across ~34 files, many entangled with asserted computed outputs.
This is bigger than a TC-1-sized hygiene insertion. Mitigation baked into the plan: (i) a fixed classification
rubric so each site is a quick decision; (ii) domain-by-domain ordering (captured-market first — highest bug-catch
value and least computation entanglement — then derived-number fixtures where re-derivation is needed); (iii) if
mid-slice the derived-number re-derivation proves larger than one slice, that is a roadmap Part-4 rule-2
re-sequencing trigger (split the derived-number domains into TD-2), briefed — NOT silently dropped.

## Part 3 — Out of scope (recorded)
No production/runtime code change; no new DQ gate or CHECK enforcing realism (the rule is a review guideline, not a
constraint — over-tight economic gates would reject legitimate stress fixtures and real tail data); no schema/
migration/permission/audit change; no new test *cases* (this is fixture-value remediation, not coverage growth —
new coverage rides its own slice); no frontend behavior change (only any hard-coded implausible example values, if
present, are corrected); the P2-7 build proceeds under the rule already (TD-1 is retrospective only).

## Part 4 — Open decisions (OQ-TD-1-1…6) — pending ratification
- **OQ-TD-1-1 — recommend APPROVE.** Run TD-1 as a Wave-1 hygiene insertion BEFORE P2-7 implementation; record the roadmap amendment. *(Alternative: after P2-7 — but the user directed "now".)* (OD-A.)
- **OQ-TD-1-2 — recommend APPROVE.** Scope = all economic-value fixtures (OD-B); plumbing + already-labeled extreme values untouched (OD-C).
- **OQ-TD-1-3 — recommend APPROVE.** The three-bucket classification method + the per-bucket remediation, incl. the (3)→plausible-preferred / (3)→relabel-escape rule. (OD-D.)
- **OQ-TD-1-4 — recommend APPROVE.** The per-domain plausibility bands as a reviewer guideline (NOT a new code gate). (OD-E.)
- **OQ-TD-1-5 — recommend APPROVE.** Full 6-finder review + unreduced gates + the test-and-example-only diff fence. (OD-F.)
- **OQ-TD-1-6 — recommend APPROVE.** The escape hatch: if derived-number re-derivation exceeds one slice, split into TD-2 via a briefed re-sequence (rule 2), rather than loosening asserts or rushing. (OD-A/rationale.)

## Part 5 — TD-1 implementation readiness gate
Implementation-ready once OQ-TD-1-1…6 are ratified. Build contract = `td_1_implementation_plan.md`.
**TD-1 planning implements nothing.** Model/effort: **Opus 4.8 / high** — classification + careful re-derivation is
templated judgement over a large surface, not novel methodology (not a Fable case); the re-derivation correctness
risk is what warrants /high + the full review.
