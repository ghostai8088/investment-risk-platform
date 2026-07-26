"""Limit endpoints (API-2, Wave-12 slice 1 — "Operations, Reachable").

The first HTTP surface over the LIM-1/MG-3 governed limit control: define a limit (born DRAFT),
edit it (a material change auto-demotes to DRAFT), APPROVE it DRAFT->ACTIVE (the person-level
maker-checker gate), suspend/resume, and read (list by status, one, health). Thin layer over
``irp_shared.limit.service`` — the router NEVER writes the ORM directly and mints no second write
path (``status`` is not a create/update field; approve/suspend/resume are dedicated verbs).

THE AUTH-BOUNDARY INVARIANT (API-2 D1): the actor id feeding the person-level SoD is canonicalized
at construction (``LimitActor.__post_init__``, the shared package) so a maker cannot self-approve
by presenting a different string-form of their own ``app_user.id``; this router additionally
fail-closes a non-UUID ``principal.user_id`` to 401. A person-level SoD refusal is **409** (the
caller HOLDS the permission; the record is off-limits — OQ-API-2-3=A). No PUT/DELETE. The breach
surface is API-2b. ``evaluate_limit``/``escalate`` are tick-only and never exposed.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_backend.deps import (
    get_tenant_session,
    map_refusal,
    require_permission,
    require_uuid_principal_id,
)
from irp_shared.db.integrity import is_unique_violation
from irp_shared.entitlement.service import Principal
from irp_shared.limit.events import LimitActor
from irp_shared.limit.models import LimitDefinition
from irp_shared.limit.service import (
    DuplicateLimitError,
    LimitError,
    LimitHealth,
    LimitSodError,
    LimitStateError,
    approve_limit,
    create_limit,
    get_limit,
    limit_health,
    list_limits,
    resume_limit,
    suspend_limit,
    update_limit,
)

router = APIRouter(prefix="/limits", tags=["limits"])

#: The REFUSAL surface, declared so it reaches the OpenAPI document and therefore the generated FE
#: types (OPS-1 medium fold — the operations UI otherwise hand-models these with no drift gate).
_WRITE_REFUSALS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"description": "The caller does not hold the required permission."},
    status.HTTP_404_NOT_FOUND: {"description": "No such limit in the acting tenant."},
    status.HTTP_409_CONFLICT: {
        "description": (
            "A state conflict, distinguished by `detail`: the maker-checker separation-of-duties "
            "refusal (the approver may not be a maker), a duplicate logical identity, or a limit "
            "not in the state the verb requires."
        )
    },
}

#: The read surface's refusals.
_READ_REFUSALS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"description": "The caller does not hold `limit.view`."},
    status.HTTP_404_NOT_FOUND: {"description": "No such limit in the acting tenant."},
}

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_manage = require_permission("limit.manage")
_require_approve = require_permission("limit.approve")
_require_view = require_permission("limit.view")

_LimitStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED"]
_HealthState = Literal["IN_APPETITE", "NEVER_EVALUABLE", "BREACHED"]

#: Fail-closed refusal -> (HTTP status, opaque detail), dispatched via ``map_refusal`` (MRO walk).
#: ``LimitSodError`` gets its OWN key (more-derived than ``LimitError``) so the person-level SoD
#: refusal is a 409, not collapsed to the 422 base (verifier B1 / OQ-API-2-3=A).
#: ``DuplicateLimitError`` is a uniform 409 with the ``IntegrityError`` race (verifier N4).
_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    LimitSodError: (status.HTTP_409_CONFLICT, "separation of duties: the actor shaped this limit"),
    DuplicateLimitError: (status.HTTP_409_CONFLICT, "a limit with that code already exists"),
    LimitStateError: (status.HTTP_409_CONFLICT, "illegal transition from the current limit state"),
    LimitError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid limit request"),
}


def _limit_actor(principal: Principal) -> LimitActor:
    """Construct the domain actor via the SHARED fail-closed step (hoisted to ``deps`` at API-2b —
    audit C-F11); the dataclass canonicalizes the id so stamp == compare for the SoD."""
    return LimitActor(actor_id=require_uuid_principal_id(principal))


# --- DTOs ---------------------------------------------------------------------------------
class LimitCreateIn(BaseModel):
    # `extra="forbid"`: an unknown field (a smuggled `status`, a typo) is a loud 422, not a silent
    # drop (verifier MED-2). `threshold_value` is a STRING in/out (precision-safe; a JS number would
    # lose precision on a large/precise threshold — verifier finder-3).
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    target_run_type: str
    metric_type: str
    scope_portfolio_id: uuid.UUID
    threshold_value: str
    threshold_unit: str
    breach_direction: str
    limit_kind: str
    benchmark_id: uuid.UUID | None = None
    # NOTE: no `status` field — a limit is born DRAFT; ACTIVE happens only via approve (D3).


class LimitUpdateIn(BaseModel):
    # The `_UPDATABLE` config knobs MINUS `status` (never edited via the API — D3). All optional;
    # `extra="forbid"` so a smuggled `status` or a frozen-field typo is a 422, not a silent no-op.
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    threshold_value: str | None = None
    limit_kind: str | None = None
    breach_direction: str | None = None


class LimitApproveIn(BaseModel):
    approval_ref: str


class LimitOut(BaseModel):
    id: str  # ORM-native id strings (path params are typed uuid.UUID for input validation)
    code: str
    name: str
    target_run_type: str
    metric_type: str
    benchmark_id: str | None
    scope_portfolio_id: str
    threshold_value: str  # fixed-point string (never a float / scientific — FE-2 decimal contract)
    threshold_unit: str
    breach_direction: str
    limit_kind: str
    status: _LimitStatus
    record_version: int
    created_by: str | None
    updated_by: str | None


class LimitHealthOut(BaseModel):
    limit_id: str
    code: str
    state: _HealthState
    latest_run_id: str | None
    latest_breach_id: str | None


def _limit_out(limit: LimitDefinition) -> LimitOut:
    return LimitOut(
        id=limit.id,
        code=limit.code,
        name=limit.name,
        target_run_type=limit.target_run_type,
        metric_type=limit.metric_type,
        benchmark_id=limit.benchmark_id,
        scope_portfolio_id=limit.scope_portfolio_id,
        threshold_value=f"{limit.threshold_value:f}",
        threshold_unit=limit.threshold_unit,
        breach_direction=limit.breach_direction,
        limit_kind=limit.limit_kind,
        status=cast(_LimitStatus, limit.status),
        record_version=limit.record_version,
        created_by=limit.created_by,
        updated_by=limit.updated_by,
    )


def _health_out(h: LimitHealth) -> LimitHealthOut:
    return LimitHealthOut(
        limit_id=h.limit_id,
        code=h.code,
        state=cast(_HealthState, h.state),
        latest_run_id=h.latest_run_id,
        latest_breach_id=h.latest_breach_id,
    )


def _refuse(db: Session, exc: LimitError) -> HTTPException:
    db.rollback()  # whole-unit rollback (CTRL-032)
    code, detail = map_refusal(exc, _ERROR_MAP)
    return HTTPException(status_code=code, detail=detail)


def _load_or_404(db: Session, principal: Principal, limit_id: uuid.UUID) -> LimitDefinition:
    limit = get_limit(db, acting_tenant=principal.tenant_id, limit_id=str(limit_id))
    if limit is None:  # missing or cross-tenant — indistinguishable 404 (no existence oracle)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="limit not found")
    return limit


# --- write endpoints ----------------------------------------------------------------------
@router.post(
    "", response_model=LimitOut, status_code=status.HTTP_201_CREATED, responses=_WRITE_REFUSALS
)
def create(
    body: LimitCreateIn,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> LimitOut:
    try:
        limit = create_limit(
            db,
            tenant_id=principal.tenant_id,
            code=body.code,
            name=body.name,
            target_run_type=body.target_run_type,
            metric_type=body.metric_type,
            scope_portfolio_id=str(body.scope_portfolio_id),
            threshold_value=body.threshold_value,
            threshold_unit=body.threshold_unit,
            breach_direction=body.breach_direction,
            limit_kind=body.limit_kind,
            benchmark_id=str(body.benchmark_id) if body.benchmark_id else None,
            actor=_limit_actor(principal),
        )
    except LimitError as exc:
        raise _refuse(db, exc) from None
    except IntegrityError as exc:  # concurrent duplicate -> the same uniform 409
        db.rollback()
        if not is_unique_violation(exc):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="a limit with that code already exists"
        ) from None
    out = _limit_out(limit)  # in-memory read; build before the single end-of-request commit
    db.commit()
    return out


@router.patch("/{limit_id}", response_model=LimitOut)
def update(
    limit_id: uuid.UUID,
    body: LimitUpdateIn,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> LimitOut:
    limit = _load_or_404(db, principal, limit_id)
    changes = body.model_dump(exclude_unset=True)
    changes.pop("status", None)  # belt-and-suspenders: `status` never rides the edit path (D3)
    if not changes:
        return _limit_out(limit)
    try:
        updated = update_limit(db, limit, actor=_limit_actor(principal), **changes)
    except LimitError as exc:
        raise _refuse(db, exc) from None
    out = _limit_out(updated)
    db.commit()
    return out


@router.post("/{limit_id}/approve", response_model=LimitOut, responses=_WRITE_REFUSALS)
def approve(
    limit_id: uuid.UUID,
    body: LimitApproveIn,
    principal: Principal = Depends(_require_approve),
    db: Session = Depends(get_tenant_session),
) -> LimitOut:
    limit = _load_or_404(db, principal, limit_id)
    try:
        approved = approve_limit(
            db, limit, actor=_limit_actor(principal), approval_ref=body.approval_ref
        )
    except LimitError as exc:
        raise _refuse(db, exc) from None
    out = _limit_out(approved)
    db.commit()
    return out


@router.post("/{limit_id}/suspend", response_model=LimitOut, responses=_WRITE_REFUSALS)
def suspend(
    limit_id: uuid.UUID,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> LimitOut:
    limit = _load_or_404(db, principal, limit_id)
    try:
        out = _limit_out(suspend_limit(db, limit, actor=_limit_actor(principal)))
    except LimitError as exc:
        raise _refuse(db, exc) from None
    db.commit()
    return out


@router.post("/{limit_id}/resume", response_model=LimitOut, responses=_WRITE_REFUSALS)
def resume(
    limit_id: uuid.UUID,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> LimitOut:
    limit = _load_or_404(db, principal, limit_id)
    try:
        out = _limit_out(resume_limit(db, limit, actor=_limit_actor(principal)))
    except LimitError as exc:
        raise _refuse(db, exc) from None
    db.commit()
    return out


# --- read endpoints (literal /health BEFORE the /{limit_id} param route) -------------------
@router.get("/health", response_model=list[LimitHealthOut], responses=_READ_REFUSALS)
def health(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[LimitHealthOut]:
    return [_health_out(h) for h in limit_health(db, acting_tenant=principal.tenant_id)]


@router.get("", response_model=list[LimitOut], responses=_READ_REFUSALS)
def index(
    status_filter: _LimitStatus | None = Query(default=None, alias="status"),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[LimitOut]:
    # `status=DRAFT` is the approval queue.
    return [
        _limit_out(x)
        for x in list_limits(db, acting_tenant=principal.tenant_id, status=status_filter)
    ]


@router.get("/{limit_id}", response_model=LimitOut, responses=_READ_REFUSALS)
def show(
    limit_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> LimitOut:
    return _limit_out(_load_or_404(db, principal, limit_id))
