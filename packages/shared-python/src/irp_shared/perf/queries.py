"""Read-only performance-run listing (PM-1 — the runs-view's perf backend addition; the FE-1
``list_risk_runs`` sibling).

One tenant-scoped query over ``calculation_run`` restricted to the PERF run family (v1: only
``PORTFOLIO_RETURN``) — the ``perf.view`` permission's honest scope (risk/exposure runs are gated by
their OWN permission families and are never silently mixed in). Filters fail CLOSED: an unknown
``run_type``/``status`` or an out-of-bounds page is a refusal (422 at the router), never a
silently-empty page. Ordering is deterministic (``created_at DESC, run_id``) so offset pagination
cannot shuffle rows between pages. Read-only => NO audit emission and NO mutation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.perf.events import RUN_TYPE_BENCHMARK_RELATIVE, RUN_TYPE_PORTFOLIO_RETURN

#: The closed set this listing may surface (the perf families). Risk/exposure runs are OUT.
PERF_RUN_TYPES: frozenset[str] = frozenset({RUN_TYPE_PORTFOLIO_RETURN, RUN_TYPE_BENCHMARK_RELATIVE})

_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in RunStatus)

LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200


class PerfRunQueryError(ValueError):
    """A fail-closed listing refusal (unknown filter / out-of-bounds page) — 422, never a guess."""


def list_perf_runs(
    session: Session,
    *,
    acting_tenant: str,
    run_type: str | None = None,
    status: str | None = None,
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
) -> list[CalculationRun]:
    """List the acting tenant's performance runs, newest first. RLS is the enforcement; the explicit
    tenant predicate is the belt-and-braces house pattern."""
    if run_type is not None and run_type not in PERF_RUN_TYPES:
        raise PerfRunQueryError(
            f"run_type must be one of {sorted(PERF_RUN_TYPES)}; got {run_type!r}"
        )
    if status is not None and status not in _STATUS_VALUES:
        raise PerfRunQueryError(f"status must be one of {sorted(_STATUS_VALUES)}; got {status!r}")
    if not 1 <= limit <= LIST_LIMIT_MAX:
        raise PerfRunQueryError(f"limit must be within 1..{LIST_LIMIT_MAX}; got {limit}")
    if offset < 0:
        raise PerfRunQueryError(f"offset must be >= 0; got {offset}")

    stmt = select(CalculationRun).where(
        CalculationRun.tenant_id == str(acting_tenant),
        CalculationRun.run_type.in_(sorted(PERF_RUN_TYPES) if run_type is None else [run_type]),
    )
    if status is not None:
        stmt = stmt.where(CalculationRun.status == status)
    stmt = (
        stmt.order_by(CalculationRun.created_at.desc(), CalculationRun.run_id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())
