"""REPRO-1: the REPRODUCTION family is admitted, and ENT-073 ``reproduction_check`` is minted.

**Why a migration exists at all, when the ratified shape said "ride the existing scheduler".**
``ck_schedule_model_version_by_family`` (0053) is a TOTAL ENUMERATION over exactly ``VAR`` and
``EXPOSURE_AGGREGATE``, and 0053's own docstring records that as deliberate: "the
exclusive-exhaustive form below fails CLOSED, which makes admitting family 3 require a migration."
PostgreSQL therefore REJECTS a ``REPRODUCTION`` schedule row until this lands. The trap worth
naming: SQLite carries no CHECK constraints, so the entire unit tier — ``make check`` — goes green
with the registry widened and no migration, and only ``test_scheduler_cadence_pg.py``'s family
matrix catches it, and only when the full-PG battery is actually run.

Three acts:

1. ``ck_schedule_model_version_by_family`` is re-created WIDENED with a third arm. REPRODUCTION is
   **model-less**: the sweep runs no model of its own, it re-executes families that each bind their
   own registered version. So the arm is ``model_version_id IS NULL``, and ``_validate_config``
   enforces that direction too — a reproduction schedule may never nominate a model version.

2. ``schedule.scope_portfolio_id`` is relaxed to NULL-able under a NEW total-enumeration CHECK,
   ``ck_schedule_portfolio_scope_by_family``. This is the 0053 pattern applied to a second column
   for the same reason: the value is REQUIRED for some families and FORBIDDEN for others. VAR and
   EXPOSURE_AGGREGATE compute a specific book's number; the reproduction sweep is tenant-wide and
   re-executes families that are not all portfolio-scoped (covariance is tenant-global). The
   alternative — nominating a sentinel book — would stamp a scope into a governed config row that
   is not true, and the OPS-1 UI renders that row to operators.

   Relaxing a shipped NOT NULL is safe in this direction (every existing row already has a value);
   the CHECK is what keeps the guarantee for the families that still need it, so nothing is lost
   except the ability to express a family that has no book.

3. ENT-073 ``reproduction_check`` — symmetric per-tenant FORCE RLS (a verdict names a book's
   governed runs), plus the ``irp_prevent_mutation`` P0001 trigger from 0001. A verdict that could
   be edited after the fact is not evidence.

**The ck expansion asymmetry (the 0058 lesson, restated because it is easy to lose):** ``ck`` is the
only NAMING_CONVENTION entry keyed on ``%(constraint_name)s``, so alembic EXPANDS what is passed to
``drop_constraint`` exactly as it does for ``create_check_constraint``. Both take the SUFFIX;
passing a full name mints ``ck_schedule_ck_schedule_...``, which PostgreSQL then truncates at 63
with a hash — invisible to a text-vs-text comparison AND to ``alembic check``. ``_IDENTIFIERS``
asserts the EXPANDED forms.

Revision id kept SHORT: ``alembic_version.version_num`` is varchar(32) and a longer id fails at the
INSERT, not at parse (the trap 0062 caught by execution).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0065_reproduction_check"  # 22 chars, well inside varchar(32)
down_revision: str | None = "0064_entitlement_sync"
branch_labels: None = None
depends_on: None = None

# --- frozen vocabulary literals -------------------------------------------------------------
# Deliberately literals, NOT imports of the live constants: a migration that imports an
# application constant silently re-writes history when the constant moves (0061's rule). 0064
# imports from bootstrap because it is a DATA sync; this is DDL.
_VAR = "VAR"
_EXPOSURE = "EXPOSURE_AGGREGATE"
_REPRODUCTION = "REPRODUCTION"

_CHECK_MODEL_VERSION = "model_version_by_family"
_CHECK_PORTFOLIO_SCOPE = "portfolio_scope_by_family"

TENANT_SCOPED_TABLES = ("reproduction_check",)
APPEND_ONLY_TABLES = ("reproduction_check",)

_IDENTIFIERS = (
    f"ck_schedule_{_CHECK_MODEL_VERSION}",
    f"ck_schedule_{_CHECK_PORTFOLIO_SCOPE}",
    "uq_reproduction_check_sweep_subject",
    "ix_reproduction_check_lookup",
    "reproduction_check_append_only",
    "tenant_isolation_reproduction_check",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]

#: The 0053 body, VERBATIM — what ``downgrade`` restores. Captured rather than re-derived: a
#: downgrade that "restores" a constraint that never existed is worse than no downgrade at all
#: (the 0059 precedent, which preserved its own predecessors' bodies for exactly this reason).
_MODEL_VERSION_SQL_0053 = (
    f"(target_run_type = '{_VAR}' AND model_version_id IS NOT NULL)"
    f" OR (target_run_type = '{_EXPOSURE}' AND model_version_id IS NULL)"
)

#: The widened body — still a TOTAL enumeration, still failing closed for a fourth family.
_MODEL_VERSION_SQL = (
    f"(target_run_type = '{_VAR}' AND model_version_id IS NOT NULL)"
    f" OR (target_run_type = '{_EXPOSURE}' AND model_version_id IS NULL)"
    f" OR (target_run_type = '{_REPRODUCTION}' AND model_version_id IS NULL)"
)

#: New at REPRO-1, and a total enumeration by construction so family 4 fails closed here too.
_PORTFOLIO_SCOPE_SQL = (
    f"(target_run_type IN ('{_VAR}', '{_EXPOSURE}') AND scope_portfolio_id IS NOT NULL)"
    f" OR (target_run_type = '{_REPRODUCTION}' AND scope_portfolio_id IS NULL)"
)


def upgrade() -> None:
    # --- 1. the family CHECK gains its REPRODUCTION arm --------------------------------------
    op.drop_constraint(_CHECK_MODEL_VERSION, "schedule", type_="check")
    op.create_check_constraint(_CHECK_MODEL_VERSION, "schedule", _MODEL_VERSION_SQL)

    # --- 2. scope_portfolio_id becomes family-gated -------------------------------------------
    op.alter_column(
        "schedule",
        "scope_portfolio_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=False),
        nullable=True,
    )
    op.create_check_constraint(_CHECK_PORTFOLIO_SCOPE, "schedule", _PORTFOLIO_SCOPE_SQL)

    # --- 3. ENT-073 ---------------------------------------------------------------------------
    op.create_table(
        "reproduction_check",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "calculation_run_id",
            sa.Uuid(),
            sa.ForeignKey("calculation_run.run_id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "subject_run_id",
            sa.Uuid(),
            sa.ForeignKey("calculation_run.run_id"),
            nullable=False,
            index=True,
        ),
        sa.Column("family_key", sa.String(length=100), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("rows_compared", sa.Integer(), nullable=False),
        sa.Column("rows_diverged", sa.Integer(), nullable=False),
        sa.Column("first_divergence", sa.Text(), nullable=True),
        # ImmutableAppendOnlyMixin records ONLY system (knowledge) time — no record_version, no
        # created_at. The ORM is the authority and the migration follows it, not the reverse
        # (0063 shipped the inverse mistake and `alembic check` caught it).
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_reproduction_check_sweep_subject",
        "reproduction_check",
        ["calculation_run_id", "subject_run_id"],
        unique=True,
    )
    op.create_index(
        "ix_reproduction_check_lookup",
        "reproduction_check",
        ["tenant_id", "family_key", "verdict"],
    )

    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    """Honestly destructive for rows only the new schema can represent.

    A REPRODUCTION schedule has a NULL ``scope_portfolio_id`` that the restored NOT NULL cannot
    hold, and its ``scheduled_run`` children are append-only. Both are deleted here rather than
    left to fail the ``ALTER`` with an opaque constraint error — the 0059 precedent, which made the
    same choice for its BUSINESS_MONTH_END rows and said so.
    """
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("reproduction_check")

    op.drop_constraint(_CHECK_PORTFOLIO_SCOPE, "schedule", type_="check")
    # The children first (FK NO ACTION), then the heads the restored NOT NULL cannot represent.
    op.execute(
        "DELETE FROM scheduled_run WHERE schedule_id IN "
        f"(SELECT id FROM schedule WHERE target_run_type = '{_REPRODUCTION}')"
    )
    op.execute(f"DELETE FROM schedule WHERE target_run_type = '{_REPRODUCTION}'")
    op.alter_column(
        "schedule",
        "scope_portfolio_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=False),
        nullable=False,
    )

    op.drop_constraint(_CHECK_MODEL_VERSION, "schedule", type_="check")
    op.create_check_constraint(_CHECK_MODEL_VERSION, "schedule", _MODEL_VERSION_SQL_0053)
