# Session Log: 14-08-2026 16:29 - G2 built as a human gate, and the structure block adjudicated

## Quick Reference (for AI scanning)

**Confidence keywords:** G2, P20, adjudication ledger, g2_adjudication_ledger.jsonl,
g2_slice_scope.json, g2_adjudicators.json, check_g2_adjudication.py, G4, capability coverage table,
close review, NO_RELIABLE_GATE_EXISTS, detector bake-off, consensus ensemble, re-baseline part 2,
REQ-PPM-006, REQ-PPM-007, REQ-PPM-008, REQ-PPM-009, REQ-PPM-010, exposure_type, uniqueness key,
aggregation contract, node-scoped runs, rollup identity, mandate declined, SCOPE-03, name inertness,
FX triangulation, fx_legs, convert_amount identity, plain writing style, mechanism versus outcome,
PRs #208 #209 #210 #211 #212 #213 #214, main 0cf3e31

**Projects:** investment-risk-platform (multi-tenant governed investment-risk platform)

**Outcome:** All four re-baseline gates built; the register reached 105 rows with every SCOPE
commitment cited; and the first five requirement rows were adjudicated by the owner under P20, who
refuted the proposer on three of them.

## Decisions Made

- **G2 is a HUMAN act, not a script (ratified).** Six detector designs were built and scored twice
  by independent agent fleets. All catch the known-bad rows; none is usable. The mechanical half
  checks paperwork only.
- **G4 binds from the Wave-18 close**, and checks the wave's OWN contribution rather than the
  platform's running total, so it cannot go stale and force a historical document to be rewritten.
- **Seven coverage gaps paid** in re-baseline part 2: capability 13.3, 16.2, and all five SCOPE ids.
  Only 20.2 and 20.4 remain, both deliberate.
- **Five structure rows adjudicated, all AMENDED.** REQ-PPM-006 through -010.
- **Mandate comparison DECLINED (REQ-PPM-009).** The owner rejected the row's premise: mandate
  compliance is a compliance function, not risk. SCOPE-03's declared risk coverage does not include
  it, and a mandate rule engine would duplicate the shipped limit framework. **This supersedes the
  Q4 answer ratified the previous day**, recorded as a supersession with two triggers.
- **REQ-PPM-010 takes the expensive option:** a reader must SEE the conversion path on a screen,
  chosen over leaving it as API evidence or dropping the triangulation marker.
- **Plain writing style adopted as a standing preference**, and it applies to requirement text, not
  only conversation.

## Key Learnings

- **G2 cannot be automated, and this was measured rather than argued.** On the best detector, with
  only REQ-PPM-004's acceptance varying: `"the rollup is NOT implemented; returns 501"` → PASS; the
  register's own repair → FLAG; the real defect plus six words `"; the hierarchy is recorded"` →
  PASS. **The check passes the bug and blocks the patch.**
- **The consensus ensemble was the trap.** Requiring 4 of 5 detectors to agree looked superb on the
  original 74 rows (3 extra flags, all genuine) and then caught **3 of 10** defective rows written
  fresh, **0 of 4** in fresh wording. The good result was five detectors fitted to the same 74
  sentences.
- **THE AUTHOR'S OWN AMENDMENTS WERE DEFECTIVE IN THE SAME WAY THE DETECTORS WERE.** Four of five
  banned a MECHANISM where they should have required an OUTCOME, and a banned mechanism rejects
  correct implementations. The rule that fell out: *state an outcome the degenerate build cannot
  produce, never forbid a route to it.*
- **The user out-adjudicated the proposer three times.** Delta-adjusted exposure only differs for
  non-linear payoffs, so a clause requiring notional and delta to differ would reject every correct
  linear-derivative build. "What about a two-level portfolio" found a clause that could be misread
  as validation and reject valid data. "Isn't mandate compliance out of scope for risk" was correct
  and their own scope document was the evidence.
- **Two clauses passed with no code written.** PPM-009's rename check (nothing reads the name) and
  PPM-010's same-currency check (`convert_amount` returns the amount untouched). Both relabelled in
  the rows as REGRESSION GUARDS, not evidence of work.
- **A control's premise can be paid out from under it.** `test_an_uncited_SCOPE_commitment_FAILS`
  relied on an uncited SCOPE id existing; part 2 cited all five, so it silently stopped testing
  anything. It now INJECTS a commitment.

## Solutions & Fixes

- `scripts/check_g2_adjudication.py` — hashes (business purpose, acceptance), requires a rostered
  human adjudication, rejects `MODEL:` adjudicators and duplicate ledger keys, demands a repair
  commit for AMENDED, exits 2 rather than reporting a pass it cannot trust.
- **The vacuity interlock**, added after the second bake-off run found the first version exited 0
  with an empty slice scope. A declared slice with an empty scope, or an undeclared scope with no
  written reason, exits 2.
- **Per-table header binding.** The gate matched `| REQ | Title |` and was blind to CAP-21's
  `| ID | Requirement | Cap |`. Fixed twice: first by content-matching (weaker — a broken header was
  skipped and its rows parsed with another table's columns), then by binding every row to the header
  of the table it is in.
- `g4_errors()` in `check_capability_coverage.py` + `close_reviews()` with a 17-file discovery floor.
- Ledger flow that works: amend the row → commit → compute the NEW hash → append the entry naming
  that commit → commit the ledger.

## Files Modified

- `scripts/check_g2_adjudication.py` (new), `02_requirements/g2_adjudication_ledger.jsonl` (new),
  `g2_adjudicators.json` (new), `g2_slice_scope.json` (new).
- `apps/backend/tests/test_g2_adjudication.py` (new, 21 controls);
  `test_capability_coverage.py` (19 controls, G4 + the rewritten SCOPE control).
- `scripts/check_capability_coverage.py` (G4), `Makefile` (`g2-check`), `.github/workflows/ci.yml`.
- `02_requirements/requirements_backbone.md` (74 → 105 rows; PPM-006..010 amended, several twice),
  `requirements_traceability_matrix.md` (31 rows behind, levelled),
  `capability_coverage_baseline.json` (seven gaps discharged), `product_rebaseline.md` (§4 rewritten,
  §6 G2/G4 recorded, Q4 superseded).
- `docs/project_memory/claude_operating_instructions.md` (P20 + G4), `current_state.md`.
- `10_delivery_backlog/g2_adjudication_proposals_wave18.md` (new).
- Memory: `plain-writing-style.md` (new), `MEMORY.md`.

## Setup & Config

- `make g2-check` added to `make check`; a CI step added alongside capability coverage.
- The G2 roster is `02_requirements/g2_adjudicators.json`, currently one handle: `ghostai8088`.
- **One ratified clause deliberately NOT implemented:** *adjudicator != PR author*. Every PR here is
  authored by the sole human, who is also the only valid adjudicator, so it would fail every run or
  be deleted. Recorded in the code with its reason.
- Local PG recipe unchanged; `DATABASE_URL` (not `IRP_TEST_DATABASE_URL`) is what alembic reads.

## Pending Tasks

- **The Wave-18 planning gate.** Scope not set. Three candidates: the structure block (the only rows
  currently cleared), "Show it to someone", or INGEST-1. Recommendation is the structure block, on
  the argument that PPM-006/007 change the shape of exposure data and demo screens built over a grain
  about to change get built twice.
- Nothing else is adjudicated, so nothing else can enter a slice.
- The advisory worklist of 11 flagged rows is unread.

## Errors & Workarounds

- **The first bake-off was NOT dead.** It completed after ~2.9 hours. The earlier conclusion that it
  had died was wrong; the relaunch produced a second independent run, which proved useful.
- **The vacuity defect inside the G2 gate itself** — exit 0 with an empty scope, in the fold written
  to prevent exactly that. Found by the second run, now a refusal with its own control.
- **A reshuffle control started failing** after the content-matching header fix, correctly: one
  broken header was being skipped rather than stopping the gate. Fixed by per-table binding.
- **My anchor guess was wrong** in the staleness control (the acceptance text had been rewritten at
  the re-baseline). The assert caught it.
- **`alembic` reads `DATABASE_URL`**, not `IRP_TEST_DATABASE_URL` — one failed migrate before
  noticing.

## Key Exchanges

- Owner asked what "exploit" means, and the word was wrong: it means passing the test without doing
  the work, not an attack. Offered "loophole" as a replacement.
- Owner asked for two options and their implications on REQ-PPM-006, in plain English. That framing
  produced a third and better answer (relax which second measure counts).
- Owner: *"Isn't funded/unfunded at the investor level?"* — sent me to read the model, which showed
  both proposed examples were unbuildable.
- Owner: *"I really don't like Opus 5's writing style."* Saved as a standing preference; applies to
  requirement text too.
- Owner: *"Why does it matter if holdings match the mandate? Isn't that compliance, not risk?
  Objective answer, please."* — the answer was that they were right, with SCOPE-03 as evidence.

## Custom Notes

None

---

## Quick Resume Context

All four re-baseline gates are built and the register is at 105 rows with every SCOPE commitment
cited by a requirement. G2 turned out to be unautomatable — six detectors were built and scored twice
and none works — so it is a human act (P20) with a bookkeeping ledger that proves the act happened
and lapses it when the text changes. The owner then adjudicated the first five rows (REQ-PPM-006 to
-010), amending all five, rejecting one row's premise outright, and refuting the proposer's own
amendments on three. **Next: the Wave-18 planning gate — set the slice scope, which is the owner's
call.** Main at `0cf3e31`, clean, CI green.

---

## Raw Session Log

The authoritative turn-by-turn transcript is the Claude Code JSONL at:

`~/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`

Referenced rather than reproduced, on the same ground as every prior log here: writing a "verbatim"
transcript from memory would fabricate a record. The chronology below is drawn from the merge history
and is verifiable against it.

### Chronology

1. **#208** — G2: the gate that cannot be a script. P20 minted, ledger created empty, 20 controls.
   The vacuity interlock added after the second bake-off run found the hole.
2. **#209** — G4: close reviews carry the capability coverage table from Wave 18 on, 10 controls.
   **All four gates built.**
3. **#210** — Re-baseline part 2: 19 rows, register 74 → 105, RTM levelled from 31 behind, seven
   coverage gaps paid.
4. **#211** — G2 adjudication proposals for the structure block, PROPOSED.
5. **#212** — the PPM-006 refutation folded in, and the three defects it exposed in the other
   amendments.
6. **#213** — the structure block adjudicated: five rows, five verdicts, ledger at 5 current.
7. **#214** — PPM-006 and PPM-007 rewritten in plain sentences and re-adjudicated.
