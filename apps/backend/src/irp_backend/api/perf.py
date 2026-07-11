"""Performance endpoints (PM-1 — ENT-053 portfolio_return_result): the governed portfolio-return
series (chain-linked time-weighted return, Modified-Dietz within caller-supplied exposure-run
valuation boundaries). The FIRST non-risk governed number, its OWN ``/perf`` family with its OWN
``perf.run``/``perf.view`` verb pair (a performance number is NOT a risk number — the governed R-07
mint).

Thin layer over the ``irp_shared.perf`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), IA TRUE
append-only, run-bound + snapshot-gated + **model_version-bound** (AD-014 / FW-RUN / TR-15 /
CTRL-003). ``POST /perf/portfolio-returns/runs`` is gated ``perf.run`` (maker); the reads gated
``perf.view`` (incl. ``auditor_3l``). ``POST /perf/models/portfolio-return`` registers the governed
return model (gated ``model.inventory.register``) so a run can bind a REGISTERED model_version.
``tenant_id`` server-stamped; a single end-of-request ``db.commit()``. There is **no
PUT/PATCH/DELETE** (append-only).

Failure model (the P3-7 precedent): a **pre-create refusal** (missing prerequisite / unregistered or
wrong model_version / unbuildable / cross-tenant / missing-FX-leg / ill-formed input) raises
(422/404/409) and rolls back — ZERO run. A **post-create FAILED** run is COMMITTED (a real resource
in FAILED state, ZERO rows — the magnitude gate) and returned with ``status='FAILED'``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, map_refusal, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import BenchmarkNotVisible, FxRateNotFound
from irp_shared.model.service import (
    ModelVersionConflictError,
    UnregisteredModelError,
    WrongModelVersionError,
)
from irp_shared.perf import (
    LIST_LIMIT_DEFAULT,
    BenchmarkRelativeActor,
    BenchmarkRelativeInputError,
    BenchmarkRelativeNotVisible,
    BenchmarkRelativeResult,
    BenchmarkRelativeRunNotVisible,
    BenchmarkRelativeRunResult,
    PerfRunQueryError,
    PortfolioReturnActor,
    PortfolioReturnInputError,
    PortfolioReturnNotVisible,
    PortfolioReturnResult,
    PortfolioReturnRunNotVisible,
    PortfolioReturnRunResult,
    list_benchmark_relatives,
    list_perf_runs,
    list_portfolio_returns,
    register_benchmark_relative_model,
    register_portfolio_return_model,
    resolve_benchmark_relative,
    resolve_benchmark_relative_run,
    resolve_portfolio_return,
    resolve_portfolio_return_run,
    run_benchmark_relative,
    run_portfolio_return,
)
from irp_shared.snapshot import (
    BenchmarkRelativeSnapshotError,
    ReturnSnapshotError,
    SnapshotNotFound,
    SnapshotPurposeError,
)

router = APIRouter(prefix="/perf", tags=["perf"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_run = require_permission("perf.run")
_require_view = require_permission("perf.view")
_require_register = require_permission("model.inventory.register")

#: Fail-closed PRE-CREATE exception -> (HTTP status, opaque detail).
_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    PortfolioReturnInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid portfolio-return run input",
    ),
    UnregisteredModelError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version is not registered (CTRL-003)",
    ),
    WrongModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version belongs to a different model (CTRL-003)",
    ),
    ModelVersionConflictError: (
        status.HTTP_409_CONFLICT,
        "version_label already registered with a different code_version",
    ),
    SnapshotPurposeError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid snapshot purpose"),
    SnapshotNotFound: (status.HTTP_404_NOT_FOUND, "snapshot not found"),
    ReturnSnapshotError: (
        status.HTTP_409_CONFLICT,
        "portfolio-return snapshot input failed closed",
    ),
    FxRateNotFound: (status.HTTP_409_CONFLICT, "no FX leg for a flow currency as-of"),
    PerfRunQueryError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid run listing filter"),
    BenchmarkRelativeInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid benchmark-relative run input",
    ),
    BenchmarkRelativeSnapshotError: (
        status.HTTP_409_CONFLICT,
        "benchmark-relative snapshot input failed closed",
    ),
    BenchmarkNotVisible: (status.HTTP_404_NOT_FOUND, "benchmark not found"),
}


def _map_error(exc: Exception) -> tuple[int, str]:
    """Resolve the (status, opaque detail) for a refusal exception by walking the MRO (the shared
    ``deps.map_refusal``; the risk/exposure/snapshot routers use it directly)."""
    return map_refusal(exc, _ERROR_MAP)


def _actor(principal: Principal) -> PortfolioReturnActor:
    return PortfolioReturnActor(actor_id=principal.user_id)


class PerfRunSummaryOut(BaseModel):
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


class PerfRunListOut(BaseModel):
    items: list[PerfRunSummaryOut]


@router.get("/runs", response_model=PerfRunListOut)
def get_perf_runs(
    run_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PerfRunListOut:
    """List the tenant's performance runs, newest first (the perf family only; read-only;
    fail-closed filters — an unknown ``run_type``/``status`` or out-of-bounds page is a 422, never a
    silently-empty page). The query param is ``status`` (aliased — the FastAPI ``status`` module
    shadows the name)."""
    try:
        runs = list_perf_runs(
            db,
            acting_tenant=principal.tenant_id,
            run_type=run_type,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except PerfRunQueryError as exc:
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from exc
    return PerfRunListOut(
        items=[
            PerfRunSummaryOut(
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


class PortfolioReturnModelIn(BaseModel):
    code_version: str  # the ONLY identity input — no numeric parameters (OD-PM-1-D)


class PortfolioReturnModelOut(BaseModel):
    model_version_id: str
    model_id: str
    version_label: str
    methodology_ref: str | None
    code_version: str | None
    status: str | None


class PortfolioReturnRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED perf.return.twr model_version (CTRL-003; required)
    # build-in-request (>= 2 ORDERED boundary exposure runs) XOR consume-existing (snapshot_id).
    exposure_run_ids: list[uuid.UUID] | None = None
    snapshot_id: uuid.UUID | None = None


class PortfolioReturnRowOut(BaseModel):
    id: str
    portfolio_id: str
    metric_type: str  # DIETZ_PERIOD (per sub-period) | TWR_LINKED (summary)
    period_start: date
    period_end: date
    begin_mv: str  # base-currency money (fixed-point, never scientific)
    end_mv: str
    net_external_flow: str
    return_value: str  # a return FRACTION (12dp)
    n_flows: int
    n_periods: int
    base_currency: str
    model_version_id: str


class PortfolioReturnRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[PortfolioReturnRowOut]


def _row_out(row: PortfolioReturnResult) -> PortfolioReturnRowOut:
    return PortfolioReturnRowOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        metric_type=row.metric_type,
        period_start=row.period_start,
        period_end=row.period_end,
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        begin_mv=f"{row.begin_mv:f}",
        end_mv=f"{row.end_mv:f}",
        net_external_flow=f"{row.net_external_flow:f}",
        return_value=f"{row.return_value:f}",
        n_flows=row.n_flows,
        n_periods=row.n_periods,
        base_currency=row.base_currency,
        model_version_id=row.model_version_id,
    )


def _run_out(result: PortfolioReturnRunResult) -> PortfolioReturnRunOut:
    run = result.run
    return PortfolioReturnRunOut(
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
    "/models/portfolio-return",
    response_model=PortfolioReturnModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_portfolio_return(
    body: PortfolioReturnModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> PortfolioReturnModelOut:
    """Register (idempotently) the governed portfolio-return model + a model_version for this
    ``code_version`` identity and return its id (OD-PM-1-D — the v1 conventions ARE the identity; a
    same-label re-register with a different ``code_version`` is a 409). No numeric parameters."""
    try:
        version = register_portfolio_return_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        # WrongModelVersionError: a same-label twin exists that is NOT a REGISTERED version of this
        # family (generically minted) — a governed refusal, not a 500 (P3-C1).
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    out = PortfolioReturnModelOut(
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
    "/portfolio-returns/runs",
    response_model=PortfolioReturnRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_portfolio_return_run(
    body: PortfolioReturnRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> PortfolioReturnRunOut:
    """Run a governed portfolio-return calculation. A pre-create refusal raises + rolls back (no
    run — incl. fewer than two boundaries, a multi-portfolio book, a NULL/unmappable flow currency,
    a missing FX leg, or a non-positive begin MV / Dietz denominator, 422/404/409); a post-create
    FAILED run is committed (``status='FAILED'``, zero rows — the magnitude gate)."""
    try:
        result = run_portfolio_return(
            db,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            exposure_run_ids=(
                None if body.exposure_run_ids is None else [str(r) for r in body.exposure_run_ids]
            ),
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        PortfolioReturnInputError,
        UnregisteredModelError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        ReturnSnapshotError,
        FxRateNotFound,
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


@router.get("/portfolio-returns/runs/{run_id}", response_model=PortfolioReturnRunOut)
def get_portfolio_return_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PortfolioReturnRunOut:
    """Read a portfolio-return run + its series rows (tenant-scoped; read-only). A committed FAILED
    run (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_portfolio_return_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except PortfolioReturnRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio-return run not found"
        ) from None
    rows = list_portfolio_returns(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return PortfolioReturnRunOut(
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


@router.get("/portfolio-returns/{result_id}", response_model=PortfolioReturnRowOut)
def get_portfolio_return(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PortfolioReturnRowOut:
    """Read a single ``portfolio_return_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_portfolio_return(db, str(result_id), acting_tenant=principal.tenant_id)
    except PortfolioReturnNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio-return result not found"
        ) from None
    return _row_out(row)


# ---------- P3-8: ex-post benchmark-relative (ENT-054; REUSES perf.run/perf.view) ----------


def _br_actor(principal: Principal) -> BenchmarkRelativeActor:
    return BenchmarkRelativeActor(actor_id=principal.user_id)


class BenchmarkRelativeModelIn(BaseModel):
    code_version: str  # the ONLY identity input — no numeric parameters (OD-P3-8-A)


class BenchmarkRelativeRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED perf.benchmark_relative version (CTRL-003; required)
    # build-in-request (all three) XOR consume-existing (snapshot_id) — the P3-C1 gate.
    portfolio_return_run_id: uuid.UUID | None = None
    benchmark_id: uuid.UUID | None = None
    return_basis: str | None = None  # PRICE / TOTAL / NET_TOTAL
    snapshot_id: uuid.UUID | None = None


class BenchmarkRelativeRowOut(BaseModel):
    id: str
    metric_type: str  # ACTIVE_RETURN | TRACKING_DIFFERENCE | TRACKING_ERROR | INFORMATION_RATIO
    period_start: date
    period_end: date
    metric_value: str  # a fraction/ratio (12dp; fixed-point, never scientific)
    portfolio_return_value: str | None  # None for TE/IR rows
    benchmark_return_value: str | None
    n_benchmark_obs: int
    n_periods: int
    base_currency: str
    return_basis: str
    benchmark_id: str
    portfolio_return_run_id: str
    model_version_id: str


class BenchmarkRelativeRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[BenchmarkRelativeRowOut]


def _br_row_out(row: BenchmarkRelativeResult) -> BenchmarkRelativeRowOut:
    return BenchmarkRelativeRowOut(
        id=row.id,
        metric_type=row.metric_type,
        period_start=row.period_start,
        period_end=row.period_end,
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        metric_value=f"{row.metric_value:f}",
        portfolio_return_value=(
            None if row.portfolio_return_value is None else f"{row.portfolio_return_value:f}"
        ),
        benchmark_return_value=(
            None if row.benchmark_return_value is None else f"{row.benchmark_return_value:f}"
        ),
        n_benchmark_obs=row.n_benchmark_obs,
        n_periods=row.n_periods,
        base_currency=row.base_currency,
        return_basis=row.return_basis,
        benchmark_id=row.benchmark_id,
        portfolio_return_run_id=row.portfolio_return_run_id,
        model_version_id=row.model_version_id,
    )


def _br_run_out(result: BenchmarkRelativeRunResult) -> BenchmarkRelativeRunOut:
    run = result.run
    return BenchmarkRelativeRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_br_row_out(r) for r in result.rows],
    )


@router.post(
    "/models/benchmark-relative",
    response_model=PortfolioReturnModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_benchmark_relative(
    body: BenchmarkRelativeModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> PortfolioReturnModelOut:
    """Register (idempotently) the governed ex-post benchmark-relative model + a model_version for
    this ``code_version`` identity and return its id (OD-P3-8-A — the v1 conventions ARE the
    identity; a same-label re-register with a different ``code_version`` is a 409). The shared
    model-registration response envelope."""
    try:
        version = register_benchmark_relative_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
        )
    except (ModelVersionConflictError, WrongModelVersionError) as exc:
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None
    out = PortfolioReturnModelOut(
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
    "/benchmark-relative/runs",
    response_model=BenchmarkRelativeRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_benchmark_relative_run(
    body: BenchmarkRelativeRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> BenchmarkRelativeRunOut:
    """Run a governed ex-post benchmark-relative calculation. A pre-create refusal raises + rolls
    back (no run — incl. a currency mismatch, a zero-benchmark-window, or a linkage mismatch,
    422/404/409); a post-create FAILED run is committed (``status='FAILED'``, zero rows — the
    magnitude gate)."""
    try:
        result = run_benchmark_relative(
            db,
            acting_tenant=principal.tenant_id,
            actor=_br_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            portfolio_return_run_id=(
                None if body.portfolio_return_run_id is None else str(body.portfolio_return_run_id)
            ),
            benchmark_id=(None if body.benchmark_id is None else str(body.benchmark_id)),
            return_basis=body.return_basis,
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
        )
    except (
        BenchmarkRelativeInputError,
        UnregisteredModelError,
        WrongModelVersionError,
        SnapshotPurposeError,
        SnapshotNotFound,
        BenchmarkRelativeSnapshotError,
        BenchmarkNotVisible,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        db.rollback()
        code, detail = _map_error(exc)
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _br_run_out(result)
    db.commit()
    return response


@router.get("/benchmark-relative/runs/{run_id}", response_model=BenchmarkRelativeRunOut)
def get_benchmark_relative_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> BenchmarkRelativeRunOut:
    """Read a benchmark-relative run + its series rows (tenant-scoped; read-only). A committed
    FAILED run (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a
    404."""
    try:
        run = resolve_benchmark_relative_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except BenchmarkRelativeRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="benchmark-relative run not found"
        ) from None
    rows = list_benchmark_relatives(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return BenchmarkRelativeRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C1)
        rows=[_br_row_out(r) for r in rows],
    )


@router.get("/benchmark-relative/{result_id}", response_model=BenchmarkRelativeRowOut)
def get_benchmark_relative(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> BenchmarkRelativeRowOut:
    """Read a single ``benchmark_relative_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_benchmark_relative(db, str(result_id), acting_tenant=principal.tenant_id)
    except BenchmarkRelativeNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="benchmark-relative result not found"
        ) from None
    return _br_row_out(row)
