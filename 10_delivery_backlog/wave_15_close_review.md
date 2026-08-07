# Wave-15 close review — run fresh-context, verified against `main` at `c532298`

**Reviewer posture.** This review was run on a different model than the builder, with the standing
instruction to verify against documents and code on `main` rather than against the builder's own
records — the same posture as the per-slice pre-merge audits this wave introduced, applied at wave
grain. Every claim below names its evidence. Items marked **PROPOSED** are Tier-3 and bind nothing
until ratified.

**CI on `main`:** run `31134065158` (`4eab7e0`) → `success`; run `31135033525` (`c532298`) →
`success`. Both quoted per P14.

---

## §0 — The one blocking-class finding: a ratified gate commitment fired silently

**OQ-W15P-7, ratified at the wave gate (2026-08-04), says:** *"Each escalation gets a host or an
explicit acceptance at RPT-1's gate at the latest,"* with the operating assumption *"that three
recorded non-movements of CTRL-018 is itself the signal, not an accident."* The three escalations:

1. **CTRL-018's scheduled reproduction job** (TR-13) — three recorded non-movements at the time;
2. **PERF-0's four homeless carries** — recommended binding: *"before any parallelization or
   grain-level performance work"*;
3. **The Wave-13 FE toolchain debt** — recommended: a dated gate.

**RPT-1's gate came and went without discharging any of the three.** The remit's decision points
(OQ-RPT-1-1…4) cover the report's content, format, the *OQ-W15P-6* carries (a different set — breach
DTO echoes / alpha-3 / 1-HHI, all three properly dispositioned in the slice record §8), and the
ENT-072 mint. Neither the remit nor the slice record mentions CTRL-018, PERF-0's carries, or the FE
toolchain debt. Verified by grep against both documents: zero hits.

Worse, the wave *extended* the pattern it was told to stop: RPT-1's CTRL-009 row explicitly writes
*"scheduling … stays CTRL-018/TR-13's territory"* — **a fourth citation-without-host for CTRL-018**,
written in the same wave whose gate ratified that three citations was already the signal.

This is exactly the P7 class — a commitment bound to a named trigger moment, and the moment fired
silently. It is a *process* defect, not a product one: nothing on `main` is wrong. But the close
cannot mark the wave clean while a ratified gate item sits undischarged, so the three dispositions
are **re-presented for ratification now**, at this close, as §5. Under P7 they may not be carried
forward by citation again — each gets a host with a date, or an explicit recorded acceptance.

## §1 — Did the wave deliver its stated purpose? Substantially yes, with one honest gap

The purpose (Part 1): *"the engine stops being something that runs on a laptop, and produces
something a human outside the team can read."*

**First half — substantially delivered, with the qualifier the gate itself chose.** CI now builds
and smoke-tests all three images, deploys the full stack to an empty database, proves
backup/restore both arms, and regenerates a governed report byte-identically across a destroyed and
restored database — all in the `stack-proof` job, which is (still) the repo's only mutation-proven
CI gate. The dev-only qualifier on "operational" claims has not vanished; it has **moved and
narrowed, by ratified choice**: OQ-W15P-3 deliberately picked a local-but-real target over a cloud
one, so the honest current claim is *"provably deployable and recoverable on a real process
boundary; not internet-facing; no cloud evidence."* CTRL-034's evidence base is unchanged by this
wave (it never was DEP-1/RPT-1 scope). Anyone reading "Operational" in the matrix should still read
it against that qualifier.

**Second half — delivered at the artifact level, NOT at the access level.** The report exists,
renders print-clean HTML, and regenerates from its id alone. But there is **no HTTP surface for
it**: nothing in `apps/backend` registers a report router, and the FE has no report view (verified
by grep against `main`). A board member cannot *obtain* the artifact; a developer with a Python
session can. This is remit-compliant — the IN list named a generation verb and a rendering, not an
endpoint, and distribution was explicitly OUT — but the wave's purpose sentence promised a human
*outside the team*, and that human today needs a developer as intermediary. **PROPOSED carry with
trigger** (§5, item D): the report read/generate endpoints are the natural next RPT increment, and
the N3 decision (may an external caller assert `generated_at`?) is already recorded on the column
as a prerequisite question.

## §2 — The operating-model change, assessed on its first full wave (n=2, stated as n=2)

The change (2026-08-05): remits define OUTCOMES + PROOFS, never steps; a fresh-context audit runs
per slice BEFORE merge.

**The evidence is small but it is not ambiguous.** Across both slices, the split found defects in a
strict gradient by distance-from-builder:

| Finder | DEP-1 | RPT-1 |
|---|---|---|
| The builder, by execution/mutation | 11 (10 pre-existing) | 9 (7 by execution/mutation) |
| The fresh-context audit | 2 gaps, found in minutes | **2 blocking** + 3 non-blocking |
| What the audit finding had in common | the worker never ran in the deploy | **both** of the builder's proof tiers re-supplied the same constant |

The RPT-1 case is the clean demonstration: the unit proof and the deployed restore proof shared one
assumption (`portfolio_code` re-supplied by the caller), so **no quantity of additional testing of
either kind could have found B1** — only evidence gathered under different assumptions could, and
the fresh context is what changed the assumptions. The audit also caught both slice-record
overstatements ("PROVEN, both tiers"; "asserting the absence of state"), which is the audit doing
precisely its stated job: checking proofs, not step-compliance.

**Cost, honestly:** roughly one model-switch round-trip and some hours per slice, plus the fold.
Against two blocking defects on a board-facing artifact, the trade is not close. **Verdict: keep
it. No amendment proposed.** What n=2 cannot yet say is whether audit quality persists once the
audit becomes routine; the close review after Wave 16 should re-ask with n≥4.

## §3 — The cross-slice pattern, named but deliberately NOT minted as a principle

DEP-1's headline: defects live **between components**, invisible to tests that never start the
system. RPT-1's: both proof tiers **shared one assumption**, invisible to any amount of testing
within either tier. The FK finding sits in both at once: SQLite's unenforced foreign keys were a
*shared-assumption* defect (every suite assumed the parent existed) found only when the *system
boundary* was crossed (PostgreSQL refused).

The common shape: **redundant evidence is not independent evidence. Adding more proofs helps only
if they do not share the assumption that is wrong.** The existing rules already gesture at this
(P9's "make it FIRE", the LIM-2 "mutate against the LIKELY input" lesson, the perspective-diverse
posture of the audits), but none states it.

I am **not** self-ratifying a P15 out of it, for the same reason P14 was not self-ratified: a rule
about what counts as sufficient evidence for my own claims is not one I should enact for myself.
**PROPOSED (§5, item E)**, one sentence: *"Two proofs sharing an assumption count as one proof; when
a claim matters, at least one proof must be constructed under different assumptions than the
implementation (a different engine, a different process, a different author, or a fresh context)."*
Ratify, amend, or discard.

## §4 — Ledger sweep at wave grain

| Ledger | State | Finding |
|---|---|---|
| Entity registry | CLEAN | ENT-072 row present; next-free = ENT-073; the **surface contradiction** between Part 1's "explicitly NOT in this wave: … new entities" and the ENT-072 mint is reconciled by the later, more specific ratified text (the remit's OUT: "entity **beyond what the report record itself requires**") — recorded here so the two documents stop disagreeing silently |
| Control matrix | CLEAN with one note | CTRL-009 Implemented (correctly restrained from Operational); CTRL-002 now true after the OQ-W15P-2 pre-work; **CTRL-018 = the §0 finding** |
| Roadmap / planning | **ONE STALE ROW** | `wave_15_planning.md` Part 6 still reads "P14 stays PROPOSED" while `claude_operating_instructions.md` records **RATIFIED 2026-08-05 by the user**. The planning doc is amended by dated note (never edited in place) in this close's fold |
| current_state | CLEAN | Verified: no false "25 families" claim (a report is evidence, not a number family — 24 stands); merge ordinals correct (#176 = 14th, #177 = 15th) |
| Audit taxonomy | CLEAN | EVT-090 `REPORT.GENERATE` still GENESIS-RESERVED, consistent with the service docstring |
| Demo counts | CLEAN | 27/44/141 unchanged — RPT-1 ratified no demo stage; noted, not defected |
| Slice records | CLEAN | Both slices carry deviations + audit sections; RPT-1's two overstatements corrected in place with the audit's §9 |

**Open anomalies, carried visibly rather than silently:** (a) the pytest final summary line was
missing from BOTH RPT-1 full-PG logs — census-by-progress-marks cross-checked exactly both times,
but an instrument that intermittently drops its summary is itself unexplained; trigger: the next
full-PG run, capture with `-rA` or tee and diagnose. (b) LIM-2's `requires_basis` flake (recorded
2026-08-01) — reproduced nowhere since; stands as recorded.

## §5 — Ratification items (Tier-3 — nothing below binds until you say so)

- **A. CTRL-018 (fourth non-movement).** PROPOSED: mint a small slice — a scheduled job that
  re-runs N historical runs nightly and diffs results — hosted in Wave 16 with a date at its
  planning gate; OR record an explicit acceptance ("reproduction stays on-demand until a regulator
  or client asks") and reword the CTRL-018 row to match. Citation-without-host is no longer
  available under the wave gate's own ruling.
- **B. PERF-0's four carries.** PROPOSED: bind now to the trigger the gate recommended — *"before
  any parallelization or grain-level performance work"* — recorded in the roadmap, so the next
  perf-touching slice inherits them mechanically.
- **C. Wave-13 FE toolchain debt.** PROPOSED: a dated gate — decide at the Wave-16 planning gate,
  where the FE's next increment (possibly the report view, item D) makes the cost concrete.
- **D. Report access.** PROPOSED carry: report generate/read endpoints (+ the `generated_at` trust
  decision recorded at N3) as the natural RPT increment; trigger: the first slice that touches the
  API surface, or an explicit user ask, whichever first.
- **E. The shared-assumption principle** (§3 wording). Ratify as P15, amend, or discard.
- **F. The FK hardening slice** (103 measured failures, breakdown in `rpt_1_slice_record.md` §6).
  PROPOSED: sequence at the Wave-16 planning gate as a named candidate, not started cold.

## §6 — Verdict

**Wave 15 is COMPLETE and its product state is clean**: both openers shipped, both audited, both
P1 sweeps clean on `main`, CI green on every merge commit, no unmerged work, no dangling branches.
The wave's one defect is procedural — a ratified gate commitment (OQ-W15P-7) that fired silently —
and its remedy is §5-A/B/C, which converts the omission into dispositions you ratify rather than a
citation that rolls forward again. The operating model introduced mid-wave has earned its keep on
the evidence of its first two outings and is recommended unchanged.

---

## §7 — Gate outcome (2026-08-07)

The user directed **"proceed"** against §5 without amending any recommendation. Per the Wave-15
Part-6 precedent, each item is taken **as recommended**, with the operating assumption stated so a
wrong assumption is visible rather than buried. Any of these is cheap to reverse by saying so.

| Item | Outcome | Operating assumption made explicit |
|---|---|---|
| **A** | **CTRL-018 gets a slice — REPRO-1, hosted in Wave 16 with a date at its planning gate** (a scheduled job re-running historical runs and diffing results) | That four citations-without-host means the platform's core "reproducible" promise deserves a machine that checks it, not another deferral. If on-demand-only is actually acceptable, say so and the CTRL-018 row is reworded instead |
| **B** | **PERF-0's four carries bound to the trigger** *"before any parallelization or grain-level performance work"*, recorded in the roadmap | That the binding makes the next perf-touching slice inherit them mechanically — no re-litigation |
| **C** | **FE toolchain debt decided at the Wave-16 planning gate** | The debt is concrete (TS→7, eslint→10, jsdom→30, + the six untypechecked root guard tests). NOTE: if RPT-2 ships an FE report view, the debt's ORIGINAL trigger ("first FE feature slice") fires anyway — the Wave-16 gate decides it either way |
| **D** | **Report generate/read endpoints = an early Wave-16 item (RPT-2)**, incl. the N3 `generated_at` trust decision | That "a human outside the team can read it" means REACH it, not merely that it exists. The N3 decision is a gate OQ, not a builder default |
| **E** | **P15 RATIFIED** — *"Two proofs sharing an assumption count as one proof; when a claim matters, at least one proof must be constructed under different assumptions than the implementation (a different engine, a different process, a different author, or a fresh context)."* Added to the standing rules | That "proceed" ratifies the §3 wording as recommended. P15 is an evidence-sufficiency standard (the P9/P13 class), not a reporting-accountability rule (the P14 class), so taking it on "proceed" follows the precedent — P14's self-ratification bar does not apply. If you meant to withhold E, one word reverses it |
| **F** | **The FK hardening slice (103 measured failures) sequenced at the Wave-16 planning gate** as a named candidate | That measured, broken-down work is scheduled — not started cold, not re-worried |
