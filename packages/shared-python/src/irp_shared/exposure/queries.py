"""Read-only exposure-run listing (P3-C2, OD-C — the exposure sibling of ``risk.queries``).

One tenant-scoped query over ``calculation_run`` restricted to the SINGLE ``EXPOSURE_AGGREGATE``
family — gated by ``exposure.view`` at the router (NOT ``risk.view``: the permission-family
separation the FE-1 review insisted on; ``risk.queries.list_risk_runs`` fences exposure OUT, this
one fences everything else out). Filters fail CLOSED (unknown ``status`` / out-of-bounds page ⇒
422); deterministic ``created_at DESC, run_id`` order; read-only ⇒ NO audit emission, NO
mutation. Mirrors ``risk.queries`` shape so the FE runs view can consume this endpoint through
the SAME row contract it uses for ``/risk/runs`` (the family selector source-switches between the
two endpoints — see the P3-C2 record Part 4.6; NOT a client-side merge).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE

_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in RunStatus)

LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200


class ExposureRunQueryError(ValueError):
    """A fail-closed listing refusal (unknown status / out-of-bounds page) — 422, never a guess."""


def list_exposure_runs(
    session: Session,
    *,
    acting_tenant: str,
    status: str | None = None,
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
) -> list[CalculationRun]:
    """List the acting tenant's EXPOSURE_AGGREGATE runs, newest first. RLS is the enforcement; the
    explicit tenant predicate is the belt-and-braces house pattern. There is no ``run_type``
    filter — this family is a singleton (the fence IS the run_type restriction)."""
    if status is not None and status not in _STATUS_VALUES:
        raise ExposureRunQueryError(
            f"status must be one of {sorted(_STATUS_VALUES)}; got {status!r}"
        )
    if not 1 <= limit <= LIST_LIMIT_MAX:
        raise ExposureRunQueryError(f"limit must be within 1..{LIST_LIMIT_MAX}; got {limit}")
    if offset < 0:
        raise ExposureRunQueryError(f"offset must be >= 0; got {offset}")

    stmt = select(CalculationRun).where(
        CalculationRun.tenant_id == str(acting_tenant),
        CalculationRun.run_type == RUN_TYPE_EXPOSURE_AGGREGATE,
    )
    if status is not None:
        stmt = stmt.where(CalculationRun.status == status)
    stmt = (
        stmt.order_by(CalculationRun.created_at.desc(), CalculationRun.run_id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())
