"""Read-only risk-run listing (FE-1, OD-FE-1-C — the runs-view's one backend addition).

One tenant-scoped query over ``calculation_run`` restricted to the risk run families —
the ``risk.view`` permission's honest scope (exposure runs are gated by ``exposure.view`` and
are a recorded follow-up, never silently mixed in). Filters fail CLOSED: an unknown
``run_type``/``status`` or an out-of-bounds page is a refusal (422 at the router), never a
silently-empty page. Ordering is deterministic (``created_at DESC, run_id``) so offset
pagination cannot shuffle rows between pages. Read-only ⇒ NO audit emission (the standing GET
precedent) and NO mutation of any kind.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.risk.events import (
    RUN_TYPE_ACTIVE_RISK,
    RUN_TYPE_COVARIANCE,
    RUN_TYPE_FACTOR_EXPOSURE,
    RUN_TYPE_SCENARIO,
    RUN_TYPE_SENSITIVITY,
    RUN_TYPE_VAR,
    RUN_TYPE_VAR_BACKTEST,
)

#: The closed set this listing may surface (OD-FE-1-C). Exposure runs are OUT.
RISK_RUN_TYPES: frozenset[str] = frozenset(
    {
        RUN_TYPE_SENSITIVITY,
        RUN_TYPE_FACTOR_EXPOSURE,
        RUN_TYPE_COVARIANCE,
        RUN_TYPE_VAR,
        RUN_TYPE_ACTIVE_RISK,
        RUN_TYPE_VAR_BACKTEST,
        RUN_TYPE_SCENARIO,
    }
)

_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in RunStatus)

LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200


class RiskRunQueryError(ValueError):
    """A fail-closed listing refusal (unknown filter / out-of-bounds page) — 422, never a guess."""


def list_risk_runs(
    session: Session,
    *,
    acting_tenant: str,
    run_type: str | None = None,
    status: str | None = None,
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
) -> list[CalculationRun]:
    """List the acting tenant's risk runs, newest first. RLS is the enforcement; the explicit
    tenant predicate is the belt-and-braces house pattern."""
    if run_type is not None and run_type not in RISK_RUN_TYPES:
        raise RiskRunQueryError(
            f"run_type must be one of {sorted(RISK_RUN_TYPES)}; got {run_type!r}"
        )
    if status is not None and status not in _STATUS_VALUES:
        raise RiskRunQueryError(f"status must be one of {sorted(_STATUS_VALUES)}; got {status!r}")
    if not 1 <= limit <= LIST_LIMIT_MAX:
        raise RiskRunQueryError(f"limit must be within 1..{LIST_LIMIT_MAX}; got {limit}")
    if offset < 0:
        raise RiskRunQueryError(f"offset must be >= 0; got {offset}")

    stmt = select(CalculationRun).where(
        CalculationRun.tenant_id == str(acting_tenant),
        CalculationRun.run_type.in_(sorted(RISK_RUN_TYPES) if run_type is None else [run_type]),
    )
    if status is not None:
        stmt = stmt.where(CalculationRun.status == status)
    stmt = (
        stmt.order_by(CalculationRun.created_at.desc(), CalculationRun.run_id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())
