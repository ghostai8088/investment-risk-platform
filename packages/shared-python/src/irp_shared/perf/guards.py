"""Shared perf-binder guards (PM-1 + P3-8 — one implementation of the cross-slice security checks).

The P3-5 principal finding: PG FK checks BYPASS RLS, so an id lifted from a hand-minted snapshot's
pinned JSON must be re-resolved under the acting tenant BEFORE it is stamped into a NOT-NULL FK
column — otherwise a durable cross-tenant reference (or a flush 500) is possible. Every perf binder
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
