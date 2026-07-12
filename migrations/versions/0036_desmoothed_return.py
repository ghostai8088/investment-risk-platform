"""PA-1: desmoothed_return_result (ENT-056 — the eleventh governed number).

ONE tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own-tenant``) — the 0009..0035 pattern; NOT hybrid, no SYSTEM_TENANT.

- ``desmoothed_return_result`` (ENT-056, **IA TRUE append-only**) — the Geltner AR(1) desmoothed
  return series of ONE (portfolio, instrument) appraisal mark window: ``n−1`` per-period
  ``DESMOOTHED_PERIOD`` rows + ONE ``DESMOOTHING_SUMMARY`` row (desmoothed vs observed stdev — the
  honest-uncertainty statement, OD-PA-1-C). In this migration's ``APPEND_ONLY_TABLES`` -> the
  ``irp_prevent_mutation`` P0001 trigger (reusing the 0001 function) + the ORM guard. Run-bound +
  snapshot-gated + model-bound (NOT-NULL FKs) + provenance FKs to the measured subject
  (``portfolio_id``/``instrument_id`` — the ENT-053 precedent).

No new audit code (``PERF.DESMOOTHED_RETURN_CREATE`` RESERVED, not minted; the run reuses
``CALC.RUN_*``); NO new permission (``perf.run``/``perf.view`` REUSED); no schema change for
``DESMOOTHING_INPUT`` (an unconstrained app-constant string; the pin flavor REUSES
``COMPONENT_KIND_VALUATION``). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG. Every DDL
identifier <= 63 chars (asserted below — the 0032/0033 lesson).

Revision ID: 0036_desmoothed_return
Revises: 0035_scenario
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_desmoothed_return"
down_revision: str | None = "0035_scenario"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("desmoothed_return_result",)
#: Truly immutable append-only (a re-run is a new run + new rows).
APPEND_ONLY_TABLES = ("desmoothed_return_result",)

#: Every name this migration mints, checked at import time (the 0032/0033 lesson; the MD-H1
#: repo-wide sweep also validates it — belt and braces).
_IDENTIFIERS = (
    "desmoothed_return_result",
    "pk_desmoothed_return_result",
    "fk_desmoothed_return_result_calculation_run_id_calculation_run",
    "fk_desmoothed_return_result_input_snapshot_id_dataset_snapshot",
    "fk_desmoothed_return_result_model_version_id_model_version",
    "fk_desmoothed_return_result_portfolio_id_portfolio",
    "fk_desmoothed_return_result_instrument_id_instrument",
    "uq_desmoothed_return_result_run_grain",
    "ix_desmoothed_return_result_tenant_id",
    "ix_desmoothed_return_result_calculation_run_id",
    "ix_desmoothed_return_result_input_snapshot_id",
    "ix_desmoothed_return_result_model_version_id",
    "ix_desmoothed_return_result_portfolio_id",
    "ix_desmoothed_return_result_instrument_id",
    "tenant_isolation_desmoothed_return_result",
    "desmoothed_return_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "desmoothed_return_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        #: DESMOOTHED_PERIOD (per consecutive-mark period) | DESMOOTHING_SUMMARY (once per run).
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        #: Per-period: the desmoothed return r_t. Summary: the desmoothed sample stdev.
        sa.Column("metric_value", sa.Numeric(precision=20, scale=12), nullable=False),
        #: Echoed consumed inputs (per-period rows; NULL on the summary) — auditable row-by-row.
        sa.Column("observed_return", sa.Numeric(precision=20, scale=12), nullable=True),
        sa.Column("begin_mark", sa.Numeric(28, 6), nullable=True),
        sa.Column("end_mark", sa.Numeric(28, 6), nullable=True),
        #: The DECLARED speed-of-adjustment (model identity), echoed on EVERY row as evidence.
        sa.Column("alpha", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("mark_currency", sa.String(length=3), nullable=False),
        #: Summary evidence (NULL on per-period rows) — the honest-uncertainty pair.
        sa.Column("observed_stdev", sa.Numeric(precision=20, scale=12), nullable=True),
        sa.Column("n_periods", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_desmoothed_return_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_desmoothed_return_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_desmoothed_return_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_desmoothed_return_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_desmoothed_return_result_portfolio_id_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_desmoothed_return_result_instrument_id_instrument",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "period_start",
            name="uq_desmoothed_return_result_run_grain",
        ),
    )
    op.create_index(
        "ix_desmoothed_return_result_tenant_id", "desmoothed_return_result", ["tenant_id"]
    )
    op.create_index(
        "ix_desmoothed_return_result_calculation_run_id",
        "desmoothed_return_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_desmoothed_return_result_input_snapshot_id",
        "desmoothed_return_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_desmoothed_return_result_model_version_id",
        "desmoothed_return_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_desmoothed_return_result_portfolio_id",
        "desmoothed_return_result",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_desmoothed_return_result_instrument_id",
        "desmoothed_return_result",
        ["instrument_id"],
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

    # --- Append-only (IA); reuse the 0001 irp_prevent_mutation function.
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
    op.drop_table("desmoothed_return_result")
