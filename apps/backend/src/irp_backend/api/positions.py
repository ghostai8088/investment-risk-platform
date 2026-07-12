"""Position endpoints (P1C-3, REQ-PPM-002) — FR bitemporal, captured directly, CAPTURE-ONLY.

Thin layer over the ``irp_shared.position`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), FR
(NOT append-only). Each write is gated deny-by-default; ``tenant_id`` is server-stamped from the
principal; ``portfolio_id``/``instrument_id`` are resolved tenant-filtered (cross-tenant/unknown ->
indistinguishable 404); a single end-of-request ``db.commit()``.

There is **no PUT/PATCH/DELETE** (no in-place content edit, no delete). A position is *superseded*
(a new effective-dated version) or *corrected* (an as-known restatement) — both append NEW versions;
the prior version's content is never mutated. The as-of read is a **single position** reconstruction
(read-only, no aggregation). **No holdings view / no rollup / no valuation / no exposure / no market
value** (capture-only; those are later slices).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.db.integrity import is_unique_violation
from irp_shared.entitlement.service import Principal
from irp_shared.portfolio import PortfolioNotVisible
from irp_shared.position import (
    NoCurrentPosition,
    Position,
    PositionActor,
    PositionNotVisible,
    PositionValueError,
    correct_position,
    create_position,
    reconstruct_position_as_of,
    resolve_position,
    supersede_position,
)
from irp_shared.reference.instrument import InstrumentNotVisible

router = APIRouter(prefix="/positions", tags=["positions"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_edit = require_permission("position.edit")
_require_view = require_permission("position.view")


def _actor(principal: Principal) -> PositionActor:
    return PositionActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


class PositionIn(BaseModel):
    portfolio_id: uuid.UUID  # malformed -> 422
    instrument_id: uuid.UUID
    quantity: Decimal  # signed (long > 0, short < 0)
    valid_from: datetime | None = None  # the as-of date; defaults to now
    cost_basis: Decimal | None = None  # opaque captured reference
    quantity_unit: str | None = None
    position_source: str | None = None


class PositionSupersedeIn(BaseModel):
    effective_at: datetime  # the new business as-of date
    quantity: Decimal | None = (
        None  # only fields set here override the carried-forward prior values
    )
    cost_basis: Decimal | None = None
    quantity_unit: str | None = None
    position_source: str | None = None


class PositionCorrectIn(BaseModel):
    restatement_reason: str
    quantity: Decimal | None = None
    cost_basis: Decimal | None = None
    quantity_unit: str | None = None
    position_source: str | None = None


class PositionOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    quantity: Decimal
    cost_basis: Decimal | None
    quantity_unit: str | None
    position_source: str | None
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    restatement_reason: str | None
    supersedes_id: str | None
    record_version: int


def _out(row: Position) -> PositionOut:
    return PositionOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        quantity=row.quantity,
        cost_basis=row.cost_basis,
        quantity_unit=row.quantity_unit,
        position_source=row.position_source,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        restatement_reason=row.restatement_reason,
        supersedes_id=row.supersedes_id,
        record_version=row.record_version,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PositionOut)
def create_position_endpoint(
    body: PositionIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> PositionOut:
    try:
        row = create_position(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            acting_tenant=principal.tenant_id,  # server-stamped; body has no tenant_id
            actor=_actor(principal),
            quantity=body.quantity,
            valid_from=body.valid_from,
            cost_basis=body.cost_basis,
            quantity_unit=body.quantity_unit,
            position_source=body.position_source,
        )
    except (PortfolioNotVisible, InstrumentNotVisible):  # cross-tenant/unknown -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio or instrument not found"
        ) from None
    except IntegrityError as exc:  # duplicate open head -> 409 (MD-H1 sibling consistency)
        db.rollback()
        if not is_unique_violation(exc):
            raise  # a real data-integrity bug stays a loud 500, never a mislabeled 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a current open position already exists for this (portfolio, instrument)",
        ) from None
    db.commit()
    return _out(row)


@router.post(
    "/{position_id}/supersede", status_code=status.HTTP_201_CREATED, response_model=PositionOut
)
def supersede_position_endpoint(
    position_id: uuid.UUID,
    body: PositionSupersedeIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> PositionOut:
    """Book a new effective-dated version for the (portfolio, instrument) of the current head."""
    try:
        head = resolve_position(db, str(position_id), acting_tenant=principal.tenant_id)
        new = supersede_position(
            db,
            portfolio_id=head.portfolio_id,
            instrument_id=head.instrument_id,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            effective_at=body.effective_at,
            **body.model_dump(exclude_unset=True, exclude={"effective_at"}),
        )
    except PositionNotVisible:  # cross-tenant/unknown -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="position not found"
        ) from None
    except NoCurrentPosition:  # no open head to supersede -> 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no current open position to supersede"
        ) from None
    except PositionValueError:  # window-incoherent effective_at (MD-H1) -> 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_at must be strictly after the current version's valid_from",
        ) from None
    db.commit()
    return _out(new)


@router.post(
    "/{position_id}/correct", status_code=status.HTTP_201_CREATED, response_model=PositionOut
)
def correct_position_endpoint(
    position_id: uuid.UUID,
    body: PositionCorrectIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> PositionOut:
    """Book an as-known restatement of the given version (prior content never mutated)."""
    try:
        row = resolve_position(db, str(position_id), acting_tenant=principal.tenant_id)
        corrected = correct_position(
            db,
            row,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            **body.model_dump(exclude_unset=True, exclude={"restatement_reason"}),
        )
    except PositionNotVisible:  # cross-tenant/unknown -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="position not found"
        ) from None
    db.commit()
    return _out(corrected)


@router.get("", response_model=list[PositionOut])
def list_positions(
    portfolio_id: uuid.UUID | None = Query(None),
    instrument_id: uuid.UUID | None = Query(None),
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[PositionOut]:
    """List CURRENT-HEAD positions (open on both axes). Filter-only — NO sum/net/aggregate."""
    stmt = (
        select(Position)
        .where(Position.valid_to.is_(None), Position.system_to.is_(None))
        .order_by(Position.system_from)
    )
    if portfolio_id is not None:
        stmt = stmt.where(Position.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(Position.instrument_id == str(instrument_id))
    rows = db.execute(stmt).scalars().all()
    return [_out(row) for row in rows]


@router.get("/as-of", response_model=PositionOut)
def reconstruct_position_endpoint(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID,
    valid_at: datetime,
    known_at: datetime | None = Query(None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PositionOut:
    """Single-position bitemporal as-of read (read-only; NO aggregation / holdings view)."""
    row = reconstruct_position_as_of(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valid_at=valid_at,
        known_at=known_at,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position not found")
    return _out(row)


@router.get("/{position_id}", response_model=PositionOut)
def get_position(
    position_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PositionOut:
    row = db.get(Position, str(position_id))
    if row is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position not found")
    return _out(row)
