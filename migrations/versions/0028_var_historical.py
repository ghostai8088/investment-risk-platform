"""VAR-HS-1: relax the parametric-only ``var_result`` columns for historical simulation.

``metric_type='VAR_HISTORICAL'`` rows (OD-VHS-C) carry no ``z_score`` (there is no normal
quantile — the method's point), no ``sigma`` (no volatility estimate is produced), and no
``covariance_run_id`` (the method consumes NO covariance run — a stuffed placeholder would be
DISHONEST provenance); all three become NULLABLE. ADDITIVE relaxation on the IA append-only
table: no row changes, no RLS/trigger/grain change; the parametric binder keeps writing all
three (its NOT-NULL discipline moves to the binder, where it always lived semantically).

No new audit code, permission, or entity. ``audit/service.py`` FROZEN.

Revision ID: 0028_var_historical
Revises: 0027_run_failure_reason
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_var_historical"
down_revision: str | None = "0027_run_failure_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("var_result", "z_score", existing_type=sa.Numeric(20, 12), nullable=True)
    op.alter_column("var_result", "sigma", existing_type=sa.Numeric(28, 6), nullable=True)
    op.alter_column(
        "var_result",
        "covariance_run_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )
    # The relaxation is METRIC-CONDITIONAL at the DB (2026-07 review, governance finder): a
    # parametric row without its declared parameters/provenance would be a permanently
    # uncorrectable IA row — the invariant stays DB-enforced, not binder-discipline-only.
    op.create_check_constraint(
        "parametric_not_null",  # the naming convention prefixes ck_var_result_
        "var_result",
        "metric_type = 'VAR_HISTORICAL' OR "
        "(z_score IS NOT NULL AND sigma IS NOT NULL AND covariance_run_id IS NOT NULL)",
    )


def downgrade() -> None:
    # VAR_HISTORICAL rows are UNREPRESENTABLE in the pre-0028 schema (NULL z_score/sigma/
    # covariance_run_id vs NOT NULL): the downgrade REMOVES them (the 0026 drop-table precedent —
    # schema reversal destroys the rows the schema can no longer hold; the P0001 append-only
    # trigger protects business mutation, not migrations, and is disabled around the delete).
    # FORCE RLS is ALSO disabled around the delete (2026-07 review — three finders
    # independently): the tenant policy binds even the table OWNER, so under any non-superuser
    # migration role the DELETE silently matched ZERO rows and the SET NOT NULL then aborted
    # the downgrade midway. CI's green smoke had proven only the container-superuser path.
    # Both toggles are transactional (env.py wraps the migration in one transaction).
    op.drop_constraint("parametric_not_null", "var_result", type_="check")  # convention expands ck_var_result_
    op.execute("ALTER TABLE var_result DISABLE TRIGGER var_result_append_only")
    op.execute("ALTER TABLE var_result DISABLE ROW LEVEL SECURITY")
    op.execute("DELETE FROM var_result WHERE metric_type = 'VAR_HISTORICAL'")
    op.execute("ALTER TABLE var_result ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE var_result FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE var_result ENABLE TRIGGER var_result_append_only")
    op.alter_column(
        "var_result",
        "covariance_run_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
    op.alter_column("var_result", "sigma", existing_type=sa.Numeric(28, 6), nullable=False)
    op.alter_column("var_result", "z_score", existing_type=sa.Numeric(20, 12), nullable=False)
