"""MG-2 breach remediation lifecycle: breach_action (ENT-034, IA append-only).

Wave-11 slice 3. Realizes the reserved ENT-034 ``breach_action`` as the DEP-WFL state machine over
``breach`` (``DETECTED → ASSIGNED → RESPONDED → REVIEWED → CLOSED`` + orthogonal ``ESCALATED``). The
operative current state is the recency-derived latest action (``ORDER BY seq DESC``); this table is
TRUE append-only (the 0001 ``irp_prevent_mutation()`` trigger + the ORM guard).

PROPRIETARY, tenant-scoped, symmetric FORCE RLS — NEVER hybrid; NO ops-role grant (the SCH-1/LIM-1
posture — the app does all reads/writes tenant-scoped NON-BYPASSRLS).

Two idempotency structures: ``uq_breach_action_seq (breach_id, seq)`` pins the per-breach monotonic
ordering key; ``uq_breach_escalation`` is a PARTIAL unique index over ESCALATE rows on
``(breach_id, response_due)`` — a breach escalates at most once per deadline epoch (a post-recovery
ASSIGN stamps a fresh ``response_due`` = a new epoch, admitting a legitimate re-escalation).

Realizes ENT-034; activates the reserved BREACH.ASSIGN/.1L_RESPONSE/.2L_REVIEW/.ESCALATE/.CLOSE audit
codes. Mints NO new governed number and NO new ``run_type``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_breach_action"
down_revision: str | None = "0050_limit_breach"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("breach_action",)
APPEND_ONLY_TABLES = ("breach_action",)

_IDENTIFIERS = (
    "breach_action",
    "pk_breach_action",
    "fk_breach_action_breach_id_breach",
    "uq_breach_action_seq",
    "uq_breach_escalation",
    "ix_breach_action_tenant_id",
    "ix_breach_action_breach_id",
    "tenant_isolation_breach_action",
    "breach_action_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    # --- ENT-034 breach_action (IA TRUE append-only; one row per lifecycle transition) ---
    op.create_table(
        "breach_action",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("breach_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=20), nullable=False),
        sa.Column("from_state", sa.String(length=20), nullable=False),
        sa.Column("to_state", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_line", sa.String(length=4), nullable=False),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("response_due", sa.DateTime(timezone=True), nullable=True),
        sa.Column("narrative", sa.String(length=2000), nullable=True),
        sa.Column("review_outcome", sa.String(length=10), nullable=True),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_breach_action"),
        sa.ForeignKeyConstraint(
            ["breach_id"], ["breach.id"], name="fk_breach_action_breach_id_breach"
        ),
        sa.UniqueConstraint("breach_id", "seq", name="uq_breach_action_seq"),
    )
    op.create_index("ix_breach_action_tenant_id", "breach_action", ["tenant_id"])
    op.create_index("ix_breach_action_breach_id", "breach_action", ["breach_id"])
    # escalate-once-per-deadline: partial unique index over ESCALATE rows only.
    op.create_index(
        "uq_breach_escalation",
        "breach_action",
        ["breach_id", "response_due"],
        unique=True,
        postgresql_where=sa.text("action_type = 'ESCALATE'"),
    )

    # --- symmetric FORCE RLS (PROPRIETARY; NO ops-role grant) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- append-only trigger (reuses the 0001 P0001 function) ---
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("breach_action")
