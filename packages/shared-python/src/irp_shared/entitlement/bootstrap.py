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
    ("portfolio.view", "View portfolios"),
    ("portfolio.edit", "Edit portfolios"),
    ("position.view", "View positions"),
    ("exposure.aggregate.run", "Run exposure aggregation"),
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
    ],
    "risk_analyst_1l": [
        "reference.instrument.view",
        "reference.issuer.view",
        "reference.counterparty.view",
        "reference.identifier.resolve",
        "portfolio.view",
        "position.view",
        "model.inventory.view",
        "dq.result.view",
        "lineage.view",
    ],
    "risk_manager_2l": [
        "reference.instrument.view",
        "reference.issuer.view",
        "reference.counterparty.view",
        "portfolio.view",
        "position.view",
        "model.inventory.view",
        "dq.result.view",
        "lineage.view",
    ],
    "auditor_3l": ["lineage.view", "model.inventory.view", "dq.result.view"],
}


def permission_id(code: str) -> str:
    return str(uuid.uuid5(_NS, f"permission:{code}"))


def role_id(name: str) -> str:
    return str(uuid.uuid5(_NS, f"role:{SYSTEM_TENANT_ID}:{name}"))


def role_permission_id(role: str, code: str) -> str:
    return str(uuid.uuid5(_NS, f"role_permission:{role}:{code}"))
