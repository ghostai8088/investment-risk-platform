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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.exposure import (
    ExposureActor,
    ExposureAggregate,
    ExposureInputError,
    ExposureNotVisible,
    ExposureRunNotVisible,
    ExposureRunResult,
    list_exposure,
    resolve_exposure,
    resolve_run,
    run_exposure,
)
from irp_shared.marketdata import FxRateNotFound
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
    SnapshotPurposeError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid snapshot purpose"),
    PortfolioNotVisible: (status.HTTP_404_NOT_FOUND, "portfolio not found"),
    SnapshotNotFound: (status.HTTP_404_NOT_FOUND, "snapshot not found"),
    HierarchyCycleError: (status.HTTP_409_CONFLICT, "hierarchy cycle or depth exceeded"),
    EmptySnapshotError: (status.HTTP_409_CONFLICT, "bound scope yields no components"),
    FxRateNotFound: (status.HTTP_409_CONFLICT, "no published FX path for a mark currency as-of"),
    DataQualityError: (status.HTTP_409_CONFLICT, "bound input set is incomplete"),
}


def _actor(principal: Principal) -> ExposureActor:
    return ExposureActor(actor_id=principal.user_id)


class ExposureRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    portfolio_id: uuid.UUID | None = None  # build-in-request scope (with as_of_valid_at)
    as_of_valid_at: datetime | None = None
    base_currency: str | None = None  # default: portfolio base, else USD
    as_of_known_at: datetime | None = None
    snapshot_id: uuid.UUID | None = None  # consume-existing alternative


class ExposureRowOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    base_currency: str
    mark_currency: str
    signed_quantity: str
    mark_value: str
    fx_rate: str
    fx_legs: list[dict]
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
    return ExposureRowOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        base_currency=row.base_currency,
        mark_currency=row.mark_currency,
        signed_quantity=str(row.signed_quantity),
        mark_value=str(row.mark_value),
        fx_rate=str(row.fx_rate),
        fx_legs=json.loads(row.fx_legs),
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
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _run_out(result)
    db.commit()
    return response


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
        failure_reason=None,
        rows=[_row_out(r) for r in rows],
    )


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
