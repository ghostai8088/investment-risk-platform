# Wave-14 Close Review — "Real data through the governed rails"

> **Status: §§0–7 PENDING RATIFICATION; §8 is the execution addendum.** Six slices closed and
> merged (CON-1, PERF-0, LIM-2, CAL-1a/1b, DATA-1, LQ-1), HEAD `1f7aff8`, migration head
> `0061_liquidity_result`, counts 27/44/141. This close finds **one BLOCKING defect in a shipped
> governed family**, seventeen distinct survivors, and a wave-wide pattern that is *not* an LQ-1
> anomaly.
>
> **§§0–7 are preserved exactly as first written — including the sentences §8 refutes.** When they
> say "nothing is folded yet," that was true at the time of writing and is no longer: **§8 records
> eight fold commits, the re-adjudication of the seventeen 2-of-3 kills (fourteen overturned), eight
> record corrections, and the close's OWN false-green episode** — six consecutive red CI runs
> reported as green, caught by the user rather than by me. Migration head is now `0062`. Read §8
> before treating any statement in §§0–7 as current.

---

## 0. Method — and the honest account of what it can and cannot see

**0.1 The audit.** Refute-by-default, in the Wave-13 pattern. Slice verifiers for all six slices
plus cross-cutting lanes (security/ratified doctrine, registers-as-claims, deferral/carry register,
the wave against itself, the wave's own delivery claims). **Every HIGH/MED finding was attacked by
three adversarial refuters with distinct lenses** (correctness · reproducibility · already-handled);
a finding survived only if fewer than two of three refuted it.

**Outcome: 20 survivor records → 17 distinct defects** (three pairs are the same defect found
independently by two lanes), **29 findings killed**, **17 killed exactly 2-of-3 and flagged for
hand re-adjudication**, **24 LOWs recorded UNREFUTED**.

**0.2 What the refutation rule did well, and where it is lane-sensitive.** Three defects were found
twice, by lanes that did not see each other's work, and survived **all six** refutation attempts:
the LQ-1 snapshot pre-build refusals with no control (slice-verifier HIGH + wave-claims BLOCKING),
the false "every refusal path is mutation-proven" claim (twice), and — inversely — `liquidity.run`,
which **survived at MED in one lane (1 of 3 refuted) and was killed 3-of-3 in another** on identical
facts. The disagreement is entirely about severity, not about the code. Read that as a calibration
warning: the rule filters *evidence*, not *framing*.

**0.3 The 24 unrefuted LOWs are a deliberate cost bound.** They were not attacked and must not be
read as verified. Several are substantive (§2, §3) and two are register-integrity items that a
future sweep will otherwise rediscover.

**0.4 What this close did NOT do.**
- It did **not** re-run `make check`, the fresh-schema full-PG battery, `fe-check`, or CI. The
  battery results in §7 are **reported by audit lanes, not personally observed by this synthesis**.
- It did **not** fold anything. Every finding below is open at the time of writing.
- The seventeen 2-of-3 kills were **not** hand-re-adjudicated by this synthesis — Wave 13 found
  three of six such kills were wrong, so §7 lists all seventeen for a human pass rather than
  burying them.
- No outward architecture/benchmark sweep. The wave's budget went to the guard layer and the
  registers, which is where the findings were.

**0.5 One operational finding from the audit itself, worth more than several of the LOWs.** A lane
reported the documented full-PG battery as **RED and non-deterministic** (50 failed / 7 errors, then
13 failed / 11 errors, same tree, same order). Three refuters, each running an **isolated**
container, got **2,980 passed / 0 failed / PYTEST_EXIT=0, twice, at identical wall-clock**. Root
cause: the shared `irp_pg_local` on port 5432 with four concurrent agent pytest processes writing
`DEMO_TENANT_ID`. The finding was correctly killed 3-of-3 — but **the standing rule is now
insufficient**: "reset the schema before each full-PG run" does not say "and hold the database
exclusively for its duration." Under a parallel agent fleet that omission manufactures a false RED,
and a false RED in a close audit is as expensive as a false GREEN.

---

## 1. Slice verification — six slices

### CON-1 (concentration, 23rd family, `0057`, ENT-069) — **no surviving slice-level finding**

The only slice to clear its own verifier lane. Its two most serious challenges — that
`denominator_basis` is a "controlled vocabulary" with **no CHECK, no census, no P6 floor** while the
sibling tables `limit_definition` (`ck_limit_definition_denominator_basis_vocab`) and
`liquidity_result` (`ck_liquidity_result_denominator_basis`) both got one, and that the
effective-number-of-holdings deferral rests on a false FE premise — were **killed 2-of-3 and 3-of-3
respectively**. The first is on the hand-re-adjudication list (§7) and should be taken seriously:
the executed reproduction stands (insert `denominator_basis='TOTAL_ASSETS_BOGUS'` into a
`LIKE ... INCLUDING ALL` clone → `INSERT 0 1`, with a working negative control on
`dimension_kind`). CON-1's exposure in this close arrives through the cross-cutting lanes instead
(§3: no methodology doc, CTRL-002).

**Verdict: SHIPPED-AS-RATIFIED, provisionally** — provisional because the strongest challenge
against it was a close call, not a clean refutation.

### PERF-0 (scale probe, no migration) — **three survivors; the headline verdicts stand, the fold and the exponents do not**

- **HIGH — the F2 fold shipped for 2 of 6 segments.** `perf_0_decision_record.md:302` says "the
  harness now folds **every** returned status into `SegmentReading.ok`"; `delivery_roadmap.md:266`
  says "statuses folded into **each segment's** ok." `_fail_segment_on_non_completed` is called at
  exactly two sites in `scripts/perf_probe.py` — `:338` (var) and `:357` (portfolio_return).
  `exposure`, `factor_exposure`, `covariance` are unchecked; **`concentration` — the segment whose
  committed-FAILED run produced the Reading-3 erratum the fold was written for — has its result
  discarded entirely** (`:363`, bare statement, no assignment). A refuter's executed control is
  decisive: wrapping the two *folded* binders to return `status=FAILED` yields `ok=False` with the
  right detail; wrapping the four *unfolded* ones yields `ok=True` on all four and counts their
  seconds into `batch_seconds`. The DB-census half of the fix (`test_perf_probe_pg.py:125-159`) is
  real and non-vacuous — but `main()` runs no census, and `main()` is the path that produced
  Readings 1–5. *(The dissent — that this is the named PERF-1 carry "status census, never
  throw-based ok" — is fair against the code and wrong against the record's own wording.)*
- **MED — "ingestion dominates risk compute by 10.9–14.4×" is a one-time backfill against a daily
  batch.** The arithmetic reproduces exactly (13,938.26/1,281.76 = 10.87; /971 = 14.35). Normalized
  to a cycle it inverts: 10,000 daily marks at the probe's own 27.4 rows/s = 6.1 min against a
  one-date batch of 16.2 min — compute dominates ~2.7×. Under the seed's **actual** month-end grain
  the inversion is far larger (~55× per business day). The readings label the seed "one-time" four
  times; they never normalize the ratio that drives the conclusion and scopes all four PERF-1
  carries at ingestion throughput.
- **MED — the readings do not reproduce on their own host, and `0.948` is cross-session.** Covariance
  — the segment the record itself calls book-independent — re-measures at 6.5 s against a recorded
  10.36–12.27 s. Worse for the record than reported: **every** segment moved together, batch total
  77.02 s → 46–55 s (~1.4–1.7×), under *higher* load, at the recorded rung on the recorded
  container. The canonical `0.948 (2k→10k)` is Reading 4's 2,000-column divided into Reading 5's
  10,000-column, two sessions, with no same-session anchor at either end. The 8.90%-of-budget
  headline is unaffected (direct measurement at the ratified budget point); the three-decimal
  exponents assert precision the harness has not demonstrated.

**Verdict: the four headline verdicts STAND. The fold claim and the exponent precision do not.**

### LIM-2 (`0058`, dimensional selector) — **one survivor, plus the wave's cleanest near-miss**

- **MED — `test_limit_resolver.py` leaks a global monkeypatch.** Three assignments in
  `TestTheLevelTrap` (`:367`, `:383`, `:396`) rebind `conc.latest_concentration` directly instead of
  via the `monkeypatch` fixture the same file uses correctly at `:90`, and never restore it.
  `_resolve_concentration` imports the name **inside** the function body (`limit/service.py:298`),
  so every later concentration limit resolution in that process reads a fixed 1-row stub. Proven by
  execution: a probe appended to the same pytest process gets
  `[... share_invested_long=Decimal('0.60') ...]` back **with `session=None`**, no database touched.
  Latent today only because no test file sorting after it exercises limit evaluation — one added
  test away from silently green-lighting the exact fabricated-value class the D1/R1 repairs closed.

Two challenges were killed 2-of-3 and belong on the hand list: `LimitFamily.requires_basis` is a
**dead declaration** (no production read; flipping it changes nothing — executed) in a dataclass
whose own docstring says it "declares ONLY what has a consumer" and whose test *name* asserts that;
and OQ-LIM-2-1=C's `authored_scheme_id` drift anchor is **optional at authoring**, so a
classification limit can silently ship with no anchor.

Unrefuted LOWs against LIM-2 are unusually dense and unusually concrete: a shipped comment citing an
adversarial case "(1b)" **that does not exist in the file**; two different wrong test counts (10 and
13, actual 16) in the record that names ledger 7; the still-unexplained `requires_basis=False`
registry anomaly carried three slices with no mechanical gate; `ck_limit_definition_issuer_only` one-
directional so the disclosure fence's predicate is app-only; and **no close section at all** in the
decision record — LIM-2 is the only Wave-14 slice whose record has no gates table, no ledger sweep,
no verify-on-main.

**Verdict: SHIPPED, with a test-hygiene defect one file away from becoming a false green, and a
record that never closed itself.**

### CAL-1 (`0059`, split 1a/1b) — **one survivor, and it is the wave's signature failure**

- **HIGH — the Sharpe UNCONSUMED-PIN refusal shipped with ZERO discriminating coverage.** Part 9
  records the MED fold as "added to **both** binders"; `delivery_roadmap.md:380` and
  `current_state.md:110-112` both state the CAL-1b fold's 1 BLOCKING / 4 HIGH / 7 MED / 7 LOW were
  "**ALL** folded with executed negative controls." The RM-1 arm has its control
  (`test_rolling_risk.py:1067`). **The SR-1 arm has none, at any tier.** Three independent
  mutations on isolated exports agree: disabling `sharpe_service.py:417` leaves ~2,400 unit tests
  green (`PYTEST_EXIT=0`, mutation marker verified still on disk after the run), while the identical
  mutation on `rolling_service.py` is killed immediately. One refuter went further and showed the
  consequence: with the guard disabled, a v1 `perf.sharpe` run over a `holiday_calendar_code`-pinned
  snapshot **COMPLETES and writes four governed rows bound to a pin the kernel never read**.
  *Verified independently by this synthesis:* the only `pytest.raises(..., "unconsumed pin")` in the
  entire tree is `test_rolling_risk.py:1083`; `test_sharpe.py:467` is prose in a docstring.
  **Zero refuters.**

Two CAL-1 challenges were killed 2-of-3 (the one-sided holiday-coverage gate below the dataset's
first covered year; the roadmap's arithmetically impossible "1,332 months 2024–2035" — 12 years is
144). Both are on the hand list. Four unrefuted LOWs are real design residue: the HOLIDAY_CALENDAR
pin captures the calendar's **entire** date set rather than the ratified span; the holiday-child read
predicate differs between the scheduler resolver and the snapshot builder/verifier; and
`dispatch_one`'s `period_key` — the month-grain double-fire backstop — has **no unit-tier control**
(nulling it leaves the whole SQLite tier green).

**Verdict: the convention move is CORRECT. The fold-completeness claim in two governed records is
FALSE.**

### DATA-1 (`0060`, ENT-070, TB3MS) — **two survivors; the wave's largest open item was avoidable**

- **HIGH — the "no independent channel is reachable" premise is false, and all 30 literals verify
  clean.** `data_1_decision_record.md:929` states "FRED and the Board's DDP CSV both refuse anonymous
  access from this environment"; `:773` says the DDP CSV "is not reachable anonymously"; the
  control matrix carries the residual as **"Standing residual, carried in the open."** Plain
  anonymous `curl`, this machine, no proxy: `fred.stlouisfed.org/series/TB3MS` → 200;
  `fredgraph.csv?id=TB3MS` → 200 (1,110 rows); Board DDP `Output.aspx` H.15 CSV → 200; Board
  `FRB_h15_xml.zip` → 200 (4.27 MB). Two channels **independent of the render proxy** — FRED's CSV
  and the Board's own H.15 package, series `RIFSGFSM03_N.M` — agree with `TB3MS_RATES` value-for-value
  on all 30 literals, mismatches `[]`, and both confirm 2026-07 is absent. Root cause found and
  agreed by all three refuters: the agent's **WebFetch tool** 403s (`:254` records this accurately);
  that tool-level 403 was generalized into an **environment-level** impossibility that was never
  tested with an ordinary HTTP client. **Zero refuters.** The residual is dischargeable today, in
  minutes, and the Board's package should become the standing re-verification path (it is also
  DDP-retirement-proof).
- **MED — CTRL-034 Execution 2 item 8 cites a test that does not exist in the file it names.** The
  control's acceptance-census row cites `test_the_final_position_count_pin` "(13-z)"; the 13-z suite's
  test is `test_the_positional_count_pin`. It **resolved** at the DATA-1 close (`0d5eb4a`) and was
  broken by LQ-1's label-relay sweep (`149d916`), which renamed the function in nine files and did
  not touch the control record. `pytest ...::test_the_final_position_count_pin --collect-only` →
  exit 5. *(The dissent is well-argued — the assertion still runs in CI, and the finding's own
  fallback fix points at a test asserting 27/44/141 rather than 26/43/139, which would make the
  control materially false. Re-point to `test_the_positional_count_pin`, not to the 14-z suite.)*

**Verdict: the dataset is CORRECT and independently verified. The record's account of why it could
not be verified is FALSE.**

### LQ-1 (liquidity tiers, 24th family, `0061`, ENT-071) — **seven survivors including the wave's only BLOCKING**

- **BLOCKING — `run_liquidity` has no `assert_model_version_of` gate.** Part 3 item 4 of the ratified
  record (`lq_1_decision_record.md:386`) requires "Registrar + `assert_model_version_of` in the
  pre-create gate." *Verified by this synthesis:* `grep -rn assert_model_version_of
  packages/shared-python/src/irp_shared/liquidity/` → **exit 1, no matches**, against 19 sibling
  services that call it (CON-1 at `concentration/service.py:121`). `run_liquidity` takes a
  `ModelVersion` **object** and only parses its assumption texts back. Executed by three lanes
  independently against live PG: register `risk.liquidity_tiers` v1, record a **REJECTED**
  `ModelValidation`, then ask both gates about the same version —
  `assert_model_version_of` → `RejectedModelVersionError ... new runs refused (CTRL-022)`;
  `run_liquidity` → `COMPLETED | rows: 7`. Seven **immutable, append-only** `liquidity_result` rows
  written under a methodology a validator stood down. The same bypass covers MG-1 OD-F's expired
  use-before-validation exception and CTRL-003/BR-3's `status != REGISTERED`. One lane additionally
  bound a **foreign-tenant** model version to a DEMO_TENANT run (superuser session — latent, not
  live). **Zero refuters.** Mitigating only in blast radius: `run_liquidity`'s sole caller today is
  the demo stage, and `api/liquidity.py` exposes GET only.
- **HIGH/BLOCKING (found twice, six refuters failed) — all four `LiquiditySnapshotError` pre-build
  refusals are uncontrolled.** *Verified by this synthesis:* `grep -rn LiquiditySnapshotError
  packages/shared-python/tests apps` → **exit 1**. Ratified OQ-LQ-1-2 required the inherited
  mixed-VERSION refusal "computed over LIVE heads and **mutation-proven** (CON-1's negative control
  is the template)." Executed: mutating `snapshot/service.py:4307` (`> 1` → `> 99`) leaves the full
  fresh-schema battery at **2,980 passed / 0 failed**; the *identical* mutation on CON-1's line
  `:4165` reddens exactly one test
  (`test_mixed_live_scheme_VERSIONS_of_one_family_refuse`). The refusals are real and fireable — one
  lane proved it — but nothing would notice if they went unfireable again, which is B1's own failure
  mode one step earlier.
- **HIGH (found twice) — "Every refusal path in LQ-1 now carries a control that has been
  mutation-proven — reverting the defect fails the test" is false.** *Verified by this synthesis:*
  `grep -rn GAP_STALE_TIERS packages/shared-python/tests apps` → **exit 1**. Three lanes, each on
  its own isolated tree and its own private database, deleted the staleness block
  (`liquidity/service.py:271-285`, both arms), reverted the H2 off-vocabulary fold, and reverted the
  H3 `known_at` branch — **2,980 passed, 0 failed, 0 skipped** every time, with the full PG tier
  live. The staleness refusal is the one B1 was about and the one an immutable `model_limitation`
  row promises to every reader.
- **HIGH — the R-07 mint shipped with no SoD holder-set pin.** *Verified by this synthesis:*
  `grep -rn "liquidity\.view\|liquidity\.run" packages/shared-python/tests apps/backend/tests` →
  **exit 1**. CON-1, one slice earlier, pinned all three of its codes both directions
  (`test_concentration_kernel.py::TestGovernancePins`). Mutation-proven blind: stripping `auditor_3l`
  of `liquidity.view` **and** granting it the maker verb `liquidity.run` leaves the entire ORM tier
  green (`PYTEST_EXIT=0`), while the identical mutation on CON-1 fails immediately. The standing
  pre-flight manifest (`claude_operating_instructions.md:341`) mandates "per-code SoD pins" for a new
  permission mint. **Zero refuters.** Also absent, from the same manifest line: LQ-1 has **no row in
  `06_security/entitlement_sod_model.md`** — `grep -rni liquid 06_security/` returns nothing.
- **MED — `liquidity.run` is minted and granted to three roles with zero enforcement surface.**
  `_require_run` is built at `api/liquidity.py:49` and referenced nowhere; there is no
  `POST /liquidity/runs`, no scheduler entry (`FAMILY_REGISTRY` = VAR + EXPOSURE_AGGREGATE), and
  `run_liquidity` has only demo callers. The 24th governed family has **no production invocation
  path**. Severity is genuinely contested: filed at HIGH in one lane it was killed 3-of-3 (mint-ahead-
  of-route has precedent — `schedule.manage`, `lineage.source.manage`, `ops.audit.verify`,
  `reference.identifier.view` are all unrouted); filed at MED in another it survived.
- **MED — the liquidity router has zero endpoint tests and CON-1's mandatory route→code census was
  not carried forward.** *Verified by this synthesis:* `ls apps/backend/tests | grep -i liquid` →
  **exit 1**. CON-1 shipped `test_every_concentration_route_is_guarded_by_the_ratified_code` as
  "OQ-CON-1-25's mandatory route test", precisely because per-code holder pins cannot catch a
  mis-scoped route. The census exists for exactly one router in the platform.
- **MED (cross-cutting) — LQ-1's own trap T4 shipped as prose with no census.** A kind added to
  `DIMENSION_KINDS` alone compiles, imports, passes every test, and then refuses **every** capture at
  runtime. Executed: injecting a fourth kind leaves the whole battery green
  (`PYTEST_EXIT=0`) while `validate_basis` refuses it for all five bases. The countermeasure shipped
  is a declarative comment — the one form P7 explicitly rules out
  (`claude_operating_instructions.md:320`). Parity holds today, so this is a missing gate, not a
  live defect.

**Verdict: the 24th governed family shipped with its model-governance gate ABSENT, its ratified
refusals UNCONTROLLED, its permission mint UNPINNED, and its record asserting all four were done.**

---

## 2. Deferral / carry register — re-baselined for Wave 15

Every row below was checked against the merged tree at `1f7aff8` by opening the cited `file:line` or
by execution. No row is taken from a record's own word.

**PAID AND VERIFIED (8).**
1. CON-1 `_METRIC_MAP` registration → paid at LIM-2, 10 CONCENTRATION metrics bindable (executed).
2. CON-1 refusal-after-success staleness → paid at LIM-2, platform-wide.
3. REF-1 read-verb gap → paid at LQ-1 (`classification/service.py:877`, `:952`). **Caveat:** both
   verbs have **zero production consumers** (finding killed 2-of-3, §7).
4. REF-1 `RULE_TYPE_COMPLETENESS` mint → fired and paid at DATA-1
   (`marketdata/benchmark_rates.py:58,89`).
5. CAL-1a coverage carry → paid at CAL-1b, forward-only advance with a negative control.
6. CAL-1's COMPONENT_KIND mandate for pinned tiers → discharged at LQ-1 (`PURPOSE_LIQUIDITY_INPUT`).
7. Wave-13's month-end holiday residual → paid by `calmath` (executed: 2027-05 LBD = 2027-05-28,
   the recorded 2027-05-31 collision handled).
8. REQ-PRF-002 RE-POINTED in **both** registers (backbone `:296`, RTM `:58`).

**OPEN — TRIGGER NOT FIRED (12).** LIM-2 classification-basis selector (first two-basis tenant; the
demo uses one basis only) · LIM-2 breach DTO dimension echoes (**re-evaluate at RPT-1's gate**) ·
CON-1 real regulatory ratio and LQ-1 limit-bindability (both wait on a NAV/net-assets entity — none
exists) · CON-1 normalized HHI · CON-1 per-basis bucketing · CON-1 effective-number 1/HHI (trigger:
the first concentration detail view — the FE still has none) · CON-1/LIM-2 concentration
schedulability (`FAMILY_REGISTRY` holds VAR + EXPOSURE_AGGREGATE only) · REF-1 alpha-3/M49
(**re-evaluate at RPT-1's gate**) · REF-1 bulk re-classification · LQ-1 restatement trail ·
LQ-1 position-grain tiers · LQ-1 AIFMD `scheme_family` · DATA-1 OQ-1a yield→period-return model
(nothing binds the real rf series; **no marker exists at its own trigger site in `perf/`**).

**OPEN AND USER-OWNED (1).** The independent re-verification of the 30 TB3MS literals
(`control_matrix_skeleton.md:75`). **This close discharges it on the evidence** (§1 DATA-1): two
non-proxy channels, all 30 exact. It requires only a record edit.

**ESCALATION (1).** CTRL-018's scheduled reproduction job — **three recorded non-movements**
(`control_matrix_skeleton.md:59`), which by LQ-1's own words is the signal it needs a slice, not a
fourth citation. *(Precision, unrefuted: they are not "consecutive" — CAL-1b and DATA-1 both edited
CTRL-018-mapped requirements and dispositioned nothing.)*

**HOMELESS (2).** PERF-0's four named carries are addressed to **"PERF-1", a slice that exists
nowhere** — not a roadmap row, not a Wave-15 opener, not an on-demand theme. And the **Wave-13 FE
toolchain debt** (TS 5.9→7.0, eslint 9→10, jsdom 29→30, six untypechecked root guard tests) passed
through Wave 14 untouched and unmentioned, including by three slices that shipped FE surfaces;
`package.json` pins are unchanged at HEAD.

---

## 3. Doc integrity — false or unsupported claims in governed records

Nine, plus three unresolved precision items. Each with its correction.

1. **`perf_0_decision_record.md:302` / `delivery_roadmap.md:266` — "every returned status" / "each
   segment's ok."** Shipped for 2 of 6. → State "var and portfolio_return; the other four remain
   throw-based, covered by the CI census only," and move the F2 line into the PERF-1 carry list where
   the record already names "status census, never throw-based ok."
2. **`delivery_roadmap.md:380` / `current_state.md:110-112` — the CAL-1b fold's findings "ALL folded
   with executed negative controls."** The SR-1 arm of the unconsumed-pin refusal has none. → Name
   the arms that had controls; add the Sharpe twin of `test_rolling_risk.py:1067`.
3. **`lq_1_decision_record.md:614-616` — "Every refusal path in LQ-1 now carries a control that has
   been mutation-proven — reverting the defect fails the test."** Executed refutation, three
   independent lanes: reverting three folded defects fails nothing. → Correct in place; the sentence
   is stated as the slice's *standing lesson*, so leaving it uncorrected propagates the error.
4. **`lq_1_decision_record.md:386` (Part 3 item 4) — "Registrar + `assert_model_version_of` in the
   pre-create gate."** Not present. → This is the BLOCKING; the record correction follows the fix,
   not the other way round.
5. **`lq_1_decision_record.md:198, 203, 377, 512` — OQ-LQ-1-2's mixed-VERSION refusal "mutation-proven"
   with "executed negative controls."** No test names `LiquiditySnapshotError`. → Port CON-1's five
   pre-build controls; correct the ratification rows in place per the record's own convention.
6. **`data_1_decision_record.md:773, 929` + `control_matrix_skeleton.md:75` + `tb3ms_rates.py:13-19`
   — "FRED and the Board's DDP CSV both refuse anonymous access from this environment."** False for
   both named channels. → Scope the module docstring to "the agent fetch tool 403s; direct HTTP
   works," record the executed Board-package verification in CTRL-034 Execution 2, and drop the
   "carried in the open" residual.
7. **`vendor_onboarding_diligence_checklist.md:57` — CTRL-034 item 8 cites
   `test_the_final_position_count_pin` (13-z).** Does not resolve. → Re-point to
   `test_the_positional_count_pin`; add CTRL-034's citation set to whatever sweep re-labels demo
   suites.
8. **`control_matrix_skeleton.md:43` — CTRL-002 "Every calculation has methodology doc," Status
   *Operational*.** Three registered families contradict it: `risk.factor_return.pure_private`
   registers `05_analytics_methodologies/pure_private_factor_v1.md`, a file that **has never existed**
   (`git log --diff-filter=A` over the directory lists all 27 files ever added; it is not among
   them), and Wave 14's two new families register **prose** refs ("docs: CON-1 decision record Parts
   1-2", "docs: LQ-1 …") against a ratified standard (OD-P3-0-C: "A methodology doc is MANDATORY
   before any risk method ships"). *Verified by this synthesis:* no concentration, liquidity, or
   pure-private file exists in `05_analytics_methodologies/`. → Write the docs **or** ratify an
   explicit exception that a decision record may serve as `methodology_ref`, and replace the 14
   hand-copied per-family doc tests with one census over every `*_METHODOLOGY_REF` constant — one
   that fails on a non-resolving path rather than silently skipping non-path values.
9. **`lq_1_decision_record.md:637` — ledger 3 records "CTRL-002 EXERCISED, not moved."** The purpose
   allow-list and parse-back halves were exercised; the control's *title obligation* was skipped. →
   Say which half. Also add LQ-1's `PURPOSE_LIQUIDITY_INPUT` trace to CTRL-002's own row, which
   carries CON-1's and not LQ-1's.
10. **`delivery_roadmap.md:375-383` + `current_state.md:7` + `lq_1_decision_record.md:629` — the
    autonomous-merge ordinals are mutually contradictory.** Git gives fourteen PR merges #156…#169 in
    order; the records claim #157=2nd, #160=6th, #162=8th, #165=10th, #168=11th, implying offsets
    0/+1/+1/0/−2. **No anchor satisfies all five** (tested exhaustively over every candidate).
    #168 is the thirteenth. → Re-derive once from `git log --first-parent`, state the inclusion rule,
    apply it uniformly — or drop the running count, which adds nothing the PR number does not.
11. **`requirements_backbone.md:181` vs `requirements_traceability_matrix.md:63` — REQ-CRD-003 is
    "In-Progress" in the canonical register and "Done" in the mirror, and the backbone cell asserts
    both statuses in one sentence.** The LIM-2 closeout appended to the backbone and replaced in the
    RTM (`git show adb2201`). The RTM's own header says status is "mirrored from the backbone
    (canonical there)." → Flip the backbone's leading token.

**Unresolved precision items (record, do not paper over).** (a) The records cite a **2,954-test**
full-PG battery (`lq_1_decision_record.md:644`, `current_state.md:9`); every isolated run in this
audit — reporter and refuters alike — **collected 2,980**, and `git diff --stat 28f76ca 1f7aff8 --
'*tests*'` is empty, so the test set has not moved since the LQ-1 merge. The cited literal is ~26
low and nobody re-measured it. (b) PERF-0's erratum "A '0.907' appears nowhere in this document"
appears in a document containing 0.907 at `:180` and `:190` (killed 2-of-3; the *intent* — that
0.907 is Reading 3's superseded exponent — is right and the wording is wrong). (c) `demo/data1_stage22.py:24`
still calls the 13-z pin FINAL-POSITION after LQ-1 demoted it, so `149d916`'s "exactly one file
carries it" is inaccurate at HEAD in the prose sense, and `test_demo_stage9zzzzzzzzzzzz_cal1b_pg.py:191`
still carries the *function name*.

---

## 4. The wave's own pattern

**It is not an LQ-1 anomaly. It is the wave.** LQ-1 supplies the density; five of six slices supply
the class.

**The class: a control's EXISTENCE was verified; its DISCRIMINATING POWER was not.** In every
instance below, someone wrote a guard, wrote a claim about the guard, and never ran the one
experiment — remove the guard, see if anything goes red — that separates the two.

| Slice | Claim in a governed record | What execution showed |
|---|---|---|
| LQ-1 | "Every refusal path … mutation-proven" | 3 folds reverted → 2,980 passed, 0 failed |
| LQ-1 | OQ-LQ-1-2 mixed-VERSION "mutation-proven" | mutating the refusal → full battery green; CON-1's twin dies |
| LQ-1 | Part 3.4 "`assert_model_version_of` in the pre-create gate" | absent; REJECTED version binds, 7 immutable rows |
| CAL-1 | fold "ALL … with executed negative controls" | 1 of 2 arms; the SR-1 mutant survives ~2,400 tests |
| PERF-0 | F2 "every returned status folded" | 2 of 6; the erratum's own segment discarded |
| LIM-2 | registry "declares ONLY what has a consumer" | `requires_basis` read nowhere (close call, §7) |
| DATA-1 | "no independent channel is reachable" | three channels answer 200 to plain curl |

Six of the seven rows are **claims about verification**, not claims about behaviour. That is the
sharper statement of the pattern than "controls were inert": the platform's guard layer is in
reasonable shape; **the platform's account of its guard layer is not**. Wave 13's P5
("assert by evidence, not by absence") governs tests. Nothing yet governs the *sentence a slice
writes about its own tests*, and ledger 7 — "delivery claims cite their artifact against the MERGED
diff" — was run by every slice and caught none of these, because a citation to a real file is
satisfied by a real file that does not do what the sentence says.

**Second pattern: the fold lands at the SITE, not the CLASS.** PERF-0's F2 fixed the two segments the
reviewer was looking at and left the four it wasn't, including the one that generated the erratum.
CAL-1b's unconsumed-pin fold fixed the binder under review and not its twin. LQ-1's B1 fold fixed the
parse and left the consuming refusal untested. In all three the *code* of the fold is correct and the
*extent* is wrong — and in all three the record describes the extent as total.

**Third pattern, and the cheapest to fix: an impossibility was recorded without executing the plainest
alternative.** DATA-1 generalized one tool's 403 into "no independent channel exists from this
environment," carried a user-facing standing residual on it, and three minutes of `curl` discharged
it. PERF-0 recorded exponents to three decimals without a same-session anchor. The roadmap recorded
"1,332 months 2024–2035" without dividing. Nobody re-counted 2,954. **The wave's failures are almost
never failures of reasoning; they are failures to run a five-second command before writing a
sentence down.**

**What did NOT recur, and deserves saying:** no BYPASSRLS app path; `audit/service.py` byte-identical
to `2411d00`; `HYBRID_TABLES` still exactly 7 in both the declaration and the live catalog; all three
new tables carry FORCE RLS with symmetric own-tenant policies; no Wave-14 migration mints a role,
grant or permission row; the SoD auditor line holds in both the declaration and the live
`role_permission` rows. The doctrine floor held.

---

## 5. Proposed standing rules (P8+)

Five, each grounded in this wave's findings, each a mechanical gate or prose bound to a trigger
moment. None is a bare "remember X."

**P8 — THE GOVERNED-BINDER CONFORMANCE CENSUS (mechanical gate).** One test enumerates every module
registering a governed family and asserts, by exact set equality, that each calls
`assert_model_version_of` (or is on an explicitly declared exception list with a written reason).
*Grounded:* LQ-1's BLOCKING — the 24th family is the only one of twenty-four missing it, and no gate
noticed for a full slice plus a close. **A per-family convention with 23 correct instances and one
wrong one is exactly what a census is for.** Recommend RATIFY.

**P9 — A REFUSAL IS NOT SHIPPED UNTIL A TEST HAS MADE IT FIRE (mechanical gate + trigger prose).**
Mechanical limb: a census asserting that every declared refusal constant and every custom
`*Error` raised in a governed binder or snapshot builder is named in at least one test that asserts
it fires. Procedural limb, bound to the fold moment: *a fold is not folded until its own negative
control has been executed against the pre-fold code and shown to fail.* *Grounded:* LQ-1's four
`LiquiditySnapshotError` refusals + `GAP_STALE_TIERS` + `GAP_CORRUPT_PINNED_CONTENT` (zero test
references, verified by this synthesis); CAL-1's Sharpe arm. **LQ-1 wrote this rule itself, in Part
10, and its own slice violated it six times over** — which is why it must become a census, not a
sentence. Recommend RATIFY.

**P10 — A FOLD APPLIES TO THE CLASS, NOT THE SITE (procedural prose, bound to the fold's closing
step).** When a review fold repairs a defect at a call site, its closing step greps the symbol,
enumerates every sibling site, and records **per site**: fixed, or not-fixed-because. The fold's
record sentence may quantify over only the sites it enumerated. *Grounded:* PERF-0 F2 (2 of 6, the
erratum's own segment omitted); CAL-1b unconsumed-pin (1 of 2 binders); LQ-1 B1 (parse fixed,
consumer untested). Recommend RATIFY.

**P11 — A PERMISSION MINT IS NOT COMPLETE WITHOUT ITS HOLDER-SET PIN, ITS ROUTE CENSUS, AND ITS SoD
REGISTER ROW (mechanical gate).** Best form is data-driven: a declared expected holder map in
`test_entitlement_bootstrap.py` compared by exact set equality, so **a newly minted code with no pin
fails by construction**; plus one platform-wide route→code census walking every router mounted in
`main.py`. *Grounded:* LQ-1's two codes — mutation-proven blind in both directions, no route census,
no `entitlement_sod_model.md` row — against CON-1's fully-pinned three one slice earlier; and four
pre-existing unrouted codes nobody has ever counted. **Implementation warning from the audit:** a
naive `app.routes` walk yields `_IncludedRouter` wrappers with no `.methods` and produces a
**green census over zero routes** — one such vacuous instance already exists at
`test_schedules_endpoint.py:346`. Recurse through `original_router.routes` or build from
`app.openapi()`. Recommend RATIFY.

**P12 — BEFORE RECORDING AN ENVIRONMENTAL IMPOSSIBILITY, EXECUTE THE PLAINEST ALTERNATIVE CLIENT
(procedural prose, bound to the moment of writing).** No governed record may state that a resource
is unreachable, a check is impossible, or a residual must be carried for environmental reasons,
until the plainest alternative has been executed and its output pasted. A tool's refusal is evidence
about the tool. *Grounded:* DATA-1's TB3MS residual — a user-facing standing residual in the control
matrix, resting on a WebFetch 403, discharged by `curl` in under three minutes, all 30 literals
exact against the publisher of record. Recommend RATIFY.

*(Considered and NOT proposed: a rule about same-session performance anchors — one slice, one
instance, and the fix is a sentence in the readings, not a standing rule. A rule about record
arithmetic — the ordinals and the 1,332/144 error are real but P3 already covers "verify the entry
against the thing it describes.")*

---

## 6. Wave-15 readiness

**Nothing opens until the BLOCKING is fixed.** `run_liquidity` must take `model_version_id: str` and
call `assert_model_version_of(..., expected_model_code=LIQUIDITY_MODEL_CODE)` before
`declared_liquidity_parameters`, with a negative control proving a REJECTED version yields zero run
and zero snapshot. Both demo call sites pass objects and move with the signature. The seven
`liquidity_result` rows written under a stood-down methodology during the audit were probe artifacts
in a local database, **but the local `irp` database now carries demo-campaign and probe residue —
reset the schema before trusting any gate run on it.**

**Before DEP-1 (the deployment floor):**
- **`seed_system_reference` has no non-test caller** and its own docstring says "Not idempotent —
  call once on a fresh database." DEP-1 **is** REF-1's trigger ("the first second consumer of the
  SYSTEM seed outside the demo campaign", `con_1_decision_record.md:818-822`). That debt fires at
  DEP-1 and must be paid there, not rediscovered.
- **`create_calendar` cannot set `holidays_complete_through`**, and only `refresh_calendar_holidays`
  can — with no HTTP route. A deployment that creates a calendar through the API gets a
  BUSINESS_MONTH_END schedule that refuses at every tick. Fail-closed and loud, but it means the
  convention move has no end-to-end production path yet.
- **The shared-database rule needs its second clause** (§0.5): a full-PG run requires exclusive use
  of its database for the run's duration, or its own container. This close nearly published a false
  RED on the wave's own battery.
- Until DEP-1 ships, **every "operational" claim in the records carries an implicit dev-only
  qualifier** — the standing Wave-15 commitment says so; this close found nothing to soften it.

**Before RPT-1 (reporting):**
- **Three carries must be re-evaluated at RPT-1's gate rather than rediscovered:** LIM-2's breach DTO
  dimension echoes (trigger: the first wire consumer — RPT-1 is the named candidate), REF-1's
  alpha-3/M49 (trigger: the first regulatory report), and CON-1's effective-number 1/HHI (trigger:
  the first concentration detail view).
- **Settle the methodology-doc question first (§3.8).** A reporting surface that renders
  `methodology_ref` will render one dangling path and two prose strings. Decide the contract before
  it becomes an outward-facing artifact.
- **`BreachOut` stays unwidened by ratified decision** — RPT-1 is the trigger that reopens it.

**Escalations that should be sliced, not cited again:** CTRL-018's scheduled reproduction job (three
recorded non-movements); PERF-0's four homeless carries need a host slice or an explicit trigger
("before any parallelization or grain-level performance work"); the Wave-13 FE toolchain debt needs
a dated gate or an explicit recurrence acceptance.

---

## 7. Evidence and outcomes

**Personally observed by this synthesis lane** (read-only, HEAD `1f7aff8`, tree clean):

| Check | Result |
|---|---|
| `ls migrations/versions \| tail` | head is `0061_liquidity_result` |
| `grep -rn assert_model_version_of .../liquidity/` | **exit 1 — no matches** (the BLOCKING) |
| `grep -rn LiquiditySnapshotError packages/shared-python/tests apps` | **exit 1 — no matches** |
| `grep -rn GAP_STALE_TIERS packages/shared-python/tests apps` | **exit 1 — no matches** |
| `grep -rn "unconsumed pin" packages/shared-python/tests` | one control only — `test_rolling_risk.py:1083`; `test_sharpe.py:467` is docstring prose |
| `grep -rn "liquidity\.view\|liquidity\.run" .../tests` | **exit 1 — no matches** |
| `ls 05_analytics_methodologies/ \| grep -iE "concentr\|liquid\|pure_private"` | **exit 1 — no matches** |
| `ls apps/backend/tests \| grep -i liquid` | **exit 1 — no matches** |

**Reported by audit lanes, NOT personally observed by this synthesis.** All mutation experiments;
all database probes (the REJECTED-model-version bind, the TB3MS channel verification, the live
catalog RLS/CHECK queries); the fresh-schema full-PG battery results (**2,980 passed / 0 failed /
`PYTEST_EXIT=0`, reproduced by three independent refuters on isolated containers**, against the
records' cited 2,954); the perf re-measurements; the `curl` transcripts. Each is cited to a lane with
its command and output in the finding text; none was re-executed here.

**Not done by this close:** `make check`, `fe-check`, `docs-check`, CI observation, `alembic
downgrade base` smoke, any fold.

**Tally.** 20 survivor records → **17 distinct defects**: 1 BLOCKING, 8 HIGH, 8 MED. 29 killed.
**24 LOWs recorded unrefuted** — a cost bound, not a verification.

**The seventeen 2-of-3 kills, flagged for hand re-adjudication** (Wave 13 found three of six such
kills were wrong): CON-1 `denominator_basis` no CHECK/census/floor · PERF-0 OQ-10 synthetic docstring
· PERF-0 OQ-2 factor-return span · PERF-0 `test_synthetic.py` fence · LIM-2 `requires_basis` dead
declaration · LIM-2 `requires_basis` "else recorded" lapsed · CAL-1 v2 holiday-coverage gate
one-sided · CAL-1 "1,332 months 2024–2035" · LQ-1 OQ-8 limitations not rendered on run detail · LQ-1
OQ-17 censuses "amended with negative controls" · LQ-1 `ILLIQUID_SHARE` vs the ratified
`illiquid_share_invested_long` · LQ-1 `GAP_CORRUPT_PINNED_CONTENT` unreachable · LQ-1 seeder-debt
trigger · REF-1 read-verbs with zero production consumers · CTRL-003 skipped both new model codes ·
PERF-0 seven-ledger sweep declared "NOT applicable" · PERF-0 erratum self-contradiction.
**Three of these — `denominator_basis`, `requires_basis`, and the LQ-1 metric name — carry executed
reproductions that no refuter contradicted; only their severity was disputed.**

**Ratified outcomes:** none yet. This document is PENDING RATIFICATION. The decision points for the
gate are: (1) fix the BLOCKING before anything else; (2) P8–P12; (3) the eleven record corrections in
§3; (4) whether the 24 LOWs are folded (the clean-code standing bar says yes) or triaged; (5) whether
the seventeen close calls get a hand pass.
---

## 8. Execution addendum — what happened AFTER §§0–7 were written (2026-08-02 / 2026-08-03)

§§0–7 above are preserved **exactly as written**, including the sentences this addendum refutes.
That is deliberate: a close review that quietly edits its own errors cannot be evidence about how
errors survive.

### 8.1 The seventeen 2-of-3 kills were re-adjudicated — and the rule under-protects

All seventeen were re-judged by hand. **Fourteen were overturned.** My first framing of that result
("82%") was inflated by my own rubric; the honest figure is **~53% of kills wrong at fold-relevant
severity** — comparable to Wave 13's three-of-six, not dramatically worse.

The failure mode is specific and worth stating precisely: **in a tally, a majority of judges finding
a real defect UNIMPORTANT is indistinguishable from a majority finding it UNREAL.** The three kills
flagged in §7 as carrying uncontradicted executed reproductions — `denominator_basis`,
`requires_basis`, the LQ-1 metric name — were all among the overturned. This is the grounding
evidence for **P13 (PROPOSED)**: kills are reserved for factual refutation, and an executed,
uncontradicted reproduction may be DOWNGRADED but never discarded on severity votes.

### 8.2 The code fold — eight commits on `wave-14-close-fold`

| # | Commit | What |
|---|---|---|
| 1 | `f18bf1d` | The BLOCKING: `run_liquidity` gains the `assert_model_version_of` gate + the **P8 census** |
| 2 | `3a037c8` | The CAL-1 start-side coverage gate, shared at the class (**P10**) |
| 3 | `da322f0` | Migration `0062` — the `denominator_basis` CHECK, and trap T1 caught in its own downgrade |
| 4 | `7c44559` | The LQ-1 limitations rendered on the ratified surface, mutation-proven |
| 5 | `19d96b2` | `list_assignments` gains its production consumer; the route gains its first tests (**P11** class) |
| 6 | `71d9f38` | The four `build_liquidity_snapshot` pre-build refusals, each made to FIRE (**P9**) |
| 7 | `15cd418` | Three CI gates + the XNYS coverage-start defect (§8.3) |
| 8 | `a9fc582` | `cryptography` 49.0.0 → 50.0.0, clearing CVE-2026-69247 |

### 8.3 The fold's own false-green — the wave's pattern, committed by the close itself

**Folds 1–6 were RED in CI on every push, from fold 1 onward, and I reported them green.**

This is the third recurrence in one wave of *a gate reported green having never been run* (LQ-1
reported two such gates; §4 named the class). It was caught only because the **user** looked at the
GitHub actions list and said the last six runs were red.

The mechanism is worth recording because it is not a simple lapse. The Backend job orders
`pip-audit` → `ruff format` → lint → mypy → pytest. A **formatting** failure at step 2 meant lint,
mypy and **the entire backend test suite never executed** on any of the six commits — and from the
outside a cosmetic failure and a total loss of test coverage look identical: one red X. Running
`make check` honestly then surfaced two further failures that had been invisible behind the
formatter (four E501s from fold 2; a mypy rebind from fold 5), and the dependency audit was hiding
one layer above that. **Four gates deep, all masked by a formatter.** The available tell was ignored:
a Backend job finishing in **31 seconds** cannot have run 2,400 tests.

This is the grounding evidence for **P14 (PROPOSED)**: a gate is not green until its exit code is
quoted; CI is not green until the run conclusion for the branch head SHA is quoted.

### 8.4 A real defect was hiding behind the trivial ones — the XNYS coverage start

Fold 2's start-side gate refused the shipped RM-1/SR-1 demo, and **it was right to**. A
`BUSINESS_MONTH_END` grid's opening boundary d_0 is the close of the month BEFORE the first measured
month, so a run whose first measured month is January 2024 adjudicates d_0 = 2023-12-29 against a
calendar that began in **2024**. The shipped dataset **could not serve the earliest month it existed
to serve**, and every such run rolled d_0 weekend-only.

The dataset was wrong, not the gate. XNYS extended back to 2023 (118 → 128 dates) rather than moving
the demo forward, which would have hidden the limitation. Provenance: the Wayback Machine's
2023-03-05 capture of the NYSE calendar, whose 2024/2025 columns agree date-for-date with the
already-shipped literals — the cross-check that establishes the 2023 column was read from the right
position. **No governed boundary literal moved** (December 2023's last weekday is Friday the 29th
either way). Full erratum in `cal_1_decision_record.md`.

**This is §4's pattern in its purest form.** CAL-1's record said the 118 literals were "verified
three ways" and they were — every check asked whether they were the RIGHT dates. **None asked
whether the set STARTED early enough.** A control's existence was verified; its *coverage* was not.

### 8.5 Record corrections executed

| Record | Correction |
|---|---|
| `data_1_decision_record.md`, control matrix, roadmap ×2 | TB3MS residual **DISCHARGED** — 30/30 literals verified against live FRED (HTTP 200 via plain `curl`), zero mismatches. The "FRED refuses anonymous access" claim was **untested and false**; one tool's 403 was recorded as a fact about the world. Grounds **P12** |
| `lq_1_decision_record.md` | "Every refusal path in LQ-1 now carries a control that has been mutation-proven" — **false when written**; quantified over the paths I had fixed, not the paths that exist. Grounds **P9** and **P10** |
| `perf_0_readings.md` | Erratum-to-the-erratum: the F4 erratum corrected the rows/s figure and then asserted nothing used the totals column — **self-refuting**, since rows/s IS derived from totals. Arithmetic re-executed; the substantive claim stands, the scope sentence did not |
| `perf_0_decision_record.md` | The whole seven-ledger sweep declared "NOT applicable" on artifact grounds; that reasoning covers only ledgers 1–3. **Ledger 7 (the record's own delivery claims) applies to every slice** — and the close found exactly its defects in this record |
| `cal_1_decision_record.md`, roadmap | The XNYS coverage-start erratum (§8.4) |
| `delivery_roadmap.md` | "1,332 months 2024–2035" → **1990–2100**. The count was right and the RANGE was wrong (2024–2035 is 144 months); re-executed 2026-08-03, 1,332 months, zero mismatches |
| `lq_1_decision_record.md` | The LIM-2 `requires_basis` carry **LAPSED** — written as "PAID if (C) taken; else recorded", (A) was ratified, and the else-branch never ran. Measured: one hit in the tree, a dataclass field with no consumer. Re-recorded as a live carry with a trigger. **A carry written as a conditional is not a carry** |
| `vendor_onboarding_diligence_checklist.md` | CTRL-034 Execution 2 item 8 cited `test_the_final_position_count_pin` for the 13-z file; the 13-z (DATA-1) function is `test_the_positional_count_pin`. The citation named a real function in the wrong file |

### 8.6 Gates — quoted, per P14

| Gate | Evidence |
|---|---|
| `make check` | **2,410 passed, `MAKE_CHECK_EXIT=0`** (captured log, no pipe in the capture path) |
| Full-PG battery | **2,970 outcome characters, all dots — 0 failed, `PYTEST_EXIT=0`**, fresh schema at head `0062` |
| `pip-audit` | "No known vulnerabilities found, 1 ignored" on the **upgraded** tree |
| CI | run **30859961988** = `success`, all six jobs green. Backend **7m40s** vs 31–43s on every red run — the visible proof the suite now executes |

### 8.7 Still open at this addendum

1. **The 24 LOWs** remain recorded-unrefuted — a cost bound, not a verification. Disposition is a
   gate decision (the clean-code standing bar argues fold).
2. **`reconstruct_assignment_as_of` still has no production consumer.** Fold 5 gave
   `list_assignments` one; its sibling remains unconsumed and is honestly recorded as such rather
   than counted as REF-1's gap paid.
3. **P13 and P14 are PROPOSED, not ratified** — they do not bind until the user ratifies them.
4. This addendum's own claims are subject to ledger 7: each is cited to its artifact above.
