# Wave-13 Close Review — "Analytics breadth on the governed rails"

> **Status: RATIFIED 2026-07-29** — the mandatory Part-4 rule-2 re-baseline over
> SCH-2 → RM-1 → SR-1 → OPS-H1 → FE-M1. **P1–P6 ALL APPROVED AS RECOMMENDED** (P4 with the
> binding re-measure clause) and **WAVE 14 RATIFIED as the direction** ("real data through the
> governed rails"; slicing at Wave-14 planning per the normal discipline). The six ratified rules
> are WRITTEN into `claude_operating_instructions.md` as standing sections (this closeout commit),
> so a future session inherits them from the read-order, not from this record. Fold batches 1–4 +
> the close document are on `wave-13-close`; validation evidence in §0.3/§7.

## 0. Method — and the honest account of what it can and cannot see

**0.1 The audit.** Ten close auditors under ultracode (121 agents, ~7.7M tokens, 68 minutes):
five slice verifiers + five cross-cutting (integration, security/doctrine, register, docs/CI,
agenda-claims), refute-by-default, every HIGH/MED finding attacked by **three adversarial refuters
with distinct lenses** (correctness / reproducibility / already-handled); a finding survived only
if fewer than two of three refuted it. **11 findings survived, 26 were killed, 20 LOWs were
recorded UNREFUTED** — the LOWs' unrefuted status is a deliberate cost bound, stated so this close
cannot read as though they were verified. The six findings killed only 2-of-3 were re-adjudicated
by hand: **three of the six kills were wrong** (the dynamic-import fence axis, SR-1's "refused at
capture" claim, the vacuous pacing purpose test) and were promoted into the fold set.

**0.2 The folds.** All 11 survivors, the 3 overturned kills, and all 20 LOWs were folded — a
deliberate departure from triage-and-defer, per the clean-code standing bar. The fold phase ran as
**one editing thread** (the SR-1 shared-tree lesson: parallel agents mutating one tree is the
incident class this wave already paid for), starting from a purged-`__pycache__`, mutation-marker-
grepped tree because the audit fleet had run mutation probes against it and a green gate from a
contaminated tree is not evidence. Every code fold carries an **executed mutation control** —
eleven mutants across the batches, each shown killing its test(s) and each restoration shown green.
A separate double-check pass re-executed the evidence for every batch-1/2 claim and found one
defect in the close's own work (raw pipes inside six stamped table cells — fixed, `4992f2e`).

**0.3 Validation.** `make check` **2201 passed / 480 skipped** post-fold (baseline 2193/478;
the delta is the folds' own tests); fresh-schema full-PG battery — result recorded in §7 from the
observed run; `fe-check` clean (prettier, eslint `--max-warnings=0`, `tsc --noEmit`, **32 files /
204 tests**, up from 190); `docs-check` green with the WIDENED closure gate; CI on the branch
recorded in §7 from observed conclusions only.

**0.4 What this close did NOT do.** No outward architecture/benchmark sweep beyond §4's
destination re-check (Wave 12's ran one; this close's budget went to the guard layer, where the
findings were). The register re-baseline (§2) leans on the audit's register dimension plus spot
re-verification, not a fresh six-way sweep of every historical item.

## 1. Slice verification — THE RUNTIME-CLEAN STREAK ENDED AT EIGHT

**The headline: one RUNTIME HIGH shipped and survived every gate.** `calc/reads.py` coerced every
entity-read filter value with a blanket `str()`. Harmless for eight waves — every prior caller
filtered a UUID/String column — until RM-1 and SR-1 routed the platform's first `Integer` filter
(`window_months`) through the seam. SQLAlchemy types a bind from the Python value, so PostgreSQL
received `integer = character varying` and refused: **all four new read endpoints
(`/perf/rolling-risk{,/latest}`, `/perf/sharpe{,/latest}`) returned 500 on the production
database** while `make check`, the PG suites, and CI were green. The two tests written
specifically for the filter passed — **SQLite's INTEGER column affinity converts `'12'` → `12`,
so the unit tier is structurally incapable of seeing this class.** The eight consecutive
"zero runtime defects" closes were measured by that tier. Fixed by binding at the column's type;
equivalence proven on live PG across ten families under three bindings (identical row counts);
regression pinned **in the PG tier only** (a unit pin cannot fail — the R-4 class at the level of
a whole test tier); mutant reproduces the exact `ProgrammingError`.

Per slice, verdicts after refutation:

- **SCH-2 — SHIPPED-AS-RATIFIED**, runtime clean. LOW folds: the dispatch-time CTRL-003 refusal
  hoisted from `_dispatch_var` into `dispatch_one`, declaration-driven like its three sibling
  layers (a third requiring family would have inherited no dispatch gate); `target_run_type` made
  a consumed declaration; two record corrections (the counts note, the Part-5 upgrade caveat).
- **RM-1 — arithmetic CONFIRMED** (goldens survived independent re-derivation), but its **headline
  fold was undefended**: deleting alignment condition (4) or (5) — the fix for the one-day-month
  HIGH — left the ENTIRE suite green, while the record asserts *"every new guard is
  mutation-tested."* The guard was real; the claim about it was not; the claim is what a later
  slice relies on. Discriminating grids added (both deletion mutants now kill), the masking regex
  tightened, the registered GRID assumption text completed from three conditions to the five the
  kernel enforces. Also: a NaN pinned return escaped as a raw `decimal.InvalidOperation` where
  SR-1 refuses it as a governed 422 over the SAME pin shape — RM-1 now shares SR-1's strict parse,
  pinned symmetrically in both suites.
- **SR-1 — arithmetic CONFIRMED**, but the R1 centrepiece — the `_persist_snapshot` purpose gate,
  cited by CTRL-002 as its "real enforcement" — had **no negative control**: the close audit
  deleted it and the suite stayed green (the only `SnapshotPurposeError` test rides
  `build_snapshot`, whose surviving pre-check masks the tail). Direct tail control added
  (refuse + zero rows), the two promised membership pins shipped, plus a both-directions census
  over every `PURPOSE_*` constant. Two false record claims corrected (§3).
- **OPS-H1 — SHIPPED-AS-RATIFIED**; every claimed HIGH against it was refuted 3/3. Folds: the
  M-C1 deadlock test's tick-victim branch now **executes** the SAVEPOINT recovery on the real
  40P01 (previously assert-only; the mechanism additionally proven deterministically with the
  victim forced via per-session `deadlock_timeout`); the composed tick now asserts the phase-4
  `notified` leg under the re-arm (the dedicated phase-4 pin cannot see the re-arm — its single
  event never crosses a commit; its false comment corrected); the H1-8 census docstring narrowed
  to what it asserts.
- **FE-M1 — migration CONFIRMED** (one React, router clean, audit 0), but the guard layer took
  three more findings: the fences' **third un-enumerated bypass axis** (dynamic `import()` —
  `no-restricted-imports` has no `ImportExpression` visitor; the write half was genuinely open
  since `../api/client` resolves locally) plus the `.mts`/`.cts` half of the extension axis R-1
  closed for the JS family only; the audit gate **failed OPEN on a malformed exception** (every JS
  relational comparison with `undefined` is false, so an exception missing `review_by` silently
  swallowed its advisory — now a shape gate that names both the record and the advisory it was
  covering); and the R-4 class recurred **in the file R-4 rewrote** (`/Breaches/` can never match
  "Breach queue"). The lockfile-delta claim was false (§3). Honest residual, recorded: a COMPUTED
  import specifier is invisible to any lint rule — the argument for §6-P6.

## 2. Deferral / carry register — re-baseline

**The three Wave-12 TIPPED items: all genuinely PAID, verified in code.** (1) the
`select_overdue_breaches` N+1 → OPS-H1 (one statement, count-asserted, equivalence held under
refutation); (2) React-19/router-8 → FE-M1 (by fix, ~3 months before the cliff); (3) demo `_NOW`
freshness → OPS-H1 (seed-relative + backdated; the OQ-W12C-3d interim prohibition retired).
Previously-PAID items spot-checked still paid.

**New deferrals recorded by Wave 13, now carried in one place** (several existed only inside slice
prose): the FE toolchain debt (TS 5.9→7.0, eslint 9→10, jsdom 29→30, the six untypechecked
root-level guard tests — count corrected at this close); the month-end **holiday residual**
(2.8%, next real collision **2027-05-31** — MUST ride Wave-14's calendar work, recorded here so it
has a dated gate); the computed-specifier fence residual (§1); the rf **uniform-shift
limitation** (undetectable in-data by design — enforcement is the declared convention + vendor
onboarding diligence, a Wave-14 obligation); the ES-multiplier backend v2 (FL-1's recorded v2 —
**correction 2026-07-29 at the Wave-14 planning gate, OQ-W14P-7:** this row originally attributed
it to SR-1, whose record contains no such item; SR-1's own recorded v2 is the
autocorrelation-corrected annualizer) and the other standing scope-outs, unchanged.

**Register hygiene finding, folded:** the OPS-H1 rows and two trigger-fired items were stale in
the Wave-12 register text; the audit's two register survivors were doc-class and are corrected by
this close's record edits rather than a register rewrite (the register's next full sweep is the
closeout of the first Wave-14 slice, under the P1 rule if ratified).

## 3. Doc integrity — four false claims in governed records, corrected in place

1. **The registered methodology doc carried refuted arithmetic.** `sharpe_v1.md` A5 — the document
   persisted as the governed model version's `methodology_ref` — still said *"9×10⁶ still
   OVERFLOWS at ×√12"*, the claim SR-1's own Part 9 records as refuted (3.12×10⁷ fits
   `Numeric(20,12)`; the gate is a policy ceiling, not an overflow guard). The Part-9 fold had
   reached `bootstrap.py` but neither the doc nor the record's own Part 3 sentence.
2. **"Refused at capture" — no such refusal exists.** The SR-1 record's mis-dated-rf sentence
   ended with an enforcement claim its own paragraph refutes; corrected to DECLARED + diligence.
3. **CTRL-002 told three different stories**: its Status read "Planned" while the SR-1 record said
   "Operational", its SR-1 trace was filed under CTRL-003's row, and "Operational" was not in the
   matrix's own declared vocabulary. All three fixed; the row now cites this close's executed
   negative control as evidence.
4. **The lockfile delta was not "exactly 12."** The merged lockfile carries **22 entry-level
   changes**: 15 realizing the declared 12 (three are relocation pairs) + **4 unattributable
   dev-transitive bumps + a 3-entry hoist**. The declared "a 13th is a defect" gate did not fire —
   it was a human counting step. Record, ladder row, and both roadmap rows corrected.

Also stamped: **six decision records were unstamped-shipped** behind the closure gate's blind spot
— FE-M1 (still "RATIFIED … Implementation next" after two merges) and five stale for many waves
(P2-7, P3-8, P3-C2, PM-1, TD-1 — the platform's seventh governed number among them). All six
stamped from their real merge evidence, every cited sha verified `merge-base --is-ancestor` main.

## 4. Outward destination (rule 6b)

Wave 13 delivered what it ratified: **two governed numbers** (rolling risk, Sharpe — 25/40/133,
counts unchanged by the close), the operations-hygiene debt paid, and the platform floor moved to
React 19 / router 8 with the supply-chain exception retired **by fix**. The Wave-12 close named
"credibility of the numbers" as the distance-to-frontier; Wave 13 closed the analytics-breadth
half of that. **The remaining half is REAL DATA** — sector/industry/geography and concentration
are still 0% computable because no reference dimensions exist, and that is a data acquisition
fact, not an engineering one. Honest new residual from this close: the platform's unit tier
cannot see engine-typed defects (§1), so PG-tier pins are now the required home for any
column-type-sensitive guard.

## 5. Re-baseline — WAVE 14 PROPOSED: "REAL DATA THROUGH THE GOVERNED RAILS"

Per the standing tee (named at the Wave-12 close, carried through every Wave-13 record): vendor
data onboarding as the payoff wave — reference dimensions (sector/industry/country-of-risk),
concentration (REQ-CRD-003), liquidity tiers (REQ-LIQ-001/002), the ENT-006 holiday calendar
(with the 2027-05-31 collision as its dated forcing function), and the rf-capture vendor
diligence obligation. Slicing to be ratified at Wave-14 planning per the normal per-slice
discipline; this close proposes only the WAVE, not its internal sequence.

## 6. Process — the proposals at the gate

**P1 — the six-ledger omission sweep as a standing closeout step**, with the verify-on-`main`
clause AS AMENDED at the FE-M1 closeout: it is a **closeout** step, runs **after the last merge**,
covers **every artifact the slice claims** (review folds included), cheap form
`git merge-base --is-ancestor <sha> origin/main`. Premise verified TRUE by the audit (both cited
instances real; both refuter objections to the amended wording were themselves refuted 3/3).
**Recommend RATIFY.**

**P2 — the shared-tree mutation rules** (never `git add -A` under agents; grep the COMMIT; purge
`__pycache__` and re-run; isolated copies for finder mutations; a green gate from a contaminated
tree is not evidence). Premise TRUE; this close OBSERVED the rules and they cost minutes.
**Recommend RATIFY** (mechanisation optional, not a precondition).

**P3 — "a register entry is a claim about the code — verify it at planning recon."** The audit's
wording objection ("FE-M1 is register silence, not a false entry") was refuted 3/3; the class
reads naturally as false-OR-missing register state, three slices demonstrate it.
**Recommend RATIFY.**

**P4 — for a migration/dependency-floor slice, the pre-ratification pass runs as an EXECUTED DRY
RUN** — premise held (executing found V-1/V-2 where reading, grep, and the upstream guide all
missed them) **but the audit refuted the pin half**: the dry run's own declared-delta number went
stale and the human gate did not fire (§3.4). **Recommend RATIFY WITH THE BINDING CLAUSE:** a dry
run's numbers are dated point-in-time readings and MUST be re-measured against the merged artifact
at closeout — never carried forward as a pin.

**P5 — assert by evidence, not by absence.** Now three confirmed instances across two languages
(R-4 itself; the session-gate matcher in the same file; the pacing purpose test whose own comment
conceded the alternate path). Generalized wording: *a test's positive result must be produced by
the property under test; a by-absence assertion requires a positive control that fails when the
mechanism breaks.* **Recommend RATIFY.**

**P6 — NEW, minted by this close: pair every ENUMERATING guard with a NON-VACUITY FLOOR.** The
closure-stamp gate was broadened three times and went blind a fourth way each time; the import
fences are on their third un-enumerated bypass axis; the GS2 floors sat 3/8 below the real totals.
A matcher covers only the shapes someone thought of; a floor does not need to predict the next
shape — it only notices coverage falling. Executed exemplars now in-tree: the closure gate's two
floors (62≥50 records, 57≥38 done-slices; the old matcher drops coverage to 29 and the floor
fires), the GS2 exact census, the `_BINDING_PREDICATES` and `PURPOSE_*` set-equality censuses,
`test_ci_pg_coverage.py` as precedent. **Recommend RATIFY.**

## 7. Evidence and outcomes

Fold commits on `wave-13-close`: `396d513` (batch 1 — the two HIGHs + the fence axes) →
`7b14264` (batch 2 — the audit-gate fail-open + RM-1's mutation controls) → `4644226` (E501) →
`4992f2e` (the close's own stamp-pipe defect) → `ca55011` (batch 3 — NaN asymmetry, purpose gate,
pacing test, four record corrections) → `b131e89` (batch 4 — the twenty LOWs).

| Gate | Result |
|---|---|
| `make check` (post-fold) | **2201 passed / 480 skipped**; secret scan + docs-check green (with the widened closure gate + floors) |
| fresh-schema full-PG | **2681 passed / 0 failed, `PYTEST_EXIT=0`** — schema reset per the standing recipe (incl. the PUBLIC grant), `alembic upgrade head`, single run, captured to a plain log |
| downgrade smoke | `alembic downgrade base` clean → `upgrade head` restored → `alembic check` no drift (head stays `0055`; this close ships no migration) |
| `fe-check` | prettier + eslint 0 + `tsc` 0 + **32 files / 204 tests** |
| Mutation controls | **11 mutants across the batches, each killed by the fold's tests; restorations shown green** |
| CI | run **30455596382** (`866e10e`) observed **completed / `conclusion=success` across all six jobs** (Frontend, Backend, DB migration, API type drift, Documentation check, Secret scan) — written after observing the completed run, per R-3 |

**Ratified outcomes (USER, 2026-07-29 — "Proceed" on the briefed recommendations):** **P1–P6 all
approved as recommended** — P1 the six-ledger sweep + verify-on-main-after-last-merge; P2 the
shared-tree mutation rules; P3 register-entries-are-claims; P4 executed dry runs WITH the binding
re-measure clause; P5 assert-by-evidence with mandatory positive controls; P6 non-vacuity floors
on enumerating guards. All six now live as standing sections in
`claude_operating_instructions.md`. **WAVE 14 RATIFIED: "REAL DATA THROUGH THE GOVERNED RAILS"**
(§5) — direction only; the slice sequence ratifies at Wave-14 planning.
