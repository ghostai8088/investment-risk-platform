# Wave-14 Planning — "Real data through the governed rails" (the ratified direction, sliced)

> **Status: DRAFT, VERIFIED — pre-ratification.** Direction ratified 2026-07-29 at the Wave-13
> close (`delivery_roadmap.md` Part 2.17). This document proposes the slice sequence and the
> wave-level decision ledger (OQ-W14P-1…8) for Tier-3 ratification. On ratification, the sequence
> is written into `delivery_roadmap.md` as **Part 2.18** and this document is stamped RATIFIED.
>
> **Method (honest labeling, per the independence ladder):** recon ran as a 6-lane parallel
> subagent fan-out in fresh contexts (requirements / data model / capture infra / engines+reads /
> scheduler+calendar / wave context), every register entry verified against today's code per the
> P3 standing rule; the draft was authored single-threaded; the pre-ratification verifier pass
> ran as 4 refute-by-default subagent lanes in fresh contexts (ladder rung 2) — **24 findings
> (2 BLOCKING, 4 HIGH, 12 MED, 6 LOW), ALL folded**; the ledger is Part 6. Both BLOCKINGs were
> re-verified by hand against the repo before folding.

## Part 0 — The organizing facts (recon-verified 2026-07-29, all against code at `2411d00`)

Platform position: migration head `0055`; next free canonical id **ENT-066** (ENT-032
`limit_utilization` reserved on paper; ENT-058 paper-only); demo counts **25/40/133** with the
final-position pin held by the SR-1 stage-17 PG suite (the count-pin relay doctrine); FE 32
files / 204 tests.

1. **Reference dimensions do not exist.** The entire classification substrate today:
   `issuer.sector` — nullable free-text `String(100)`, API-writable, consumed by NOTHING
   (`reference/models.py:236`); `legal_entity.jurisdiction` — ISO-3166 **domicile**, not
   country-of-risk (`reference/models.py:205`); no industry column, no country-of-risk column,
   no liquidity attribute anywhere in the schema. No demo fixture creates an issuer; no engine
   reads `sector`. The Wave-12/13 "0% computable" claim re-verified true.
2. **No requirement covers classification vocabularies.** REQ-SMR-005 is scoped to
   "currency, rating scale" (CAP-2.5b) only — a **REQ mint** is needed (the BT-1→REQ-MKT-005 /
   RM-1→REQ-MKT-006 precedent).
3. **Concentration is a NEW governed family, not an extension.** `exposure_aggregate` is IA
   append-only with `instrument_id NOT NULL` in the run-grain unique constraint and a closed
   one-member `EXPOSURE_TYPES` vocab — a sector/issuer/country-grain row structurally cannot
   live there. A reproducible concentration run also needs a **new snapshot COMPONENT_KIND**
   (the 23-kind vocabulary has nothing for classification reference data; AD-014 requires the
   compute to read only pinned content). SCH-2's `FAMILY_REGISTRY` gives a new family the
   dispatch + CTRL-003 model-binding gate by declaration **plus a migration**: the
   total-enumeration DB CHECK `ck_schedule_model_version_by_family` (0053) is a two-family OR,
   so a new schedulable family is un-insertable until the CHECK is amended — and the CHECK's
   content depends on the family's model fork, so the fork must be decided before the migration
   is authored (the slice-gate ordering provides this).
4. **The limit machinery cannot express a concentration limit** in three specific places:
   `_METRIC_MAP` admits exactly (VAR × 6) + (ACTIVE_RISK × TRACKING_ERROR); `_resolve_latest`
   is a hardcoded two-family if/else; `limit_definition` scopes only by exact
   `scope_portfolio_id` — "sector TECH ≤ 20%" has nowhere to put TECH. `breach` echoes the
   metric identity (run_type, metric_type, benchmark_id) but NOT the portfolio scope — so a
   dimensional selector needs BOTH a `limit_definition` column and a `breach` echo column, and
   the missing scope echo is a pre-existing gap the LIM-2 echo design should note. Downstream
   of a Breach row everything rides for free (lifecycle, notifications, FE queue/detail).
5. **ENT-006 is vocabulary-only and its consumers are deliberately holiday-blind.**
   `calendar`/`calendar_holiday` ARE 2 of the closed 5 hybrid tables, but: the SYSTEM seed is
   one XNYS calendar with TWO token holidays; holiday children are **create-once**
   (`create_calendar` folds them into one REFERENCE.CREATE; `update_calendar` patches head
   attrs only — an annual holiday refresh has no rail); zero `is_business_day`-class functions
   exist anywhere; the month-end predicate is weekend-only pure arithmetic in TWO deliberately
   hand-mirrored copies (scheduling + perf) under a conformance pin. Residual: 4 collisions in
   144 months 2024–2035; **next real one 2027-05-31 (Memorial Day)**; a burned tick bucket is
   PERMANENT (IA ledger + `uq(schedule_id, scheduled_for)`, no re-fire verb; ≤33-day
   out-of-band repair window).
6. **The convention-atomicity trap:** RM-1's `is_month_end` accepts calendar-month-end OR last
   WEEKDAY — so the true last business day before a Monday holiday (2027-05-28) would be
   **REFUSED by the governed rolling-risk series** the moment the scheduler learns holidays.
   Scheduler and perf conventions must move in the SAME slice, and the weekend-only convention
   is a DECLARED registered assumption of shipped RM-1/SR-1 numbers — moving it is a
   model-convention change, not a bugfix.
7. **Two capture rails exist; neither is complete for vendor files.** Per-row governed capture
   binders (full tenancy/RLS/audit/lineage/DQ, no batch identity) vs the P1A-4 CSV staging
   pipeline (batch identity ENT-047/048 + anti-corruption + fail-closed DQ, but staged rows
   have ZERO canonical-mapping consumers — a dead end; its recorded "P1B/P1C" deferral target
   is stale). DQ has exactly three rule types (NOT_NULL / ALLOWED_VALUES / RANGE) — **no
   completeness/gap/reconciliation rule type exists, and that is the dominant vendor-file
   failure mode** (a file missing a holiday or an issuer passes all three silently). Disposed
   at REF-1's gate (Part 2 slice 0) — not left hanging.
8. **The rf vendor-diligence obligation is real and open:** `capture_benchmark_return` accepts
   ANY `return_date` (no month-alignment refusal — the SR-1 record's overclaim was corrected at
   the close); the Sharpe binder catches a partial shift, never a uniform one; enforcement is
   the declared convention + onboarding diligence — "the Wave-14 carry"
   (`perf/sharpe_kernel.py:86-94`, `snapshot/service.py:1962-1966`).
9. **REQ-LIQ-001 splits cleanly in two:** the tier ASSIGNMENT is a captured input (binds no
   run/snapshot/model — the pattern-choice invariant), while "% illiquid" is a governed derived
   number (run + snapshot bound; whether a registered `model_version` applies — tier vocabulary
   + denominator as methodology vs model-less EXPOSURE_AGGREGATE-class arithmetic — is the
   SAME fork CON-1 carries, resolved at LQ-1's slice gate). **REQ-LIQ-002 (redemption stress &
   waterfall) is a scenario engine** — the existing CAP-9 substrate is linear factor shocks
   only; a redemption scenario is not representable in it. Materially heavier than everything
   else in the named scope.
10. **Stale registers found at recon (the P3 obligation, both directions):** REQ-LIM-001/002/003,
    REQ-BRC-001/002/003, REQ-SCN-001, REQ-ADM-001 all read "Draft" while the platform shipped
    them (SCN-001 as far back as Wave 2's P3-6 — stale ~11 waves; LIM/BRC in Waves 11–12;
    ADM-001 at Wave 9's SSO-1); REQ-DQR-001 says "2 generic evaluators" (three exist);
    REQ-SMR-004 defers roll math "to P1C" (closed — of its QS-10/11 pair, **only the QS-11
    holiday/business-day half is the Wave-14 carry (CAL-1); QS-10 day-count stays
    trigger-based** on the first accrual/pricing methodology needing a declared convention);
    RTM §3 coverage summary predates six REQ mints; `ingestion/models.py:12` defers canonical
    mapping "to P1B/P1C" (long closed); `wave_13_close_review.md:113-114` attributes an
    "ES-multiplier v2" to SR-1 that SR-1's record does not contain (it is FL-1's recorded
    backend v2); `sr_1_decision_record.md:68/:97` pin the ENT-021 curve revisit to "Wave-14"
    BY NAME on the then-assumption that Wave 14 meant curve feeds — once this plan ratifies a
    curve-free Wave 14, those pointers need re-pointing to the event trigger.

## Part 1 — Scope boundary: what "real data" means in this wave

**IN:** genuine external/authoritative datasets onboarded through the governed capture rails —
a real market-holiday calendar set, a real classification taxonomy (sector/industry/
country-of-risk) applied to the platform's instruments/issuers, real-shaped liquidity tier
assignments — plus the vendor-onboarding **diligence control** (the rf dating-convention
obligation discharged as an auditable artifact, not prose).

**OUT (recorded, with triggers):**
- Live vendor adapters / API/SFTP feeds — REQ-INT-002/003 stay Draft; **trigger: a real vendor
  contract.**
- The REQ-LIQ-002 redemption waterfall (named in the ratified tee, so this is the OUT list's
  highest-stakes entry) — see OQ-W14P-5; on ratification it is HOMED by roadmap amendment to
  the Part 3 "Private assets + liquidity (RTM-P4)" theme with **trigger: the first scenario
  slice extending CAP-9 beyond linear factor shocks, or a user redemption-stress ask.**
- The ENT-021 curve-feed revisit for the rf leg — SR-1's recorded trigger, accurately quoted,
  is "becomes attractive only when Wave-14 real-data onboarding lands **genuine curve feeds**";
  no curve feeds are in this wave, so it does not fire (and the record's two wave-named
  pointers re-point to the event trigger via OQ-W14P-7).
- P3-8's benchmark-series trading-calendar completeness validation — its named prerequisite
  (business-day functions + real holiday data) DISSOLVES at CAL-1, so it is either ridden
  there or re-deferred: **carried as a named CAL-1 slice-gate OQ** (paired with the
  DQ-completeness fork at REF-1's gate).
- QS-10 day-count conventions (the other half of REQ-SMR-004's deferral) — **trigger: first
  accrual/pricing methodology needing a declared convention.**
- Monte-Carlo/credit themes (roadmap Part 3 unchanged); FE toolchain majors (OQ-W14P-8).

## Part 2 — Proposed slice sequence (ratifies as roadmap Part 2.18)

*(Slice 0 is named **REF-1** — "RD-1" is a shipped Wave-3 slice (`rd_1_decision_record.md`,
PR #17) and RD-1/2/3 are the existing dedup-hygiene series; REF-1 verified unused across the
roadmap, backlog filenames, and memory index.)*

| # | Slice | What it is | Size |
|---|---|---|---|
| 0 | **REF-1 — reference dimensions + the vendor-classification capture rail** | The wave's substrate. Mints the classification REQ (fact 2) and the new entities (ENT-066+): sector/industry/country-of-risk as governed reference dimensions with a controlled taxonomy, captured through the governed rails with lineage + DQ; the demo campaign's FIRST issuer-creating, classification-bearing stages (a new fixture domain — issuers exist nowhere in the demo today; count-pin relay moves the baton); disposition of the free-text `issuer.sector` (govern, backfill, or deprecate); the **vendor-onboarding diligence control** discharging the rf carry (checklist artifact + control-matrix row; the capture-time convention-field option is a SECOND migration if taken — named split candidate). Tier-3 forks AT THE SLICE GATE: grain (issuer vs instrument per dimension); storage + temporal class (EV attribute vs FR assignment table — the AD-005 §2A promotion test); taxonomy scheme (OQ-W14P-3 sets direction); onboarding rail (per-row binders vs completing the staged→canonical mapping — the mapping branch is an L on its own and fires split trigger (a) below); **scheme tenancy per OQ-W14P-6's ratified direction** (AD-013 cited there — the wave gate decides direction, the slice gate the mechanics); **completeness/gap DQ rule type: in or out** (fact 7 — the rail slice is its natural home; if out, the trigger is the first vendor dataset whose acceptance needs it, likely CAL-1's holiday set). **Split triggers ratified with OQ-W14P-1:** (a) rail fork = staged→canonical completion → split REF-1a (dimensions) / REF-1b (mapping); (b) if the slice runs long, the diligence control is the first split candidate (near-zero coupling). | **L** |
| 1 | **CON-1 — concentration, the 23rd governed number family (REQ-CRD-003's concentration half)** | A NEW result family (new table, migration incl. the `ck_schedule_model_version_by_family` amendment — fact 3, new snapshot COMPONENT_KIND for pinned classification, FAMILY_REGISTRY entry) computing dimensional concentration (per issuer / sector / country: share-of-total, top-N, HHI-class metrics — the exact set is the slice's Tier-3 methodology gate WITH the Part-4 rule-6a cited external-benchmark research section, e.g. UCITS 5/10/40-class regimes). Derived-of-derived over the latest COMPLETED exposure run (the VaR precedent). Model fork at the slice gate: registered model_version (bucketing + denominator are methodology) vs model-less like EXPOSURE_AGGREGATE — decided BEFORE the migration is authored. **CON-1's dimension-identity representation (code vs FK vs scheme-qualified code) ratifies WITH the LIM-2 selector shape as a named acceptance constraint** (REQ-CRD-003 "limits-ready") — the representation is shared; only the columns land in LIM-2. Rule-7 reads + FE in-slice; new non-String filter columns get **PG-tier pins**. Issuer grain = immediate issuer; the ultimate-parent ROLLUP stays deferred (REQ-SMR-002; adjacency exists, traversal does not — recorded scope-out with trigger). | M/L |
| 2 | **LIM-2 — concentration limits: the dimensional selector** | Makes CON-1's metrics literally "limits-ready": dimension selector columns on `limit_definition` + echo columns on `breach` (migrations on both; the OD-I frozen-identity rule extends to them; the missing portfolio-scope echo from fact 4 is addressed in the same echo design), `_METRIC_MAP`/`_resolve_latest` re-founded on a registry (the SCH-2 FAMILY_REGISTRY pattern — kills the hardcoded two-family if/else before a third family makes it a trap), possibly realizing reserved ENT-032 `limit_utilization` (slice-gate call). Everything downstream rides for free — verified at recon. P4 dry run on the double-table ALTER with the OD-I identity checks (the wave's highest-risk migration). | M |
| 3 | **CAL-1 — ENT-006 holiday-calendar resolution** | Real holiday data + business-day logic, atomically. In-slice scope, enumerated: (a) a real market-calendar holiday set (source licensing checked at the gate — OQ-W14P-6's conditional); (b) the **holiday-refresh write path that does not exist today** (children are create-once); (c) a shared business-day/roll helper in a leaf module (scheduling cannot be imported by perf — extend the mirror + conformance-pin pattern or re-home it); (d) the scheduler's month-end predicate AND RM-1's `is_month_end` moving in the SAME slice (fact 6 — the refusal trap), with the model-convention consequence for shipped RM-1/SR-1 registered assumptions handled as a governed convention change (new/amended model_version — Tier-3 at the slice gate) and GIPS 2.A.23.b "last business day" as the rule-6a citation; (e) the calendar↔schedule binding (per-schedule FK — **a `schedule` migration if taken** — vs tenant default vs SYSTEM XNYS) and the tenant-override-moves-a-live-grid hazard; (f) the P3-8 benchmark-series completeness OQ (Part 1). **Split line if the gate finds it running L: CAL-1a (dataset + refresh write path) / CAL-1b (the atomic convention move + model-version amendment)** — the atomicity constraint binds only CAL-1b's two predicates to each other, not the data onboarding to them. Forcing function 2027-05-31 is comfortably post-wave. | **M/L** |
| 4 | **LQ-1 — liquidity tiers (REQ-LIQ-001)** | Both halves, correctly patterned. Captured half: the tier ASSIGNMENT as a captured input (instrument-or-position grain is the slice-gate fork; REQ-LIQ-001 says positions, tiers are plausibly instrument attributes) with a controlled tier vocabulary, entering through REF-1's rail, list reads from birth. Governed half: **% illiquid** as a new governed derived family — new result table + migration, a snapshot COMPONENT_KIND for pinned tier assignments (same AD-014 argument as fact 3), the registry/CHECK amendment, **the model fork (registered methodology vs model-less — fact 9) at the slice gate**, Rule-7 reads + FE, demo stage, PG-tier pins. **LQ-1's denominator convention adopts or explicitly diverges from CON-1's ratified denominator** (a consistency constraint, decided at LQ-1's gate with CON-1's record cited). REQ-LIQ-002 does NOT ride (OQ-W14P-5). | **M/L** |

**Dependency spine (honest form):** REF-1 is the hard substrate for CON-1 (dimensions) and
LQ-1 (the assignment rail + the same capture conventions). CON-1 → LIM-2 is a hard order
(selector needs the metric family). **CAL-1 has NO hard dependency on REF-1** — holiday sets
land via the SYSTEM-chain seed/binder path (already-hybrid tables), not the classification
rail; the reuse is only file-parse/DQ conventions — so CAL-1's position is a workload/payoff
choice, argued in OQ-W14P-1 on those honest terms. LQ-1 is independent of CAL-1.

## Part 3 — Wave-level decision ledger (Tier-3, ratify at this gate)

- **OQ-W14P-1 — the slice sequence.** **Recommend A: REF-1 → CON-1 → LIM-2 → CAL-1 → LQ-1.**
  The argument is payoff order, not dependency: the user-directed analytics remainder
  (2026-07-26: "no sector/geography exposure, no concentration") completes earliest, and the
  2027-05-31 forcing function leaves CAL-1 ten months of slack. B: CAL-1 second — equally
  legal (no dependency bars it); de-risks the dated collision earliest and onboards the
  simplest real dataset first; costs the analytics payoff two slices of delay. C: fold LIM-2
  into CON-1 — refuted by the SCH-2 sizing lesson (two migrations + a registry re-founding +
  a governed number is the hidden-L shape). **The REF-1 and CAL-1 split triggers (Part 2)
  ratify with this OQ.**
- **OQ-W14P-2 — the "real data" boundary.** **Recommend A:** authoritative external datasets
  through governed capture; NO live adapters this wave (REQ-INT-002/003 stay Draft with the
  vendor-contract trigger). B: include one real adapter — refuted by recon: no vendor
  relationship exists, and an adapter without a counterparty is scaffolding.
- **OQ-W14P-3 — taxonomy licensing (outward-facing).** **Recommend A: an open/vendor-neutral
  scheme** (ICB/GICS-SHAPED structure without licensed content, or NACE/NAICS-class public
  codes) — no procurement, no license exposure; the dimension tables carry a `scheme`
  discriminator so a licensed taxonomy is additive data later. B: license GICS/ICB now — a
  real procurement/legal decision the USER owns; nothing in-wave requires it. The scheme
  choice inside A finalizes at REF-1's gate. *(Note: the swap-in-later mechanics depend on
  OQ-W14P-6's tenancy direction — under a global scheme one curated swap serves all tenants;
  under per-tenant schemes each tenant swaps separately.)*
- **OQ-W14P-4 — split REQ-CRD-003.** **Recommend A:** mint the spread-sensitivity half
  (CAP-6.3) as its own REQ (the BT-1→REQ-MKT-005 precedent) so concentration (CAP-6.4) can
  reach Done without an unpayable spread conjunct; spread sensitivity stays themed (Part 3,
  credit) with the curve-feed trigger. B: leave the compound row — guarantees a permanently
  In-Progress requirement.
- **OQ-W14P-5 — REQ-LIQ-002 (redemption waterfall).** **Recommend A: defer, homed and
  triggered** — a roadmap amendment homes it to the Part 3 RTM-P4 theme with trigger "the
  first scenario slice extending CAP-9 beyond linear factor shocks, or a user
  redemption-stress ask" (Part 1). The substrate cannot represent it (fact 9); naming
  LIQ-001+002 together in the tee named the capability family, not a commitment to the
  waterfall engine. B: in-wave — adds an L-sized engine to a 5-slice wave.
- **OQ-W14P-6 — tenancy of the real datasets + the demo tenant.** Three clauses, briefed
  separately because one touches an Accepted baseline:
  **(i) Scheme tenancy — a genuine fork against AD-013 (surfaced per the objectivity rule).**
  AD-013 (Accepted 2026-06-18) classes "standard calendars/rating scales/**classifications**"
  as GLOBAL system reference; AD-013-R1 scoped the hybrid implementation to the five tables
  that existed at P1B-0 (`currency, calendar, calendar_holiday, rating_scale, rating_grade`) —
  an implementation scoping, not a decision that standard classifications are proprietary; the
  structural twin of a taxonomy vocabulary (`rating_scale`/`rating_grade`) IS hybrid with a
  SYSTEM seed. **Recommend A: extend the hybrid set** for the new scheme/taxonomy tables via
  an explicit AD-013-R2 + an amendment to the CLAUDE.md closed-set invariant and the
  migration-0008/ORM closed-set mirrors (a user-ratified invariant change — that is exactly
  what this gate is for), SYSTEM-seeded via the bootstrap mechanism, tenant-overridable per
  `dedupe_tenant_wins`. B: proprietary symmetric RLS — no invariant change, but the recorded
  consequences: a SYSTEM seed is unreadable under symmetric `USING`, so NO curated global
  source exists, every current and future tenant re-captures the taxonomy, and OQ-W14P-3's
  swap-in-later degrades to per-tenant swaps. (AD-013's rejected third pattern — separate
  RLS-exempt global tables — was considered and rejected at R1; recorded here so the option
  space is honest.) Final mechanics at REF-1's gate under the ratified direction.
  **(ii) Assignment tenancy — not a fork:** classification/tier ASSIGNMENTS attach to
  proprietary issuers/instruments (MNPI-adjacent) and stay per-tenant symmetric either way
  (the OD-P1B-C precedent).
  **(iii) Demo + holiday data.** **Recommend:** the demo campaign EXTENDS (new stages create
  issuers/classifications/tiers; the 25/40/133 final-position pin RELAYS per the baton
  doctrine); holiday sets land as SYSTEM rows **conditional on an open/public source**
  (exchange-published calendars) — a licensed vendor calendar product falls under the
  `fx_rate` per-tenant-licensed precedent and lands as tenant captures (the licensing check
  is a CAL-1 gate input). Alternative (a second "real" tenant) doubles every census with no
  user-visible payoff this wave.
- **OQ-W14P-7 — the stale-register re-sync (P3 discharge), tier-split honestly.**
  **Recommend A: ride this planning branch, in two declared classes.** Class 1 (Tier 0/1,
  status-not-decisions): the REQ/RTM status flips with hashes (LIM/BRC/SCN/ADM rows, DQR
  evaluator count, RTM §3 summary) and the REQ-SMR-004 re-point **to exactly "QS-11 half →
  CAL-1; QS-10 half → trigger-based"** (fact 10). Class 2 (**Tier 2 — production source or
  ratified-record text**, riding the already-Tier-2 planning PR as declared items): the
  `ingestion/models.py:12` docstring re-point (a source file); the `wave_13_close_review.md`
  ES-multiplier correction (an edit to a ratified close record — the close's own
  corrected-in-place precedent, recorded as an amendment); the `sr_1_decision_record.md:68/:97`
  re-points of "Wave-14" to the event trigger (same class). B: defer to first closeout —
  leaves registers this plan CITES false for a slice.
- **OQ-W14P-8 — FE toolchain debt.** **Recommend A: re-defer with recorded triggers**
  (TS 7 / eslint 10 / jsdom 30 majors: trigger = first FE feature slice or a security
  advisory; the six untypechecked root guard tests: same trigger, needs one new dev
  dependency). No dated cliff exists (the 2026-10-24 cliff died with FE-M1). B: an FE-H1
  hygiene slice in-wave — no forcing function; Wave-14's payoff is elsewhere.

## Part 4 — Standing-rule application map (how P1–P6 bind this wave)

- **P1 (six-ledger sweep + verify-on-main):** every slice closeout; REF-1's is the wave's
  first full sweep. New ENT ids at REF-1/CON-1/LQ-1 move the registry + next-free pointer.
- **P2 (shared-tree mutation):** recon and verifier fan-outs in this wave are read-only; any
  mutation battery stages explicit paths, greps the COMMIT, purges `__pycache__`.
- **P3 (registers are claims):** discharged at this recon (fact 10 + OQ-W14P-7); re-runs at
  every slice's own planning recon.
- **P4 (executed dry runs):** **binds EVERY migration slice — REF-1, CON-1, LIM-2, LQ-1, and
  CAL-1 if the binding FK or convention-field migrations land.** LIM-2's double-table ALTER
  with the OD-I identity checks is the highest-risk instance. Every dry-run number is
  re-measured at closeout, never carried as a pin.
- **P5 (assert by evidence):** every new refusal/gate test asserts the evidencing artifact;
  column-type-sensitive guards (CON-1/LQ-1's new filter columns) get **PG-tier pins** — the
  unit tier is structurally blind to the class (the streak-ending lesson).
- **P6 (non-vacuity floors):** the new FAMILY_REGISTRY/metric-registry censuses extend the
  set-equality pattern; any new enumerating matcher (taxonomy scheme census, tier vocabulary,
  the widened `ck_schedule_model_version_by_family` enumeration) ships with a floor.
- **Rule 6a (external benchmark research):** CON-1 (concentration metrics) and CAL-1 (the
  business-day convention change) are methodology slices — cited research sections required.
- **Rule 7 (reads in-slice):** CON-1 and LQ-1 mint governed numbers — entity/time reads + FE
  consumers ship in the same slice; FE types regenerate in-slice (the FE-2 contract guard).
- **SCH-2 lesson (demo stage = mandatory scope):** REF-1, CON-1, LIM-2, LQ-1 each carry a demo
  stage; CAL-1 exercises a real holiday boundary in the demo grid.

## Part 5 — What this wave decides vs defers (the pre-emption ledger, exact)

**Decided AT THIS GATE (wave level):** the slice sequence + split triggers (OQ-1); the
real-data boundary (OQ-2); taxonomy licensing direction (OQ-3); the REQ-CRD-003 split (OQ-4);
the LIQ-002 deferral + homing (OQ-5); the scheme-tenancy DIRECTION incl. whether the hybrid
closed set is amended (OQ-6i — this one deliberately pre-empts part of REF-1's RLS fork, and
says so; the mechanics stay at the slice gate); the demo/holiday landing pattern (OQ-6iii,
holiday clause conditional on licensing); the re-sync tiering (OQ-7); the FE-debt deferral
(OQ-8).

**Deferred TO SLICE GATES (enumerated, consistent with Part 2):** REF-1 — dimension grain;
storage + temporal class (AD-005 §2A); the concrete scheme inside OQ-3's direction; the
onboarding rail; the RLS mechanics under OQ-6i's direction; the DQ-completeness rule-type
fork; the `issuer.sector` disposition; the diligence-control form (checklist-only vs
convention field). CON-1 — the metric set + denominator; the model fork; the
dimension-identity representation (with the LIM-2 acceptance constraint). LIM-2 — the ENT-032
call; the selector/echo column shapes. CAL-1 — the calendar↔schedule binding; the
convention-versioning mechanics (new vs amended model_version); the holiday-source licensing
check; the P3-8 completeness OQ; the CAL-1a/1b split call. LQ-1 — the assignment grain; the
tier vocabulary; the model fork; the denominator-consistency call against CON-1's record.

Each slice runs the full per-slice discipline: decision record + plan + pre-ratification
verifier pass + OQ ratification + adversarial review + closeout sweeps (P1).

## Part 6 — Pre-ratification verifier pass: findings ledger

Four refute-by-default lanes (claims-vs-code / sequencing-sizing / governance-invariants /
completeness-critic), fresh contexts, 2026-07-29. **24 findings; all folded into this
revision; none deferred; none refuted after hand re-verification.** Convergent findings
(two lanes independently): the RD-1 slice-id collision; the CAL-1 dependency overclaim; the
LQ-1 model-fork pre-emption.

- **BLOCKING (2):** slice-0 id "RD-1" collides with the shipped Wave-3 slice → renamed REF-1
  (verified unused). The taxonomy-tenancy recommendation contradicted Accepted AD-013 without
  citing it → OQ-W14P-6 rebuilt around the AD-013/AD-013-R1 fork with both options' recorded
  consequences (hand-verified against `architecture_decision_log.md` before folding).
- **HIGH (4):** REF-1 resized M/L→L with ratified split triggers; CAL-1 resized M→M/L with its
  seven workstreams enumerated + the CAL-1a/1b split line; the OQ-W14P-6/Part-5 pre-emption
  contradiction → Part 5 rewritten as an exact decided-vs-deferred ledger; (the second
  RD-1-collision report, converged).
- **MED (12), folded:** P4 scope corrected to every migration slice; the LQ-1 model fork
  restored to its slice gate (fact 9 + Part 2 + Part 5, twice-reported); the CAL-1→REF-1
  dependency overclaim removed from the spine and OQ-1's A-vs-B re-argued honestly
  (twice-reported); fact 3's registry-only claim corrected with the
  `ck_schedule_model_version_by_family` migration coupling (hand-verified in 0053); LQ-1
  resized with the full governed-family checklist + the CON-1 denominator-consistency
  constraint; OQ-W14P-7 tier-split (two items are Tier-2 by the footprint algorithm); the
  holiday-source licensing conditional added to OQ-6iii; the DQ-completeness gap disposed at
  REF-1's gate + OUT-list trigger; P3-8's dissolving deferral homed as a CAL-1 gate OQ; the
  SR-1 wave-named curve pointers added to the re-sync list.
- **LOW (6), folded:** breach echoes metric identity not portfolio scope (fact 4); SCN-001
  staleness re-attributed to Wave 2 (strengthens OQ-7); the QS-10/QS-11 split in fact 10 and
  the SMR-004 re-point; the LIQ-002 trigger made concrete + homed; the CON-1↔LIM-2
  frozen-identity representation constraint named; Part 2/Part 5 fork lists made identical.
