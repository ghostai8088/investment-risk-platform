# Current State

## ⚠️ CURRENT TRUTH (2026-08-14) — read this block; everything below it is HISTORY

**Main `0cf3e31`, tree clean, CI green on all nine checks. Migration head `0070_app_role`, one head.
Next free canonical id ENT-076. NEXT = the Wave-18 planning gate.**

### The re-baseline, and why it happened

The owner asked whether the platform's data-inflow assumptions were current best practice. That
question ended eight weeks of drift. The diagnosis is one sentence: **the requirement register's
acceptance criteria were satisfiable without delivering their stated purpose.** REQ-PPM-004 promised
*"Roll up exposures across hierarchy"* and accepted *"Aggregates reproduce within tolerance and bind
lineage"*. Neither clause requires a rollup: lineage binds whatever was computed, and an
aggregation that rolls up nothing reproduces perfectly. A test-driven process built exactly what
could pass. Of the 74 rows then in the register, 22 required reproduction and **two** required a
human to see anything.

**Why seventeen wave-close audits missed it:** every one compared code against requirements, or
records against code. The register was the yardstick in all of them, and the register carried the
gap. *An audit whose reference point is the artifact carrying the defect cannot see the defect.*

### What is built

Merged as PRs **#202** through **#214**: the capability-coverage gate and the re-baseline document
(#202); DEPLOY-1, which found the deployed stack connected as a SUPERUSER with 84 FORCE-RLS tables
bypassed, fixed by migration `0070_app_role` and proven over HTTP (#203); the INGEST-1 decision
record (#204); the register at 74 → 86 rows with CAP-21 Presentation minted (#205); the Monte Carlo
withdrawal (#206); gate G3 (#207); gate G2 (#208); gate G4 (#209); re-baseline part 2 (#210); and
the G2 proposals plus the first five adjudications (#211 – #214).

**All four gates are built:**

- **G1** capability coverage (built 2026-08-12). Ratchet, **6 controls at the mint**; the file that
  holds them is at 19 today because G3 and G4 landed in it too. Its inputs are deliberately
  documents Claude did not generate, because every prior audit used the requirement register as its
  yardstick. *(The figure read "8 controls" until 2026-08-14. Eight was G1+G3 together at a moment
  already two commits stale — a number carried forward without re-measuring, which is the exact
  habit that made this file go stale in the first place.)*
- **G2** (built 2026-08-13) adjudication, and **not as specified**. Six detector designs were
  built and
  scored twice by independent fleets. All six catch the three known-bad rows and none is usable, so
  G2 is a HUMAN act (**P20**) with bookkeeping that proves the act happened. The mechanical half
  checks paperwork only and must never be cited as a check on requirement quality.
- **G3** (built 2026-08-13) presentation rows need a visible acceptance. It rejected a row written
  an hour before it existed.
- **G4** (built 2026-08-13) from the Wave-18 close on, a close review must carry a
  `## Capability coverage (G4)` section naming the leaves the wave newly covered. It binds to zero documents today, and a control
  asserts exactly that and instructs its own deletion at the first close under it.

**The register is at 104 rows** (105 after re-baseline part 2 added nineteen on 2026-08-13; minus
REQ-CPT-002/-004 withdrawn and plus REQ-CRD-008 minted at the 2026-08-15 worklist adjudication),
and the RTM is level with it. Part 1 had updated only one half,
which is the P1 ledger-5 omission class with nothing mechanical checking it. **Seven coverage gaps
were paid, every one found by the gate itself** refusing to pass with stale exemptions in the
baseline: `13.3` exception management, `16.2` scenario and breach reports, and all five SCOPE
commitments, discharged by rows that CITE the id they serve. Two accepted gaps remain by choice:
`20.2` money-weighted return and `20.4` composites. *A cited SCOPE id means a requirement answers to
the commitment. It does not mean the commitment is built. SCOPE-02's derivative half is still the
largest gap the re-baseline found.*

**Ratified, and three of them ratify a LOSS:** Monte Carlo withdrawn from the governed spine,
counterparty risk declined, report sign-off deferred. Measured rather than argued, and quoted as
the RANGE both measurements produced rather than the favourable end: Decimal pricing of 5,000
positions × 20 scenarios at **4.5–6.5s**, and a Decimal factor model at 117 factors × 10,000
instruments at **0.61–0.84s** per period. The lower figure of each pair is the researcher's, the
higher the independent adversary's; `product_rebaseline.md` carries both.

### What is adjudicated, and what that gates

**Five rows are cleared through G2: REQ-PPM-006 through REQ-PPM-010, all AMENDED**
(`02_requirements/g2_adjudication_ledger.jsonl`, eight entries: 006 was adjudicated three times
and 007 twice, after their text was rewritten. That is the lapse rule working, not a duplicate —
006's two re-adjudications are different acts, one substantive and one presentational.) The owner refuted the proposer on three of them,
and rejected one row's premise outright: **mandate comparison is DECLINED** (REQ-PPM-009), because
mandate compliance is a compliance function and not risk, SCOPE-03's declared risk coverage does not
include it, and a mandate rule engine would duplicate the shipped limit framework. That supersedes
the Q4 answer ratified the previous day, and is recorded with two triggers.

**The advisory worklist of 11 flagged rows was WORKED THROUGH 2026-08-15** (proposals in
`10_delivery_backlog/g2_adjudication_proposals_worklist.md`, ratified by the owner as
recommended). Nine acceptance cells rewritten with ledger entries: REQ-PPM-001, REQ-PPM-002,
REQ-PUB-002, REQ-MKT-002, REQ-LIM-002, REQ-SCN-003, REQ-CRD-005, REQ-LIQ-004 (whose Status also
read bare Draft while CC-2 had shipped the per-pair kernel — the OQ-LQ-1-12 register-silence
class), and REQ-RPT-001 (NARROWED to exact set equality against REPORT_FAMILIES; the credit
report minted as REQ-CRD-008, homed with the Q6 credit build). **REQ-CPT-002 and REQ-CPT-004
WITHDRAWN** — rows removed, leaves 7.2/7.5 recorded as accepted coverage gaps — executing the
ratified MC withdrawal and counterparty decline. The register is at 104 rows. **Amendment is not
clearance: every amended row carries a NEW hash and re-enters G2 at slice entry.** The five
structure rows remain the only slice-ready cleared set. *(This block named
`g2_adjudication_proposals_wave18.md` until 2026-08-14. That file holds the five rows that ARE
adjudicated, so the pointer sent a reader to an artifact contradicting the sentence around it.)*

**The lesson from the G2 build, and it applies to every requirement written from here:** four of
five of the author's own amendments banned a MECHANISM where they should have required an OUTCOME,
and a banned mechanism rejects correct implementations. *State an outcome the degenerate build
cannot produce; never forbid a route to it.*

### NEXT

**The Wave-18 planning gate.** The scope is not set and it is the owner's call. Every row entering
the slice scope needs a G2 adjudication first (P20, T1). The sequencing argument is in
`product_rebaseline.md` §5: the risk-bearing exposure measure and the aggregation contract come
first, because nothing analytic is safe to build before them. Three candidates were named at the
close of the last session: the structure block (the only rows currently cleared), "Show it to
someone", and INGEST-1.

---

## Previous truth — swept at the Wave-17 close, 2026-08-11

**The Wave-17 PLANNING-gate snapshot moved to `current_state_archive.md` in the 2026-08-14
shrink.** It was the newest text in this file for the whole of Wave 17: `git log -1` on this file named
`a69775c` ("ONBOARD-1 RATIFIED"), an ancestor of all seven Wave-17 merge commits, with 38 commits
and 11 merges landing after it. Its "NEXT = the ONBOARD-1a implementation plan" line pointed at a
slice that merged as PR #191 and was followed by nine more merges.

That is the finding, not the staleness itself: **P1 ledger (4) went unswept across five consecutive
slice closeouts, and `test_ledger_census.py:19` explicitly leaves this ledger procedural** ("the P1
seven-ledger sweep owns it"), so nothing mechanical will ever catch it. The mitigating fact is that
the authoritative ledgers were right and `test_migration_head.py` pins the head mechanically, so a
successor following the stale snapshot would have been reddened before shipping — but they would
have read it first, and CLAUDE.md orders every session to read this file second.

**Wave 17 is BUILT and CLOSED.** Four slices, all merged and verified on main:

| Slice | PR | What it made possible |
|---|---|---|
| ONBOARD-1a | #191 | **The ignition** — a tenant can be created over HTTP. ENT-074 registry, migration `0067`, the `tenant.create` platform catalog, the SYSTEM-router fence |
| ONBOARD-1b | #192 | The tenant administers itself — four tenant-admin codes, ENT-075 four-eyes, migration `0068`, `/admin/users`; CTRL-025 + CTRL-037 → Implemented |
| ALERT-1 | #195 | Alarm-channel health — twelve recomputed fields, `GET /reproduction/alarm-health`, `/ops/alerting` |
| REPRO-2 (parts 1+2) | #197, #198 | CTRL-018 goes from **3 governed families to 19**; a schedule WRITE API; `/ops/reproduction` |
| RPT-3 | #199, #200 | `ROLLING_RISK` joins `PERF_RUN_TYPES`; the generate-report form at `/ops/reports` |

**Measured at the close, not carried forward:** migration head `0068_entitlement_request` (one head);
route census **263 paths / 305 operations**; next free canonical id **ENT-076**; reproduction census
**19 reproducible + 2 unreproducible** = the whole 21-family run-type vocabulary; 84 mutants, all
anchors matching.

**What the close review found, all four confirmed by execution before the fold:** the alarm-health
surface read HEALTHY through a sweep failing at dispatch every night (a fire is not a landing); the
three CTRL-018 registers still described a three-family control with no write API; the
closure-discipline gate had been structurally blind since 2026-07-29 while exiting 0; and the
committed mutation battery was RED at HEAD with four alarm controls dark and no gate running it.

**NEXT = the Wave-18 planning gate.** The sequence is not set: the roadmap runs to Part 2.19
(Wave 17) and then to Part 3, which is explicitly unsequenced — which is why thirteen of Wave 17's
carries name a host that does not exist, and why they are labelled as deferral decisions at this
close rather than parked (P19 clause B).

## History archive

`current_state_archive.md` holds every prior-truth block, verbatim and newest-first. Two shrinks
put them there:

- **2026-07-30** — the 2026-07-29b block and earlier, plus the PA-0-era standing sections.
- **2026-08-14** — the 2026-08-08 Wave-17 planning-gate snapshot down to the 2026-07-29c block.
  Seven blocks, 513 lines, which took this file from 680 lines to 165.

What stays here is the current-truth block and the most recent wave close, because Wave-18
planning still reads Wave 17's carries. The archive is history, not truth — where it disagrees
with the CURRENT TRUTH block above or `delivery_roadmap.md`, THEY win.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now HTTPS** (`https://github.com/ghostai8088/…`; keychain-cached PAT — flipped from SSH 2026-07-09 at P3-C3 because SSH port 22 is BLOCKED on the current network, timing out; HTTPS push works cleanly. Plain `git push` now uses HTTPS + PAT — no hotspot / URL-push workaround needed).

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- **2026-07-14 pointer (PA-4 closeout):** the OPERATIVE executed ledger is `10_delivery_backlog/delivery_roadmap.md` (Waves 1–4 rows + the dated log table) — the per-slice narrative below this file's Wave-2 era is intentionally not duplicated here. Main HEAD ≥ `8ef70db6` (PA-4, **PR #30**); migration head **`0038_var_residual_variance`** (thirteen governed numbers; the chain since this file's last deep refresh: `0036` PA-1 desmoothing, `0037` PA-3 proxy-weight estimates, `0038` PA-4 residual variance).
- **Delivery autonomy (2026-07-12, EXTENDED 2026-07-14):** Claude self-drives plan→implement→review→commit→push AND **opens + merges the PRs** (the adversarial review + `make check` + full-PG + CI-to-green gates replace the human merge gate; branch protection's required checks stay on; PR create/merge via the GitHub REST API with the keychain credential). The USER still signs off Tier-3 decisions and genuine design forks. The older "USER opens+merges" statements — now in `current_state_archive.md` — are superseded, as are ALL stale HEAD/migration-head/governed-number-count claims that predate this pointer (e.g. the PA-0-era "0034" / `ad3d3fe` lines, also archived): where this pointer and older text disagree, the pointer + the roadmap win (Wave-4 close audit fix).
- `git log -1 --oneline` and `git status --short` — confirm main HEAD and branch state.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — the public repo REST API answers unauthenticated, 60 req/hr).
- `git remote -v` — origin is HTTPS (`https://github.com/ghostai8088/…`; flipped from SSH at P3-C3 — port 22 blocked).
- `project_state.yaml` is **RETIRED** (2026-07-06 stub; found drifted at the P3-3 planning session) — the recovery set is `CLAUDE.md` + this file + `phase_status.md` + `next_actions.md`.
- **This machine's environment (verified 2026-07-07):** the repo sits nested at `~/Projects/investment_risk_platform/investment-risk-platform/`; the venv is **Python 3.13.0** (CI runs 3.12); **`irp_pg_local` IS stood up** (reused `postgres:16`; `postgresql+psycopg://irp:irp@localhost:5432/irp`) — reset the schema between full PG pytest runs and NEVER manually grant `irp_ops` schema USAGE (migrations re-grant; the extra grant breaks the downgrade smoke); `gh` is not installed (use the public REST API).

