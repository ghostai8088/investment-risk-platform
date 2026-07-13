"""PA-3: proxy_weight_estimate_result (ENT-057 — the twelfth governed number) + the
``proxy_mapping.source_calculation_run_id`` promotion-provenance column.

ONE tenant-scoped PROPRIETARY IA table under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own-tenant``) — the 0009..0036 pattern; NOT hybrid, no SYSTEM_TENANT.

- ``proxy_weight_estimate_result`` (ENT-057, **IA TRUE append-only**) — the OLS regression of a
  private instrument's DESMOOTHED appraisal return series (a consumed ``DESMOOTHED_RETURN`` run's
  output) on the candidate public factor returns: one ``WEIGHT`` row per candidate factor
  (estimated coefficient + its standard error), one ``INTERCEPT`` row, one ``ESTIMATION_SUMMARY``
  row (R², n_observations, n_regressors, residual stdev). Run-bound + snapshot-gated + model-bound
  (NOT-NULL FKs) + provenance FKs to the measured subject (``portfolio_id``/``instrument_id``) and
  to the consumed desmoothed run (``source_desmoothed_run_id``). ``factor_id`` is set on ``WEIGHT``
  rows (FK ``factor``) and NULL on the two singleton rows. In ``APPEND_ONLY_TABLES`` -> the
  ``irp_prevent_mutation`` P0001 trigger (reusing the 0001 function) + the ORM guard.

- ``proxy_mapping.source_calculation_run_id`` (additive, NULLABLE) — the PROMOTION evidence edge
  (OD-PA-3-E): a ``REGRESSION``-method captured proxy weight cites the estimation run it came from;
  ``MANUAL`` captures leave it NULL. FK to ``calculation_run.run_id``. No RLS/policy change
  (``proxy_mapping`` already carries the symmetric loop from 0034).

No new audit code (``RISK.PROXY_WEIGHT_ESTIMATE_CREATE`` RESERVED, not minted; the run reuses
``CALC.RUN_*``; promotion reuses ``MARKET.PROXY_MAPPING_*``); NO new permission (``risk.run``/
``risk.view`` REUSED). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG. Every DDL identifier
<= 63 chars (asserted below — the 0032/0033 lesson).

Revision ID: 0037_proxy_weight_estimate
Revises: 0036_desmoothed_return
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_proxy_weight_estimate"
down_revision: str | None = "0036_desmoothed_return"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("proxy_weight_estimate_result",)
#: Truly immutable append-only (a re-run is a new run + new rows).
APPEND_ONLY_TABLES = ("proxy_weight_estimate_result",)

#: Every name this migration mints, checked at import time (the 0032/0033 lesson; the MD-H1
#: repo-wide sweep also validates it — belt and braces).
_IDENTIFIERS = (
    "proxy_weight_estimate_result",
    "pk_proxy_weight_estimate_result",
    "fk_proxy_weight_estimate_result_calc_run",
    "fk_proxy_weight_estimate_result_input_snapshot",
    "fk_proxy_weight_estimate_result_model_version",
    "fk_proxy_weight_estimate_result_portfolio",
    "fk_proxy_weight_estimate_result_instrument",
    "fk_proxy_weight_estimate_result_source_run",
    "uq_proxy_weight_estimate_result_run_grain",
    "ix_proxy_weight_estimate_result_tenant_id",
    "ix_proxy_weight_estimate_result_calculation_run_id",
    "ix_proxy_weight_estimate_result_input_snapshot_id",
    "ix_proxy_weight_estimate_result_model_version_id",
    "ix_proxy_weight_estimate_result_portfolio_id",
    "ix_proxy_weight_estimate_result_instrument_id",
    "tenant_isolation_proxy_weight_estimate_result",
    "proxy_weight_estimate_result_append_only",
    "fk_proxy_mapping_source_calculation_run_id_calculation_run",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "proxy_weight_estimate_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        #: The consumed DESMOOTHED_RETURN run whose series was regressed (provenance echo).
        sa.Column("source_desmoothed_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        #: WEIGHT (per candidate factor) | INTERCEPT (once) | ESTIMATION_SUMMARY (once).
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        #: The candidate factor for a WEIGHT row; NULL on INTERCEPT / ESTIMATION_SUMMARY.
        sa.Column("factor_id", postgresql.UUID(as_uuid=False), nullable=True),
        #: WEIGHT/INTERCEPT: the estimated coefficient. ESTIMATION_SUMMARY: the R^2.
        sa.Column("metric_value", sa.Numeric(precision=20, scale=12), nullable=False),
        #: WEIGHT/INTERCEPT: the coefficient's standard error (the honest-uncertainty statement).
        sa.Column("std_error", sa.Numeric(precision=20, scale=12), nullable=True),
        #: ESTIMATION_SUMMARY evidence (NULL on WEIGHT/INTERCEPT rows).
        sa.Column("n_observations", sa.Integer(), nullable=True),
        sa.Column("n_regressors", sa.Integer(), nullable=True),
        sa.Column("residual_stdev", sa.Numeric(precision=20, scale=12), nullable=True),
        #: The DECLARED minimum-observations floor (model identity), echoed on EVERY row.
        sa.Column("min_observations", sa.Integer(), nullable=False),
        #: The regressed series' currency (echoed evidence; single-currency in v1).
        sa.Column("series_currency", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_proxy_weight_estimate_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_proxy_weight_estimate_result_calc_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_proxy_weight_estimate_result_input_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_proxy_weight_estimate_result_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_proxy_weight_estimate_result_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_proxy_weight_estimate_result_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["source_desmoothed_run_id"],
            ["calculation_run.run_id"],
            name="fk_proxy_weight_estimate_result_source_run",
        ),
        #: ``factor_id`` is deliberately NOT a hard FK — the EV ``factor`` head is supersedable
        #: in place and the pinned ``COMPONENT_KIND_FACTOR`` component is the authoritative version
        #: (the ``factor_exposure_result`` precedent).
        #: The constraint DB-enforces WEIGHT-row uniqueness per factor (a duplicate coefficient is
        #: rejected). The INTERCEPT/ESTIMATION_SUMMARY singletons carry a NULL factor_id — PG treats
        #: NULLs as distinct in a UNIQUE, so their one-per-run property is guaranteed by CODE
        #: (``_compute`` emits exactly one each) + the append-only trigger (no post-hoc insert into a
        #: committed run), NOT by this constraint. A partial unique index WHERE factor_id IS NULL is
        #: the recorded defense-in-depth option (deferred — not reachable through the governed run).
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "factor_id",
            name="uq_proxy_weight_estimate_result_run_grain",
        ),
    )
    op.create_index(
        "ix_proxy_weight_estimate_result_tenant_id",
        "proxy_weight_estimate_result",
        ["tenant_id"],
    )
    op.create_index(
        "ix_proxy_weight_estimate_result_calculation_run_id",
        "proxy_weight_estimate_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_proxy_weight_estimate_result_input_snapshot_id",
        "proxy_weight_estimate_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_proxy_weight_estimate_result_model_version_id",
        "proxy_weight_estimate_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_proxy_weight_estimate_result_portfolio_id",
        "proxy_weight_estimate_result",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_proxy_weight_estimate_result_instrument_id",
        "proxy_weight_estimate_result",
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

    # --- Additive promotion-provenance edge on proxy_mapping (nullable; no RLS change).
    op.add_column(
        "proxy_mapping",
        sa.Column("source_calculation_run_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_proxy_mapping_source_calculation_run_id_calculation_run",
        "proxy_mapping",
        "calculation_run",
        ["source_calculation_run_id"],
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_proxy_mapping_source_calculation_run_id_calculation_run",
        "proxy_mapping",
        type_="foreignkey",
    )
    op.drop_column("proxy_mapping", "source_calculation_run_id")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("proxy_weight_estimate_result")
