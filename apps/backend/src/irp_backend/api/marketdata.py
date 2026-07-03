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
    FREQUENCY_DAILY,
    PRICE_TYPE_CLOSE,
    RATE_TYPE_MID,
    REFERENCE_KEY_NONE,
    RETURN_TYPE_SIMPLE,
    Benchmark,
    BenchmarkActor,
    BenchmarkConstituent,
    BenchmarkNotVisible,
    BenchmarkValueError,
    ConstituentInput,
    Curve,
    CurveActor,
    CurveNode,
    CurveNotVisible,
    CurvePoint,
    CurveValueError,
    Factor,
    FactorActor,
    FactorNotVisible,
    FactorReturn,
    FactorValueError,
    FxRate,
    FxRateActor,
    FxRateNotFound,
    FxRateNotVisible,
    FxRateValueError,
    NoCurrentCurve,
    NoCurrentFactorReturn,
    NoCurrentFxRate,
    NoCurrentMembership,
    NoCurrentPrice,
    PriceActor,
    PriceNotVisible,
    PricePoint,
    PriceValueError,
    capture_benchmark,
    capture_curve,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    capture_membership,
    capture_price,
    convert,
    correct_curve,
    correct_factor_return,
    correct_fx_rate,
    correct_membership,
    correct_price,
    list_benchmarks,
    list_curve_points,
    list_factor_returns,
    list_factors,
    reconstruct_curve_as_of,
    reconstruct_factor_return_as_of,
    reconstruct_fx_rate_as_of,
    reconstruct_membership_as_of,
    reconstruct_price_as_of,
    resolve_benchmark,
    resolve_curve,
    resolve_factor,
    resolve_fx_rate,
    resolve_price,
    supersede_curve,
    supersede_factor_return,
    supersede_fx_rate,
    supersede_membership,
    supersede_price,
    update_benchmark,
    update_factor,
)
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.reference.service import CurrencyNotVisible

router = APIRouter(prefix="/fx", tags=["marketdata"])
price_router = APIRouter(prefix="/prices", tags=["marketdata"])
curve_router = APIRouter(prefix="/curves", tags=["marketdata"])
benchmark_router = APIRouter(prefix="/benchmarks", tags=["marketdata"])
factor_router = APIRouter(prefix="/factors", tags=["marketdata"])

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


# --- Curves (P2-5, ENT-021/023) — captured RAW vendor yield/spread curves on the FR protocol ---


def _curve_actor(principal: Principal) -> CurveActor:
    return CurveActor(actor_id=principal.user_id)


class CurveNodeIn(BaseModel):
    tenor_label: str
    tenor_days: int
    value_type: str
    point_value: Decimal


class CurveIn(BaseModel):
    curve_type: str
    currency_code: str
    curve_date: date
    curve_source: str
    nodes: list[CurveNodeIn]
    reference_key: str = REFERENCE_KEY_NONE
    interpolation_method: str | None = None
    valid_from: datetime | None = None


class CurveReversionIn(BaseModel):
    nodes: list[CurveNodeIn]
    interpolation_method: str | None = None


class CurveSupersedeIn(CurveReversionIn):
    effective_at: datetime


class CurveCorrectIn(CurveReversionIn):
    restatement_reason: str


class CurveNodeOut(BaseModel):
    tenor_label: str
    tenor_days: int
    value_type: str
    point_value: Decimal


class CurveOut(BaseModel):
    id: str
    curve_type: str
    currency_code: str
    reference_key: str
    curve_date: date
    curve_source: str
    interpolation_method: str | None
    point_count: int
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    restatement_reason: str | None
    supersedes_id: str | None
    record_version: int
    nodes: list[CurveNodeOut]


def _nodes_in(body_nodes: list[CurveNodeIn]) -> list[CurveNode]:
    return [
        CurveNode(
            tenor_label=n.tenor_label,
            tenor_days=n.tenor_days,
            value_type=n.value_type,
            point_value=n.point_value,
        )
        for n in body_nodes
    ]


def _curve_out(header: Curve, points: list[CurvePoint]) -> CurveOut:
    return CurveOut(
        id=header.id,
        curve_type=header.curve_type,
        currency_code=header.currency_code,
        reference_key=header.reference_key,
        curve_date=header.curve_date,
        curve_source=header.curve_source,
        interpolation_method=header.interpolation_method,
        point_count=header.point_count,
        valid_from=header.valid_from,
        valid_to=header.valid_to,
        system_from=header.system_from,
        system_to=header.system_to,
        restatement_reason=header.restatement_reason,
        supersedes_id=header.supersedes_id,
        record_version=header.record_version,
        nodes=[
            CurveNodeOut(
                tenor_label=p.tenor_label,
                tenor_days=p.tenor_days,
                value_type=p.value_type,
                point_value=p.point_value,
            )
            for p in points
        ],
    )


#: Governed-write error → (status, detail). Fail-closed; rolls back before mapping.
_CURVE_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    CurveValueError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid curve input"),
    CurrencyNotVisible: (status.HTTP_404_NOT_FOUND, "currency not found"),
    CurveNotVisible: (status.HTTP_404_NOT_FOUND, "curve not found"),
    NoCurrentCurve: (status.HTTP_409_CONFLICT, "no current curve version to supersede"),
    DataQualityError: (status.HTTP_409_CONFLICT, "curve failed a data-quality gate"),
}


def _raise_curve_write(db: Session, exc: Exception) -> None:
    db.rollback()  # whole-unit rollback (CTRL-032) before mapping
    code, detail = _CURVE_WRITE_ERRORS[type(exc)]
    raise HTTPException(status_code=code, detail=detail) from None


def _curve_with_nodes(db: Session, header: Curve, principal: Principal) -> CurveOut:
    points = list_curve_points(db, header.id, acting_tenant=principal.tenant_id)
    return _curve_out(header, points)


@curve_router.post("", response_model=CurveOut, status_code=status.HTTP_201_CREATED)
def create_curve(
    body: CurveIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> CurveOut:
    """Capture a curve (header + its node set, one governed unit: VENDOR-source ORIGIN lineage +
    MARKET.CURVE_CREATE + the DQ gate)."""
    try:
        header = capture_curve(
            db,
            curve_type=body.curve_type,
            currency_code=body.currency_code,
            curve_date=body.curve_date,
            curve_source=body.curve_source,
            nodes=_nodes_in(body.nodes),
            acting_tenant=principal.tenant_id,
            actor=_curve_actor(principal),
            reference_key=body.reference_key,
            interpolation_method=body.interpolation_method,
            valid_from=body.valid_from,
        )
    except (CurveValueError, CurrencyNotVisible, DataQualityError) as exc:
        _raise_curve_write(db, exc)
    out = _curve_with_nodes(db, header, principal)
    db.commit()
    return out


@curve_router.post(
    "/{curve_id}/supersede", response_model=CurveOut, status_code=status.HTTP_201_CREATED
)
def supersede_curve_endpoint(
    curve_id: str,
    body: CurveSupersedeIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> CurveOut:
    """Effective-dated re-capture for the SAME logical key of an existing head (new version + fresh
    node set)."""
    try:
        prior = resolve_curve(db, curve_id, acting_tenant=principal.tenant_id)
        header = supersede_curve(
            db,
            curve_type=prior.curve_type,
            currency_code=prior.currency_code,
            curve_date=prior.curve_date,
            curve_source=prior.curve_source,
            nodes=_nodes_in(body.nodes),
            acting_tenant=principal.tenant_id,
            actor=_curve_actor(principal),
            effective_at=body.effective_at,
            reference_key=prior.reference_key,
            interpolation_method=body.interpolation_method,
        )
    except (
        CurveValueError,
        CurrencyNotVisible,
        CurveNotVisible,
        NoCurrentCurve,
        DataQualityError,
    ) as exc:
        _raise_curve_write(db, exc)
    out = _curve_with_nodes(db, header, principal)
    db.commit()
    return out


@curve_router.post(
    "/{curve_id}/correct", response_model=CurveOut, status_code=status.HTTP_201_CREATED
)
def correct_curve_endpoint(
    curve_id: str,
    body: CurveCorrectIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> CurveOut:
    """As-known vendor restatement of a specific curve version (same valid period + logical key +
    fresh node set)."""
    try:
        prior = resolve_curve(db, curve_id, acting_tenant=principal.tenant_id)
        header = correct_curve(
            db,
            prior,
            restatement_reason=body.restatement_reason,
            nodes=_nodes_in(body.nodes),
            acting_tenant=principal.tenant_id,
            actor=_curve_actor(principal),
            interpolation_method=body.interpolation_method,
        )
    except (CurveValueError, CurrencyNotVisible, CurveNotVisible, DataQualityError) as exc:
        _raise_curve_write(db, exc)
    out = _curve_with_nodes(db, header, principal)
    db.commit()
    return out


@curve_router.get("/as-of", response_model=CurveOut)
def get_curve_as_of(
    curve_type: str = Query(...),
    currency_code: str = Query(...),
    curve_date: date = Query(...),
    curve_source: str = Query(...),
    valid_at: datetime = Query(...),
    reference_key: str = Query(default=REFERENCE_KEY_NONE),
    known_at: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CurveOut:
    """The single head curve (header + pinned nodes) for a logical key as-of (valid_at, known_at)
    — 404 if none."""
    header = reconstruct_curve_as_of(
        db,
        acting_tenant=principal.tenant_id,
        curve_type=curve_type,
        currency_code=currency_code,
        curve_date=curve_date,
        curve_source=curve_source,
        valid_at=valid_at,
        reference_key=reference_key,
        known_at=known_at,
    )
    if header is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="curve not found")
    return _curve_with_nodes(db, header, principal)


@curve_router.get("", response_model=list[CurveOut])
def list_curves(
    curve_type: str = Query(...),
    currency_code: str = Query(...),
    curve_date_from: date = Query(...),
    curve_date_to: date = Query(...),
    curve_source: str = Query(...),
    valid_at: datetime = Query(...),
    reference_key: str = Query(default=REFERENCE_KEY_NONE),
    known_at: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[CurveOut]:
    """The as-of head curve (header + nodes) for each curve_date in [from, to] for a logical key —
    read-only."""
    from irp_shared.db.mixins import utcnow

    known = known_at or utcnow()
    headers = (
        db.execute(
            select(Curve)
            .where(
                Curve.tenant_id == str(principal.tenant_id),
                Curve.curve_type == curve_type,
                Curve.currency_code == currency_code,
                Curve.reference_key == reference_key,
                Curve.curve_source == curve_source,
                Curve.curve_date >= curve_date_from,
                Curve.curve_date <= curve_date_to,
                Curve.valid_from <= valid_at,
                or_(Curve.valid_to.is_(None), Curve.valid_to > valid_at),
                Curve.system_from <= known,
                or_(Curve.system_to.is_(None), Curve.system_to > known),
            )
            .order_by(Curve.curve_date)
        )
        .scalars()
        .all()
    )
    return [_curve_with_nodes(db, h, principal) for h in headers]


# --- Benchmarks (P2-6, ENT-009) — captured benchmark/index definitions + FR membership ---
# Governance family split (OQ-P2-6-11 Option A): the EV definition is audited REFERENCE.*; the FR
# membership is audited MARKET.BENCHMARK_CONSTITUENT_*. Entitlement reuses marketdata.view/.ingest.


def _benchmark_actor(principal: Principal) -> BenchmarkActor:
    return BenchmarkActor(actor_id=principal.user_id)


class BenchmarkIn(BaseModel):
    benchmark_code: str
    benchmark_source: str
    benchmark_currency: str
    benchmark_name: str | None = None
    index_family: str | None = None
    vendor_code: str | None = None
    methodology_label: str | None = None


class BenchmarkUpdateIn(BaseModel):
    benchmark_currency: str | None = None
    benchmark_name: str | None = None
    index_family: str | None = None
    vendor_code: str | None = None
    methodology_label: str | None = None


class BenchmarkOut(BaseModel):
    id: str
    benchmark_code: str
    benchmark_source: str
    benchmark_currency: str
    benchmark_name: str | None
    index_family: str | None
    vendor_code: str | None
    methodology_label: str | None
    valid_from: datetime
    valid_to: datetime | None
    record_version: int


class ConstituentIn(BaseModel):
    instrument_id: str
    weight: Decimal
    constituent_currency: str | None = None


class ConstituentOut(BaseModel):
    instrument_id: str
    weight: Decimal
    constituent_currency: str | None
    effective_date: date
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    supersedes_id: str | None
    record_version: int


class MembershipIn(BaseModel):
    effective_date: date
    constituents: list[ConstituentIn]


class MembershipSupersedeIn(MembershipIn):
    effective_at: datetime


class MembershipCorrectIn(MembershipIn):
    restatement_reason: str


class MembershipOut(BaseModel):
    benchmark_id: str
    effective_date: date
    constituents: list[ConstituentOut]


def _constituents_in(body_constituents: list[ConstituentIn]) -> list[ConstituentInput]:
    return [
        ConstituentInput(
            instrument_id=c.instrument_id,
            weight=c.weight,
            constituent_currency=c.constituent_currency,
        )
        for c in body_constituents
    ]


def _benchmark_out(row: Benchmark) -> BenchmarkOut:
    return BenchmarkOut(
        id=row.id,
        benchmark_code=row.benchmark_code,
        benchmark_source=row.benchmark_source,
        benchmark_currency=row.benchmark_currency,
        benchmark_name=row.benchmark_name,
        index_family=row.index_family,
        vendor_code=row.vendor_code,
        methodology_label=row.methodology_label,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        record_version=row.record_version,
    )


def _constituent_out(row: BenchmarkConstituent) -> ConstituentOut:
    return ConstituentOut(
        instrument_id=row.instrument_id,
        weight=row.weight,
        constituent_currency=row.constituent_currency,
        effective_date=row.effective_date,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        supersedes_id=row.supersedes_id,
        record_version=row.record_version,
    )


def _membership_out(
    benchmark_id: str, effective_date: date, rows: list[BenchmarkConstituent]
) -> MembershipOut:
    return MembershipOut(
        benchmark_id=benchmark_id,
        effective_date=effective_date,
        constituents=[_constituent_out(r) for r in rows],
    )


#: Governed-write error → (status, detail). Fail-closed; rolls back before mapping.
_BENCHMARK_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    BenchmarkValueError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid benchmark input"),
    CurrencyNotVisible: (status.HTTP_404_NOT_FOUND, "currency not found"),
    InstrumentNotVisible: (status.HTTP_404_NOT_FOUND, "instrument not found"),
    BenchmarkNotVisible: (status.HTTP_404_NOT_FOUND, "benchmark not found"),
    NoCurrentMembership: (status.HTTP_409_CONFLICT, "no current membership to supersede/correct"),
    DataQualityError: (status.HTTP_409_CONFLICT, "benchmark failed a data-quality gate"),
}


def _raise_benchmark_write(db: Session, exc: Exception) -> None:
    db.rollback()  # whole-unit rollback (CTRL-032) before mapping
    code, detail = _BENCHMARK_WRITE_ERRORS[type(exc)]
    raise HTTPException(status_code=code, detail=detail) from None


@benchmark_router.post("", response_model=BenchmarkOut, status_code=status.HTTP_201_CREATED)
def create_benchmark(
    body: BenchmarkIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> BenchmarkOut:
    """Capture a benchmark DEFINITION (EV; REFERENCE.CREATE + VENDOR_BENCHMARK ORIGIN lineage)."""
    try:
        row = capture_benchmark(
            db,
            benchmark_code=body.benchmark_code,
            benchmark_source=body.benchmark_source,
            benchmark_currency=body.benchmark_currency,
            acting_tenant=principal.tenant_id,
            actor=_benchmark_actor(principal),
            benchmark_name=body.benchmark_name,
            index_family=body.index_family,
            vendor_code=body.vendor_code,
            methodology_label=body.methodology_label,
        )
    except (BenchmarkValueError, CurrencyNotVisible) as exc:
        _raise_benchmark_write(db, exc)
    out = _benchmark_out(row)
    db.commit()
    return out


@benchmark_router.post("/{benchmark_id}/update", response_model=BenchmarkOut)
def update_benchmark_endpoint(
    benchmark_id: str,
    body: BenchmarkUpdateIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> BenchmarkOut:
    """Apply attribute changes to a benchmark DEFINITION in place (EV; REFERENCE.UPDATE)."""
    try:
        row = resolve_benchmark(db, benchmark_id, acting_tenant=principal.tenant_id)
        update_benchmark(
            db,
            row,
            acting_tenant=principal.tenant_id,
            actor=_benchmark_actor(principal),
            **body.model_dump(exclude_unset=True),
        )
    except (BenchmarkValueError, BenchmarkNotVisible, CurrencyNotVisible) as exc:
        _raise_benchmark_write(db, exc)
    out = _benchmark_out(row)
    db.commit()
    return out


@benchmark_router.post(
    "/{benchmark_id}/membership", response_model=MembershipOut, status_code=status.HTTP_201_CREATED
)
def capture_membership_endpoint(
    benchmark_id: str,
    body: MembershipIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> MembershipOut:
    """Capture a membership set for (benchmark, effective_date) as ONE governed unit."""
    try:
        benchmark = resolve_benchmark(db, benchmark_id, acting_tenant=principal.tenant_id)
        rows = capture_membership(
            db,
            benchmark,
            effective_date=body.effective_date,
            constituents=_constituents_in(body.constituents),
            acting_tenant=principal.tenant_id,
            actor=_benchmark_actor(principal),
        )
    except (
        BenchmarkValueError,
        BenchmarkNotVisible,
        InstrumentNotVisible,
        CurrencyNotVisible,
        DataQualityError,
    ) as exc:
        _raise_benchmark_write(db, exc)
    out = _membership_out(benchmark_id, body.effective_date, rows)
    db.commit()
    return out


@benchmark_router.post(
    "/{benchmark_id}/membership/supersede",
    response_model=MembershipOut,
    status_code=status.HTTP_201_CREATED,
)
def supersede_membership_endpoint(
    benchmark_id: str,
    body: MembershipSupersedeIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> MembershipOut:
    """Effective-dated re-capture of a (benchmark, effective_date) membership (fresh set)."""
    try:
        benchmark = resolve_benchmark(db, benchmark_id, acting_tenant=principal.tenant_id)
        rows = supersede_membership(
            db,
            benchmark,
            effective_date=body.effective_date,
            constituents=_constituents_in(body.constituents),
            acting_tenant=principal.tenant_id,
            actor=_benchmark_actor(principal),
            effective_at=body.effective_at,
        )
    except (
        BenchmarkValueError,
        BenchmarkNotVisible,
        InstrumentNotVisible,
        CurrencyNotVisible,
        NoCurrentMembership,
        DataQualityError,
    ) as exc:
        _raise_benchmark_write(db, exc)
    out = _membership_out(benchmark_id, body.effective_date, rows)
    db.commit()
    return out


@benchmark_router.post(
    "/{benchmark_id}/membership/correct",
    response_model=MembershipOut,
    status_code=status.HTTP_201_CREATED,
)
def correct_membership_endpoint(
    benchmark_id: str,
    body: MembershipCorrectIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> MembershipOut:
    """As-known restatement of a (benchmark, effective_date) membership (same valid period)."""
    try:
        benchmark = resolve_benchmark(db, benchmark_id, acting_tenant=principal.tenant_id)
        rows = correct_membership(
            db,
            benchmark,
            effective_date=body.effective_date,
            constituents=_constituents_in(body.constituents),
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_benchmark_actor(principal),
        )
    except (
        BenchmarkValueError,
        BenchmarkNotVisible,
        InstrumentNotVisible,
        CurrencyNotVisible,
        NoCurrentMembership,
        DataQualityError,
    ) as exc:
        _raise_benchmark_write(db, exc)
    out = _membership_out(benchmark_id, body.effective_date, rows)
    db.commit()
    return out


@benchmark_router.get("/{benchmark_id}/membership/as-of", response_model=MembershipOut)
def get_membership_as_of(
    benchmark_id: str,
    effective_date: date = Query(...),
    valid_at: datetime = Query(...),
    known_at: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> MembershipOut:
    """The membership set for (benchmark, effective_date) as-of (valid_at, known_at)."""
    try:
        resolve_benchmark(db, benchmark_id, acting_tenant=principal.tenant_id)
    except BenchmarkNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="benchmark not found"
        ) from None
    rows = reconstruct_membership_as_of(
        db,
        acting_tenant=principal.tenant_id,
        benchmark_id=benchmark_id,
        effective_date=effective_date,
        valid_at=valid_at,
        known_at=known_at,
    )
    return _membership_out(benchmark_id, effective_date, rows)


@benchmark_router.get("", response_model=list[BenchmarkOut])
def list_benchmarks_endpoint(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[BenchmarkOut]:
    """All current benchmark definitions for the acting tenant."""
    return [_benchmark_out(row) for row in list_benchmarks(db, acting_tenant=principal.tenant_id)]


# --- factor (P3-2, ENT-025) — captured factor-return INPUTS (definition EV + return series FR) ---


def _factor_actor(principal: Principal) -> FactorActor:
    return FactorActor(actor_id=principal.user_id)


class FactorIn(BaseModel):
    factor_code: str
    factor_source: str
    factor_family: str
    factor_type: str | None = None
    region: str | None = None
    currency_code: str | None = None
    asset_class: str | None = None
    frequency: str = FREQUENCY_DAILY
    factor_name: str | None = None
    description: str | None = None


class FactorUpdateIn(BaseModel):
    factor_family: str | None = None
    factor_type: str | None = None
    region: str | None = None
    currency_code: str | None = None
    asset_class: str | None = None
    frequency: str | None = None
    factor_name: str | None = None
    description: str | None = None


class FactorOut(BaseModel):
    id: str
    factor_code: str
    factor_source: str
    factor_family: str
    factor_type: str | None
    region: str | None
    currency_code: str | None
    asset_class: str | None
    frequency: str
    factor_name: str | None
    description: str | None
    valid_from: datetime
    valid_to: datetime | None
    record_version: int


class FactorReturnIn(BaseModel):
    return_date: date
    return_value: Decimal
    return_type: str = RETURN_TYPE_SIMPLE


class FactorReturnSupersedeIn(FactorReturnIn):
    effective_at: datetime


class FactorReturnCorrectIn(FactorReturnIn):
    restatement_reason: str


class FactorReturnOut(BaseModel):
    id: str
    factor_id: str
    return_date: date
    return_type: str
    return_value: Decimal
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    supersedes_id: str | None
    record_version: int


def _factor_out(row: Factor) -> FactorOut:
    return FactorOut(
        id=row.id,
        factor_code=row.factor_code,
        factor_source=row.factor_source,
        factor_family=row.factor_family,
        factor_type=row.factor_type,
        region=row.region,
        currency_code=row.currency_code,
        asset_class=row.asset_class,
        frequency=row.frequency,
        factor_name=row.factor_name,
        description=row.description,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        record_version=row.record_version,
    )


def _factor_return_out(row: FactorReturn) -> FactorReturnOut:
    return FactorReturnOut(
        id=row.id,
        factor_id=row.factor_id,
        return_date=row.return_date,
        return_type=row.return_type,
        return_value=row.return_value,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        supersedes_id=row.supersedes_id,
        record_version=row.record_version,
    )


#: Governed-write error → (status, detail). Fail-closed; rolls back before mapping.
_FACTOR_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    FactorValueError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid factor input"),
    CurrencyNotVisible: (status.HTTP_404_NOT_FOUND, "currency not found"),
    FactorNotVisible: (status.HTTP_404_NOT_FOUND, "factor not found"),
    NoCurrentFactorReturn: (
        status.HTTP_409_CONFLICT,
        "no current factor return to supersede/correct",
    ),
    DataQualityError: (status.HTTP_409_CONFLICT, "factor return failed a data-quality gate"),
}


def _raise_factor_write(db: Session, exc: Exception) -> None:
    db.rollback()  # whole-unit rollback (CTRL-032) before mapping
    code, detail = _FACTOR_WRITE_ERRORS[type(exc)]
    raise HTTPException(status_code=code, detail=detail) from None


@factor_router.post("", response_model=FactorOut, status_code=status.HTTP_201_CREATED)
def create_factor(
    body: FactorIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FactorOut:
    """Capture a factor DEFINITION (EV; REFERENCE.CREATE + VENDOR_FACTOR ORIGIN lineage)."""
    try:
        row = capture_factor(
            db,
            factor_code=body.factor_code,
            factor_source=body.factor_source,
            factor_family=body.factor_family,
            acting_tenant=principal.tenant_id,
            actor=_factor_actor(principal),
            factor_type=body.factor_type,
            region=body.region,
            currency_code=body.currency_code,
            asset_class=body.asset_class,
            frequency=body.frequency,
            factor_name=body.factor_name,
            description=body.description,
        )
    except (FactorValueError, CurrencyNotVisible) as exc:
        _raise_factor_write(db, exc)
    out = _factor_out(row)
    db.commit()
    return out


@factor_router.post("/{factor_id}/update", response_model=FactorOut)
def update_factor_endpoint(
    factor_id: str,
    body: FactorUpdateIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FactorOut:
    """Apply attribute changes to a factor DEFINITION in place (EV; REFERENCE.UPDATE)."""
    try:
        row = resolve_factor(db, factor_id, acting_tenant=principal.tenant_id)
        update_factor(
            db,
            row,
            acting_tenant=principal.tenant_id,
            actor=_factor_actor(principal),
            **body.model_dump(exclude_unset=True),
        )
    except (FactorValueError, FactorNotVisible, CurrencyNotVisible) as exc:
        _raise_factor_write(db, exc)
    out = _factor_out(row)
    db.commit()
    return out


@factor_router.post(
    "/{factor_id}/returns", response_model=FactorReturnOut, status_code=status.HTTP_201_CREATED
)
def capture_factor_return_endpoint(
    factor_id: str,
    body: FactorReturnIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FactorReturnOut:
    """Capture the first open factor return for (factor, return_date, return_type)."""
    try:
        factor = resolve_factor(db, factor_id, acting_tenant=principal.tenant_id)
        row = capture_factor_return(
            db,
            factor,
            return_date=body.return_date,
            return_value=body.return_value,
            return_type=body.return_type,
            acting_tenant=principal.tenant_id,
            actor=_factor_actor(principal),
        )
    except (FactorValueError, FactorNotVisible, DataQualityError) as exc:
        _raise_factor_write(db, exc)
    out = _factor_return_out(row)
    db.commit()
    return out


@factor_router.post(
    "/{factor_id}/returns/supersede",
    response_model=FactorReturnOut,
    status_code=status.HTTP_201_CREATED,
)
def supersede_factor_return_endpoint(
    factor_id: str,
    body: FactorReturnSupersedeIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FactorReturnOut:
    """Effective-dated re-capture of a factor return (valid-time; a new version)."""
    try:
        factor = resolve_factor(db, factor_id, acting_tenant=principal.tenant_id)
        row = supersede_factor_return(
            db,
            factor,
            return_date=body.return_date,
            return_value=body.return_value,
            return_type=body.return_type,
            effective_at=body.effective_at,
            acting_tenant=principal.tenant_id,
            actor=_factor_actor(principal),
        )
    except (FactorValueError, FactorNotVisible, NoCurrentFactorReturn, DataQualityError) as exc:
        _raise_factor_write(db, exc)
    out = _factor_return_out(row)
    db.commit()
    return out


@factor_router.post(
    "/{factor_id}/returns/correct",
    response_model=FactorReturnOut,
    status_code=status.HTTP_201_CREATED,
)
def correct_factor_return_endpoint(
    factor_id: str,
    body: FactorReturnCorrectIn,
    principal: Principal = Depends(_require_ingest),
    db: Session = Depends(get_tenant_session),
) -> FactorReturnOut:
    """As-known restatement (system-time) of a factor return; a corrected version."""
    try:
        factor = resolve_factor(db, factor_id, acting_tenant=principal.tenant_id)
        row = correct_factor_return(
            db,
            factor,
            return_date=body.return_date,
            return_value=body.return_value,
            return_type=body.return_type,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_factor_actor(principal),
        )
    except (FactorValueError, FactorNotVisible, NoCurrentFactorReturn, DataQualityError) as exc:
        _raise_factor_write(db, exc)
    out = _factor_return_out(row)
    db.commit()
    return out


@factor_router.get("/{factor_id}/returns/as-of", response_model=FactorReturnOut)
def get_factor_return_as_of(
    factor_id: str,
    return_date: date = Query(...),
    valid_at: datetime = Query(...),
    return_type: str = Query(default=RETURN_TYPE_SIMPLE),
    known_at: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> FactorReturnOut:
    """Bitemporal as-of read of a factor return (fail-closed on an unknown factor / no version)."""
    try:
        resolve_factor(db, factor_id, acting_tenant=principal.tenant_id)
    except FactorNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="factor not found"
        ) from None
    row = reconstruct_factor_return_as_of(
        db,
        acting_tenant=principal.tenant_id,
        factor_id=factor_id,
        return_date=return_date,
        return_type=return_type,
        valid_at=valid_at,
        known_at=known_at,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no factor return as-of"
        ) from None
    return _factor_return_out(row)


@factor_router.get("/{factor_id}/returns", response_model=list[FactorReturnOut])
def list_factor_returns_endpoint(
    factor_id: str,
    return_type: str | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[FactorReturnOut]:
    """The current-head factor return series for a factor (tenant-scoped)."""
    try:
        resolve_factor(db, factor_id, acting_tenant=principal.tenant_id)
    except FactorNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="factor not found"
        ) from None
    return [
        _factor_return_out(row)
        for row in list_factor_returns(
            db, acting_tenant=principal.tenant_id, factor_id=factor_id, return_type=return_type
        )
    ]


@factor_router.get("", response_model=list[FactorOut])
def list_factors_endpoint(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[FactorOut]:
    """All current factor definitions for the acting tenant."""
    return [_factor_out(row) for row in list_factors(db, acting_tenant=principal.tenant_id)]
