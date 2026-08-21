"""Baseline entitlement bootstrap data (P0.5).

The global permission catalog and baseline role *templates* seeded by migration
``0002_entitlement_seed``. Kept here (not inline in the migration) so the catalog is
importable and unit-testable and there is one source of truth. Roles are templates under
the reserved system tenant (AD-013); tenant onboarding later clones them into tenant-scoped
roles. IDs are derived with ``uuid5`` so the seed migration is deterministic/reproducible.
"""

from __future__ import annotations

import uuid

#: Reserved system tenant for global/template entitlement data (AD-013).
SYSTEM_TENANT_ID = "00000000-0000-0000-0000-000000000001"

#: Deterministic namespace for seeded row IDs (no random UUIDs in migrations).
_NS = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

#: Global permission catalog: (code, description).
PERMISSIONS: list[tuple[str, str]] = [
    ("ops.audit.verify", "Run audit chain verification"),
    ("data.upload", "Upload/ingest data via the anti-corruption layer"),
    ("lineage.view", "View data lineage"),
    ("lineage.source.manage", "Register and manage data sources (lineage provenance roots)"),
    ("model.inventory.view", "View the model inventory"),
    ("model.inventory.register", "Register a model or model version"),
    # VW-1 (ENT-037, SR 11-7 / P7): the 2L independent-validation write verb — a governed R-07 mint
    # (the first model.* mint since P0.5). Granted to risk_manager_2l (ROLE-MV) + platform_admin
    # ONLY; deliberately WITHHELD from risk_analyst_1l — the SOLE model.inventory.register holder
    # (SOD-03: author ≠ validator) — and from data_steward (holds no model.* code; a maker-tier
    # role must not gain a 2L assurance verb). Reads reuse model.inventory.view (a validation record
    # is inventory metadata; the P3-8 no-new-view-code precedent).
    ("model.validate", "Record a model validation (2L independent, SR 11-7)"),
    ("dq.rule.manage", "Manage data quality rules"),
    ("dq.result.view", "View data quality results"),
    ("reference.instrument.view", "View instruments"),
    ("reference.instrument.edit", "Edit instruments"),
    ("reference.issuer.view", "View issuers"),
    ("reference.issuer.edit", "Edit issuers"),
    ("reference.counterparty.view", "View counterparties"),
    ("reference.counterparty.edit", "Edit counterparties"),
    ("reference.identifier.resolve", "Resolve instrument identifiers"),
    ("reference.corporate_action.edit", "Edit corporate actions"),
    ("reference.calendar.edit", "Edit calendars"),
    # P1B-1 reference-data vocabularies (additive; AD-013-R1 hybrid set). reference.rating.* is
    # RESERVED for the future FR rating-ASSIGNMENT domain and is deliberately NOT minted here.
    ("reference.currency.view", "View currencies"),
    ("reference.currency.edit", "Edit currencies"),
    ("reference.rating_scale.view", "View rating scales"),
    ("reference.rating_scale.edit", "Edit rating scales"),
    ("reference.calendar.view", "View calendars"),
    # P1B-2 legal_entity core (additive; PROPRIETARY tenant-scoped). issuer/counterparty perms
    # exist above. reference.rating.* stays RESERVED. legal_entity.view granted to EXACTLY
    # the issuer/counterparty.view recipient set (proprietary-identity SoD — EXCLUDES auditor_3l).
    ("reference.legal_entity.view", "View legal entities"),
    ("reference.legal_entity.edit", "Edit legal entities"),
    # P1B-3 instrument identifiers (additive; PROPRIETARY tenant-scoped). reference.instrument.view/
    # edit and reference.identifier.resolve already exist above — only .view/.edit are NEW. The
    # existing .resolve recipient set is UNCHANGED (NOT widened to risk_manager_2l). rating.* stays
    # RESERVED. .view granted to the reference.instrument.view set; auditor_3l EXCLUDED (SoD).
    ("reference.identifier.view", "View instrument identifiers"),
    ("reference.identifier.edit", "Edit instrument identifiers"),
    # P1B-4 corporate_action (additive; PROPRIETARY tenant-scoped). reference.corporate_action.edit
    # already exists above — only .view is NEW. .view granted to the reference.instrument.view set;
    # auditor_3l EXCLUDED (proprietary security-master SoD). reference.rating.* stays RESERVED.
    ("reference.corporate_action.view", "View corporate actions"),
    # REF-1 classification (Wave-14 slice 0). THREE codes, split by TENANCY CLASS — the
    # verifier pass caught a single `.view` here as a BLOCKING SoD defect: it would have gated the
    # hybrid SYSTEM-global vocabulary AND the proprietary issuer-attached assignments with one
    # permission, and granting it to auditor_3l (which the demo does) would have handed the 3L
    # auditor its first proprietary-identity read. No shipped test would have caught that, because
    # the SoD pins are PER CODE. reference.rating.* stays RESERVED.
    #   .view          -> the hybrid vocabulary; auditor-INCLUDED (the currency/rating_scale set).
    #   _assignment.view -> the proprietary assignments; auditor-EXCLUDED (the legal_entity set).
    #   .edit          -> the steward maker verb over both.
    ("reference.classification.view", "View classification schemes and nodes"),
    ("reference.classification_assignment.view", "View classification assignments"),
    ("reference.classification.edit", "Edit classification schemes, nodes and assignments"),
    ("portfolio.view", "View portfolios"),
    ("portfolio.edit", "Edit portfolios"),
    ("position.view", "View positions"),
    # P1C-3 position (FR captured holdings). `position.view` pre-exists as a seeded placeholder
    # (granted to the read tiers + admin); `position.edit` is the NEW maker verb minted here (a
    # position is captured/superseded/corrected — `.edit`, not `.record`; FR is close-out-updated).
    ("position.edit", "Edit positions"),
    # P2-3 exposure (ENT-014, the first governed derived number). `exposure.aggregate.run`
    # pre-exists as a seeded reserved-unwired code; P2-3 WIRES it + mints `exposure.view`.
    # `.aggregate.run` is the run-the-governed-compute verb (a derived number is *run*, not
    # edited/recorded). `auditor_3l` is INCLUDED in `.view` (the FIRST domain perm to grant the 3L
    # auditor a read — a governed OUTPUT is 3L-oversight scope, the dq.result.view/lineage.view
    # precedent; OD-P2-3-I/OQ-P2-3-2).
    ("exposure.aggregate.run", "Run exposure aggregation"),
    ("exposure.view", "View exposure aggregates"),
    # P3-1 risk (ENT-028 sensitivity_result, the first reproducible governed RISK number). BOTH
    # codes are NEW. `risk.run` is the run-the-governed-compute verb (a risk number is *run*, not
    # edited/recorded; mirrors `exposure.aggregate.run`); `risk.view` reads results. `auditor_3l` is
    # INCLUDED in `risk.view` (governed risk OUTPUT is 3L-oversight scope — the exposure.view
    # precedent; OD-P3-1-I). Both maker/read sets mirror the exposure family.
    ("risk.run", "Run governed risk analytics (analytic sensitivities)"),
    ("risk.view", "View risk results (sensitivities)"),
    # PM-1 perf (ENT-053 portfolio_return_result, the FIRST non-risk governed number). BOTH codes
    # are NEW — a PERFORMANCE number is NOT a risk number, so it gets its OWN verb pair, never
    # risk.run/risk.view (OD-PM-1-A: a governed R-07 mint). `perf.run` is the run-the-governed
    # compute verb (a return is *run*, not edited/recorded; mirrors risk.run/exposure run);
    # `perf.view` reads results. `auditor_3l` is INCLUDED in `perf.view` (a governed performance
    # OUTPUT is 3L-oversight scope — the risk.view precedent). Maker/read sets mirror the risk fam.
    ("perf.run", "Run governed performance analytics (portfolio returns)"),
    ("perf.view", "View performance results (portfolio returns)"),
    # P1C-2 transaction (additive; PROPRIETARY tenant-scoped, IA append-only). `.record` is the
    # append-only governed-write verb (a transaction is recorded, never edited — no `.edit`).
    ("transaction.view", "View transactions"),
    ("transaction.record", "Record transactions"),
    # P1C-4 valuation (FR captured marks). BOTH codes are NEW (neither pre-exists in the catalog,
    # unlike position.view). `.edit` is the FR maker verb (a mark is captured/superseded/corrected —
    # `.edit`, not `.record`; FR is close-out-updated). auditor_3l excluded from both.
    ("valuation.view", "View valuations"),
    ("valuation.edit", "Edit valuations"),
    # P2-1 dataset_snapshot (ENT-049/050, the AD-014 reproducible input snapshot). BOTH codes are
    # NEW. `.create` (NOT `.record`) is the deliberate verb — a snapshot is a create-once run
    # artifact (like calculation_run is created/initiated), not a recorded business event. `.create`
    # is maker/admin-only (data_steward + platform_admin); the read tiers hold `.view`; auditor_3l
    # excluded from both (operational reproducibility-input SoD).
    ("snapshot.view", "View dataset snapshots"),
    ("snapshot.create", "Create dataset snapshots (reproducible input snapshots)"),
    # P2-2 market data (ENT-024 fx_rate first; price/curve/benchmark join additively). BOTH codes
    # NEW + REUSABLE across all market data (NOT per-entity fx_rate.*). `.ingest` is the governed
    # canonical-write verb (capture/supersede/correct) — distinct from `data.upload` (raw staging).
    # `.ingest` is maker/admin-only (data_steward + platform_admin); the read tiers hold `.view`;
    # auditor_3l excluded from both (vendor-license isolation is by tenant-scoped RLS, not a role).
    ("marketdata.view", "View market data (FX rates, prices, curves)"),
    ("marketdata.ingest", "Capture/correct governed market data (FX rates, prices, curves)"),
    # CC-1 private capital (ENT-015 commitment FR + ENT-016 capital_call/distribution IA) —
    # a governed R-07 mint (OD-CC-1-B, ratified 2026-07-20). THREE codes because the family spans
    # BOTH temporal classes and the verb shape is doctrine: `.edit` is the FR maker (a commitment
    # is captured/superseded/corrected — the position/valuation precedent), `.record` is the IA
    # maker (a call/distribution is recorded, never edited — the transaction precedent; reversals
    # are themselves appended records). ONE `.view` reads all three tables. Both makers are
    # maker/admin-only (data_steward + platform_admin — identical holder sets, so the third code
    # adds no SoD surface); auditor_3l is EXCLUDED from all three (captured-INPUT read scope — the
    # marketdata/valuation precedent; governed OUTPUTS are where the 3L auditor reads).
    ("commitment.view", "View commitments, capital calls and distributions"),
    ("commitment.edit", "Capture/supersede/correct commitments (FR maker)"),
    ("commitment.record", "Record capital calls and distributions (IA maker, incl. reversals)"),
    # CC-2 pacing (ENT-059 pacing_projection_result, the SEVENTEENTH governed number) —
    # a governed R-07 mint (OD-CC-2-E, ratified 2026-07-20). BOTH codes NEW — a commitment-pacing
    # PROJECTION is neither a risk nor a performance number, and the capture verbs `commitment.*`
    # gate the captured INPUT surface (auditor_3l EXCLUDED); a governed OUTPUT read must INCLUDE
    # auditor_3l — so reusing `commitment.view` would break one rule or the other. The PM-1
    # "own domain, own pair" precedent applies verbatim. `pacing.run` is the run-the-governed
    # compute verb (a projection is *run*; mirrors risk.run/perf.run); `pacing.view` reads results.
    # `auditor_3l` is INCLUDED in `pacing.view` (a governed OUTPUT is 3L-oversight scope — the
    # perf.view precedent). Maker/read sets mirror the perf family.
    ("pacing.run", "Run governed commitment-pacing projections"),
    ("pacing.view", "View commitment-pacing projection results"),
    # CON-1 (OQ-CON-1-25, the v6 THREE-code split by WHAT THE READ EXPOSES): `.view` carries the
    # summary metrics + sector/country buckets (no issuer identity anywhere in the payload) and is
    # 3L-oversight scope (the pacing.view governed-output precedent); `.issuer.view` carries the
    # ISSUER-dimension detail reads and any payload with issuer_id/name — auditor_3l is EXCLUDED,
    # consistent with reference.issuer.view/legal_entity.view/classification_assignment.view (the
    # three prior issuer-identity refusals). One combined code would hand the 3L auditor exactly
    # the proprietary-identity read those mints refused — and the per-code SoD pins would PASS.
    ("concentration.run", "Run governed dimensional-concentration calculations"),
    ("concentration.view", "View concentration results (no issuer identity)"),
    ("concentration.issuer.view", "View ISSUER-dimension concentration detail (issuer identity)"),
    # LQ-1 (ratified OQ-LQ-1-13) — a governed R-07 mint. TWO codes, and deliberately NOT three:
    # nothing in the liquidity payload carries a proprietary identity, so there is no narrower
    # read to split off. auditor_3l HOLDS liquidity.view because it is a governed OUTPUT (the
    # concentration.view placement); the CAPTURED tier assignments are read through
    # reference.classification_assignment.view, which EXCLUDES auditor_3l. The two sit on opposite
    # sides of the auditor line, which is why one combined code was refused — SoD pins are
    # per-code, so a route on the wrong guard would pass every shipped test (REF-1's BLOCKING).
    # Forward-gate (close-review L9, folded): `liquidity.run` has NO route today — LQ-1's Part 3
    # names four READS and no write endpoint. The code is Tier-3 ratified and stays minted; when a
    # run endpoint lands it MUST carry require_permission("liquidity.run") (the schedule.manage /
    # limit.manage pattern above). The dead guard singleton that used to sit in `api/liquidity.py`
    # was REMOVED rather than kept as a placeholder — an unused bound guard reads as protection.
    ("liquidity.run", "Run governed liquidity-tier calculations"),
    ("liquidity.view", "View liquidity tier distribution results"),
    # SCH-1 scheduling (ENT-061 schedule / ENT-062 scheduled_run, Wave-11 slice 1) — a governed
    # R-07 mint (OD-SCH-1-G, ratified 2026-07-23). BOTH codes NEW — a schedule is a control-plane
    # config object that DRIVES governed-number production; neither a risk nor a performance verb
    # gates it. `schedule.manage` is the maker verb (create/edit/pause a schedule — mirrors
    # pacing.run/risk.run); `schedule.view` reads schedules + the scheduled_run ledger. `.manage`
    # goes to the 1L risk maker + the data_steward ops maker (the pacing.run placement); `.view`
    # goes broadly INCLUDING auditor_3l — a governed control-plane object is 3L-oversight scope
    # (the pacing.view precedent). Dispatch itself runs as a synthesized SYSTEM actor, ungated.
    # Forward-gate DISCHARGED at REPRO-2 (2026-08-10): the schedule API landed
    # (`api/schedule_admin.py` — POST /schedules, /{id}/pause, /{id}/resume) and it carries
    # require_permission("schedule.manage"), so the census entry was deleted. The maker-checker
    # question SCH-2 reserved was answered at the same gate: create/resume are not four-eyes acts
    # (they only ADD detection), and PAUSE stays one-person with compensating VISIBILITY — a
    # tenant whose reproduction schedules are all paused reads RED on the alarm-health surface.
    # The original forward-gate wording, kept because its reason still binds every future route:
    # nothing below the API layer enforces the maker verb (consistent with the perf/pacing
    # service-ungated design).
    ("schedule.manage", "Create, edit and pause governed run schedules"),
    ("schedule.view", "View run schedules and the scheduled-run ledger"),
    # LIM-1 limits/breach (ENT-031 limit_definition / ENT-033 breach, Wave-11 slice 2) — a governed
    # R-07 mint (OD-LIM-1-J, ratified 2026-07-23) ACTIVATING the genesis-reserved LIMIT/BREACH
    # decades. THE SoD TWIST vs SCH-1: `limit.manage` is a 2L RISK-MANAGER function (personas: limit
    # maker = P-RM 2L; BX-SOD lists limits as maker-checked) — it goes to risk_manager_2l (+ admin),
    # NOT the 1L analyst who runs the numbers (author != limit-setter, the VW-1 model.validate
    # precedent). `limit.view` + `breach.view` go broadly INCLUDING auditor_3l (a governed
    # control-plane object is 3L-oversight scope, the pacing.view/schedule.view precedent). Breach
    # detection runs as a synthesized SYSTEM actor on the operational tick, ungated. Forward-gate:
    # a future limit API endpoint MUST carry require_permission("limit.manage"). The formal
    # MG-3 ACTIVATES the reserved LIMIT.APPROVE maker-checker gate (OQ-MG-2-1=B, ratified
    # 2026-07-24, OQ-MG-3-2=A): `limit.approve` goes to the SAME risk_manager_2l as the maker verb
    # `limit.manage`, because the gate is PERSON-level, not role-level — a limit is born DRAFT and a
    # SECOND 2L person (approver != the draft's maker, by principal id) approves it into ACTIVE
    # (personas: limit-change checker = "P-CRO / second 2L"; SOD-02). Unlike breach.respond/review
    # (a cross-line 1L/2L partition, never co-granted), maker and checker here are the SAME role,
    # so the runtime approver != created_by/updated_by refusal is the WHOLE gate. A material change
    # to a LIVE limit re-enters the gate (auto-demote to DRAFT). Forward-gate: a future limit API
    # endpoint MUST carry require_permission("limit.approve") on approve_limit.
    ("limit.manage", "Define, edit and suspend governed risk limits (2L)"),
    ("limit.approve", "Approve a DRAFT limit into ACTIVE — maker-checker sign-off (2L)"),
    ("limit.view", "View risk limit definitions"),
    ("breach.view", "View limit breach records"),
    # MG-2 breach remediation lifecycle (ENT-034 breach_action, Wave-11 slice 3) — a governed R-07
    # mint splitting the three-lines-of-defense breach workflow: `breach.respond` is the 1L verb
    # (the analyst who runs the numbers owns and remediates the breach), `breach.review` is the 2L
    # verb (assign an owner, review the 1L response, escalate, close). These two are NEVER
    # co-granted to a non-admin role (the SOD-03 register/validate partition precedent) — the role
    # partition is the FIRST line of the maker-checker SoD; the runtime person-level refusal
    # (reviewer/closer != any prior 1L responder, SOD-02) is the backstop for the platform_admin
    # dual-hat. A future breach-action API endpoint MUST carry the matching require_permission.
    ("breach.respond", "File a 1L remediation response on a breach (1L)"),
    ("breach.review", "Assign, review, escalate and close a breach (2L)"),
    # W19-S3b (INGEST-1, REQ-INT-001 clause 6): the mapping governance mint, splitting the
    # maker and the checker of a source mapping across ROLES rather than only across persons.
    #
    # The precedent is `breach.respond`/`breach.review` — a CROSS-LINE partition — and NOT
    # `limit.manage`/`limit.approve`, which deliberately share a role because that gate is
    # person-level. The two shapes look alike and enforce opposite things; the wave plan requires
    # the ratifier code to be "never co-granted with the proposer path", so the partition is the
    # one that applies.
    #
    # `ingest.mapping.view` is the third code and exists for a reason found at recon: every
    # `/ingest` read was gated on the MAKER's `data.upload`, so a ratifier-only holder would have
    # got 403 on the very screens showing what they were about to approve. A checker who cannot
    # read the artifact is not a checker (DS3b-2).
    ("ingest.mapping.propose", "Propose a source mapping version for ratification (maker)"),
    ("ingest.mapping.ratify", "Ratify or supersede a source mapping version (checker)"),
    ("ingest.mapping.view", "Read source mapping versions and their ratification history"),
    # RPT-2 (Wave-16) — a governed R-07 mint. TWO codes, split by
    # **RATIFICATION STATUS, corrected at the pre-merge audit: the Wave-16 gate (OQ-W16P-1..7)
    # asked NO permission question and enumerated NO holder set.** An earlier version of this
    # comment cited it as ratifying these holders; it does not. The split below is the BUILDER's
    # application of the standing doctrine (governed-output reads include auditor_3l; write verbs
    # exclude it) — defensible, consistent with every prior mint, and NOT user-ratified. The
    # holder sets are carried to the Wave-16 close as an explicit Tier-3 item; every prior mint
    # (OQ-CON-1-25, OQ-LQ-1-13) had its sets enumerated to the user, and this one must too.
    # The split is by
    # VERB CLASS on the auditor line: `report.view` gates a governed OUTPUT artifact — the rendered
    # report IS the governed numbers, with provenance — so auditor_3l HOLDS it (the exposure.view →
    # ... → liquidity.view chain, unbroken). `report.generate` is a WRITE verb (it mints a REPORT
    # calculation_run, a REPORT_INPUT snapshot and an IA ENT-072 row), so auditor_3l does NOT — 3L
    # observes evidence, it never creates it (the snapshot.create / *.run exclusion class).
    # Holders for .generate mirror liquidity.run/concentration.run: the 1L maker + the data_steward
    # ops maker (+ admin). NOT 2L: generating a report is running the numbers, not approving them.
    # SOD-08 ("Generate a report | Approve/publish a board report") stays HALF-RESERVED: generate is
    # minted HERE; approve/publish is NOT minted — no publish verb ships in RPT-2, and minting the
    # checker half without its workflow would be a dead guard (the liquidity.run forward-gate
    # lesson, inverted). ROLE-RC "Report Consumer" (entitlement_sod_model.md §4) is NOT minted as a
    # template role — a role is under the same R-07 freeze as a code, and no ratification names it.
    ("report.generate", "Generate a governed report (mints a run + snapshot + ENT-072 row)"),
    # ONBOARD-1b: the tenant-local administration verbs, filling the `tenant_admin` template 1a
    # minted EMPTY. Holders: tenant_admin + platform_admin only.
    #
    # `user.view` deliberately EXCLUDES auditor_3l, and the exclusion is a decision with a reason:
    # an entitlement roster carries `external_subject` (the OIDC subject) and `display_name` —
    # person-identifying data, the class every proprietary-identity read has withheld from the 3L
    # auditor (reference.issuer/legal_entity/classification_assignment.view). The schedule.view
    # precedent does NOT apply: a schedule row carries no identity. A redacted auditor roster is
    # deliberately NOT minted (the SOD-08 half-mint precedent) — its trigger is a real 3L
    # access-review requirement.
    #
    # `role.approve` is the CHECKER half of SOD-04's four-eyes, and it is held by the SAME role as
    # the maker verbs — the MG-3 pattern verbatim: the gate is PERSON-level (approver != requester
    # by principal id), not role-level, because a tenant's admins are peers. A role-level split
    # would need two admin roles and would still not stop one person holding both.
    ("user.manage", "Create and deactivate users within a tenant"),
    ("role.assign", "Grant and revoke roles within a tenant"),
    ("user.view", "View users and their role assignments"),
    ("role.approve", "Approve another admin's entitlement change — four-eyes (SOD-04)"),
    ("report.view", "View governed reports: metadata, listings and the rendered artifact"),
]

#: All permission codes, in catalog order.
ALL_CODES: list[str] = [code for code, _ in PERMISSIONS]

#: Baseline role templates: template code -> granted permission codes.
ROLE_TEMPLATES: dict[str, list[str]] = {
    "platform_admin": list(ALL_CODES),
    "ops": ["ops.audit.verify"],
    "data_steward": [
        "data.upload",
        "lineage.view",
        "lineage.source.manage",
        "dq.rule.manage",
        "dq.result.view",
        "reference.instrument.view",
        "reference.instrument.edit",
        "reference.issuer.view",
        "reference.issuer.edit",
        "reference.counterparty.view",
        "reference.counterparty.edit",
        "reference.identifier.resolve",
        "reference.corporate_action.edit",
        "reference.calendar.edit",
        # P1B-1 reference vocabularies: steward holds view + edit (the reference maker).
        "reference.currency.view",
        "reference.currency.edit",
        "reference.classification.edit",
        "reference.rating_scale.view",
        "reference.rating_scale.edit",
        "reference.calendar.view",
        # P1B-2 legal_entity: steward holds view + edit (the maker).
        "reference.legal_entity.view",
        "reference.legal_entity.edit",
        # P1B-3 instrument identifiers: steward holds view + edit (the maker).
        # reference.instrument.* + reference.identifier.resolve already granted above.
        "reference.identifier.view",
        "reference.identifier.edit",
        # P1B-4 corporate_action: steward holds view (.edit already granted above).
        "reference.corporate_action.view",
        "reference.classification.view",
        "reference.classification_assignment.view",
        # P1C-1 portfolio: steward is the maker — holds BOTH view + edit (so it can read its own
        # writes). The codes pre-exist in the catalog (placeholders); this is the additive GRANT
        # (OD-P1C1-3). risk_analyst_1l/risk_manager_2l already hold portfolio.view (below);
        # portfolio.edit is maker/admin-only (data_steward + platform_admin); auditor_3l excluded.
        "portfolio.view",
        "portfolio.edit",
        # P1C-2 transaction: steward is the maker/recorder — holds BOTH view + record (reads its own
        # writes). transaction.record is maker/admin-only (data_steward + platform_admin);
        # risk_analyst_1l/risk_manager_2l hold transaction.view (below); auditor_3l excluded.
        "transaction.view",
        "transaction.record",
        # P1C-3 position: steward is the maker — holds BOTH view + edit (reads its own writes).
        # position.view pre-exists (granted to the read tiers below); this is the additive steward
        # GRANT + the NEW position.edit (maker/admin-only); auditor_3l excluded (OD-P1C3-2).
        "position.view",
        "position.edit",
        # P1C-4 valuation: steward is the maker — holds BOTH view + edit (reads its own writes).
        # BOTH codes are NEW; risk_analyst_1l/risk_manager_2l hold valuation.view (below);
        # valuation.edit is maker/admin-only; auditor_3l excluded (OD-P1C4-2).
        "valuation.view",
        "valuation.edit",
        # P2-1 dataset_snapshot: steward is the maker — holds BOTH view + create (reads its own
        # writes). risk_analyst_1l/risk_manager_2l hold snapshot.view (below); snapshot.create is
        # maker/admin-only; auditor_3l excluded.
        "snapshot.view",
        "snapshot.create",
        # W19-S3b: the steward PROPOSES a mapping and READS it, and never ratifies — the maker
        # side of the INGEST-1 partition.
        "ingest.mapping.propose",
        "ingest.mapping.view",
        # P2-2 market data: steward is the maker — holds BOTH view + ingest (reads its own writes).
        # risk_analyst_1l/risk_manager_2l hold marketdata.view (below); marketdata.ingest is
        # maker/admin-only; auditor_3l excluded.
        "marketdata.view",
        "marketdata.ingest",
        # P2-3 exposure: steward is a maker — holds run + view (reads its own writes).
        "exposure.aggregate.run",
        "exposure.view",
        # P3-1 risk: steward is a maker — holds run + view (the exposure precedent).
        "risk.run",
        "risk.view",
        # PM-1 perf: steward is a maker — holds run + view (the risk precedent).
        "perf.run",
        "perf.view",
        # CC-1 private capital: steward is the maker on BOTH temporal classes — holds edit
        # (FR commitment ops) + record (IA call/distribution capture) + view (reads its own
        # writes). Both maker verbs are maker/admin-only; auditor_3l excluded from all three.
        "commitment.view",
        "commitment.edit",
        "commitment.record",
        # CC-2 pacing: steward is a maker — holds run + view (the perf/risk precedent).
        "pacing.run",
        "pacing.view",
        # CON-1: steward is a maker — run + both view codes (the pacing.run placement).
        "concentration.run",
        "concentration.view",
        "concentration.issuer.view",
        # LQ-1: steward is a maker — run + view (the concentration.run placement).
        "liquidity.run",
        "liquidity.view",
        # RPT-2: steward is a maker — generate + view (the liquidity.run placement).
        "report.generate",
        "report.view",
        # SCH-1 scheduling: steward is an ops maker — manage + view (the pacing.run precedent).
        "schedule.manage",
        "schedule.view",
        # LIM-1 limits: view-only (limit.manage is a 2L risk-manager function — OD-LIM-1-J).
        "limit.view",
        "breach.view",
    ],
    "risk_analyst_1l": [
        "reference.instrument.view",
        "reference.issuer.view",
        "reference.counterparty.view",
        "reference.identifier.resolve",
        # P1B-1 reference vocabularies: view-only for the read tiers.
        "reference.currency.view",
        "reference.rating_scale.view",
        "reference.calendar.view",
        # P1B-2 legal_entity: view-only (matches the issuer/counterparty.view read tier).
        "reference.legal_entity.view",
        # P1B-3 instrument identifiers: view-only (reference.identifier.resolve already above).
        "reference.identifier.view",
        # P1B-4 corporate_action: view-only.
        "reference.corporate_action.view",
        "reference.classification.view",
        "reference.classification_assignment.view",
        "portfolio.view",
        "position.view",
        # P1C-2 transaction: read-tier view-only (transaction.record is maker/admin-only).
        "transaction.view",
        # P1C-4 valuation: read-tier view-only (valuation.edit is maker/admin-only).
        "valuation.view",
        # P2-1 dataset_snapshot: read-tier view-only (snapshot.create is maker/admin-only).
        "snapshot.view",
        # P2-2 market data: read-tier view-only (marketdata.ingest is maker/admin-only).
        "marketdata.view",
        # P2-3 exposure: the 1L analyst RUNS exposure (maker) + views the results.
        "exposure.aggregate.run",
        "exposure.view",
        # P3-1 risk: the 1L analyst RUNS sensitivities (maker) + views the results.
        "risk.run",
        "risk.view",
        # PM-1 perf: the 1L analyst RUNS portfolio returns (maker) + views the results.
        "perf.run",
        "perf.view",
        # CC-1 private capital: read-tier view-only (both maker verbs are maker/admin-only).
        "commitment.view",
        # CC-2 pacing: the 1L analyst RUNS projections (maker) + views the results.
        "pacing.run",
        "pacing.view",
        # CON-1: the 1L analyst RUNS concentration (maker) + both view codes.
        "concentration.run",
        "concentration.view",
        "liquidity.run",
        "liquidity.view",
        # RPT-2: the 1L maker generates + reads reports (the liquidity.run placement).
        "report.generate",
        "report.view",
        "concentration.issuer.view",
        # SCH-1 scheduling: the 1L analyst is the risk maker — manages + views schedules.
        "schedule.manage",
        "schedule.view",
        # LIM-1 limits: the 1L RUNS the numbers but does NOT set limits (SoD) — view-only.
        "limit.view",
        "breach.view",
        # MG-2: the 1L OWNS and remediates a breach (files the response) — but never reviews/closes
        # it (SOD-02); `breach.review` is withheld from 1L (the register/validate partition twin).
        "breach.respond",
        "model.inventory.view",
        # 1L model developer/owner = the maker side of the future SOD-03 maker-checker (P1A-2,
        # OQ-P1A-2-ENT); the independent validator (2L) deliberately does NOT hold register (MG-04).
        "model.inventory.register",
        "dq.result.view",
        "lineage.view",
    ],
    "risk_manager_2l": [
        "reference.instrument.view",
        "reference.issuer.view",
        "reference.counterparty.view",
        # P1B-1 reference vocabularies: view-only.
        "reference.currency.view",
        "reference.rating_scale.view",
        "reference.calendar.view",
        # P1B-2 legal_entity: view-only (matches the issuer/counterparty.view read tier).
        "reference.legal_entity.view",
        # P1B-3 instrument identifiers: view-only. reference.identifier.resolve is NOT granted to
        # risk_manager_2l (its existing recipient set is unchanged — purely additive .view).
        "reference.identifier.view",
        # P1B-4 corporate_action: view-only.
        "reference.corporate_action.view",
        "reference.classification.view",
        "reference.classification_assignment.view",
        "portfolio.view",
        "position.view",
        # P1C-2 transaction: read-tier view-only (transaction.record is maker/admin-only).
        "transaction.view",
        # P1C-4 valuation: read-tier view-only (valuation.edit is maker/admin-only).
        "valuation.view",
        # P2-1 dataset_snapshot: read-tier view-only (snapshot.create is maker/admin-only).
        "snapshot.view",
        # P2-2 market data: read-tier view-only (marketdata.ingest is maker/admin-only).
        "marketdata.view",
        # P2-3 exposure: 2L view-only (exposure.aggregate.run is maker/admin-only).
        "exposure.view",
        # P3-1 risk: 2L view-only (risk.run is maker/admin-only).
        "risk.view",
        # PM-1 perf: 2L view-only (perf.run is maker/admin-only).
        "perf.view",
        # CC-1 private capital: 2L view-only (both maker verbs are maker/admin-only).
        "commitment.view",
        # CC-2 pacing: 2L view-only (pacing.run is maker/admin-only).
        "pacing.view",
        # CON-1: 2L view-only, BOTH codes (concentration.run is maker/admin-only).
        "concentration.view",
        "liquidity.view",
        # RPT-2: 2L reads reports; generate is a 1L/ops maker verb (the *.run split).
        "report.view",
        "concentration.issuer.view",
        # SCH-1 scheduling: 2L view-only (schedule.manage is maker/admin-only).
        "schedule.view",
        # LIM-1 limits: the 2L risk-manager is the limit MAKER (OD-LIM-1-J, the SoD twist) + views.
        "limit.manage",
        # MG-3: the 2L is ALSO the limit CHECKER — maker and checker share the role because the gate
        # is PERSON-level (approver != the draft's maker, SOD-02); a second 2L person signs off.
        "limit.approve",
        "limit.view",
        "breach.view",
        # MG-2: the 2L independently REVIEWS the breach lifecycle — assign an owner, review the 1L
        # response, escalate, close. NEVER co-held with `breach.respond` (SOD-02, the maker-checker
        # partition); the person-level reviewer/closer != responder refusal is the runtime backstop.
        "breach.review",
        # W19-S3b: the 2L manager RATIFIES a mapping and READS it, and never proposes — the
        # checker side. NEVER co-held with `ingest.mapping.propose`, which is what makes this a
        # role-level partition rather than the person-level `limit.approve` shape.
        "ingest.mapping.ratify",
        "ingest.mapping.view",
        "model.inventory.view",
        # VW-1: the 2L independent validator (ROLE-MV) is the ONLY non-admin holder of
        # model.validate — SOD-03 (author ≠ validator): risk_analyst_1l holds register, not this.
        "model.validate",
        "dq.result.view",
        "lineage.view",
    ],
    # ONBOARD-1a: the SEVENTH template, realizing ROLE-ADM ("User/role admin; cannot approve own
    # entitlement requests or edit audit", entitlement_sod_model.md §4) — described since P0.5,
    # never minted. **Deliberately EMPTY in ONBOARD-1a.** The ROLE must exist here because tenant
    # onboarding's seed grant needs something to grant; its VERBS (`user.manage`, `role.assign`,
    # `user.view`, and OQ-9's `role.approve`) are ONBOARD-1b's mint and land with the routes that
    # enforce them. A role with codes but no routes would be a dead guard; a role with routes but
    # no codes cannot exist. Empty-until-1b is the honest ordering, and 1b is a sequenced slice
    # (P19), not a hope.
    "tenant_admin": [
        # ONBOARD-1b fills what 1a minted empty. ROLE-ADM realized: "User/role admin; cannot
        # approve own entitlement requests" — the second clause is `role.approve` plus the
        # person-level refusal, not a withheld code.
        "user.manage",
        "role.assign",
        "user.view",
        "role.approve",
    ],
    "auditor_3l": [
        # W19-S3b: 3L READS the mapping and its ratification history and holds neither verb —
        # the standing 3L exclusion, applied per code rather than to the family.
        "ingest.mapping.view",
        "lineage.view",
        "model.inventory.view",
        "dq.result.view",
        # P1B-1 reference vocabularies: read access for the independent (3L) reviewer.
        "reference.currency.view",
        "reference.rating_scale.view",
        "reference.calendar.view",
        # REF-1: the 3L auditor reads the GLOBAL taxonomy vocabulary (the
        # currency/rating_scale precedent) but NOT classification ASSIGNMENTS,
        # which attach to proprietary issuers/instruments (the legal_entity /
        # identifier / corporate_action exclusion). Two codes exist precisely so
        # this line can differ from the others.
        "reference.classification.view",
        # P2-3 exposure: the 3L auditor VIEWS governed derived outputs (the deliberate inclusion —
        # OD-P2-3-I; distinct from the operational input SoD that excludes auditor from
        # portfolio/transaction/position/valuation/marketdata).
        "exposure.view",
        # P3-1 risk: the 3L auditor VIEWS governed risk outputs (the exposure.view precedent —
        # OD-P3-1-I; governed risk results are 3L-oversight scope).
        "risk.view",
        # PM-1 perf: the 3L auditor VIEWS governed performance outputs (the risk.view precedent —
        # OD-PM-1-A; governed performance results are 3L-oversight scope).
        "perf.view",
        # CC-2 pacing: the 3L auditor VIEWS governed pacing-projection outputs (the perf.view
        # precedent — OD-CC-2-E; a governed OUTPUT is 3L-oversight scope, UNLIKE the captured-input
        # commitment.* verbs the auditor is excluded from).
        "pacing.view",
        # CON-1: the 3L auditor VIEWS governed concentration outputs — `.view` ONLY. The
        # `.issuer.view` code is deliberately ABSENT from this line: issuer-identity reads are the
        # class three prior mints refused the auditor (reference.issuer/legal_entity/
        # classification_assignment.view), and this split exists precisely so this line can differ.
        "concentration.view",
        "liquidity.view",
        # RPT-2: a governed-output artifact read — the unbroken 3L chain (exposure.view →
        # risk.view → perf.view → pacing.view → concentration.view → liquidity.view).
        # NEVER report.generate: 3L observes evidence, it never creates it.
        "report.view",
        # SCH-1 scheduling: the 3L auditor VIEWS schedules + the scheduled_run ledger — a governed
        # control-plane object is 3L-oversight scope (the pacing.view precedent).
        "schedule.view",
        # LIM-1 limits: the 3L auditor VIEWS limits + breach records (governed oversight scope).
        "limit.view",
        "breach.view",
    ],
}


#: The templates a CUSTOMER tenant receives at onboarding (ratified OQ-ONB-6, 2026-08-09).
#:
#: `ops` and `platform_admin` are deliberately EXCLUDED, and the reasons are different:
#:
#: * `ops` holds exactly `ops.audit.verify`, whose only consumer is the BYPASSRLS ops CLI — no HTTP
#:   route enforces it. Cloning it hands a tenant admin a grantable code for a tool tenants never
#:   run: authority with no surface, which reads as protection.
#: * `platform_admin` is `list(ALL_CODES)`. Inside a customer tenant that single role collapses
#:   every SoD partition the matrix builds — register/validate (SOD-03), respond/review (SOD-02),
#:   manage/approve (MG-3) — because one person holding it is on both sides of all three. A tenant
#:   that wants a super-user grants several roles explicitly, where the matrix can see it.
#:
#: The SYSTEM tenant keeps both, unchanged: they are the templates, and the ops CLI is a platform
#: tool. A census asserts no CLONED role is one of these two.
CLONED_TEMPLATES: tuple[str, ...] = (
    "data_steward",
    "risk_analyst_1l",
    "risk_manager_2l",
    "auditor_3l",
    "tenant_admin",
)


#: The tenant-role derivations ONBOARD-1a adds, and the reason they are NEW functions.
#:
#: `role_id(name)` below hardcodes ``SYSTEM_TENANT_ID`` and takes no tenant argument, and
#: `role_permission_id(role, code)` carries no tenant component at all. The first draft of the
#: ONBOARD-1 record claimed "the existing uuid5 derivation already namespaces by tenant"; the
#: verifier pass executed both helpers and refuted it. Reusing either for clones would give every
#: tenant the SAME role id — a collision, not a namespace.
def tenant_role_id(tenant_id: str, name: str) -> str:
    return str(uuid.uuid5(_NS, f"role:{tenant_id}:{name}"))


def tenant_role_permission_id(tenant_id: str, role: str, code: str) -> str:
    return str(uuid.uuid5(_NS, f"role_permission:{tenant_id}:{role}:{code}"))


def permission_id(code: str) -> str:
    return str(uuid.uuid5(_NS, f"permission:{code}"))


def role_id(name: str) -> str:
    return str(uuid.uuid5(_NS, f"role:{SYSTEM_TENANT_ID}:{name}"))


def role_permission_id(role: str, code: str) -> str:
    return str(uuid.uuid5(_NS, f"role_permission:{role}:{code}"))
