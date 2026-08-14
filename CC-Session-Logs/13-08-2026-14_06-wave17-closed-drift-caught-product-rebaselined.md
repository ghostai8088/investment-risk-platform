# Session Log: 13-08-2026 14:06 - Wave-17 closed, the product drift caught, and the platform re-baselined

## Quick Reference (for AI scanning)

**Confidence keywords:** Wave-17 close, product re-baseline, requirements drift, acceptance criteria,
REQ-PPM-004, REQ-MKT-003, REQ-SMR-001, capability coverage gate, CAP-21 Presentation, G1 G2 G3 G4,
DEPLOY-1, irp_app, RLS bypass, BYPASSRLS, break-in test, IGNITION_EXIT, SBOM, CycloneDX, LGPL,
psycopg, licence position, retention 2557, INGEST-1, AI-drafted mappings, schema-not-data,
Decimal pricing engine, Monte Carlo withdrawn, QS-18, Decimal factor model, risk decomposition,
performance attribution, scenario fence, VAR_HORIZON_DAYS, SUPPORTED_FACTOR_FAMILIES, ultracode,
PRs #202 #203 #204 #205 #206 #207, workflow died silently, liveness probe

**Projects:** investment-risk-platform (multi-tenant governed investment-risk platform)

**Outcome:** Wave 17 closed and merged; then the owner's question about best practice exposed an
eight-week product drift, its exact mechanism was found and fixed at the instrument level, and six
PRs landed — including the RLS bypass in the deployed stack and the first two of four gates.

## Decisions Made

- **The RLS bypass is fixed BEFORE the wave** (user-ratified). Migration `0070` mints `irp_app`
  NOSUPERUSER NOBYPASSRLS; backend + worker connect as it; `migrate` keeps the owner for DDL.
- **Wave-18 thesis = "Show it to someone"** (DEMO-1, DEMO-2, ONBOARD-2, RUN-UI, PRESENT-1) — later
  superseded in emphasis by the re-baseline, which the owner ordered ahead of any further building.
- **Licence: PROPRIETARY**, with the LGPL obligation for `psycopg` stated explicitly. SBOM job added
  with a copyleft gate. All five manifests stamped.
- **Retention: 2,557 days (7y) archive boundary, 730 days (2y) hot**; the audit half cannot be
  deleted at all (hash-chained, append-only), so the real decision is archival, not deletion.
- **INGEST-1 ratified (4/4)**: mappings are versioned DATA interpreted by a CLOSED operation set;
  the AI drafts OPERATOR-SIDE seeing **schema only, never rows**; positions first. The drafting
  model is REGISTERED so every proposal is attributable.
- **Ten re-baseline questions ratified as recommended**, including three that ratify a LOSS:
  **Monte Carlo withdrawn from the governed spine** (supersedes a ratified requirement),
  counterparty risk declined, report sign-off deferred.
- **Branch protection: 5 required checks → 9** (user made the change on GitHub).
- **The requirement set is PROPOSED, not adopted** — adopting it means writing rows with testable
  acceptance criteria, which is itself the work.

## Key Learnings

- **THE MECHANISM OF THE DRIFT: acceptance criteria satisfiable without delivering the stated
  purpose.** REQ-PPM-004 purpose "roll up exposures across hierarchy", acceptance "aggregates
  reproduce within tolerance" — an aggregation that rolls up NOTHING reproduces perfectly.
  REQ-MKT-003 purpose "attribute risk to factors", acceptance "contributions sum to total within ε"
  — an allocation identity satisfies it trivially, and the row's own status admitted
  contribution-to-risk was deferred. **No test consumes a business-purpose column.**
- **Why 17 wave-closes missed it: every audit compared code against requirements or records against
  code.** The register was the yardstick in all of them and the register carried the gap. *An audit
  whose reference point is the artifact carrying the defect cannot see the defect.*
- **The bias underneath: correctness is verifiable, direction is not** — so instruments kept getting
  built to measure what could be measured.
- Of 74 rows, **22 mention reproduction, 2 mention a human seeing anything**; the DoD's only UI
  clause is a prohibition; `SCOPE-01..05` were cited in exactly one file, their own.
- **Measured, not argued (spikes):** Decimal pricing of 5,000 positions × 20 scenarios = **4.5s /
  6.5s**; Decimal factor model at 117 factors × 10,000 instruments = **0.838s / 0.607s** per period;
  18,000 Decimal ops across two implementations at three precisions = **zero mismatches**. The one
  cliff is Monte Carlo at ~112h vs ~15s vectorised.
- **A workflow can die silently and look alive.** The decisive liveness test is whether agents
  produced ARTIFACTS, not whether an output file is empty — output files are written at completion.

## Solutions & Fixes

- `migrations/versions/0070_app_role.py` — role NOLOGIN (no secret in source) + default privileges
  so future tables are covered by construction.
- `prepare.py::_grant_app_role_login` — password quoted BY THE SERVER (`SELECT quote_literal(:pw)`),
  because `ALTER ROLE` takes no bind parameters.
- `scripts/check_capability_coverage.py` — G1 + G3, ratchet baseline, six then eight controls.
- `prove_onboarding.sh` arm 6 — the deployed break-in test, `IGNITION_EXIT=0`.
- Liveness probe pattern: count `/tmp/*.py` every 30s against a baseline; any increase = proof of life.

## Files Modified

- `migrations/versions/0070_app_role.py`, `docker-compose.yml`, `.env.example`, `LICENSE` (new),
  all five package manifests, `deploy/prepare.py`, `infra/deploy/prove_onboarding.sh`.
- `scripts/check_capability_coverage.py` (new), `02_requirements/capability_coverage_baseline.json`
  (new), `apps/backend/tests/test_capability_coverage.py` (new, 8 controls).
- `02_requirements/product_rebaseline.md` (new), `requirements_backbone.md` (74→86 rows, CAP-21
  minted, two acceptance criteria rewritten), `10_delivery_backlog/ingest_1_decision_record.md` (new),
  `delivery_roadmap.md`, `05_analytics_methodologies/numerical_quant_standards.md` (QS-18).
- `.github/workflows/ci.yml` (SBOM job, capability-coverage step), `Makefile`.

## Setup & Config

- Branch protection now enforces **9** required checks (was 5). Stack proof, API type drift,
  Container images and SBOM added by the user via the GitHub UI.
- `IRP_APP_DB_PASSWORD` is now REQUIRED for a working deploy; absent = fails closed at prepare.
- Local PG reset recipe unchanged; head is now `0070_app_role`.
- Ultracode toggled on and off during the session; workflows need explicit opt-in when off.

## Pending Tasks

- **G2 bake-off is RUNNING** (relaunched 14:02:50 after the first run died silently; confirmed alive
  at 14:05:50). Six detector strategies scored against a labelled 74-row register.
- **G4** — the close review cannot close without the coverage table.
- **Re-baseline part 2** — the remaining ~18 requirement rows (node-scoped runs, Mandate/Measured,
  reporting currency, the rest of reporting, credit).
- Four coverage-baseline entries still owed: 13.3, 16.2, 20.2, 20.4. All five SCOPE ids still uncited
  by any requirement row.

## Errors & Workarounds

- **A workflow died silently and I asserted twice that it was fine.** 157 minutes, 0-byte output,
  zero agent artifacts. I reasoned about file-write timing instead of checking for artifacts. Fixed
  by relaunching and installing an artifact-based liveness probe.
- **The coverage gate's own defects, all found by running it:** 47 false positives (rows write
  `12.1/12.2`); a negative control that PASSED because it anchored on text not in the file; and a
  SCOPE scan so loose that the re-baseline document *discussing* the gaps marked them discharged.
- **The break-in test's first two versions proved nothing:** a route `tenant_admin` cannot read on
  EITHER tenant (wrong and right answers coincided), then a 401 assertion where the answer is 403.
- **The SBOM job** scanned the environment it installed the scanner into, then omitted `psycopg`
  entirely — the one dependency with a real licence obligation.
- **G3 rejected a requirement written an hour earlier** (REQ-PRS-005 had no visible acceptance).
- An insert script died on the LAST section (no successor header) and wrote nothing, while a separate
  baseline edit had already run — the gate caught the inconsistent state.

## Key Exchanges

- Owner asked whether the platform's data-inflow assumptions were best practice and whether AI
  changes the answer — which surfaced the drift.
- Owner rejected the "evidence system" positioning: wants a competitor to Aladdin/Barra serving 1st
  and 2nd line, maths and visualisation as the star, any product/fund/sleeve structure, publics and
  privates. Asked how it got "antithetical to the original plan".
- Owner asked, angrily and fairly, how they can be sure repeated harness audits won't miss this again.
  Answer: the audits all used a document Claude generated as their yardstick; the fix points a gate
  at documents the OWNER wrote.
- Owner asked "so wtf have you actually been building?" — answered with the 40/33/23/1 line split and
  the honest diagnosis: 21 families built one inch deep.
- Owner asked whether to raise the effort level; answer was that the fan-out matters more, and that
  G2 has GROUND TRUTH so it can be scored rather than argued.

## Custom Notes

None

---

## Quick Resume Context

Wave 17 closed (#201) and then the session pivoted entirely: the owner's questions about best
practice exposed that eight weeks of delivery had drifted from the product's stated intent, because
the requirement register's acceptance criteria were satisfiable without delivering their stated
purpose. Six PRs landed (#202–#207): the RLS bypass in the deployed stack fixed and proven over HTTP,
a capability-coverage gate whose inputs are documents the owner wrote, the re-baseline document, the
first twelve rewritten requirements with CAP-21 Presentation minted, the Monte Carlo withdrawal
annotated everywhere it was promised, and gate G3. **Next: the G2 detector bake-off is running;
then G4, then the remaining ~18 requirement rows.** Main at `59e7a42`, clean, all checks green.

---

## Raw Session Log

The authoritative turn-by-turn transcript is the Claude Code JSONL at:

`~/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`

Referenced rather than reproduced, on the same ground as every prior log in this directory: writing
a "verbatim" transcript from memory would fabricate a record. That would be especially wrong in this
session, whose entire subject was a register that claimed more than it delivered — and which ended
with me asserting twice that a dead process was running because I preferred my inference to a check.

### Chronology

1. **#201 = `1544fa9`** — Wave-17 close (32nd merge). Two BLOCKING found: three registers describing
   a control that had moved 16 families beneath them, and an alarm surface reading HEALTHY through
   thirty consecutive failed nights.
2. **The pivot** — owner's best-practice question → three adversarial runs (13, 13, 21 agents) →
   the drift mechanism identified and verified.
3. **#203 = DEPLOY-1** — `irp_app`, the break-in test, the licence position, the SBOM job.
4. **#202** — the capability-coverage gate + the re-baseline document.
5. **#204** — the INGEST-1 decision record.
6. **#205** — 74→86 rows, CAP-21 minted, two acceptance criteria rewritten, 20.3 discharged.
7. **#206** — Monte Carlo withdrawn at REQ-MKT-001, the roadmap register, and QS-18.
8. **#207** — gate G3, which rejected a row written an hour before it existed.
