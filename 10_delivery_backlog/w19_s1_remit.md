# W19-S1 — PRESENT-1: the presentation contract and the governed chart

**Rows entering build:** REQ-PRS-001, REQ-PRS-002. Both were AMENDED and adjudicated at the Wave-19
planning gate (2026-08-20, ledger lines 59–60, amendment commit `32e88a5`). This remit does not
re-open the acceptance text; it plans against it, and flags the two places where the ratified text
is wrong about the code.

Measured on `4475d09` (main), migration head `0077`, tree clean, CI nine-for-nine.

---

## Part 0 — What already exists, measured

| Fact | Citation |
|---|---|
| The report renders from PINNED content only; `regenerate_report` never re-reads family tables | `report/service.py:479-515` |
| The content hash is `sha256` over ONE joined string, `body` | `report/service.py:74-75, 350` |
| A section's pinned content is exactly `governed_value_content()`'s dict | `report/service.py:95-136` |
| `values` are pinned as pre-formatted STRINGS, verbatim from the source Decimal repr | `report/service.py:135` |
| `renderer_version` is pinned into every section and **no code BRANCHES on it** — but it is inside the bytes `verify_snapshot` compares, so it is not inert, and changing it is not free | `report/service.py:49, 134`; `snapshot/service.py:4095` |
| `REPORT_FAMILIES` = 4 presentable families: `var`, `concentration`, `liquidity`, `rolling_risk` | `report/families.py:352-387` |
| `REPRODUCIBLE ∪ UNREPRODUCIBLE` = **21**; the run-type VOCABULARY is **22** — `RUN_TYPE_REPRODUCTION` is in neither set | measured |
| **`var` yields exactly ONE row per run — 82 of 82.** `concentration` 1/8/16/18 buckets; `liquidity` 1/2/7 | measured against the seeded DB |
| **`rolling_risk`'s 33 rows are NINE series, not one**: four 7-point `:12m` series (MAX_DRAWDOWN, ROLLING_RETURN, ROLLING_VOLATILITY, ROLLING_VOLATILITY_ANN) and five 1-point `:36m` rows, **all five SUPPRESSED** and pinned as non-numeric `SUPPRESSED (...)` strings | measured; `report/families.py:296-298` |
| `AGGREGATION_CONTRACTS` covers all 21 — the DP-13 precedent for a per-family declaration | `aggregation/contracts.py:104-128` |
| `UNREPRODUCIBLE_FAMILIES` is the declared-exclusion precedent: family → written reason | `reproduction/registry.py:629-660` |
| Registry keys are UPPERCASE run types (`VAR`); report family keys are lowercase (`var`) — **two namespaces** | `report/families.py:352-387` |
| **There is no SVG or chart code anywhere in the repo.** REQ-PRS-002 is greenfield | measured |

### The seam this slice needs already exists and has never fired

`renderer_version` is written into every pinned section and **no code branches on it**. It is the
dispatch point S1 needs: a section pinned before S1 carries `rpt-1-html-v1`, one pinned after carries
a new value, so the renderer can render each section the way its own pin says to. Making it branch is
what turns "a regenerated historical report is byte-identical" from an accident into a structural
guarantee.

*The first draft called it "READ BY NOTHING" and treated it as free to change. It is not inert: it
sits inside the dict `verify_snapshot` re-derives and hash-compares, so bumping it reddens every
pre-S1 pin. See Part 1 §2 — that mistake is the reason the fix below is parameterisation rather than
a bare version bump.*

---

## Part 1 — One RETRACTION of mine, and one real hazard the ratified text did not anticipate

### 1. RETRACTED: my "the pinning rationale cites the wrong surface" claim was FALSE

The first draft of this remit asserted that REQ-PRS-001's amendment was wrong to say a render-time
contract lookup "would mark every pre-edit report DIVERGED in the CTRL-018 reproduction sweep",
on the grounds that the sweep does not read snapshot content hashes.

**The ratified text is TRUE and my correction was false**, confirmed by opening the file the
different-engine pass pointed at:

- `reproduction/registry.py:424` — `_REPORT_COMPARED = ("content_hash",)`
- `_recompute_report` imports and calls `regenerate_report` on every `ReportGeneration`, recording
  `IDENTITY-FAILURE` on `ReportIdentityError`
- `RUN_TYPE_REPORT` is in `REPRODUCIBLE_FAMILIES`, so the daily sweep covers it

So an unpinned, render-time contract lookup really would mark every pre-edit report DIVERGED in the
sweep — daily, on the platform's headline reproduction control.

**How I got it wrong, because the mechanism matters more than the apology.** At W19-S3b I
established by execution that the CTRL-018 sweep does not read **snapshot** content hashes. That was
true and is still true. The pinning rationale is about **report** content hashes — a different hash,
reached through `regenerate_report`, not through `verify_snapshot`. I generalised a correct narrow
finding into an incorrect broad one and then wrote it into a plan under a heading claiming to
correct false-at-citation prose. That is a P13 violation — killing a true claim without a factual
refutation — committed inside the section named for that exact failure.

The consequence for the plan is not cosmetic: **pinning is more load-bearing than I credited.** An
unpinned contract reddens the daily control, not an endpoint nobody calls.

### 2. The drift hazard is REAL, and it is WIDER than the contract field

`_reresolve_content`'s `GOVERNED_VALUE` branch re-derives the section by **calling
`governed_value_content()` live** (`snapshot/service.py:3861-3896`), and `verify_snapshot` compares
the serialized result against the pinned component hash (`:4095`).

`governed_value_content` **stamps the live `RENDERER_VERSION` module constant** and takes no
parameter for it (`report/service.py:134`). Therefore:

- **Bumping `RENDERER_VERSION` at all reddens EVERY pre-S1 report snapshot at verify** — before any
  contract exists, under either arm of any decision about the contract. Four independent
  verification lanes found this; the first draft of this remit mandated the bump in Outcome 2 and
  fenced only the contract field, so **the plan shipped the defect its own Part 1 diagnosed.**
- The same applies to a `presentation_contract` field.

**The fix is structural and is now part of the build, not a decision:** `governed_value_content`
gains explicit `renderer_version` and `presentation_contract` parameters, and `_reresolve_content`
passes BOTH forward **from the pin** — the pattern already used two lines away for
`source_known_at`, whose comment says carrying it forward "is not a shortcut, it is the only
definition". A proof runs `verify_snapshot` over a PRE-BUMP pin and asserts it does not redden.

## Part 2 — The build

### Outcome 1 — `PRESENTATION_CONTRACTS`, declared and censused (REQ-PRS-001)

A new `irp_shared/presentation/contracts.py`, mirroring `aggregation/contracts.py`'s import-light
shape (string-literal keys, no service imports).

**The census universe is the 22-member run-type VOCABULARY, discovered mechanically** — not the
21-member `REPRODUCIBLE ∪ UNREPRODUCIBLE` union. `RUN_TYPE_REPRODUCTION` is in neither of those sets,
so a census keyed on the union would leave it in no set and nothing would fail: silence where the
acceptance demands a DECLARED exclusion. The ratified wave plan put REPRODUCTION *inside* the
exclusion vocabulary; the first draft of this remit silently dropped it.

**The key-namespace bridge is declared, not assumed.** Contracts are keyed by UPPERCASE run type
(`VAR`) because that is the census universe; sections pin a lowercase family key (`var`). The
mapping between them is a declared constant with its own exact-set test against `REPORT_FAMILIES`,
because an implicit `.upper()` is the kind of coupling that breaks silently when a family key stops
being a lowercased run type.

The census asserts:

- `set(CONTRACTS) | set(EXCLUSIONS) == vocabulary`, **exact, both directions**;
- the two sets are **disjoint**;
- every contract names ≥1 identity field, a mark type from the acceptance's four (`path`, `rect`,
  `line`, `circle`), a unit and a precision;
- every exclusion names a reason from a closed categorical vocabulary (DS1-1);
- **a family in neither FAILS**, proven by planting a synthetic vocabulary entry and driving the real
  census function — not asserted in prose;
- the presentable set equals `REPORT_FAMILIES` exactly, through the declared bridge;
- non-vacuity floors on all populations.

### Outcome 2 — pinned, carried forward, and CONSUMED (REQ-PRS-001's second half)

- `governed_value_content` gains **explicit `renderer_version` and `presentation_contract`
  parameters**. It stops stamping the live module constant.
- `_reresolve_content`'s GOVERNED_VALUE branch passes **both forward from the pin**, as it already
  does for `source_known_at`. This is the fix for the BLOCKING defect the first draft shipped.
- **AND it must reproduce key ABSENCE.** The `source_known_at` analogy is not exact: pre-S1 pins
  contain a `renderer_version` key but contain NO `presentation_contract` key at all. Serialization
  is exact over sorted keys, so emitting the new key unconditionally reddens every historical pin
  even when its value is carried forward. `governed_value_content` must OMIT the key when the pin
  did not have one. The PRE-BUMP proof below is what catches a literal reading of the analogy.
- `RENDERER_VERSION` moves to `rpt-2-html-v1` for NEWLY pinned sections only.
- `render_report_html` **branches on the section's pinned `renderer_version`**: `rpt-1` sections
  render byte-for-byte as today; `rpt-2` sections render through their own pinned contract.
- **An unknown renderer_version, or an unresolvable contract, RAISES a named exception** —
  `PresentationContractError` — mapped explicitly at the API boundary. A silent default here would
  recreate the inert-declaration defect inside its own fix.
- **Identity fields are CONSUMED**: the rendered section labels each value with its declared identity
  fields, so "no rendered number is anonymous" is a property of the bytes rather than of a dict that
  nothing reads. Declaring and counting them without rendering them is the D2 shape again.

### Outcome 3 — the governed chart (REQ-PRS-002)

A deterministic server-rendered inline-SVG fragment emitted **inside** `render_report_html`'s
`body` — the only place the report content hash reaches.

**Subject: see DS1-2. It is NOT `var`.** Measured: every one of 82 `var` runs produces exactly one
`var_result` row, so "the VaR metric series for the pinned run" does not exist and a one-datapoint
chart is not a chart. The ratified wave plan recommended `var`; that recommendation is refuted by the
data and the substitution is a change to the ratified plan, which is why it is a decision.

Determinism requirements, named because the fragment lands inside a hash:
Decimal-only coordinate projection (no float round-trip), a declared rounding mode, fixed-precision
coordinate formatting, escaped text, fixed viewBox, and defined behaviour for the degenerate cases —
**0 datapoints, 1 datapoint, all-equal values (zero range), negative values, and a NON-NUMERIC pinned value** — `rolling_risk` pins `SUPPRESSED (...)` strings and every seeded run has five of them, so this case is guaranteed rather than hypothetical. Each gets a test;
a zero-range chart that divides by the range is the obvious crash.

The fragment carries the run id it was produced from and contains the declared mark shapes for its
declared mark type.

### Outcome 4 — Rule 7 reads

The ratified wave plan puts the chart on **the run-detail screen**; the first draft of this remit
silently moved it to the Reports screen and asserted "no new route expected". The report HTML is
already served and the chart rides inside it, so the Reports screen gets it for free — but the
ratified surface is the run-detail screen and any deviation is a scope change, not a detail. **Plan:
deliver the ratified surface**; confirm at build time whether a route is needed and treat a new one
as a route-census delta rather than a surprise.

---

## Part 3 — Fences enumerated before drafting

1. **`EXPECTED_ROUTE_COUNT = 315`** moves only if a route is added.
2. **The content hash covers `body` and nothing else.**
3. **`_reresolve_content` re-derives GOVERNED_VALUE live** — Outcome 2's parameterisation is what
   keeps that honest.
4. **`RENDERER_VERSION` is inside the verify byte comparison.** Changing it is never free.
5. **Reasons in a declared-exclusion dict have been FALSE here before** (four of REPRO-1's).
6. **`test_report_identity.py`'s `_section()` helper stamps the LIVE constant** — after the bump,
   ~10 existing tests would construct `rpt-2` sections with no contract and detonate the
   unresolvable-contract rule. They must be updated in the same commit.
7. **Determinism**: no timestamps, no unordered iteration, no per-render ids.
8. **Decimal, never float**, including every chart coordinate.
9. **ZERO migrations.** Nothing here is a schema change; a migration appearing is a design error.
10. **`gen-api-check` is not in `make check`** — run it if any DTO changes.
11. **`rolling_risk` pins `SUPPRESSED(...)` strings for some values** — any pin-time formatting rule
    must define what it does with a non-numeric pinned value.

---

## Part 4 — Decisions — **ALL THREE RATIFIED BY THE OWNER, 2026-09-05, as recommended**

| Decision | Ratified |
|---|---|
| DS1-1 exclusion vocabulary | **(a) closed categorical vocabulary** — `NOT_A_MEASURE` / `INTERMEDIATE_INPUT` / `NO_SECTION_YET` |
| DS1-2 chart subject | **RE-RATIFIED 2026-09-05 after a correction: (a) ONE named series, `ROLLING_VOLATILITY:12m` (7 points, none suppressed), with the `(metric_type, window_months)` selector declared IN the contract's identity fields.** The first framing was false at the data and the owner ratified on it; see DS1-2 below |
| DS1-3 formatting locus | **(a) render time; `values` stay verbatim** |

*The owner was shown the measured row counts and the honest caveat that a category is censused for
MEMBERSHIP in the vocabulary, not for TRUTH. The full option sets and reasoning are retained below.*

**DS1-2 was ratified TWICE, and the first ratification was on false information I supplied.** I
described rolling_risk's 33 rows as one series; they are nine. The correction, the true shape and the
re-ratification are recorded in DS1-2 rather than quietly overwritten, because a decision record that
hides which facts the decision was actually made on is worth less than none.


*DS1-1 in the first draft asked what `_reresolve_content` should do with the pinned contract. That is
no longer a decision: carrying it forward is forced, because the alternative reddens every historical
report snapshot and neither arm of the old fork prevented it. It has moved into Outcome 2 as
build work.*

### DS1-1 — the exclusion vocabulary: categorical, or free text?

18 of 22 families are excluded. If every reason is "no report section binds this family", the census
reduces to a tautology dressed as a control.

(a) **A closed categorical vocabulary** — `NOT_A_MEASURE` (REPORT, REPRODUCTION: a generation or
sweep row has no presentable number), `INTERMEDIATE_INPUT` (consumed by another family, never a
headline), `NO_SECTION_YET` (would be presentable; nothing binds it) — with the census asserting the
category is one of the declared set. *Recommended.* The categories are falsifiable claims about each
family, which is what makes the declaration worth censusing.

(b) **Free text per family**, mirroring `UNREPRODUCIBLE_FAMILIES` exactly. Matches precedent, and
carries the known hazard that reasons here have been false before.

**Honest caveat on (a):** a category is censused for MEMBERSHIP in the vocabulary, not for TRUTH.
Neither option makes a wrong classification fail a test. (a) narrows what can be said and makes a
wrong claim easier to spot on review; it does not mechanise correctness, and claiming otherwise would
be the same overclaim this gate keeps finding.

### DS1-2 — the chart subject, now that `var` is refuted

**RE-POSED 2026-09-05 — the first framing of this decision was FALSE at the data, and the owner
ratified on it.** It said rolling_risk's "33 rows per run, consistently" were "a genuine time
series". They are NINE series: four 7-point `:12m` series and five 1-point `:36m` rows, every one of
those five SUPPRESSED and therefore pinned as a non-numeric `SUPPRESSED (...)` string. Charting "the
values" would concatenate drawdown, return and volatility — annualised and not — into one
meaningless line, and five of the 33 points are unparseable as Decimal.

**This is the `var` error repeated one step later**: I measured row COUNT and inferred series-ness,
having just caught the same inference in the ratified wave plan. The decision is re-posed on the
measured shape.

(a) **ONE named `rolling_risk` series — `ROLLING_VOLATILITY:12m`, 7 points, no suppressed values** —
with the `(metric_type, window_months)` selector declared IN the contract's identity fields, so the
chart's subject is part of the pinned contract rather than hard-coded in the renderer.
(b) **`concentration`** — 8 to 18 buckets per run: a bar chart of `rect` marks, arguably more
board-relevant, and a naturally categorical subject needing no series selector. Cardinality varies
run to run and one seeded run has a single bucket, so the degenerate one-bar case is live.
(c) Keep `var` and chart a single value. Refused: it is a table cell drawn in SVG, which is precisely
what REQ-PRS-002's amendment was written to forbid.

### DS1-3 — where the contract governs number formatting

(a) **Render-time formatting from the pinned contract; `values` stay verbatim.** The contract is
genuinely consumed at render; a precision edit moves a NEW report's bytes because the new report
pins the new contract and renders through it; historical reports render through their own pinned
contract and stay byte-identical. *Recommended.*
(b) **Pin-time formatting.** The first draft recommended this and the verification refuted it twice:
it collides with the documented "values verbatim from the source Decimal repr" invariant, and because
`_reresolve_content` re-derives values LIVE from the family, a pin-time formatting rule would make
every NEW report snapshot drift from birth unless the formatting also runs inside the re-derive path.

---

## Part 6 — Found while opening this gate, NOT in scope

**A time bomb, fixed because it was RED and blocking.** `test_proxy_mapping_endpoint.py` read a
proxy mapping as-of a hard-coded `_MID = "2026-09-01"` while capturing with a now-based
`valid_from`. The wall clock overtook it on 2026-09-01; the test has been red since, with no commit
to blame, and nothing noticed because CI last ran on 2026-08-25. Fixed by deriving the instants from
`now()`.

**TWELVE other test files carry the same shape** — a literal future instant that now() will one day
overtake: `test_holiday_binding`, `test_data_quality`, `test_reference`, `test_sharpe`,
`test_scheduler`, `test_model_validation_pg`, `test_scheduler_cadence_pg`,
`test_demo_stage9zzzzzzzzzzzz_cal1b_pg`, `test_factor_endpoint`, `test_reference_endpoint`,
`test_reference_instruments_endpoint`, `test_benchmark_endpoint`. All green today; each has a
different fuse. **Not fixed here** — a planning gate is the wrong place to sweep twelve files, and
doing it quietly would hide the class. It wants its own item with a mechanical guard (a test that
fails when any test-module literal instant is within N days of now would turn a silent flip into a
loud one).

---

## Part 5 — Proofs this slice owes

- `make check`, full-PG, `fe-check`, `gen-api-check`, `g2-check` — all exit 0, counts quoted.
- **`verify_snapshot` over a PRE-BUMP pin does NOT redden.** The mechanism must be stated, because
  a pin built through the NEW code can pass while real pre-S1 pins redden: the test constructs the
  component's `captured_content` as the LITERAL pre-S1 dict — `rpt-1-html-v1`, no
  `presentation_contract` key — and verifies against it. A monkeypatched constant is not a pre-bump
  pin.
- **`verify_snapshot` over a POST-S1 pin does not redden either** — the born-drifted case.
- The census: exact set equality both directions, disjointness, a PLANTED family failing by driving
  the real census function, the presentable-set bridge, floors.
- **Both halves of byte-identity at GENERATION time**: a contract edit moves a NEW report's bytes AND
  a report generated BEFORE the edit still regenerates byte-identically — in one test, with the
  before-report generated first. The contract edit must be applied so the pinned constant genuinely
  differs, not monkeypatched in a way both halves see.
- An `rpt-1`-pinned section renders byte-for-byte as today.
- An unknown renderer_version and an unresolvable contract each RAISE, fired in a test (P9).
- The chart: byte-identical re-render; carries its run id; mutating one datapoint moves the REPORT
  content hash; either side of a contract edit moves the SVG bytes; the fragment contains declared
  mark shapes; **the anti-vacuity guard is per-mark-type, not a raw count** — one `<path>` element
  legitimately carries all N datapoints, so counting elements is unsatisfiable for a line chart. For
  `path`, assert the path's coordinate command count matches the datapoint count; for `rect`/`circle`,
  assert one element per datapoint. Either way a chart that renders NO data fails. The degenerate
  cases each behave as declared.
- Mutants for: the renderer_version carry-forward, the dispatch defaulting instead of raising, the
  census's exact-set arm, the contract-resolution failure path, the chart's contract consumption, and
  the identity-field rendering.
- **P15: this remit has had one different-engine pass (Fable, 40 agents, 35 raised / 21 confirmed /
  8 BLOCKING). The revision above answers it; a second pass runs on the REVISED remit before
  ratification**, because the first pass verified a document that no longer exists.
- The seven-ledger sweep, verify-on-main AFTER the merge.
