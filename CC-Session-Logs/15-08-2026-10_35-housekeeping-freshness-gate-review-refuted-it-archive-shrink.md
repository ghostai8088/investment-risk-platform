# Session Log: 15-08-2026 10:35 - Housekeeping: the freshness gate, the review that refuted it, the archive shrink

## Quick Reference (for AI scanning)

**Confidence keywords:** housekeeping, current_state.md, freshness gate, check_docs.py,
_freshness_errors, _truth_headings, _strip_fences, _H2_HEADING, _MIN_TRUTH_HEADINGS,
_MIN_TRUTH_HEADING_SHARE, entry-point test, inert control, mutation battery, mutants.toml,
current-state group, M-CS1, adversarial review, four lanes, false negatives, false positives,
vacuity audit, 16 of 24 mutants survived, migration-head rule removed, 19 of 21 commits,
test_migration_head.py, hand-mirrored global fact, archive shrink, current_state_archive.md,
branch prune, refs/remotes/origin/HEAD, ls-remote, PUBLIC schema USAGE, irp_ops, migration 0003,
PYTHONDONTWRITEBYTECODE, pyc corruption, PR #215, PR #216, main 3ca0271

**Projects:** investment-risk-platform (multi-tenant governed investment-risk platform)

**Outcome:** Housekeeping done and merged in two PRs; a freshness gate was built, then an
adversarial review proved it could be unplugged from `main()` with every test still green, so its
worst rule was deleted and its tests rebuilt around the entry point and negative controls.

## Decisions Made

- **Housekeeping scope (user, AskUserQuestion):** items 1-4 (current_state fix + mechanical gate,
  session logs, local branch prune, pycache purge). Remote prune and archive shrink deferred, then
  requested later in the session and both completed.
- **The freshness check ships as a mechanical gate wired into `make check`**, not a promise to
  sweep harder (P7). User chose "Both, gate in make check".
- **Adversarial review run before merging** (user chose "Run the review first"), against my own
  recommendation-free framing. It changed what shipped.
- **After the review, the gate was SIMPLIFIED rather than fully patched** (user chose "Simplify the
  gate"): the migration-head equality rule was deleted outright.
- **The gate lives in `check_docs.py`**, not a new script, because `docs-check` is already a
  Makefile target and a CI job. No new wiring surface.
- **Head freshness returns to the closeout sweep** (operating instructions, ledger 4) rather than
  being mechanically enforced per-push.
- **Staleness-by-omission is explicitly NOT checked and is named as such in the code.** The
  candidate fix (anchor the top-block date to the newest `CC-Session-Logs` filename) was declined
  because it ties a repository gate to a personal workflow artifact.

## Key Learnings

- **A gate's tests must call the ENTRY POINT.** Deleting one line from `main()` left all twenty
  tests green while `check_docs.py` printed "Documentation check passed" and exited 0 over the
  exact defect it was built for. Helper tests prove the logic, not that it is reachable. Saved as
  a new standing memory.
- **"10 mutants, 10 killed" measured only the loud mutants.** An independent lane ran 24 more and
  16 survived. A self-run mutation battery is scoped by the author's imagination.
- **All twenty original tests asserted the gate FIRES; none asserted it stays QUIET.** Six false
  positives reached review as a direct consequence, each of which would have reddened CI on an
  honest edit. Negative controls are now half the file.
- **A control coupling a document to a moving artifact costs more than it buys.** The head-equality
  rule would have reddened CI on 19 of the last 21 migration commits, measured by checking each
  commit for whether it also touched `current_state.md`.
- **The `.pyc` corruption mechanism, named exactly:** CPython invalidates on (mtime, SIZE). Two
  mutants differing by the same byte count in the same second silently reuse the previous
  bytecode. Same-length edits (`if x:` -> `if False:`) are the NORM in mutation testing, so this
  is the common case. Always `PYTHONDONTWRITEBYTECODE=1` AND purge between mutants.
- **A mutant whose anchor is not found is a BROKEN mutant, not a survivor.** Two of mine "survived"
  because the anchor matched a comment above the code, or was mangled by shell quoting. Assert the
  anchor matched and grep the mutated file.
- **A witness must pin an invariant, not a shape.** My test required the live file to contain a
  `PRIOR CURRENT-TRUTH` block; the archive legitimately removed it. The Wave-17 close's witnesses
  are shipped slices, which can never un-ship — archive depth is not that kind of fact.
- **A comment can be false in a way tests cannot catch.** I wrote that alternation ORDER fixed the
  hyphen bug. Measured: with a lazy quantifier the earliest matching POSITION wins regardless of
  order, so reordering is an equivalent mutant. The character class `[- ]` is the fix.
- **The memory INDEX line is a load-bearing artifact.** I re-derived a documented 2026-07-07
  finding from scratch because `MEMORY.md`'s one-line summary had compressed away the half of the
  PG reset recipe that mattered.

## Solutions & Fixes

- **The freshness gate as shipped** (`scripts/check_docs.py`): strip fenced code blocks; parse
  dated truth headings with a captured `kind`; assert (a) only the document title may precede the
  first truth block, (b) exactly one CURRENT TRUTH and it is first, (c) dates never increase
  reading down, walked over EVERY adjacent pair; plus a count floor of 2 and an H2-only coverage
  ratio floor of 0.30.
- `_current_state_errors(root=...)` takes an injectable root purely so `main()` can be run against
  a fabricated tree in a test. That seam is the fix for the unplugging defect.
- **The restructure was done by a line-range splice script**, not hand transcription, so 500 lines
  of history moved byte-identically. Verified with `diff <(sed -n 'A,Bp' old) <(sed -n 'C,Dp' new)`
  → exit 0.
- **Local PG reset, the complete four-part recipe:**
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp;
  GRANT USAGE ON SCHEMA public TO PUBLIC;` then `DATABASE_URL=... alembic upgrade head`.
- **Safe remote branch prune:** derive the list from `git ls-remote --heads origin`, NOT from
  `git branch -r`, then re-verify `git merge-base --is-ancestor "origin/$b" origin/main` per branch
  at the moment of deletion.

## Files Modified

- `scripts/check_docs.py` — the freshness gate (added, then substantially rewritten after review).
- `apps/backend/tests/test_check_docs_current_state.py` — new; 20 tests, then rebuilt to 30 with
  half as negative controls plus a real entry-point test.
- `scripts/mutants.toml` — new group `current-state`, four mutants (M-CS1..M-CS4); 93 → 97.
- `docs/project_memory/current_state.md` — restructured newest-first, six factual errors fixed,
  then shrunk 680 → 172 lines.
- `docs/project_memory/current_state_archive.md` — 1299 → 1823 lines (seven blocks, 513 lines).
- `02_requirements/g2_adjudication_ledger.jsonl` — header corrected twice (comment lines only).
- `CC-Session-Logs/` — six previously untracked logs committed.
- Memory: `gate-tests-must-call-the-entry-point.md` (new), `shared-tree-mutation-hazard.md`
  (the exact `.pyc` trigger), `MEMORY.md` (index line for the PG recipe corrected + new entry).

## Setup & Config

- The CI `docs-check` job is bare `actions/setup-python` + `python scripts/check_docs.py` with
  **no dependency install at all**. Anything it imports must be stdlib. This killed the first
  version of the gate in 7 seconds.
- `ci.yml` runs `on: push, pull_request` with no path filters, so every job runs on every push.
- The mutation battery is `scripts/mutation_battery.py` + `scripts/mutants.toml`;
  `--check-anchors` is the cheap half wired into `make check`, `--group <name>` runs a group.
- `gh` at `~/.local/bin/gh`, working; `gh pr create` / `--watch` / `merge --merge`.

## Pending Tasks

- **The Wave-18 planning gate.** Scope not set; the owner's call. Three candidates: the structure
  block (the only G2-cleared rows), "Show it to someone", INGEST-1.
- **The 11-row advisory worklist is unread** — the `worklist` array in
  `02_requirements/g2_slice_scope.json` (NOT the proposals markdown; that pointer was wrong and is
  now fixed and enumerated in `current_state.md`).
- Nothing else is G2-adjudicated, so nothing else can enter a slice.

## Errors & Workarounds

- **The gate imported alembic; CI's docs-check has no dependencies.** Replaced with a stdlib
  parse of `migrations/versions`, cross-checked against alembic in the Backend job — then the
  whole rule was deleted at the review fold, taking the cross-check with it.
- **Started a full-PG run without resetting the schema first** and got a wave of collision
  failures. Killed it, reset properly, re-ran. Exactly the hazard the local-PG memory warns about.
- **`test_ops_bypassrls_reads_across_tenants` failed** with `UndefinedTable: audit_event`.
  Pre-existing on pristine `0cf3e31`, verified by stashing (with a file backup taken first).
  Cause: migration `0003` grants `irp_ops` SELECT on the tables but never schema USAGE, relying on
  the implicit grant `initdb` puts on the original `public` schema; `DROP SCHEMA public CASCADE`
  destroys it permanently. Already documented 2026-07-07.
- **The document title `# Current State` is itself a heading**, so the "nothing above the first
  truth block" rule fired on every valid document. Fixed with a positional allowance for exactly
  one title heading.
- **The archive shrink tripped my own coverage-ratio floor.** Diagnosis found the denominator was
  wrong on its own terms: `###` subsections live inside a block and can never be one, and twelve
  of them with nothing archived drops the ratio to 0.29. Denominator is now H2-only; floor value
  unchanged at 0.30.
- **The branch-prune candidate list contained a bare `origin` entry** — that is
  `refs/remotes/origin/HEAD`, whose `refname:short` has no slash, so `grep -v HEAD` missed it.
  Building from `git ls-remote --heads` removed the class.

## Key Exchanges

- User: *"Let's do some house cleaning first. What would you recommend?"* — produced a ranked list
  from measured state (145 pycache dirs, 16 merged local branches, 115 remote, 6 untracked logs)
  rather than generic advice.
- Plan mode toggled on and off mid-turn; work paused, then resumed.
- User chose **"Run the review first"** over merging without it. The review then found the gate
  could be unplugged, which nothing else would have caught.
- User chose **"Simplify the gate"** after the review, which deleted the head-equality rule rather
  than patching its six false positives.
- User: *"Can you just do the housekeeping items now?"* — the two deferred items, both completed.

## Custom Notes

None

---

## Quick Resume Context

Main is `3ca0271`, clean, CI green. Two housekeeping PRs merged: **#215** put the newest block back
at the top of `current_state.md` and added a freshness gate to `make check` and CI; **#216** shrank
the file 680 → 172 lines into the archive and pruned the remote from 117 branches to 1. The
session's real lesson is that a four-lane adversarial review refuted my own work: the gate could be
deleted from `main()` with all twenty tests still green, and my "10/10 mutants killed" had found
only the loud ones. The gate now has an entry-point test, negative controls as half its suite, and
four mutants in the committed battery. **Next: the Wave-18 planning gate — the scope is the owner's
call, and only the structure block has G2-cleared rows.**

---

## Raw Session Log

### Turn 1 — `/resume`

Read `CC-Session-Logs` (38 logs), the most recent summary (14-08 G2 gate), and
`docs/project_memory/current_state.md`. Verified HEAD `0cf3e31` and CI via the REST API: 9
check-runs, all `success`.

Reported: all four re-baseline gates built; G2 is a human act (P20) after six detector designs
were scored twice and none was usable; register at 105 rows; five rows adjudicated (REQ-PPM-006
through -010, all AMENDED); next is the Wave-18 planning gate.

### Turn 2 — User: "Let's do some house cleaning first. What would you recommend?"

Measured the actual state rather than guessing:

- 38 session logs, **32 tracked, 6 untracked**, not gitignored
- **16 local branches, every one merged into main**
- **115 remote branches, 0 open PRs**
- **145 `__pycache__` dirs, 1,481 `.pyc`**
- `current_state.md` 631 lines; `current_state_archive.md` 1,299

Then found the item that mattered. `current_state.md` line 3 read:

```
> ## ⚠️ CURRENT TRUTH (2026-08-08, latest) — read this block; everything below it is HISTORY
```

with its `NEXT` (line 99) pointing at the ONBOARD-1a implementation plan — merged as PR #191,
twenty-three merges earlier — and stating migration head `0068_entitlement_request` when
`migrations/versions/` held `0070_app_role`. The real current truth sat at line 105, *below* the
block instructing the reader to treat everything below it as history.

Line 162 of the same file diagnosed the identical class at the Wave-17 close ("P1 ledger (4) went
unswept across five consecutive slice closeouts") — and the fix applied then had been to append a
newer block *underneath* the stale one.

Recommended items 1-5, asked two questions.

**User answers:** "Items 1-4 (Recommended)" and "Both, gate in make check (Recommended)".

### Turn 3 — Execution

Purged pycache (145 → 0). Deleted 16 merged local branches. Confirmed migration head single at
`0070_app_role`. Read the G2 ledger: 8 entries, 5 distinct rows, all AMENDED.

**Restructure.** Wrote a new top block, then spliced by line range with a Python script carrying
assertions on every boundary, so history moved verbatim. Verified by sorted-line-multiset diff:
35 lines removed, all accounted for (the re-baseline block carried forward into the new top block,
plus two demoted headings and two rewritten pointer sentences).

**Gate v1** added to `check_docs.py`: heading-date ordering + migration-head equality. First run
failed on `2026-07-29c` — the disambiguating letter breaks a trailing `\b`. Fixed with a lookahead.

**Probed the guard against the real pre-fix file** (`git show HEAD:...`): 3 errors — 3 headings
claiming CURRENT TRUTH, a 2026-08-12 block below a 2026-08-08 one, and the `0068` head claim.

15 tests written. 7 mutants, 7 killed, `check_docs.py` restored byte-identical from a file backup.

`make fix` → `FIX_EXIT=0`. `make check` → `CHECKS_EXIT=0`, 2804 passed.

**Full-PG:** reset + migrate + pytest → **1 failed**, `test_ops_bypassrls_reads_across_tenants`,
`UndefinedTable: audit_event`. Backed the working tree up to scratch, stashed, re-ran on pristine
`0cf3e31` — **fails identically**. Popped, verified byte-identical recovery against the backup.
Diagnosed: `irp_ops` has SELECT on the table but no schema USAGE; migration `0003` never grants it;
`DROP SCHEMA public CASCADE` destroys the implicit `initdb` grant. Proved the fix
(`GRANT USAGE ON SCHEMA public TO PUBLIC`) — 8 passed.

Four commits, pushed, **PR #215** opened.

**CI failed in 7 seconds** on my own gate. The `docs-check` job is bare `setup-python` +
`python scripts/check_docs.py` with no dependency install; the gate imported alembic. Replaced with
a stdlib parse of `migrations/versions`, plus a test asserting it equals alembic's answer, run in
the Backend job where alembic exists. Reproduced the CI condition locally with an import-blocking
meta-path hook: `NO_ALEMBIC_DOCS_EXIT=0`.

Made the two floors testable via an injectable `versions_dir`. 10 mutants, 10 killed. Committed and
pushed. Full-PG re-run on the final tree: `PG_PYTEST_EXIT=0`, 3,432 passed.

### Turn 4 — The review gate

Asked whether to merge without the adversarial review, given `make check`, full-PG and CI were
green. **User chose "Run the review first (Recommended)."**

Verified CI against the head SHA directly (not the watch's exit 0): 18 check-runs, all `success`.

Launched four lanes in parallel: false negatives, false positives, restructure audit, test vacuity.

### Turn 5 — Lane results

**False positives.** Rule 3 (head equality) would have reddened CI on **19 of the last 21**
migration commits, measured commit-by-commit; it re-mints a head literal that the ratified
2026-08-09 fold consolidated to one line; and it was not load-bearing on the real defect. Plus five
more false positives with executed repros: fenced quotations, hard-wrapped head claims, a current
block narrating a past head, the unhyphenated `Prior current truth`, and the `_MIN_TRUTH_HEADINGS`
floor blocking the ratified archive act with a message giving wrong advice.

**False negatives.** F1: a stale banner *above* the current block — `#`, `#####`, bold — is
invisible; five spellings passed carrying the 2026-08-14 defect verbatim. F2: the gate never asks
whether a new block was written at all; the file as it stood on 08-12, eleven PRs behind, returns
`[]`. F3: `max(dates)` is an escape hatch — "re-confirmed 2026-08-14" is six characters and
silences the ordering check. Plus `_top_block` truncation and `_HEAD_CLAIM` resolving only 5 of 12
head statements in the file.

**Restructure audit.** Content integrity confirmed byte-identical. Then six factual errors in my
new top block, two blocking: the advisory-worklist pointer named the wrong file, and "G1 … 8
controls" was G1+G3 at a stale moment (G1 has six; the file holds 19). Plus the eight-entry
arithmetic not closing, the "same day it was built" ambiguity, one-sided Decimal timings, and a
truncated acceptance quote.

**Test vacuity.** 24 mutants, **16 survived**. The worst: deleting `errors.extend(_current_state_errors())`
from `main()` left all 20 tests green while `check_docs.py` exited 0 over the real defect. Also
found `scripts/__pycache__` silently corrupting mutation runs.

### Turn 6 — The fold

Asked how much should ship. **User chose "Simplify the gate (Recommended)."**

Removed the head-equality rule entirely, with `_HEAD_CLAIM`, `_top_block`,
`_migration_head_from_source`, `_actual_migration_head`, `_MIN_MIGRATIONS`. Added: fenced-block
stripping, `kind`-based classification, first-date-not-max, the positional title allowance, the
adjacent-pair walk, a count floor of 2 with an honest message, and a coverage ratio.

Rebuilt the tests to 26 with half as negative controls, and a real entry-point test that
monkeypatches `check_docs.ROOT` and calls `main()`.

Re-ran the review's survivors: 9 of 10 killed; the 10th was an equivalent mutant, proven by
comparing both alternation orderings on the exact input — which showed my own code comment was
false. Corrected it.

Applied the six factual corrections. Registered four mutants in `mutants.toml` (93 → 97); group
`current-state` **4/4 killed**.

`CHECKS_EXIT=0` (2,815) · full-PG `PG_PYTEST_EXIT=0` (3,438) · CI 18/18 `success` on `b756415`,
verified against the SHA. **Merged #215** = `c1b365f`. Verify-on-main: gate green from the merged
tree, still fires on the pre-fix file (2 errors now — the third was the removed rule).

Memory updated: new `gate-tests-must-call-the-entry-point.md`, the exact `.pyc` trigger added to
`shared-tree-mutation-hazard.md`, and `MEMORY.md`'s PG-recipe index line corrected.

### Turn 7 — User: "Can you just do the housekeeping items now?"

**Remote branches:** all 116 verified merged. Built the list from `git ls-remote --heads` after
catching a bare `origin` entry (= `refs/remotes/origin/HEAD`). Deleted 114, then the two spent
housekeeping branches. **117 → 1.** Verified `origin/main` unchanged and commits from deleted
branches still reachable.

**Archive shrink:** measured first — archiving to 2 blocks would trip my own share floor (2/11 =
0.18). Diagnosed the denominator as wrong on its own terms: `###` subsections can never be blocks,
and twelve of them with nothing archived drops the ratio to 0.29. Changed to H2-only; floor value
unchanged at 0.30. Three tests pin both directions.

Moved seven blocks (513 lines) to the archive. Integrity: 0 lines unaccounted for,
`RANGE_DIFF_EXIT=0`. Fixed two directional references the move made false. `current_state.md`
**680 → 172 lines**.

`make check` then failed on my own witness test, which required the live file to contain a
`PRIOR CURRENT-TRUTH` block — a shape, not an invariant. Moved the branch witnesses to synthetic
input; the real-file test now asserts only what holds at any archive depth.

`CHECKS_EXIT=0` (2,819) · battery 4/4 · full-PG `PG_PYTEST_EXIT=0` (3,442) · CI 18/18 `success` on
`86d7ff4`, verified against the SHA. **Merged #216** = `3ca0271`.

### Final state

Main `3ca0271`, clean, CI green. `current_state.md` 172 lines, archive 1,823. Remote: 1 branch.
Local: 1 branch. Battery 97 anchors, group `current-state` 4/4.
