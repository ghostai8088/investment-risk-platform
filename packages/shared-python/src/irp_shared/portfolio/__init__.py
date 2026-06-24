"""Portfolio domain package (P1C-1) — the portfolio/fund/strategy/account hierarchy.

The platform's first **domain** (non-reference) package. ``portfolio`` (ENT-010) is a single
effective-dated (EV) table with a ``node_type`` controlled-vocab and a ``parent_portfolio_id``
self-FK adjacency — the entitlement portfolio-scope **ANCHOR** for CAP-1.

Mirrors the ``reference`` package shape (models / events / service / binder) but is
**self-contained**:
it imports only the rails (``lineage`` / ``audit`` / ``db``), never ``reference``, ``irp_backend``,
or
``irp_shared.models`` (the aggregator) — enforced by an import-direction test. A portfolio holds
**nothing** (no positions/valuations/holdings); the descendant resolver records future ABAC subtree
semantics but **no scope is enforced** (anchor-not-enforce, AD-017 / OD-P1C-A).
"""

from __future__ import annotations

from irp_shared.portfolio.events import PORTFOLIO_CREATE_EVENT, PORTFOLIO_UPDATE_EVENT
from irp_shared.portfolio.models import Portfolio
from irp_shared.portfolio.portfolio import (
    MAX_HIERARCHY_DEPTH,
    HierarchyCycleError,
    PortfolioNotVisible,
    create_portfolio,
    resolve_descendants,
    resolve_portfolio,
    resolve_ultimate_parent,
    update_portfolio,
)
from irp_shared.portfolio.service import PortfolioActor

__all__ = [
    "Portfolio",
    "PortfolioActor",
    "PortfolioNotVisible",
    "HierarchyCycleError",
    "MAX_HIERARCHY_DEPTH",
    "PORTFOLIO_CREATE_EVENT",
    "PORTFOLIO_UPDATE_EVENT",
    "resolve_portfolio",
    "resolve_ultimate_parent",
    "resolve_descendants",
    "create_portfolio",
    "update_portfolio",
]
