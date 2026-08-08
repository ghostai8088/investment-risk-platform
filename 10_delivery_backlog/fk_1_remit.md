# FK-1 remit — foreign keys become true on the unit tier

**Wave 16, slice 3 of 3.** Branch `fk-1-foreign-keys`. Sequenced at the Wave-15 close (§7-F) and
the Wave-16 gate; the carry is RPT-1's, recorded with a measured number and the instruction "do NOT
flip the pragma globally without budgeting for 103 fixtures". This slice is that budget.

Remits state OUTCOMES and PROOFS (the DEP-1 operating model), not steps.

## Outcomes

1. **Every SQLite engine built by `irp_shared.db.session.make_engine` enforces
   `PRAGMA foreign_keys=ON`.** In the factory, dialect-guarded — not per-suite opt-in, because an
   opt-in control is a control only for the suites that opted in, and the next suite is born blind.
   PostgreSQL is untouched (always enforces).
2. **Every test fixture seeds genuine parents.** No test satisfies the FK by weakening anything:
   no nullable-ing of columns, no dropped constraints, no suite-local pragma-off, no assertion
   deletions. Fixture values stay economically plausible (the TD-1 standing rule).
3. **RPT-1's suite-local listener is retired** — redundant once the factory enforces, and two
   mechanisms for one property is how the next reader trusts the wrong one.
4. **The count goes to zero and stays there structurally**: with enforcement on, the full unit
   suite is green, and the enforcement itself is pinned by tests that fire.

## Proofs

- **The measurement, before and after, quoted**: 104 failed + 47 errors across 14 suites at
  `a37db29` with the pragma flipped (measured this slice — the carried 103 was stale: two backend
  endpoint suites and one more shared suite had joined since RPT-1's census). After: 0, full suite,
  exit code quoted.
- **A negative control that FIRES (P9)**: a child row naming a nonexistent parent must raise
  `IntegrityError` on an engine from `make_engine`; its sibling positive control (genuine parent →
  accepted) proves the test can tell the difference.
- **Mutation battery**: deleting the factory listener must redden the negative control; the battery
  reports an unmatched anchor as a SURVIVOR, never a pass.
- **Both tiers**: `make check-all` and the full-PG battery (schema reset first) at the frozen tree,
  exit codes quoted (P14). CI to green; the P16 citation check at the PR boundary.

## Non-goals

- No production-code changes beyond the factory listener. If a fixture fix appears to require a
  production change, that is a FINDING to report, not an edit to make.
- No new entities, permissions, migrations, or audit codes.
