"""Liquidity endpoints (LQ-1, ENT-071 — the 24th governed number family).

Thin layer over the ``irp_shared.liquidity`` binder. PROPRIETARY tenant-scoped, IA TRUE
append-only, run-bound + snapshot-gated + model-bound (AD-014).

**The permission split is by WHAT THE READ EXPOSES (ratified OQ-LQ-1-13):** ``liquidity.view``
gates the governed OUTPUT and INCLUDES auditor_3l (3L oversight reads governed numbers); the
CAPTURED tier assignments are read through ``reference.classification_assignment.view``, which
EXCLUDES auditor_3l. The two sit on opposite sides of the auditor line, so no single code spans
both — that was REF-1's BLOCKING defect, and SoD pins are per-code, so no shipped test would have
caught a route on the wrong guard.

**The limitations ride the run-detail payload** (ratified OQ-LQ-1-8). A registered limitation that
no screen renders beside the number is not a control, and the first limitation here is the one that
matters most: this is NOT the Rule 22e-4 15% test, and the direction of its error is indeterminate.

Failure model: a pre-create refusal (wrong-purpose snapshot, unregistered/edited model version, a
snapshot pre-build refusal — mixed live scheme versions, mixed basis, empty atoms) raises and rolls
the whole unit back. A post-build gap (no invested-long book, sub-floor coverage, tier heads past
the declared max age, corrupt pinned content) is a COMMITTED FAILED run with zero rows. There is no
PUT/PATCH/DELETE (append-only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.liquidity.bootstrap import LIQUIDITY_LIMITATIONS
from irp_shared.liquidity.models import LiquidityResult
from irp_shared.liquidity.service import (
    latest_liquidity,
    liquidity_rows_for_run,
    liquidity_run_head,
    list_liquidity_results,
    list_liquidity_runs,
)

router = APIRouter(prefix="/liquidity", tags=["liquidity"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_run = require_permission("liquidity.run")
_require_view = require_permission("liquidity.view")


class LiquidityRowOut(BaseModel):
    run_id: str
    portfolio_id: str
    row_kind: str
    bucket_code: str
    metric_type: str
    denominator_basis: str
    long_amount: Decimal
    tier_share: Decimal | None
    metric_value: Decimal | None
    coverage_ratio: Decimal | None
    coverage_classifiable: Decimal | None
    untiered_instrument_count: int | None
    input_snapshot_id: str
    model_version_id: str


class LiquidityListOut(BaseModel):
    rows: list[LiquidityRowOut]


class LiquidityRunSummaryOut(BaseModel):
    run_id: str
    run_type: str
    status: str
    created_at: datetime | None
    completed_at: datetime | None
    initiated_by: str | None
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    failure_reason: str | None


class LiquidityRunListOut(BaseModel):
    items: list[LiquidityRunSummaryOut]


class LiquidityRunOut(BaseModel):
    run_id: str
    status: str
    failure_reason: str | None
    rows: list[LiquidityRowOut]
    #: The registered limitations, carried WITH the number rather than left in a registration
    #: table nobody opens (OQ-LQ-1-8). These are the model's own rows, not prose duplicated here.
    limitations: list[str]


def _row_out(row: LiquidityResult) -> LiquidityRowOut:
    return LiquidityRowOut(
        run_id=str(row.calculation_run_id),
        portfolio_id=str(row.portfolio_id),
        row_kind=row.row_kind,
        bucket_code=row.bucket_code,
        metric_type=row.metric_type,
        denominator_basis=row.denominator_basis,
        long_amount=row.long_amount,
        tier_share=row.tier_share,
        metric_value=row.metric_value,
        coverage_ratio=row.coverage_ratio,
        coverage_classifiable=row.coverage_classifiable,
        untiered_instrument_count=row.untiered_instrument_count,
        input_snapshot_id=str(row.input_snapshot_id),
        model_version_id=str(row.model_version_id),
    )


# --- rule-7 reads (liquidity.view) ---


@router.get("/results", response_model=LiquidityListOut)
def list_results(
    portfolio_id: uuid.UUID | None = Query(default=None),
    row_kind: str | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    bucket_code: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> LiquidityListOut:
    """Entity/time-centric list across COMPLETED runs (silent-empty on a foreign id)."""
    rows = list_liquidity_results(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id) if portfolio_id else None,
        row_kind=row_kind,
        metric_type=metric_type,
        bucket_code=bucket_code,
        as_of=as_of,
    )
    return LiquidityListOut(rows=[_row_out(r) for r in rows])


@router.get("/results/latest", response_model=LiquidityListOut)
def latest_results(
    portfolio_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> LiquidityListOut:
    """The latest COMPLETED run's rows (404 when none)."""
    rows = latest_liquidity(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id) if portfolio_id else None,
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no completed liquidity run"
        )
    return LiquidityListOut(rows=[_row_out(r) for r in rows])


@router.get("/runs", response_model=LiquidityRunListOut)
def get_liquidity_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> LiquidityRunListOut:
    """List the tenant's liquidity runs, newest first (the runs-surface source for the FE)."""
    runs = list_liquidity_runs(
        db,
        acting_tenant=principal.tenant_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return LiquidityRunListOut(
        items=[
            LiquidityRunSummaryOut(
                run_id=str(r.run_id),
                run_type=r.run_type,
                status=r.status,
                created_at=r.created_at,
                completed_at=r.completed_at,
                initiated_by=r.initiated_by,
                input_snapshot_id=str(r.input_snapshot_id) if r.input_snapshot_id else None,
                model_version_id=str(r.model_version_id) if r.model_version_id else None,
                code_version=r.code_version,
                environment_id=r.environment_id,
                failure_reason=r.failure_reason,
            )
            for r in runs
        ]
    )


@router.get("/runs/{run_id}", response_model=LiquidityRunOut)
def get_liquidity_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> LiquidityRunOut:
    """One run's rows plus the registered limitations (a FAILED run legitimately has no rows;
    404 on an unknown/foreign run id).

    The limitations are returned even on a FAILED run: a reader looking at a refusal needs the
    same context as a reader looking at a number.
    """
    run = liquidity_run_head(db, acting_tenant=principal.tenant_id, run_id=str(run_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    rows = liquidity_rows_for_run(db, acting_tenant=principal.tenant_id, run_id=str(run_id))
    return LiquidityRunOut(
        run_id=str(run.run_id),
        status=run.status,
        failure_reason=run.failure_reason,
        rows=[_row_out(r) for r in rows],
        limitations=list(LIQUIDITY_LIMITATIONS),
    )
