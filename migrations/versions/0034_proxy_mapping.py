"""PA-0: proxy_mapping (ENT-019, FR bitemporal captured private→public factor proxy weights).

The FIRST private-asset foundation (the differentiation-thesis destination). A **captured** proxy
weight — a governance judgment call recording that a PRIVATE instrument's risk loads on a public
``factor`` — **NEVER computed** (no regression engine in v1; a regression-derived weight is a v2
extension). Tenant-scoped PROPRIETARY under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own``) — the SAME pattern as 0009..0033. **NOT hybrid** (private-asset
proxy data is per-tenant proprietary). The 0008 hybrid loop + the closed 5-table hybrid set are
UNCHANGED.

**NOT append-only** (FR requires close-out UPDATEs to ``valid_to``/``system_to`` on a proxy
revision) — ``APPEND_ONLY_TABLES`` is empty and NO ``irp_prevent_mutation`` trigger is installed
(the 0023 factor_return / 0021 benchmark precedent). Content-immutability is service-enforced +
tested.

Current-head partial-unique ``(tenant_id, private_instrument_id, factor_id) WHERE valid_to IS NULL
AND system_to IS NULL`` — exactly one OPEN weight per instrument+factor pair (a MULTI-row blend
across factors per instrument is normal; weights are NOT constrained to sum to 1). ``weight``
``Numeric(20, 12)`` (a signed public-factor loading, NOT currency). Two hard FKs:
``private_instrument_id`` → ``instrument.id``, ``factor_id`` → ``factor.id`` (a private asset is an
ORDINARY instrument with a documented private ``asset_class`` convention — NO new instrument
schema).

**Captured INPUT only** — NO ``calculation_run``, NO ``model_version``, NO snapshot pin (the
``factor_return`` precedent; a governed number consuming this — the PA-1 desmoothing/proxy transform
— is a LATER slice). No new audit code / permission table (``MARKET.PROXY_MAPPING_*`` are
caller-side constants; ``marketdata.view``/``.ingest`` REUSED). Every DDL identifier here is <= 63
chars (asserted below — the P3-8/BT-1 lesson).

Revision ID: 0034_proxy_mapping
Revises: 0033_var_backtest
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_proxy_mapping"
down_revision: str | None = "0033_var_backtest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("proxy_mapping",)
#: NOT append-only — FR requires close-out UPDATEs. NO irp_prevent_mutation trigger (the 0023
#: factor_return precedent).
APPEND_ONLY_TABLES: tuple[str, ...] = ()

#: Every name this migration mints, checked at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "proxy_mapping",
    "pk_proxy_mapping",
    "fk_proxy_mapping_private_instrument_id_instrument",
    "fk_proxy_mapping_factor_id_factor",
    "fk_proxy_mapping_supersedes_id_proxy_mapping",
    "ix_proxy_mapping_tenant_id",
    "ix_proxy_mapping_private_instrument_id",
    "ix_proxy_mapping_factor_id",
    "uq_proxy_mapping_current",
    "tenant_isolation_proxy_mapping",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "proxy_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("private_instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("factor_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("weight", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("mapping_method", sa.String(length=30), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_proxy_mapping"),
        sa.ForeignKeyConstraint(
            ["private_instrument_id"],
            ["instrument.id"],
            name="fk_proxy_mapping_private_instrument_id_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["factor_id"], ["factor.id"], name="fk_proxy_mapping_factor_id_factor"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["proxy_mapping.id"],
            name="fk_proxy_mapping_supersedes_id_proxy_mapping",
        ),
    )
    op.create_index("ix_proxy_mapping_tenant_id", "proxy_mapping", ["tenant_id"])
    op.create_index(
        "ix_proxy_mapping_private_instrument_id", "proxy_mapping", ["private_instrument_id"]
    )
    op.create_index("ix_proxy_mapping_factor_id", "proxy_mapping", ["factor_id"])
    op.create_index(
        "uq_proxy_mapping_current",
        "proxy_mapping",
        ["tenant_id", "private_instrument_id", "factor_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17).
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- NO append-only trigger: proxy_mapping (FR) is NOT append-only (APPEND_ONLY_TABLES empty —
    # --- the 0023 factor_return precedent). ---
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in PA-0
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in PA-0
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("proxy_mapping")
