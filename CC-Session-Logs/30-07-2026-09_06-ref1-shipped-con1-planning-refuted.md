# Session Log: 30-07-2026 09:06 - REF-1 Shipped, CON-1 Planning Refuted Twice

## Quick Reference (for AI scanning)

**Confidence keywords:** Wave-14, Wave-14-planning, OQ-W14P-1-8, REF-1, OQ-REF-1-1-30, CON-1,
OQ-CON-1-1-25, ENT-066, ENT-067, ENT-068, classification_scheme, classification_node,
classification_assignment, migration-0056, migration-0057, AD-013-R2, hybrid-set-5-to-7, N=7,
HYBRID_TABLES, 0008-is-DDL-not-a-mirror, 38-sites-36-files, closed-set-declaration,
tenancy-floors, COALESCE-with_check-qual, USING-only-policy, FORCE-RLS-floor,
closure-stamp-recurrence-EIGHT, _RECORDS_WITHOUT_RECOGNIZED_STATUS, exact-grandfather-set,
three-permission-codes, reference.classification.view, reference.classification_assignment.view,
auditor_3l-SoD-per-code-pins, ISIC-Rev-5, ISO-3166-1-alpha-2, UNSD-M49, GICS-licence-struck,
sector-industry-one-hierarchy, ancestor-resolver, cycle-guard, level-monotonicity,
country-of-risk-CAPTURED, basis-NOT-NULL-sentinel, kind-basis-invariant-both-directions,
drift-on-verify, snapshotVerified-NOT-WIRED, vacuous-fence-no-writer, issuer.sector-freeze,
_FROZEN_ATTRIBUTES, REQ-SMR-006, REQ-CRD-005, CRD-004-collision, demo-stage-18, stage9zzzzzzzzz,
count-pin-relay-unchanged, issuer_id-backfill, superuser-bypasses-RLS, SYSTEM-tenant-fixture-collision,
refuse-not-skip-family-version, dbce327-CI-failure, 21-migration-head-pins, action-constants,
import-direction-fence, 529-overload-six-lanes-lost, two-batches-of-three,
denominator-gross-refuted, Reg-231-2013-Art-7-is-numerator, Art-6-1-NAV, CESR-10-788-post-netting,
ESMA-2013-1339-para-87-total-assets, UCITS-Art-52, IRC-851-b-3, dual-share-ALSO-REFUTED,
share_total_assets-is-not-total-assets, cash-cash-items-receivables, false-breach-not-withdrawable,
_METRIC_MAP-single-result_attr, String-30-overflow, HHI-ulp-identity, CR-N-degenerate,
FIFTH-undelivered-REF-1-ratification, PR-147, PR-148, PR-149, 727f3c9, 1a50b2c, 3b74a52, dfe0591,
full-PG-2720

**Projects:** investment-risk-platform (ghostai8088/investment-risk-platform)

**Outcome:** Wave 14 was sliced and ratified, then **REF-1 was planned, built, closed and MERGED**
(PR #148 + #149) — the platform's first governed reference dimensions, taking the closed hybrid set
from five tables to seven under AD-013-R2. **CON-1's planning then broke twice**: v1 at 46 findings
(5 BLOCKING, including a rule-6a research section that cited three regulatory texts for the
opposite of what they say), and v3 at a further 47 (8 BLOCKING) — including that the dual-share
denominator ratified to fix v1 **relocated the fail-open defect rather than removing it**. Five
false or undelivered claims were found in REF-1's own merged record.

---

## Decisions Made

### Wave-14 planning gate (OQ-W14P-1…8, all ratified as recommended)

- Sequence **REF-1 → CON-1 → LIM-2 → CAL-1 → LQ-1**, argued on payoff order rather than dependency
  (the recon refuted the claimed CAL-1→REF-1 dependency).
- No live vendor adapters this wave (trigger: a real vendor contract). Open/vendor-neutral taxonomy
  schemes. REQ-CRD-003 SPLITS. REQ-LIQ-002 deferred and homed to the Part-3 RTM-P4 theme.
- **Scheme tenancy = EXTEND the hybrid set** via an explicit AD-013-R2 — surfaced as a genuine fork
  because the draft's recommendation contradicted Accepted AD-013 without citing it.
- The stale-register re-sync rides the planning PR, tier-split (status flips Tier 0/1; a production
  docstring and two ratified-record edits declared Tier 2).

### REF-1 gate (OQ-REF-1-1…30, all ratified as recommended)

- **ISIC Rev. 5** canonical; **sector and industry are LEVELS OF ONE HIERARCHY**, so "sector" is the
  level-1 ANCESTOR of an assigned leaf and REF-1 ships the ancestor resolver CON-1 consumes.
- **"ICB/GICS-SHAPED structure" STRUCK** — S&P DJI's licence covers the structure itself, so a
  deliberately GICS-shaped hierarchy is the derivative-work case, not a safe harbour.
- **Country-of-risk is CAPTURED**, not derived, with a NOT NULL `basis` discriminator — no
  authoritative rule (MSCI/FTSE nationality, BIS ultimate-risk) is computable on today's schema.
- Countries ride an ISO-3166-1 scheme rather than a fourth table, so **N = 7** not 8.
- Assignments are **FR bitemporal**, decided on drift-on-verify (test-proven both directions), at
  **instrument grain** via a polymorphic target.
- **THREE permission codes split by tenancy class** — the fix for a BLOCKING SoD defect.
- Split trigger (b) FIRED: the rf diligence control moved to CAL-1.

### CON-1 (drafted, NOT ratifiable — see Pending)

- Denominator ratified 2026-07-29 as the **dual-share form** (option 2 of three briefed) on the
  ground that REQ-CRD-003's acceptance verb is literally "limits-ready". **The re-verification then
  refuted that too** (see Pending Tasks).

---

## Key Learnings

1. **Migration 0008's `HYBRID_TABLES` tuple is DDL, not a mirror.** It drives 0008's own
   `CREATE POLICY` loop, so adding a name to it makes `alembic upgrade head` from zero try to police
   tables 0008 never creates — the exact path CI takes. Every migration polices only what it created;
   one ORM declaration is the governance concept and the parity test asserts
   `declaration == union(migrations)`. The ratified wave plan said "mirror" and was wrong.

2. **"Drift-prone" is a property of the SERIALIZER, not of the temporal class.** `verify_snapshot`
   compares only `content_hash`, never `pinned_record_version`. A pin over `{id, tenant_id,
   issuer_id}` drifts iff the issuer edge moves. REF-1's "EV-flavored, drift-prone" framing
   foreclosed a design it never evaluated.

3. **Recurrence EIGHT of the closure-stamp class — in this slice's own record.** The status sat in a
   blockquote, so `_status_lines` returned `[]`. The two count floors added at the Wave-13 close
   could never catch it: 61 of 62 records still had a status, above the floor of 50. **A MINIMUM is
   blind to one record going dark; only an EXACT set is not.**

4. **A per-slice fence must assert its OWN subject.** One test pinned the GLOBAL hybrid total inside
   a P1B-3 fence, so an unrelated slice's ratified extension read as this slice's regression.

5. **These demo PG suites connect as SUPERUSER, which bypasses RLS** — so "everything in the table"
   is never a safe scope in a shared database. Three separate isolation defects came from that one
   fact, including my own PG fixture seeding a SYSTEM `ISIC Rev. 5` that collided with the demo's
   real seed and made the stage's refuse-not-skip guard fire against a scheme it never seeded.

6. **A refuse-not-skip guard must identify its OWN seed exactly** (family AND version), or a test
   fixture makes it refuse and leave the demo silently unclassified.

7. **Verify that a negative control actually FIRES.** Mine didn't: psycopg sends a Python `str` as
   *unknown* and PostgreSQL coerces it to integer. The real Wave-13 failure shape needs an explicit
   `CAST(:x AS varchar)` to produce `operator does not exist: integer = character varying`.

8. **Rule 6a is not satisfied by citations that say the opposite of the claim** — that is worse than
   citing nothing, because it launders a guess as authority. All three of CON-1 v1's regulatory
   citations were misread: Reg 231/2013 Art. 7 is the leverage NUMERATOR (Art. 6(1) gives NAV as the
   denominator); CESR/10-788's absolute value is applied AFTER netting; and ESMA/2013/1339 **¶87,
   sitting between the two paragraphs I cited**, gives the denominator as "percentage in terms of
   total value of assets".

9. **A fold can RELOCATE a defect rather than remove it.** The dual-share fix for the denominator
   asserted `sum(long_amount)` "equals total assets on a long-only book" — false, because total
   assets includes cash, cash items and receivables (IRC §851(b)(3)(A)(i) is explicit) and an
   exposure row exists only for a position with a mark and a resolvable FX path. The error direction
   is harmful: a denominator missing cash OVERSTATES shares, so LIM-2 would record **false breaches**
   — which enter the append-only remediation lifecycle and fire notifications, neither withdrawable.

10. **Five false or undelivered claims in ONE merged record is a pattern, not five accidents.**
    Forward-looking prose in a decision record reads as delivery. Found: the ratified `issuer.sector`
    write-freeze never implemented; the `snapshotVerified` user-visibility claim (no production view
    passes the prop); a node fence with no writer to constrain; a `run_presence_gate` "first
    capture-path caller" claim the rail never makes; and a fifth the re-verification surfaced.

11. **My own arithmetic in prose is not a reference value.** I wrote HHI = 0.348834; re-deriving with
    `Decimal` gave **0.356057**. And the identity I called "exact" is off by up to N ulps —
    quantize-then-square ≠ square-then-quantize — so a test written to it fails on its own reference
    values.

12. **`pytest` config matters when reading a signal.** `addopts = "-q"` plus my own `-q` suppressed
    the summary line entirely, and `testpaths` covers THREE directories while I was running one.
    Reconciling the discrepancy rather than accepting it is what surfaced both.

---

## Solutions & Fixes

- **The classification substrate** — `classification/models.py` (three entities, the
  `dimension_kind`↔`basis` invariant enforced in BOTH directions with a NOT NULL sentinel on the
  `curve_type`↔`REFERENCE_KEY_NONE` precedent), `classification/service.py` (the `proxy_mapping` FR
  protocol, two fail-closed resolvers, a bounded cycle-safe ancestor walk), migration `0056`
  (its own asymmetric hybrid policy + a symmetric proprietary policy, both arms explicit).
- **The closed-set collapse** — 31 hand-mirrored 5-tuples replaced by imports of one declaration;
  the parity test re-founded on `declaration == union(0008, 0056)`.
- **Three platform floors** — the EFFECTIVE write check `COALESCE(with_check, qual)` (with a negative
  control creating a `USING`-only policy and proving the naive census reads NULL while the floor sees
  the breach); FORCE-RLS coverage over every `tenant_id`-bearing table; and a closure-stamp COVERAGE
  floor as an EXACT grandfather set of 11 legacy records, negative-controlled by reverting this
  record to the blockquote shape.
- **The R-07 mint** — three codes with holder sets equal to their precedents, pinned in both
  directions plus an inequality assertion between the two view codes.
- **The delivered write-freeze** — `sector` removed from `_UPDATABLE`, from `create_issuer`'s
  SIGNATURE (so passing it raises `TypeError`) and from `IssuerIn`; `IssuerOut` and the column kept;
  the audit payload key retained at `None` because that key set is a pinned contract.
- **Demo stage 18** — SYSTEM taxonomy seed, the demo's first issuers, and the `issuer_id` backfill so
  CON-1 computes over a classified book; the count pin relays at UNCHANGED 25/40/133.
- **`dedupe_tenant_wins` generalized** to take a key function (default `r.code`), forced by mypy
  because `classification_scheme` has no `code` — the same defect the verifier predicted from the
  opposite direction.

---

## Files Modified

### New source
- `packages/shared-python/src/irp_shared/classification/{__init__,models,service}.py`
- `migrations/versions/0056_classification.py`
- `apps/backend/src/irp_backend/api/classification.py`
- `packages/shared-python/src/irp_shared/demo/ref1_stage18.py`

### New tests
- `test_classification.py` (21 cases, every guard negative-controlled)
- `test_classification_pg.py` (tenancy arms, FR byte-stability, GUID/timestamp/Integer bind pins)
- `test_tenancy_floors_pg.py` (the three floors + the USING-only negative control)
- `test_demo_stage9zzzzzzzzz_ref1_pg.py` (final-position count pin, unchanged counts)

### Changed
- `reference/models.py` (the single closed-set declaration, N=7), `reference/issuer.py` (the freeze),
  `reference/service.py` (generalized dedupe), `entitlement/bootstrap.py` (3 codes + templates),
  `irp_shared/models.py`, `scripts/check_docs.py` (the coverage floor), `.github/workflows/ci.yml`
  (3 new PG steps), 31 PG test modules + 3 SQLite modules (literal collapse), ~21 migration-head
  pins, `test_synthetic.py` (glob 0056→0057), `apps/frontend/openapi.json` + `api-types.d.ts`.

### Governance
- `04_data_model/canonical_data_model_standard.md` (ENT-066/067/068; next-free → ENT-069)
- `04_data_model/audit_event_taxonomy.md` (the REFERENCE extension, node-folds-into-parent grain)
- `09_compliance_controls/control_matrix_skeleton.md` (CTRL-017 evidence)
- `11_decision_log/architecture_decision_log.md` (**AD-013-R2**)
- `CLAUDE.md` (**the hard invariant: closed 5-table → 7-table**)
- `02_requirements/requirements_backbone.md` + `_traceability_matrix.md` (REQ-SMR-006, REQ-CRD-005,
  CRD-003 narrowed, ~10 stale rows re-synced, coverage summary re-measured)
- `10_delivery_backlog/{wave_14_planning,ref_1_decision_record,con_1_decision_record,delivery_roadmap}.md`
- `docs/project_memory/current_state.md`

### Memory (outside the repo)
- NEW `wave-14-planning-state.md`, `ref-1-planning-state.md`; updated `delivery-roadmap-state.md`,
  `MEMORY.md`.

### Commits
`489c7fd` → `7723db4` (Wave-14 planning, PR #147) · `41e8836` → `dbce327` → `3f75907` → `138b38d` →
`da09a85` → `6a5b929` → `1ff0d70` (REF-1, PR #148 = `727f3c9`) · `255ed3b` (closeout, PR #149 =
`1a50b2c`) · `3b74a52` → `dfe0591` (the REF-1 fold + CON-1 planning, UNMERGED)

---

## Setup & Config

- Local PG: single reused container `irp_pg_local` (`postgres:16`, `irp:irp@localhost:5432/irp`).
- **PG tests are gated on `IRP_TEST_DATABASE_URL`**, not `DATABASE_URL` — setting the wrong one
  silently SKIPS every PG test (all `s`, exit 0).
- **`pyproject.toml` has `addopts = "-q"`** so passing `-q` again suppresses the summary line, and
  **`testpaths` covers three directories** (`apps/backend/tests`, `apps/worker/tests`,
  `packages/shared-python/tests`) — running one gives an incomplete signal.
- Full-PG protocol: reset schema (`DROP SCHEMA public CASCADE` + `GRANT USAGE/CREATE ... TO PUBLIC`)
  **before each run**, `alembic upgrade head`, purge `__pycache__`, `PYTHONDONTWRITEBYTECODE=1`.
- The demo PG suites connect as the **superuser**, which bypasses RLS.
- `gh` is not installed — CI via the public GitHub REST API.

---

## Pending Tasks

1. **TWO UNMERGED BRANCHES.** `ref-1-fold-missed-freeze` carries `3b74a52` (the delivered freeze + 4
   corrections, CI green) and `dfe0591` (CON-1 planning v2/v3). Neither is on `main`.

2. **CON-1 IS NOT RATIFIABLE — 8 NEW BLOCKING findings from the re-verification (47 total).** The
   headline: **the dual-share denominator ratified to fix v1 is itself refuted.**
   - `share_total_assets` does NOT equal total assets — that denominator excludes cash, cash items,
     receivables and unsettled trades, so it OVERSTATES shares and LIM-2 would record **false
     breaches into an append-only, non-withdrawable lifecycle**. Proposed fix: rename to
     `share_invested_long` on a `long_exposure` denominator, replace the boolean flag with a
     `denominator_basis` enum, and either forbid regulatory-shaped limits until a NAV entity exists
     or require a captured `total_assets` run input.
   - The dual-share form is **structurally unrepresentable** in the record's own ratified vocabulary:
     `_METRIC_MAP` maps a pair to ONE `result_attr`; both shares are FRACTION so the unit guard is
     blind to basis; the ratified `UNIQUE(run, metric_type)` bars two bases as separate rows; and
     suffixing overflows `String(30)` across THREE tables.
   - **`concentration.view` with `auditor_3l` included re-commits REF-1's exact SoD defect**, because
     CON-1 denormalizes the proprietary `issuer_id` into the result row — and the per-code pin would
     PASS on the defective set.
   - The two issuer-bucket CHECKs are **jointly unsatisfiable**; the nullable `issuer_id`
     re-introduces the PostgreSQL NULL-vacuity the same paragraph claims to fix; `scheme_family` is
     NOT on the assignment row so OQ-CON-1-24(ii) is unreachable as written; Part 5's restated
     citations reintroduce misattribution.

3. **A FIFTH (and sixth, seventh) undelivered REF-1 ratification** surfaced — one of which
   "CON-1's sector bucket rests on". Must be swept and folded.

4. **P1 six-ledger coverage in CON-1 is 2 of 6**; P6 is not applied anywhere in the record; migration
   `0057`'s downgrade body is unspecified; the count triple leaves N unpinned; Part 2's reference
   values were not re-derived after the folds.

5. **The ratified partial-coverage demo book is unreachable** from the shipped fixtures — both named
   options fail against the assignment grain.

**Honest position:** CON-1 needs a v4 rewrite, not another fold pass. Two consecutive verifier passes
found its foundation wrong in different places, and the second found the first fix wrong too.

---

## Errors & Workarounds

- **`dbce327` CI failure (self-inflicted).** Shipped migration `0056` without relaying the pins a
  migration moves: 21 migration-head assertions, the synthetic next-free-slot glob, three closed-set
  fences, and raw `action="CREATE"` literals a shipped guard correctly rejected. Root cause: ran
  `make check` before writing the tests that pin the head, then pushed on a partial signal.
- **529 Overloaded lost all six CON-1 recon lanes.** Verified the journal (6 started, 0 results,
  nothing recoverable) rather than assuming. Retried with two sequential batches of three plus a
  per-lane retry.
- **Demo-pollution false failures** — 31 tests failed because the battery ran twice without a schema
  reset (the documented `DEMO_TENANT_ID` census pollution).
- **The import-direction fence caught a real layering error** — `reference/models.py` importing
  `classification/models.py` inverts the dependency. Fixed by spelling the two table names literally
  (a table name is a governance fact, not a code dependency).
- **PostgreSQL's 63-char identifier limit** killed a 68-char FK name — found by the executed dry run,
  fixed by naming it explicitly in BOTH the ORM and the migration so `alembic check` sees no drift.
- **A dead RLS sandwich** copied from SCH-2 into a drop-the-table downgrade: RLS governs DML, not
  DDL, so `DROP TABLE` needs no sandwich. Removed rather than left as decoration.
- **`REQ-CRD-004` collided** with an existing requirement (Internal/shadow ratings) — the same
  id-namespace class the verifier caught on the slice name. Renumbered to REQ-CRD-005.
- **My own vacuous assertion**: `pytest.raises((ProgrammingError, Exception))` accepts anything.
  Tightened to require SQLSTATE 42501 plus a positive control.

---

## Key Exchanges

- **User: "dbce327 failed"** — caught a red CI before I did. Led to fixing the pins AND to verifying
  on both tiers thereafter, which is how the incomplete-testpaths measurement surfaced.
- **User: "Why should I start a fresh session?"** — my recommendation was inherited habit; the honest
  answer was to continue, since the context held the recon and fork inventory and the 1M window
  removed the pressure. Revised on the spot.
- **User asked for the denominator decision** after I flagged it as genuinely theirs; "proceed" was
  read as adopting option 2, flagged explicitly because I had muddled my own recommendation.

---

## Custom Notes

None.

---

## Quick Resume Context

`main` = `1a50b2c` (PR #149). **REF-1 is CLOSED and merged** — ENT-066/067/068, migration head
`0056`, next free id **ENT-069**, demo counts **UNCHANGED 25/40/133**, closed hybrid set **N = 7**
under AD-013-R2 with `CLAUDE.md` amended. Full-PG at REF-1's close: **2719/0**; after the fold branch:
**2720/0**.

**Two branches await merge:** `ref-1-fold-missed-freeze` (`3b74a52` delivered freeze + 4 corrections,
CI green; `dfe0591` CON-1 planning). **CON-1 is NOT ratifiable** — two verifier passes produced 93
findings (13 BLOCKING) and the second refuted the fix ratified for the first. Start by reading
`con_1_decision_record.md` Parts 1/3 against
`/private/tmp/.../tasks/con1_reverify.json`, then rewrite as v4 rather than folding again. The
governing correction: **no NAV/total-assets denominator is computable on this schema**, so any share
CON-1 emits must be named for what it provably is and forbidden from carrying a regulatory-shaped
limit until a cash/NAV entity exists.

---

## Raw Session Log

> **Note on fidelity:** this section is a faithful turn-by-turn record rather than a verbatim
> transcript — the session ran to roughly 100 turns with several 100KB+ subagent payloads, so
> verbatim reproduction would exceed practical file limits. Every decision, finding, command class
> and correction is captured above and below; the full subagent outputs remain on disk at
> `/private/tmp/claude-501/.../tasks/{wiuqetzd1,w03zmr0l5,wf1ywihcz,wqalizw0x,wsq5bwpec,w1l1vgzlq,wp6mwzas1,wojjugwka}.output`
> and the parsed forms at `con1_parsed.json`, `con1_verify.json`, `con1_reverify.json`,
> `recon_parsed.json`, `verify_parsed.json`, `ref1_parsed.json`, `ref1_verify.json`.

**1. `/model` → `/resume`.** Loaded CLAUDE.md, the last three session summaries, `current_state.md`
and roadmap Part 2.17. Reported: Wave 13 CLOSED + RATIFIED at `2411d00`, P1–P6 standing, counts
25/40/133, head `0055`, NEXT = Wave-14 planning.

**2. "Approved. Proceed with workflows."** Ran a 6-lane recon (`wiuqetzd1`) over requirements, data
model, capture infra, engines/reads, scheduler/calendar, wave context. Drafted `wave_14_planning.md`
single-threaded. Ran a 4-lane refute-by-default verifier (`w03zmr0l5`): **24 findings, 2 BLOCKING** —
the slice id "RD-1" collided with a shipped Wave-3 slice, and the taxonomy-tenancy recommendation
contradicted Accepted AD-013 uncited. Both hand-verified, all folded. Committed `489c7fd`, CI green.

**3. Gate briefed in plain language; user "Proceed".** Ratified OQ-W14P-1…8. Wrote roadmap Part 2.18,
the Part-3 homings, the amendment-log row, the OQ-W14P-7 register re-sync (~10 stale rows, RTM
summary re-measured), three declared Tier-2 corrections. `make check` 2201/480 → committed `7723db4`,
CI green all six. Merged as PR #147.

**4. "Why should I start a fresh session?"** Gave the honest accounting: the recommendation was
inherited, the 1M window removed the context-pressure argument, and continuing kept the fork
inventory. Recommended continuing; noted the branch should merge first so the P1 sweep measures
delivery.

**5. REF-1 planning.** 6-lane recon (`wf1ywihcz`) instructed to treat the wave plan as unverified —
returned **52 corrections to a document ratified hours earlier**. Drafted the record; 4-lane verifier
(`wqalizw0x`) returned **61 findings, 3 BLOCKING**: a single `.view` code would hand `auditor_3l` its
first proprietary-identity read (invisible because SoD pins are per-code); the grain argument's
decisive reason was refuted; and **the record's own status line was invisible to the closure-stamp
gate — recurrence EIGHT** (executed `_status_lines` → `[]`). All folded; the BLOCKINGs hand-verified.

**6. Gate briefed; user "proceed".** Ratified OQ-REF-1-1…30. Built the slice across five commits:
substrate + migration `0056` (P4 dry run found the 63-char FK limit and the dead RLS sandwich); the
CI-failure fix after the user flagged `dbce327`; three platform floors + the classification PG suite +
two REQ mints; the read surface + generalized dedupe + the Integer PG pin (whose first negative
control did not fire, because psycopg sends `str` as *unknown*); demo stage 18 (three superuser-RLS
isolation defects found and fixed). Closeout: AD-013-R2, the CLAUDE.md invariant, the P1 six-ledger
sweep. Merged as PR #148 = `727f3c9`; closeout PR #149 = `1a50b2c`; verify-on-main clean.

**7. CON-1 planning.** First recon attempt lost all six lanes to 529 overload; journal verified empty;
retried in two batches of three (`w1l1vgzlq`). The recon **found three false claims in REF-1's merged
record** — the undelivered `issuer.sector` freeze, the unwired `snapshotVerified` badge, and a node
fence with no writer. All three hand-verified and folded as `3b74a52` (freeze delivered, full-PG
2720/0, CI green). Drafted CON-1; my own arithmetic check caught a wrong HHI in my own draft.

**8. Verifier pass (`wp6mwzas1`): 46 findings, 5 BLOCKING** — including that all three rule-6a
regulatory citations were misread, the result table could not represent the per-issuer bucket, and the
grain constraint would be silently vacuous. Folded to v2; found a **fourth** false REF-1 claim while
drafting. Committed `dfe0591`.

**9. Briefed the denominator as a genuine user decision** (three options). "proceed" read as option 2
(dual-share), recorded with the interpretation flagged. Ran a second verifier pass (`wojjugwka`):
**47 findings, 8 BLOCKING — the dual-share fix is itself refuted**, having relocated the fail-open
defect rather than removed it.

**10. `/compress`.** This log.
