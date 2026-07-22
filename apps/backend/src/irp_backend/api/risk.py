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
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, map_refusal, require_permission
from irp_shared.db.integrity import is_unique_violation
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.exposure.service import ExposureRunNotVisible
from irp_shared.marketdata.benchmark import BenchmarkNotVisible
from irp_shared.marketdata.factor import FactorNotVisible
from irp_shared.model.service import (
    ExpiredModelExceptionError,
    RejectedModelVersionError,
    UnregisteredModelError,
)
from irp_shared.risk import (
    ActiveRiskActor,
    ActiveRiskInputError,
    ActiveRiskNotVisible,
    ActiveRiskResult,
    ActiveRiskRunNotVisible,
    ActiveRiskRunResult,
    CovarianceActor,
    CovarianceInputError,
    CovarianceNotVisible,
    CovarianceResult,
    CovarianceRunNotVisible,
    CovarianceRunResult,
    EsBacktestActor,
    EsBacktestInputError,
    EsBacktestNotVisible,
    EsBacktestRunNotVisible,
    EsBacktestRunResult,
    FactorExposureActor,
    FactorExposureInputError,
    FactorExposureNotVisible,
    FactorExposureResult,
    FactorExposureRunNotVisible,
    FactorExposureRunResult,
    HsVarInputError,
    HsVarRunResult,
    ModelVersionConflictError,
    NoCurrentScenarioShock,
    PrivateCovarianceNotVisible,
    PrivateFactorReturnResult,
    ProxyWeightEstimateActor,
    ProxyWeightEstimateResult,
    ProxyWeightEstimateResultNotVisible,
    ProxyWeightEstimateRunNotVisible,
    ProxyWeightEstimateRunResult,
    ProxyWeightInputError,
    PurePrivateFactorResultNotVisible,
    ResidualShrinkageInputError,
    ResidualShrinkageRunResult,
    RiskRunQueryError,
    ScenarioActor,
    ScenarioDefinition,
    ScenarioInputError,
    ScenarioNotVisible,
    ScenarioResult,
    ScenarioResultNotVisible,
    ScenarioRunNotVisible,
    ScenarioRunResult,
    ScenarioShock,
    ScenarioValueError,
    SensitivityActor,
    SensitivityInputError,
    SensitivityNotVisible,
    SensitivityResult,
    SensitivityRunNotVisible,
    SensitivityRunResult,
    VarActor,
    VarBacktestActor,
    VarBacktestInputError,
    VarBacktestNotVisible,
    VarBacktestResult,
    VarBacktestRunNotVisible,
    VarBacktestRunResult,
    VarInputError,
    VarNotVisible,
    VarResult,
    VarRunNotVisible,
    VarRunResult,
    WrongModelVersionError,
    capture_scenario_shock,
    correct_scenario_shock,
    create_scenario_definition,
    latest_active_risk_for_portfolio,
    latest_covariances,
    latest_es_backtest,
    latest_factor_exposure,
    latest_private_covariances,
    latest_proxy_weight_result,
    latest_pure_private_factor_for_segment,
    latest_scenario_results,
    latest_sensitivities,
    latest_var_backtest,
    latest_var_for_portfolio,
    list_active_risk_results,
    list_active_risks,
    list_covariances,
    list_es_backtests,
    list_es_backtests_by_entity,
    list_factor_exposures,
    list_factor_exposures_by_entity,
    list_proxy_weight_results,
    list_proxy_weight_results_by_entity,
    list_pure_private_factor_results_by_segment,
    list_risk_runs,
    list_scenario_definitions,
    list_scenario_results,
    list_scenario_shocks,
    list_sensitivities,
    list_var_backtests,
    list_var_backtests_by_entity,
    list_var_results,
    list_vars,
    reconstruct_scenario_shock_as_of,
    register_active_risk_model,
    register_covariance_model,
    register_es_backtest_model,
    register_factor_exposure_loadings_model,
    register_factor_exposure_model,
    register_factor_exposure_proxy_model,
    register_historical_var_es_model,
    register_historical_var_model,
    register_proxy_weight_ewma_model,
    register_proxy_weight_regression_model,
    register_proxy_weight_shrinkage_eb_model,
    register_scenario_model,
    register_sensitivity_model,
    register_var_backtest_christoffersen_model,
    register_var_backtest_model,
    register_var_model,
    register_var_parametric_es_model,
    register_var_parametric_es_total_model,
    register_var_parametric_total_model,
    resolve_active_risk,
    resolve_active_risk_run,
    resolve_covariance,
    resolve_covariance_run,
    resolve_es_backtest,
    resolve_es_backtest_run,
    resolve_factor_exposure,
    resolve_factor_exposure_run,
    resolve_private_covariance,
    resolve_proxy_weight_result,
    resolve_proxy_weight_run,
    resolve_pure_private_factor_result,
    resolve_run,
    resolve_scenario_definition,
    resolve_scenario_result,
    resolve_scenario_run,
    resolve_sensitivity,
    resolve_var,
    resolve_var_backtest,
    resolve_var_backtest_run,
    resolve_var_run,
    run_active_risk,
    run_covariance,
    run_es_backtest,
    run_factor_exposure,
    run_proxy_weight_estimate,
    run_residual_shrinkage,
    run_scenario,
    run_sensitivities,
    run_var,
    run_var_backtest,
    run_var_historical,
    supersede_scenario_shock,
    update_scenario_definition,
)
from irp_shared.risk.queries import LIST_LIMIT_DEFAULT
from irp_shared.snapshot import (
    ActiveRiskSnapshotError,
    CovarianceSnapshotError,
    CurveSelector,
    CurveSnapshotError,
    EmptySnapshotError,
    FactorExposureSnapshotError,
    ProxyWeightSnapshotError,
    ResidualShrinkageSnapshotError,
    ScenarioSnapshotError,
    SnapshotNotFound,
    SnapshotPurposeError,
    VarBacktestSnapshotError,
    VarSnapshotError,
    VarTotalSnapshotError,
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
        "model_version does not match this model's registered identity (CTRL-003)",
    ),
    RejectedModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version latest validation outcome is REJECTED — new runs refused (VW-1 / CTRL-022)",
    ),
    ExpiredModelExceptionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version use-before-validation EXCEPTION has expired — new runs refused until a "
        "fresh exception is granted or a validation is recorded (MG-1 / CTRL-022)",
    ),
    ModelVersionConflictError: (
        status.HTTP_409_CONFLICT,
        "version_label already registered with a different declared identity",
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
    HsVarInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid historical-VaR run input",
    ),
    VarSnapshotError: (status.HTTP_409_CONFLICT, "VaR snapshot input failed closed"),
    # Subclasses of VarSnapshotError — listed FIRST so the MRO walk gives the specific detail.
    ActiveRiskSnapshotError: (
        status.HTTP_409_CONFLICT,
        "active-risk snapshot input failed closed",
    ),
    VarTotalSnapshotError: (
        status.HTTP_409_CONFLICT,
        "total-VaR snapshot input failed closed",
    ),
    ActiveRiskInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid active-risk run input",
    ),
    VarBacktestInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid var-backtest run input",
    ),
    EsBacktestInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid es-backtest run input",
    ),
    VarBacktestSnapshotError: (
        status.HTTP_409_CONFLICT,
        "var-backtest snapshot input failed closed",
    ),
    ScenarioInputError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid scenario run input"),
    ScenarioSnapshotError: (
        status.HTTP_409_CONFLICT,
        "scenario snapshot input failed closed",
    ),
    ScenarioValueError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid scenario input"),
    NoCurrentScenarioShock: (status.HTTP_409_CONFLICT, "no current scenario shock to supersede"),
    ScenarioNotVisible: (status.HTTP_404_NOT_FOUND, "scenario not found"),
    ScenarioRunNotVisible: (status.HTTP_404_NOT_FOUND, "scenario run not found"),
    ScenarioResultNotVisible: (status.HTTP_404_NOT_FOUND, "scenario result not found"),
    FactorExposureRunNotVisible: (status.HTTP_404_NOT_FOUND, "factor-exposure run not found"),
    ProxyWeightInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid proxy-weight-estimate run input",
    ),
    ProxyWeightSnapshotError: (
        status.HTTP_409_CONFLICT,
        "proxy-weight snapshot input failed closed",
    ),
    ProxyWeightEstimateRunNotVisible: (
        status.HTTP_404_NOT_FOUND,
        "proxy-weight-estimate run not found",
    ),
    ResidualShrinkageInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid residual-shrinkage run input",
    ),
    ResidualShrinkageSnapshotError: (
        status.HTTP_409_CONFLICT,
        "residual-shrinkage snapshot input failed closed",
    ),
    CovarianceRunNotVisible: (status.HTTP_404_NOT_FOUND, "covariance run not found"),
    PurePrivateFactorResultNotVisible: (
        status.HTTP_404_NOT_FOUND,
        "pure-private factor result not found",
    ),
    BenchmarkNotVisible: (status.HTTP_404_NOT_FOUND, "benchmark not found"),
    RiskRunQueryError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid run listing filter"),
}


def _map_error(exc: Exception) -> tuple[int, str]:
    """Resolve the (status, opaque detail) for a refusal exception by walking the MRO (P3-C1,
    OD-F — the shared ``deps.map_refusal``; the exposure/snapshot routers use it directly)."""
    return map_refusal(exc, _ERROR_MAP)


def _actor(principal: Principal) -> SensitivityActor:
    return SensitivityActor(actor_id=principal.user_id)


# ---------- FE-1: the read-only runs listing (OD-FE-1-C) ----------


class RiskRunSummaryOut(BaseModel):
    run_id: str
    run_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    initiated_by: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    failure_reason: str | None


class RiskRunListOut(BaseModel):
    items: list[RiskRunSummaryOut]


@router.get("/runs", response_model=RiskRunListOut)
def get_risk_runs(
    run_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> RiskRunListOut:
    """List the tenant's risk runs, newest first (the SIX risk families only; read-only;
    fail-closed filters — an unknown ``run_type``/``status`` or out-of-bounds page is a 422,
    never a silently-empty page). The query param is ``status`` (aliased here — the FastAPI
    ``status`` module shadows the name)."""
    try:
        runs = list_risk_runs(
            db,
            acting_tenant=principal.tenant_id,
            run_type=run_type,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except RiskRunQueryError as exc:
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from exc
    return RiskRunListOut(
        items=[
            RiskRunSummaryOut(
                run_id=r.run_id,
                run_type=r.run_type,
                status=r.status,
                created_at=r.created_at,
                completed_at=r.completed_at,
                initiated_by=r.initiated_by,
                input_snapshot_id=r.input_snapshot_id,
                model_version_id=r.model_version_id,
                code_version=r.code_version,
                environment_id=r.environment_id,
                failure_reason=r.failure_reason,
            )
            for r in runs
        ]
    )


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
    calculation_run_id: str  # the run pin (TR-09) — cross-run aggregation is a CONSUMER ERROR


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
        calculation_run_id=row.calculation_run_id,
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
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        # WrongModelVersionError: a same-label twin exists that is NOT a REGISTERED version of
        # this family (generically minted) — a governed refusal, not a 500 (P3-C1).
        db.rollback()
        code, detail = _map_error(exc)
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
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        CurveSnapshotError,
        EmptySnapshotError,
        DataQualityError,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
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
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_row_out(r) for r in rows],
    )


@router.get("/sensitivities/latest", response_model=list[SensitivityRowOut])
def latest_sensitivities_endpoint(
    curve_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[SensitivityRowOut]:
    """API-1 latest-resolver (Class B): the newest COMPLETED sensitivity run's rows, optionally
    row-filtered to a ``curve_id`` (empty when none). A sensitivity run is curve-intrinsic (no
    portfolio/instrument entity); the whole run — or the queried curve's slice of it — is the
    readable unit. Each row carries ``calculation_run_id``."""
    rows = latest_sensitivities(
        db,
        acting_tenant=principal.tenant_id,
        curve_id=(str(curve_id) if curve_id is not None else None),
        as_of=as_of,
    )
    return [_row_out(r) for r in rows]


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
    calculation_run_id: str  # API-1: discriminates runs in an entity/time read
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
        calculation_run_id=row.calculation_run_id,
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
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        # WrongModelVersionError: a same-label twin exists that is NOT a REGISTERED version of
        # this family (generically minted) — a governed refusal, not a 500 (P3-C1).
        db.rollback()
        code, detail = _map_error(exc)
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
    "/models/factor-exposure-proxy",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_factor_exposure_proxy(
    body: SensitivityModelIn,  # the identical one-field payload — reused, not duplicated
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed PROXY factor-exposure model + a model_version for this
    ``code_version`` (PA-2, OD-PA-2-A) — the run endpoint is the SHARED
    ``POST /risk/factor-exposures/runs`` (the binder dispatches on the bound model)."""
    try:
        version = register_factor_exposure_proxy_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/models/factor-exposure-loadings",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_factor_exposure_loadings(
    body: SensitivityModelIn,  # the identical one-field payload — reused, not duplicated
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed LOADINGS factor-exposure model + a model_version for
    this ``code_version`` (FL-1, OD-FL-1-D) — the run endpoint is the SHARED
    ``POST /risk/factor-exposures/runs`` (the binder dispatches on the bound model)."""
    try:
        version = register_factor_exposure_loadings_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        FactorExposureSnapshotError,
        ExposureRunNotVisible,
        FactorNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
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
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_fx_row_out(r) for r in rows],
    )


@router.get("/factor-exposures", response_model=list[FactorExposureRowOut])
def list_factor_exposures_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[FactorExposureRowOut]:
    """API-1 entity/time read: rows across COMPLETED runs filtered by entity + an optional
    ``as_of`` run cutoff (silent-empty on a foreign id). Each row carries ``calculation_run_id`` —
    cross-run aggregation is a CONSUMER ERROR."""
    rows = list_factor_exposures_by_entity(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
        as_of=as_of,
    )
    return [_fx_row_out(r) for r in rows]


@router.get("/factor-exposures/latest", response_model=list[FactorExposureRowOut])
def latest_factor_exposures_endpoint(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[FactorExposureRowOut]:
    """API-1 latest-resolver: the newest COMPLETED run's rows for the entity (empty when none)."""
    rows = latest_factor_exposure(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
        as_of=as_of,
    )
    return [_fx_row_out(r) for r in rows]


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
    calculation_run_id: str  # the run pin (TR-09) — the matrix identity a client re-pins on


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
        calculation_run_id=row.calculation_run_id,
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
        code, detail = _map_error(exc)
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
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        CovarianceSnapshotError,
        FactorNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
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
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_cov_row_out(r) for r in rows],
    )


@router.get("/covariances/latest", response_model=list[CovarianceRowOut])
def latest_covariances_endpoint(
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[CovarianceRowOut]:
    """API-1 latest-resolver (Class B): the newest COMPLETED covariance run's FULL matrix (empty
    when none). A covariance run IS the matrix identity — no entity sub-filter; rows present in
    canonical pair order. Each row carries ``calculation_run_id``."""
    rows = latest_covariances(db, acting_tenant=principal.tenant_id, as_of=as_of)
    return [_cov_row_out(r) for r in rows]


@router.get("/covariances/{covariance_id}", response_model=CovarianceRowOut)
def get_covariance(
    covariance_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CovarianceRowOut:
    """Read a single ``covariance_result`` row (tenant-scoped; read-only). The step-1 ``run_type``
    filter keeps a private Ω_pp row (same table) OUT of this PUBLIC surface."""
    try:
        row = resolve_covariance(db, str(covariance_id), acting_tenant=principal.tenant_id)
    except CovarianceNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="covariance not found"
        ) from None
    return _cov_row_out(row)


# ---------- PPF-2: private-factor covariance block Ω_pp (reuses CovarianceRowOut; APPRAISAL) ----
@router.get("/private-covariances/latest", response_model=list[CovarianceRowOut])
def latest_private_covariances_endpoint(
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[CovarianceRowOut]:
    """The newest COMPLETED private-covariance (Ω_pp) run's FULL matrix (empty when none). The
    ``run_type=COVARIANCE_PRIVATE`` filter keeps the PUBLIC covariance out of this shared-table
    read. A run IS the matrix identity — no entity sub-filter; rows in canonical pair order,
    ``frequency`` = APPRAISAL. Each row carries ``calculation_run_id`` (TR-09)."""
    rows = latest_private_covariances(db, acting_tenant=principal.tenant_id, as_of=as_of)
    return [_cov_row_out(r) for r in rows]


@router.get("/private-covariances/{covariance_id}", response_model=CovarianceRowOut)
def get_private_covariance(
    covariance_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CovarianceRowOut:
    """Read a single PRIVATE ``covariance_result`` row (tenant-scoped; read-only). The
    ``run_type`` filter keeps a PUBLIC covariance row (same table) OUT of this private surface."""
    try:
        row = resolve_private_covariance(db, str(covariance_id), acting_tenant=principal.tenant_id)
    except PrivateCovarianceNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="private covariance not found"
        ) from None
    return _cov_row_out(row)


# ---------- P3-5: parametric VaR (delta-normal v1) ----------


def _var_actor(principal: Principal) -> VarActor:
    return VarActor(actor_id=principal.user_id)


class VarModelIn(BaseModel):
    code_version: str
    # the DECLARED confidence (vocabulary {0.95, 0.975, 0.99}) — OD-P3-5-D; 0.975 admitted by ES-1
    confidence_level: str
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
    z_score: str | None  # None for VAR_HISTORICAL (0028 — no normal quantile)
    sigma: str | None  # None for VAR_HISTORICAL (no volatility estimate)
    # The METRIC's number, discriminated by ``metric_type`` — for an ES_PARAMETRIC row this is an
    # Expected Shortfall, NOT a VaR (ES-1; the VAR_HISTORICAL generic-by-metric_type precedent).
    # The shape is UNCHANGED by ES-1: the ES rides var_value and needs no new field. NOTE an ES
    # row does not reconcile against its own columns — z_score is echoed (the PG CHECK forces it)
    # but is NOT the ES arithmetic; the multiplier lives in the bound model_version's declared
    # es_multiplier. Key off metric_type, and reproduce an ES through its model_version.
    var_value: str
    n_factors: int
    n_observations: int
    window_start: date
    window_end: date
    exposure_run_id: str
    covariance_run_id: str | None  # None for VAR_HISTORICAL (no covariance run)
    model_version_id: str
    residual_variance: str | None  # PA-4: the idiosyncratic leg; None off VAR_PARAMETRIC_TOTAL
    # BT-2: the MAX age (calendar days) of the cited residual estimates at this run's as-of.
    # None off the total family, on a total run citing no estimates, and on an ungated
    # grandfathered v1 bind whose estimate snapshot is unresolvable. Negative = a look-ahead.
    estimate_age_days: int | None


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
        z_score=(None if row.z_score is None else f"{row.z_score:f}"),
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        sigma=(None if row.sigma is None else f"{row.sigma:f}"),
        var_value=f"{row.var_value:f}",
        n_factors=row.n_factors,
        n_observations=row.n_observations,
        window_start=row.window_start,
        window_end=row.window_end,
        exposure_run_id=row.exposure_run_id,
        covariance_run_id=row.covariance_run_id,
        model_version_id=row.model_version_id,
        residual_variance=(None if row.residual_variance is None else f"{row.residual_variance:f}"),
        estimate_age_days=row.estimate_age_days,
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
        code, detail = _map_error(exc)
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


class VarTotalModelIn(BaseModel):
    code_version: str
    # the DECLARED confidence (vocabulary {0.95, 0.975, 0.99}) — OD-P3-5-D; 0.975 admitted by ES-1
    confidence_level: str
    appraisal_days: int  # the DECLARED appraisal cadence (calendar days, e.g. 91) — OD-PA-4-D
    # BT-2 (OD-BT-2-C): the DECLARED staleness policy — the max age (calendar days) of a cited
    # residual estimate at the run's as-of. REQUIRED, no default: a staleness policy is a
    # conscious declaration, not an inherited convenience (the OD-P3-5-D philosophy). Registers
    # the total model at v2; pre-BT-2 v1 registrations stay ungated (the recorded grandfather).
    max_estimate_age_days: int
    horizon_days: int = 1


@router.post(
    "/models/var-parametric-total",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_parametric_total(
    body: VarTotalModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed total-parametric-VaR model (PA-4 — factor variance +
    the idiosyncratic residual of the proxied instruments' cited proxy-weight estimates) + a
    model_version for this ``(code_version, confidence_level, horizon_days, appraisal_days,
    max_estimate_age_days)`` identity (BT-2: **v2** — the declared staleness policy joined the
    identity) and return its id. Dispatched through the SAME ``POST /risk/vars/runs`` endpoint as
    the plain parametric family — the binder resolves the bound model's code. A same-label
    re-register with a different declaration is a 409; a confidence outside the v1 vocabulary or a
    non-positive ``appraisal_days``/``max_estimate_age_days`` is a 422. The shared registration
    envelope."""
    try:
        version = register_var_parametric_total_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            confidence_level=body.confidence_level,
            appraisal_days=body.appraisal_days,
            max_estimate_age_days=body.max_estimate_age_days,
            horizon_days=body.horizon_days,
        )
    except ValueError:  # out-of-vocab confidence / non-v1 horizon / non-positive days
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "confidence_level/horizon_days/appraisal_days/max_estimate_age_days outside the "
                "v1 declared vocabulary"
            ),
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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


class VarEsModelIn(BaseModel):
    code_version: str
    # the DECLARED confidence (vocabulary {0.95, 0.975, 0.99}) — 0.975 is BCBS d457 MAR33.3's
    # prescribed ES level and the only externally-anchored one. The es_multiplier k_c is NOT a
    # body field: it is looked up from the registered table for this confidence and declared by
    # the registrar, so a caller cannot pair a confidence with a mismatched multiplier.
    confidence_level: str
    horizon_days: int = 1


class VarEsTotalModelIn(BaseModel):
    code_version: str
    # the DECLARED confidence (vocabulary {0.95, 0.975, 0.99}) — see VarEsModelIn
    confidence_level: str
    appraisal_days: int  # the DECLARED appraisal cadence (calendar days, e.g. 91) — OD-PA-4-D
    # REQUIRED from birth on this family: unlike risk.var.parametric_total (whose immutable v1
    # predates BT-2 and is the recorded ungated grandfather), the ES-total code is born with the
    # declaration, so no legitimate ungated version can exist and an absent one REFUSES at bind.
    max_estimate_age_days: int
    horizon_days: int = 1


@router.post(
    "/models/var-es",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_parametric_es(
    body: VarEsModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed parametric-Expected-Shortfall model (ES-1 — the
    alpha-tail mean, ``ES_c = k_c * sigma_p``, over the SAME governed factor sigma as the plain
    parametric VaR family) + a model_version for this ``(code_version, confidence_level,
    horizon_days, z, es_multiplier)`` identity, and return its id. Dispatched through the SAME
    ``POST /risk/vars/runs`` endpoint as every VaR family — the binder resolves the bound model's
    code. A same-label re-register with a different declaration is a 409; a confidence outside the
    vocabulary or a non-v1 horizon is a 422. The shared registration envelope."""
    try:
        version = register_var_parametric_es_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            confidence_level=body.confidence_level,
            horizon_days=body.horizon_days,
        )
    except ValueError:  # out-of-vocab confidence / non-v1 horizon
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confidence_level/horizon_days outside the declared vocabulary",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/models/var-es-total",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_parametric_es_total(
    body: VarEsTotalModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed TOTAL parametric-Expected-Shortfall model (ES-1 —
    ``ES_c = k_c * sigma_total``, the registered multiplier over PA-4's factor+idiosyncratic sigma,
    carrying BT-2's staleness gate) + a model_version for this ``(code_version, confidence_level,
    horizon_days, z, es_multiplier, appraisal_days, max_estimate_age_days)`` identity, and return
    its id. Dispatched through the SAME ``POST /risk/vars/runs`` endpoint. A same-label re-register
    with a different declaration is a 409; a confidence outside the vocabulary, a non-v1 horizon or
    a non-positive ``appraisal_days``/``max_estimate_age_days`` is a 422."""
    try:
        version = register_var_parametric_es_total_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            confidence_level=body.confidence_level,
            appraisal_days=body.appraisal_days,
            max_estimate_age_days=body.max_estimate_age_days,
            horizon_days=body.horizon_days,
        )
    except ValueError:  # out-of-vocab confidence / non-v1 horizon / non-positive days
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "confidence_level/horizon_days/appraisal_days/max_estimate_age_days outside the "
                "declared vocabulary"
            ),
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        VarSnapshotError,
        FactorExposureRunNotVisible,
        CovarianceRunNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
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
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_var_row_out(r) for r in rows],
    )


@router.get("/vars", response_model=list[VarRowOut])
def list_vars_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[VarRowOut]:
    """API-1b entity read (Class C): governed VaR rows resolved via the run's ROOT
    ``scope_portfolio_id`` (``var_result`` carries no portfolio) + an optional ``metric_type``
    (parametric/total/HS/ES) and ``as_of`` run cutoff. Silent-empty on a foreign/NULL-scope id.
    Each row carries ``calculation_run_id`` — cross-run aggregation is a CONSUMER ERROR."""
    rows = list_var_results(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        metric_type=metric_type,
        as_of=as_of,
    )
    return [_var_row_out(r) for r in rows]


@router.get("/vars/latest", response_model=list[VarRowOut])
def latest_var_endpoint(
    portfolio_id: uuid.UUID,
    metric_type: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[VarRowOut]:
    """API-1b latest-resolver: the newest COMPLETED VaR run scoped to the portfolio (its metric
    row(s), or the one ``metric_type``) — the flagship 'latest VaR for portfolio P' read. Empty
    when the portfolio has no scoped COMPLETED run (a snapshot-consume-rooted or pre-0046 run is
    honestly unresolvable)."""
    rows = latest_var_for_portfolio(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        metric_type=metric_type,
        as_of=as_of,
    )
    return [_var_row_out(r) for r in rows]


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


# ---------- VAR-HS-1: historical-simulation VaR (OD-VHS-A..G) ----------


class HsVarModelIn(BaseModel):
    code_version: str
    confidence_level: str  # the DECLARED confidence (shared v1 vocabulary) — OD-VHS-B
    window_observations: int  # window-as-identity (>= the OD-VHS-E adequacy floor)
    horizon_days: int = 1


class HsVarRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    # A REGISTERED model_version of EITHER historical family (CTRL-003): the binder dispatches
    # risk.var.historical -> VAR_HISTORICAL / risk.var.historical_es -> ES_HISTORICAL (ES-HS-1).
    model_version_id: uuid.UUID
    exposure_run_id: uuid.UUID | None = None  # build-in-request
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


def _hs_var_run_out(result: HsVarRunResult) -> VarRunOut:
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


@router.post(
    "/models/var-historical",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_historical(
    body: HsVarModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed historical-simulation VaR model + a model_version
    for this (code_version, confidence_level, horizon_days, window_observations,
    quantile_convention) identity (OD-VHS-B). Same-label different-declaration = 409; an
    out-of-vocabulary confidence, non-v1 horizon, or a window below the OD-VHS-E adequacy
    floor = 422. The shared registration envelope."""
    try:
        version = register_historical_var_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            confidence_level=body.confidence_level,
            window_observations=body.window_observations,
            horizon_days=body.horizon_days,
        )
    except ValueError:  # vocabulary / horizon / adequacy-floor refusals
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "confidence_level/horizon_days/window_observations outside the v1 declared "
                "vocabulary or below the adequacy floor"
            ),
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/models/var-historical-es",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_historical_es(
    body: HsVarModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed historical-simulation ES model + a model_version
    for this (code_version, confidence_level, horizon_days, window_observations,
    estimator_convention) identity (ES-HS-1, OD-B — the estimator convention is
    REGISTRAR-STAMPED, never caller-suppliable). Same-label different-declaration = 409; an
    out-of-vocabulary confidence, non-v1 horizon, or a window below the shared adequacy
    floor = 422. The shared registration envelope."""
    try:
        version = register_historical_var_es_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            confidence_level=body.confidence_level,
            window_observations=body.window_observations,
            horizon_days=body.horizon_days,
        )
    except ValueError:  # vocabulary / horizon / adequacy-floor refusals
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "confidence_level/horizon_days/window_observations outside the v1 declared "
                "vocabulary or below the adequacy floor"
            ),
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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


@router.post("/vars-historical/runs", response_model=VarRunOut, status_code=status.HTTP_201_CREATED)
def create_var_historical_run(
    body: HsVarRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> VarRunOut:
    """Run a governed historical-simulation calculation — EITHER family, dispatched on the
    bound model (VAR-HS-1: ``risk.var.historical`` ⇒ ``metric_type='VAR_HISTORICAL'``;
    ES-HS-1: ``risk.var.historical_es`` ⇒ ``metric_type='ES_HISTORICAL'``, the empirical
    tail mean). A pre-create refusal raises + rolls back (no run, 422/404/409); a post-create
    FAILED run is committed (``status='FAILED'``, zero rows — the magnitude gate). The run +
    row read back through the EXISTING ``GET /risk/vars/runs/{run_id}`` /
    ``GET /risk/vars/{var_id}`` (same run family + result table;
    ``z_score``/``sigma``/``covariance_run_id`` honestly null for both metrics)."""
    try:
        result = run_var_historical(
            db,
            acting_tenant=principal.tenant_id,
            actor=_var_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            exposure_run_id=(None if body.exposure_run_id is None else str(body.exposure_run_id)),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        HsVarInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        VarSnapshotError,
        FactorExposureRunNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit).
    response = _hs_var_run_out(result)
    db.commit()
    return response


# ---------- P3-7: ex-ante active risk / tracking error (parametric v1) ----------


def _active_risk_actor(principal: Principal) -> ActiveRiskActor:
    return ActiveRiskActor(actor_id=principal.user_id)


class ActiveRiskModelIn(BaseModel):
    code_version: str  # the ONLY identity input — no numeric parameters (OD-P3-7-D)


class ActiveRiskRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED active-risk model_version (CTRL-003; required)
    # build-in-request (all four together) XOR consume-existing (snapshot_id) — the P3-C1 gate.
    exposure_run_id: uuid.UUID | None = None
    covariance_run_id: uuid.UUID | None = None
    benchmark_id: uuid.UUID | None = None
    benchmark_effective_date: date | None = None
    snapshot_id: uuid.UUID | None = None


class ActiveRiskRowOut(BaseModel):
    id: str
    metric_type: str
    base_currency: str
    te_value: str  # a DAILY active-return volatility FRACTION (12dp; fixed-point, never scientific)
    portfolio_value: str  # the net book value used as the active-weight denominator (evidence)
    n_factors: int
    n_constituents: int
    benchmark_id: str
    benchmark_effective_date: date
    factor_exposure_run_id: str
    covariance_run_id: str
    model_version_id: str


class ActiveRiskRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[ActiveRiskRowOut]


def _active_risk_row_out(row: ActiveRiskResult) -> ActiveRiskRowOut:
    return ActiveRiskRowOut(
        id=row.id,
        metric_type=row.metric_type,
        base_currency=row.base_currency,
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        te_value=f"{row.te_value:f}",
        portfolio_value=f"{row.portfolio_value:f}",
        n_factors=row.n_factors,
        n_constituents=row.n_constituents,
        benchmark_id=row.benchmark_id,
        benchmark_effective_date=row.benchmark_effective_date,
        factor_exposure_run_id=row.factor_exposure_run_id,
        covariance_run_id=row.covariance_run_id,
        model_version_id=row.model_version_id,
    )


def _active_risk_run_out(result: ActiveRiskRunResult) -> ActiveRiskRunOut:
    run = result.run
    return ActiveRiskRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_active_risk_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/active-risk",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_active_risk(
    body: ActiveRiskModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed active-risk model + a model_version for this
    ``code_version`` identity and return its id (OD-P3-7-D — the v1 conventions ARE the identity;
    a same-label re-register with a different ``code_version`` is a 409). No numeric parameters."""
    try:
        version = register_active_risk_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/active-risk/runs",
    response_model=ActiveRiskRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_active_risk_run(
    body: ActiveRiskRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ActiveRiskRunOut:
    """Run a governed ex-ante active-risk (tracking-error) calculation. A pre-create refusal raises
    + rolls back (no run — incl. an uncovered exposure factor, a NULL/unmappable constituent
    currency, or a non-positive benchmark weight sum, 422); a post-create FAILED run is committed
    (``status='FAILED'``, zero rows — the OD-P3-5-G non-PSD radicand gate + a magnitude gate)."""
    try:
        result = run_active_risk(
            db,
            acting_tenant=principal.tenant_id,
            actor=_active_risk_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            exposure_run_id=(None if body.exposure_run_id is None else str(body.exposure_run_id)),
            covariance_run_id=(
                None if body.covariance_run_id is None else str(body.covariance_run_id)
            ),
            benchmark_id=(None if body.benchmark_id is None else str(body.benchmark_id)),
            benchmark_effective_date=body.benchmark_effective_date,
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        ActiveRiskInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        VarSnapshotError,  # incl. the ActiveRiskSnapshotError subclass (mapped to its own detail)
        FactorExposureRunNotVisible,
        CovarianceRunNotVisible,
        FactorNotVisible,  # build_active_risk_snapshot resolves each covariance factor definition
        BenchmarkNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _active_risk_run_out(result)
    db.commit()
    return response


@router.get("/active-risk/runs/{run_id}", response_model=ActiveRiskRunOut)
def get_active_risk_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ActiveRiskRunOut:
    """Read an active-risk run + its summary row (tenant-scoped; read-only). A committed FAILED run
    (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_active_risk_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except ActiveRiskRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="active-risk run not found"
        ) from None
    rows = list_active_risks(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return ActiveRiskRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_active_risk_row_out(r) for r in rows],
    )


@router.get("/active-risk", response_model=list[ActiveRiskRowOut])
def list_active_risk_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    benchmark_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ActiveRiskRowOut]:
    """API-1b entity read (Class C): governed active-risk rows resolved via the run's ROOT
    ``scope_portfolio_id`` + an optional native ``benchmark_id`` and ``as_of`` run cutoff.
    Silent-empty on a foreign/NULL-scope id. Each row carries ``calculation_run_id``."""
    rows = list_active_risk_results(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        benchmark_id=(str(benchmark_id) if benchmark_id is not None else None),
        as_of=as_of,
    )
    return [_active_risk_row_out(r) for r in rows]


@router.get("/active-risk/latest", response_model=list[ActiveRiskRowOut])
def latest_active_risk_endpoint(
    portfolio_id: uuid.UUID,
    benchmark_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ActiveRiskRowOut]:
    """API-1b latest-resolver: the newest COMPLETED active-risk run scoped to the portfolio (its
    metric row(s), optionally for one ``benchmark_id``). Empty when none."""
    rows = latest_active_risk_for_portfolio(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        benchmark_id=(str(benchmark_id) if benchmark_id is not None else None),
        as_of=as_of,
    )
    return [_active_risk_row_out(r) for r in rows]


@router.get("/active-risk/{active_risk_id}", response_model=ActiveRiskRowOut)
def get_active_risk(
    active_risk_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ActiveRiskRowOut:
    """Read a single ``active_risk_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_active_risk(db, str(active_risk_id), acting_tenant=principal.tenant_id)
    except ActiveRiskNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="active-risk result not found"
        ) from None
    return _active_risk_row_out(row)


# ---------- BT-1: VaR backtesting (ENT-055; REUSES risk.run/risk.view) ----------


def _var_backtest_actor(principal: Principal) -> VarBacktestActor:
    return VarBacktestActor(actor_id=principal.user_id)


class VarBacktestModelIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    alpha: str = "0.05"  # the DECLARED Kupiec significance level (OD-BT-1-A; {0.05, 0.01})


class VarBacktestRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED risk.var_backtest version (CTRL-003; required)
    # build-in-request (both) XOR consume-existing (snapshot_id) — the P3-C1 gate.
    portfolio_return_run_id: uuid.UUID | None = None
    var_run_ids: list[uuid.UUID] | None = None
    snapshot_id: uuid.UUID | None = None


class VarBacktestRowOut(BaseModel):
    id: str
    calculation_run_id: str  # API-1: discriminates runs in an entity/time read
    metric_type: str  # EXCEPTION_INDICATOR | EXCEPTION_COUNT | KUPIEC_LR | BASEL_ZONE
    var_metric_type: str  # WHICH VaR method was backtested (VAR_PARAMETRIC | VAR_HISTORICAL)
    period_start: date
    period_end: date
    metric_value: str  # 0/1, a count, or the Kupiec LR (fixed-point, never scientific)
    realized_pnl: str | None  # per-pair money evidence (None for summary rows)
    var_value: str | None
    n_pairs: int
    n_exceptions: int
    confidence_level: str
    horizon_days: int
    test_decision: str | None  # REJECT / FAIL_TO_REJECT (KUPIEC_LR row only)
    basel_zone: str | None  # GREEN / YELLOW / RED (BASEL_ZONE row only; domain-gated)
    base_currency: str
    portfolio_return_run_id: str
    model_version_id: str


class VarBacktestRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[VarBacktestRowOut]


def _var_backtest_row_out(row: VarBacktestResult) -> VarBacktestRowOut:
    return VarBacktestRowOut(
        id=row.id,
        calculation_run_id=row.calculation_run_id,
        metric_type=row.metric_type,
        var_metric_type=row.var_metric_type,
        period_start=row.period_start,
        period_end=row.period_end,
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        metric_value=f"{row.metric_value:f}",
        realized_pnl=None if row.realized_pnl is None else f"{row.realized_pnl:f}",
        var_value=None if row.var_value is None else f"{row.var_value:f}",
        n_pairs=row.n_pairs,
        n_exceptions=row.n_exceptions,
        confidence_level=f"{row.confidence_level:f}",
        horizon_days=row.horizon_days,
        test_decision=row.test_decision,
        basel_zone=row.basel_zone,
        base_currency=row.base_currency,
        portfolio_return_run_id=row.portfolio_return_run_id,
        model_version_id=row.model_version_id,
    )


def _var_backtest_run_out(result: VarBacktestRunResult) -> VarBacktestRunOut:
    run = result.run
    return VarBacktestRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_var_backtest_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/var-backtest",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_backtest(
    body: VarBacktestModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed VaR-backtesting model + a model_version for this
    ``(code_version, alpha)`` identity and return its id (OD-BT-1-A — the DECLARED alpha is part
    of the version identity; a same-label re-register with a different declaration is a 409; an
    off-vocabulary alpha is a 422)."""
    try:
        version = register_var_backtest_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            alpha=body.alpha,
        )
    except ValueError:
        # The strict alpha-vocabulary parse (never a 500 for an off-vocab declaration). A FIXED
        # opaque detail — the file's uniform refusal style (review fold: no raw str(exc) echo).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="alpha is not in the declared v1 vocabulary {0.05, 0.01}",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/var-backtests/runs",
    response_model=VarBacktestRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_var_backtest_run(
    body: VarBacktestRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> VarBacktestRunOut:
    """Run a governed VaR backtest. A pre-create refusal raises + rolls back (no run — incl. an
    unpaired forecast, a horizon mismatch, mixed methods, a broken MV chain, or a cross-portfolio
    identity failure, 422/404/409); a post-create FAILED run is committed (``status='FAILED'``,
    zero rows — the magnitude gate)."""
    try:
        result = run_var_backtest(
            db,
            acting_tenant=principal.tenant_id,
            actor=_var_backtest_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            portfolio_return_run_id=(
                None if body.portfolio_return_run_id is None else str(body.portfolio_return_run_id)
            ),
            var_run_ids=(None if body.var_run_ids is None else [str(r) for r in body.var_run_ids]),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        VarBacktestInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        VarBacktestSnapshotError,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _var_backtest_run_out(result)
    db.commit()
    return response


@router.get("/var-backtests/runs/{run_id}", response_model=VarBacktestRunOut)
def get_var_backtest_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> VarBacktestRunOut:
    """Read a var-backtest run + its result rows (tenant-scoped; read-only). A committed FAILED
    run (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_var_backtest_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except VarBacktestRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="var-backtest run not found"
        ) from None
    rows = list_var_backtests(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return VarBacktestRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_var_backtest_row_out(r) for r in rows],
    )


@router.get("/var-backtests", response_model=list[VarBacktestRowOut])
def list_var_backtests_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[VarBacktestRowOut]:
    """API-1 entity/time read: rows across COMPLETED runs filtered by entity + an optional
    ``as_of`` run cutoff (silent-empty on a foreign id). Each row carries ``calculation_run_id`` —
    cross-run aggregation is a CONSUMER ERROR."""
    rows = list_var_backtests_by_entity(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        as_of=as_of,
    )
    return [_var_backtest_row_out(r) for r in rows]


@router.get("/var-backtests/latest", response_model=list[VarBacktestRowOut])
def latest_var_backtests_endpoint(
    portfolio_id: uuid.UUID,
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[VarBacktestRowOut]:
    """API-1 latest-resolver: the newest COMPLETED run's rows for the entity (empty when none)."""
    rows = latest_var_backtest(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        as_of=as_of,
    )
    return [_var_backtest_row_out(r) for r in rows]


@router.get("/var-backtests/{result_id}", response_model=VarBacktestRowOut)
def get_var_backtest(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> VarBacktestRowOut:
    """Read a single ``var_backtest_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_var_backtest(db, str(result_id), acting_tenant=principal.tenant_id)
    except VarBacktestNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="var-backtest result not found"
        ) from None
    return _var_backtest_row_out(row)


# ---------- BT-3: ES backtesting (ENT-055 extension; REUSES risk.run/risk.view) ----------


def _es_backtest_actor(principal: Principal) -> EsBacktestActor:
    return EsBacktestActor(actor_id=principal.user_id)


class EsBacktestModelIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    significance: str = "0.05"  # the DECLARED Z2 verdict significance (OD-BT-3-B; {0.05, 0.0001})
    version_label: str | None = None  # defaults to the family's v1 label


class VarBacktestChristoffersenModelIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    alpha: str = "0.05"  # the DECLARED Kupiec/LR significance ({0.05, 0.01})
    version_label: str | None = None  # defaults to v2-christoffersen


class EsBacktestRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED risk.es_backtest version (CTRL-003; required)
    # build-in-request (all three) XOR consume-existing (snapshot_id).
    portfolio_return_run_id: uuid.UUID | None = None
    var_run_ids: list[uuid.UUID] | None = None
    es_run_ids: list[uuid.UUID] | None = None
    snapshot_id: uuid.UUID | None = None


class EsBacktestRowOut(BaseModel):
    id: str
    calculation_run_id: str  # API-1: discriminates runs in an entity/time read
    metric_type: str  # ES_EXCEPTION_INDICATOR | ES_PAIR_COUNT | AS_Z2 | AS_Z1
    var_metric_type: str  # always ES_HISTORICAL (the paired family)
    period_start: date
    period_end: date
    metric_value: str  # 0/1, the pair count, or a Z statistic (fixed-point, never scientific)
    realized_pnl: str | None  # per-pair money evidence (None for summary rows)
    var_value: str | None  # the VaR sibling's forecast (per-pair rows)
    es_value: str | None  # the ES forecast tested against (per-pair rows; migration 0043)
    n_pairs: int
    n_exceptions: int
    confidence_level: str
    horizon_days: int
    # REJECT / FAIL_TO_REJECT — AS_Z2 row ONLY, and ONLY inside the registered verdict domain
    # (confidence 0.9750 AND n_pairs 250); None elsewhere — the absence is derivable from the
    # persisted ES_PAIR_COUNT row + the version's stamped domain (OD-BT-3-B).
    test_decision: str | None
    base_currency: str
    portfolio_return_run_id: str
    model_version_id: str


class EsBacktestRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[EsBacktestRowOut]


def _es_backtest_row_out(row: VarBacktestResult) -> EsBacktestRowOut:
    return EsBacktestRowOut(
        id=row.id,
        calculation_run_id=row.calculation_run_id,
        metric_type=row.metric_type,
        var_metric_type=row.var_metric_type,
        period_start=row.period_start,
        period_end=row.period_end,
        metric_value=f"{row.metric_value:f}",
        realized_pnl=None if row.realized_pnl is None else f"{row.realized_pnl:f}",
        var_value=None if row.var_value is None else f"{row.var_value:f}",
        es_value=None if row.es_value is None else f"{row.es_value:f}",
        n_pairs=row.n_pairs,
        n_exceptions=row.n_exceptions,
        confidence_level=f"{row.confidence_level:f}",
        horizon_days=row.horizon_days,
        test_decision=row.test_decision,
        base_currency=row.base_currency,
        portfolio_return_run_id=row.portfolio_return_run_id,
        model_version_id=row.model_version_id,
    )


@router.post(
    "/models/es-backtest",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_es_backtest(
    body: EsBacktestModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed AS ES-backtest model + a model_version for this
    ``(code_version, significance)`` identity (BT-3, OD-BT-3-B/D — the verdict domain
    (0.9750, 250) is REGISTRAR-STAMPED, never caller-suppliable; an off-vocabulary significance
    is a 422; a same-label different-declaration is a 409)."""
    if body.version_label is not None and not body.version_label.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="version_label must be a non-empty string",
        )
    try:
        version = register_es_backtest_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            significance=body.significance,
            **({} if body.version_label is None else {"version_label": body.version_label}),
        )
    except ValueError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="significance is not in the declared v1 vocabulary {0.05, 0.0001}",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/models/var-backtest-christoffersen",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_var_backtest_christoffersen(
    body: VarBacktestChristoffersenModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the Christoffersen v2 of ``risk.var_backtest`` (BT-3, OD-BT-3-E:
    ``independence=CHRISTOFFERSEN_MARKOV`` is REGISTRAR-STAMPED; the shipped v1 stays
    byte-preserved via the absent-convention grandfather). Runs ride the EXISTING
    ``POST /risk/var-backtests/runs``."""
    if body.version_label is not None and not body.version_label.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="version_label must be a non-empty string",
        )
    try:
        version = register_var_backtest_christoffersen_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            alpha=body.alpha,
            **({} if body.version_label is None else {"version_label": body.version_label}),
        )
    except ValueError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="alpha is not in the declared v1 vocabulary {0.05, 0.01}",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/es-backtests/runs",
    response_model=EsBacktestRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_es_backtest_run(
    body: EsBacktestRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> EsBacktestRunOut:
    """Run a governed AS ES backtest (BT-3). A pre-create refusal raises + rolls back (no run —
    incl. a sibling snapshot/confidence mismatch, a non-bijective pairing, a stray metric_type,
    a per-leg model-version mix, ES <= 0, or any BT-1-class alignment failure; 422/404/409); a
    post-create FAILED run is committed (the magnitude gate)."""
    try:
        result = run_es_backtest(
            db,
            acting_tenant=principal.tenant_id,
            actor=_es_backtest_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            portfolio_return_run_id=(
                None if body.portfolio_return_run_id is None else str(body.portfolio_return_run_id)
            ),
            var_run_ids=(None if body.var_run_ids is None else [str(r) for r in body.var_run_ids]),
            es_run_ids=(None if body.es_run_ids is None else [str(r) for r in body.es_run_ids]),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        EsBacktestInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        VarBacktestSnapshotError,
    ) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None

    response = _es_backtest_run_out_from_result(result)
    db.commit()
    return response


def _es_backtest_run_out_from_result(result: EsBacktestRunResult) -> EsBacktestRunOut:
    run = result.run
    return EsBacktestRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_es_backtest_row_out(r) for r in result.rows],
    )


@router.get("/es-backtests/runs/{run_id}", response_model=EsBacktestRunOut)
def get_es_backtest_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> EsBacktestRunOut:
    """Read an es-backtest run + its result rows (tenant-scoped; read-only). A committed FAILED
    run (zero rows) is surfaced with ``status='FAILED'``, NOT a 404."""
    try:
        run = resolve_es_backtest_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except EsBacktestRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="es-backtest run not found"
        ) from None
    rows = list_es_backtests(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return EsBacktestRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,
        rows=[_es_backtest_row_out(r) for r in rows],
    )


@router.get("/es-backtests", response_model=list[EsBacktestRowOut])
def list_es_backtests_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[EsBacktestRowOut]:
    """API-1 entity/time read: rows across COMPLETED runs filtered by entity + an optional
    ``as_of`` run cutoff (silent-empty on a foreign id). Each row carries ``calculation_run_id`` —
    cross-run aggregation is a CONSUMER ERROR."""
    rows = list_es_backtests_by_entity(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        as_of=as_of,
    )
    return [_es_backtest_row_out(r) for r in rows]


@router.get("/es-backtests/latest", response_model=list[EsBacktestRowOut])
def latest_es_backtests_endpoint(
    portfolio_id: uuid.UUID,
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[EsBacktestRowOut]:
    """API-1 latest-resolver: the newest COMPLETED run's rows for the entity (empty when none)."""
    rows = latest_es_backtest(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        as_of=as_of,
    )
    return [_es_backtest_row_out(r) for r in rows]


@router.get("/es-backtests/{result_id}", response_model=EsBacktestRowOut)
def get_es_backtest(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> EsBacktestRowOut:
    """Read a single ES-backtest ``var_backtest_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_es_backtest(db, str(result_id), acting_tenant=principal.tenant_id)
    except EsBacktestNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="es-backtest result not found"
        ) from None
    return _es_backtest_row_out(row)


# ---------- P3-6: stress/scenario (ENT-029/030 — the tenth governed number) ----------


class ScenarioDefinitionIn(BaseModel):
    code: str
    name: str
    scenario_type: str  # HYPOTHETICAL | HISTORICAL | REGULATORY (binder-enforced)
    description: str | None = None
    valid_from: datetime | None = None  # capture-only EV valid-time; defaults to now


class ScenarioDefinitionUpdateIn(BaseModel):
    name: str | None = None
    scenario_type: str | None = None
    description: str | None = None


class ScenarioShockIn(BaseModel):
    factor_id: uuid.UUID
    shock_value: Decimal  # a signed RETURN fraction (-0.10 = -10%)
    shock_type: str = "RETURN"
    valid_from: datetime | None = None  # capture-only; a supersede uses effective_at


class ScenarioShockSupersedeIn(BaseModel):
    factor_id: uuid.UUID
    shock_value: Decimal
    shock_type: str = "RETURN"
    effective_at: datetime


class ScenarioShockCorrectIn(BaseModel):
    factor_id: uuid.UUID
    shock_value: Decimal
    shock_type: str = "RETURN"
    restatement_reason: str


class ScenarioDefinitionOut(BaseModel):
    id: str
    code: str
    name: str
    scenario_type: str
    description: str | None
    record_version: int


class ScenarioShockOut(BaseModel):
    id: str
    scenario_definition_id: str
    factor_id: str
    shock_value: str  # fixed-point, never scientific
    shock_type: str
    record_version: int
    valid_from: datetime
    valid_to: datetime | None


class ScenarioModelIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)


class ScenarioRunIn(BaseModel):
    code_version: str
    environment_id: str
    model_version_id: uuid.UUID  # a REGISTERED risk.scenario.factor_shock version (CTRL-003)
    # build-in-request (both) XOR consume-existing (snapshot_id) — the P3-C1 gate.
    factor_exposure_run_id: uuid.UUID | None = None
    scenario_definition_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None


class ScenarioRowOut(BaseModel):
    id: str
    metric_type: str  # SCENARIO_PNL | SCENARIO_PNL_TOTAL
    scenario_definition_id: str
    scenario_code: str
    factor_id: str | None  # NULL on the TOTAL row
    factor_code: str | None
    factor_family: str | None
    pnl: str  # fixed-point
    shock_value: str | None  # echoed input (per-factor rows only)
    exposure_amount: str | None
    n_factors_exposed: int | None  # TOTAL row only
    n_factors_shocked: int | None
    n_shocks_unmatched: int | None
    base_currency: str
    model_version_id: str
    calculation_run_id: str  # the run pin (TR-09) — cross-run aggregation is a CONSUMER ERROR


class ScenarioRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[ScenarioRowOut]


def _scenario_actor(principal: Principal) -> ScenarioActor:
    return ScenarioActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


def _definition_out(row: ScenarioDefinition) -> ScenarioDefinitionOut:
    return ScenarioDefinitionOut(
        id=row.id,
        code=row.code,
        name=row.name,
        scenario_type=row.scenario_type,
        description=row.description,
        record_version=row.record_version,
    )


def _shock_out(row: ScenarioShock) -> ScenarioShockOut:
    return ScenarioShockOut(
        id=row.id,
        scenario_definition_id=row.scenario_definition_id,
        factor_id=row.factor_id,
        shock_value=f"{row.shock_value:f}",
        shock_type=row.shock_type,
        record_version=row.record_version,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
    )


def _scenario_row_out(row: ScenarioResult) -> ScenarioRowOut:
    return ScenarioRowOut(
        id=row.id,
        metric_type=row.metric_type,
        scenario_definition_id=row.scenario_definition_id,
        scenario_code=row.scenario_code,
        factor_id=row.factor_id,
        factor_code=row.factor_code,
        factor_family=row.factor_family,
        pnl=f"{row.pnl:f}",
        shock_value=(None if row.shock_value is None else f"{row.shock_value:f}"),
        exposure_amount=(None if row.exposure_amount is None else f"{row.exposure_amount:f}"),
        n_factors_exposed=row.n_factors_exposed,
        n_factors_shocked=row.n_factors_shocked,
        n_shocks_unmatched=row.n_shocks_unmatched,
        base_currency=row.base_currency,
        model_version_id=row.model_version_id,
        calculation_run_id=row.calculation_run_id,
    )


def _scenario_run_out(result: ScenarioRunResult) -> ScenarioRunOut:
    run = result.run
    return ScenarioRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_scenario_row_out(r) for r in result.rows],
    )


def _raise_scenario_write(db: Session, exc: Exception) -> None:
    """Roll back, then map a scenario-write refusal. A unique-violation IntegrityError is a 409 with
    a detail DISCRIMINATED by which current-head constraint collided (the shared raiser serves both
    the definition-code path and the shock path — a shock-worded message on a duplicate code would
    misdescribe the conflict); any other integrity failure stays a loud 500."""
    db.rollback()
    if isinstance(exc, IntegrityError):
        if not is_unique_violation(exc):
            raise exc
        text = str(getattr(exc, "orig", exc))
        if "scenario_shock" in text:
            detail = "a current open shock already exists for this (scenario, factor)"
        elif "scenario_definition" in text:
            detail = "a scenario definition with this code already exists"
        else:
            detail = "a conflicting current-head scenario row already exists"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None
    code, detail = _map_error(exc)
    raise HTTPException(status_code=code, detail=detail) from None


@router.post(
    "/scenarios", response_model=ScenarioDefinitionOut, status_code=status.HTTP_201_CREATED
)
def create_scenario(
    body: ScenarioDefinitionIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ScenarioDefinitionOut:
    """Create a versioned scenario definition (EV; ``risk.run``-gated — defining IS the running
    persona's action). An out-of-vocab ``scenario_type`` is 422; a duplicate ``code`` is 409."""
    try:
        row = create_scenario_definition(
            db,
            code=body.code,
            name=body.name,
            scenario_type=body.scenario_type,
            acting_tenant=principal.tenant_id,
            actor=_scenario_actor(principal),
            description=body.description,
            valid_from=body.valid_from,
        )
    except (ScenarioValueError, IntegrityError) as exc:
        _raise_scenario_write(db, exc)
    out = _definition_out(row)
    db.commit()
    return out


@router.post("/scenarios/{scenario_id}/update", response_model=ScenarioDefinitionOut)
def update_scenario(
    scenario_id: uuid.UUID,
    body: ScenarioDefinitionUpdateIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ScenarioDefinitionOut:
    """In-place EV re-version of a scenario header (``record_version`` bump)."""
    try:
        definition = resolve_scenario_definition(
            db, str(scenario_id), acting_tenant=principal.tenant_id
        )
        row = update_scenario_definition(
            db,
            definition,
            acting_tenant=principal.tenant_id,
            actor=_scenario_actor(principal),
            name=body.name,
            scenario_type=body.scenario_type,
            description=body.description,
        )
    except (ScenarioNotVisible, ScenarioValueError) as exc:
        _raise_scenario_write(db, exc)
    out = _definition_out(row)
    db.commit()
    return out


@router.get("/scenarios", response_model=list[ScenarioDefinitionOut])
def list_scenarios(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ScenarioDefinitionOut]:
    """List the tenant's scenario definitions (read-only)."""
    rows = list_scenario_definitions(db, acting_tenant=principal.tenant_id)
    return [_definition_out(r) for r in rows]


@router.get("/scenarios/{scenario_id}/shocks", response_model=list[ScenarioShockOut])
def list_shocks(
    scenario_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ScenarioShockOut]:
    """The current-head shock set of a scenario (read-only)."""
    try:
        resolve_scenario_definition(db, str(scenario_id), acting_tenant=principal.tenant_id)
    except ScenarioNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="scenario not found"
        ) from None
    rows = list_scenario_shocks(
        db, scenario_definition_id=str(scenario_id), acting_tenant=principal.tenant_id
    )
    return [_shock_out(r) for r in rows]


@router.post(
    "/scenarios/{scenario_id}/shocks",
    response_model=ScenarioShockOut,
    status_code=status.HTTP_201_CREATED,
)
def capture_shock(
    scenario_id: uuid.UUID,
    body: ScenarioShockIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ScenarioShockOut:
    """Capture the first open shock for a (scenario, factor). Vocab/finiteness/CURRENCY-scope are
    422; a duplicate open shock is a discriminated 409."""
    try:
        row = capture_scenario_shock(
            db,
            scenario_definition_id=str(scenario_id),
            factor_id=str(body.factor_id),
            shock_value=body.shock_value,
            acting_tenant=principal.tenant_id,
            actor=_scenario_actor(principal),
            shock_type=body.shock_type,
            valid_from=body.valid_from,
        )
    except (ScenarioNotVisible, ScenarioValueError, DataQualityError, IntegrityError) as exc:
        _raise_scenario_write(db, exc)
    out = _shock_out(row)
    db.commit()
    return out


@router.post(
    "/scenarios/{scenario_id}/shocks/supersede",
    response_model=ScenarioShockOut,
    status_code=status.HTTP_201_CREATED,
)
def supersede_shock(
    scenario_id: uuid.UUID,
    body: ScenarioShockSupersedeIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ScenarioShockOut:
    """Effective-dated re-capture of a shock (valid-time). A backdated ``effective_at`` (window
    incoherence, MD-H1) is 422; no open head is 409."""
    try:
        row = supersede_scenario_shock(
            db,
            scenario_definition_id=str(scenario_id),
            factor_id=str(body.factor_id),
            shock_value=body.shock_value,
            acting_tenant=principal.tenant_id,
            actor=_scenario_actor(principal),
            effective_at=body.effective_at,
            shock_type=body.shock_type,
        )
    except (ScenarioValueError, NoCurrentScenarioShock, DataQualityError, IntegrityError) as exc:
        _raise_scenario_write(db, exc)
    out = _shock_out(row)
    db.commit()
    return out


@router.post(
    "/scenarios/{scenario_id}/shocks/correct",
    response_model=ScenarioShockOut,
    status_code=status.HTTP_201_CREATED,
)
def correct_shock(
    scenario_id: uuid.UUID,
    body: ScenarioShockCorrectIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ScenarioShockOut:
    """As-known (system-time) correction of a shock (TR-08; a restatement_reason is required)."""
    try:
        row = correct_scenario_shock(
            db,
            scenario_definition_id=str(scenario_id),
            factor_id=str(body.factor_id),
            shock_value=body.shock_value,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_scenario_actor(principal),
            shock_type=body.shock_type,
        )
    except (ScenarioValueError, NoCurrentScenarioShock, DataQualityError, IntegrityError) as exc:
        _raise_scenario_write(db, exc)
    out = _shock_out(row)
    db.commit()
    return out


@router.get("/scenarios/{scenario_id}/shocks/as-of", response_model=ScenarioShockOut)
def get_shock_as_of(
    scenario_id: uuid.UUID,
    factor_id: uuid.UUID,
    valid_at: datetime,
    known_at: datetime,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ScenarioShockOut:
    """The bitemporal reconstruct of one shock (read-only). 404 if no version covers both."""
    row = reconstruct_scenario_shock_as_of(
        db,
        scenario_definition_id=str(scenario_id),
        factor_id=str(factor_id),
        valid_at=valid_at,
        known_at=known_at,
        acting_tenant=principal.tenant_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no scenario shock as-of that instant"
        )
    return _shock_out(row)


@router.post(
    "/models/scenario", response_model=SensitivityModelOut, status_code=status.HTTP_201_CREATED
)
def register_scenario(
    body: ScenarioModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed scenario model + a model_version for this
    ``code_version`` identity and return its id (a same-label re-register with a different
    ``code_version`` is a 409)."""
    try:
        version = register_scenario_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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


@router.post("/scenario-runs", response_model=ScenarioRunOut, status_code=status.HTTP_201_CREATED)
def create_scenario_run(
    body: ScenarioRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ScenarioRunOut:
    """Run a governed factor-shock scenario. A pre-create refusal raises + rolls back (no run —
    422/404/409); a post-create FAILED run is committed (``status='FAILED'``, zero rows — the
    magnitude gate)."""
    try:
        result = run_scenario(
            db,
            acting_tenant=principal.tenant_id,
            actor=_scenario_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            factor_exposure_run_id=(
                None if body.factor_exposure_run_id is None else str(body.factor_exposure_run_id)
            ),
            scenario_definition_id=(
                None if body.scenario_definition_id is None else str(body.scenario_definition_id)
            ),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        ScenarioInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        ScenarioSnapshotError,
    ) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    response = _scenario_run_out(result)
    db.commit()
    return response


@router.get("/scenario-runs/{run_id}", response_model=ScenarioRunOut)
def get_scenario_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ScenarioRunOut:
    """Read a scenario run + its result rows (tenant-scoped; read-only). A committed FAILED run
    (zero rows) is surfaced with ``status='FAILED'``, NOT a 404."""
    try:
        run = resolve_scenario_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except ScenarioRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="scenario run not found"
        ) from None
    rows = list_scenario_results(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return ScenarioRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,
        rows=[_scenario_row_out(r) for r in rows],
    )


@router.get("/scenario-results/latest", response_model=list[ScenarioRowOut])
def latest_scenario_results_endpoint(
    scenario_definition_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ScenarioRowOut]:
    """API-1 latest-resolver (Class B): the newest COMPLETED scenario run's rows, optionally pinned
    to a ``scenario_definition_id`` (empty when none). A scenario run computes ONE definition, so
    the filter selects runs of that scenario. Each row carries ``calculation_run_id``."""
    rows = latest_scenario_results(
        db,
        acting_tenant=principal.tenant_id,
        scenario_definition_id=(
            str(scenario_definition_id) if scenario_definition_id is not None else None
        ),
        as_of=as_of,
    )
    return [_scenario_row_out(r) for r in rows]


@router.get("/scenario-results/{result_id}", response_model=ScenarioRowOut)
def get_scenario_result(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ScenarioRowOut:
    """Read a single ``scenario_result`` row by id (tenant-scoped; read-only) — the API-1 by-id
    parity read closing the house-pattern asymmetry."""
    try:
        row = resolve_scenario_result(db, str(result_id), acting_tenant=principal.tenant_id)
    except ScenarioResultNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="scenario result not found"
        ) from None
    return _scenario_row_out(row)


# ---------- PA-3: proxy-weight regression estimates (ENT-057) ----------


def _pw_actor(principal: Principal) -> ProxyWeightEstimateActor:
    return ProxyWeightEstimateActor(actor_id=principal.user_id)


class ProxyWeightModelIn(BaseModel):
    code_version: str  # the deterministic anchor
    min_observations: int  # the declared identity floor (>= 3; part of the model identity)


class ProxyWeightRunIn(BaseModel):
    code_version: str  # required (FW-RUN/TR-15)
    environment_id: str  # required
    model_version_id: uuid.UUID  # a REGISTERED proxy-weight model_version (CTRL-003)
    desmoothed_run_id: uuid.UUID | None = None  # build-in-request (with factor_ids)
    factor_ids: list[uuid.UUID] | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


class ProxyWeightRowOut(BaseModel):
    id: str
    calculation_run_id: str  # API-1: discriminates runs in an entity/time read
    metric_type: str  # WEIGHT | INTERCEPT | ESTIMATION_SUMMARY
    factor_id: str | None  # set on WEIGHT rows; null on INTERCEPT/ESTIMATION_SUMMARY
    metric_value: str  # coefficient (WEIGHT/INTERCEPT) | R^2 (ESTIMATION_SUMMARY)
    std_error: str | None  # coefficient std error (WEIGHT/INTERCEPT)
    n_observations: int | None  # ESTIMATION_SUMMARY only
    n_regressors: int | None
    residual_stdev: str | None
    min_observations: int
    series_currency: str
    source_desmoothed_run_id: str
    portfolio_id: str
    instrument_id: str


class ProxyWeightRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[ProxyWeightRowOut]


def _pw_row_out(row: ProxyWeightEstimateResult) -> ProxyWeightRowOut:
    return ProxyWeightRowOut(
        id=row.id,
        calculation_run_id=row.calculation_run_id,
        metric_type=row.metric_type,
        factor_id=row.factor_id,
        metric_value=str(row.metric_value),
        std_error=None if row.std_error is None else str(row.std_error),
        n_observations=row.n_observations,
        n_regressors=row.n_regressors,
        residual_stdev=None if row.residual_stdev is None else str(row.residual_stdev),
        min_observations=row.min_observations,
        series_currency=row.series_currency,
        source_desmoothed_run_id=row.source_desmoothed_run_id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
    )


def _pw_run_out(result: ProxyWeightEstimateRunResult) -> ProxyWeightRunOut:
    run = result.run
    return ProxyWeightRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_pw_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/proxy-weight-regression",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_proxy_weight_model(
    body: ProxyWeightModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) the governed proxy-weight regression model + a model_version for this
    ``(code_version, min_observations)`` identity (PA-3, OD-PA-3-D) — a same-label re-register with
    a different code_version OR floor is a governed 409 conflict. The run endpoint is
    ``POST /risk/proxy-weight-estimates/runs``."""
    try:
        version = register_proxy_weight_regression_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            min_observations=body.min_observations,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    except ValueError as exc:  # min_observations < 3 (the structural floor)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
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
    "/proxy-weight-estimates/runs",
    response_model=ProxyWeightRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_proxy_weight_run(
    body: ProxyWeightRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ProxyWeightRunOut:
    """Run a governed proxy-weight OLS estimation. A pre-create refusal raises + rolls back (no
    run); a post-create FAILED run (the magnitude gate) is committed with ``status='FAILED'`` + zero
    rows (durable refusal evidence)."""
    try:
        result = run_proxy_weight_estimate(
            db,
            acting_tenant=principal.tenant_id,
            actor=_pw_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            desmoothed_run_id=(
                None if body.desmoothed_run_id is None else str(body.desmoothed_run_id)
            ),
            factor_ids=(None if body.factor_ids is None else [str(f) for f in body.factor_ids]),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        ProxyWeightInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        ProxyWeightSnapshotError,
        FactorNotVisible,
    ) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    response = _pw_run_out(result)
    db.commit()
    return response


@router.get("/proxy-weight-estimates", response_model=list[ProxyWeightRowOut])
def list_proxy_weight_estimates_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ProxyWeightRowOut]:
    """API-1 entity/time read: rows across COMPLETED runs filtered by entity + an optional
    ``as_of`` run cutoff (silent-empty on a foreign id). Each row carries ``calculation_run_id`` —
    cross-run aggregation is a CONSUMER ERROR."""
    rows = list_proxy_weight_results_by_entity(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
        as_of=as_of,
    )
    return [_pw_row_out(r) for r in rows]


@router.get("/proxy-weight-estimates/latest", response_model=list[ProxyWeightRowOut])
def latest_proxy_weight_estimates_endpoint(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ProxyWeightRowOut]:
    """API-1 latest-resolver: the newest COMPLETED run's rows for the entity (empty when none)."""
    rows = latest_proxy_weight_result(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
        as_of=as_of,
    )
    return [_pw_row_out(r) for r in rows]


@router.get("/proxy-weight-estimates/runs/{run_id}", response_model=ProxyWeightRunOut)
def get_proxy_weight_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ProxyWeightRunOut:
    """Read a proxy-weight-estimate run + its rows (tenant-scoped; read-only). A committed FAILED
    run (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_proxy_weight_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except ProxyWeightEstimateRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="proxy-weight-estimate run not found"
        ) from None
    rows = list_proxy_weight_results(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return ProxyWeightRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,
        rows=[_pw_row_out(r) for r in rows],
    )


@router.get("/proxy-weight-estimates/{result_id}", response_model=ProxyWeightRowOut)
def get_proxy_weight_estimate(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ProxyWeightRowOut:
    """Read a single ``proxy_weight_estimate_result`` row by id (tenant-scoped; read-only) — the
    API-1 by-id parity read closing the house-pattern asymmetry."""
    try:
        row = resolve_proxy_weight_result(db, str(result_id), acting_tenant=principal.tenant_id)
    except ProxyWeightEstimateResultNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="proxy-weight-estimate not found"
        ) from None
    return _pw_row_out(row)


# ---------- RS-1: residual-estimator conventions (EWMA + empirical-Bayes shrinkage) ----------


class ProxyWeightEwmaModelIn(BaseModel):
    code_version: str
    decay_lambda: str  # the declared EWMA decay in (0, 1), e.g. "0.94" (0.<1..6 digits>)
    min_observations: int  # the declared regression observation floor (>= 3)
    version_label: str | None = None  # optional; defaults to the family's v2-ewma label


class ProxyWeightShrinkageEbModelIn(BaseModel):
    code_version: str
    version_label: str | None = None  # optional; defaults to the family's v2-shrinkage-eb label


class ResidualShrinkageRunIn(BaseModel):
    code_version: str  # required (FW-RUN/TR-15)
    environment_id: str  # required
    model_version_id: uuid.UUID  # a REGISTERED SHRINKAGE_CROSS_SECTIONAL_EB model_version
    target_estimate_run_id: uuid.UUID  # the cohort member this run shrinks (its raw estimate run)
    cohort_estimate_run_ids: list[uuid.UUID] | None = None  # build-in-request (>= 3 comparable)
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


@router.post(
    "/models/proxy-weight-ewma",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_proxy_weight_ewma_model_endpoint(
    body: ProxyWeightEwmaModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) an EWMA residual-variance version of the proxy-weight family (RS-1,
    OD-RS-1-A). The estimator convention + decay_lambda are REGISTRAR-STAMPED; a same-label
    re-register with a different declaration is a governed 409. Runs via the existing
    ``POST /risk/proxy-weight-estimates/runs`` (dispatch is on the bound version)."""
    try:
        version = register_proxy_weight_ewma_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            decay_lambda=body.decay_lambda,
            min_observations=body.min_observations,
            **({} if body.version_label is None else {"version_label": body.version_label}),
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    except ValueError as exc:  # bad decay_lambda / min_observations < 3
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
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
    "/models/proxy-weight-shrinkage-eb",
    response_model=SensitivityModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_proxy_weight_shrinkage_eb_model_endpoint(
    body: ProxyWeightShrinkageEbModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> SensitivityModelOut:
    """Register (idempotently) an empirical-Bayes shrinkage version of the proxy-weight family
    (RS-1, OD-RS-1-B). Method-as-identity: the convention is REGISTRAR-STAMPED, NO numeric intensity
    (the per-instrument w_i are computed + pin-reproduced). Runs via
    ``POST /risk/residual-shrinkage/runs``."""
    try:
        version = register_proxy_weight_shrinkage_eb_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            **({} if body.version_label is None else {"version_label": body.version_label}),
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
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
    "/residual-shrinkage/runs",
    response_model=ProxyWeightRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_residual_shrinkage_run(
    body: ResidualShrinkageRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ProxyWeightRunOut:
    """Run a governed empirical-Bayes residual shrinkage for one target instrument (RS-1,
    OD-RS-1-B). Pins the whole comparable cohort's raw estimates, recomputes every w_i from the pin,
    and persists ONE shrunk ESTIMATION_SUMMARY carrying the target's regression identity (promotes
    like a raw estimate). A pre-create refusal raises + rolls back (no run)."""
    try:
        result: ResidualShrinkageRunResult = run_residual_shrinkage(
            db,
            acting_tenant=principal.tenant_id,
            actor=_pw_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            target_estimate_run_id=str(body.target_estimate_run_id),
            cohort_estimate_run_ids=(
                None
                if body.cohort_estimate_run_ids is None
                else [str(r) for r in body.cohort_estimate_run_ids]
            ),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        ResidualShrinkageInputError,
        UnregisteredModelError,
        RejectedModelVersionError,
        ExpiredModelExceptionError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        ResidualShrinkageSnapshotError,
    ) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    run = result.run
    response = ProxyWeightRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_pw_row_out(r) for r in result.rows],
    )
    db.commit()
    return response


# ---------- PPF-1: the pure-private factor return (ENT-060, the 18th governed number) ----------
#
# Read-only surface (rule 7, in-slice): the run + model-registration paths are exercised only by
# the governed demo stage (irp_shared.demo, no HTTP) — the same asymmetry as every prior
# governed-number slice's demo path. list/latest/by-id mirror the API-1b VaR reads.


class PurePrivateFactorRowOut(BaseModel):
    id: str
    metric_type: str
    segment_factor_id: str
    period_start: date
    period_end: date
    metric_value: str
    member_count: int
    period_count: int | None
    pooling_convention: str
    intercept_convention: str
    min_members: int
    calculation_run_id: str
    input_snapshot_id: str
    model_version_id: str


def _ppf_row_out(row: PrivateFactorReturnResult) -> PurePrivateFactorRowOut:
    return PurePrivateFactorRowOut(
        id=row.id,
        metric_type=row.metric_type,
        segment_factor_id=row.segment_factor_id,
        period_start=row.period_start,
        period_end=row.period_end,
        metric_value=f"{row.metric_value:f}",
        member_count=row.member_count,
        period_count=row.period_count,
        pooling_convention=row.pooling_convention,
        intercept_convention=row.intercept_convention,
        min_members=row.min_members,
        calculation_run_id=row.calculation_run_id,
        input_snapshot_id=row.input_snapshot_id,
        model_version_id=row.model_version_id,
    )


@router.get("/private-factor-returns", response_model=list[PurePrivateFactorRowOut])
def list_private_factor_returns_endpoint(
    segment_factor_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[PurePrivateFactorRowOut]:
    """Rule-7 entity read: pure-private factor-return rows across COMPLETED runs for a segment
    factor + an optional ``as_of`` run cutoff (silent-empty on a foreign/unknown segment). Each row
    carries ``calculation_run_id`` — cross-run aggregation is a CONSUMER ERROR."""
    rows = list_pure_private_factor_results_by_segment(
        db,
        acting_tenant=principal.tenant_id,
        segment_factor_id=(str(segment_factor_id) if segment_factor_id is not None else None),
        as_of=as_of,
    )
    return [_ppf_row_out(r) for r in rows]


@router.get("/private-factor-returns/latest", response_model=list[PurePrivateFactorRowOut])
def latest_private_factor_returns_endpoint(
    segment_factor_id: uuid.UUID,
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[PurePrivateFactorRowOut]:
    """Rule-7 latest-resolver: the newest COMPLETED run's rows for the segment factor (empty when
    the segment has no COMPLETED run)."""
    rows = latest_pure_private_factor_for_segment(
        db,
        acting_tenant=principal.tenant_id,
        segment_factor_id=str(segment_factor_id),
        as_of=as_of,
    )
    return [_ppf_row_out(r) for r in rows]


@router.get("/private-factor-returns/{result_id}", response_model=PurePrivateFactorRowOut)
def get_private_factor_return(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PurePrivateFactorRowOut:
    """Read a single ``private_factor_return_result`` row by id (tenant-scoped; read-only)."""
    try:
        row = resolve_pure_private_factor_result(
            db, str(result_id), acting_tenant=principal.tenant_id
        )
    except PurePrivateFactorResultNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pure-private factor result not found"
        ) from None
    return _ppf_row_out(row)
