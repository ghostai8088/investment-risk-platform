"""Reference legal-entity / issuer / counterparty endpoints (P1B-2, REQ-SMR-002).

Thin layer over the `irp_shared.reference` legal-entity/issuer/counterparty binders, in a SEPARATE
file from `api/reference.py` (the P1B-1 currency/calendar/rating endpoints) so each entity family
stays cohesive. These three are PROPRIETARY tenant-scoped (NEVER hybrid), so there is
NO `DISTINCT ON` dedup (no SYSTEM rows). Each write is gated deny-by-default; `tenant_id` is
**server-stamped from the principal** (never the body); profile creates resolve their `legal_entity`
core with an explicit tenant predicate (cross-tenant/unknown → indistinguishable 404); a single
end-of-request `db.commit()`. The legal-entity detail returns the `ultimate_parent_id` (a pure
structural adjacency walk — no exposure math). No PUT/DELETE/bulk/search.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.reference.counterparty import create_counterparty
from irp_shared.reference.issuer import create_issuer
from irp_shared.reference.legal_entity import (
    HierarchyCycleError,
    LegalEntityNotVisible,
    create_legal_entity,
    resolve_ultimate_parent,
)
from irp_shared.reference.models import Counterparty, Issuer, LegalEntity
from irp_shared.reference.service import ReferenceActor

router = APIRouter(prefix="/reference", tags=["reference-entities"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_le_edit = require_permission("reference.legal_entity.edit")
_require_le_view = require_permission("reference.legal_entity.view")
_require_issuer_edit = require_permission("reference.issuer.edit")
_require_issuer_view = require_permission("reference.issuer.view")
_require_cpty_edit = require_permission("reference.counterparty.edit")
_require_cpty_view = require_permission("reference.counterparty.view")


def _actor(principal: Principal) -> ReferenceActor:
    return ReferenceActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


# --------------------------------------------------------------------------- legal_entity


class LegalEntityIn(BaseModel):
    code: str
    name: str
    lei: str | None = None
    jurisdiction: str | None = None
    entity_type: str | None = None
    parent_legal_entity_id: uuid.UUID | None = None  # malformed -> 422
    is_active: bool = True


class LegalEntityOut(BaseModel):
    id: str
    code: str
    name: str
    lei: str | None
    jurisdiction: str | None
    entity_type: str | None
    parent_legal_entity_id: str | None
    is_active: bool


class LegalEntityDetailOut(LegalEntityOut):
    ultimate_parent_id: str


def _legal_entity_out(le: LegalEntity) -> LegalEntityOut:
    return LegalEntityOut(
        id=le.id,
        code=le.code,
        name=le.name,
        lei=le.lei,
        jurisdiction=le.jurisdiction,
        entity_type=le.entity_type,
        parent_legal_entity_id=le.parent_legal_entity_id,
        is_active=le.is_active,
    )


@router.post("/legal-entities", status_code=status.HTTP_201_CREATED, response_model=LegalEntityOut)
def create_legal_entity_endpoint(
    body: LegalEntityIn,
    principal: Principal = Depends(_require_le_edit),
    db: Session = Depends(get_tenant_session),
) -> LegalEntityOut:
    try:
        le = create_legal_entity(
            db,
            tenant_id=principal.tenant_id,  # server-stamped; body has no tenant_id
            code=body.code,
            name=body.name,
            actor=_actor(principal),
            lei=body.lei,
            jurisdiction=body.jurisdiction,
            entity_type=body.entity_type,
            parent_legal_entity_id=(
                str(body.parent_legal_entity_id) if body.parent_legal_entity_id else None
            ),
            is_active=body.is_active,
        )
    except LegalEntityNotVisible:  # cross-tenant/unknown parent -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="parent legal_entity not found"
        ) from None
    db.commit()
    return _legal_entity_out(le)


@router.get("/legal-entities", response_model=list[LegalEntityOut])
def list_legal_entities(
    _: Principal = Depends(_require_le_view),
    db: Session = Depends(get_tenant_session),
) -> list[LegalEntityOut]:
    rows = db.execute(select(LegalEntity).order_by(LegalEntity.code)).scalars().all()
    return [_legal_entity_out(le) for le in rows]


@router.get("/legal-entities/{legal_entity_id}", response_model=LegalEntityDetailOut)
def get_legal_entity(
    legal_entity_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    principal: Principal = Depends(_require_le_view),
    db: Session = Depends(get_tenant_session),
) -> LegalEntityDetailOut:
    le = db.get(LegalEntity, str(legal_entity_id))
    if le is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="legal_entity not found")
    try:
        ultimate = resolve_ultimate_parent(db, le, acting_tenant=principal.tenant_id)
    except HierarchyCycleError:  # stored cycle (only reachable via raw inserts) -> 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="legal_entity hierarchy cycle"
        ) from None
    out = _legal_entity_out(le)
    return LegalEntityDetailOut(**out.model_dump(), ultimate_parent_id=ultimate)


# --------------------------------------------------------------------------- issuer


class IssuerIn(BaseModel):
    legal_entity_id: uuid.UUID  # malformed -> 422
    issuer_type: str | None = None
    sector: str | None = None
    is_active: bool = True


class IssuerOut(BaseModel):
    id: str
    legal_entity_id: str
    issuer_type: str | None
    sector: str | None
    is_active: bool


class IssuerDetailOut(IssuerOut):
    legal_entity_code: str
    legal_entity_name: str
    lei: str | None


def _issuer_out(i: Issuer) -> IssuerOut:
    return IssuerOut(
        id=i.id,
        legal_entity_id=i.legal_entity_id,
        issuer_type=i.issuer_type,
        sector=i.sector,
        is_active=i.is_active,
    )


@router.post("/issuers", status_code=status.HTTP_201_CREATED, response_model=IssuerOut)
def create_issuer_endpoint(
    body: IssuerIn,
    principal: Principal = Depends(_require_issuer_edit),
    db: Session = Depends(get_tenant_session),
) -> IssuerOut:
    try:
        issuer = create_issuer(
            db,
            tenant_id=principal.tenant_id,
            legal_entity_id=str(body.legal_entity_id),
            actor=_actor(principal),
            issuer_type=body.issuer_type,
            sector=body.sector,
            is_active=body.is_active,
        )
    except LegalEntityNotVisible:  # cross-tenant/unknown core -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="legal_entity not found"
        ) from None
    db.commit()
    return _issuer_out(issuer)


@router.get("/issuers", response_model=list[IssuerOut])
def list_issuers(
    _: Principal = Depends(_require_issuer_view),
    db: Session = Depends(get_tenant_session),
) -> list[IssuerOut]:
    rows = db.execute(select(Issuer)).scalars().all()
    return [_issuer_out(i) for i in rows]


@router.get("/issuers/{issuer_id}", response_model=IssuerDetailOut)
def get_issuer(
    issuer_id: uuid.UUID,
    _: Principal = Depends(_require_issuer_view),
    db: Session = Depends(get_tenant_session),
) -> IssuerDetailOut:
    issuer = db.get(Issuer, str(issuer_id))
    if issuer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issuer not found")
    core = db.get(LegalEntity, issuer.legal_entity_id)  # RLS-scoped; same tenant -> always visible
    out = _issuer_out(issuer)
    return IssuerDetailOut(
        **out.model_dump(),
        legal_entity_code=core.code if core else "",
        legal_entity_name=core.name if core else "",
        lei=core.lei if core else None,
    )


# --------------------------------------------------------------------------- counterparty


class CounterpartyIn(BaseModel):
    legal_entity_id: uuid.UUID
    counterparty_type: str | None = None
    is_active: bool = True


class CounterpartyOut(BaseModel):
    id: str
    legal_entity_id: str
    counterparty_type: str | None
    is_active: bool


class CounterpartyDetailOut(CounterpartyOut):
    legal_entity_code: str
    legal_entity_name: str
    lei: str | None


def _counterparty_out(c: Counterparty) -> CounterpartyOut:
    return CounterpartyOut(
        id=c.id,
        legal_entity_id=c.legal_entity_id,
        counterparty_type=c.counterparty_type,
        is_active=c.is_active,
    )


@router.post("/counterparties", status_code=status.HTTP_201_CREATED, response_model=CounterpartyOut)
def create_counterparty_endpoint(
    body: CounterpartyIn,
    principal: Principal = Depends(_require_cpty_edit),
    db: Session = Depends(get_tenant_session),
) -> CounterpartyOut:
    try:
        counterparty = create_counterparty(
            db,
            tenant_id=principal.tenant_id,
            legal_entity_id=str(body.legal_entity_id),
            actor=_actor(principal),
            counterparty_type=body.counterparty_type,
            is_active=body.is_active,
        )
    except LegalEntityNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="legal_entity not found"
        ) from None
    db.commit()
    return _counterparty_out(counterparty)


@router.get("/counterparties", response_model=list[CounterpartyOut])
def list_counterparties(
    _: Principal = Depends(_require_cpty_view),
    db: Session = Depends(get_tenant_session),
) -> list[CounterpartyOut]:
    rows = db.execute(select(Counterparty)).scalars().all()
    return [_counterparty_out(c) for c in rows]


@router.get("/counterparties/{counterparty_id}", response_model=CounterpartyDetailOut)
def get_counterparty(
    counterparty_id: uuid.UUID,
    _: Principal = Depends(_require_cpty_view),
    db: Session = Depends(get_tenant_session),
) -> CounterpartyDetailOut:
    counterparty = db.get(Counterparty, str(counterparty_id))
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="counterparty not found")
    core = db.get(LegalEntity, counterparty.legal_entity_id)
    out = _counterparty_out(counterparty)
    return CounterpartyDetailOut(
        **out.model_dump(),
        legal_entity_code=core.code if core else "",
        legal_entity_name=core.name if core else "",
        lei=core.lei if core else None,
    )
