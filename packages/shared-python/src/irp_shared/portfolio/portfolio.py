"""Portfolio binder + bounded, cycle-safe hierarchy resolvers (P1C-1, ENT-010).

Owns the **tenant-filtered** resolution helpers + the governed create/amend binders:

- ``resolve_portfolio`` resolves a node by id with an **EXPLICIT ``tenant_id == acting_tenant``
  predicate** (the ``reference.resolve_legal_entity`` pattern) — a cross-tenant/unknown id raises
  ``PortfolioNotVisible`` and fails closed on **SQLite AND PostgreSQL** (RLS WITH CHECK is the PG
  backstop; the service predicate is what keeps a parent from being attached cross-tenant).
- ``resolve_ultimate_parent`` walks ``parent_portfolio_id`` **upward** to the root (ancestor) — a
  direct reuse of the shipped ``legal_entity.resolve_ultimate_parent`` shape (visited-set + depth
  cap
  + per-hop tenant predicate + boundary-stop). Pure structural traversal — **no exposure/scope
  math.**
- ``resolve_descendants`` walks ``parent_portfolio_id`` **downward** (the node's subtree) — a NEW
  bounded resolver built to the SAME safety invariants. This records the future ABAC **subtree**
  semantics (OD-P1C-B: a grant on a node reaches its descendants) but **enforces nothing** — nothing
  here reads or filters by scope (anchor-not-enforce, AD-017 / OD-P1C-A).

ABAC NOTE (residual risk, documented per OD-P1C-A / §15): there is **no scope enforcement** in
P1C-1.
Within a tenant, any principal holding ``portfolio.view`` can read **all** portfolios — RLS isolates
tenants, not portfolios. Portfolio-scope enforcement (the ``entitlement_grant`` scope payload
binding
``SCOPE-PORTFOLIO -> portfolio.id`` with subtree semantics) is deferred to P6+. This is acceptable
in
P1C because the data is synthetic (DC-1/DC-2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.portfolio.models import Portfolio
from irp_shared.portfolio.service import (
    PortfolioActor,
    record_portfolio_create,
    record_portfolio_update,
)

#: Defense-in-depth bound for hierarchy walks (the visited-set already guarantees termination;
# : exceeding the cap raises ``HierarchyCycleError`` regardless of a true cycle). Mirrors
# legal_entity.
MAX_HIERARCHY_DEPTH = 32

#: Mutable attributes ``update_portfolio`` will diff/apply (``code`` is the stable identity key;
#: ``status`` rides on ``PORTFOLIO.UPDATE`` — no separate lifecycle event in P1C-1).
_UPDATABLE = (
    "name",
    "node_type",
    "parent_portfolio_id",
    "base_currency_code",
    "status",
    "description",
)


class PortfolioNotVisible(Exception):
    """Raised when a ``portfolio_id`` (a node, or a parent) is not visible in the acting tenant
    scope (cross-tenant id hidden, or unknown) — a dependent write/resolve fails closed."""

    def __init__(self, portfolio_id: str) -> None:
        super().__init__(f"portfolio {portfolio_id} is not visible in the current tenant context")
        self.portfolio_id = str(portfolio_id)


class HierarchyCycleError(Exception):
    """Raised when the ``parent_portfolio_id`` walk cycles or exceeds ``MAX_HIERARCHY_DEPTH`` (in
    either direction), or when a re-parent would create a cycle."""

    def __init__(self, portfolio_id: str) -> None:
        super().__init__(f"portfolio hierarchy from {portfolio_id} cycles or exceeds the depth cap")
        self.portfolio_id = str(portfolio_id)


def resolve_portfolio(session: Session, portfolio_id: str, *, acting_tenant: str) -> Portfolio:
    """Resolve a ``portfolio`` by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed on SQLite AND PG). Raises :class:`PortfolioNotVisible` on a hidden/unknown id."""
    node = session.execute(
        select(Portfolio).where(
            Portfolio.id == str(portfolio_id),
            Portfolio.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if node is None:
        raise PortfolioNotVisible(str(portfolio_id))
    return node


def resolve_ultimate_parent(session: Session, portfolio: Portfolio, *, acting_tenant: str) -> str:
    """Return the ultimate-parent (root) id by walking ``parent_portfolio_id`` upward within the
    acting tenant — bounded (visited-set + depth cap), cycle-safe, boundary-terminating.

    A NULL parent ends the walk (current is the root). A parent not visible in ``acting_tenant``
    ends the walk at the highest visible ancestor. A repeat (cycle) or exceeding the depth cap
    raises
    :class:`HierarchyCycleError`."""
    if str(portfolio.tenant_id) != str(acting_tenant):
        raise PortfolioNotVisible(str(portfolio.id))
    current = portfolio
    visited = {str(current.id)}
    for _ in range(MAX_HIERARCHY_DEPTH):
        parent_id = current.parent_portfolio_id
        if parent_id is None:
            return str(current.id)
        if str(parent_id) in visited:
            raise HierarchyCycleError(str(portfolio.id))
        parent = session.execute(
            select(Portfolio).where(
                Portfolio.id == str(parent_id),
                Portfolio.tenant_id
                == str(acting_tenant),  # explicit tenant filter -> boundary stop
            )
        ).scalar_one_or_none()
        if parent is None:
            return str(current.id)  # boundary: parent not visible -> highest visible ancestor
        visited.add(str(parent.id))
        current = parent
    raise HierarchyCycleError(str(portfolio.id))  # exceeded the depth cap


def resolve_descendants(
    session: Session, portfolio: Portfolio, *, acting_tenant: str
) -> list[Portfolio]:
    """Return the node's descendants (its **subtree**, excluding the node itself) by walking
    ``parent_portfolio_id`` downward within the acting tenant — bounded (visited-set + depth cap),
    cycle-safe, tenant-filtered. The substrate for future ABAC **subtree** scope (OD-P1C-B); it
    **enforces nothing**. A repeat (cycle) or exceeding the depth cap raises
    :class:`HierarchyCycleError`."""
    if str(portfolio.tenant_id) != str(acting_tenant):
        raise PortfolioNotVisible(str(portfolio.id))
    visited = {str(portfolio.id)}
    descendants: list[Portfolio] = []
    frontier = [str(portfolio.id)]
    for _ in range(MAX_HIERARCHY_DEPTH):
        if not frontier:
            return descendants
        children = list(
            session.execute(
                select(Portfolio)
                .where(
                    Portfolio.parent_portfolio_id.in_(frontier),
                    Portfolio.tenant_id == str(acting_tenant),  # tenant-bounded subtree
                )
                .order_by(Portfolio.code)
            )
            .scalars()
            .all()
        )
        frontier = []
        for child in children:
            child_id = str(child.id)
            if child_id in visited:
                raise HierarchyCycleError(str(portfolio.id))  # cycle
            visited.add(child_id)
            descendants.append(child)
            frontier.append(child_id)
    if frontier:
        raise HierarchyCycleError(str(portfolio.id))  # exceeded the depth cap (subtree too deep)
    return descendants


def _reject_reparent_cycle(
    session: Session, portfolio: Portfolio, new_parent: Portfolio, *, acting_tenant: str
) -> None:
    """Reject a re-parent that would create a cycle: walk upward from ``new_parent``; if the node
    ``portfolio`` is itself an ancestor of the new parent, the move would close a loop. Bounded."""
    if str(new_parent.id) == str(portfolio.id):
        raise HierarchyCycleError(str(portfolio.id))
    current = new_parent
    visited = {str(current.id)}
    for _ in range(MAX_HIERARCHY_DEPTH):
        parent_id = current.parent_portfolio_id
        if parent_id is None:
            return
        if str(parent_id) == str(portfolio.id):
            raise HierarchyCycleError(str(portfolio.id))  # re-parent would create a cycle
        if str(parent_id) in visited:
            raise HierarchyCycleError(str(portfolio.id))  # a pre-existing cycle
        parent = session.execute(
            select(Portfolio).where(
                Portfolio.id == str(parent_id),
                Portfolio.tenant_id == str(acting_tenant),
            )
        ).scalar_one_or_none()
        if parent is None:
            return  # boundary
        visited.add(str(parent.id))
        current = parent
    raise HierarchyCycleError(str(portfolio.id))  # too deep


def create_portfolio(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    node_type: str,
    actor: PortfolioActor,
    parent_portfolio_id: str | None = None,
    base_currency_code: str | None = None,
    status: str = "ACTIVE",
    description: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Portfolio:
    """Create a ``portfolio`` node (governed: MANUAL-source ORIGIN lineage + ``PORTFOLIO.CREATE``).

    If ``parent_portfolio_id`` is given it is resolved tenant-filtered (a cross-tenant/unknown
    parent
    fails closed via :class:`PortfolioNotVisible`). Self-parenting is impossible on create (the new
    id
    is server-generated and the parent must pre-exist) — it is guarded on update.

    ``entity_id``/``now`` are the deterministic-injection seam (keyword-only, default-None ⇒ every
    production call site is unchanged: server `uuid4` id + the EV mixin's wall-clock `valid_from`);
    only the synthetic seed passes them for `uuid5` ids + a fixed clock."""
    if parent_portfolio_id is not None:
        resolve_portfolio(session, parent_portfolio_id, acting_tenant=tenant_id)

    portfolio = Portfolio(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        node_type=node_type,
        parent_portfolio_id=(str(parent_portfolio_id) if parent_portfolio_id else None),
        base_currency_code=base_currency_code,
        status=status,
        description=description,
        record_version=1,
    )
    if now is not None:
        portfolio.valid_from = (
            now  # seam: fixed clock (else the EV mixin default stamps wall-clock)
        )
    if entity_id is not None:
        portfolio.id = entity_id  # seam: deterministic uuid5 id (skips the `default=new_uuid`)
    session.add(portfolio)
    session.flush()
    record_portfolio_create(
        session,
        entity=portfolio,
        after_value={
            "code": code,
            "name": name,
            "node_type": node_type,
            "status": status,
            "parent_portfolio_id": portfolio.parent_portfolio_id,
            "base_currency_code": base_currency_code,
        },
        actor=actor,
        now=now,
    )
    return portfolio


def update_portfolio(
    session: Session,
    portfolio: Portfolio,
    *,
    actor: PortfolioActor,
    **changes: Any,
) -> Portfolio:
    """Apply mutable changes (incl. re-parent / rename / status flip), bump ``record_version``, emit
    ``PORTFOLIO.UPDATE``. A re-parent rejects **self-parent** (``parent_portfolio_id == id``),
    resolves the new parent tenant-filtered (cross-tenant/unknown -> :class:`PortfolioNotVisible`),
    and re-runs the **cycle guard** (the new parent's ancestor chain must not contain this node)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable portfolio attributes: {sorted(unknown)}")

    new_parent_id = changes.get("parent_portfolio_id")
    if "parent_portfolio_id" in changes and new_parent_id is not None:
        if str(new_parent_id) == str(portfolio.id):
            raise ValueError("portfolio cannot be its own parent")
        new_parent = resolve_portfolio(session, new_parent_id, acting_tenant=portfolio.tenant_id)
        _reject_reparent_cycle(session, portfolio, new_parent, acting_tenant=portfolio.tenant_id)
        changes["parent_portfolio_id"] = str(new_parent_id)

    before = {key: getattr(portfolio, key) for key in changes}
    for key, value in changes.items():
        setattr(portfolio, key, value)
    portfolio.record_version += 1
    session.flush()
    record_portfolio_update(
        session,
        entity=portfolio,
        before_value=before,
        after_value={key: getattr(portfolio, key) for key in changes},
        actor=actor,
    )
    return portfolio
