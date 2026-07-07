"""Risk endpoints (P3-1 sensitivities + P3-3 factor exposures — ENT-028; P3-4 covariance
matrices — ENT-051; P3-5 parametric VaR — ENT-027): the governed risk numbers (curve-node DV01 /
spread-DV01; indicator-loading CURRENCY-family factor exposures; equal-weighted unbiased sample
factor covariances; zero-mean delta-normal 1-day VaR).

Thin layer over the ``irp_shared.risk`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), IA TRUE
append-only, run-bound + snapshot-gated + **model_version-bound** (AD-014 / FW-RUN / TR-15 /
CTRL-003). ``POST /risk/sensitivities/runs`` is gated ``risk.run`` (maker); the reads gated
``risk.view`` (incl. ``auditor_3l``). ``POST /risk/models/sensitivity`` registers the governed
sensitivity model (gated ``model.inventory.register``) so a run can bind a REGISTERED
model_version.
``tenant_id`` server-stamped; a single end-of-request ``db.commit()``. There is **no
PUT/PATCH/DELETE** (append-only).

Failure model (the P2-3 precedent): a **pre-create refusal** (missing prerequisite / unregistered
model_version / unbuildable / cross-tenant / missing-curve / incomplete) raises (422/404/409) and
rolls back — ZERO run. A **post-create FAILED** run is COMMITTED (a real resource in FAILED state,
ZERO rows) and returned with ``status='FAILED'``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.exposure.service import ExposureRunNotVisible
from irp_shared.marketdata.factor import FactorNotVisible
from irp_shared.model.service import UnregisteredModelError
from irp_shared.risk import (
    CovarianceActor,
    CovarianceInputError,
    CovarianceNotVisible,
    CovarianceResult,
    CovarianceRunNotVisible,
    CovarianceRunResult,
    FactorExposureActor,
    FactorExposureInputError,
    FactorExposureNotVisible,
    FactorExposureResult,
    FactorExposureRunNotVisible,
    FactorExposureRunResult,
    ModelVersionConflictError,
    SensitivityActor,
    SensitivityInputError,
    SensitivityNotVisible,
    SensitivityResult,
    SensitivityRunNotVisible,
    SensitivityRunResult,
    VarActor,
    VarInputError,
    VarNotVisible,
    VarResult,
    VarRunNotVisible,
    VarRunResult,
    WrongModelVersionError,
    list_covariances,
    list_factor_exposures,
    list_sensitivities,
    list_vars,
    register_covariance_model,
    register_factor_exposure_model,
    register_sensitivity_model,
    register_var_model,
    resolve_covariance,
    resolve_covariance_run,
    resolve_factor_exposure,
    resolve_factor_exposure_run,
    resolve_run,
    resolve_sensitivity,
    resolve_var,
    resolve_var_run,
    run_covariance,
    run_factor_exposure,
    run_sensitivities,
    run_var,
)
from irp_shared.snapshot import (
    CovarianceSnapshotError,
    CurveSelector,
    CurveSnapshotError,
    EmptySnapshotError,
    FactorExposureSnapshotError,
    SnapshotNotFound,
    SnapshotPurposeError,
    VarSnapshotError,
)

router = APIRouter(prefix="/risk", tags=["risk"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_run = require_permission("risk.run")
_require_view = require_permission("risk.view")
_require_register = require_permission("model.inventory.register")

#: Fail-closed PRE-CREATE exception -> (HTTP status, opaque detail).
_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    SensitivityInputError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid sensitivity run input"),
    UnregisteredModelError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version is not registered (CTRL-003)",
    ),
    SnapshotPurposeError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid snapshot purpose"),
    SnapshotNotFound: (status.HTTP_404_NOT_FOUND, "snapshot not found"),
    CurveSnapshotError: (status.HTTP_409_CONFLICT, "no curve for a selector as-of"),
    EmptySnapshotError: (status.HTTP_409_CONFLICT, "no curve components to pin"),
    DataQualityError: (status.HTTP_409_CONFLICT, "curve input set is incomplete"),
    FactorExposureInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid factor-exposure run input",
    ),
    FactorExposureSnapshotError: (
        status.HTTP_409_CONFLICT,
        "factor-exposure snapshot input failed closed",
    ),
    ExposureRunNotVisible: (status.HTTP_404_NOT_FOUND, "exposure run not found"),
    FactorNotVisible: (status.HTTP_404_NOT_FOUND, "factor not found"),
    WrongModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version belongs to a different model (CTRL-003)",
    ),
    ModelVersionConflictError: (
        status.HTTP_409_CONFLICT,
        "version_label already registered with a different code_version",
    ),
    CovarianceInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid covariance run input",
    ),
    CovarianceSnapshotError: (
        status.HTTP_409_CONFLICT,
        "covariance snapshot input failed closed",
    ),
    VarInputError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid VaR run input"),
    VarSnapshotError: (status.HTTP_409_CONFLICT, "VaR snapshot input failed closed"),
    FactorExposureRunNotVisible: (status.HTTP_404_NOT_FOUND, "factor-exposure run not found"),
    CovarianceRunNotVisible: (status.HTTP_404_NOT_FOUND, "covariance run not found"),
}


def _actor(principal: Principal) -> SensitivityActor:
    return SensitivityActor(actor_id=principal.user_id)


class CurveSelectorIn(BaseModel):
    curve_type: str
    currency_code: str
    curve_date: date
    curve_source: str
    reference_key: str = "NONE"


class SensitivityRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED model_version (CTRL-003; required)
    curve_selectors: list[CurveSelectorIn] | None = None  # build-in-request (with as_of_valid_at)
    as_of_valid_at: datetime | None = None
    as_of_known_at: datetime | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


class SensitivityRowOut(BaseModel):
    id: str
    curve_id: str
    curve_type: str
    currency_code: str
    reference_key: str
    value_type: str
    tenor_days: int
    tenor_label: str
    sensitivity_type: str
    sensitivity_value: str
    bump_bps: str
    model_version_id: str


class SensitivityRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[SensitivityRowOut]


class SensitivityModelOut(BaseModel):
    model_version_id: str
    model_id: str
    version_label: str
    methodology_ref: str | None
    code_version: str | None
    status: str | None


class SensitivityModelIn(BaseModel):
    code_version: str


def _row_out(row: SensitivityResult) -> SensitivityRowOut:
    return SensitivityRowOut(
        id=row.id,
        curve_id=row.curve_id,
        curve_type=row.curve_type,
        currency_code=row.currency_code,
        reference_key=row.reference_key,
        value_type=row.value_type,
        tenor_days=row.tenor_days,
        tenor_label=row.tenor_label,
        sensitivity_type=row.sensitivity_type,
        sensitivity_value=str(row.sensitivity_value),
        bump_bps=str(row.bump_bps),
        model_version_id=row.model_version_id,
    )


def _run_out(result: SensitivityRunResult) -> SensitivityRunOut:
    run = result.run
    return SensitivityRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/sensitivity", response_model=SensitivityModelOut, status_code=status.HTTP_201_CREATED
)
def register_sensitivity(
    body: SensitivityModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed analytic-sensitivity model + a model_version for this
    ``code_version`` and return its id — so a run can bind a REGISTERED model_version
    (OD-P3-1-M)."""
    try:
        version = register_sensitivity_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except ModelVersionConflictError as exc:
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None
    out = SensitivityModelOut(
        model_version_id=version.id,
        model_id=version.model_id,
        version_label=version.version_label,
        methodology_ref=version.methodology_ref,
        code_version=version.code_version,
        status=version.status,
    )
    db.commit()
    return out


@router.post(
    "/sensitivities/runs", response_model=SensitivityRunOut, status_code=status.HTTP_201_CREATED
)
def create_sensitivity_run(
    body: SensitivityRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> SensitivityRunOut:
    """Run a governed analytic-sensitivity calculation. A pre-create refusal raises + rolls back
    (no
    run); a post-create FAILED run is committed (``status='FAILED'``, zero rows)."""
    selectors = (
        None
        if body.curve_selectors is None
        else [
            CurveSelector(
                curve_type=s.curve_type,
                currency_code=s.currency_code,
                curve_date=s.curve_date,
                curve_source=s.curve_source,
                reference_key=s.reference_key,
            )
            for s in body.curve_selectors
        ]
    )
    try:
        result = run_sensitivities(
            db,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            curve_selectors=selectors,
            as_of_valid_at=body.as_of_valid_at,
            as_of_known_at=body.as_of_known_at,
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        SensitivityInputError,
        UnregisteredModelError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        CurveSnapshotError,
        EmptySnapshotError,
        DataQualityError,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _run_out(result)
    db.commit()
    return response


@router.get("/sensitivities/runs/{run_id}", response_model=SensitivityRunOut)
def get_sensitivity_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> SensitivityRunOut:
    """Read a sensitivity run + its rows (tenant-scoped; read-only). A committed FAILED run (zero
    rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except SensitivityRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="sensitivity run not found"
        ) from None
    rows = list_sensitivities(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return SensitivityRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=None,
        rows=[_row_out(r) for r in rows],
    )


@router.get("/sensitivities/{sensitivity_id}", response_model=SensitivityRowOut)
def get_sensitivity(
    sensitivity_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> SensitivityRowOut:
    """Read a single ``sensitivity_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_sensitivity(db, str(sensitivity_id), acting_tenant=principal.tenant_id)
    except SensitivityNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="sensitivity not found"
        ) from None
    return _row_out(row)


# ---------- P3-3: factor exposures (allocation v1) ----------


def _fx_actor(principal: Principal) -> FactorExposureActor:
    return FactorExposureActor(actor_id=principal.user_id)


class FactorExposureRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED model_version (CTRL-003; required)
    exposure_run_id: uuid.UUID | None = None  # build-in-request (with factor_ids)
    factor_ids: list[uuid.UUID] | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


class FactorExposureRowOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    factor_id: str
    factor_code: str
    factor_family: str
    base_currency: str
    mark_currency: str
    loading: str
    exposure_amount: str
    model_version_id: str


class FactorExposureRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[FactorExposureRowOut]


def _fx_row_out(row: FactorExposureResult) -> FactorExposureRowOut:
    return FactorExposureRowOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        factor_id=row.factor_id,
        factor_code=row.factor_code,
        factor_family=row.factor_family,
        base_currency=row.base_currency,
        mark_currency=row.mark_currency,
        loading=str(row.loading),
        exposure_amount=str(row.exposure_amount),
        model_version_id=row.model_version_id,
    )


def _fx_run_out(result: FactorExposureRunResult) -> FactorExposureRunOut:
    run = result.run
    return FactorExposureRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_fx_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/factor-exposure",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_factor_exposure(
    body: SensitivityModelIn,  # the identical one-field payload — reused, not duplicated
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed factor-exposure allocation model + a model_version for
    this ``code_version`` and return its id — so a run can bind a REGISTERED model_version
    (OD-P3-3-G; the sensitivity-registration shape and response envelope)."""
    try:
        version = register_factor_exposure_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except ModelVersionConflictError as exc:
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None
    out = SensitivityModelOut(
        model_version_id=version.id,
        model_id=version.model_id,
        version_label=version.version_label,
        methodology_ref=version.methodology_ref,
        code_version=version.code_version,
        status=version.status,
    )
    db.commit()
    return out


@router.post(
    "/factor-exposures/runs",
    response_model=FactorExposureRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_factor_exposure_run(
    body: FactorExposureRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> FactorExposureRunOut:
    """Run a governed factor-exposure allocation. A pre-create refusal raises + rolls back (no
    run); a post-create FAILED run is committed (``status='FAILED'``, zero rows — an unmapped
    atom, OD-P3-3-N)."""
    try:
        result = run_factor_exposure(
            db,
            acting_tenant=principal.tenant_id,
            actor=_fx_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            exposure_run_id=(None if body.exposure_run_id is None else str(body.exposure_run_id)),
            factor_ids=(None if body.factor_ids is None else [str(f) for f in body.factor_ids]),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        FactorExposureInputError,
        UnregisteredModelError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        FactorExposureSnapshotError,
        ExposureRunNotVisible,
        FactorNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _fx_run_out(result)
    db.commit()
    return response


@router.get("/factor-exposures/runs/{run_id}", response_model=FactorExposureRunOut)
def get_factor_exposure_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> FactorExposureRunOut:
    """Read a factor-exposure run + its rows (tenant-scoped; read-only). A committed FAILED run
    (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_factor_exposure_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except FactorExposureRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="factor-exposure run not found"
        ) from None
    rows = list_factor_exposures(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return FactorExposureRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=None,
        rows=[_fx_row_out(r) for r in rows],
    )


@router.get("/factor-exposures/{factor_exposure_id}", response_model=FactorExposureRowOut)
def get_factor_exposure(
    factor_exposure_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> FactorExposureRowOut:
    """Read a single ``factor_exposure_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_factor_exposure(
            db, str(factor_exposure_id), acting_tenant=principal.tenant_id
        )
    except FactorExposureNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="factor exposure not found"
        ) from None
    return _fx_row_out(row)


# ---------- P3-4: covariance matrices (sample v1) ----------


def _cov_actor(principal: Principal) -> CovarianceActor:
    return CovarianceActor(actor_id=principal.user_id)


class CovarianceModelIn(BaseModel):
    code_version: str
    window_observations: int  # the DECLARED estimation window — version identity (OD-P3-4-G)


class CovarianceRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED model_version (CTRL-003; required)
    factor_ids: list[uuid.UUID] | None = None  # build-in-request
    as_of_valid_at: datetime | None = None
    as_of_known_at: datetime | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


class CovarianceRowOut(BaseModel):
    id: str
    factor_id_1: str
    factor_id_2: str
    factor_code_1: str
    factor_code_2: str
    statistic_type: str
    return_type: str
    frequency: str
    n_observations: int
    window_start: date
    window_end: date
    covariance_value: str
    model_version_id: str


class CovarianceRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[CovarianceRowOut]


def _cov_row_out(row: CovarianceResult) -> CovarianceRowOut:
    return CovarianceRowOut(
        id=row.id,
        factor_id_1=row.factor_id_1,
        factor_id_2=row.factor_id_2,
        factor_code_1=row.factor_code_1,
        factor_code_2=row.factor_code_2,
        statistic_type=row.statistic_type,
        return_type=row.return_type,
        frequency=row.frequency,
        n_observations=row.n_observations,
        window_start=row.window_start,
        window_end=row.window_end,
        # Fixed-point, never scientific: str(Decimal('1E-8')) would flip notation for small
        # covariances (the 2026-07 review fix).
        covariance_value=f"{row.covariance_value:f}",
        model_version_id=row.model_version_id,
    )


def _cov_run_out(result: CovarianceRunResult) -> CovarianceRunOut:
    run = result.run
    return CovarianceRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_cov_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/covariance",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_covariance(
    body: CovarianceModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed covariance model + a model_version for this
    ``(code_version, window_observations)`` pair and return its id (OD-P3-4-G — the window is
    version identity; a same-label re-register with a different window OR code_version is a 409).
    The response envelope is the shared registration shape."""
    try:
        version = register_covariance_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            window_observations=body.window_observations,
        )
    except ValueError:  # window_observations < 2 (the registration floor)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="window_observations must be >= 2",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        # WrongModelVersionError: the existing same-label version carries a malformed/absent
        # declared window (mintable via the GENERIC model endpoint) — a governed refusal, not a
        # 500 (the 2026-07 review fix).
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None
    out = SensitivityModelOut(
        model_version_id=version.id,
        model_id=version.model_id,
        version_label=version.version_label,
        methodology_ref=version.methodology_ref,
        code_version=version.code_version,
        status=version.status,
    )
    db.commit()
    return out


@router.post(
    "/covariances/runs",
    response_model=CovarianceRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_covariance_run(
    body: CovarianceRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> CovarianceRunOut:
    """Run a governed sample-covariance estimation. A pre-create refusal raises + rolls back (no
    run — incl. a short/misaligned window, 409); a post-create FAILED run is committed
    (``status='FAILED'``, zero rows — the defensive output-sanity gate)."""
    try:
        result = run_covariance(
            db,
            acting_tenant=principal.tenant_id,
            actor=_cov_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            factor_ids=(None if body.factor_ids is None else [str(f) for f in body.factor_ids]),
            as_of_valid_at=body.as_of_valid_at,
            as_of_known_at=body.as_of_known_at,
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        CovarianceInputError,
        UnregisteredModelError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        CovarianceSnapshotError,
        FactorNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _cov_run_out(result)
    db.commit()
    return response


@router.get("/covariances/runs/{run_id}", response_model=CovarianceRunOut)
def get_covariance_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CovarianceRunOut:
    """Read a covariance run + its matrix rows (tenant-scoped; read-only). A committed FAILED run
    (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_covariance_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except CovarianceRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="covariance run not found"
        ) from None
    rows = list_covariances(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return CovarianceRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=None,
        rows=[_cov_row_out(r) for r in rows],
    )


@router.get("/covariances/{covariance_id}", response_model=CovarianceRowOut)
def get_covariance(
    covariance_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CovarianceRowOut:
    """Read a single ``covariance_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_covariance(db, str(covariance_id), acting_tenant=principal.tenant_id)
    except CovarianceNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="covariance not found"
        ) from None
    return _cov_row_out(row)


# ---------- P3-5: parametric VaR (delta-normal v1) ----------


def _var_actor(principal: Principal) -> VarActor:
    return VarActor(actor_id=principal.user_id)


class VarModelIn(BaseModel):
    code_version: str
    confidence_level: str  # the DECLARED confidence (v1 vocabulary {0.95, 0.99}) — OD-P3-5-D
    horizon_days: int = 1


class VarRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED model_version (CTRL-003; required)
    exposure_run_id: uuid.UUID | None = None  # build-in-request (with covariance_run_id)
    covariance_run_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


class VarRowOut(BaseModel):
    id: str
    metric_type: str
    base_currency: str
    confidence_level: str
    horizon_days: int
    z_score: str
    sigma: str
    var_value: str
    n_factors: int
    n_observations: int
    window_start: date
    window_end: date
    exposure_run_id: str
    covariance_run_id: str
    model_version_id: str


class VarRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[VarRowOut]


def _var_row_out(row: VarResult) -> VarRowOut:
    return VarRowOut(
        id=row.id,
        metric_type=row.metric_type,
        base_currency=row.base_currency,
        confidence_level=f"{row.confidence_level:f}",
        horizon_days=row.horizon_days,
        z_score=f"{row.z_score:f}",
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        sigma=f"{row.sigma:f}",
        var_value=f"{row.var_value:f}",
        n_factors=row.n_factors,
        n_observations=row.n_observations,
        window_start=row.window_start,
        window_end=row.window_end,
        exposure_run_id=row.exposure_run_id,
        covariance_run_id=row.covariance_run_id,
        model_version_id=row.model_version_id,
    )


def _var_run_out(result: VarRunResult) -> VarRunOut:
    run = result.run
    return VarRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_var_row_out(r) for r in result.rows],
    )


@router.post("/models/var", response_model=SensitivityModelOut, status_code=status.HTTP_201_CREATED)
def register_var(
    body: VarModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed parametric-VaR model + a model_version for this
    ``(code_version, confidence_level, horizon_days)`` identity and return its id (OD-P3-5-D —
    the declarations are version identity; a same-label re-register with a different declaration
    is a 409; a confidence outside the v1 vocabulary is a 422). The shared registration
    envelope."""
    try:
        version = register_var_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            confidence_level=body.confidence_level,
            horizon_days=body.horizon_days,
        )
    except ValueError:  # out-of-vocabulary confidence / non-v1 horizon
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confidence_level/horizon_days outside the v1 declared vocabulary",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None
    out = SensitivityModelOut(
        model_version_id=version.id,
        model_id=version.model_id,
        version_label=version.version_label,
        methodology_ref=version.methodology_ref,
        code_version=version.code_version,
        status=version.status,
    )
    db.commit()
    return out


@router.post("/vars/runs", response_model=VarRunOut, status_code=status.HTTP_201_CREATED)
def create_var_run(
    body: VarRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> VarRunOut:
    """Run a governed parametric-VaR calculation. A pre-create refusal raises + rolls back (no
    run — incl. an uncovered exposure factor, 422); a post-create FAILED run is committed
    (``status='FAILED'``, zero rows — the OD-P3-5-G non-PSD radicand gate)."""
    try:
        result = run_var(
            db,
            acting_tenant=principal.tenant_id,
            actor=_var_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            exposure_run_id=(None if body.exposure_run_id is None else str(body.exposure_run_id)),
            covariance_run_id=(
                None if body.covariance_run_id is None else str(body.covariance_run_id)
            ),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        VarInputError,
        UnregisteredModelError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        VarSnapshotError,
        FactorExposureRunNotVisible,
        CovarianceRunNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _var_run_out(result)
    db.commit()
    return response


@router.get("/vars/runs/{run_id}", response_model=VarRunOut)
def get_var_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> VarRunOut:
    """Read a VaR run + its summary row (tenant-scoped; read-only). A committed FAILED run (zero
    rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_var_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except VarRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="VaR run not found"
        ) from None
    rows = list_vars(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return VarRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=None,
        rows=[_var_row_out(r) for r in rows],
    )


@router.get("/vars/{var_id}", response_model=VarRowOut)
def get_var(
    var_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> VarRowOut:
    """Read a single ``var_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_var(db, str(var_id), acting_tenant=principal.tenant_id)
    except VarNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="VaR result not found"
        ) from None
    return _var_row_out(row)
