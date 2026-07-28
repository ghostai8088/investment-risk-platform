"""SR-1: sharpe_ratio_result (ENT-065 — the TWENTY-SECOND governed number).

``sharpe_ratio_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — as in 0009..0054. NOT hybrid,
no SYSTEM_TENANT (the closed 5-table hybrid set is unchanged). **TRULY IMMUTABLE / append-only**:
the ``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function), paired with the ORM
before_update/before_delete guard. Run-bound + snapshot-gated + model-bound, plus hard FKs to the
ONE upstream PM-1 ``PORTFOLIO_RETURN`` run consumed, the measured book, and the risk-free benchmark
head.

**Why a NEW entity rather than an ENT-064 column** (OD-SR-1-C, ratified): a Sharpe row carries
``risk_free_benchmark_id`` provenance that a rolling-risk row has no meaning for. Extending ENT-064
would put a NULLABLE provenance column on every existing rolling-risk row — a stuffed placeholder
by another name (the 0028 doctrine) — and leave one table holding rows with two different
provenance shapes. Every perf family that differs in provenance got its own entity
(ENT-053/054/056/064).

**RM-1's two departures are inherited deliberately:**

1. **A FOUR-column grain** ``(calculation_run_id, metric_type, window_months, period_start)``. SR-1
   emits the same statistic at two windows, which collides under the sibling three-column grain —
   producing an ``IntegrityError`` at flush (a 500 inside the emit path) rather than a governed
   refusal. ``window_months`` is **NOT NULL**: a nullable window would constrain NOTHING on
   PostgreSQL (``NULL != NULL`` in a UNIQUE constraint).
2. **A NULLABLE ``metric_value`` + an explicit ``suppressed`` flag.** **Zero is a legitimate Sharpe
   ratio** — a book that exactly earns the risk-free rate over the window scores 0 — so a stuffed
   zero would be indistinguishable from "not computable", and a consumer would read the latter as
   "earned nothing above cash" rather than "we could not compute this". The CHECK below is a TOTAL
   enumeration over the boolean (the 0042/0054 precedent), so ``suppression_reason IS NOT NULL`` is
   enforced iff suppressed and no third state passes vacuously.

Unlike ENT-064, this family also stores ``rf_return_basis`` — the risk-free series' PRICE / TOTAL /
NET_TOTAL basis echoed on every row (the ENT-054 precedent). The benchmark head alone does not
identify a series: one head can publish all three bases, and two Sharpe runs against the same head
on different bases are different governed numbers.

No schema change for ``COMPONENT_KIND_*`` / ``PURPOSE_SHARPE_INPUT`` (unconstrained strings — app
constants; the purpose joins the allow-list in application code, which SR-1 also moves INTO
``_persist_snapshot`` so it is enforcement rather than convention). No new audit code (the run
reuses ``CALC.RUN_*``; ``PERF.*`` stays RESERVED-not-minted). ``PreciseDecimal`` renders
``NUMERIC(p,s)`` on PG — ``alembic check`` no-op. Every DDL identifier is <= 63 chars (asserted at
import). Downgrade is honestly destructive: it drops the trigger, the policy, and the table with
every Sharpe row.

Revision ID: 0055_sharpe_ratio_result
Revises: 0054_rolling_risk_result
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_sharpe_ratio_result"
down_revision: str | None = "0054_rolling_risk_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("sharpe_ratio_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("sharpe_ratio_result",)

#: The suppression CHECK — a TOTAL enumeration over the boolean, so there is no third state that
#: passes vacuously (the SCH-2 lesson: the implication form fails OPEN for unenumerated values).
#:
#: **The SUFFIX only, on BOTH sides.** `env.py` passes `target_metadata`, so `op.create_table` DOES
#: apply the `ck_%(table_name)s_%(constraint_name)s` convention here — passing the full name mints a
#: doubled, 63-char-truncated, hash-suffixed name that silently DRIFTS from the ORM's, and
#: `alembic check` does NOT compare CHECK constraints, so the drift gate is blind to it. Verified by
#: applying the migration and reading `pg_constraint` back (the RM-1 lesson, inherited on day one).
_CHECK_SUPPRESSION = "suppression_coherent"

#: Every name this migration mints, checked at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "sharpe_ratio_result",
    "pk_sharpe_ratio_result",
    "fk_sharpe_ratio_result_calc_run",
    "fk_sharpe_ratio_result_input_snapshot",
    "fk_sharpe_ratio_result_model_version",
    "fk_sharpe_ratio_result_portfolio",
    "fk_sharpe_ratio_result_portfolio_return_run",
    "fk_sharpe_ratio_result_risk_free_benchmark",
    "uq_sharpe_ratio_result_run_grain",
    f"ck_sharpe_ratio_result_{_CHECK_SUPPRESSION}",
    "ix_sharpe_ratio_result_tenant_id",
    "ix_sharpe_ratio_result_calculation_run_id",
    "ix_sharpe_ratio_result_input_snapshot_id",
    "ix_sharpe_ratio_result_model_version_id",
    "ix_sharpe_ratio_result_portfolio_id",
    "ix_sharpe_ratio_result_portfolio_return_run_id",
    "ix_sharpe_ratio_result_risk_free_benchmark_id",
    "tenant_isolation_sharpe_ratio_result",
    "sharpe_ratio_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "sharpe_ratio_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        # Run-bound + snapshot-gated + model-bound (AD-014 / FW-RUN / TR-15 / CTRL-003 at the DB).
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The measured book.
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The ONE upstream PM-1 PORTFOLIO_RETURN run whose DIETZ_PERIOD series this consumes.
        sa.Column("portfolio_return_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The captured risk-free series' head. NOT NULL: a Sharpe row that cannot say what it was
        # measured against is not evidence of anything.
        sa.Column("risk_free_benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        # PRICE | TOTAL | NET_TOTAL — echoed per row (the head alone does not identify the series).
        sa.Column("rf_return_basis", sa.String(length=20), nullable=False),
        # Controlled vocab (plain String, extended by value — never silently).
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        # The trailing window in MONTHS.
        sa.Column("window_months", sa.Integer(), nullable=False),
        # The window's economic span, in valuation dates.
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        # The number: a RATIO at the shared Numeric(20,12) scale — not a fraction of anything, and
        # not currency. NULLABLE, and that nullability is the whole point (see the docstring).
        sa.Column("metric_value", sa.Numeric(precision=20, scale=12), nullable=True),
        # Suppression as a FIRST-CLASS governed state, never inferred from a sentinel value.
        sa.Column("suppressed", sa.Boolean(), nullable=False),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        # NONE on the raw ratio, SQRT_12 on the annualized one. NOT NULL on every row — the read
        # surface's disambiguation key is (metric_type, window_months, annualization_basis).
        sa.Column("annualization_basis", sa.String(length=20), nullable=False),
        # The sampling frequency the statistic was computed at (MONTHLY in v1). A Sharpe ratio that
        # does not carry its frequency cannot be honestly compared with any other.
        sa.Column("sampling_frequency", sa.String(length=10), nullable=False),
        # Observations inside the window (NULL when suppressed — there is no sample).
        sa.Column("n_observations", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sharpe_ratio_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_sharpe_ratio_result_calc_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_sharpe_ratio_result_input_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_sharpe_ratio_result_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name="fk_sharpe_ratio_result_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_return_run_id"],
            ["calculation_run.run_id"],
            name="fk_sharpe_ratio_result_portfolio_return_run",
        ),
        sa.ForeignKeyConstraint(
            ["risk_free_benchmark_id"],
            ["benchmark.id"],
            name="fk_sharpe_ratio_result_risk_free_benchmark",
        ),
        # THE FOUR-COLUMN GRAIN — three columns cannot carry two windows (the RM-1 precedent).
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "window_months",
            "period_start",
            name="uq_sharpe_ratio_result_run_grain",
        ),
        # TOTAL enumeration over `suppressed`: a suppressed row has NO value and MUST say why; an
        # emitted row has a value and MUST NOT carry a reason. Written as the two-sided form rather
        # than an implication so no third state passes vacuously.
        sa.CheckConstraint(
            "(suppressed = true AND metric_value IS NULL AND suppression_reason IS NOT NULL)"
            " OR (suppressed = false AND metric_value IS NOT NULL"
            " AND suppression_reason IS NULL)",
            name=_CHECK_SUPPRESSION,  # SUFFIX ONLY — see the constant's note above.
        ),
    )
    op.create_index("ix_sharpe_ratio_result_tenant_id", "sharpe_ratio_result", ["tenant_id"])
    for column in (
        "calculation_run_id",
        "input_snapshot_id",
        "model_version_id",
        "portfolio_id",
        "portfolio_return_run_id",
        "risk_free_benchmark_id",
    ):
        op.create_index(f"ix_sharpe_ratio_result_{column}", "sharpe_ratio_result", [column])

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17).
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: truly immutable IA table (BR-12/BR-18 / AUD-01), reuse the 0001 function.
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    # Honestly destructive: drops every Sharpe row (IA governed evidence). The table itself is
    # dropped, and DROP TABLE is not a row mutation, so the append-only trigger never fires.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("sharpe_ratio_result")
