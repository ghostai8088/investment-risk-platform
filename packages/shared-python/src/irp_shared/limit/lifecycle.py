"""The breach remediation lifecycle — the DEP-WFL machine over ENT-034 ``breach_action`` (MG-2).

The machine: ``DETECTED → ASSIGNED → RESPONDED(1L) → REVIEWED(2L) → CLOSED`` with an orthogonal
``ESCALATED`` (reachable from ASSIGNED/RESPONDED when the response deadline passes). The breach's
OPERATIVE current state is the ``to_state`` of the latest ``breach_action`` by ``seq`` (recency-
derived — the VW-1 pattern; NEVER a mutated flag, since the table is append-only).

Every transition is serialized per breach by a ``SELECT … FOR UPDATE`` on the parent ``breach`` row
(``_lock_breach``): this makes the read-state → validate → append sequence linearizable even under
concurrent per-tenant operational ticks (VERIFIER B-2/B-3/H-1 — the append-only log otherwise
permits a nondeterministic-state / double-escalate / stale-resurrection / SoD-bypass race). Under
the lock, ``seq`` is assigned as ``max(seq)+1`` (race-free monotonic ordering, cross-tier — SQLite
has no ``FOR UPDATE`` but serializes all writes globally, VERIFIER B-1).

Person-level SoD (SOD-02, the platform's FIRST same-actor refusal): a ``2L_REVIEW``/``CLOSE`` actor
is refused if they are in the SET of ALL prior ``1L_RESPONSE`` actors on the breach (VERIFIER B-3 —
a latest-only check is defeatable across a reject→re-respond cycle). The role partition
(``breach.respond`` 1L / ``breach.review`` 2L, never co-granted to a non-admin role) is the first
line; this set-check is the backstop for the ``platform_admin`` dual-hat.
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session, aliased

from irp_shared.audit.actions import ACTION_RECORD
from irp_shared.audit.service import record_event
from irp_shared.limit.events import (
    BREACH_ACTION_1L_RESPONSE,
    BREACH_ACTION_2L_REVIEW,
    BREACH_ACTION_ASSIGN,
    BREACH_ACTION_CLOSE,
    BREACH_ACTION_ESCALATE,
    BREACH_ACTION_EVENTS,
    BREACH_LINE_1L,
    BREACH_LINE_2L,
    BREACH_LINE_SYSTEM,
    BREACH_REVIEW_ACCEPT,
    BREACH_REVIEW_OUTCOMES,
    BREACH_REVIEW_REJECT,
    BREACH_SLA_DAYS,
    BREACH_STATE_ASSIGNED,
    BREACH_STATE_CLOSED,
    BREACH_STATE_DETECTED,
    BREACH_STATE_ESCALATED,
    BREACH_STATE_RESPONDED,
    BREACH_STATE_REVIEWED,
    BREACH_STATES,
    BREACH_SYSTEM_ACTOR_TYPE,
    ENTITY_BREACH_ACTION,
    SOURCE_MODULE_LIMIT,
    BreachActor,
    _canonical_actor_id,
)
from irp_shared.limit.models import Breach, BreachAction, LimitDefinition

# States eligible for auto-escalation (a response clock is running). DETECTED (never assigned) has
# no clock; REVIEWED/ESCALATED/CLOSED are not overdue-escalatable.
_ESCALATABLE_STATES = frozenset({BREACH_STATE_ASSIGNED, BREACH_STATE_RESPONDED})


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a stored deadline to tz-aware UTC before comparison (PG returns aware datetimes;
    SQLite drops the tz — the ``db/bitemporal.py`` convention). A no-op on already-aware values."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class BreachLifecycleError(Exception):
    """A breach-lifecycle rule was violated (mapped to HTTP 422 at the API boundary)."""


class BreachTransitionError(BreachLifecycleError):
    """An illegal state transition, a missing/cross-tenant breach, or a non-human actor."""


class BreachStaleSeqError(BreachTransitionError):
    """The optimistic-concurrency precondition failed: the timeline advanced since the caller read
    it (OPS-1 fold H2). A SUBCLASS of ``BreachTransitionError`` so every existing handler keeps
    working, but it gets its OWN API error-map key: on the wire it was previously INDISTINGUISHABLE
    from an illegal transition (same 409, same detail string), which would make an operations UI
    say "you may not do this" when the truthful answer is "someone — probably the tick — changed
    this breach while you were reading it; reload and retry". Those demand opposite user actions."""


class BreachSodError(BreachLifecycleError):
    """A person-level SoD violation (a prior 1L responder cannot review/close the same breach)."""


class BreachAssigneeError(BreachLifecycleError):
    """``assigned_to`` failed resolution (not UUID-shaped / unknown / inactive / cross-tenant) —
    a REQUEST-CONTENT refusal, mapped 422, NEVER the 409 state-conflict class (4-finder M1: the
    409 detail "illegal transition" would be a lie about a perfectly healthy breach state)."""


def _resolve_to_state(from_state: str, action_type: str, review_outcome: str | None) -> str:
    """The allowed-transition table (VW-1 has none to copy — this IS the greenfield artifact).

    Raises ``BreachTransitionError`` on any illegal ``(from_state, action_type)``.
    """
    if action_type == BREACH_ACTION_ASSIGN and from_state == BREACH_STATE_DETECTED:
        return BREACH_STATE_ASSIGNED
    if action_type == BREACH_ACTION_1L_RESPONSE and from_state in {
        BREACH_STATE_ASSIGNED,
        BREACH_STATE_ESCALATED,
    }:
        return BREACH_STATE_RESPONDED
    if action_type == BREACH_ACTION_ESCALATE and from_state in _ESCALATABLE_STATES:
        return BREACH_STATE_ESCALATED
    if action_type == BREACH_ACTION_2L_REVIEW and from_state in {
        BREACH_STATE_RESPONDED,
        BREACH_STATE_ESCALATED,
    }:
        # ACCEPT advances to REVIEWED; REJECT sends it back to ASSIGNED (a fresh response epoch).
        return (
            BREACH_STATE_REVIEWED
            if review_outcome == BREACH_REVIEW_ACCEPT
            else BREACH_STATE_ASSIGNED
        )
    if action_type == BREACH_ACTION_CLOSE and from_state == BREACH_STATE_REVIEWED:
        return BREACH_STATE_CLOSED
    raise BreachTransitionError(
        f"illegal breach transition: {from_state} --{action_type}--> (not permitted)"
    )


def _lock_breach(session: Session, breach_id: str, tenant_id: str) -> Breach:
    """Re-resolve the breach tenant-filtered AND take a row lock (the linearizability backstop).

    The tenant filter is load-bearing: PG FK checks bypass RLS, so a caller-supplied cross-tenant
    ``breach_id`` must be refused, not acted on (the P3-5 doctrine, LIM-1 ``create_limit``). The
    ``with_for_update`` serializes all transitions on this breach; on SQLite it is a no-op but
    SQLite serializes writes globally, so the invariant holds cross-tier.
    """
    breach = session.execute(
        select(Breach)
        .where(Breach.id == breach_id, Breach.tenant_id == tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if breach is None:
        raise BreachTransitionError(f"breach {breach_id} not found in tenant {tenant_id}")
    return breach


def current_breach_state(session: Session, breach_id: str, *, acting_tenant: str) -> str:
    """The operative lifecycle state = the latest ``breach_action.to_state`` by ``seq`` (recency),
    or ``DETECTED`` if no action exists. Tenant-filtered atop RLS (VERIFIER H-2)."""
    state = session.execute(
        select(BreachAction.to_state)
        .where(BreachAction.breach_id == breach_id, BreachAction.tenant_id == acting_tenant)
        .order_by(BreachAction.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    return state or BREACH_STATE_DETECTED


def _governing_assign(session: Session, breach_id: str, tenant_id: str) -> BreachAction | None:
    """The governing epoch-opening action = the latest action whose ``to_state == ASSIGNED`` (the
    ASSIGN, or a 2L REJECT re-assignment). Its ``response_due`` is the deadline in force; its
    ``seq`` is the escalation epoch key (a true monotonic id — VERIFIER-F1-MED1)."""
    return session.execute(
        select(BreachAction)
        .where(
            BreachAction.breach_id == breach_id,
            BreachAction.tenant_id == tenant_id,
            BreachAction.to_state == BREACH_STATE_ASSIGNED,
        )
        .order_by(BreachAction.seq.desc())
        .limit(1)
    ).scalar_one_or_none()


def _prior_1l_responders(session: Session, breach_id: str, tenant_id: str) -> set[str]:
    """The SET of ALL principals who filed a 1L_RESPONSE on this breach (the SoD forbidden set —
    VERIFIER B-3: not merely the latest responder)."""
    rows = session.execute(
        select(BreachAction.actor_id).where(
            BreachAction.breach_id == breach_id,
            BreachAction.tenant_id == tenant_id,
            BreachAction.action_type == BREACH_ACTION_1L_RESPONSE,
        )
    ).scalars()
    return set(rows)


def _next_seq(session: Session, breach_id: str, tenant_id: str) -> int:
    """The next per-breach monotonic ``seq`` (``max+1``, 1-based) — race-free under the lock."""
    current = session.execute(
        select(func.max(BreachAction.seq)).where(
            BreachAction.breach_id == breach_id, BreachAction.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    return (current or 0) + 1


def _check_expected_seq(session: Session, breach: Breach, expected_seq: int | None) -> None:
    """The OQ-API-2b-4=A optimistic-concurrency precondition, checked UNDER the lock.

    A caller that read the timeline at ``seq == expected_seq`` is refused if any action landed
    since — closing the cycle-class retry hole (a gateway-retried respond after an interleaved tick
    ESCALATE would otherwise silently clear the alarm state; audit F-B3/F-B5). ``None`` (the
    default) preserves the unconditioned MG-2 behavior for every existing caller.
    """
    if expected_seq is None:
        return
    current = _next_seq(session, breach.id, breach.tenant_id) - 1
    if current != expected_seq:
        # BreachStaleSeqError (not the bare transition error): "reload, someone changed this" is a
        # different instruction to the operator than "that move is illegal" (OPS-1 fold H2).
        raise BreachStaleSeqError(
            f"stale expected_seq {expected_seq}: the breach timeline has advanced to {current}"
        )


def _require_current_epoch_response(session: Session, breach: Breach) -> None:
    """The EPOCH-AWARE review guard (audit A-F1, uniform on ACCEPT and REJECT — OQ-A2b-3=A).

    A 2L review requires a ``1L_RESPONSE`` filed IN THE CURRENT EPOCH — ``seq`` strictly greater
    than the governing epoch-opening action's ``seq`` (the latest ``to_state == ASSIGNED`` row).
    The all-time set check (REQ-BRC-002) alone is epoch-blind: after a REJECT, the rejected
    response still satisfies it, so reject → (escalate) → ACCEPT could ratify the exact response
    the 2L organization formally adjudicated inadequate, with zero fresh 1L work.
    """
    governing = _governing_assign(session, breach.id, breach.tenant_id)
    governing_seq = governing.seq if governing is not None else 0
    latest_response = session.execute(
        select(func.max(BreachAction.seq)).where(
            BreachAction.breach_id == breach.id,
            BreachAction.tenant_id == breach.tenant_id,
            BreachAction.action_type == BREACH_ACTION_1L_RESPONSE,
        )
    ).scalar_one_or_none()
    if latest_response is None or latest_response <= governing_seq:
        raise BreachTransitionError(
            "a 2L review requires a 1L response from the CURRENT epoch — the prior response "
            "was adjudicated by an earlier review (REQ-BRC-002, epoch-aware)"
        )


def _resolve_assignee(session: Session, tenant_id: str, assigned_to: str) -> str:
    """Canonicalize + resolve ``assigned_to`` to an ACTIVE same-tenant ``app_user.id`` (audit
    A-F5/C-F5, the D8 demand): the stamped value is the RESOLVED canonical id, never the request
    string — a non-canonical stamp would silently never match the canonical queue filter (the D1
    stamp≠compare bug's third instance). Raw SQL keeps the shared limit package free of an
    entitlement-model import (the ``service.py`` benchmark-check precedent)."""
    if not assigned_to or not assigned_to.strip():
        raise BreachAssigneeError("assigned_to requires a non-empty principal id")
    canonical = _canonical_actor_id(assigned_to.strip())
    try:
        uuid_module.UUID(canonical)
    except (ValueError, AttributeError, TypeError):
        # Refuse BEFORE the SQL bind: a non-UUID string against the PG uuid column is a 22P02
        # DataError -> an unmapped 500 (4-finder fold, finders 1+4 converged; SQLite-invisible).
        raise BreachAssigneeError("assigned_to must be an app_user id") from None
    row = session.execute(
        text("SELECT 1 FROM app_user WHERE id = :id AND tenant_id = :tenant AND is_active"),
        {"id": canonical, "tenant": tenant_id},
    ).scalar()
    if row is None:
        raise BreachAssigneeError(
            "assigned_to must resolve to an ACTIVE app_user in the acting tenant"
        )
    return canonical


def _insert_action(
    session: Session,
    breach: Breach,
    *,
    action_type: str,
    from_state: str,
    to_state: str,
    actor_id: str,
    actor_line: str,
    now: datetime,
    assigned_to: str | None = None,
    response_due: datetime | None = None,
    epoch_seq: int | None = None,
    narrative: str | None = None,
    review_outcome: str | None = None,
    evidence_ref: str | None = None,
) -> BreachAction:
    """Append one ``breach_action`` (seq under the lock) and emit its realized BREACH.* event."""
    action = BreachAction(
        tenant_id=breach.tenant_id,
        breach_id=breach.id,
        seq=_next_seq(session, breach.id, breach.tenant_id),
        action_type=action_type,
        from_state=from_state,
        to_state=to_state,
        actor_id=actor_id,
        actor_line=actor_line,
        assigned_to=assigned_to,
        response_due=response_due,
        epoch_seq=epoch_seq,
        narrative=narrative,
        review_outcome=review_outcome,
        evidence_ref=evidence_ref,
        occurred_at=now,
    )
    session.add(action)
    session.flush()
    _record_breach_action_event(session, breach=breach, action=action)
    return action


def _record_breach_action_event(session: Session, *, breach: Breach, action: BreachAction) -> None:
    """Emit the realized BREACH lifecycle audit event caller-side to the FROZEN ``record_event``."""
    is_system = action.actor_line == BREACH_LINE_SYSTEM
    record_event(
        session,
        event_type=BREACH_ACTION_EVENTS[action.action_type],
        tenant_id=breach.tenant_id,
        actor_type=BREACH_SYSTEM_ACTOR_TYPE if is_system else "user",
        actor_id=action.actor_id,
        source_module=SOURCE_MODULE_LIMIT,
        entity_type=ENTITY_BREACH_ACTION,
        entity_id=action.id,
        action=ACTION_RECORD,
        # An escalation is an alarm — raise the audit envelope severity.
        severity="warning" if action.action_type == BREACH_ACTION_ESCALATE else "info",
        after_value={
            "breach_id": str(action.breach_id),
            "seq": action.seq,
            "action_type": action.action_type,
            "from_state": action.from_state,
            "to_state": action.to_state,
            "actor_line": action.actor_line,
            "assigned_to": action.assigned_to,
            "response_due": action.response_due.isoformat() if action.response_due else None,
            "epoch_seq": action.epoch_seq,
            "review_outcome": action.review_outcome,
            "evidence_ref": action.evidence_ref,
        },
    )


def _require_human(actor: BreachActor) -> None:
    if actor.actor_type != "user":
        raise BreachTransitionError("a breach lifecycle transition requires a human actor (BR-15)")


def _sla_due(breach: Breach, now: datetime) -> datetime:
    """The response deadline = ``now + SLA(limit_kind)`` (the OQ-4 hardcoded HARD/SOFT map v1)."""
    sla_days = BREACH_SLA_DAYS.get(breach.limit_kind)
    if sla_days is None:  # off-vocab limit_kind — a clean 422, not a bare KeyError → 500
        raise BreachTransitionError(f"no response SLA for limit_kind {breach.limit_kind!r}")
    return now + timedelta(days=sla_days)


def assign_breach(
    session: Session,
    breach: Breach,
    *,
    assigned_to: str,
    actor: BreachActor,
    now: datetime,
    expected_seq: int | None = None,
) -> BreachAction:
    """2L assigns a 1L owner + starts the clock (DETECTED → ASSIGNED). Gate breach.review.

    ``assigned_to`` is canonicalized + resolved to an ACTIVE same-tenant ``app_user`` UNDER the
    lock (API-2b A-F5/D8 — a raw stamp would silently never match the canonical queue filter).
    """
    _require_human(actor)
    locked = _lock_breach(session, breach.id, breach.tenant_id)
    _check_expected_seq(session, locked, expected_seq)
    resolved = _resolve_assignee(session, locked.tenant_id, assigned_to)
    state = current_breach_state(session, locked.id, acting_tenant=locked.tenant_id)
    to_state = _resolve_to_state(state, BREACH_ACTION_ASSIGN, None)
    return _insert_action(
        session,
        locked,
        action_type=BREACH_ACTION_ASSIGN,
        from_state=state,
        to_state=to_state,
        actor_id=actor.actor_id,
        actor_line=BREACH_LINE_2L,
        now=now,
        assigned_to=resolved,
        response_due=_sla_due(locked, now),
    )


def respond_breach(
    session: Session,
    breach: Breach,
    *,
    narrative: str,
    actor: BreachActor,
    now: datetime,
    expected_seq: int | None = None,
) -> BreachAction:
    """1L files a remediation response (ASSIGNED|ESCALATED → RESPONDED). Gate: breach.respond."""
    _require_human(actor)
    if not narrative or not narrative.strip():
        raise BreachTransitionError("a 1L response requires a narrative")
    locked = _lock_breach(session, breach.id, breach.tenant_id)
    _check_expected_seq(session, locked, expected_seq)
    state = current_breach_state(session, locked.id, acting_tenant=locked.tenant_id)
    to_state = _resolve_to_state(state, BREACH_ACTION_1L_RESPONSE, None)
    return _insert_action(
        session,
        locked,
        action_type=BREACH_ACTION_1L_RESPONSE,
        from_state=state,
        to_state=to_state,
        actor_id=actor.actor_id,
        actor_line=BREACH_LINE_1L,
        now=now,
        narrative=narrative,
    )


def review_breach(
    session: Session,
    breach: Breach,
    *,
    outcome: str,
    actor: BreachActor,
    now: datetime,
    narrative: str | None = None,
    assigned_to: str | None = None,
    expected_seq: int | None = None,
) -> BreachAction:
    """2L reviews a 1L response (RESPONDED|ESCALATED → REVIEWED on ACCEPT, → ASSIGNED on REJECT).

    Gate: ``breach.review``. A 2L review REQUIRES a 1L response FROM THE CURRENT EPOCH (the
    epoch-aware form of REQ-BRC-002 — API-2b A-F1: the all-time set alone would let a REJECTed
    response be ACCEPTed later with zero fresh 1L work). Person-level SoD: reviewer must NOT be
    a prior 1L responder (the all-time SET — cumulative is correct for SoD). A REJECT re-opens
    to ASSIGNED with a FRESH response deadline (a new escalation epoch) and CARRIES the owner
    (OQ-API-2b-1=A): ``assigned_to`` explicit (resolved like ASSIGN) or defaulted to the prior
    epoch's assignee — the queue's owner concept never goes None on a REJECT. ``assigned_to``
    is refused on ACCEPT (an accepted breach awaits closure, not a new owner).
    """
    _require_human(actor)
    if outcome not in BREACH_REVIEW_OUTCOMES:
        raise BreachTransitionError(f"invalid review outcome {outcome!r}")
    if assigned_to is not None and outcome != BREACH_REVIEW_REJECT:
        raise BreachTransitionError("assigned_to may only accompany a REJECT review")
    locked = _lock_breach(session, breach.id, breach.tenant_id)
    _check_expected_seq(session, locked, expected_seq)
    responders = _prior_1l_responders(session, locked.id, locked.tenant_id)
    if actor.actor_id in responders:
        raise BreachSodError(
            f"actor {actor.actor_id} filed a 1L response on this breach; cannot review it (SOD-02)"
        )
    _require_current_epoch_response(session, locked)  # subsumes the empty-set REQ-BRC-002 check
    state = current_breach_state(session, locked.id, acting_tenant=locked.tenant_id)
    to_state = _resolve_to_state(state, BREACH_ACTION_2L_REVIEW, outcome)
    # A REJECT restarts the clock; an ACCEPT clears it (the breach awaits closure, not response).
    response_due = _sla_due(locked, now) if to_state == BREACH_STATE_ASSIGNED else None
    carried_assignee: str | None = None
    if to_state == BREACH_STATE_ASSIGNED:
        if assigned_to is not None:
            carried_assignee = _resolve_assignee(session, locked.tenant_id, assigned_to)
        else:
            governing = _governing_assign(session, locked.id, locked.tenant_id)
            carried_assignee = governing.assigned_to if governing is not None else None
    return _insert_action(
        session,
        locked,
        action_type=BREACH_ACTION_2L_REVIEW,
        from_state=state,
        to_state=to_state,
        actor_id=actor.actor_id,
        actor_line=BREACH_LINE_2L,
        now=now,
        review_outcome=outcome,
        narrative=narrative,
        response_due=response_due,
        assigned_to=carried_assignee,
    )


def close_breach(
    session: Session,
    breach: Breach,
    *,
    evidence_ref: str,
    actor: BreachActor,
    now: datetime,
    narrative: str | None = None,
    expected_seq: int | None = None,
) -> BreachAction:
    """2L closes a reviewed breach with evidence (REVIEWED → CLOSED). Gate: ``breach.review``.

    ``evidence_ref`` is REQUIRED (REQ-BRC-003). Person-level SoD: the closer must NOT be a prior 1L
    responder (SOD-02, "1L cannot approve own closure").
    """
    _require_human(actor)
    if not evidence_ref or not evidence_ref.strip():
        raise BreachTransitionError("closing a breach requires closure evidence (REQ-BRC-003)")
    locked = _lock_breach(session, breach.id, breach.tenant_id)
    _check_expected_seq(session, locked, expected_seq)
    if actor.actor_id in _prior_1l_responders(session, locked.id, locked.tenant_id):
        raise BreachSodError(
            f"actor {actor.actor_id} filed a 1L response; cannot close this breach (SOD-02)"
        )
    state = current_breach_state(session, locked.id, acting_tenant=locked.tenant_id)
    to_state = _resolve_to_state(state, BREACH_ACTION_CLOSE, None)
    return _insert_action(
        session,
        locked,
        action_type=BREACH_ACTION_CLOSE,
        from_state=state,
        to_state=to_state,
        actor_id=actor.actor_id,
        actor_line=BREACH_LINE_2L,
        now=now,
        evidence_ref=evidence_ref,
        narrative=narrative,
    )


def escalate_overdue_breach(session: Session, breach: Breach, now: datetime) -> BreachAction | None:
    """Auto-escalate one overdue breach (SYSTEM). Returns the action, or ``None`` if — re-checked
    UNDER the lock — the breach is no longer escalatable (recovered/closed) or not yet overdue.

    Idempotency: the ESCALATE row is keyed by the governing ASSIGN action's ``epoch_seq``;
    ``uq_breach_escalation`` (breach_id, epoch_seq) makes a re-escalation of the SAME epoch a benign
    dedup, while a post-recovery REJECT opens a NEW governing action (a new epoch) that CAN escalate
    again — robust even if two epochs compute the same ``response_due`` (VERIFIER-F1-MED1).
    """
    now_utc = _as_utc(now)
    assert now_utc is not None
    locked = _lock_breach(session, breach.id, breach.tenant_id)
    state = current_breach_state(session, locked.id, acting_tenant=locked.tenant_id)
    if state not in _ESCALATABLE_STATES:
        return None
    governing = _governing_assign(session, locked.id, locked.tenant_id)
    due = _as_utc(governing.response_due) if governing is not None else None
    if governing is None or due is None or due >= now_utc:
        return None
    return _insert_action(
        session,
        locked,
        action_type=BREACH_ACTION_ESCALATE,
        from_state=state,
        to_state=BREACH_STATE_ESCALATED,
        actor_id=f"breach-deadline:{locked.id}",
        actor_line=BREACH_LINE_SYSTEM,
        now=now_utc,
        response_due=due,
        epoch_seq=governing.seq,
    )


# --- API-2b reads (D9/C-F2: the batched greatest-n-per-group; one module owns the recency rule) ---


def get_breach(session: Session, *, acting_tenant: str, breach_id: str) -> Breach | None:
    """One breach, tenant-filtered atop RLS (mirrors ``get_limit`` — missing/cross-tenant → None,
    an indistinguishable 404 at the API). Doubles as the transition endpoints' load step."""
    return session.execute(
        select(Breach).where(Breach.id == breach_id, Breach.tenant_id == acting_tenant)
    ).scalar_one_or_none()


def breach_action_timeline(
    session: Session, *, acting_tenant: str, breach_id: str
) -> list[BreachAction]:
    """The breach's full action timeline ordered by ``seq`` ASC — NEVER ``occurred_at``, which is
    non-monotonic across writers (tick ``now`` vs request ``now`` — audit B-F9)."""
    return list(
        session.execute(
            select(BreachAction)
            .where(
                BreachAction.breach_id == breach_id,
                BreachAction.tenant_id == acting_tenant,
            )
            .order_by(BreachAction.seq.asc())
        ).scalars()
    )


def _effective_due(state: str, response_due: datetime | None) -> datetime | None:
    """The deadline IN FORCE for display: an ACCEPT deliberately clears the clock, but the
    governing ASSIGNED row still carries the old ``response_due`` — resurfacing it on a
    REVIEWED/CLOSED breach reads as a live (possibly overdue) deadline (4-finder fold). Only the
    response-pending states carry a deadline."""
    if state in (BREACH_STATE_REVIEWED, BREACH_STATE_CLOSED):
        return None
    return response_due


@dataclass(frozen=True)
class BreachQueueItem:
    """One breach-queue row: the breach + its recency-derived state + the governing epoch's owner
    and deadline (ONE governing row post-OQ-1=A — the latest ``to_state==ASSIGNED`` action carries
    both) + the parent limit's frozen-identity echo for FE grouping (OQ-API-2b-2=A)."""

    breach: Breach
    state: str
    assigned_to: str | None
    response_due: datetime | None
    scope_portfolio_id: str
    limit_code: str
    #: The breach's CURRENT timeline head — ``max(BreachAction.seq)``, or 0 when no action has been
    #: filed yet. This is exactly the ``expected_seq`` token the write verbs take (OPS-1 fold H3):
    #: without it a client had to fetch the whole action list just to learn the head, and the
    #: unconditioned ``expected_seq=None`` default is the fail-open path API-2b added it to close.
    seq: int


def breach_detail(
    session: Session, *, acting_tenant: str, breach_id: str
) -> BreachQueueItem | None:
    """One breach's queue view (state + owner + deadline + the limit echo). Per-breach queries are
    fine at single-entity scale — the batched form exists for LIST scale (D9)."""
    breach = get_breach(session, acting_tenant=acting_tenant, breach_id=breach_id)
    if breach is None:
        return None
    state = current_breach_state(session, breach.id, acting_tenant=acting_tenant)
    governing = _governing_assign(session, breach.id, acting_tenant)
    parent = session.execute(
        select(LimitDefinition).where(
            LimitDefinition.id == breach.limit_definition_id,
            LimitDefinition.tenant_id == acting_tenant,
        )
    ).scalar_one_or_none()
    if parent is None:  # orphan/cross-tenant parent — impossible via governed writes; fail as 404
        return None
    return BreachQueueItem(
        breach=breach,
        state=state,
        assigned_to=governing.assigned_to if governing is not None else None,
        response_due=_effective_due(
            state, governing.response_due if governing is not None else None
        ),
        scope_portfolio_id=parent.scope_portfolio_id,
        limit_code=parent.code,
        seq=_next_seq(session, breach.id, acting_tenant) - 1,  # the current head (0 when empty)
    )


def list_breaches(
    session: Session,
    *,
    acting_tenant: str,
    state: str | None = None,
    open_only: bool = False,
    portfolio_id: str | None = None,
    assigned_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BreachQueueItem]:
    """The batched breach-queue read — ONE statement, portable PG+SQLite (plain GROUP-BY joins;
    no ``DISTINCT ON``/window), never the ``select_overdue_breaches`` N+1 (D9).

    Recency state = the latest action's ``to_state`` per breach, OUTER-joined + coalesced to
    ``DETECTED`` so zero-action breaches surface (and a ``state=DETECTED`` filter finds them).
    Owner + deadline come from the governing epoch row (the latest ``to_state==ASSIGNED`` action —
    which post-OQ-1=A always carries the assignee). ``uq_breach_action_seq`` makes every max-seq
    join ≤1 row per breach (no fan-out). Explicit tenant predicates on EVERY table incl. inside
    the subqueries (the house rule atop RLS; SQLite has no RLS — the predicate is what tests
    prove). Ordered ``detected_at DESC, id`` (deterministic); LIMIT/OFFSET after all filters.
    """
    if state is not None and state not in BREACH_STATES:
        raise BreachLifecycleError(f"unknown breach state {state!r}")

    latest_seq = (
        select(BreachAction.breach_id, func.max(BreachAction.seq).label("max_seq"))
        .where(BreachAction.tenant_id == acting_tenant)
        .group_by(BreachAction.breach_id)
        .subquery()
    )
    latest_action = aliased(BreachAction)
    governing_seq = (
        select(BreachAction.breach_id, func.max(BreachAction.seq).label("gov_seq"))
        .where(
            BreachAction.tenant_id == acting_tenant,
            BreachAction.to_state == BREACH_STATE_ASSIGNED,
        )
        .group_by(BreachAction.breach_id)
        .subquery()
    )
    governing_action = aliased(BreachAction)
    derived_state = func.coalesce(latest_action.to_state, BREACH_STATE_DETECTED)

    stmt = (
        select(
            Breach,
            derived_state.label("state"),
            governing_action.assigned_to,
            governing_action.response_due,
            LimitDefinition.scope_portfolio_id,
            LimitDefinition.code,
            # the timeline head for the expected_seq token (0 when the breach has no actions yet)
            func.coalesce(latest_seq.c.max_seq, 0).label("seq"),
        )
        .join(
            LimitDefinition,
            and_(
                LimitDefinition.id == Breach.limit_definition_id,
                LimitDefinition.tenant_id == acting_tenant,
            ),
        )
        .outerjoin(latest_seq, latest_seq.c.breach_id == Breach.id)
        .outerjoin(
            latest_action,
            and_(
                latest_action.breach_id == latest_seq.c.breach_id,
                latest_action.seq == latest_seq.c.max_seq,
                latest_action.tenant_id == acting_tenant,
            ),
        )
        .outerjoin(governing_seq, governing_seq.c.breach_id == Breach.id)
        .outerjoin(
            governing_action,
            and_(
                governing_action.breach_id == governing_seq.c.breach_id,
                governing_action.seq == governing_seq.c.gov_seq,
                governing_action.tenant_id == acting_tenant,
            ),
        )
        .where(Breach.tenant_id == acting_tenant)
    )
    if state is not None:
        stmt = stmt.where(derived_state == state)
    if open_only:
        stmt = stmt.where(derived_state != BREACH_STATE_CLOSED)
    if portfolio_id is not None:
        stmt = stmt.where(LimitDefinition.scope_portfolio_id == portfolio_id)
    if assigned_to is not None:
        # canonical-to-canonical compare (the D1 stamp==compare discipline applied to a read).
        stmt = stmt.where(governing_action.assigned_to == _canonical_actor_id(assigned_to))
    stmt = stmt.order_by(Breach.detected_at.desc(), Breach.id).limit(limit).offset(offset)
    return [
        BreachQueueItem(
            breach=row[0],
            state=row[1],
            assigned_to=row[2],
            response_due=_effective_due(row[1], row[3]),
            scope_portfolio_id=row[4],
            limit_code=row[5],
            seq=row[6],
        )
        for row in session.execute(stmt).all()
    ]


def select_overdue_breaches(session: Session, now: datetime, *, acting_tenant: str) -> list[Breach]:
    """Candidate breaches for auto-escalation: current state ∈ {ASSIGNED, RESPONDED} AND the
    governing response deadline has passed. A read-side pre-filter only —
    ``escalate_overdue_breach`` re-checks every condition UNDER the lock, so a stale candidate is
    harmless. Ordered by ``Breach.id`` for a DETERMINISTIC cross-tick lock order (no lock-ordering
    deadlock between two concurrent same-tenant ticks — VERIFIER-F3-MED1)."""
    now_utc = _as_utc(now)
    assert now_utc is not None
    breaches = (
        session.execute(select(Breach).where(Breach.tenant_id == acting_tenant).order_by(Breach.id))
        .scalars()
        .all()
    )
    overdue: list[Breach] = []
    for breach in breaches:
        state = current_breach_state(session, breach.id, acting_tenant=acting_tenant)
        if state not in _ESCALATABLE_STATES:
            continue
        governing = _governing_assign(session, breach.id, acting_tenant)
        due = _as_utc(governing.response_due) if governing is not None else None
        if due is not None and due < now_utc:
            overdue.append(breach)
    return overdue
