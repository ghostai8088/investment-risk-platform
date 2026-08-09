"""ONBOARD-1b: ENT-075 ``entitlement_request`` + the four tenant-administration codes.

**CTRL-025 finally gets its code.** `entitlement_sod_model.md` §7 has required four-eyes on
entitlement changes since P0.5, and the control row has been *Planned* the whole time. ONBOARD-1's
first design draft contradicted the rule outright (a single admin granting directly); the verifier
pass called it, and OQ-ONB-9A ratified the maker-checker with a single-admin bootstrap window.

**What ships here:**

* ENT-075 ``entitlement_request`` — IA append-only, symmetric tenant-scoped FORCE RLS, the
  ``irp_prevent_mutation`` P0001 trigger. An approval that could be edited into existence after
  the fact is not an approval, which is the only property this table has to have.
* the per-tenant monotonic ``seq`` unique key (the MG-2 pattern — wall-clock ties, and two admins
  acting in the same millisecond is precisely what this table adjudicates);
* three CHECKs, all TOTAL enumerations (the 0053 pattern) — action, status, and the resolution
  coherence check: PENDING iff unresolved. That last one is a CHECK rather than application
  discipline because "approved by nobody" is the single state that would make the control
  decorative;
* the four codes, delivered to running databases via ``sync_catalog`` — ``DELIVERS`` below is what
  P17's gate reads, and ONBOARD-1a proved by execution that a catalog the gate cannot see is a
  catalog with no delivery discipline at all.

**The `tenant_admin` template gains its grants here too.** 1a minted the role EMPTY (the seed
grant needed something to grant; the verbs had no routes yet). The sync inserts the new
role_permission rows for the SYSTEM template — and, deliberately, **not** for tenants already
onboarded: post-clone drift is tenant configuration, and delivering into existing tenants' clones
is the mint-checklist row §5C-5 exists to force a decision about. That decision is recorded in the
slice record: existing tenants' `tenant_admin` clones are backfilled HERE, because at the time of
writing exactly one deployment path exists and a tenant whose admin role silently lacks the verbs
its own UI offers is worse than the drift the general rule guards against.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from irp_shared.db.types import GUID
from irp_shared.entitlement.bootstrap import (
    SYSTEM_TENANT_ID,
    permission_id,
    role_permission_id,
    tenant_role_permission_id,
)
from irp_shared.entitlement.sync import sync_catalog

revision: str = "0068_entitlement_request"
down_revision: str | None = "0067_tenant_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)

#: The permission codes this revision DELIVERS to a running database (P17).
DELIVERS: tuple[str, ...] = (
    "user.manage",
    "role.assign",
    "user.view",
    "role.approve",
)

_role = sa.table(
    "role",
    sa.column("id", GUID()),
    sa.column("tenant_id", GUID()),
    sa.column("code", sa.String()),
)
_role_permission = sa.table(
    "role_permission",
    sa.column("id", GUID()),
    sa.column("role_id", GUID()),
    sa.column("permission_id", GUID()),
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "entitlement_request",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("target_role_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolves_request_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_entitlement_request"),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["app_user.id"],
            name="fk_entitlement_request_target_user_id_app_user",
        ),
        sa.ForeignKeyConstraint(
            ["target_role_id"], ["role.id"], name="fk_entitlement_request_target_role_id_role"
        ),
        sa.ForeignKeyConstraint(
            ["resolves_request_id"],
            ["entitlement_request.id"],
            name="fk_entitlement_request_resolves_request_id_entitlement_request",
        ),
        sa.UniqueConstraint("tenant_id", "seq", name="uq_entitlement_request_seq"),
    )
    op.create_index("ix_entitlement_request_tenant_id", "entitlement_request", ["tenant_id"])
    op.create_index(
        "ix_entitlement_request_target_user_id", "entitlement_request", ["target_user_id"]
    )
    op.create_index(
        "ix_entitlement_request_target_role_id", "entitlement_request", ["target_role_id"]
    )
    op.create_index(
        "ix_entitlement_request_tenant_status", "entitlement_request", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_entitlement_request_resolves_request_id",
        "entitlement_request",
        ["resolves_request_id"],
    )
    op.create_check_constraint(
        "action",
        "entitlement_request",
        "action IN ('GRANT_ROLE', 'REVOKE_ROLE', 'DEACTIVATE_USER')",
    )
    op.create_check_constraint(
        "status",
        "entitlement_request",
        "status IN ('PENDING', 'APPROVED', 'REJECTED', 'DIRECT')",
    )
    # A RESOLUTION row points at what it resolves; an originating row does not. Appending the
    # decision rather than mutating the request is what makes the trigger below compatible with a
    # lifecycle at all — the first implementation mutated, and PostgreSQL refused it.
    op.create_check_constraint(
        "resolution_link",
        "entitlement_request",
        "(resolves_request_id IS NULL AND status IN ('PENDING', 'DIRECT')) "
        "OR (resolves_request_id IS NOT NULL AND status IN ('APPROVED', 'REJECTED'))",
    )
    # The one CHECK that makes the control non-decorative: a resolved request NAMES its resolver.
    op.create_check_constraint(
        "resolution",
        "entitlement_request",
        "(status = 'PENDING' AND resolved_by IS NULL AND resolved_at IS NULL) "
        "OR (status <> 'PENDING' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
    )

    if is_pg:
        op.execute("ALTER TABLE entitlement_request ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE entitlement_request FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation_entitlement_request ON entitlement_request "
            "USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            "WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )
        # IA append-only: the 0001 P0001 trigger. Evidence of who approved what must not be
        # editable by the people it constrains.
        op.execute(
            "CREATE TRIGGER trg_entitlement_request_no_mutation "
            "BEFORE UPDATE OR DELETE ON entitlement_request "
            "FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )

    # --- deliver the four codes + the tenant_admin template grants -----------------------------
    report = sync_catalog(bind, now=TS)
    print(  # noqa: T201 - migration console output
        f"0068: +{report.permissions_inserted} permissions, +{report.grants_inserted} grants"
    )

    # --- backfill EXISTING tenants' tenant_admin clones (see the module docstring) --------------
    if is_pg:
        op.execute(
            sa.text("SELECT set_config('app.current_tenant', :t, true)").bindparams(
                t=SYSTEM_TENANT_ID
            )
        )
    tenant_admin_roles = bind.execute(
        sa.select(_role.c.id, _role.c.tenant_id).where(
            _role.c.code == "tenant_admin", _role.c.tenant_id != SYSTEM_TENANT_ID
        )
    ).all()
    missing = []
    for role_id_value, tenant_id_value in tenant_admin_roles:
        for code in DELIVERS:
            gid = tenant_role_permission_id(
                str(tenant_id_value), "tenant_admin", permission_id(code)
            )
            missing.append(
                {
                    "id": gid,
                    "role_id": str(role_id_value),
                    "permission_id": permission_id(code),
                }
            )
    if missing:
        present = {
            str(r)
            for r in bind.execute(
                sa.select(_role_permission.c.id).where(
                    _role_permission.c.id.in_([m["id"] for m in missing])
                )
            )
            .scalars()
            .all()
        }
        to_insert = [m for m in missing if m["id"] not in present]
        if to_insert:
            op.bulk_insert(_role_permission, to_insert)
        print(f"0068: +{len(to_insert)} tenant_admin clone grants backfilled")  # noqa: T201


def downgrade() -> None:
    """Drop ENT-075; leave the entitlement rows (the ``0064``/``0067`` reasoning).

    Honest about the consequence: dropping this table destroys the record of who approved which
    entitlement change. The schema reverses; the evidence does not come back.
    """
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_entitlement_request_no_mutation ON entitlement_request")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_entitlement_request ON entitlement_request")
    op.drop_table("entitlement_request")
