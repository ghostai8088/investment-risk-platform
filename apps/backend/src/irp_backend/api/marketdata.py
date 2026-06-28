"""Market-data endpoints — captured FR FX rates (P2-2, ENT-024) + price history (P2-4, ENT-020).

Thin layer over ``irp_shared.marketdata``. PROPRIETARY tenant-scoped (NEVER hybrid), FR (NOT
append-only). Writes are gated ``marketdata.ingest`` (the governed canonical-write verb); reads +
``convert`` are gated ``marketdata.view`` (the SAME two verbs are REUSED for prices). ``tenant_id``
server-stamped; the instrument FK + currencies are resolved tenant-/hybrid-aware (→ 404); a single
end-of-request ``db.commit()`` on writes. There is **no PUT/PATCH/DELETE** — a rate/price is
*superseded* (effective-dated re-quote) or *corrected* (as-known restatement), both append NEW
versions. ``convert`` is published-rate arithmetic only (direct / reciprocal /
triangulation-through-base, fail-closed). Prices are **captured RAW** — NO conversion, NO pricing/
valuation model, NO exposure, NO ``calculation_run``, no audit on read.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import (
    DEFAULT_BASE,
    PRICE_TYPE_CLOSE,
    RATE_TYPE_MID,
    FxRate,
    FxRateActor,
    FxRateNotFound,
    FxRateNotVisible,
    FxRateValueError,
    NoCurrentFxRate,
    NoCurrentPrice,
    PriceActor,
    PriceNotVisible,
    PricePoint,
    PriceValueError,
    capture_fx_rate,
    capture_price,
    convert,
    correct_fx_rate,
    correct_price,
    reconstruct_fx_rate_as_of,
    reconstruct_price_as_of,
    resolve_fx_rate,
    resolve_price,
    supersede_fx_rate,
    supersede_price,
)
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.reference.service import CurrencyNotVisible

router = APIRouter(prefix="/fx", tags=["marketdata"])
price_router = APIRouter(prefix="/prices", tags=["marketdata"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_ingest = require_permission("marketdata.ingest")
_require_view = require_permission("marketdata.view")


def _actor(principal: Principal) -> FxRateActor:
    return FxRateActor(actor_id=principal.user_id)


class FxRateIn(BaseModel):
    base_currency: str
    quote_currency: str
    rate_date: date
    rate: Decimal
    rate_type: str = RATE_TYPE_MID
    valid_from: datetime | None = None
    rate_source: str | None = None


class FxSupersedeIn(BaseModel):
    effective_at: datetime
    rate: Decimal | None = None  # only fields set here override the carried-forward prior rate
    rate_source: str | None = None


class FxCorrectIn(BaseModel):
    restatement_reason: str
    rate: Decimal | None = None
    rate_source: str | None = None


class FxRateOut(BaseModel):
    id: str
    base_currency: str
    quote_currency: str
    rate_date: date
    rate: Decimal
    rate_type: str
    rate_source: str | None
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    restatement_reason: str | None
    supersedes_id: str | None
    record_version: int


class ConvertOut(BaseModel):
    amount: Decimal
    from_currency: str
    to_currency: str
    converted_amount: Decimal
    rate_type: str
    rate_path: list[str]


def _out(row: FxRate) -> FxRateOut:
    return FxRateOut(
        id=row.id,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate_date=row.rate_date,
        rate=row.rate,
        rate_type=row.rate_type,
        rate_source=row.rate_source,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        restatement_reason=row.restatement_reason,
        supersedes_id=row.supersedes_id,
        record_version=row.record_version,
    )


#: Governed-write error → (status, detail). Fail-closed; rolls back before mapping.
_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    FxRateValueError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid fx_rate input"),
    CurrencyNotVisible: (status.HTTP_404_NOT_FOUND, "currency not found"),
    FxRateNotVisible: (status.HTTP_404_NOT_FOUND, "fx_rate not found"),
    NoCurrentFxRate: (status.HTTP_409_CONFLICT, "no current fx_rate version to supersede"),
    DataQualityError: (status.HTTP_409_CONFLICT, "fx_rate failed a data-quality gate"),
}


def _raise_write(db: Session, exc: Exception) -> None:
    db.rollback()  # whole-unit rollback (CTRL-032) before mapping
    code, detail = _WRITE_ERRORS[type(exc)]
    raise HTTPException(status_code=code, detail=detail) from None


@router.post("", response_model=FxRateOut, status_code=status.HTTP_201_CREATED)
def create_fx_rate(
    body: FxRateIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FxRateOut:
    """Capture an FX rate (governed: VENDOR-source ORIGIN lineage + MARKET.FX_CREATE + the DQ
    gate)."""
    try:
        row = capture_fx_rate(
            db,
            base_currency=body.base_currency,
            quote_currency=body.quote_currency,
            rate_date=body.rate_date,
            rate=body.rate,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            rate_type=body.rate_type,
            valid_from=body.valid_from,
            rate_source=body.rate_source,
        )
    except (FxRateValueError, CurrencyNotVisible, DataQualityError) as exc:
        _raise_write(db, exc)
    out = _out(row)
    db.commit()
    return out


@router.post(
    "/{fx_rate_id}/supersede", response_model=FxRateOut, status_code=status.HTTP_201_CREATED
)
def supersede_fx_rate_endpoint(
    fx_rate_id: str,
    body: FxSupersedeIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FxRateOut:
    """Effective-dated re-quote for the SAME (pair, rate_date, rate_type) of an existing head."""
    try:
        prior = resolve_fx_rate(db, fx_rate_id, acting_tenant=principal.tenant_id)
        overrides = body.model_dump(exclude_none=True, exclude={"effective_at"})
        row = supersede_fx_rate(
            db,
            base_currency=prior.base_currency,
            quote_currency=prior.quote_currency,
            rate_date=prior.rate_date,
            rate_type=prior.rate_type,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            effective_at=body.effective_at,
            **overrides,
        )
    except (
        FxRateValueError,
        CurrencyNotVisible,
        FxRateNotVisible,
        NoCurrentFxRate,
        DataQualityError,
    ) as exc:
        _raise_write(db, exc)
    out = _out(row)
    db.commit()
    return out


@router.post("/{fx_rate_id}/correct", response_model=FxRateOut, status_code=status.HTTP_201_CREATED)
def correct_fx_rate_endpoint(
    fx_rate_id: str,
    body: FxCorrectIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FxRateOut:
    """As-known vendor restatement of a specific fx_rate version (same valid period + logical
    key)."""
    try:
        prior = resolve_fx_rate(db, fx_rate_id, acting_tenant=principal.tenant_id)
        overrides = body.model_dump(exclude_none=True, exclude={"restatement_reason"})
        row = correct_fx_rate(
            db,
            prior,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            **overrides,
        )
    except (FxRateValueError, CurrencyNotVisible, FxRateNotVisible, DataQualityError) as exc:
        _raise_write(db, exc)
    out = _out(row)
    db.commit()
    return out


@router.get("/as-of", response_model=FxRateOut)
def get_fx_as_of(
    base_currency: str = Query(...),
    quote_currency: str = Query(...),
    rate_date: date = Query(...),
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(default=None),
    rate_type: str = Query(default=RATE_TYPE_MID),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> FxRateOut:
    """The single head rate for a logical key as-of (valid_at, known_at) — 404 if none."""
    row = reconstruct_fx_rate_as_of(
        db,
        acting_tenant=principal.tenant_id,
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate_date=rate_date,
        valid_at=valid_at,
        rate_type=rate_type,
        known_at=known_at,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="fx_rate not found")
    return _out(row)


@router.get("", response_model=list[FxRateOut])
def list_fx_rates(
    base_currency: str = Query(...),
    quote_currency: str = Query(...),
    rate_date_from: date = Query(...),
    rate_date_to: date = Query(...),
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(default=None),
    rate_type: str = Query(default=RATE_TYPE_MID),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[FxRateOut]:
    """The as-of head rate for each rate_date in [from, to] for a (pair, rate_type) — read-only."""
    from irp_shared.db.mixins import utcnow

    known = known_at or utcnow()
    rows = (
        db.execute(
            select(FxRate)
            .where(
                FxRate.tenant_id == str(principal.tenant_id),
                FxRate.base_currency == base_currency,
                FxRate.quote_currency == quote_currency,
                FxRate.rate_type == rate_type,
                FxRate.rate_date >= rate_date_from,
                FxRate.rate_date <= rate_date_to,
                FxRate.valid_from <= valid_at,
                or_(FxRate.valid_to.is_(None), FxRate.valid_to > valid_at),
                FxRate.system_from <= known,
                or_(FxRate.system_to.is_(None), FxRate.system_to > known),
            )
            .order_by(FxRate.rate_date)
        )
        .scalars()
        .all()
    )
    return [_out(row) for row in rows]


@router.get("/convert", response_model=ConvertOut)
def convert_fx(
    amount: Decimal = Query(...),
    from_currency: str = Query(...),
    to_currency: str = Query(...),
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(default=None),
    base: str = Query(default=DEFAULT_BASE),
    rate_type: str = Query(default=RATE_TYPE_MID),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ConvertOut:
    """Convert an amount between currencies as-of using PUBLISHED rates only (direct / reciprocal /
    triangulation-through-base). Read-only (no audit/lineage/DQ); fails closed → 404 if no path."""
    try:
        result = convert(
            db,
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            valid_at=valid_at,
            acting_tenant=principal.tenant_id,
            known_at=known_at,
            base=base,
            rate_type=rate_type,
        )
    except FxRateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no published FX path as-of"
        ) from None
    return ConvertOut(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        converted_amount=result.converted_amount,
        rate_type=result.rate_type,
        rate_path=result.rate_path,
    )


# --- Price history (P2-4, ENT-020) — captured RAW vendor prices on the FR protocol -------------


def _price_actor(principal: Principal) -> PriceActor:
    return PriceActor(actor_id=principal.user_id)


class PriceIn(BaseModel):
    instrument_id: str
    price_date: date
    price: Decimal
    currency_code: str
    price_source: str
    price_type: str = PRICE_TYPE_CLOSE
    valid_from: datetime | None = None


class PriceSupersedeIn(BaseModel):
    effective_at: datetime
    price: Decimal | None = None  # only fields set here override the carried-forward prior price


class PriceCorrectIn(BaseModel):
    restatement_reason: str
    price: Decimal | None = None


class PriceOut(BaseModel):
    id: str
    instrument_id: str
    price_date: date
    price: Decimal
    price_type: str
    currency_code: str
    price_source: str
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    restatement_reason: str | None
    supersedes_id: str | None
    record_version: int


def _price_out(row: PricePoint) -> PriceOut:
    return PriceOut(
        id=row.id,
        instrument_id=row.instrument_id,
        price_date=row.price_date,
        price=row.price,
        price_type=row.price_type,
        currency_code=row.currency_code,
        price_source=row.price_source,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        restatement_reason=row.restatement_reason,
        supersedes_id=row.supersedes_id,
        record_version=row.record_version,
    )


#: Governed-write error → (status, detail). Fail-closed; rolls back before mapping.
_PRICE_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    PriceValueError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid price_point input"),
    InstrumentNotVisible: (status.HTTP_404_NOT_FOUND, "instrument not found"),
    CurrencyNotVisible: (status.HTTP_404_NOT_FOUND, "currency not found"),
    PriceNotVisible: (status.HTTP_404_NOT_FOUND, "price_point not found"),
    NoCurrentPrice: (status.HTTP_409_CONFLICT, "no current price_point version to supersede"),
    DataQualityError: (status.HTTP_409_CONFLICT, "price_point failed a data-quality gate"),
}


def _raise_price_write(db: Session, exc: Exception) -> None:
    db.rollback()  # whole-unit rollback (CTRL-032) before mapping
    code, detail = _PRICE_WRITE_ERRORS[type(exc)]
    raise HTTPException(status_code=code, detail=detail) from None


@price_router.post("", response_model=PriceOut, status_code=status.HTTP_201_CREATED)
def create_price(
    body: PriceIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> PriceOut:
    """Capture a price (governed: VENDOR-source ORIGIN lineage + MARKET.PRICE_CREATE + the DQ
    gate)."""
    try:
        row = capture_price(
            db,
            instrument_id=body.instrument_id,
            price_date=body.price_date,
            price=body.price,
            currency_code=body.currency_code,
            price_source=body.price_source,
            acting_tenant=principal.tenant_id,
            actor=_price_actor(principal),
            price_type=body.price_type,
            valid_from=body.valid_from,
        )
    except (PriceValueError, InstrumentNotVisible, CurrencyNotVisible, DataQualityError) as exc:
        _raise_price_write(db, exc)
    out = _price_out(row)
    db.commit()
    return out


@price_router.post(
    "/{price_id}/supersede", response_model=PriceOut, status_code=status.HTTP_201_CREATED
)
def supersede_price_endpoint(
    price_id: str,
    body: PriceSupersedeIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> PriceOut:
    """Effective-dated re-price for the SAME logical key of an existing head."""
    try:
        prior = resolve_price(db, price_id, acting_tenant=principal.tenant_id)
        overrides = body.model_dump(exclude_none=True, exclude={"effective_at"})
        row = supersede_price(
            db,
            instrument_id=prior.instrument_id,
            price_date=prior.price_date,
            price_type=prior.price_type,
            currency_code=prior.currency_code,
            price_source=prior.price_source,
            acting_tenant=principal.tenant_id,
            actor=_price_actor(principal),
            effective_at=body.effective_at,
            **overrides,
        )
    except (
        PriceValueError,
        InstrumentNotVisible,
        CurrencyNotVisible,
        PriceNotVisible,
        NoCurrentPrice,
        DataQualityError,
    ) as exc:
        _raise_price_write(db, exc)
    out = _price_out(row)
    db.commit()
    return out


@price_router.post(
    "/{price_id}/correct", response_model=PriceOut, status_code=status.HTTP_201_CREATED
)
def correct_price_endpoint(
    price_id: str,
    body: PriceCorrectIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> PriceOut:
    """As-known vendor restatement of a specific price_point version (same valid period + logical
    key)."""
    try:
        prior = resolve_price(db, price_id, acting_tenant=principal.tenant_id)
        overrides = body.model_dump(exclude_none=True, exclude={"restatement_reason"})
        row = correct_price(
            db,
            prior,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_price_actor(principal),
            **overrides,
        )
    except (
        PriceValueError,
        InstrumentNotVisible,
        CurrencyNotVisible,
        PriceNotVisible,
        DataQualityError,
    ) as exc:
        _raise_price_write(db, exc)
    out = _price_out(row)
    db.commit()
    return out


@price_router.get("/as-of", response_model=PriceOut)
def get_price_as_of(
    instrument_id: str = Query(...),
    price_date: date = Query(...),
    currency_code: str = Query(...),
    price_source: str = Query(...),
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(default=None),
    price_type: str = Query(default=PRICE_TYPE_CLOSE),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PriceOut:
    """The single head price for a logical key as-of (valid_at, known_at) — 404 if none."""
    row = reconstruct_price_as_of(
        db,
        acting_tenant=principal.tenant_id,
        instrument_id=instrument_id,
        price_date=price_date,
        price_type=price_type,
        currency_code=currency_code,
        price_source=price_source,
        valid_at=valid_at,
        known_at=known_at,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="price_point not found")
    return _price_out(row)


@price_router.get("", response_model=list[PriceOut])
def list_prices(
    instrument_id: str = Query(...),
    price_date_from: date = Query(...),
    price_date_to: date = Query(...),
    currency_code: str = Query(...),
    price_source: str = Query(...),
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(default=None),
    price_type: str = Query(default=PRICE_TYPE_CLOSE),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[PriceOut]:
    """The as-of head price for each price_date in [from, to] for a logical key — read-only."""
    from irp_shared.db.mixins import utcnow

    known = known_at or utcnow()
    rows = (
        db.execute(
            select(PricePoint)
            .where(
                PricePoint.tenant_id == str(principal.tenant_id),
                PricePoint.instrument_id == instrument_id,
                PricePoint.price_type == price_type,
                PricePoint.currency_code == currency_code,
                PricePoint.price_source == price_source,
                PricePoint.price_date >= price_date_from,
                PricePoint.price_date <= price_date_to,
                PricePoint.valid_from <= valid_at,
                or_(PricePoint.valid_to.is_(None), PricePoint.valid_to > valid_at),
                PricePoint.system_from <= known,
                or_(PricePoint.system_to.is_(None), PricePoint.system_to > known),
            )
            .order_by(PricePoint.price_date)
        )
        .scalars()
        .all()
    )
    return [_price_out(row) for row in rows]
