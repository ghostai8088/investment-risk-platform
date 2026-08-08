# FK-1 slice record — foreign keys became true on the unit tier

**Wave 16, slice 3 of 3.** Remit: `fk_1_remit.md`. Branch `fk-1-foreign-keys`.

## 1. What shipped

`irp_shared.db.session.make_engine` now installs `PRAGMA foreign_keys=ON` on every SQLite engine it
builds (dialect-guarded; PostgreSQL untouched — it always enforces). For the platform's whole life
before this slice, the unit tier silently accepted an INSERT naming a parent that does not exist
while PostgreSQL refused it, and the whole suite was green over rows that could never exist in
production.

| Artifact | Where |
|---|---|
| The enforcement (factory, not opt-in) | `irp_shared/db/session.py::make_engine` |
| The pins: negative + positive control, factory-property test | `tests/test_db_foreign_keys.py` (new) |
| 151 fixtures given genuine parents | 14 test suites (census below) |
| RPT-1's interim per-suite listener RETIRED | `tests/test_report_generation.py` |
| The remit (outcomes + proofs) | `fk_1_remit.md` |

No production code changed beyond the factory listener. No entity, permission, migration, or audit
code. Migration head unchanged at `0065`.

## 2. Gates, with captured exit codes (P14)

Measured at the merge head, tree verified unchanged during both full gates.

| Gate | Result |
|---|---|
| The measurement, BEFORE | **104 failed + 47 errors** across 14 suites with the pragma flipped, at `a37db29` |
| The measurement, AFTER | full unit tier **`FULL_UNIT_EXIT=0`** — `2554 passed, 602 skipped` |
| `make check-all` (both tiers) | **`CHECK_ALL_EXIT=0`** (tree verified unchanged during the run) |
| Full-PG battery, schema reset then migrated to head | **`PG_PYTEST_EXIT=0`** — `3159 passed`, zero skips |
| Mutation battery, 4 controls | **`MUTATION_EXIT=0`** — 4/4 on BOTH runs; the first run's green was over a tree its own F-D arm had corrupted (§4b), so the battery was corrected and re-run |
| Lint + typecheck | **`LINT_TYPECHECK_EXIT=0`** |

**The carried number was STALE, and re-measuring was the first act of the slice.** RPT-1 carried
"103 remaining across 12 suites". At this head the true figure was **151 across 14** — two backend
endpoint suites (`test_breaches_endpoint` 34, `test_schedules_endpoint` 13) and
`test_benchmark_series` had joined since that census, because suites written after RPT-1 inherited
the blind engine. That decay is itself the argument for the factory fix: an opt-in control cannot
cover suites that do not exist yet.

## 3. How the 151 were fixed, and how they were NOT

Fourteen agents, one suite each, under an explicit doctrine: seed the GENUINE parent (economically
plausible, in the suite's own helper style — most fixes were ONE helper because whole suites flowed
through a single `_seed_*`), and five individually forbidden shortcuts — disabling the pragma,
nullable-ing a column, weakening or deleting an assertion, deleting a test, touching any file
outside the assigned suite. Anything smelling of a production defect was a FINDING to report, not
an edit to make. **Zero findings were reported; zero doctrine violations found.**

The independent doctrine audit re-ran the census greps over the combined diff: no `PRAGMA` in any
test diff, no `nullable`, no deleted tests, no placeholder values, and exactly ONE deleted `assert`
— `test_scheduler_dispatch`'s comparison against a fabricated literal run id, replaced by a
strictly stronger pair (the fake now creates a genuine FAILED run; the ledger row is compared
against the id actually created, and creation itself is asserted).

**The workflow's own auditor returned prematurely (“suite at ~43% and running”), and its report was
DISCARDED rather than trusted** — an audit that did not finish is not an audit. Its steps were
re-executed in full at the coordinator level; the numbers above are from that re-execution.

## 4. The controls, and what made them fire

- **Negative control**: a governed VaR row whose FIVE parents are all genuine EXCEPT the run —
  `pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed")`. The match clause is
  load-bearing: the first draft seeded nothing, and it passed on a NOT NULL violation of a
  different column — an `IntegrityError` for the WRONG reason, a refusal test proving nothing about
  the constraint. The two controls now differ by exactly one thing.
- **Positive control**: the identical row with the real run — accepted.
- **Factory-property test**: `PRAGMA foreign_keys` asked of the ENGINE, so the property stays
  attached to `make_engine` rather than to whichever suite happens to exercise it.
- **Mutation battery, 4/4**: the listener deleted; the pragma flipped to OFF; the dialect guard
  inverted; and a whole fixed suite REVERTED to its `main` state (red under the enforced factory —
  the fixture fixes are load-bearing, not incidental).

## 4b. The battery DESTROYED a fix, and the full gate caught it

**The slice's own worst defect was in its verification harness.** The suite-revert mutant restored
`test_sharpe.py` with `git checkout <branch> -- <file>` — which restores the COMMITTED state, and
the fixes under test were uncommitted working-tree changes. The "restore" silently reverted the
sharpe fix to its broken state, and the truncated `git status | head -20` hid the file dropping off
the modified list (it sorts after the cutoff). Both full gates then went RED — `PG_PYTEST_EXIT=1`,
29 failures, all sharpe; `CHECK_ALL_EXIT=2` — which is P14 doing precisely its job: the earlier
green was quoted, the corruption happened after it, and the re-run at the frozen tree refused to
carry it forward.

The fix was recovered from the fix agent's own transcript — its two Edit calls re-applied
byte-identically (2/2 anchors matched first try) and the suite went back to `34 passed`. Two rules
fall out, both now mechanical: **a mutation battery may only ever restore the exact bytes it
displaced** (a file backup, never git — git restores a STATE, not YOUR state), and **tree censuses
never go through `head`** — the pipe hid exactly the line that mattered, which is the same
truncating-pipe defect DATA-1 recorded about a different census. The battery's F-D arm now backs up
before reverting and restores in a `finally`; the corrected battery re-ran 4/4 with the fix proven
present afterwards.

## 5. Carries

| | | Host |
|---|---|---|
| (a) | The PG tier and the unit tier still differ on FK *timing* (SQLite checks at flush, immediate; PG through the same ORM path also at flush — but DEFERRABLE constraints, if ever introduced, would diverge). No current schema uses them | Noted for the migration that first introduces one |
| (b) | `test_private_capital.commitment_version_id` and `FactorExposureResult.instrument_id/factor_id` are deliberate non-FK provenance echoes — the census accepted them because the MODELS declare no constraint. If they ever become FKs, those suites join the census | The mint that adds the constraint |

## 6. Scrutiny applied

| Stage | Result |
|---|---|
| Fresh measurement before building | The carried 103 refuted: 151 across 14 |
| 14-agent fan-out under doctrine | All suites GREEN, exit codes quoted per suite; zero findings |
| Doctrine audit (re-executed after the agent's premature return) | Census clean; the one deleted assert verified strictly stronger |
| Mutation battery | 4/4 twice — the first run itself corrupted the tree (§4b); corrected, re-run, fix proven present after |
| The guard's own first draft caught | The negative control initially passed for the wrong reason (NOT NULL, not FK) — caught by the match clause it was born with, fixed by the single-difference discipline |

Counts **MEASURED** on a fresh collect at the merge head: **3,159** collected platform-wide
(3,156 at the REPRO-1 close + the three FK guard tests).
