"""Breach lifecycle endpoints (API-2b, Wave-12 slice 1b — "Operations, Reachable").

The HTTP surface over the MG-2 breach remediation machine: ``assign`` (2L starts the clock),
``respond`` (1L files remediation), ``review`` (2L ACCEPT/REJECT — REJECT re-opens a fresh epoch
and CARRIES the owner, OQ-API-2b-1=A), ``close`` (2L, evidence required), plus the queue reads.
Thin pass-throughs to ``irp_shared.limit.lifecycle`` — the router NEVER writes the ORM directly;
``evaluate_limit``/``escalate_overdue_breach`` are tick-only and never exposed (D10).

Boundary invariants (the API-2b audit): the actor id feeds the person-level SoD via the SHARED
fail-closed constructor (``require_uuid_principal_id`` → ``BreachActor.__post_init__``
canonicalization — D1 inherited); a SoD refusal is **409** (OQ-API-2-3=A, uniform with limits);
every reachable ``BreachTransitionError`` post-DTO-validation is a genuine state conflict → 409;
``IntegrityError`` is NOT mapped on the verbs (a seq collision under the lock = a lock/isolation
regression — fail LOUD, audit B-F7); a deadlock victim (40P01) maps to **503 + Retry-After**
(static body, no post-rollback DB reads — B-F1/B-F8). ``BreachOut`` NEVER serializes the frozen
``Breach.status`` column — ``state`` is recency-derived (D6). Timeline order is ``seq``, never
``occurred_at`` (B-F9).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from irp_backend.deps import (
    deadlock_503,
    get_tenant_session,
    map_refusal,
    require_permission,
    require_uuid_principal_id,
)
from irp_shared.db.mixins import utcnow
from irp_shared.entitlement.service import Principal, has_permission
from irp_shared.limit.events import BreachActor
from irp_shared.limit.lifecycle import (
    BreachAssigneeError,
    BreachLifecycleError,
    BreachQueueItem,
    BreachSodError,
    BreachStaleSeqError,
    BreachTransitionError,
    _as_utc,
    assign_breach,
    breach_action_timeline,
    breach_detail,
    close_breach,
    get_breach,
    list_breaches,
    respond_breach,
    review_breach,
)
from irp_shared.limit.models import Breach, BreachAction
from irp_shared.notification.models import BreachNotification
from irp_shared.notification.service import list_breach_notifications

router = APIRouter(prefix="/breaches", tags=["breaches"])

#: Module-level guard singletons (deny-by-default; the D4 permission table).
_require_respond = require_permission("breach.respond")
_require_review = require_permission("breach.review")
_require_view = require_permission("breach.view")

_BreachState = Literal["DETECTED", "ASSIGNED", "RESPONDED", "REVIEWED", "ESCALATED", "CLOSED"]
_ActionType = Literal["ASSIGN", "1L_RESPONSE", "2L_REVIEW", "ESCALATE", "CLOSE"]
_ReviewOutcome = Literal["ACCEPT", "REJECT"]
_ActorLine = Literal["1L", "2L", "SYS"]
_Kind = Literal["HARD", "SOFT"]
_Direction = Literal["ABOVE", "BELOW"]
_Unit = Literal["CURRENCY", "FRACTION"]
_NotifyOutcome = Literal["SENT", "FAILED", "SUPPRESSED"]
_NotifyChannel = Literal["LOG", "EMAIL", "WEBHOOK"]
_NotifySourceEvent = Literal["BREACH.DETECT", "BREACH.ESCALATE"]

#: Fail-closed refusal map (audit C-F4): the SoD sibling gets its OWN key (409); every reachable
#: post-DTO ``BreachTransitionError`` is a genuine state conflict (409); the BASE stays 422 for
#: future subclasses. NO ``IntegrityError`` key (B-F7 — fail loud) and never ``raise_mapped_write``
#: (exact-type lookup would KeyError on the siblings).
_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    BreachAssigneeError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "assignee must resolve to an active user in the tenant",
    ),
    BreachSodError: (
        status.HTTP_409_CONFLICT,
        "separation of duties: the actor responded to this breach",
    ),
    # OPS-1 fold H2: the stale-seq subclass needs its OWN key (map_refusal walks the MRO, so the
    # nearest ancestor wins — without this it inherited the transition detail and was
    # wire-INDISTINGUISHABLE from an illegal move). The two demand OPPOSITE operator actions:
    # "reload and retry" vs "this move is not legal from here".
    BreachStaleSeqError: (
        status.HTTP_409_CONFLICT,
        "the breach changed while you were reading it; reload and retry",
    ),
    BreachTransitionError: (
        status.HTTP_409_CONFLICT,
        "illegal transition from the current breach state",
    ),
    BreachLifecycleError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid breach request"),
}


#: The REFUSAL surface, declared so it reaches the OpenAPI document and therefore the generated FE
#: types (OPS-1 medium fold). Until now the verbs documented only 200/422, so the operations UI had
#: to hand-model 403/409/503 with ZERO drift protection from `gen-api-check` — precisely the
#: FE-2 lesson (a contract you hand-model is a contract that silently rots). These are documentation
#: only: the runtime statuses are produced by `_refuse` / `deadlock_503` / the permission guard.
_WRITE_REFUSALS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"description": "The caller does not hold the required permission."},
    status.HTTP_404_NOT_FOUND: {"description": "No such breach in the acting tenant."},
    status.HTTP_409_CONFLICT: {
        "description": (
            "A state conflict. Three distinct causes, distinguished by `detail`: a separation-of-"
            "duties refusal, a stale `expected_seq` (reload and retry), or an illegal transition."
        )
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "description": "Transient lock contention (deadlock victim). Retryable; see `Retry-After`."
    },
}

#: The read surface's refusals (no write conflicts).
_READ_REFUSALS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"description": "The caller does not hold `breach.view`."},
    status.HTTP_404_NOT_FOUND: {"description": "No such breach in the acting tenant."},
}

#: Collection reads cannot 404 (an empty list is a valid answer) — 403 only.
_COLLECTION_REFUSALS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"description": "The caller does not hold `breach.view`."},
}


def _breach_actor(principal: Principal) -> BreachActor:
    """The domain actor via the SHARED fail-closed step (C-F11); canonicalized at construction."""
    return BreachActor(actor_id=require_uuid_principal_id(principal))


def _refuse(db: Session, exc: BreachLifecycleError) -> HTTPException:
    db.rollback()  # whole-unit rollback; NO DB reads after this (the GUC is gone — B-F8)
    code, detail = map_refusal(exc, _ERROR_MAP)
    return HTTPException(status_code=code, detail=detail)


def _may_see_issuer_breaches(db: Session, principal: Principal) -> bool:
    """Whether this caller may receive breaches that carry issuer identity (review D2).

    The same gate ``api/limits.py`` applies, for the same reason and on stronger grounds: a
    SHARE/ISSUER breach's ``observed_value`` IS the ISSUER-dimension share CON-1 fenced, so this
    surface discloses the NUMBER, not merely an id. ``auditor_3l`` holds ``breach.view`` and is
    deliberately excluded from ``concentration.issuer.view``.
    """
    return has_permission(db, principal, "concentration.issuer.view", principal.tenant_id)


def _load_or_404(
    db: Session, principal: Principal, breach_id: uuid.UUID, *, include_issuer_detail: bool
) -> Breach:
    """Load one breach or 404.

    ``include_issuer_detail`` is REQUIRED rather than defaulted, exactly as on the limits router:
    the mutation verbs must pass ``True`` (they are separately gated on ``breach.respond`` /
    ``breach.review``, and a fenced load would make every issuer-bearing breach unremediable),
    while the read paths pass the caller's entitlement. A default would hide the wrong choice at
    the call site, and this is a disclosure boundary.
    """
    breach = get_breach(
        db,
        acting_tenant=principal.tenant_id,
        breach_id=str(breach_id),
        include_issuer_detail=include_issuer_detail,
    )
    if breach is None:
        # Missing, cross-tenant, or issuer-fenced — ONE indistinguishable 404. A 403 on the fenced
        # case would itself confirm that a breach exists at that id.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="breach not found")
    return breach


def _require_assignee_can_respond(db: Session, tenant_id: str, assigned_to: str) -> str:
    """C-OQ2=B: the assignee must hold ``breach.respond`` — assigning to someone who cannot
    respond guarantees escalation. Checked at the ROUTER (entitlement is an API-layer concern;
    the shared limit package stays free of entitlement imports). The id is UUID-shape-checked and
    CANONICALIZED first (4-finder fold): a raw non-UUID string would 22P02→500 at the PG uuid
    cast, and a raw-cased compare is tier-divergent (the D1 stamp≠compare class). Returns the
    canonical id for the service call."""
    try:
        canonical = str(uuid.UUID(assigned_to.strip()))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assignee must be a user id",
        ) from None
    assignee = Principal(user_id=canonical, tenant_id=tenant_id)
    if not has_permission(db, assignee, "breach.respond", tenant_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assignee must hold breach.respond",
        )
    return canonical


# --- DTOs ---------------------------------------------------------------------------------
class BreachAssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_to: str  # resolved+canonicalized in the SERVICE (D8); permission-checked here
    expected_seq: int | None = None

    @field_validator("assigned_to")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip() or len(v) > 255:
            raise ValueError("assigned_to must be a non-empty principal id (max 255)")
        return v


class BreachRespondIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narrative: str
    expected_seq: int | None = None

    @field_validator("narrative")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip() or len(v) > 2000:
            raise ValueError("narrative must be non-empty (max 2000)")
        return v


class BreachReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: _ReviewOutcome
    narrative: str | None = None
    assigned_to: str | None = None  # REJECT only (service-refused on ACCEPT); OQ-1=A
    expected_seq: int | None = None

    @field_validator("narrative")
    @classmethod
    def _bounded(cls, v: str | None) -> str | None:
        if v is not None and (not v.strip() or len(v) > 2000):
            raise ValueError("must be non-empty when present (max 2000)")
        return v

    @field_validator("assigned_to")
    @classmethod
    def _bounded_assignee(cls, v: str | None) -> str | None:
        if v is not None and (not v.strip() or len(v) > 255):
            raise ValueError("must be non-empty when present (max 255)")
        return v


class BreachCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_ref: str
    narrative: str | None = None
    expected_seq: int | None = None

    @field_validator("evidence_ref")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip() or len(v) > 500:
            raise ValueError("evidence_ref must be non-empty (max 500)")
        return v

    @field_validator("narrative")
    @classmethod
    def _bounded(cls, v: str | None) -> str | None:
        if v is not None and (not v.strip() or len(v) > 2000):
            raise ValueError("narrative must be non-empty when present (max 2000)")
        return v


class BreachOut(BaseModel):
    id: str
    limit_definition_id: str
    calculation_run_id: str
    detected_at: datetime
    target_run_type: str
    metric_type: str
    benchmark_id: str | None
    observed_value: str  # fixed-point string (FE-2 decimal contract)
    threshold_value: str
    threshold_unit: _Unit
    breach_direction: _Direction
    limit_kind: _Kind
    severity: _Kind
    # NOTE: the frozen `Breach.status` column is deliberately NOT serialized (D6) — `state` is the
    # recency-derived lifecycle truth; the column reads DETECTED forever.
    state: _BreachState
    assigned_to: str | None
    response_due: datetime | None
    scope_portfolio_id: str
    limit_code: str
    #: The CURRENT timeline head (max action ``seq``; 0 when none) — the token to send back as
    #: ``expected_seq`` on the next write (OPS-1 fold H3). Serializing it here is what makes the
    #: optimistic-concurrency precondition usable: previously a client had to fetch the full action
    #: list to learn the head, so the fail-open ``expected_seq=None`` default was the path of least
    #: resistance. A COUNT, not a decimal (see the FE decimal-contract guard).
    seq: int


class BreachActionOut(BaseModel):
    id: str
    breach_id: str
    seq: int
    action_type: _ActionType
    from_state: _BreachState
    to_state: _BreachState
    actor_id: str
    actor_line: _ActorLine
    assigned_to: str | None
    response_due: datetime | None
    epoch_seq: int | None
    narrative: str | None
    review_outcome: _ReviewOutcome | None
    evidence_ref: str | None
    occurred_at: datetime


def _breach_out(item: BreachQueueItem) -> BreachOut:
    b = item.breach
    return BreachOut(
        id=b.id,
        limit_definition_id=b.limit_definition_id,
        calculation_run_id=b.calculation_run_id,
        detected_at=cast(datetime, _as_utc(b.detected_at)),
        target_run_type=b.target_run_type,
        metric_type=b.metric_type,
        benchmark_id=b.benchmark_id,
        observed_value=f"{b.observed_value:f}",
        threshold_value=f"{b.threshold_value:f}",
        threshold_unit=cast(_Unit, b.threshold_unit),
        breach_direction=cast(_Direction, b.breach_direction),
        limit_kind=cast(_Kind, b.limit_kind),
        severity=cast(_Kind, b.severity),
        state=cast(_BreachState, item.state),
        assigned_to=item.assigned_to,
        response_due=_as_utc(item.response_due),
        scope_portfolio_id=item.scope_portfolio_id,
        limit_code=item.limit_code,
        seq=item.seq,
    )


def _action_out(a: BreachAction) -> BreachActionOut:
    return BreachActionOut(
        id=a.id,
        breach_id=a.breach_id,
        seq=a.seq,
        action_type=cast(_ActionType, a.action_type),
        from_state=cast(_BreachState, a.from_state),
        to_state=cast(_BreachState, a.to_state),
        actor_id=a.actor_id,
        actor_line=cast(_ActorLine, a.actor_line),
        assigned_to=a.assigned_to,
        response_due=_as_utc(a.response_due),
        epoch_seq=a.epoch_seq,
        narrative=a.narrative,
        review_outcome=cast("_ReviewOutcome | None", a.review_outcome),
        evidence_ref=a.evidence_ref,
        occurred_at=cast(datetime, _as_utc(a.occurred_at)),
    )


class BreachNotificationOut(BaseModel):
    id: str
    breach_id: str
    source_sequence_no: int
    source_event_type: _NotifySourceEvent
    recipient_id: str
    recipient_reason: str
    channel: _NotifyChannel
    outcome: _NotifyOutcome
    failure_reason: str | None
    severity: str
    notified_at: datetime


def _notification_out(n: BreachNotification) -> BreachNotificationOut:
    return BreachNotificationOut(
        id=n.id,
        breach_id=n.breach_id,
        source_sequence_no=n.source_sequence_no,
        source_event_type=cast(_NotifySourceEvent, n.source_event_type),
        recipient_id=n.recipient_id,
        recipient_reason=n.recipient_reason,
        channel=cast(_NotifyChannel, n.channel),
        outcome=cast(_NotifyOutcome, n.outcome),
        failure_reason=n.failure_reason,
        severity=n.severity,
        notified_at=cast(datetime, _as_utc(n.notified_at)),
    )


def _detail_out(db: Session, principal: Principal, breach_id: str) -> BreachOut:
    item = breach_detail(
        db,
        acting_tenant=principal.tenant_id,
        breach_id=breach_id,
        include_issuer_detail=_may_see_issuer_breaches(db, principal),
    )
    if item is None:  # unreachable post-load; defensive
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="breach not found")
    return _breach_out(item)


# --- transition endpoints -----------------------------------------------------------------
@router.post("/{breach_id}/assign", response_model=BreachOut, responses=_WRITE_REFUSALS)
def assign(
    breach_id: uuid.UUID,
    body: BreachAssignIn,
    principal: Principal = Depends(_require_review),
    db: Session = Depends(get_tenant_session),
) -> BreachOut:
    breach = _load_or_404(db, principal, breach_id, include_issuer_detail=True)
    assignee = _require_assignee_can_respond(db, principal.tenant_id, body.assigned_to)
    try:
        assign_breach(
            db,
            breach,
            assigned_to=assignee,
            actor=_breach_actor(principal),
            now=utcnow(),
            expected_seq=body.expected_seq,
        )
    except BreachLifecycleError as exc:
        raise _refuse(db, exc) from None
    except OperationalError as exc:
        raise deadlock_503(db, exc) from None
    out = _detail_out(db, principal, str(breach_id))  # build BEFORE the single commit
    db.commit()
    return out


@router.post("/{breach_id}/respond", response_model=BreachOut, responses=_WRITE_REFUSALS)
def respond(
    breach_id: uuid.UUID,
    body: BreachRespondIn,
    principal: Principal = Depends(_require_respond),
    db: Session = Depends(get_tenant_session),
) -> BreachOut:
    breach = _load_or_404(db, principal, breach_id, include_issuer_detail=True)
    try:
        respond_breach(
            db,
            breach,
            narrative=body.narrative,
            actor=_breach_actor(principal),
            now=utcnow(),
            expected_seq=body.expected_seq,
        )
    except BreachLifecycleError as exc:
        raise _refuse(db, exc) from None
    except OperationalError as exc:
        raise deadlock_503(db, exc) from None
    out = _detail_out(db, principal, str(breach_id))
    db.commit()
    return out


@router.post("/{breach_id}/review", response_model=BreachOut, responses=_WRITE_REFUSALS)
def review(
    breach_id: uuid.UUID,
    body: BreachReviewIn,
    principal: Principal = Depends(_require_review),
    db: Session = Depends(get_tenant_session),
) -> BreachOut:
    if body.outcome == "REJECT" and (body.narrative is None or not body.narrative.strip()):
        # A bare rejection gives the 1L nothing to remediate against (audit A-F8) — DTO-tier rule.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a REJECT review requires a narrative",
        )
    breach = _load_or_404(db, principal, breach_id, include_issuer_detail=True)
    assignee: str | None = None
    if body.assigned_to is not None:
        assignee = _require_assignee_can_respond(db, principal.tenant_id, body.assigned_to)
    try:
        review_breach(
            db,
            breach,
            outcome=body.outcome,
            actor=_breach_actor(principal),
            now=utcnow(),
            narrative=body.narrative,
            assigned_to=assignee,
            expected_seq=body.expected_seq,
        )
    except BreachLifecycleError as exc:
        raise _refuse(db, exc) from None
    except OperationalError as exc:
        raise deadlock_503(db, exc) from None
    out = _detail_out(db, principal, str(breach_id))
    db.commit()
    return out


@router.post("/{breach_id}/close", response_model=BreachOut, responses=_WRITE_REFUSALS)
def close(
    breach_id: uuid.UUID,
    body: BreachCloseIn,
    principal: Principal = Depends(_require_review),
    db: Session = Depends(get_tenant_session),
) -> BreachOut:
    breach = _load_or_404(db, principal, breach_id, include_issuer_detail=True)
    try:
        close_breach(
            db,
            breach,
            evidence_ref=body.evidence_ref,
            actor=_breach_actor(principal),
            now=utcnow(),
            narrative=body.narrative,
            expected_seq=body.expected_seq,
        )
    except BreachLifecycleError as exc:
        raise _refuse(db, exc) from None
    except OperationalError as exc:
        raise deadlock_503(db, exc) from None
    out = _detail_out(db, principal, str(breach_id))
    db.commit()
    return out


# --- reads --------------------------------------------------------------------------------
@router.get("", response_model=list[BreachOut], responses=_COLLECTION_REFUSALS)
def index(
    state_filter: _BreachState | None = Query(default=None, alias="state"),
    open_only: bool = Query(default=False, alias="open"),
    portfolio_id: uuid.UUID | None = Query(default=None),
    assigned_to_me: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[BreachOut]:
    # The batched queue read (D9) — one statement; `open=true` = the working queue.
    items = list_breaches(
        db,
        acting_tenant=principal.tenant_id,
        state=state_filter,
        open_only=open_only,
        portfolio_id=str(portfolio_id) if portfolio_id else None,
        assigned_to=principal.user_id if assigned_to_me else None,
        limit=limit,
        offset=offset,
        include_issuer_detail=_may_see_issuer_breaches(db, principal),
    )
    return [_breach_out(x) for x in items]


@router.get("/{breach_id}", response_model=BreachOut, responses=_READ_REFUSALS)
def show(
    breach_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> BreachOut:
    _load_or_404(
        db, principal, breach_id, include_issuer_detail=_may_see_issuer_breaches(db, principal)
    )
    return _detail_out(db, principal, str(breach_id))


@router.get("/{breach_id}/actions", response_model=list[BreachActionOut], responses=_READ_REFUSALS)
def actions(
    breach_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[BreachActionOut]:
    _load_or_404(
        db, principal, breach_id, include_issuer_detail=_may_see_issuer_breaches(db, principal)
    )
    timeline = breach_action_timeline(
        db, acting_tenant=principal.tenant_id, breach_id=str(breach_id)
    )
    return [_action_out(a) for a in timeline]


@router.get(
    "/{breach_id}/notifications",
    response_model=list[BreachNotificationOut],
    responses=_READ_REFUSALS,
)
def notifications(
    breach_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[BreachNotificationOut]:
    # NOTIF-1: the alarm-attempt evidence for this breach — "who was owed an alert, with what
    # outcome". Gated `breach.view` (a notification is breach-adjacent evidence; no new permission).
    _load_or_404(
        db, principal, breach_id, include_issuer_detail=_may_see_issuer_breaches(db, principal)
    )
    rows = list_breach_notifications(
        db, acting_tenant=principal.tenant_id, breach_id=str(breach_id), limit=limit, offset=offset
    )
    return [_notification_out(n) for n in rows]
