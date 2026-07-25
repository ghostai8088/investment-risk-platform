"""NOTIF-1 breach notification: breach_notification (ENT-064, IA append-only).

Wave-12 slice 2. Realizes ENT-064 ``breach_notification`` — one durable attempt row per
(alarm audit event, recipient), the system-of-record for "who was owed a breach alert, for what
event, when, with what outcome" (OQ-1=A record-first). Consumed by tick phase 4
(``notify_tenant_breaches``) over the ``BREACH.DETECT``/``BREACH.ESCALATE`` audit stream.

PROPRIETARY, tenant-scoped, symmetric FORCE RLS — NEVER hybrid; NO ops-role grant (the SCH-1/LIM-1
posture — the app does all reads/writes tenant-scoped NON-BYPASSRLS). TRUE append-only (the 0001
``irp_prevent_mutation()`` trigger + the ORM guard).

Idempotency: ``uq_breach_notification_event_recipient (tenant_id, source_sequence_no, recipient_id)``
= at-most-once per recipient per alarm event (the ``uq_breach_escalation`` pattern). The per-tenant
high-water is DERIVED from ``MAX(source_sequence_no)`` (OQ-4=B — no separate cursor table); a
no-recipient event writes ONE ``SUPPRESSED`` sentinel row (``recipient_id`` = the fixed non-null
all-zeros UUID) so the derived cursor still advances.

Mints NO governed number and NO ``run_type``. NO new permission (the read reuses ``breach.view``).
Activates the R-07-minted ``NOTIFY.DISPATCH`` audit code (OQ-5=A; the taxonomy row IS the mint
record) — emitted caller-side to the FROZEN ``record_event``, which is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052_breach_notification"
down_revision: str | None = "0051_breach_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("breach_notification",)
APPEND_ONLY_TABLES = ("breach_notification",)

_IDENTIFIERS = (
    "breach_notification",
    "pk_breach_notification",
    "fk_breach_notification_breach_id_breach",
    "uq_breach_notification_event_recipient",
    "ix_breach_notification_tenant_id",
    "ix_breach_notification_breach_id",
    "ix_breach_notification_tenant_seq",
    "tenant_isolation_breach_notification",
    "breach_notification_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    # --- ENT-064 breach_notification (IA TRUE append-only; one row per (event, recipient)) ---
    op.create_table(
        "breach_notification",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_sequence_no", sa.BigInteger(), nullable=False),
        sa.Column("source_event_type", sa.String(length=100), nullable=False),
        sa.Column("breach_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("recipient_id", sa.String(length=255), nullable=False),
        sa.Column("recipient_reason", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_breach_notification"),
        sa.ForeignKeyConstraint(
            ["breach_id"], ["breach.id"], name="fk_breach_notification_breach_id_breach"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_sequence_no",
            "recipient_id",
            name="uq_breach_notification_event_recipient",
        ),
    )
    op.create_index("ix_breach_notification_tenant_id", "breach_notification", ["tenant_id"])
    op.create_index("ix_breach_notification_breach_id", "breach_notification", ["breach_id"])
    # the derived-high-water scan: "alarm events already notified for this tenant".
    op.create_index(
        "ix_breach_notification_tenant_seq",
        "breach_notification",
        ["tenant_id", "source_sequence_no"],
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
    op.drop_table("breach_notification")
