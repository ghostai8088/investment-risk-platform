"""Shared tenant-scoped calculation-run resolvers (RD-1 dedup, 2026-07-12).

Every governed-number family resolved a run by id with the SAME query — an EXPLICIT tenant +
``run_type`` predicate (fail-closed; RLS is the belt, this explicit predicate the braces), surfacing
a committed FAILED run rather than hiding it. That body had accumulated to ten near-verbatim
copies (eight ``resolve_*_run`` reads across risk + perf; two ``_resolve_run`` consumed-run
guards), meeting the P3-4-R0 3rd-consumer tipping rule. This module owns the one query; each
family keeps its own thin wrapper + its own exception type (the API error-maps depend on the
specific classes).

Two shapes:
- :func:`resolve_run_of_type` — the READ resolver (a family's ``resolve_*_run``); raises a
  caller-supplied ``*RunNotVisible`` built from the run_id.
- :func:`resolve_completed_run_of_type` — the pre-FK CONSUMED-run guard (adds a COMPLETED
  assertion; PG FK checks bypass RLS, the P3-5 finding); raises a caller-supplied input-error class.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus


def resolve_run_of_type(
    session: Session,
    run_id: str,
    *,
    acting_tenant: str,
    run_type: str,
    not_visible: Callable[[str], Exception],
) -> CalculationRun:
    """Resolve a ``calculation_run`` by id under an EXPLICIT tenant + ``run_type`` predicate
    (fail-closed; a committed FAILED run is surfaced, not hidden). Raises ``not_visible(run_id)``
    on a hidden/unknown id or a wrong-``run_type`` run."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == run_type,
        )
    ).scalar_one_or_none()
    if run is None:
        raise not_visible(str(run_id))
    return run


def resolve_completed_run_of_type(
    session: Session,
    run_id: str,
    *,
    acting_tenant: str,
    run_type: str,
    label: str,
    error: Callable[[str], Exception],
) -> CalculationRun:
    """Re-resolve a CONSUMED run (tenant + ``run_type`` + COMPLETED) BEFORE its id is stamped into a
    hard-FK column (PG FK checks bypass RLS — P3-5). Raises ``error(msg)`` (the binder input-error
    class) on a missing/wrong-``run_type`` run OR a non-COMPLETED status."""
    run = resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=run_type,
        not_visible=lambda rid: error(
            f"{label} run {rid} is not a visible {run_type} run — refused"
        ),
    )
    if run.status != RunStatus.COMPLETED.value:
        raise error(f"{label} run {run_id} status {run.status!r} != COMPLETED — refused")
    return run
