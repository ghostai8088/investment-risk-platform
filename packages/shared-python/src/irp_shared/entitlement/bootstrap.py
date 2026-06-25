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
    ("exposure.aggregate.run", "Run exposure aggregation"),
    # P1C-2 transaction (additive; PROPRIETARY tenant-scoped, IA append-only). `.record` is the
    # append-only governed-write verb (a transaction is recorded, never edited — no `.edit`).
    ("transaction.view", "View transactions"),
    ("transaction.record", "Record transactions"),
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
        "model.inventory.view",
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
    ],
}


def permission_id(code: str) -> str:
    return str(uuid.uuid5(_NS, f"permission:{code}"))


def role_id(name: str) -> str:
    return str(uuid.uuid5(_NS, f"role:{SYSTEM_TENANT_ID}:{name}"))


def role_permission_id(role: str, code: str) -> str:
    return str(uuid.uuid5(_NS, f"role_permission:{role}:{code}"))
