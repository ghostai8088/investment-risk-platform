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
    # SCH-1 scheduling (ENT-061 schedule / ENT-062 scheduled_run, Wave-11 slice 1) — a governed
    # R-07 mint (OD-SCH-1-G, ratified 2026-07-23). BOTH codes NEW — a schedule is a control-plane
    # config object that DRIVES governed-number production; neither a risk nor a performance verb
    # gates it. `schedule.manage` is the maker verb (create/edit/pause a schedule — mirrors
    # pacing.run/risk.run); `schedule.view` reads schedules + the scheduled_run ledger. `.manage`
    # goes to the 1L risk maker + the data_steward ops maker (the pacing.run placement); `.view`
    # goes broadly INCLUDING auditor_3l — a governed control-plane object is 3L-oversight scope
    # (the pacing.view precedent). Dispatch itself runs as a synthesized SYSTEM actor, ungated.
    # Forward-gate: SCH-1 ships no schedule API endpoint yet; when one lands it MUST carry
    # require_permission("schedule.manage") (the pacing.py pattern) — nothing below the API layer
    # enforces the maker verb (consistent with the perf/pacing service-ungated design).
    ("schedule.manage", "Create, edit and pause governed run schedules"),
    ("schedule.view", "View run schedules and the scheduled-run ledger"),
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
        # SCH-1 scheduling: steward is an ops maker — manage + view (the pacing.run precedent).
        "schedule.manage",
        "schedule.view",
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
        # SCH-1 scheduling: the 1L analyst is the risk maker — manages + views schedules.
        "schedule.manage",
        "schedule.view",
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
        # SCH-1 scheduling: 2L view-only (schedule.manage is maker/admin-only).
        "schedule.view",
        "model.inventory.view",
        # VW-1: the 2L independent validator (ROLE-MV) is the ONLY non-admin holder of
        # model.validate — SOD-03 (author ≠ validator): risk_analyst_1l holds register, not this.
        "model.validate",
        "dq.result.view",
        "lineage.view",
    ],
    "auditor_3l": [
        "lineage.view",
        "model.inventory.view",
        "dq.result.view",
        # P1B-1 reference vocabularies: read access for the independent (3L) reviewer.
        "reference.currency.view",
        "reference.rating_scale.view",
        "reference.calendar.view",
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
        # SCH-1 scheduling: the 3L auditor VIEWS schedules + the scheduled_run ledger — a governed
        # control-plane object is 3L-oversight scope (the pacing.view precedent).
        "schedule.view",
    ],
}


def permission_id(code: str) -> str:
    return str(uuid.uuid5(_NS, f"permission:{code}"))


def role_id(name: str) -> str:
    return str(uuid.uuid5(_NS, f"role:{SYSTEM_TENANT_ID}:{name}"))


def role_permission_id(role: str, code: str) -> str:
    return str(uuid.uuid5(_NS, f"role_permission:{role}:{code}"))
