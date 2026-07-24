"""MG-2 breach remediation lifecycle — the DEP-WFL state machine over ``breach_action``.

Covers the transition table, the person-level SoD (all-responders set), recency-by-seq determinism,
the human-actor + evidence + narrative guards, and the deadline auto-escalation phase (idempotency +
recovery re-escalation). A ``breach`` row is seeded directly (SQLite: no FK/RLS enforcement) — the
lifecycle needs only a persisted breach with a ``limit_kind`` (the SLA source)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.limit.events import (
    BREACH_1L_RESPONSE_EVENT,
    BREACH_2L_REVIEW_EVENT,
    BREACH_ASSIGN_EVENT,
    BREACH_CLOSE_EVENT,
    BREACH_ESCALATE_EVENT,
    BREACH_REVIEW_ACCEPT,
    BREACH_REVIEW_REJECT,
    BREACH_STATE_ASSIGNED,
    BREACH_STATE_CLOSED,
    BREACH_STATE_DETECTED,
    BREACH_STATE_ESCALATED,
    BREACH_STATE_RESPONDED,
    BREACH_STATE_REVIEWED,
    LIMIT_KIND_HARD,
    LIMIT_KIND_SOFT,
    BreachActor,
)
from irp_shared.limit.lifecycle import (
    BreachSodError,
    BreachTransitionError,
    assign_breach,
    close_breach,
    current_breach_state,
    escalate_overdue_breach,
    respond_breach,
    review_breach,
    select_overdue_breaches,
)
from irp_shared.limit.models import Breach, BreachAction
from irp_worker.deadlines import poll_tenant_breach_deadlines  # noqa: E402

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_ANALYST = BreachActor(actor_id="analyst-1l")
_MANAGER = BreachActor(actor_id="manager-2l")


def _seed_breach(session: Session, tenant: str, *, limit_kind: str = LIMIT_KIND_HARD) -> Breach:
    breach = Breach(
        tenant_id=tenant,
        limit_definition_id=str(uuid.uuid4()),
        calculation_run_id=str(uuid.uuid4()),
        detected_at=_T0,
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        observed_value=Decimal("100"),
        threshold_value=Decimal("50"),
        threshold_unit="CURRENCY",
        breach_direction="ABOVE",
        limit_kind=limit_kind,
        severity=limit_kind,
        status="DETECTED",
    )
    session.add(breach)
    session.flush()
    return breach


def _events(session: Session, tenant: str, event_type: str) -> list[AuditEvent]:
    return list(
        session.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant, AuditEvent.event_type == event_type
            )
        ).scalars()
    )


def test_happy_path_assign_respond_review_close(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)

    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_DETECTED
    a1 = assign_breach(session, breach, assigned_to="analyst-1l", actor=_MANAGER, now=_T0)
    assert a1.seq == 1
    assert a1.from_state == BREACH_STATE_DETECTED and a1.to_state == BREACH_STATE_ASSIGNED
    assert a1.response_due == _T0 + timedelta(days=1)  # HARD SLA
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ASSIGNED

    a2 = respond_breach(session, breach, narrative="hedged the book", actor=_ANALYST, now=_T0)
    assert a2.seq == 2 and a2.to_state == BREACH_STATE_RESPONDED

    a3 = review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    assert a3.seq == 3 and a3.to_state == BREACH_STATE_REVIEWED

    a4 = close_breach(session, breach, evidence_ref="ticket://RISK-42", actor=_MANAGER, now=_T0)
    assert a4.seq == 4 and a4.to_state == BREACH_STATE_CLOSED
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_CLOSED

    # Every transition realized its BREACH.* audit code.
    for evt in (
        BREACH_ASSIGN_EVENT,
        BREACH_1L_RESPONSE_EVENT,
        BREACH_2L_REVIEW_EVENT,
        BREACH_CLOSE_EVENT,
    ):
        assert len(_events(session, tenant, evt)) == 1, evt


def test_illegal_transitions_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    with pytest.raises(BreachTransitionError):  # respond before assign
        respond_breach(session, breach, narrative="x", actor=_ANALYST, now=_T0)
    with pytest.raises(BreachTransitionError):  # close before review
        close_breach(session, breach, evidence_ref="e", actor=_MANAGER, now=_T0)
    assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
    with pytest.raises(BreachTransitionError):  # double-assign
        assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)


def test_person_level_sod_all_responders_not_latest(session: Session) -> None:
    """VERIFIER B-3: a PRIOR (not just latest) 1L responder cannot review/close."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    x = BreachActor(actor_id="person-x")
    y = BreachActor(actor_id="person-y")
    assign_breach(session, breach, assigned_to="person-x", actor=_MANAGER, now=_T0)
    respond_breach(session, breach, narrative="x responds", actor=x, now=_T0)  # X responds
    review_breach(session, breach, outcome=BREACH_REVIEW_REJECT, actor=_MANAGER, now=_T0)  # ->ASGN
    respond_breach(session, breach, narrative="y responds", actor=y, now=_T0)  # Y latest responder
    # X (a PRIOR responder, not the latest) must still be refused as reviewer.
    with pytest.raises(BreachSodError):
        review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=x, now=_T0)


def test_sod_closer_cannot_be_responder(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    responder = BreachActor(actor_id="dual-hat")
    assign_breach(session, breach, assigned_to="dual-hat", actor=_MANAGER, now=_T0)
    respond_breach(session, breach, narrative="self", actor=responder, now=_T0)
    review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    with pytest.raises(BreachSodError):
        close_breach(session, breach, evidence_ref="e", actor=responder, now=_T0)


def test_human_actor_required(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    robot = BreachActor(actor_id="ai", actor_type="SYSTEM")
    with pytest.raises(BreachTransitionError):
        assign_breach(session, breach, assigned_to="a", actor=robot, now=_T0)


def test_evidence_and_narrative_required(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
    with pytest.raises(BreachTransitionError):
        respond_breach(session, breach, narrative="   ", actor=_ANALYST, now=_T0)
    respond_breach(session, breach, narrative="ok", actor=_ANALYST, now=_T0)
    review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    with pytest.raises(BreachTransitionError):
        close_breach(session, breach, evidence_ref="", actor=_MANAGER, now=_T0)


def test_recency_is_by_seq_not_occurred_at(session: Session) -> None:
    """VERIFIER B-1: two actions with the SAME occurred_at resolve deterministically by seq."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
    respond_breach(session, breach, narrative="same instant", actor=_ANALYST, now=_T0)
    rows = list(
        session.execute(
            select(BreachAction.seq, BreachAction.to_state)
            .where(BreachAction.breach_id == breach.id)
            .order_by(BreachAction.seq)
        )
    )
    assert [r[0] for r in rows] == [1, 2]
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_RESPONDED


def test_overdue_selection_and_escalation(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    # unassigned (DETECTED) is never overdue
    assert select_overdue_breaches(session, _T0 + timedelta(days=99), acting_tenant=tenant) == []
    assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)  # due T0+1d (HARD)
    assert select_overdue_breaches(session, _T0, acting_tenant=tenant) == []  # not yet overdue
    late = _T0 + timedelta(days=2)
    overdue = select_overdue_breaches(session, late, acting_tenant=tenant)
    assert [b.id for b in overdue] == [breach.id]
    action = escalate_overdue_breach(session, breach, late)
    assert action is not None and action.to_state == BREACH_STATE_ESCALATED
    assert action.actor_line == "SYS" and action.response_due == _T0 + timedelta(days=1)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ESCALATED
    assert len(_events(session, tenant, BREACH_ESCALATE_EVENT)) == 1


def test_escalation_idempotent_no_storm(session: Session) -> None:
    """A long-overdue breach escalates ONCE per deadline epoch (the tick phase swallows dedup)."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
    late = _T0 + timedelta(days=2)
    assert poll_tenant_breach_deadlines(session, late, acting_tenant=tenant) == [breach.id]
    # recovery: 1L responds (ESCALATED -> RESPONDED); still past the SAME deadline
    respond_breach(session, breach, narrative="recovering", actor=_ANALYST, now=late)
    # a later tick re-selects it but the (breach, due) epoch is already escalated -> no storm
    second = poll_tenant_breach_deadlines(session, late + timedelta(days=1), acting_tenant=tenant)
    assert second == []
    assert len(_events(session, tenant, BREACH_ESCALATE_EVENT)) == 1


def test_reject_starts_new_epoch_reescalates(session: Session) -> None:
    """A 2L REJECT stamps a fresh deadline (a new epoch) that CAN escalate again."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
    late = _T0 + timedelta(days=2)
    assert poll_tenant_breach_deadlines(session, late, acting_tenant=tenant) == [breach.id]
    respond_breach(session, breach, narrative="r", actor=_ANALYST, now=late)
    # 2L rejects at `late` -> ASSIGNED with a FRESH due = late + 1d
    review_breach(session, breach, outcome=BREACH_REVIEW_REJECT, actor=_MANAGER, now=late)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ASSIGNED
    later = late + timedelta(days=2)  # past the NEW deadline -> a legitimate second escalation
    assert poll_tenant_breach_deadlines(session, later, acting_tenant=tenant) == [breach.id]
    assert len(_events(session, tenant, BREACH_ESCALATE_EVENT)) == 2


def test_soft_limit_gets_longer_sla(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant, limit_kind=LIMIT_KIND_SOFT)
    action = assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
    assert action.response_due == _T0 + timedelta(days=5)  # SOFT SLA
