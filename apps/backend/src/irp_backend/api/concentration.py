"""Concentration endpoints (CON-1, ENT-069 — the 23rd governed number family).

Thin layer over the ``irp_shared.concentration`` binder. PROPRIETARY tenant-scoped, IA TRUE
append-only, run-bound + snapshot-gated + model-bound (AD-014). **The three-code split is by WHAT
THE READ EXPOSES (OQ-CON-1-25):** ``concentration.run`` gates the maker verb; ``concentration.view``
gates the summary metrics + classification-dimension buckets — NO issuer identity anywhere in the
payload, excluded STRUCTURALLY at the service query, and 3L-oversight scope (auditor included);
``concentration.issuer.view`` gates the ISSUER-dimension detail rows (issuer identity — auditor
EXCLUDED, the reference.issuer.view precedent). ``_METRIC_MAP`` registration is DEFERRED to LIM-2
(the OQ-CON-1-15 reversal): no limit can bind these metrics yet, by existing fail-closed code.

Failure model (the governed-run precedent): a pre-create refusal (missing prerequisite /
wrong-or-unregistered model / non-COMPLETED / wrong-type / NULL-scope upstream run / a snapshot
pre-build refusal — mixed basis, mixed same-family versions, empty atoms) raises and rolls the
whole unit back — ZERO run, ZERO snapshot. A post-build gap (zero invested-long / the
all-UNCLASSIFIABLE 0/0 book / sub-floor classifiable coverage) is a COMMITTED FAILED run with zero
rows, returned with ``status='FAILED'``. There is no PUT/PATCH/DELETE (append-only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.api.write_errors import raise_mapped_write
from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.classification.service import ClassificationNotVisible
from irp_shared.concentration.bootstrap import (
    ConcentrationModelParameterError,
    register_concentration_model,
)
from irp_shared.concentration.events import ConcentrationActor
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.concentration.service import (
    ConcentrationInputError,
    concentration_rows_for_run,
    concentration_run_head,
    latest_concentration,
    list_concentration_issuer_detail,
    list_concentration_results,
    list_concentration_runs,
    run_concentration,
)
from irp_shared.entitlement.service import Principal
from irp_shared.model.service import (
    ExpiredModelExceptionError,
    ModelVersionConflictError,
    RejectedModelVersionError,
    UnregisteredModelError,
    WrongModelVersionError,
)
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.snapshot.service import ConcentrationSnapshotError

router = APIRouter(prefix="/concentration", tags=["concentration"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_register = require_permission("model.inventory.register")
_require_run = require_permission("concentration.run")
_require_view = require_permission("concentration.view")
#: THE ISSUER-IDENTITY GATE — a distinct code so the auditor_3l exclusion is per-code enforceable
#: (the REF-1 lesson: SoD pins are per code; a route on the wrong guard is the residual risk the
#: route-level test pins).
_require_issuer_view = require_permission("concentration.issuer.view")


def _actor(principal: Principal) -> ConcentrationActor:
    return ConcentrationActor(actor_id=principal.user_id)


# --- exact-type pre-create refusal map (fail-closed; whole-unit rollback) ---

_RUN_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    ConcentrationInputError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid concentration run input",
    ),
    UnregisteredModelError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version is not registered (CTRL-003)",
    ),
    WrongModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version does not match the concentration model's registered identity (CTRL-003)",
    ),
    RejectedModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version latest validation outcome is REJECTED — new runs refused (VW-1 / CTRL-022)",
    ),
    ExpiredModelExceptionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version use-before-validation EXCEPTION has expired — new runs refused (MG-1)",
    ),
    ConcentrationSnapshotError: (
        status.HTTP_409_CONFLICT,
        "concentration snapshot input failed closed (mixed basis / mixed same-family scheme "
        "versions / scheme-dimension mismatch / empty atoms)",
    ),
    ClassificationNotVisible: (
        status.HTTP_409_CONFLICT,
        "a pinned classification input is not visible (truncated ancestor walk refused)",
    ),
    InstrumentNotVisible: (
        status.HTTP_409_CONFLICT,
        "a pinned instrument is not visible to this tenant",
    ),
}

_RUN_EXCS = tuple(_RUN_WRITE_ERRORS)

_MODEL_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    ModelVersionConflictError: (
        status.HTTP_409_CONFLICT,
        "a same-label concentration model version exists with a DIFFERENT declaration",
    ),
    WrongModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "the resolved concentration model version is not usable (CTRL-003)",
    ),
    # NOT bare ValueError: that would relabel any server-side bug inside registration as a client
    # 422, and would re-arm the API-2 MRO trap (isinstance-caught, exact-type-mapped → KeyError).
    ConcentrationModelParameterError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid concentration model parameters",
    ),
}


# --- DTOs ---


class ConcentrationModelIn(BaseModel):
    code_version: str
    coverage_floor: Decimal
    version_label: str = "v1"


class ConcentrationModelOut(BaseModel):
    model_version_id: str
    model_code: str
    version_label: str
    status: str


class ConcentrationRunIn(BaseModel):
    exposure_run_id: uuid.UUID
    #: dimension_kind -> scheme_id for the classification dimensions (ISSUER is always computed
    #: and carries no scheme — sending it is a 422 from the binder).
    scheme_by_dimension: dict[str, uuid.UUID]
    model_version_id: uuid.UUID
    code_version: str
    environment_id: str


class ConcentrationRowOut(BaseModel):
    id: str
    calculation_run_id: str
    input_snapshot_id: str
    model_version_id: str
    portfolio_id: str
    row_kind: str
    dimension_kind: str
    metric_type: str
    bucket_code: str
    issuer_id: str | None
    scheme_id: str | None
    basis: str
    denominator_basis: str
    gross_amount: Decimal
    long_amount: Decimal
    short_amount: Decimal
    net_amount: Decimal
    share_invested_long: Decimal | None
    metric_value: Decimal | None
    coverage_ratio: Decimal | None
    coverage_classifiable: Decimal | None


class ConcentrationRunOut(BaseModel):
    run_id: str
    status: str
    failure_reason: str | None
    rows: list[ConcentrationRowOut]


class ConcentrationListOut(BaseModel):
    rows: list[ConcentrationRowOut]


def _row_out(row: ConcentrationResult) -> ConcentrationRowOut:
    return ConcentrationRowOut(
        id=str(row.id),
        calculation_run_id=str(row.calculation_run_id),
        input_snapshot_id=str(row.input_snapshot_id),
        model_version_id=str(row.model_version_id),
        portfolio_id=str(row.portfolio_id),
        row_kind=row.row_kind,
        dimension_kind=row.dimension_kind,
        metric_type=row.metric_type,
        bucket_code=row.bucket_code,
        issuer_id=str(row.issuer_id) if row.issuer_id is not None else None,
        scheme_id=str(row.scheme_id) if row.scheme_id is not None else None,
        basis=row.basis,
        denominator_basis=row.denominator_basis,
        gross_amount=row.gross_amount,
        long_amount=row.long_amount,
        short_amount=row.short_amount,
        net_amount=row.net_amount,
        share_invested_long=row.share_invested_long,
        metric_value=row.metric_value,
        coverage_ratio=row.coverage_ratio,
        coverage_classifiable=row.coverage_classifiable,
    )


# --- model registration (model.inventory.register) ---


@router.post(
    "/models/dimensional",
    response_model=ConcentrationModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_model(
    body: ConcentrationModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationModelOut:
    """Register the governed concentration model with its declared parameters (idempotent; a
    same-label different-declaration is a 409)."""
    try:
        version = register_concentration_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            coverage_floor=body.coverage_floor,
            version_label=body.version_label,
        )
    except tuple(_MODEL_WRITE_ERRORS) as exc:
        raise_mapped_write(db, exc, _MODEL_WRITE_ERRORS)
    response = ConcentrationModelOut(
        model_version_id=str(version.id),
        model_code="concentration.dimensional",
        version_label=version.version_label,
        status=version.status or "REGISTERED",
    )
    db.commit()
    return response


# --- the maker verb (concentration.run) ---


@router.post("/runs", response_model=ConcentrationRunOut, status_code=status.HTTP_201_CREATED)
def create_concentration_run(
    body: ConcentrationRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationRunOut:
    """Run a governed concentration calculation over an EXPLICITLY SELECTED exposure run (never
    'latest' — Part 6b item 5). The response carries only NON-issuer rows; the issuer detail rides
    ``GET /concentration/results/issuers`` behind its own code."""
    try:
        outcome = run_concentration(
            db,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            exposure_run_id=str(body.exposure_run_id),
            scheme_by_dimension={k: str(v) for k, v in body.scheme_by_dimension.items()},
        )
    except _RUN_EXCS as exc:
        raise_mapped_write(db, exc, _RUN_WRITE_ERRORS)

    response = ConcentrationRunOut(
        run_id=str(outcome.run.run_id),
        status=outcome.status,
        failure_reason=outcome.failure_reason,
        rows=[
            _row_out(r)
            for r in outcome.rows
            if not (r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL")
        ],
    )
    db.commit()
    return response


# --- rule-7 reads (concentration.view — NO issuer identity in any payload) ---


@router.get("/results", response_model=ConcentrationListOut)
def list_results(
    portfolio_id: uuid.UUID | None = Query(default=None),
    dimension_kind: str | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationListOut:
    """Entity/time-centric list across COMPLETED runs (silent-empty on a foreign id). ISSUER
    detail rows are excluded STRUCTURALLY at the service query — not filtered here."""
    rows = list_concentration_results(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id) if portfolio_id else None,
        dimension_kind=dimension_kind,
        metric_type=metric_type,
        as_of=as_of,
    )
    return ConcentrationListOut(rows=[_row_out(r) for r in rows])


@router.get("/results/latest", response_model=ConcentrationListOut)
def latest_results(
    portfolio_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationListOut:
    """The latest COMPLETED run's rows (404 when none)."""
    rows = latest_concentration(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id) if portfolio_id else None,
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no completed concentration run"
        )
    return ConcentrationListOut(rows=[_row_out(r) for r in rows])


# --- the issuer-identity read (concentration.issuer.view — auditor_3l EXCLUDED) ---


@router.get("/results/issuers", response_model=ConcentrationListOut)
def list_issuer_detail(
    portfolio_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_issuer_view),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationListOut:
    """The ISSUER-dimension detail rows — the ONLY read that returns ``issuer_id``."""
    rows = list_concentration_issuer_detail(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id) if portfolio_id else None,
        as_of=as_of,
    )
    return ConcentrationListOut(rows=[_row_out(r) for r in rows])


# --- the FE runs surface (concentration.view; the FE-1 runs-listing shape) ---


class ConcentrationRunSummaryOut(BaseModel):
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


class ConcentrationRunListOut(BaseModel):
    items: list[ConcentrationRunSummaryOut]


@router.get("/runs", response_model=ConcentrationRunListOut)
def get_concentration_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationRunListOut:
    """List the tenant's concentration runs, newest first (the runs-surface source for the FE)."""
    runs = list_concentration_runs(
        db,
        acting_tenant=principal.tenant_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return ConcentrationRunListOut(
        items=[
            ConcentrationRunSummaryOut(
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


@router.get("/runs/{run_id}", response_model=ConcentrationRunOut)
def get_concentration_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ConcentrationRunOut:
    """One run's rows (non-issuer — the ``.view`` payload; a FAILED run legitimately has none;
    404 on an unknown/foreign run id)."""
    run = concentration_run_head(db, acting_tenant=principal.tenant_id, run_id=str(run_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    rows = concentration_rows_for_run(db, acting_tenant=principal.tenant_id, run_id=str(run_id))
    return ConcentrationRunOut(
        run_id=str(run.run_id),
        status=run.status,
        failure_reason=run.failure_reason,
        rows=[_row_out(r) for r in rows],
    )
