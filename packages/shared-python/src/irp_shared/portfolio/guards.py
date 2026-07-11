"""Shared portfolio guards — one implementation of the cross-family tenant-resolution checks.

(Relocated from ``perf/guards.py`` at BT-1: once a RISK binder also needed the check, the perf
home violated the "nothing imports perf" fence — the guard is about PORTFOLIO tenant resolution,
so it lives with portfolio.)

The P3-5 principal finding: PG FK checks BYPASS RLS, so an id lifted from a hand-minted snapshot's
pinned JSON must be re-resolved under the acting tenant BEFORE it is stamped into a NOT-NULL FK
column — otherwise a durable cross-tenant reference (or a flush 500) is possible. Every
governed-number binder that stamps a portfolio FK
applies the same guard; it lives ONCE here, parameterized by the binder's own pre-create refusal
error class (each governed number keeps its own error vocabulary — the API maps them per family).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def assert_portfolio_in_tenant(
    session: Session, portfolio_id: str, *, acting_tenant: str, error: type[Exception]
) -> None:
    """Re-resolve the measured book's ``portfolio_id`` under the acting tenant with an EXPLICIT
    tenant predicate (models-only import — the ``portfolio`` SERVICE is not imported, keeping the
    perf fence). Raises ``error`` if the id is not visible in the acting tenant — a
    FOREIGN/non-existent portfolio_id must never be stamped into the NOT-NULL ``portfolio`` FK."""
    from irp_shared.portfolio.models import Portfolio  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(Portfolio).where(
            Portfolio.id == str(portfolio_id),
            Portfolio.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise error(
            f"the measured portfolio {portfolio_id} is not visible in the acting tenant — refused"
        )
