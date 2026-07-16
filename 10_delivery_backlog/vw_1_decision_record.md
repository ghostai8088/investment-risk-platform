# VW-1 Decision Record — model-validation workflow (SR 11-7 / P7; Wave-5 slice 2)

| | |
|---|---|
| **Status** | **CLOSED 2026-07-15** — implementation `726373f` + CI fix `93ab215` **merged via PR #36 = `a9a00eb`, CI GREEN** (migration head `0039_model_validation`). RATIFIED 2026-07-14: OQ-VW-1-1…7 approved as recommended (user: "Approved"; OQ-VW-1-5 staleness fork answered **A** — VW-1 delivers the generic ongoing-monitoring leg, the σ_e estimate-age gate is a named BT-2 ride-along). Review dispositions: Part 6. Residual deferrals: Part 3 (all trigger-based). |
| **Grounding** | Drafted 2026-07-14 against `main` HEAD `29bc5a2` (merge of PR #34 = RD-3 impl `d751fde`). Verified at HEAD: migration head `0038_var_residual_variance` (next free = **0039**); **ENT-037 `model_validation` RESERVED** in `04_data_model/canonical_data_model_standard.md` (BC-11 block — realization, NOT a new mint; next free mint id would be ENT-058, not needed); **`MODEL.VALIDATE`/`.APPROVE`/`.RESTRICT`/`.RETIRE` RESERVED** in the audit taxonomy EVT-050 block (activation, not mint); REQ-MDG-002/003 exist as **Draft** RTM rows (no REQ mint needed); permission catalog carries `model.inventory.view`/`model.inventory.register` ONLY (no validate verb — an R-07 mint is required); 14 registered model codes across 12 governed run families, ALL at the non-enforcing `validation_status="UNVALIDATED"`; the ONE enforcing registry gate today is `assert_model_version_of` (requires `model_version.status == "REGISTERED"`, called pre-create by every model-bound binder). |
| **Wave-5 mandate** | Roadmap Part 2.8 slice 2 (ratified at the Wave-4 close, OQ-W4C-2 fork answered "A: Self-governance"): "validation states + independent-review/approval transitions on the model registry; periodic-revalidation triggers consuming BT-1 outcomes; the **estimate-staleness governance** register item folded in as the ongoing-monitoring leg. The named 'nearest supervisory gap' at three consecutive closes." |

## Part 1 — Decisions (OD-VW-1-A…H)

- **OD-VW-1-A — Entity: realize ENT-037 `model_validation` as a CAPTURED, IA append-only
  validation record at model_version grain** (+ two IA children: `model_validation_finding`,
  `model_validation_evidence`). A validation is a point-in-time human governance judgment — the
  capture-side pattern (the `proxy_mapping` MANUAL/PA-3 promotion precedent), **NOT a governed
  number**: it binds NO snapshot, NO run, NO model_version-as-methodology (the CLAUDE.md
  pattern-fence: captured inputs bind none of those). Recency semantics: the LATEST record per
  model_version (by `system_from`) is operative; no is-current flag, no supersede machinery.
  Core columns: `model_version_id` (hard FK, tenant re-resolved pre-stamp — the P3-5 guard —
  AND required to be a `status == "REGISTERED"` version: a non-REGISTERED version is already
  refused at every bind, so validating one is moot; the workflow scopes to bindable versions),
  `validation_type` ∈ {INITIAL, PERIODIC, TRIGGERED} (controlled-vocab string, no enum),
  `outcome` ∈ {APPROVED, APPROVED_WITH_CONDITIONS, REJECTED} (the OSFI E-23 vocabulary),
  `conditions` (required iff APPROVED_WITH_CONDITIONS — the PA-3 blur-guard, fail-closed both
  directions), `scope_summary` (required — SR 11-7 p.21: reports "articulate model aspects that
  were reviewed"), `report_ref` (optional pointer to the full report), `next_review_due`
  (required for APPROVED/APPROVED_WITH_CONDITIONS AND refused for REJECTED — symmetric blur
  guard: a rejected version has no scheduled next review, its re-validation is TRIGGERED by
  remediation; the ongoing-monitoring hook, OD-D), `validated_by` + actor rails.
- **OD-VW-1-B — Enforcement semantics (the load-bearing call): a latest-outcome-REJECTED
  model_version REFUSES new runs, fail-closed, at the existing `assert_model_version_of` seam**
  (one shared function → every model-bound binder inherits the gate; new
  `RejectedModelVersionError` → 422). **UNVALIDATED continues to run** — the platform explicitly
  adopts SR 26-2's use-before-validation exception posture (limits: recorded; monitoring: BT-1 +
  drift verify; notification: every registrar's limitation row already says "UNVALIDATED —
  recorded, non-enforcing until the P7 validation workflow"). NO validation-before-first-use
  gate in v1 (it would instantly break all 12 families; the exception posture is the honest,
  citable alternative). APPROVED_WITH_CONDITIONS runs normally; its conditions are recorded
  evidence, not machine-enforced limits (v1 limitation, Part 3).
- **OD-VW-1-C — Evidence + findings, minimally**: `model_validation_evidence` rows cite what the
  validator examined — `evidence_type` ∈ {CALCULATION_RUN, DOCUMENT}; a CALCULATION_RUN row
  carries a hard FK to `calculation_run.run_id`, **re-resolved tenant-visible + COMPLETED before
  stamping** (the PA-3 `source_calculation_run_id` precedent) — this is how a BT-1 backtest run
  (Kupiec + Basel zone) becomes first-class outcomes-analysis evidence (the FRTB MAR32 pattern:
  quantitative evidence feeding approval status). `model_validation_finding` rows carry
  `finding_text` + optional `severity` ∈ {HIGH, MEDIUM, LOW} + optional `authored_by` (an
  unranked observation is a legitimate record). **No remediation lifecycle
  in v1** (no finding state machine — append-only capture; remediation tracking is a recorded
  limitation, Part 3).
- **OD-VW-1-D — The ongoing-monitoring leg + the folded staleness register item, split
  honestly**: (i) **generic, in VW-1**: `next_review_due` on every non-REJECTED validation +
  an `overdue` flag computed on the read surface (MG-13/14; SS1/23 P4.5's tier-driven cadence
  reduced to validator-declared cadence while tiering is unbuilt — OD-033 stays open); (ii)
  **the σ_e-specific estimate-age GATE at total-VaR bind time is NOT implemented here — it is
  reassigned as a named BT-2 ride-along** (BT-2 already opens the exact binder + evidence chain:
  total-series backtest over `VAR_PARAMETRIC_TOTAL`); VW-1 pays the register item's
  *governance-surface* half (a validation record on `risk.var.parametric_total` can now record
  the staleness concern as a finding + a conditions clause), BT-2 pays the *mechanical-gate*
  half. Recorded in Part 3 so the register item's disposition is auditable.
- **OD-VW-1-E — Permission + SoD: mint ONE code `model.validate` via the governed R-07 process**
  (the first `model.*` mint since P0.5). Grants: `risk_manager_2l` (ROLE-MV, the 2L independent
  validator) + `platform_admin`; **deliberately withheld from `risk_analyst_1l`** — the SOLE
  `model.inventory.register` holder (SOD-03: author ≠ validator, enforced at the ROLE level;
  the `bootstrap.py` comment confirms the 1L-register/2L-validate split was pre-designed at
  P1A-2) — **and from `data_steward`** (it holds NO `model.*` code today; granting a maker-tier
  role a 2L assurance verb would CREATE an SoD exposure, not resolve one). Reads reuse
  `model.inventory.view` (a validation record is inventory metadata; the P3-8 no-new-view-code
  precedent). MG-04 data-level dev≠validator enforcement is a recorded limitation (the registry
  does not stamp per-version developer identity today).
- **OD-VW-1-F — Human-only v1 (MG-07/BR-15 fail-safe)**: `record_validation` refuses
  `actor_type != "user"` — while NO model carries a tier (all `tier` columns NULL), every model
  is potentially Tier-1, and BR-15/MG-07 forbid AI as sole approver for Tier-1; the fail-safe
  posture is human-only validation until tiering (REQ-MDG-002) ships. Audit: activate the
  RESERVED **`MODEL.VALIDATE`** code (caller-side constant; `audit/service.py` FROZEN,
  untouched; one event per validation record with outcome + finding/evidence counts in
  `after_value`, the MODEL.VERSION grain precedent). `.APPROVE`/`.RESTRICT`/`.RETIRE` stay
  reserved (v1 has no separate approval step: the validation record with outcome IS the
  Tier-2/3-grade act; the Tier-1 H-02 approval layer rides tiering, Part 3).
  - **MG-1 note (2026-07-15, additive):** tiering SHIPPED (OD-MG-1-A/B) — tiers now EXIST, so
    this OD's original justification ("while NO model carries a tier, every model is potentially
    Tier-1") is RESTATED, not relaxed: **Tier-1 models exist and validation remains human-only
    pending the H-02 approval workflow** (BR-15/MG-07). The human-only guard itself is UNCHANGED
    — do not relax it.
- **OD-VW-1-G — API surface (no FE in v1)**:
  `POST /models/{model_id}/versions/{version_id}/validations` gated `model.validate`;
  `GET .../validations` gated `model.inventory.view`; `GET /models/{model_id}` detail grows a
  per-version `latest_validation {outcome, validated_at, next_review_due, overdue}` block.
  Registry siblings' conventions hold: no lineage edge (model-registry writes are
  audit-tracked, not lineage-tracked — consistent with `MODEL.REGISTER`/`MODEL.VERSION`), no DQ
  rule (binder-side vocab/blur/actor guards are the refusal layer), indistinguishable 404 on
  cross-tenant reads.
- **OD-VW-1-H — Registry-doc obligations (no mints, three advances)**: ENT-037 catalog row →
  "REALIZED-IN-VW-1"; RTM REQ-MDG-003 Draft → In-Progress (REQ-MDG-002 tiering stays Draft);
  control matrix CTRL-022 Planned → Operational (evidence = ENT-037 rows, exactly as its row
  already states); audit-taxonomy MODEL row annotated "`.VALIDATE` activated in VW-1" (the
  taxonomy row IS the activation record, P3-2 precedent); `entitlement_sod_model.md` mint
  record for `model.validate`; `model_governance_independence_policy.md` cross-note (MG-04/07
  enforcement state + OD-033 still open). `model.validation_status` (the EV-head placeholder
  column) is **deprecated-in-place**: ENT-037 becomes the source of truth at version grain; the
  head column is neither written nor read by VW-1 (a projection would be model-grain-ambiguous
  across versions; noted in the column comment).

## Part 2 — External benchmark research (roadmap Part 4 rule 6; sources checked 2026-07-14)

**Citation-currency note (material):** SR 11-7 / OCC 2011-12 was **superseded 2026-04-17** by the
interagency *Revised Guidance on Model Risk Management* (Fed **SR 26-2** / OCC Bulletin
**2026-13**, which also rescinds the 2021 Comptroller's Handbook MRM booklet). The house label
"P7 / SR 11-7 workflow" is retained as shorthand; this record cites SR 11-7 as the structural
template (it remains the more prescriptive text on validation mechanics) AND SR 26-2 as the
current supervisory statement.

- **SR 11-7 / OCC 2011-12** (Fed/OCC 2011), "Supervisory Guidance on Model Risk Management" —
  the three validation elements (conceptual soundness incl. developmental evidence; ongoing
  monitoring incl. process verification + benchmarking; outcomes analysis incl. back-testing,
  §V p.11); validation before first use + **at-least-annual periodic review** + material-change
  trigger (p.10); significant deficiencies → use "not … allowed or … permitted only under very
  tight constraints", severe → "the model should be rejected" (p.10/15); inventory field list
  incl. restrictions, validation dates, expected-validity timeframe (p.20); validation-report
  contents (p.21). ADOPTED: the record schema (scope/findings/outcome/next-due), the
  REJECTED-blocks-use gate, evidence citation. DEVIATION (recorded): no
  validation-before-first-use gate in v1 — see SR 26-2 below.
- **SR 26-2 / OCC 2026-13** (Fed/OCC/FDIC, 2026-04-17), "Revised Guidance on Model Risk
  Management" — retains the three-component anatomy; **explicitly provides the
  use-before-validation exception path** (limits on use + closer monitoring + stakeholder
  notification); softens independence to "rigor and effectiveness of the review rather than …
  organizational structure". ADOPTED: the v1 UNVALIDATED-keeps-running posture is this
  exception path, documented; role-level (not org-level) independence is the cited basis for
  OD-E's permission-split SoD.
  - **MG-1 note (2026-07-15, additive):** the Wave-5 close's **F3** finding — this citation's
    blanket UNVALIDATED-keeps-running posture stretched SR 26-2's *per-model* exception into a
    tenant-wide default — is **FIXED at MG-1**: the exception path is now per-model + TIME-BOXED
    (`validation_type="EXCEPTION"`, AWC-only, expiry on `next_review_due`; an EXPIRED exception
    refuses new binds — OD-MG-1-E/F). The blanket text above is SUPERSEDED: outside the demo
    tenant the blanket default survives only as a DISCLOSED, proportionality-anchored POC
    posture (MG-1 record Part 3 item 2; policy doc §5A).
- **PRA SS1/23** (Bank of England, 2023; in force 2024), "Model risk management principles for
  banks" — P1.3 tiering drives revalidation cadence, tier reassessed at each validation; P4.5
  periodic revalidation decides whether "previous validation findings remain valid, should be
  updated, or … repeated"; P5.2 restrictions tracked in the inventory. ADOPTED:
  `next_review_due` plus the TRIGGERED/PERIODIC/INITIAL type vocabulary. DEFERRED: tier-driven
  cadence (tiering =
  REQ-MDG-002, unbuilt; cadence is validator-declared in v1, OD-033 open).
- **ECB Guide to Internal Models** (release 4.1, 2026) — para. 18: initial + **annual** internal
  validation, "initial" re-triggered by material change/extension; paras. 19-24 grade three
  acceptable independence arrangements (proportionality argument for role-separation on a small
  platform). ADOPTED: the TRIGGERED validation type; role-separation independence.
- **BCBS d457 / FRTB** (2019), MAR30/32 — internal-model use is a revocable permission
  conditioned on continuous quantitative performance (backtesting zones, PLA; red zone →
  automatic demotion). ADOPTED as the design precedent for OD-C: BT-1 backtest runs cited as
  first-class evidence rows feeding an approval outcome. (The platform's BT-1 zones descend
  from **BCBS 22** (1996), cited as lineage.)
- **OSFI Guideline E-23** (Canada, 2025, effective 2027) — "the model may be approved despite
  identified weaknesses or limitations provided that compensating mitigants are in place".
  ADOPTED: the APPROVED_WITH_CONDITIONS outcome + conditions-required blur guard.
- **OCC Comptroller's Handbook, MRM v1.0** (2021; rescinded 2026) — the richest public
  field-level enumeration of validation-record contents (status vocab, issue status,
  restrictions, planned-validation dates). Used as the schema checklist, labeled rescinded.
- **Derman (1996)**, "Model Risk", Goldman Sachs QSRN — the failure-mode taxonomy; grounds why
  findings are free-text + severity (the *kind* of failure is the validator's judgment) rather
  than a fixed defect enum. **GARP Risk Intelligence (2022)** whitepaper — secondary/industry
  corroboration of severity-graded findings + final rating as the record shape.
- **UNVERIFIED (named, not relied on):** McKinsey "Evolution of MRM" (2017; fetch failed);
  Commission Delegated Regulation (EU) 529/2014 (not fetched; EU model-change materiality
  taxonomy — known context only).

## Part 3 — Limitations carried forward + out of scope (recorded)

1. **No validation-before-first-use gate**: all 14 model codes keep running at UNVALIDATED —
   the documented SR 26-2 exception posture. Trigger to revisit: the first real validation
   campaign, or tiering (REQ-MDG-002).
2. **No tiering / no tier-driven cadence** (REQ-MDG-002 stays Draft; OD-033 cadence policy
   stays open in `model_governance_independence_policy.md`). `next_review_due` is
   validator-declared.
3. **No Tier-1 human-approval layer** (BR-15/MG-07): v1's fail-safe substitute is the
   human-only actor guard (OD-F). The H-02 approval step + `.APPROVE` activation ride tiering.
4. **No data-level dev≠validator check** (MG-04): the registry does not stamp per-version
   developer identity; SoD is role-level (OD-E). Trigger: registry owner/developer stamping.
5. **No remediation lifecycle on findings** (no state machine; append-only capture). Trigger:
   first validation campaign producing OPEN findings that need tracked closure.
6. **Conditions are recorded, not machine-enforced** (APPROVED_WITH_CONDITIONS does not
   restrict run parameters). Trigger: a real conditions clause that is mechanically checkable.
7. **The σ_e estimate-age gate → BT-2 ride-along** (OD-D): the register item's mechanical half
   is paid there; if BT-2's ratification declines it, the item returns to the register intact.
8. **No FE surface** (model inventory has no frontend view at all today; a validation view is a
   future FE slice candidate).
9. **`model.validation_status` head column deprecated-in-place** (neither written nor read;
   ENT-037 is version-grain truth).

## Part 4 — Open questions for ratification (OQ-VW-1-1…7)

- **OQ-VW-1-1 — OD-A: realize ENT-037 as an IA capture-side record at model_version grain**
  with outcome vocab {APPROVED, APPROVED_WITH_CONDITIONS, REJECTED} + type vocab {INITIAL,
  PERIODIC, TRIGGERED}; validation records only attach to `status="REGISTERED"` versions (a
  non-REGISTERED version is already refused at every bind — validating it is moot).
  *Recommend APPROVE — the reserved catalog row says exactly this ("Validation status, tier,
  approval"); version grain matches SR 11-7's inventory prescription; the capture-vs-governed
  split is the platform's own hard invariant.*
- **OQ-VW-1-2 — OD-B: latest-REJECTED blocks NEW runs fail-closed at `assert_model_version_of`;
  UNVALIDATED keeps running (documented SR 26-2 exception posture); no
  validation-before-first-use gate in v1.** *Recommend APPROVE — this is the smallest gate that
  makes validation REAL (a REJECTED verdict has teeth, SR 11-7 p.10/15) without breaking all 12
  families on day one; the exception posture is honest and citable.*
- **OQ-VW-1-3 — OD-E: mint ONE permission `model.validate` (R-07), granted `risk_manager_2l` +
  `platform_admin`; withheld from `risk_analyst_1l` (the SOLE register-holder — SOD-03 at role
  level) and from `data_steward` (holds no `model.*` code; a maker-tier role should not gain a
  2L assurance verb); reads reuse `model.inventory.view`; activate `MODEL.VALIDATE` only.**
  *Recommend APPROVE — executes the pre-designed 1L-register/2L-validate split; one code, one
  event, both already reserved in the catalogs.*
- **OQ-VW-1-4 — OD-F: human-only validation in v1** (`actor_type="user"` required). *Recommend
  APPROVE — with tier unstamped every model is potentially Tier-1, and BR-15/MG-07 forbid
  AI-sole approval there; fail-safe until tiering ships.*
- **OQ-VW-1-5 — OD-D: the staleness fork.** (A) VW-1 delivers the generic ongoing-monitoring
  leg (`next_review_due` + overdue flag); the σ_e estimate-age GATE is reassigned as a named
  BT-2 ride-along. (B) VW-1 also implements the estimate-age refusal inside the total-VaR
  binder now. *Recommend (A) — BT-2 already opens exactly that binder and its evidence chain;
  mixing a binder-compute change into a workflow slice recreates the scope-blur the house
  discipline exists to prevent. The register item's disposition is recorded either way (Part 3
  item 7).*
- **OQ-VW-1-6 — OD-C: findings as append-only text+severity rows, evidence as
  {CALCULATION_RUN (hard FK, re-resolved), DOCUMENT} rows; no remediation lifecycle in v1.**
  *Recommend APPROVE — captures what SR 11-7 requires a report to contain without inventing a
  workflow engine before the first real validation exists.*
- **OQ-VW-1-7 — Scope fence: migration `0039` (3 IA tables, FORCE RLS, append-only triggers,
  ≤63-char identifiers asserted); NO new ENT/REQ mint (realizations/advances only, OD-H, incl.
  the deprecate-in-place of the `model.validation_status` head column — ENT-037 becomes the
  version-grain source of truth, the head column is neither written nor read); NO
  binder-compute change; `audit/service.py` FROZEN; proportionate 4-finder review with one
  adversarial finder on the OD-B gate change.** *Recommend APPROVE.*

## Part 5 — Implementation readiness gate

Implementation starts only after OQ-VW-1-1…7 ratification, per `vw_1_implementation_plan.md`
(the 8-step build contract). Validation battery: `make check` + full local-PG (schema-reset AND
dirty-schema double-run — the RD-3 standing capability) + `alembic check`/downgrade-base smoke +
CI-watch-to-green; the new PG suite added to `ci.yml` in the SAME commit (the PA-4 lesson).
Recommended implementation model/effort: **Opus 4.8 / High** (templated build — every step
mirrors a shipped exemplar; the adversarial review catches subtle gate bugs), 4-finder review
with one adversarial finder on the OD-B gate change.

## Part 5.5 — Implementation deviations from the ratified plan

- **Single-column-index choice (minor).** Plan Step 1 described a composite `(tenant_id,
  model_version_id, system_from)` latest-read index AND kept `index=True` on the FK column. The
  build dropped the redundant single-column FK index and kept ONLY the composite
  `ix_model_validation_latest` (it serves both the point query and the per-version listing under
  RLS's always-present tenant predicate). ORM + migration stay in sync (`alembic check` clean).
- Everything else was built as ratified: 3 IA tables (migration `0039`), the shared-seam REJECTED
  gate, 2 new + 1 extended endpoint, the `model.validate` R-07 mint, the doc advances. No
  migration beyond `0039`; `audit/service.py` untouched; no governed-number/binder-compute change.

## Part 6 — Review dispositions + closure

**Implemented** (branch `vw-1-impl`): the 8-step build; `make check` **1407 passed** + full
local-PG (schema-reset run, dirty-schema double-run, `alembic check` clean, downgrade-base/
upgrade-head smoke) all green.

**Review: 4 finders (1 adversarial on the OD-B gate, per OQ-VW-1-7).** Findings + dispositions:

1. **HIGH (finder 4) — the REJECTED gate returned a raw 500, not the promised 422, at every real
   family run endpoint.** `RejectedModelVersionError` was raised inside the shared
   `assert_model_version_of` seam but was absent from the risk/perf run-endpoint `except` tuples
   AND from their `_ERROR_MAP`s — so a REJECTED-version run driven through `risk.py`/`perf.py`
   produced an unhandled 500, making the slice's headline ("a REJECTED verdict refuses new runs")
   an overclaim relative to observable API behavior. The seam-only tests hid it. **FIXED**: added
   `RejectedModelVersionError` → 422 to both `_ERROR_MAP`s and all 12 run-endpoint `except` tuples
   (9 risk + 3 perf), and added END-TO-END tests driving a REJECTED version through a real risk
   endpoint (`test_var_endpoint`) AND a real perf endpoint (`test_perf_endpoint`) asserting 422 +
   no run persisted — the "one risk + one perf" integration proof the plan's Step 8 intended
   (which, done seam-only, had masked this defect).
2. **MEDIUM-safety/LOW-reachability (finder 1, adversarial) — the `latest_validation` recency read
   is DETERMINISTIC but not write-order-recency-correct**, and the docstring overstated the
   tiebreaker as a guarantee. Two validations of one version with an IDENTICAL `system_from`
   resolve by UUID order, not insertion order. Not reachable through the human-only, non-injected-
   clock production path (no same-microsecond tie); a coarse-granularity backfill could hit it, and
   no such path exists today, and there is no sequence column on these IA tables to order by
   instead. **FIXED as a documentation correction** (both `validation.latest_validation` and the
   `ix_model_validation_latest` comment now say the id leg guarantees DETERMINISM/stable-plan, NOT
   recency, and declare equal-timestamp validations of one version out of contract) + a new
   `test_latest_uses_system_from_not_id` that anti-correlates `system_from` with `id` to prove the
   `system_from` leg is load-bearing. The heavier fix (a monotonic sequence column) is not
   warranted at POC scope. Adversarial findings 2-7 (tenant scoping, exposure exemption,
   backtest-independence, dispatch error-class, index usage, bypass surface, REGISTERED coupling)
   all CONFIRMED SOUND.
3. **LOW (finder 2) — asymmetric evidence blur**: a `CALCULATION_RUN` evidence row silently
   persisted a stray `reference`, and a `DOCUMENT` row's stray `run_id` was dropped-not-refused.
   **FIXED**: the blur guard is now symmetric both ways (a CALCULATION_RUN row must NOT carry a
   reference; a DOCUMENT row must NOT carry a run_id) + two new unit tests.
4. **LOW (finder 3) — `overdue` used server-LOCAL `date.today()`** while the platform stamps UTC
   everywhere. **FIXED**: `datetime.now(UTC).date()` (a read-time display flag; avoids a
   near-midnight boundary flip on a non-UTC server).
5. **LOW (finder 4) — the OD-G no-DQ half of the emission test was unpinned** (only zero-lineage
   asserted). **FIXED**: added a zero-`DataQualityResult` assertion.
6. **LOW (finder 4) — the cross-model version-id 404 branch was untested.** **FIXED**: added
   `test_record_validation_cross_model_version_404`.

**Accepted-as-recorded (no code change):** the input-length guard gap (finder 2 F3 — an
over-2000-char `scope_summary` raises a DB `DataError` at flush rather than a pre-write 422) is
consistent with the existing registry precedent (`assumption_text`/`limitation_text` are likewise
unguarded); recorded as a family-wide convention, not a VW-1 regression. The findings/evidence
read order degenerates to UUID order within a record's shared `system_from` (finder 2 F2) — a
recorded limitation (no ordinal column; the API does not promise submission order); a future
touch adds an ordinal if the FE needs ordered rendering.

**Residual deferrals (trigger-based, from Part 3, unchanged):** no tiering/tier-cadence
(REQ-MDG-002; OD-033 open); no Tier-1 H-02 approval leg (`MODEL.APPROVE` reserved); no data-level
dev≠validator (MG-04, no per-version developer stamp); no remediation lifecycle; conditions
recorded-not-enforced; the σ_e estimate-age gate → BT-2 ride-along; no FE surface.

**VW-1 CLOSED** pending PR merge + CI green (commit hash recorded in delivery-roadmap-state memory
at close).
