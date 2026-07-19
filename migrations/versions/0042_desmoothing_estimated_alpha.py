"""DS-2: relax ``desmoothed_return_result.alpha`` for Okunev-White rows + the estimated-α band.

The OKUNEV_WHITE_ITERATIVE convention (OD-DS-2-B) has NO single alpha — its rows carry ``alpha``
NULL (a stuffed placeholder would be dishonest provenance; the 0028 rationale verbatim). The
AR1_ESTIMATED convention (OD-DS-2-A) persists its Bartlett band on the DESMOOTHING_SUMMARY row in
the NEW nullable ``alpha_stderr`` column — DB-guarded summary-only by the CHECK (the 0028
DB-enforced-invariant precedent: the constraint element, not binder discipline alone). ADDITIVE on
the IA append-only table: no row changes, no RLS/trigger/grain change; the DECLARED convention's
binder keeps writing a NOT-NULL alpha (its discipline moves to the binder, where it always lived
semantically).

``alpha_stderr`` is EXCLUDED from the pin serializer (the 0038/0040 false-drift landmine — adding
a key falsifies historical pins); the EXISTING ``alpha`` pin key is None-tolerant for OW rows only
(the 0028 None-tolerance precedent; existing pins byte-identical).

No new audit code, permission, or entity. ``audit/service.py`` FROZEN.

Revision ID: 0042_desmoothing_estimated_alpha
Revises: 0041_es_historical
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_desmoothing_estimated_alpha"
down_revision: str | None = "0041_es_historical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_NAME = "stderr_summary_only"  # convention expands to ck_desmoothed_return_result_...
assert len(f"ck_desmoothed_return_result_{_CHECK_NAME}") <= 63  # the PG identifier cap


def upgrade() -> None:
    op.alter_column(
        "desmoothed_return_result",
        "alpha",
        existing_type=sa.Numeric(20, 12),
        nullable=True,
    )
    op.add_column(
        "desmoothed_return_result",
        sa.Column("alpha_stderr", sa.Numeric(20, 12), nullable=True),
    )
    # The band lives on the SUMMARY row only — DB-enforced (the 0028 review-forced CHECK
    # element carried forward; verifier U7).
    op.create_check_constraint(
        _CHECK_NAME,
        "desmoothed_return_result",
        "alpha_stderr IS NULL OR metric_type = 'DESMOOTHING_SUMMARY'",
    )


def downgrade() -> None:
    # OW rows (alpha IS NULL) are UNREPRESENTABLE in the pre-0042 schema (NOT NULL alpha): the
    # downgrade REMOVES them — the 0028 destructive precedent verbatim. The P0001 append-only
    # trigger protects business mutation, not migrations, and is disabled around the delete;
    # FORCE RLS is ALSO disabled (the 0028 three-finder lesson: the tenant policy binds even the
    # table OWNER, so a non-superuser migration role would otherwise silently delete ZERO rows
    # and the SET NOT NULL would abort midway — proven live at 0041 under an owner-via-membership
    # role). Both toggles are transactional (env.py wraps the migration in one transaction).
    # Delete BEFORE the NOT-NULL re-tighten (PG validates existing rows at ALTER time).
    op.drop_constraint(_CHECK_NAME, "desmoothed_return_result", type_="check")
    op.drop_column("desmoothed_return_result", "alpha_stderr")
    op.execute(
        "ALTER TABLE desmoothed_return_result DISABLE TRIGGER desmoothed_return_result_append_only"
    )
    op.execute("ALTER TABLE desmoothed_return_result DISABLE ROW LEVEL SECURITY")
    op.execute("DELETE FROM desmoothed_return_result WHERE alpha IS NULL")
    op.execute("ALTER TABLE desmoothed_return_result ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE desmoothed_return_result FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE desmoothed_return_result ENABLE TRIGGER desmoothed_return_result_append_only"
    )
    op.alter_column(
        "desmoothed_return_result",
        "alpha",
        existing_type=sa.Numeric(20, 12),
        nullable=False,
    )
