"""P3-C1: additive calculation_run.failure_reason (OD-P3-C1-C).

The human-readable reason a run FAILED, persisted at the FAILED transition so a later read can
answer WHY (previously shown once in the POST response and discarded — the GET endpoints
hardcoded None). NULLABLE + ADDITIVE on the status-mutable IA ``calculation_run`` (the
``environment_id`` precedent, migration 0018): no existing row changes, no RLS/trigger change,
no new table. The DQ rows remain the durable defect EVIDENCE; this column is
presentation-persistence.

No new audit code, permission, or entity. ``audit/service.py`` FROZEN.

Revision ID: 0027_run_failure_reason
Revises: 0026_var
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_run_failure_reason"
down_revision: str | None = "0026_var"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calculation_run", sa.Column("failure_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calculation_run", "failure_reason")
