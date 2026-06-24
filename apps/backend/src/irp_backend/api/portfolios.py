"""Portfolio hierarchy endpoints (P1C-1, REQ-PPM-001) — the ABAC scope ANCHOR.

Thin layer over the ``irp_shared.portfolio`` binder. PROPRIETARY tenant-scoped (NEVER hybrid). Each
write is gated deny-by-default; ``tenant_id`` is server-stamped from the principal; a
``parent_portfolio_id`` is resolved tenant-filtered (cross-tenant/unknown -> indistinguishable 404);
a single end-of-request ``db.commit()``. ``POST /{id}`` is an EV amend (in-place supersede). No
DELETE/PUT (retire via ``status``).

ABAC NOTE (anchor-not-enforce, AD-017 / OD-P1C-A): ``portfolio.view`` gates by **role + tenant**
only
— there is **no portfolio-scope filtering**. Within a tenant, any ``portfolio.view`` holder sees ALL
portfolios (incl. the ``/tree`` subtree). The subtree read records future ABAC semantics; it
enforces
nothing. Portfolio-scope enforcement is deferred to P6+.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.portfolio import (
    HierarchyCycleError,
    Portfolio,
    PortfolioActor,
    PortfolioNotVisible,
    create_portfolio,
    resolve_descendants,
    resolve_portfolio,
    update_portfolio,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_edit = require_permission("portfolio.edit")
_require_view = require_permission("portfolio.view")

#: The amendable attribute fields (NOT code — code is the stable identity key).
_AMENDABLE = (
    "name",
    "node_type",
    "parent_portfolio_id",
    "base_currency_code",
    "status",
    "description",
)


def _actor(principal: Principal) -> PortfolioActor:
    return PortfolioActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


class PortfolioIn(BaseModel):
    code: str
    name: str
    node_type: str
    parent_portfolio_id: uuid.UUID | None = None  # malformed -> 422
    base_currency_code: str | None = None
    status: str = "ACTIVE"
    description: str | None = None


class PortfolioAmendIn(BaseModel):
    name: str | None = None
    node_type: str | None = None
    parent_portfolio_id: uuid.UUID | None = None
    base_currency_code: str | None = None
    status: str | None = None
    description: str | None = None

    def attr_changes(self) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field in _AMENDABLE:
            value = getattr(self, field)
            if value is None:
                continue
            changes[field] = str(value) if field == "parent_portfolio_id" else value
        return changes


class PortfolioOut(BaseModel):
    id: str
    code: str
    name: str
    node_type: str
    parent_portfolio_id: str | None
    base_currency_code: str | None
    status: str
    description: str | None
    record_version: int


def _out(node: Portfolio) -> PortfolioOut:
    return PortfolioOut(
        id=node.id,
        code=node.code,
        name=node.name,
        node_type=node.node_type,
        parent_portfolio_id=node.parent_portfolio_id,
        base_currency_code=node.base_currency_code,
        status=node.status,
        description=node.description,
        record_version=node.record_version,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PortfolioOut)
def create_portfolio_endpoint(
    body: PortfolioIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> PortfolioOut:
    try:
        node = create_portfolio(
            db,
            tenant_id=principal.tenant_id,  # server-stamped; body has no tenant_id
            code=body.code,
            name=body.name,
            node_type=body.node_type,
            actor=_actor(principal),
            parent_portfolio_id=(
                str(body.parent_portfolio_id) if body.parent_portfolio_id else None
            ),
            base_currency_code=body.base_currency_code,
            status=body.status,
            description=body.description,
        )
    except PortfolioNotVisible:  # cross-tenant/unknown parent -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="parent portfolio not found"
        ) from None
    db.commit()
    return _out(node)


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(
    node_type: str | None = Query(None),
    parent_portfolio_id: uuid.UUID | None = Query(None),
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[PortfolioOut]:
    # No portfolio-scope filtering (anchor-not-enforce): any view-holder sees ALL tenant nodes.
    stmt = select(Portfolio).order_by(Portfolio.code)
    if node_type is not None:
        stmt = stmt.where(Portfolio.node_type == node_type)
    if parent_portfolio_id is not None:
        stmt = stmt.where(Portfolio.parent_portfolio_id == str(parent_portfolio_id))
    rows = db.execute(stmt).scalars().all()
    return [_out(node) for node in rows]


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(
    portfolio_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PortfolioOut:
    node = db.get(Portfolio, str(portfolio_id))
    if node is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found")
    return _out(node)


@router.get("/{portfolio_id}/tree", response_model=list[PortfolioOut])
def get_portfolio_tree(
    portfolio_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[PortfolioOut]:
    """The node's descendants (subtree, excluding itself), bounded + tenant-scoped. Records future
    ABAC subtree semantics; enforces nothing (anchor-not-enforce)."""
    try:
        node = resolve_portfolio(db, str(portfolio_id), acting_tenant=principal.tenant_id)
        descendants = resolve_descendants(db, node, acting_tenant=principal.tenant_id)
    except PortfolioNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found"
        ) from None
    except HierarchyCycleError:  # corrupt/too-deep hierarchy -> 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="hierarchy cycle or depth exceeded"
        ) from None
    return [_out(child) for child in descendants]


@router.post("/{portfolio_id}", response_model=PortfolioOut)
def amend_portfolio_endpoint(
    portfolio_id: uuid.UUID,
    body: PortfolioAmendIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> PortfolioOut:
    try:
        node = resolve_portfolio(db, str(portfolio_id), acting_tenant=principal.tenant_id)
        node = update_portfolio(db, node, actor=_actor(principal), **body.attr_changes())
    except (
        PortfolioNotVisible
    ):  # cross-tenant/unknown (node or new parent) -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found"
        ) from None
    except HierarchyCycleError:  # re-parent would create a cycle -> 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="illegal re-parent (cycle)"
        ) from None
    except ValueError:  # self-parent / non-updatable attribute -> 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid amend"
        ) from None
    db.commit()
    return _out(node)
