"""Exposure endpoints (P2-3, ENT-014) — the first governed derived number (basic signed market
value).

Thin layer over the ``irp_shared.exposure`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), IA
TRUE
append-only, run-bound + snapshot-gated (AD-014 / FW-RUN / TR-15). ``POST /exposure/runs`` is gated
``exposure.aggregate.run`` (maker); the reads gated ``exposure.view`` (incl. ``auditor_3l``).
``tenant_id`` server-stamped; a single end-of-request ``db.commit()``. There is **no
PUT/PATCH/DELETE**
(append-only).

Failure model (OD-P2-3-F): a **pre-create refusal** (missing prerequisite / unbuildable /
cross-tenant
/ incomplete / FX-missing) raises (422/404/409) and rolls back — ZERO run. A **post-create FAILED**
run
is COMMITTED (a real resource in FAILED state, ZERO rows) and returned with ``status='FAILED'``.
**NOT
risk** — ``MARKET_VALUE`` only.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, map_refusal, require_permission
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.exposure import (
    LIST_LIMIT_DEFAULT,
    ExposureActor,
    ExposureAggregate,
    ExposureInputError,
    ExposureNotVisible,
    ExposureRunNotVisible,
    ExposureRunQueryError,
    ExposureRunResult,
    ReportingCurrencyConflictError,
    UndeclaredReportingCurrencyError,
    latest_exposure,
    list_exposure,
    list_exposure_by_entity,
    list_exposure_runs,
    resolve_exposure,
    resolve_run,
    run_exposure,
)
from irp_shared.marketdata import FxRateNotFound, derive_pivot
from irp_shared.portfolio import HierarchyCycleError, PortfolioNotVisible
from irp_shared.snapshot import EmptySnapshotError, SnapshotNotFound, SnapshotPurposeError

router = APIRouter(prefix="/exposure", tags=["exposure"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_run = require_permission("exposure.aggregate.run")
_require_view = require_permission("exposure.view")

#: Fail-closed PRE-CREATE exception -> (HTTP status, opaque detail). Cross-tenant/unknown is an
#: indistinguishable 404; completeness/empty/cycle/FX-missing are 409; bad input is 422.
_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    ExposureInputError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid exposure run input"),
    # STRUCT-4 (DP-11): subclasses carry their OWN keys (the API-2 error-map lesson) — each
    # refusal names its distinct cause rather than collapsing into the generic input detail.
    UndeclaredReportingCurrencyError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "no reporting currency declared on the scope or any ancestor",
    ),
    ReportingCurrencyConflictError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "base_currency contradicts the node's declared reporting currency",
    ),
    SnapshotPurposeError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid snapshot purpose"),
    PortfolioNotVisible: (status.HTTP_404_NOT_FOUND, "portfolio not found"),
    SnapshotNotFound: (status.HTTP_404_NOT_FOUND, "snapshot not found"),
    HierarchyCycleError: (status.HTTP_409_CONFLICT, "hierarchy cycle or depth exceeded"),
    EmptySnapshotError: (status.HTTP_409_CONFLICT, "bound scope yields no components"),
    FxRateNotFound: (status.HTTP_409_CONFLICT, "no published FX path for a mark currency as-of"),
    DataQualityError: (status.HTTP_409_CONFLICT, "bound input set is incomplete"),
    ExposureRunQueryError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid run listing filter"),
}


class ExposureRunSummaryOut(BaseModel):
    run_id: str
    run_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    initiated_by: str
    input_snapshot_id: str | None
    # Always None for the model-less exposure family; carried for byte-for-byte parity with the
    # risk sibling (RiskRunSummaryOut) so the shared FE RiskRunSummary contract is satisfied.
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    failure_reason: str | None


class ExposureRunListOut(BaseModel):
    items: list[ExposureRunSummaryOut]


def _actor(principal: Principal) -> ExposureActor:
    return ExposureActor(actor_id=principal.user_id)


class ExposureRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    portfolio_id: uuid.UUID | None = None  # build-in-request scope (with as_of_valid_at)
    as_of_valid_at: datetime | None = None
    # STRUCT-4 (DP-11): default = the scope's DECLARED reporting currency (own, else inherited
    # from the nearest declared ancestor); an undeclared scope REFUSES — the "else USD" tail died.
    base_currency: str | None = None
    as_of_known_at: datetime | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative
    # STRUCT-3 (DP-7 / REQ-PPM-008): the consume path's explicit node — REQUIRED for a
    # full-subtree (v2) snapshot; validated against the pinned subtree; stamped on the run.
    scope_node_id: uuid.UUID | None = None


class ExposureRowOut(BaseModel):
    id: str
    calculation_run_id: str  # API-1: discriminates runs in an entity/time read
    portfolio_id: str
    instrument_id: str
    base_currency: str
    mark_currency: str
    signed_quantity: str
    mark_value: str
    fx_rate: str
    fx_legs: list[dict]
    # STRUCT-4 (DP-12): the triangulation pivot — STATED in new rows' legs, DERIVED at read
    # time for shipped rows (their pinned bytes are never rewritten); None off the 2-leg path.
    fx_pivot: str | None
    exposure_amount: str
    exposure_type: str


class ExposureRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[ExposureRowOut]


def _row_out(row: ExposureAggregate) -> ExposureRowOut:
    legs = json.loads(row.fx_legs)
    return ExposureRowOut(
        id=row.id,
        calculation_run_id=row.calculation_run_id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        base_currency=row.base_currency,
        mark_currency=row.mark_currency,
        signed_quantity=str(row.signed_quantity),
        mark_value=str(row.mark_value),
        fx_rate=str(row.fx_rate),
        fx_legs=legs,
        fx_pivot=derive_pivot(legs),
        exposure_amount=str(row.exposure_amount),
        exposure_type=row.exposure_type,
    )


def _run_out(result: ExposureRunResult) -> ExposureRunOut:
    run = result.run
    return ExposureRunOut(
        run_id=run.run_id,
        status=result.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=result.failure_reason,
        rows=[_row_out(r) for r in result.rows],
    )


@router.post("/runs", response_model=ExposureRunOut, status_code=status.HTTP_201_CREATED)
def create_exposure_run(
    body: ExposureRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ExposureRunOut:
    """Run a governed exposure aggregation. A pre-create refusal raises + rolls back (no run); a
    post-create FAILED run is committed (``status='FAILED'``, zero rows)."""
    try:
        result = run_exposure(
            db,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            portfolio_id=(None if body.portfolio_id is None else str(body.portfolio_id)),
            as_of_valid_at=body.as_of_valid_at,
            base_currency=body.base_currency,
            as_of_known_at=body.as_of_known_at,
            snapshot_id=(None if body.snapshot_id is None else str(body.snapshot_id)),
            scope_node_id=(None if body.scope_node_id is None else str(body.scope_node_id)),
        )
    except (
        ExposureInputError,
        SnapshotPurposeError,
        PortfolioNotVisible,
        SnapshotNotFound,
        HierarchyCycleError,
        EmptySnapshotError,
        FxRateNotFound,
        DataQualityError,
    ) as exc:
        # Pre-create refusal: whole-unit rollback (no run/exposure/audit) before the HTTP error.
        db.rollback()
        code, detail = map_refusal(exc, _ERROR_MAP)
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _run_out(result)
    db.commit()
    return response


@router.get("/runs", response_model=ExposureRunListOut)
def get_exposure_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = LIST_LIMIT_DEFAULT,
    offset: int = 0,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ExposureRunListOut:
    """List the tenant's EXPOSURE_AGGREGATE runs, newest first (gated ``exposure.view`` — the
    sibling of ``GET /risk/runs`` for the exposure family; read-only; fail-closed filters). The
    query param is ``status`` (aliased — the FastAPI ``status`` module shadows the name)."""
    try:
        runs = list_exposure_runs(
            db,
            acting_tenant=principal.tenant_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except ExposureRunQueryError as exc:
        code, detail = map_refusal(exc, _ERROR_MAP)
        raise HTTPException(status_code=code, detail=detail) from exc
    return ExposureRunListOut(
        items=[
            ExposureRunSummaryOut(
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


@router.get("/runs/{run_id}", response_model=ExposureRunOut)
def get_exposure_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ExposureRunOut:
    """Read an exposure run + its rows (tenant-scoped; read-only). Returns the REAL run envelope —
    a committed FAILED run (zero rows) is surfaced with ``status='FAILED'`` (the durable refusal
    evidence a 3L auditor reviews), NOT a 404 (reserved for an unknown/cross-tenant run)."""
    try:
        run = resolve_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except ExposureRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="exposure run not found"
        ) from None
    rows = list_exposure(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return ExposureRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,  # persisted at the FAILED transition (P3-C2 scaffold)
        rows=[_row_out(r) for r in rows],
    )


@router.get("", response_model=list[ExposureRowOut])
def list_exposure_by_entity_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    exposure_type: str | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ExposureRowOut]:
    """API-1 entity/time read: exposure-aggregate rows across COMPLETED runs filtered by
    ``portfolio_id``/``instrument_id`` + an optional ``as_of`` run cutoff (a run spans the portfolio
    SUBTREE, so the filter row-filters to the queried book; silent-empty on a foreign id). Each row
    carries ``calculation_run_id`` — cross-run aggregation is a CONSUMER ERROR.
    ``exposure_type`` (STRUCT-1) filters to ONE measure; an unknown measure is a 422."""
    try:
        rows = list_exposure_by_entity(
            db,
            acting_tenant=principal.tenant_id,
            portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
            instrument_id=(str(instrument_id) if instrument_id is not None else None),
            as_of=as_of,
            exposure_type=exposure_type,
        )
    except ExposureInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    return [_row_out(r) for r in rows]


@router.get("/latest", response_model=list[ExposureRowOut])
def latest_exposure_endpoint(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    exposure_type: str | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ExposureRowOut]:
    """API-1 latest-resolver: the newest COMPLETED exposure run's rows for the portfolio (empty
    when none). ``exposure_type`` (STRUCT-1) = the newest run CARRYING that measure; an unknown
    measure is a 422."""
    try:
        rows = latest_exposure(
            db,
            acting_tenant=principal.tenant_id,
            portfolio_id=str(portfolio_id),
            instrument_id=(str(instrument_id) if instrument_id is not None else None),
            as_of=as_of,
            exposure_type=exposure_type,
        )
    except ExposureInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    return [_row_out(r) for r in rows]


class ExposureSumOut(BaseModel):
    total: str  # decimal-as-string, the platform convention
    exposure_type: str
    base_currency: str
    calculation_run_id: str
    n_rows: int


@router.get("/latest/sum", response_model=ExposureSumOut)
def summed_latest_exposure_endpoint(
    portfolio_id: uuid.UUID,
    exposure_type: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ExposureSumOut:
    """STRUCT-2 (REQ-PPM-007): the ADDITIVE positive case — the newest COMPLETED run's total for
    ONE declared measure. Refuses 422 without ``exposure_type`` (a sum across measures is a
    category error, never a conversion) and consults the aggregation contract before summing."""
    from irp_shared.aggregation.contracts import NotAggregatableError
    from irp_shared.exposure.service import NothingToSumError, summed_latest_exposure

    try:
        result = summed_latest_exposure(
            db,
            acting_tenant=principal.tenant_id,
            portfolio_id=str(portfolio_id),
            exposure_type=exposure_type,
            as_of=as_of,
        )
    except (ExposureInputError, NotAggregatableError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    except NothingToSumError as exc:
        # 409, the empty-scope convention: an empty book is a state of the world, not a caller
        # defect (review fold).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return ExposureSumOut(
        total=str(result.total),
        exposure_type=result.exposure_type,
        base_currency=result.base_currency,
        calculation_run_id=result.calculation_run_id,
        n_rows=result.n_rows,
    )


class NodeRollupOut(BaseModel):
    node_id: str
    exposure_type: str
    total: str
    n_rows: int
    base_currency: str
    # STRUCT-4 (REQ-PPM-010): the node's declared reporting currency + the total TRANSLATED into
    # it from the run's PINNED FX (decimals as strings; legs carry the published-rate evidence;
    # the pivot is stated where two legs were taken). A pre-PPM-010 snapshot lacking the leg
    # surfaces ``missing_fx`` honestly — never a retroactive refusal, never a fabricated 1.0.
    reporting_currency: str | None
    translated_total: str | None
    translated_currency: str | None
    translation_fx_rate: str | None
    translation_legs: list[dict]
    translation_pivot: str | None
    missing_fx: str | None


@router.get("/runs/{run_id}/rollup", response_model=list[NodeRollupOut])
def rollup_exposure_endpoint(
    run_id: uuid.UUID,
    node_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[NodeRollupOut]:
    """STRUCT-3 (REQ-PPM-008 / DP-9): a node's composed totals per measure — read-time
    composition over the run's leaf rows within the node's PINNED subtree; the contract governs
    (operator + grain selector); no parent row is persisted. 422 on a node outside the pinned
    subtree or a pre-STRUCT-3 run."""
    from irp_shared.aggregation.contracts import NotAggregatableError
    from irp_shared.exposure.service import rollup_exposure

    try:
        rollups = rollup_exposure(
            db, acting_tenant=principal.tenant_id, run_id=str(run_id), node_id=str(node_id)
        )
    except (ExposureInputError, NotAggregatableError) as exc:
        # NotAggregatableError joined at the review fold: the PPM-007 refusal must reach HTTP
        # as a 422, never a 500 (map_refusal KeyErrors loudly on unmapped classes).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    except ExposureRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="exposure run not found"
        ) from None
    return [
        NodeRollupOut(
            node_id=r.node_id,
            exposure_type=r.exposure_type,
            total=str(r.total),
            n_rows=r.n_rows,
            base_currency=r.base_currency,
            reporting_currency=r.reporting_currency,
            translated_total=(None if r.translated_total is None else str(r.translated_total)),
            translated_currency=r.translated_currency,
            translation_fx_rate=(
                None if r.translation_fx_rate is None else str(r.translation_fx_rate)
            ),
            translation_legs=[leg.as_dict() for leg in r.translation_legs],
            translation_pivot=r.translation_pivot,
            missing_fx=r.missing_fx,
        )
        for r in rollups
    ]


@router.get("/{exposure_id}", response_model=ExposureRowOut)
def get_exposure(
    exposure_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ExposureRowOut:
    """Read a single ``exposure_aggregate`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_exposure(db, str(exposure_id), acting_tenant=principal.tenant_id)
    except ExposureNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="exposure not found"
        ) from None
    return _row_out(row)
