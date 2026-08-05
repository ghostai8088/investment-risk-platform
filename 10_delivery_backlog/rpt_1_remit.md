# RPT-1 Remit — the first reproducible risk report

> **Status: RATIFIED 2026-08-05 — OQ-RPT-1-1…4 ALL as recommended** ("proceed" on the briefed
> gate): v1 content = the §2.1 spine (total VaR + ES, concentration, liquidity, rolling
> risk/Sharpe); HTML print-clean, no PDF pipeline; the three OQ-W15P-6 carries each recorded
> **evaluated / does-not-fire** with triggers carried forward (breach echoes → breaches in report
> content; alpha-3/M49 → a regulatory-format section; effective-number → a concentration detail
> view); the report record mints **ENT-072** with its canonical registry row. Wave-15 opener 2, sequenced after DEP-1
> (CLOSED 2026-08-05, PRs #173/#174) by ratified OQ-W15P-1 — deliberately, because DEP-1 is what
> makes this slice's central claim *testable*: "regenerates identically" can now be proven across a
> real process boundary, including from a restored backup.
>
> **This is the first remit written under the 2026-08-05 operating model.** It defines the GOAL,
> the SCOPE BOUNDARY, the INVARIANTS, and the NAMED PROOFS with their expected evidence. It does
> NOT define implementation steps: DEP-1's four failed deploy attempts were each killed by a fact
> no planner could have known, and a remit that scripts the keystrokes either gets followed off a
> cliff or turns every discovery into a replanning round-trip. The builder is free on method and
> REQUIRED to record deviations. A fresh-context audit runs before merge.

## Goal

**REQ-RPT-001 minimal core** (verbatim: *"Generate governed, reproducible risk reports … Report
binds run IDs; regenerates identically (BR-9)"*): ONE report, for one portfolio as of one date,
over ALREADY-SHIPPED governed numbers — run-ID-bound, snapshot-pinned, model-version-stamped —
that a CRO, board member, or regulator can read, and that **regenerates byte-identically** from
its bound run IDs. This is the first artifact a buyer or examiner asks for, currently wholly
unowned across 24 governed families, and the first end-to-end exercise of the thesis §2.3
reproducibility claim by a human-consumable artifact.

## Pre-work that lands FIRST (ratified OQ-W15P-2, not yet executed)

A report renders `methodology_ref`, and the measured state (Wave-15 planning F4) is 24 resolving /
**1 dangling** (`pure_private_factor_v1.md`, never existed) / **2 prose**. So, before the report:

1. **Write the three missing methodology docs** (pure-private, concentration, liquidity) — the
   ratified OD-P3-0-C standard says mandatory, and this is the wave that renders them.
2. **ONE census over every `*_METHODOLOGY_REF` constant that FAILS on a non-resolving path**,
   replacing the 14 hand-copied per-family doc tests (P6/P8/P10 form).

## Scope boundary

- **IN:** one registered report definition (its identity, sections, and bound families are the
  gate's OQ-1); a generation verb that binds run IDs/snapshot IDs/model versions at generation
  time; a durable record of each generated report (what was bound, when, by whom); one
  human-readable rendering; the regeneration verb + its identity proof; CTRL-009 moved
  Planned → Implemented on OBSERVED evidence only.
- **OUT (explicitly):** scheduling of reports (SCH machinery exists; wiring it is a later slice);
  PDF typography beyond a clean printable page; any NEW governed number, entity beyond what the
  report record itself requires, or model; dashboards; distribution/e-mail (the webhook sink
  exists; report distribution is its own decision); any regulatory FORM (an N-PORT-shaped artifact
  is a different slice with a different evidence bar).

## Invariants (each becomes at least one named proof)

| # | Invariant | The proof that makes it real |
|---|---|---|
| I1 | The report binds run IDs, snapshot IDs and model-version IDs **at generation time**; nothing in it is re-derived from live tables at render time | A mutation that re-reads a live table at render must fail a test |
| I2 | **Regeneration is byte-identical** from the bound IDs | The BR-9 proof: generate → regenerate → hash-equal. And the DEP-1 dividend: regenerate **after a backup/restore cycle** on the deployed stack — hash-equal across the process boundary |
| I3 | A report whose bound inputs have been superseded regenerates **the original**, not the corrected view — and SAYS so | A correction is applied to a bound input; regeneration is hash-equal AND the rendering carries the as-of/known-at distinction |
| I4 | A report over a run that does not exist, is not COMPLETED, or belongs to another tenant is **REFUSED, fail-closed, with nothing persisted** (P9: each refusal FIRES in a test; the cross-tenant arm uses a REAL foreign-owned run, not a random UUID — the LIM-2/DEP-1 lesson) | Hostile-caller tests asserting the refusal AND the absence of state |
| I5 | Every number rendered carries its `GovernedValue` provenance (run ID, snapshot verification, model version, methodology ref) — and every rendered `methodology_ref` **resolves** | The census from the pre-work, plus a rendering test that fails on a dangling ref |
| I6 | The report record is IA append-only on the governed rails (audit event, lineage, RLS) — same evidence bar as every governed artifact | The standard PG-tier battery of RLS/append-only tests for the new table |

## Named proofs, with expected evidence (P14 applies to every one)

1. `make check-all` — exit code quoted.
2. Full-PG fresh-schema battery — outcome census + `PYTEST_EXIT` quoted; exclusive DB per OQ-W15P-9.
3. The BR-9 identity proof (I2), including the **restore-cycle regeneration** on the deployed
   stack — extend `stack-proof` or the deploy script; either way it runs in CI, not from memory.
4. Every refusal in I4 executed with the hostile input, mutation-proven where a guard is new.
5. CI to green on the head SHA — run conclusion quoted; merge only after; P1 sweep after the merge.

## Decision points for the gate (Tier-3 — the user's, not the builder's)

- **OQ-RPT-1-1 — report content:** which governed families are IN report v1? (Recommendation: the
  §2.1 spine — total VaR + ES, concentration, liquidity, rolling risk/Sharpe — because each has
  entity/time reads shipped under Rule 7; everything else is a section added later, not a redesign.)
- **OQ-RPT-1-2 — rendering format:** HTML (printable) vs PDF generation in v1. (Recommendation:
  HTML-first, print-clean; a PDF pipeline adds a heavy dependency for typography nobody ratified.)
- **OQ-RPT-1-3 — the three OQ-W15P-6 carries**, re-evaluated HERE with a recorded
  fires/does-not-fire each: LIM-2 breach DTO echoes (fires only if breaches are IN v1 content);
  REF-1 alpha-3/M49 (fires only if a regulatory-format section is IN, recommendation: not in v1);
  CON-1 effective-number 1/HHI (fires only if the concentration section renders a detail view).
- **OQ-RPT-1-4 — the report record's identity:** new ENT (next free: ENT-072) with its canonical
  registry row, or a captured artifact on an existing rail. (Recommendation: a new ENT — a report
  IS a governed evidence artifact, and the seven-ledger machinery expects it to have a name.)

## Handoff

Per the operating model: **this remit is the planning artifact; the build executes against it with
freedom on method; deviations are recorded in the slice record; the fresh-context audit runs before
merge and checks the PROOFS above, not step-compliance.**
