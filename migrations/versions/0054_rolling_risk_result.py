"""RM-1: rolling_risk_result (ENT-064 — the TWENTY-FIRST governed number).

``rolling_risk_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — as in 0009..0053. NOT hybrid, no
SYSTEM_TENANT (the closed 5-table hybrid set is unchanged). **TRULY IMMUTABLE / append-only**: the
``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function), paired with the ORM
before_update/before_delete guard. Run-bound + snapshot-gated + model-bound, plus a hard FK to the
ONE upstream PM-1 ``PORTFOLIO_RETURN`` run it consumes (``portfolio_return_run_id`` — the
P3-8/BT-1/PA-3 single-upstream precedent).

**Two deliberate DEPARTURES from the sibling perf families, both ratified:**

1. **A FOUR-column grain** ``(calculation_run_id, metric_type, window_months, period_start)``
   (OD-RM-1-J). The sibling three-column grain is *insufficient*, not merely tighter: RM-1 emits the
   same statistic at two windows, which collides under every ``period_start`` convention — producing
   an ``IntegrityError`` at flush, i.e. a 500 inside the emit path rather than a governed refusal.
   The window must NOT be folded into ``metric_type`` instead: ``ROLLING_VOLATILITY_ANNUALIZED_36M``
   is 33 characters against a ``String(30)`` column. ``window_months`` is **NOT NULL** with an
   explicit ``0`` sentinel for run-summary rows — a nullable window would constrain NOTHING on
   PostgreSQL (``NULL != NULL`` in a UNIQUE constraint).

2. **A NULLABLE ``metric_value`` + an explicit ``suppressed`` flag** (OD-RM-1-I). Every sibling
   family has a NOT-NULL value column, which here would force a stuffed ``0.000000000000`` — and
   **zero is a legitimate governed value for all three metrics** (a monotonically rising window has
   ``MDD = 0``; identical months give ``sigma = 0``). A suppressed row and a genuine zero would be
   indistinguishable on the read surface, and a naive consumer would read "not computable" as "no
   drawdown, excellent". The family's own doctrine forbids exactly this ("a stuffed placeholder
   would be dishonest provenance" — ``perf/models.py``, the 0028 rationale). The DB CHECK below is a
   TOTAL enumeration over the boolean, so it also enforces ``suppression_reason IS NOT NULL`` iff
   suppressed — the 0042 CHECK precedent.

No schema change for ``COMPONENT_KIND_*`` / ``PURPOSE_ROLLING_RISK_INPUT`` (unconstrained strings —
app constants; the purpose joins the ENFORCED ``SNAPSHOT_PURPOSES`` allow-list in application code).
No new audit code (the run reuses ``CALC.RUN_*``; ``PERF.*`` stays RESERVED-not-minted).
``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — ``alembic check`` no-op. Every DDL identifier is
<= 63 chars (asserted at import — the P3-8/BT-1 lesson). Downgrade is honestly destructive: it
drops the trigger, the policy, and the table with every rolling-risk row.

Revision ID: 0054_rolling_risk_result
Revises: 0053_schedule_cadence_family
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_rolling_risk_result"
down_revision: str | None = "0053_schedule_cadence_family"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("rolling_risk_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("rolling_risk_result",)

#: The suppression CHECK — a TOTAL enumeration over the boolean, so there is no third state that
#: passes vacuously (the SCH-2 lesson: the implication form fails OPEN for unenumerated values).
_CHECK_SUPPRESSION = "suppression_coherent"

#: Every name this migration mints, checked at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "rolling_risk_result",
    "pk_rolling_risk_result",
    "fk_rolling_risk_result_calc_run",
    "fk_rolling_risk_result_input_snapshot",
    "fk_rolling_risk_result_model_version",
    "fk_rolling_risk_result_portfolio",
    "fk_rolling_risk_result_portfolio_return_run",
    "uq_rolling_risk_result_run_grain",
    f"ck_rolling_risk_result_{_CHECK_SUPPRESSION}",
    "ix_rolling_risk_result_tenant_id",
    "ix_rolling_risk_result_calculation_run_id",
    "ix_rolling_risk_result_input_snapshot_id",
    "ix_rolling_risk_result_model_version_id",
    "ix_rolling_risk_result_portfolio_id",
    "ix_rolling_risk_result_portfolio_return_run_id",
    "tenant_isolation_rolling_risk_result",
    "rolling_risk_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "rolling_risk_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        # Run-bound + snapshot-gated + model-bound (AD-014 / FW-RUN / TR-15 / CTRL-003 at the DB).
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The measured book.
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The ONE upstream PM-1 PORTFOLIO_RETURN run whose DIETZ_PERIOD series this consumes. A hard
        # FK because there is exactly one (unlike PM-1's variable-N boundary runs, whose provenance
        # can only live in the pinned atoms).
        sa.Column("portfolio_return_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        # Controlled vocab (plain String, extended by value — never silently).
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        # The trailing window in MONTHS. 0 = a run-summary row (the explicit sentinel; see the
        # module docstring on why this cannot be NULL).
        sa.Column("window_months", sa.Integer(), nullable=False),
        # The window's economic span, in valuation dates.
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        # The number: a FRACTION at the Numeric(20,12) return scale, NOT currency. NULLABLE — and
        # that nullability is the whole point of the suppression design (see the docstring).
        sa.Column("metric_value", sa.Numeric(precision=20, scale=12), nullable=True),
        # Suppression as a FIRST-CLASS governed state, never inferred from a sentinel value.
        sa.Column("suppressed", sa.Boolean(), nullable=False),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        # Which annualization transform produced this row: NONE | SQRT_12 | GEOMETRIC_12. NOT NULL
        # on every row — the read surface's disambiguation key is
        # (metric_type, window_months, annualization_basis), so a NULL here would make two governed
        # numbers indistinguishable to a consumer (OD-RM-1-K).
        sa.Column("annualization_basis", sa.String(length=20), nullable=False),
        # The sampling frequency the statistic was computed at. MDD in particular is
        # frequency-dependent and downward-biased by discretisation
        # (sup(subset) <= sup(superset)), so a row that does not carry its frequency cannot be
        # honestly compared with any other.
        sa.Column("sampling_frequency", sa.String(length=10), nullable=False),
        # Observations inside the window (NULL when suppressed — there is no sample).
        sa.Column("n_observations", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_risk_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_rolling_risk_result_calc_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_rolling_risk_result_input_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_rolling_risk_result_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name="fk_rolling_risk_result_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_return_run_id"],
            ["calculation_run.run_id"],
            name="fk_rolling_risk_result_portfolio_return_run",
        ),
        # THE FOUR-COLUMN GRAIN (OD-RM-1-J) — three columns cannot carry two windows.
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "window_months",
            "period_start",
            name="uq_rolling_risk_result_run_grain",
        ),
        # TOTAL enumeration over `suppressed`: a suppressed row has NO value and MUST say why; an
        # emitted row has a value and MUST NOT carry a reason. Written as the two-sided form rather
        # than an implication so no third state passes vacuously.
        sa.CheckConstraint(
            "(suppressed = true AND metric_value IS NULL AND suppression_reason IS NOT NULL)"
            " OR (suppressed = false AND metric_value IS NOT NULL"
            " AND suppression_reason IS NULL)",
            # The SUFFIX only. `env.py` passes `target_metadata`, so `op.create_table` DOES apply
            # the `ck_%(table_name)s_%(constraint_name)s` convention here — passing the full name
            # mints `ck_rolling_risk_result_ck_rolling_risk_result_suppressi_075e` (doubled, then
            # truncated to 63 chars with a hash suffix) which silently DRIFTS from the ORM's name.
            # `alembic check` does NOT compare CHECK constraints, so the drift gate is blind to it;
            # caught by applying the migration and reading `pg_constraint` back.
            name=_CHECK_SUPPRESSION,
        ),
    )
    op.create_index("ix_rolling_risk_result_tenant_id", "rolling_risk_result", ["tenant_id"])
    for column in (
        "calculation_run_id",
        "input_snapshot_id",
        "model_version_id",
        "portfolio_id",
        "portfolio_return_run_id",
    ):
        op.create_index(f"ix_rolling_risk_result_{column}", "rolling_risk_result", [column])

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
    # Honestly destructive: drops every rolling-risk row (IA governed evidence). Unlike 0053's
    # two-table cascade this needs no trigger/RLS sandwich — the table itself is dropped, and
    # DROP TABLE is not a row mutation, so the append-only trigger never fires.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("rolling_risk_result")
