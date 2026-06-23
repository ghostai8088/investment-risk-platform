"""Reference instrument / instrument_terms / identifier endpoints (P1B-3, REQ-SMR-001/003).

A THIRD ``APIRouter(prefix="/reference")`` (the P1B-1 ``api/reference.py`` and P1B-2
``api/reference_entities.py`` routers are both untouched); the sub-paths ``/instruments*``,
``/identifier-xrefs``, ``/identifiers/resolve`` are disjoint from both. These three entities are
PROPRIETARY tenant-scoped (NEVER hybrid) — no ``DISTINCT ON`` dedup. Each write is gated
deny-by-default; ``tenant_id`` is server-stamped from the principal (never the body); a single
end-of-request ``db.commit()``. The terms ``POST`` dispatches create / effective-dated supersede /
as-known correction; ``/terms/as-of`` is the FR bitemporal reconstruction; ``/identifiers/resolve``
returns 200 (one) / 404 (none) / 409 (ambiguous). No PUT/DELETE/bulk/search.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.reference.identifier import (
    AmbiguousIdentifier,
    create_identifier_xref,
    resolve_identifier,
)
from irp_shared.reference.instrument import (
    InstrumentNotVisible,
    create_instrument,
)
from irp_shared.reference.instrument_terms import (
    TERM_FIELDS,
    NoCurrentTerms,
    correct_instrument_terms,
    create_instrument_terms,
    reconstruct_terms_as_of,
    supersede_instrument_terms,
)
from irp_shared.reference.issuer import IssuerNotVisible
from irp_shared.reference.models import IdentifierXref, Instrument, InstrumentTerms
from irp_shared.reference.service import ReferenceActor

router = APIRouter(prefix="/reference", tags=["reference-instruments"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_instr_edit = require_permission("reference.instrument.edit")
_require_instr_view = require_permission("reference.instrument.view")
_require_ident_edit = require_permission("reference.identifier.edit")
_require_ident_resolve = require_permission("reference.identifier.resolve")


def _actor(principal: Principal) -> ReferenceActor:
    return ReferenceActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


# --------------------------------------------------------------------------- instrument


class InstrumentIn(BaseModel):
    code: str
    name: str
    asset_class: str
    instrument_type: str | None = None
    issuer_id: uuid.UUID | None = None  # malformed -> 422
    currency_code: str | None = None
    is_active: bool = True


class InstrumentOut(BaseModel):
    id: str
    code: str
    name: str
    asset_class: str
    instrument_type: str | None
    issuer_id: str | None
    currency_code: str | None
    is_active: bool


def _instrument_out(i: Instrument) -> InstrumentOut:
    return InstrumentOut(
        id=i.id,
        code=i.code,
        name=i.name,
        asset_class=i.asset_class,
        instrument_type=i.instrument_type,
        issuer_id=i.issuer_id,
        currency_code=i.currency_code,
        is_active=i.is_active,
    )


@router.post("/instruments", status_code=status.HTTP_201_CREATED, response_model=InstrumentOut)
def create_instrument_endpoint(
    body: InstrumentIn,
    principal: Principal = Depends(_require_instr_edit),
    db: Session = Depends(get_tenant_session),
) -> InstrumentOut:
    try:
        instrument = create_instrument(
            db,
            tenant_id=principal.tenant_id,  # server-stamped; body has no tenant_id
            code=body.code,
            name=body.name,
            asset_class=body.asset_class,
            actor=_actor(principal),
            instrument_type=body.instrument_type,
            issuer_id=(str(body.issuer_id) if body.issuer_id else None),
            currency_code=body.currency_code,
            is_active=body.is_active,
        )
    except IssuerNotVisible:  # cross-tenant/unknown issuer -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="issuer not found"
        ) from None
    db.commit()
    return _instrument_out(instrument)


@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(
    _: Principal = Depends(_require_instr_view),
    db: Session = Depends(get_tenant_session),
) -> list[InstrumentOut]:
    rows = db.execute(select(Instrument).order_by(Instrument.code)).scalars().all()
    return [_instrument_out(i) for i in rows]


@router.get("/instruments/{instrument_id}", response_model=InstrumentOut)
def get_instrument(
    instrument_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_instr_view),
    db: Session = Depends(get_tenant_session),
) -> InstrumentOut:
    instrument = db.get(Instrument, str(instrument_id))
    if instrument is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found")
    return _instrument_out(instrument)


# --------------------------------------------------------------------------- instrument_terms


class TermsIn(BaseModel):
    mode: Literal["create", "supersede", "correct"] = "create"
    effective_at: datetime | None = None  # required for supersede
    valid_from: datetime | None = None  # optional for create
    terms_id: uuid.UUID | None = None  # required for correct
    restatement_reason: str | None = None  # required for correct
    coupon_rate: Decimal | None = None
    coupon_frequency: str | None = None
    issue_date: Any | None = None
    maturity_date: Any | None = None
    day_count: str | None = None
    denomination_currency: str | None = None
    face_value: Decimal | None = None
    term_source: str | None = None

    def term_kwargs(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in TERM_FIELDS if getattr(self, f) is not None}


class TermsOut(BaseModel):
    id: str
    instrument_id: str
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    coupon_rate: Decimal | None
    coupon_frequency: str | None
    issue_date: Any | None
    maturity_date: Any | None
    day_count: str | None
    denomination_currency: str | None
    face_value: Decimal | None
    term_source: str | None
    restatement_reason: str | None
    supersedes_id: str | None
    record_version: int


def _terms_out(t: InstrumentTerms) -> TermsOut:
    return TermsOut(
        id=t.id,
        instrument_id=t.instrument_id,
        valid_from=t.valid_from,
        valid_to=t.valid_to,
        system_from=t.system_from,
        system_to=t.system_to,
        coupon_rate=t.coupon_rate,
        coupon_frequency=t.coupon_frequency,
        issue_date=t.issue_date,
        maturity_date=t.maturity_date,
        day_count=t.day_count,
        denomination_currency=t.denomination_currency,
        face_value=t.face_value,
        term_source=t.term_source,
        restatement_reason=t.restatement_reason,
        supersedes_id=t.supersedes_id,
        record_version=t.record_version,
    )


@router.post(
    "/instruments/{instrument_id}/terms",
    status_code=status.HTTP_201_CREATED,
    response_model=TermsOut,
)
def post_instrument_terms(
    instrument_id: uuid.UUID,
    body: TermsIn,
    principal: Principal = Depends(_require_instr_edit),
    db: Session = Depends(get_tenant_session),
) -> TermsOut:
    tenant = principal.tenant_id
    try:
        if body.mode == "create":
            row = create_instrument_terms(
                db,
                instrument_id=str(instrument_id),
                acting_tenant=tenant,
                actor=_actor(principal),
                valid_from=body.valid_from,
                **body.term_kwargs(),
            )
        elif body.mode == "supersede":
            if body.effective_at is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="effective_at is required for supersede",
                )
            row = supersede_instrument_terms(
                db,
                instrument_id=str(instrument_id),
                acting_tenant=tenant,
                actor=_actor(principal),
                effective_at=body.effective_at,
                **body.term_kwargs(),
            )
        else:  # correct
            if body.terms_id is None or not body.restatement_reason:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="terms_id and restatement_reason are required for correct",
                )
            prior = db.get(InstrumentTerms, str(body.terms_id))
            if prior is None or str(prior.instrument_id) != str(instrument_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="instrument_terms not found"
                )
            row = correct_instrument_terms(
                db,
                prior,
                restatement_reason=body.restatement_reason,
                acting_tenant=tenant,
                actor=_actor(principal),
                **body.term_kwargs(),
            )
    except InstrumentNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found"
        ) from None
    except NoCurrentTerms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no current terms to supersede"
        ) from None
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="instrument_terms conflict"
        ) from None
    db.commit()
    return _terms_out(row)


@router.get("/instruments/{instrument_id}/terms", response_model=list[TermsOut])
def list_instrument_terms(
    instrument_id: uuid.UUID,
    _: Principal = Depends(_require_instr_view),
    db: Session = Depends(get_tenant_session),
) -> list[TermsOut]:
    rows = (
        db.execute(
            select(InstrumentTerms)
            .where(InstrumentTerms.instrument_id == str(instrument_id))
            .order_by(InstrumentTerms.system_from)
        )
        .scalars()
        .all()
    )
    return [_terms_out(t) for t in rows]


@router.get("/instruments/{instrument_id}/terms/as-of", response_model=TermsOut)
def get_instrument_terms_as_of(
    instrument_id: uuid.UUID,
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(None),
    principal: Principal = Depends(_require_instr_view),
    db: Session = Depends(get_tenant_session),
) -> TermsOut:
    row = reconstruct_terms_as_of(
        db,
        str(instrument_id),
        acting_tenant=principal.tenant_id,
        valid_at=valid_at,
        known_at=known_at,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no terms as of the requested time"
        )
    return _terms_out(row)


# --------------------------------------------------------------------------- identifier_xref


class IdentifierXrefIn(BaseModel):
    instrument_id: uuid.UUID
    scheme: str
    value: str
    source: str | None = None
    valid_from: datetime | None = None
    is_active: bool = True


class IdentifierXrefOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    scheme: str
    value: str
    source: str | None
    is_active: bool


def _xref_out(x: IdentifierXref) -> IdentifierXrefOut:
    return IdentifierXrefOut(
        id=x.id,
        entity_type=x.entity_type,
        entity_id=x.entity_id,
        scheme=x.scheme,
        value=x.value,
        source=x.source,
        is_active=x.is_active,
    )


@router.post(
    "/identifier-xrefs", status_code=status.HTTP_201_CREATED, response_model=IdentifierXrefOut
)
def create_identifier_xref_endpoint(
    body: IdentifierXrefIn,
    principal: Principal = Depends(_require_ident_edit),
    db: Session = Depends(get_tenant_session),
) -> IdentifierXrefOut:
    try:
        xref = create_identifier_xref(
            db,
            tenant_id=principal.tenant_id,
            instrument_id=str(body.instrument_id),
            scheme=body.scheme,
            value=body.value,
            actor=_actor(principal),
            source=body.source,
            valid_from=body.valid_from,
            is_active=body.is_active,
        )
    except InstrumentNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found"
        ) from None
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="identifier already active"
        ) from None
    db.commit()
    return _xref_out(xref)


@router.get("/identifiers/resolve", response_model=InstrumentOut)
def resolve_identifier_endpoint(
    scheme: str = Query(...),
    value: str = Query(...),
    principal: Principal = Depends(_require_ident_resolve),
    db: Session = Depends(get_tenant_session),
) -> InstrumentOut:
    try:
        instrument = resolve_identifier(
            db, scheme=scheme, value=value, acting_tenant=principal.tenant_id
        )
    except AmbiguousIdentifier as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "ambiguous_identifier",
                "scheme": exc.scheme,
                "value": exc.value,
                "matches": exc.matched_entity_ids,
            },
        ) from None
    if instrument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="identifier not found")
    return _instrument_out(instrument)
