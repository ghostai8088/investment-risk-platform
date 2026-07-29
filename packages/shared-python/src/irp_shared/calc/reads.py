"""Shared entity/time-centric read helpers for governed results (API-1, OD-API-1-A/G).

Read-only query utilities factoring the CC-2 pacing read pattern (the platform's FIRST
latest-resolver, ``pacing/service.py`` ``list_pacing_projections``/``latest_pacing_projection``)
so the API-1 back-fill replicates it across the entity-native governed families WITHOUT copy-paste.
**Read-only** — NO writes, NO run creation; the governed-run scaffold (``calc/scaffold.py``) and the
run-id reads are untouched. Entity reads are purely ADDITIVE; reproducibility-by-run-pin (TR-09) is
the governed contract and does not move.

The pattern: join ``CalculationRun`` on the result's ``calculation_run_id``, filter to the acting
tenant + COMPLETED runs (FAILED runs have zero rows, so COMPLETED-filtering hides nothing readable),
apply the entity equality filter(s) + an optional ``as_of`` run cutoff (``CalculationRun.system_from
<= as_of``), and TOTALLY order (``system_from`` DESC, ``run_id`` DESC, the intra-run grain ASC) so
``latest_run_rows`` can take the newest run deterministically. Silent-empty on an unknown/foreign id
(the positions/valuations entity-filter precedent).

Typing note: ``model``/``order_by`` are ``Any`` (a SQLAlchemy mapped class + a column expr — mypy
cannot bind the column descriptors through a generic here); the CONCRETE element type is preserved
at each family's own typed wrapper (e.g. ``list_pacing_projections`` returns
``list[PacingProjectionResult]``), which is where callers get their static safety.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import String, select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus


def _bind_at_column_type(column: Any, value: object) -> object:
    """Bind a filter value at the COLUMN's type instead of blindly as text.

    **Wave-13 close fold — a shipped HIGH.** This helper used to be an unconditional ``str(value)``
    inline in the filter loop. That was invisible for eight waves because every caller filtered a
    UUID- or String-typed column, where the coercion is a no-op. RM-1 and SR-1 were the FIRST to
    route an ``Integer`` column (``window_months``) through this seam, and SQLAlchemy types a bind
    parameter from the PYTHON value, not from the column — so the query went to PostgreSQL as
    ``window_months = $1::VARCHAR`` and the server refused it:

        ProgrammingError: operator does not exist: integer = character varying

    i.e. ``GET /perf/rolling-risk?window_months=…`` and the three sibling endpoints returned 500 on
    the production database. **The unit tier could not see it**: SQLite applies INTEGER column
    affinity and silently converts ``'12'`` -> ``12``, so the two tests written specifically for
    this filter passed against the engine the platform does not run on. That is why the regression
    pin lives in the PG tier (``test_rolling_risk_pg`` / ``test_sharpe_pg``) — a unit-tier test
    here would be structurally incapable of failing.

    The coercion is kept for string-typed columns because callers legitimately pass ``uuid.UUID``
    objects and stringly-typed ids there; it is dropped everywhere else so the value keeps the type
    the column expects. ``Text``/``Unicode``/``Enum`` all subclass ``String``, so they coerce too.
    """
    return str(value) if isinstance(column.type, String) else value


def list_governed_results(
    session: Session,
    model: Any,
    *,
    acting_tenant: str,
    filters: Iterable[tuple[Any, object | None]] = (),
    run_type: str | None = None,
    as_of: datetime | None = None,
    order_by: Any,
) -> list[Any]:
    """Entity/time-centric read of ONE governed-result family (the CC-2 pacing pattern, factored).

    ``model`` MUST carry ``calculation_run_id`` + ``tenant_id`` (the run-bound trio — every governed
    result does). ``filters`` are ``(column, value)`` pairs applied ONLY when ``value`` is not None
    (an absent filter widens; a foreign id yields silent-empty), each bound at its COLUMN's type via
    ``_bind_at_column_type`` — see that helper for why a blanket ``str()`` was a shipped 500 on
    PostgreSQL that the SQLite unit tier could not detect. ``run_type`` filters
    the joined ``CalculationRun.run_type`` — REQUIRED to disambiguate families that SHARE a result
    table (es-backtest + var-backtest share ``var_backtest_result``, distinguished by run_type).
    ``as_of`` is a run ``system_from`` cutoff (None = now). ``order_by`` is the intra-run grain
    column — a single column OR an iterable of columns (all applied ASC after the run ordering, so
    a composite grain like covariance ``(factor_id_1, factor_id_2)`` presents canonically).
    COMPLETED runs only.
    """
    stmt = (
        select(model)
        .join(CalculationRun, CalculationRun.run_id == model.calculation_run_id)
        .where(
            model.tenant_id == str(acting_tenant),
            CalculationRun.status == RunStatus.COMPLETED.value,
        )
    )
    if run_type is not None:
        stmt = stmt.where(CalculationRun.run_type == run_type)
    for column, value in filters:
        if value is not None:
            stmt = stmt.where(column == _bind_at_column_type(column, value))
    if as_of is not None:
        stmt = stmt.where(CalculationRun.system_from <= as_of)
    grain = order_by if isinstance(order_by, list | tuple) else (order_by,)
    stmt = stmt.order_by(
        CalculationRun.system_from.desc(),
        CalculationRun.run_id.desc(),
        *(column.asc() for column in grain),
    )
    return list(session.execute(stmt).scalars().all())


def latest_run_rows(rows: Sequence[Any]) -> list[Any]:
    """Given run-DESC-ordered rows from :func:`list_governed_results`, keep ONLY the newest run's
    rows — the latest-resolver ("current" = the latest COMPLETED run across all model versions;
    empty when none). ONE code path over the list (the CC-2 ``latest_pacing_projection`` contract);
    cross-run aggregation is a CONSUMER ERROR."""
    if not rows:
        return []
    latest_run_id = rows[0].calculation_run_id  # rows are run-DESC ordered; the first is newest
    return [r for r in rows if r.calculation_run_id == latest_run_id]
