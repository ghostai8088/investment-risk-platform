"""Pacing endpoints (CC-2, ENT-059 — the commitment-pacing projection; the SEVENTEENTH governed
number): the deterministic Takahashi-Alexander future-only projection of a private-fund commitment's
capital calls, distributions, and NAV over the CC-1 captured substrate.

Thin layer over the ``irp_shared.pacing`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), IA TRUE
append-only, run-bound + snapshot-gated + **model_version-bound** (AD-014 / FW-RUN / TR-15 /
CTRL-003). ``POST /pacing/models/commitment-projection`` registers the governed pacing model with
its FIVE declared parameters (gated ``model.inventory.register``); ``POST /pacing/projections/runs``
is gated ``pacing.run`` (maker); the reads gated ``pacing.view`` (a governed-output ``.view``, so it
INCLUDES ``auditor_3l`` — the exposure/risk/perf precedent). ``tenant_id`` server-stamped; a single
end-of-request ``db.commit()``. There is **no PUT/PATCH/DELETE** (append-only).

The run body is EITHER consume-existing (``snapshot_id``) OR build-in-request (``portfolio_id`` +
``instrument_id`` — the binder is consume-only, so the endpoint builds the ``PACING_INPUT`` snapshot
first); exactly one of the two forms (both/neither is a 422).

Failure model (the governed-run precedent): a **pre-create refusal** (missing/invalid prerequisite /
unregistered-or-wrong model_version / incoherent anchor / past fund life / snapshot-build-failed)
raises (422/404/409) and rolls the WHOLE unit back — ZERO run. A **post-create FAILED** run (the
magnitude envelope) is COMMITTED (a real resource in FAILED state, ZERO rows) and returned with
``status='FAILED'``.

RULE 7 in-slice (OD-CC-2-F): ``GET /pacing/projections`` (entity filters + ``as_of``; silent-empty)
and ``GET /pacing/projections/latest`` (the platform's FIRST latest-resolver; ``as_of``-aware; 404
when none). The list is FLAT rows each carrying ``calculation_run_id`` + ``model_version_id``;
**cross-run aggregation is a CONSUMER ERROR** (a pair may hold several runs — e.g. successive
versions).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.api.write_errors import raise_mapped_write
from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.model.service import (
    ExpiredModelExceptionError,
    ModelVersionConflictError,
    RejectedModelVersionError,
    UnregisteredModelError,
    WrongModelVersionError,
)
from irp_shared.pacing import (
    PacingActor,
    PacingInputError,
    PacingNotVisible,
    PacingRunNotVisible,
    PacingRunResult,
    latest_pacing_projection,
    list_pacing_projections,
    list_pacing_rows,
    register_pacing_projection_model,
    resolve_pacing_row,
    resolve_pacing_run,
    run_pacing_projection,
)
from irp_shared.pacing.models import PacingProjectionResult
from irp_shared.snapshot import (
    PacingSnapshotError,
    SnapshotNotFound,
    SnapshotPurposeError,
    build_pacing_snapshot,
)
from irp_shared.snapshot.events import SnapshotActor

router = APIRouter(prefix="/pacing", tags=["pacing"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_register = require_permission("model.inventory.register")
_require_run = require_permission("pacing.run")
_require_view = require_permission("pacing.view")


def _actor(principal: Principal) -> PacingActor:
    return PacingActor(actor_id=principal.user_id)


def _snapshot_actor(principal: Principal) -> SnapshotActor:
    return SnapshotActor(actor_id=principal.user_id)


# --- exact-type pre-create refusal map (fail-closed; whole-unit rollback via raise_mapped_write) --

_RUN_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    PacingInputError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid pacing run input"),
    UnregisteredModelError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version is not registered (CTRL-003)",
    ),
    WrongModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version does not match the pacing model's registered identity (CTRL-003)",
    ),
    RejectedModelVersionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version latest validation outcome is REJECTED — new runs refused (VW-1 / CTRL-022)",
    ),
    ExpiredModelExceptionError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "model_version use-before-validation EXCEPTION has expired — new runs refused (MG-1 / "
        "CTRL-022)",
    ),
    SnapshotPurposeError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid snapshot purpose"),
    SnapshotNotFound: (status.HTTP_404_NOT_FOUND, "snapshot not found"),
    PacingSnapshotError: (
        status.HTTP_409_CONFLICT,
        "pacing snapshot input failed closed (no current commitment / hidden pair)",
    ),
}

_RUN_EXCS = (
    PacingInputError,
    UnregisteredModelError,
    WrongModelVersionError,
    RejectedModelVersionError,
    ExpiredModelExceptionError,
    SnapshotPurposeError,
    SnapshotNotFound,
    PacingSnapshotError,
)


# --- DTOs ---


class PacingModelIn(BaseModel):
    code_version: str
    # The FIVE declared parameters ARE the version identity (OD-CC-2-B). Sent as strings/decimals;
    # canonicalized at registration so 0.25 and 0.250 cannot mint distinct identities.
    rc_schedule: list[Decimal]  # rate-of-contribution per age (each in [0,1]; len <= fund_life)
    fund_life: int  # L, positive integer
    bow: Decimal  # B, the distribution-curve bow (signed)
    growth: Decimal  # G, the per-period NAV growth (signed)
    yield_floor: Decimal  # Y, the distribution-rate floor (in [0,1])
    version_label: str = "v1"


class PacingModelOut(BaseModel):
    model_version_id: str
    model_id: str
    version_label: str
    methodology_ref: str | None
    code_version: str | None
    status: str | None


class PacingRunIn(BaseModel):
    code_version: str  # the deterministic anchor (FW-RUN/TR-15; required)
    environment_id: str  # the run environment (FW-RUN §5 item 7; required)
    model_version_id: uuid.UUID  # a REGISTERED pacing model_version (CTRL-003; required)
    snapshot_id: uuid.UUID | None = None  # consume-existing PACING_INPUT snapshot
    portfolio_id: uuid.UUID | None = None  # build-in-request (with instrument_id)
    instrument_id: uuid.UUID | None = None


class PacingRowOut(BaseModel):
    id: str
    calculation_run_id: str
    input_snapshot_id: str
    model_version_id: str
    portfolio_id: str
    instrument_id: str
    period_index: int  # the fund age in periods (1..L)
    period_start: date
    period_end: date
    projected_call: str
    projected_distribution: str
    projected_nav: str
    unfunded_end: str
    currency_code: str


class PacingRunOut(BaseModel):
    run_id: str
    status: str
    run_type: str
    input_snapshot_id: str | None
    model_version_id: str | None
    code_version: str | None
    environment_id: str | None
    initiated_by: str
    failure_reason: str | None
    rows: list[PacingRowOut]


class PacingProjectionListOut(BaseModel):
    items: list[PacingRowOut]


def _row_out(row: PacingProjectionResult) -> PacingRowOut:
    return PacingRowOut(
        id=row.id,
        calculation_run_id=row.calculation_run_id,
        input_snapshot_id=row.input_snapshot_id,
        model_version_id=row.model_version_id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        period_index=row.period_index,
        period_start=row.period_start,
        period_end=row.period_end,
        # Fixed-point, never scientific (the P3-4 serialization lesson).
        projected_call=f"{row.projected_call:f}",
        projected_distribution=f"{row.projected_distribution:f}",
        projected_nav=f"{row.projected_nav:f}",
        unfunded_end=f"{row.unfunded_end:f}",
        currency_code=row.currency_code,
    )


def _run_out(result: PacingRunResult) -> PacingRunOut:
    run = result.run
    return PacingRunOut(
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


# --- registrar (model.inventory.register) ---


@router.post(
    "/models/commitment-projection",
    response_model=PacingModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_pacing_model(
    body: PacingModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> PacingModelOut:
    """Register (idempotently) the governed pacing model + a model_version for this
    ``(code_version, rc_schedule, fund_life, bow, growth, yield_floor, functional_form=TA)``
    identity and return its id (OD-CC-2-B — the FIVE declared parameters are version identity;
    a same-label re-register with a different declaration is a 409; invalid parameters are a 422).
    NO numeric constant is minted from Takahashi-Alexander — only the FUNCTIONAL FORM is TA's."""
    try:
        version = register_pacing_projection_model(
            db,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            code_version=body.code_version,
            rc_schedule=list(body.rc_schedule),
            fund_life=body.fund_life,
            bow=body.bow,
            growth=body.growth,
            yield_floor=body.yield_floor,
            version_label=body.version_label,
        )
    except ValueError:  # invalid declared parameters (domain breach) / empty label
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid pacing model parameters",
        ) from None
    except (ModelVersionConflictError, WrongModelVersionError):
        # WrongModelVersionError: a same-label twin exists that is NOT a REGISTERED version of this
        # family (generically minted) — a governed 409 refusal, not a 500 (the P3-C1 contract).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="version_label already registered with a different declared identity",
        ) from None
    out = PacingModelOut(
        model_version_id=version.id,
        model_id=version.model_id,
        version_label=version.version_label,
        methodology_ref=version.methodology_ref,
        code_version=version.code_version,
        status=version.status,
    )
    db.commit()
    return out


# --- run (pacing.run) ---


@router.post("/projections/runs", response_model=PacingRunOut, status_code=status.HTTP_201_CREATED)
def create_pacing_run(
    body: PacingRunIn,
    principal: Principal = Depends(_require_run),
    db: Session = Depends(get_tenant_session),
) -> PacingRunOut:
    """Run a governed commitment-pacing projection. Provide EITHER ``snapshot_id`` (consume an
    existing ``PACING_INPUT`` snapshot) OR ``portfolio_id`` + ``instrument_id`` (build one first) —
    exactly one form. A pre-create refusal raises + rolls back (no run); a post-create FAILED run is
    committed (``status='FAILED'``, zero rows — the magnitude envelope)."""
    has_snapshot = body.snapshot_id is not None
    has_pair = body.portfolio_id is not None and body.instrument_id is not None
    if has_snapshot == has_pair:  # both or neither
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provide EITHER snapshot_id OR (portfolio_id, instrument_id), not both/neither",
        )

    try:
        if has_snapshot:
            snapshot_id = str(body.snapshot_id)
        else:
            # Build-in-request: the binder is consume-only, so the endpoint builds the snapshot
            # under the same governed unit (a build failure rolls back with the run refusal).
            snapshot = build_pacing_snapshot(
                db,
                acting_tenant=principal.tenant_id,
                actor=_snapshot_actor(principal),
                portfolio_id=str(body.portfolio_id),
                instrument_id=str(body.instrument_id),
            )
            snapshot_id = snapshot.id
        result = run_pacing_projection(
            db,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            code_version=body.code_version,
            environment_id=body.environment_id,
            model_version_id=str(body.model_version_id),
            snapshot_id=snapshot_id,
        )
    except _RUN_EXCS as exc:
        # Pre-create refusal: whole-unit rollback (no run/result/audit) before the HTTP error.
        raise_mapped_write(db, exc, _RUN_WRITE_ERRORS)

    # Build the response BEFORE commit (the request GUC clears at commit). Both a COMPLETED and a
    # post-create FAILED run are committed (the FAILED run is durable refusal evidence).
    response = _run_out(result)
    db.commit()
    return response


# --- run-centric reads (pacing.view) ---


@router.get("/projections/runs/{run_id}", response_model=PacingRunOut)
def get_pacing_run(
    run_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PacingRunOut:
    """Read a pacing run + its projected period rows (tenant-scoped; read-only). A committed FAILED
    run (zero rows) is surfaced with ``status='FAILED'`` (durable refusal evidence), NOT a 404."""
    try:
        run = resolve_pacing_run(db, str(run_id), acting_tenant=principal.tenant_id)
    except PacingRunNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pacing run not found"
        ) from None
    rows = list_pacing_rows(db, run_id=str(run_id), acting_tenant=principal.tenant_id)
    return PacingRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,  # persisted at the FAILED transition
        rows=[_row_out(r) for r in rows],
    )


@router.get("/projections/results/{result_id}", response_model=PacingRowOut)
def get_pacing_result(
    result_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PacingRowOut:
    """Read a single ``pacing_projection_result`` row (tenant-scoped; read-only)."""
    try:
        row = resolve_pacing_row(db, str(result_id), acting_tenant=principal.tenant_id)
    except PacingNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pacing projection not found"
        ) from None
    return _row_out(row)


# --- rule-7 entity/time-centric reads (pacing.view) ---


@router.get("/projections/latest", response_model=PacingRunOut)
def get_latest_pacing_projection(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID,
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PacingRunOut:
    """The platform's FIRST latest-resolver (OD-CC-2-F): the newest COMPLETED projection run for the
    (portfolio, instrument) pair across ALL model versions ("current" = the latest run), as of an
    optional run cutoff (``as_of=None`` means now — ONE code path), returned as its period rows.
    404 when the pair has no COMPLETED projection. Cross-run aggregation is a CONSUMER ERROR: this
    resolver returns exactly ONE run's rows; use ``GET /pacing/projections`` for the full set."""
    rows = latest_pacing_projection(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        as_of=as_of,
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no completed pacing projection for this portfolio/instrument pair",
        )
    run = resolve_pacing_run(db, rows[0].calculation_run_id, acting_tenant=principal.tenant_id)
    return PacingRunOut(
        run_id=run.run_id,
        status=run.status,
        run_type=run.run_type,
        input_snapshot_id=run.input_snapshot_id,
        model_version_id=run.model_version_id,
        code_version=run.code_version,
        environment_id=run.environment_id,
        initiated_by=run.initiated_by,
        failure_reason=run.failure_reason,
        rows=[_row_out(r) for r in rows],
    )


@router.get("/projections", response_model=PacingProjectionListOut)
def list_pacing_projections_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> PacingProjectionListOut:
    """The rule-7 entity/time-centric read (OD-CC-2-F): projected rows across COMPLETED runs for the
    (portfolio, instrument) pair, optionally as of a run cutoff (``as_of``: resolution scoped to
    runs with ``system_from <= as_of``). FLAT rows each carrying ``calculation_run_id`` +
    ``model_version_id``; total ordering (run ``system_from`` DESC, run_id DESC, ``period_index``
    ASC). **Cross-run aggregation is a CONSUMER ERROR** — a pair may hold several runs (e.g.
    successive versions); discriminate by ``calculation_run_id``. Silent-empty on an unknown/foreign
    id (the positions/valuations entity-filter precedent)."""
    rows = list_pacing_projections(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
        as_of=as_of,
    )
    return PacingProjectionListOut(items=[_row_out(r) for r in rows])
