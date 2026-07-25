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
from irp_shared.entitlement.models import AppUser
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


def _seed_breach(
    session: Session,
    tenant: str,
    *,
    limit_kind: str = LIMIT_KIND_HARD,
    limit_definition_id: str | None = None,
) -> Breach:
    breach = Breach(
        tenant_id=tenant,
        limit_definition_id=limit_definition_id or str(uuid.uuid4()),
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


def _mk_assignee(session: Session, tenant: str) -> str:
    """A real ACTIVE app_user to assign to (API-2b D8: ``assigned_to`` is canonicalized + resolved
    to an ACTIVE same-tenant app_user inside ``assign_breach`` — no longer a free string)."""
    user = AppUser(tenant_id=tenant, display_name="assignee")
    session.add(user)
    session.flush()
    return user.id


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
    a1 = assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
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
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
    with pytest.raises(BreachTransitionError):  # double-assign
        assign_breach(
            session,
            breach,
            assigned_to=_mk_assignee(session, breach.tenant_id),
            actor=_MANAGER,
            now=_T0,
        )


def test_person_level_sod_all_responders_not_latest(session: Session) -> None:
    """VERIFIER B-3: a PRIOR (not just latest) 1L responder cannot review/close."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    x = BreachActor(actor_id="person-x")
    y = BreachActor(actor_id="person-y")
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
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
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
    respond_breach(session, breach, narrative="self", actor=responder, now=_T0)
    review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    with pytest.raises(BreachSodError):
        close_breach(session, breach, evidence_ref="e", actor=responder, now=_T0)


def test_human_actor_required(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    robot = BreachActor(actor_id="ai", actor_type="SYSTEM")
    with pytest.raises(BreachTransitionError):
        assign_breach(
            session,
            breach,
            assigned_to=_mk_assignee(session, breach.tenant_id),
            actor=robot,
            now=_T0,
        )


def test_evidence_and_narrative_required(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
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
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
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


def test_a_breach_on_a_since_demoted_limit_still_escalates(session: Session) -> None:
    # Wave-11 close (cross-slice anti-laundering): MG-3 demoting/suspending a limit must NOT stop an
    # ALREADY-OPEN breach's escalation clock — `select_overdue_breaches` filters on breach lifecycle
    # state, NOT the parent limit's status. Else suspend→wait would launder a missed 1L deadline.
    from irp_shared.limit.events import (
        BREACH_ABOVE,
        THRESHOLD_UNIT_CURRENCY,
        LimitActor,
    )
    from irp_shared.limit.service import approve_limit, create_limit, suspend_limit
    from irp_shared.portfolio.models import Portfolio

    tenant = str(uuid.uuid4())
    pf = Portfolio(
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        status="ACTIVE",
        record_version=1,
    )
    session.add(pf)
    session.flush()
    drafter, approver = LimitActor(actor_id="rm-2l-a"), LimitActor(actor_id="rm-2l-b")
    limit = create_limit(
        session,
        tenant_id=tenant,
        code="ceiling",
        name="ceiling",
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        scope_portfolio_id=str(pf.id),
        threshold_value=Decimal("50"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        actor=drafter,
    )
    approve_limit(session, limit, actor=approver, approval_ref="RC-1")
    breach = _seed_breach(session, tenant, limit_definition_id=limit.id)
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )  # due T0+1d (HARD)
    # The parent limit is SUSPENDED after the breach is open (the laundering attempt).
    suspend_limit(session, limit, actor=drafter)
    late = _T0 + timedelta(days=2)
    overdue = select_overdue_breaches(session, late, acting_tenant=tenant)
    assert breach.id in [b.id for b in overdue]  # still overdue despite the limit being SUSPENDED
    action = escalate_overdue_breach(session, breach, late)
    assert action is not None and action.to_state == BREACH_STATE_ESCALATED


def test_overdue_selection_and_escalation(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    # unassigned (DETECTED) is never overdue
    assert select_overdue_breaches(session, _T0 + timedelta(days=99), acting_tenant=tenant) == []
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )  # due T0+1d (HARD)
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
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
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
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
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
    action = assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
    assert action.response_due == _T0 + timedelta(days=5)  # SOFT SLA


def test_migration_chain_breach_action() -> None:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0051_breach_action"  # MG-2
    assert script.get_revision("0051_breach_action").down_revision == "0050_limit_breach"


def test_cannot_review_without_1l_response(session: Session) -> None:
    """VERIFIER-F1-HIGH1: an unresponded (escalated) breach cannot be reviewed/closed — a 2L review
    REQUIRES a prior 1L response, else a single 2L could assign→review→close with vacuous SoD."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
    # never responded → auto-escalate → still no response
    escalate_overdue_breach(session, breach, _T0 + timedelta(days=2))
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ESCALATED
    with pytest.raises(BreachTransitionError):
        review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)


def test_review_from_escalated_after_response(session: Session) -> None:
    """A breach that WAS responded then escalated (slow 2L review) can still be reviewed from
    ESCALATED — both ACCEPT (→REVIEWED→CLOSE) and REJECT (→ASSIGNED) branches."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
    respond_breach(session, breach, narrative="responded", actor=_ANALYST, now=_T0)
    # 2L review is overdue → escalate from RESPONDED
    escalate_overdue_breach(session, breach, _T0 + timedelta(days=2))
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ESCALATED
    # REJECT from ESCALATED → ASSIGNED
    review_breach(session, breach, outcome=BREACH_REVIEW_REJECT, actor=_MANAGER, now=_T0)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ASSIGNED
    # re-respond, escalate again, ACCEPT from ESCALATED → REVIEWED → CLOSE
    respond_breach(session, breach, narrative="again", actor=_ANALYST, now=_T0)
    escalate_overdue_breach(session, breach, _T0 + timedelta(days=9))
    review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_REVIEWED
    close_breach(session, breach, evidence_ref="ev://x", actor=_MANAGER, now=_T0)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_CLOSED


def test_full_reject_recovery_to_close(session: Session) -> None:
    """A rejected breach carried through re-respond → re-review(ACCEPT) → CLOSE."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, breach.tenant_id),
        actor=_MANAGER,
        now=_T0,
    )
    respond_breach(session, breach, narrative="v1", actor=_ANALYST, now=_T0)
    review_breach(session, breach, outcome=BREACH_REVIEW_REJECT, actor=_MANAGER, now=_T0)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_ASSIGNED
    respond_breach(session, breach, narrative="v2", actor=_ANALYST, now=_T0)
    review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    close_breach(session, breach, evidence_ref="ev://done", actor=_MANAGER, now=_T0)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_CLOSED


def test_audit_payload_shape_and_severity(session: Session) -> None:
    """The realized BREACH.* events carry the full DC-2 transition payload; ESCALATE is a SYSTEM
    warning; narrative is NOT leaked into the payload."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    owner = _mk_assignee(session, breach.tenant_id)
    assign_breach(session, breach, assigned_to=owner, actor=_MANAGER, now=_T0)
    respond_breach(session, breach, narrative="secret remediation detail", actor=_ANALYST, now=_T0)

    assign_evt = _events(session, tenant, BREACH_ASSIGN_EVENT)[0]
    assert assign_evt.actor_type == "user" and assign_evt.severity == "info"
    assert set(assign_evt.after_value) == {
        "breach_id",
        "seq",
        "action_type",
        "from_state",
        "to_state",
        "actor_line",
        "assigned_to",
        "response_due",
        "epoch_seq",
        "review_outcome",
        "evidence_ref",
    }
    assert assign_evt.after_value["to_state"] == BREACH_STATE_ASSIGNED
    assert assign_evt.after_value["actor_line"] == "2L"
    assert assign_evt.after_value["assigned_to"] == owner
    # narrative must NOT appear in any audit payload (free-text, potential sensitivity)
    resp_evt = _events(session, tenant, BREACH_1L_RESPONSE_EVENT)[0]
    assert "narrative" not in resp_evt.after_value

    escalate_overdue_breach(session, breach, _T0 + timedelta(days=2))
    esc_evt = _events(session, tenant, BREACH_ESCALATE_EVENT)[0]
    assert esc_evt.actor_type == "SYSTEM" and esc_evt.severity == "warning"
    assert esc_evt.after_value["epoch_seq"] == 1  # the governing ASSIGN's seq


# --- API-2b: the epoch-aware review guard (A-F1) + OQ-1=A ownership + expected_seq + D8 ------
def test_accept_cannot_ratify_a_rejected_response(session: Session) -> None:
    """THE audit A-F1 defeat, refused: assign→respond→REJECT→escalate→ACCEPT would have closed the
    breach on the exact response the 2L formally rejected, with zero fresh 1L work. The epoch-aware
    guard requires a 1L response with seq > the governing ASSIGNED-row seq — uniform on ACCEPT and
    REJECT (OQ-A2b-3=A)."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(
        session, breach, assigned_to=_mk_assignee(session, tenant), actor=_MANAGER, now=_T0
    )
    respond_breach(session, breach, narrative="v1", actor=_ANALYST, now=_T0)
    review_breach(
        session,
        breach,
        outcome=BREACH_REVIEW_REJECT,
        narrative="inadequate",
        actor=_MANAGER,
        now=_T0,
    )
    escalate_overdue_breach(session, breach, _T0 + timedelta(days=3))  # epoch-2 overdue → ESCALATED
    with pytest.raises(BreachTransitionError):  # ACCEPT of the stale (rejected) response — REFUSED
        review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    with pytest.raises(BreachTransitionError):  # uniform: re-REJECT of the stale epoch — REFUSED
        review_breach(session, breach, outcome=BREACH_REVIEW_REJECT, actor=_MANAGER, now=_T0)
    # a FRESH response re-opens the path and the review proceeds
    respond_breach(session, breach, narrative="v2", actor=_ANALYST, now=_T0)
    review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_REVIEWED


def test_reject_carries_the_owner_forward(session: Session) -> None:
    """OQ-API-2b-1=A: a REJECT re-opens the breach WITH an owner — default carry-forward of the
    prior epoch's assignee; an explicit handoff is resolved like ASSIGN; assigned_to on ACCEPT is
    refused. Pre-fix, the REJECT row's assigned_to was None → the ownership vacuum (A-F2)."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    owner = _mk_assignee(session, tenant)
    assign_breach(session, breach, assigned_to=owner, actor=_MANAGER, now=_T0)
    respond_breach(session, breach, narrative="v1", actor=_ANALYST, now=_T0)
    r1 = review_breach(
        session, breach, outcome=BREACH_REVIEW_REJECT, narrative="redo", actor=_MANAGER, now=_T0
    )
    assert r1.assigned_to == owner  # carried forward — never None
    respond_breach(session, breach, narrative="v2", actor=_ANALYST, now=_T0)
    other = _mk_assignee(session, tenant)
    r2 = review_breach(
        session,
        breach,
        outcome=BREACH_REVIEW_REJECT,
        narrative="handoff",
        actor=_MANAGER,
        now=_T0,
        assigned_to=other,
    )
    assert r2.assigned_to == other  # explicit handoff, resolved
    respond_breach(session, breach, narrative="v3", actor=_ANALYST, now=_T0)
    with pytest.raises(BreachTransitionError):  # assigned_to may only accompany a REJECT
        review_breach(
            session,
            breach,
            outcome=BREACH_REVIEW_ACCEPT,
            actor=_MANAGER,
            now=_T0,
            assigned_to=other,
        )


def test_expected_seq_precondition(session: Session) -> None:
    """OQ-API-2b-4=A: a caller passing the timeline position it acted on is refused if any action
    landed since (the cycle-class retry hole B-F3 — a retried respond after an interleaved
    ESCALATE would silently clear the alarm state). None (default) = unconditioned."""
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    assign_breach(
        session,
        breach,
        assigned_to=_mk_assignee(session, tenant),
        actor=_MANAGER,
        now=_T0,
        expected_seq=0,
    )  # fresh breach: current max seq is 0 → passes
    with pytest.raises(BreachTransitionError):  # stale: the assign advanced the timeline to 1
        respond_breach(session, breach, narrative="x", actor=_ANALYST, now=_T0, expected_seq=0)
    respond_breach(session, breach, narrative="x", actor=_ANALYST, now=_T0, expected_seq=1)
    assert current_breach_state(session, breach.id, acting_tenant=tenant) == BREACH_STATE_RESPONDED


def test_assign_resolves_and_canonicalizes_the_assignee(session: Session) -> None:
    """D8/A-F5/C-F5: assigned_to must resolve to an ACTIVE same-tenant app_user and is stamped
    CANONICAL (a non-canonical stamp would silently never match the canonical queue filter — the
    D1 stamp≠compare bug's third instance)."""
    tenant = str(uuid.uuid4())
    # garbage / blank / cross-tenant / inactive all refused
    for bad in ("not-a-user", "  "):
        breach = _seed_breach(session, tenant)
        with pytest.raises(BreachTransitionError):
            assign_breach(session, breach, assigned_to=bad, actor=_MANAGER, now=_T0)
    foreign = _mk_assignee(session, str(uuid.uuid4()))  # another tenant's user
    breach = _seed_breach(session, tenant)
    with pytest.raises(BreachTransitionError):
        assign_breach(session, breach, assigned_to=foreign, actor=_MANAGER, now=_T0)
    inactive = AppUser(tenant_id=tenant, display_name="gone", is_active=False)
    session.add(inactive)
    session.flush()
    with pytest.raises(BreachTransitionError):
        assign_breach(session, breach, assigned_to=inactive.id, actor=_MANAGER, now=_T0)
    # a case-variant form of a REAL user resolves and stamps the canonical id
    owner = _mk_assignee(session, tenant)
    action = assign_breach(session, breach, assigned_to=owner.upper(), actor=_MANAGER, now=_T0)
    assert action.assigned_to == owner  # canonical, not the presented uppercase form
