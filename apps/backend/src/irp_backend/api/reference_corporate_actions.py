"""Reference corporate-action endpoints (P1B-4, REQ-SMR-004 corporate_action) — CAPTURE-ONLY.

A FOURTH ``APIRouter(prefix="/reference")`` (the P1B-1/P1B-2/P1B-3 routers are all untouched). Thin
layer over the `irp_shared.reference.corporate_action` binder. PROPRIETARY tenant-scoped (NEVER
hybrid) — no `DISTINCT ON`. Each write is gated deny-by-default; `tenant_id` is server-stamped from
the principal; the `instrument_id` is resolved tenant-filtered (cross-tenant/unknown →
indistinguishable
404); a single end-of-request `db.commit()`. The `POST /{id}` dispatches `amend` (attribute change)
or
`status` (lifecycle transition). **No application/position/valuation logic** (capture-only). No
DELETE/PUT.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.reference.corporate_action import (
    CorporateActionNotVisible,
    IllegalStatusTransition,
    create_corporate_action,
    resolve_corporate_action,
    transition_corporate_action_status,
    update_corporate_action,
)
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.reference.models import CorporateAction
from irp_shared.reference.service import ReferenceActor

router = APIRouter(prefix="/reference", tags=["reference-corporate-actions"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_ca_edit = require_permission("reference.corporate_action.edit")
_require_ca_view = require_permission("reference.corporate_action.view")

#: The amendable attribute fields (NOT code/instrument_id/status — status uses the transition path).
_AMENDABLE = (
    "action_type",
    "announcement_date",
    "ex_date",
    "record_date",
    "pay_date",
    "effective_date",
    "ratio",
    "amount",
    "currency_code",
    "description",
    "source",
)


def _actor(principal: Principal) -> ReferenceActor:
    return ReferenceActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


class CorporateActionIn(BaseModel):
    code: str
    instrument_id: uuid.UUID  # malformed -> 422
    action_type: str
    status: str = "ANNOUNCED"
    announcement_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    pay_date: date | None = None
    effective_date: date | None = None
    ratio: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    description: str | None = None
    source: str | None = None


class CorporateActionAmendIn(BaseModel):
    mode: Literal["amend", "status"]
    new_status: str | None = None  # required for mode=status
    reason: str | None = None
    action_type: str | None = None
    announcement_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    pay_date: date | None = None
    effective_date: date | None = None
    ratio: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    description: str | None = None
    source: str | None = None

    def attr_changes(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in _AMENDABLE if getattr(self, f) is not None}


class CorporateActionOut(BaseModel):
    id: str
    code: str
    instrument_id: str
    action_type: str
    status: str
    announcement_date: date | None
    ex_date: date | None
    record_date: date | None
    pay_date: date | None
    effective_date: date | None
    ratio: Decimal | None
    amount: Decimal | None
    currency_code: str | None
    description: str | None
    source: str | None
    record_version: int


def _ca_out(ca: CorporateAction) -> CorporateActionOut:
    return CorporateActionOut(
        id=ca.id,
        code=ca.code,
        instrument_id=ca.instrument_id,
        action_type=ca.action_type,
        status=ca.status,
        announcement_date=ca.announcement_date,
        ex_date=ca.ex_date,
        record_date=ca.record_date,
        pay_date=ca.pay_date,
        effective_date=ca.effective_date,
        ratio=ca.ratio,
        amount=ca.amount,
        currency_code=ca.currency_code,
        description=ca.description,
        source=ca.source,
        record_version=ca.record_version,
    )


@router.post(
    "/corporate-actions", status_code=status.HTTP_201_CREATED, response_model=CorporateActionOut
)
def create_corporate_action_endpoint(
    body: CorporateActionIn,
    principal: Principal = Depends(_require_ca_edit),
    db: Session = Depends(get_tenant_session),
) -> CorporateActionOut:
    try:
        ca = create_corporate_action(
            db,
            tenant_id=principal.tenant_id,  # server-stamped; body has no tenant_id
            code=body.code,
            instrument_id=str(body.instrument_id),
            action_type=body.action_type,
            actor=_actor(principal),
            status=body.status,
            announcement_date=body.announcement_date,
            ex_date=body.ex_date,
            record_date=body.record_date,
            pay_date=body.pay_date,
            effective_date=body.effective_date,
            ratio=body.ratio,
            amount=body.amount,
            currency_code=body.currency_code,
            description=body.description,
            source=body.source,
        )
    except InstrumentNotVisible:  # cross-tenant/unknown instrument -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found"
        ) from None
    except IllegalStatusTransition:  # out-of-vocab initial status -> 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid status"
        ) from None
    db.commit()
    return _ca_out(ca)


@router.get("/corporate-actions", response_model=list[CorporateActionOut])
def list_corporate_actions(
    instrument_id: uuid.UUID | None = Query(None),
    _: Principal = Depends(_require_ca_view),
    db: Session = Depends(get_tenant_session),
) -> list[CorporateActionOut]:
    stmt = select(CorporateAction).order_by(CorporateAction.code)
    if instrument_id is not None:
        stmt = stmt.where(CorporateAction.instrument_id == str(instrument_id))
    rows = db.execute(stmt).scalars().all()
    return [_ca_out(ca) for ca in rows]


@router.get("/corporate-actions/{corporate_action_id}", response_model=CorporateActionOut)
def get_corporate_action(
    corporate_action_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_ca_view),
    db: Session = Depends(get_tenant_session),
) -> CorporateActionOut:
    ca = db.get(CorporateAction, str(corporate_action_id))
    if ca is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="corporate_action not found"
        )
    return _ca_out(ca)


@router.post("/corporate-actions/{corporate_action_id}", response_model=CorporateActionOut)
def amend_corporate_action_endpoint(
    corporate_action_id: uuid.UUID,
    body: CorporateActionAmendIn,
    principal: Principal = Depends(_require_ca_edit),
    db: Session = Depends(get_tenant_session),
) -> CorporateActionOut:
    try:
        ca = resolve_corporate_action(
            db, str(corporate_action_id), acting_tenant=principal.tenant_id
        )
        if body.mode == "amend":
            ca = update_corporate_action(db, ca, actor=_actor(principal), **body.attr_changes())
        else:  # status
            if not body.new_status:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="new_status is required for mode=status",
                )
            ca = transition_corporate_action_status(
                db, ca, new_status=body.new_status, actor=_actor(principal), reason=body.reason
            )
    except CorporateActionNotVisible:  # cross-tenant/unknown -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="corporate_action not found"
        ) from None
    except IllegalStatusTransition:  # disallowed lifecycle move -> 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="illegal status transition"
        ) from None
    db.commit()
    return _ca_out(ca)
