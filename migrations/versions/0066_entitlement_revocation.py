"""The revocation ledger — the half of P17 that stops a sync resurrecting a governance act.

Migration ``0064`` fixed a platform-wide defect (a permission appended to ``bootstrap.py`` never
reaches a database that already exists, so deny-by-default 403s every holder in production while
every from-empty test passes). It fixed it by syncing the whole catalog into whatever is already
there — and, as merged, that sync **re-inserted template grants an administrator had deliberately
revoked**, because a revoked grant and a never-delivered grant are the same database state: the
deterministic ``uuid5`` id is a function of ``(role, code)`` alone.

The Wave-16 close review refused to ratify the sync on those terms — mandating it without
addressing revocation durability institutionalises the resurrection and makes a governance action
transient. This table is the missing bit of state. ``entitlement.sync.sync_catalog`` consults it
and SKIPS + LOGS; ``0064`` was amended to route through that one implementation.

**Shape.** A deliberate mirror of ``role_permission``: global (no ``tenant_id``, no RLS — the pair
it shadows has none either), keyed by the same ``(role_id, permission_id)``, unique on that pair.
Keying on the ids rather than on the codes means a revocation cannot name a role or a permission
that does not exist, which the FKs enforce.

**No data.** The ledger ships EMPTY. Populating it would assert that somebody revoked something,
and nobody has; the first row is an administrative act, not a migration's business.

**What this does not repair.** Downgrading below this revision drops the table, so a re-upgrade has
nothing to consult and ``0064`` reverts to additive-only behaviour. No mechanism inside a migration
can survive the destruction of its own evidence — stated here rather than papered over.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0066_entitlement_revocation"
down_revision: str | None = "0065_reproduction_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_permission_revocation",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_role_permission_revocation"),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name="fk_role_permission_revocation_role_id_role"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permission.id"],
            name="fk_role_permission_revocation_permission_id_permission",
        ),
        sa.UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permission_revocation_role_id"
        ),
    )
    op.create_index(
        "ix_role_permission_revocation_role_id", "role_permission_revocation", ["role_id"]
    )
    op.create_index(
        "ix_role_permission_revocation_permission_id",
        "role_permission_revocation",
        ["permission_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_role_permission_revocation_permission_id", "role_permission_revocation")
    op.drop_index("ix_role_permission_revocation_role_id", "role_permission_revocation")
    op.drop_table("role_permission_revocation")
