"""As-of holdings / portfolio view endpoint (P1C-5) — READ-ONLY composition.

A thin layer over the ``irp_shared.holdings`` read models. It reconstructs the *set* of holdings in
a portfolio (or its bounded subtree) as-of a ``(valid_at, known_at)`` point, optionally attaching
the **display-only** captured valuation mark per holding. It is read-only: no ``db.commit()``, no
audit event, no lineage/DQ write. It computes nothing — no aggregation, no ``market_value``, no
``quantity x mark_value``, no exposure, no total (AD-017 capture-only; OD-P1C-F/G/H).

Entitlement: ``portfolio.view`` + ``position.view`` are enforced as route dependencies (deny-by-
default). ``valuation.view`` is enforced **in-handler**, only when ``include_marks=true``, BEFORE
any mark lookup (a position-only viewer cannot obtain valuations through this endpoint). Tenant
isolation is inherited from the RLS-scoped session + the service tenant predicate. Subtree traversal
is read COMPOSITION, not ABAC scope enforcement (anchor-not-enforce -> P6+).

Errors: unknown/cross-tenant ``portfolio_id`` -> 404; corrupt/too-deep hierarchy on ``subtree=true``
-> 409 (mirrors ``GET /portfolios/{id}/tree``); ``include_marks=true`` without ``valuation_date`` ->
422; malformed ``portfolio_id``/dates -> 422.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal, has_permission
from irp_shared.holdings import (
    HoldingWithMark,
    attach_marks_as_of,
    reconstruct_holdings_as_of,
    reconstruct_subtree_holdings_as_of,
)
from irp_shared.holdings.service import HoldingRow
from irp_shared.portfolio import HierarchyCycleError, PortfolioNotVisible, resolve_portfolio

router = APIRouter(prefix="/portfolios", tags=["holdings"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_portfolio_view = require_permission("portfolio.view")
_require_position_view = require_permission("position.view")


class MarkOut(BaseModel):
    """Display-only captured mark (present only when ``include_marks=true`` and a mark exists)."""

    valuation_id: str
    valuation_date: date
    mark_value: Decimal
    currency_code: str | None
    mark_source: str | None
    price_basis: str | None


class HoldingOut(BaseModel):
    """A single as-of holding — stored position fields only (+ optional display-only mark). NO
    computed/aggregate field (no market_value, exposure, total, weight)."""

    position_id: str
    portfolio_id: str
    instrument_id: str
    quantity: Decimal
    quantity_unit: str | None
    cost_basis: Decimal | None
    position_source: str | None
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    record_version: int
    mark: MarkOut | None = None


class AsOf(BaseModel):
    valid_at: datetime
    known_at: datetime | None


class HoldingsOut(BaseModel):
    """The as-of holdings list for a portfolio (or bounded subtree). A LIST, never an aggregate —
    there is no total/sum/rollup field anywhere in this schema."""

    portfolio_id: str
    subtree: bool
    as_of: AsOf
    holdings: list[HoldingOut]


def _mark_out(mark) -> MarkOut | None:  # noqa: ANN001 - MarkView | None
    if mark is None:
        return None
    return MarkOut(
        valuation_id=mark.valuation_id,
        valuation_date=mark.valuation_date,
        mark_value=mark.mark_value,
        currency_code=mark.currency_code,
        mark_source=mark.mark_source,
        price_basis=mark.price_basis,
    )


def _holding_out(holding: HoldingRow, mark=None) -> HoldingOut:  # noqa: ANN001 - MarkView | None
    return HoldingOut(
        position_id=holding.position_id,
        portfolio_id=holding.portfolio_id,
        instrument_id=holding.instrument_id,
        quantity=holding.quantity,
        quantity_unit=holding.quantity_unit,
        cost_basis=holding.cost_basis,
        position_source=holding.position_source,
        valid_from=holding.valid_from,
        valid_to=holding.valid_to,
        system_from=holding.system_from,
        system_to=holding.system_to,
        record_version=holding.record_version,
        mark=_mark_out(mark),
    )


@router.get(
    "/{portfolio_id}/holdings",
    response_model=HoldingsOut,
    dependencies=[Depends(_require_position_view)],
)
def get_holdings(
    portfolio_id: UUID,  # malformed -> uniform 422 before any DB hit
    valid_at: datetime,  # REQUIRED — the business as-of (matches reconstruct_position_as_of)
    known_at: datetime | None = Query(None),  # optional system/knowledge time (default now)
    subtree: bool = Query(False),  # bounded descendant composition (read convenience)
    include_marks: bool = Query(False),  # opt-in display-only marks
    valuation_date: date | None = Query(None),  # REQUIRED iff include_marks=true
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(_require_portfolio_view),
    db: Session = Depends(get_tenant_session),
) -> HoldingsOut:
    """Read-only as-of holdings for a portfolio (or its bounded subtree). Composes captured position
    (+ optional display-only valuation) FR reads; computes nothing; emits no audit/lineage."""
    if include_marks and valuation_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="valuation_date is required when include_marks=true",
        )
    # Conditional entitlement: valuation.view is checked in-handler BEFORE any mark lookup, so a
    # position-only viewer cannot obtain valuation data through the holdings endpoint (fail-closed).
    if include_marks and not has_permission(db, principal, "valuation.view", principal.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied: valuation.view required for marks",
        )

    try:
        if subtree:
            rows = reconstruct_subtree_holdings_as_of(
                db,
                acting_tenant=principal.tenant_id,
                portfolio_id=str(portfolio_id),
                valid_at=valid_at,
                known_at=known_at,
            )
        else:
            # Resolve the node first so an unknown/cross-tenant portfolio fails closed (404) rather
            # than silently returning an empty list.
            node = resolve_portfolio(db, str(portfolio_id), acting_tenant=principal.tenant_id)
            rows = reconstruct_holdings_as_of(
                db,
                acting_tenant=principal.tenant_id,
                portfolio_id=node.id,
                valid_at=valid_at,
                known_at=known_at,
            )
    except PortfolioNotVisible:  # unknown/cross-tenant -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found"
        ) from None
    except HierarchyCycleError:  # corrupt/too-deep subtree -> 409 (parity with /tree)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="hierarchy cycle or depth exceeded"
        ) from None

    page = rows[offset : offset + limit]  # limit/offset pagination; no total-count exposure

    if include_marks:
        assert valuation_date is not None  # guarded above; for the type-checker
        enriched: list[HoldingWithMark] = attach_marks_as_of(
            db,
            acting_tenant=principal.tenant_id,
            holdings=page,
            valuation_date=valuation_date,
            valid_at=valid_at,
            known_at=known_at,
        )
        out = [_holding_out(e.holding, e.mark) for e in enriched]
    else:
        out = [_holding_out(h) for h in page]

    return HoldingsOut(
        portfolio_id=str(portfolio_id),
        subtree=subtree,
        as_of=AsOf(valid_at=valid_at, known_at=known_at),
        holdings=out,
    )
