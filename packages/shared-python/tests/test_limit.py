"""LIM-1 limit unit tests (SQLite) — the breach predicate, the metric-selector guards, the audited
EV CRUD, the identity-frozen invariant, and the breach append-only guard."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_STATUS_CHANGE
from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_BELOW,
    BREACH_STATUS_DETECTED,
    LIMIT_APPROVE_EVENT,
    LIMIT_CHANGE_EVENT,
    LIMIT_DEFINE_EVENT,
    LIMIT_KIND_HARD,
    LIMIT_STATUS_ACTIVE,
    LIMIT_STATUS_DRAFT,
    LIMIT_STATUS_SUSPENDED,
    THRESHOLD_UNIT_CURRENCY,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.limit.service import (
    LimitError,
    LimitSodError,
    _breaches,
    approve_limit,
    create_limit,
    resume_limit,
    select_active_limits,
    suspend_limit,
    update_limit,
)

#: The DRAFTER (maker). MG-3's person-level SoD forbids this principal from approving its own draft.
_ACTOR = LimitActor(actor_id="risk-mgr-2l", actor_type="user")
#: A DISTINCT 2L principal — the CHECKER (approver != maker, SOD-02).
_APPROVER = LimitActor(actor_id="risk-mgr-2l-b", actor_type="user")
#: A THIRD 2L principal — needed when both the author AND an editor are SoD-excluded makers.
_APPROVER2 = LimitActor(actor_id="risk-mgr-2l-c", actor_type="user")


def _portfolio(session: Session, tenant: str) -> str:
    """A real portfolio (the create_limit FK guard re-resolves scope tenant-filtered)."""
    from irp_shared.portfolio.models import Portfolio

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
    return str(pf.id)


def _mk(session: Session, tenant: str, **over: object) -> LimitDefinition:
    kwargs: dict[str, object] = {
        "tenant_id": tenant,
        "code": f"lim-{uuid.uuid4().hex[:8]}",
        "name": "VaR ceiling",
        "target_run_type": "VAR",
        "metric_type": "VAR_PARAMETRIC",
        "scope_portfolio_id": _portfolio(session, tenant),
        "threshold_value": Decimal("5000000"),
        "threshold_unit": THRESHOLD_UNIT_CURRENCY,
        "breach_direction": BREACH_ABOVE,
        "limit_kind": LIMIT_KIND_HARD,
        "actor": _ACTOR,
    }
    kwargs.update(over)
    return create_limit(session, **kwargs)  # type: ignore[arg-type]  # MG-3: born DRAFT


def _mk_active(session: Session, tenant: str, **over: object) -> LimitDefinition:
    """A DRAFT limit created by ``_ACTOR`` then APPROVED into ACTIVE by the distinct ``_APPROVER``
    (the maker-checker gate exercised through ``approve_limit``, not a status shortcut)."""
    limit = _mk(session, tenant, **over)
    return approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-2026-001")


# --- the breach predicate ---
def test_breaches_above_ceiling_strict_boundary() -> None:
    assert _breaches(Decimal("900"), Decimal("822"), BREACH_ABOVE) is True
    assert _breaches(Decimal("800"), Decimal("822"), BREACH_ABOVE) is False
    assert _breaches(Decimal("822"), Decimal("822"), BREACH_ABOVE) is False  # at-limit=ok


def test_breaches_below_floor_strict_boundary() -> None:
    assert _breaches(Decimal("0.4"), Decimal("0.5"), BREACH_BELOW) is True
    assert _breaches(Decimal("0.6"), Decimal("0.5"), BREACH_BELOW) is False
    assert _breaches(Decimal("0.5"), Decimal("0.5"), BREACH_BELOW) is False


def test_breaches_rejects_unknown_direction() -> None:
    with pytest.raises(LimitError):
        _breaches(Decimal("1"), Decimal("1"), "SIDEWAYS")


# --- CRUD + audit + validate ---
def test_create_limit_is_draft_emits_define_and_sets_v1(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    assert limit.record_version == 1
    # MG-3: a new limit is born DRAFT (not immediately ACTIVE) and is NOT evaluated until approved.
    assert limit.status == LIMIT_STATUS_DRAFT
    assert limit.created_by == _ACTOR.actor_id  # the drafter-of-record for the SoD
    assert select_active_limits(session, acting_tenant=tenant) == []
    events = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == LIMIT_DEFINE_EVENT)
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].chain_id == tenant


def test_create_rejects_unit_mismatch(session: Session) -> None:
    # A VaR metric is CURRENCY — a FRACTION threshold_unit is refused (the unit landmine guard).
    with pytest.raises(LimitError):
        _mk(session, str(uuid.uuid4()), threshold_unit=THRESHOLD_UNIT_FRACTION)


def test_create_rejects_unknown_metric_selector(session: Session) -> None:
    with pytest.raises(LimitError):
        _mk(session, str(uuid.uuid4()), target_run_type="SENSITIVITY", metric_type="DV01")


def test_active_risk_requires_a_benchmark(session: Session) -> None:
    # ACTIVE_RISK/TRACKING_ERROR is a FRACTION metric that REQUIRES a benchmark_id.
    with pytest.raises(LimitError):
        _mk(
            session,
            str(uuid.uuid4()),
            target_run_type="ACTIVE_RISK",
            metric_type="TRACKING_ERROR",
            threshold_unit=THRESHOLD_UNIT_FRACTION,
            threshold_value=Decimal("0.02"),
            benchmark_id=None,
        )
    # a VaR limit must NOT carry a benchmark_id
    with pytest.raises(LimitError):
        _mk(session, str(uuid.uuid4()), benchmark_id=str(uuid.uuid4()))


def test_create_rejects_non_positive_threshold(session: Session) -> None:
    with pytest.raises(LimitError):
        _mk(session, str(uuid.uuid4()), threshold_value=Decimal("0"))


def test_update_changes_threshold_and_bumps_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    update_limit(session, limit, actor=_ACTOR, threshold_value=Decimal("6000000"))
    assert limit.threshold_value == Decimal("6000000")
    assert limit.record_version == 2
    changes = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == LIMIT_CHANGE_EVENT)
        ).scalars()
    )
    assert len(changes) == 1


def test_update_rejects_frozen_identity_attribute(session: Session) -> None:
    # target_run_type / metric_type / scope / benchmark / threshold_unit are FROZEN (OD-I).
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    with pytest.raises(LimitError):
        update_limit(session, limit, actor=_ACTOR, metric_type="VAR_HISTORICAL")
    with pytest.raises(LimitError):
        update_limit(session, limit, actor=_ACTOR, scope_portfolio_id=str(uuid.uuid4()))


def test_suspend_then_resume(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)
    suspend_limit(session, limit, actor=_ACTOR)
    assert limit.status == LIMIT_STATUS_SUSPENDED
    assert select_active_limits(session, acting_tenant=tenant) == []
    resume_limit(session, limit, actor=_ACTOR)
    assert limit.status == LIMIT_STATUS_ACTIVE
    assert len(select_active_limits(session, acting_tenant=tenant)) == 1


# --- breach append-only guard ---
def test_breach_is_append_only(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    breach = Breach(
        tenant_id=tenant,
        limit_definition_id=limit.id,
        calculation_run_id=str(uuid.uuid4()),
        detected_at=datetime(2026, 1, 5, tzinfo=UTC),
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        benchmark_id=None,
        observed_value=Decimal("900"),
        threshold_value=Decimal("822"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        severity=LIMIT_KIND_HARD,
        status=BREACH_STATUS_DETECTED,
    )
    session.add(breach)
    session.flush()
    breach.status = "CLOSED"
    with pytest.raises(AppendOnlyViolation):
        session.flush()


# --- the 4-finder coverage folds ---
def test_create_refuses_a_foreign_portfolio(session: Session) -> None:
    # D1: the P3-5 FK guard — a scope_portfolio_id from ANOTHER tenant is refused (PG FK checks
    # bypass RLS, so create_limit re-resolves the target tenant-filtered).
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_pf = _portfolio(session, tenant_b)
    with pytest.raises(LimitError):
        create_limit(
            session,
            tenant_id=tenant_a,
            code="foreign",
            name="foreign",
            target_run_type="VAR",
            metric_type="VAR_PARAMETRIC",
            scope_portfolio_id=foreign_pf,
            threshold_value=Decimal("1000000"),
            threshold_unit=THRESHOLD_UNIT_CURRENCY,
            breach_direction=BREACH_ABOVE,
            limit_kind=LIMIT_KIND_HARD,
            actor=_ACTOR,
        )


def test_create_refuses_a_duplicate_code(session: Session) -> None:
    tenant = str(uuid.uuid4())
    pf = _portfolio(session, tenant)
    kw = dict(
        tenant_id=tenant,
        code="dup",
        name="dup",
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        scope_portfolio_id=pf,
        threshold_value=Decimal("1000000"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        actor=_ACTOR,
    )
    create_limit(session, **kw)  # type: ignore[arg-type]
    with pytest.raises(LimitError):
        create_limit(session, **kw)  # type: ignore[arg-type]  # same (tenant, code) -> clean error


def test_update_change_event_payload_serializes_the_threshold(session: Session) -> None:
    # S4: the LIMIT.CHANGE before/after must carry the OLD/NEW threshold as JSON-safe strings.
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)  # threshold 5000000
    update_limit(session, limit, actor=_ACTOR, threshold_value=Decimal("6000000"))
    event = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == LIMIT_CHANGE_EVENT)
    ).scalar_one()
    assert event.before_value["threshold_value"] == "5000000"
    assert event.after_value["threshold_value"] == "6000000"


# --- MG-3: the LIMIT.APPROVE maker-checker gate -----------------------------------------------
def test_approve_activates_a_draft_and_emits_the_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    assert select_active_limits(session, acting_tenant=tenant) == []  # DRAFT is not evaluated
    approved = approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-2026-007")
    assert approved.status == LIMIT_STATUS_ACTIVE
    assert approved.record_version == 2  # create (v1) -> approve (v2)
    assert len(select_active_limits(session, acting_tenant=tenant)) == 1  # now evaluated
    event = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == LIMIT_APPROVE_EVENT)
    ).scalar_one()
    assert event.action == ACTION_STATUS_CHANGE
    assert event.approval_ref == "RC-2026-007"
    assert event.after_value["approved_by"] == _APPROVER.actor_id
    assert event.after_value["checked_makers"] == [_ACTOR.actor_id]  # the maker SoD was checked vs
    assert event.before_value["status"] == LIMIT_STATUS_DRAFT


def test_approve_refuses_the_drafter_self_approving(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)  # drafted by _ACTOR
    with pytest.raises(LimitSodError):
        approve_limit(
            session, limit, actor=_ACTOR, approval_ref="RC-1"
        )  # maker == checker (SOD-02)


def test_approve_requires_a_human_actor(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    ai = LimitActor(actor_id="agent-x", actor_type="ai")
    with pytest.raises(LimitError):  # BR-15: AI never approves
        approve_limit(session, limit, actor=ai, approval_ref="RC-1")


def test_approve_requires_a_non_empty_approval_ref(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    with pytest.raises(LimitError):
        approve_limit(session, limit, actor=_APPROVER, approval_ref="   ")


def test_approve_refuses_a_non_draft_limit(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)  # already ACTIVE
    with pytest.raises(LimitError):  # re-approve of ACTIVE refused (idempotency / from-state)
        approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-2")


def test_approve_refuses_a_draft_with_no_maker(session: Session) -> None:
    # A DRAFT with no recorded maker cannot establish SoD -> vacuous-SoD refusal (MG-2 precedent).
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    limit.created_by = None
    limit.updated_by = None
    session.flush()
    with pytest.raises(LimitSodError):
        approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-3")


def test_update_cannot_activate_a_draft(session: Session) -> None:
    # The create-side twin's edit-path sibling: update_limit must not flip DRAFT->ACTIVE (bypass).
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    with pytest.raises(LimitError):
        update_limit(session, limit, actor=_APPROVER, status=LIMIT_STATUS_ACTIVE)


def test_update_cannot_set_draft(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)
    with pytest.raises(LimitError):
        update_limit(session, limit, actor=_ACTOR, status=LIMIT_STATUS_DRAFT)


def test_material_change_to_an_active_limit_demotes_to_draft(session: Session) -> None:
    # REQ-LIM-001 (OQ-MG-3-5=A): loosening a LIVE limit re-enters the maker-checker gate.
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)  # drafted by _ACTOR, approved by _APPROVER
    update_limit(session, limit, actor=_ACTOR, threshold_value=Decimal("9000000"))
    assert limit.status == LIMIT_STATUS_DRAFT  # auto-demoted, not evaluated
    assert limit.updated_by == _ACTOR.actor_id  # the editor is the new maker
    assert select_active_limits(session, acting_tenant=tenant) == []
    # the editor cannot self-re-approve; a DISTINCT principal must sign off
    with pytest.raises(LimitSodError):
        approve_limit(session, limit, actor=_ACTOR, approval_ref="RC-4")
    approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-5")
    assert limit.status == LIMIT_STATUS_ACTIVE


def test_both_the_author_and_the_editor_are_sod_excluded(session: Session) -> None:
    # The maker SET is {created_by, updated_by}: neither the original author (A) nor a later editor
    # (B) may approve — else A could self-approve a draft B merely touched (SOD-02). Only a THIRD
    # principal (C) can sign off.
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)  # authored by _ACTOR (A)
    update_limit(session, limit, actor=_APPROVER, threshold_value=Decimal("7000000"))  # edited by B
    assert limit.status == LIMIT_STATUS_DRAFT
    assert limit.updated_by == _APPROVER.actor_id
    with pytest.raises(LimitSodError):  # B edited it
        approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-6")
    with pytest.raises(LimitSodError):  # A authored it
        approve_limit(session, limit, actor=_ACTOR, approval_ref="RC-7")
    approve_limit(session, limit, actor=_APPROVER2, approval_ref="RC-8")  # C is neither
    assert limit.status == LIMIT_STATUS_ACTIVE


def test_noop_governing_resave_does_not_demote_an_active_limit(session: Session) -> None:
    # Presence of a governing field in the edit is not enough — only an ACTUAL value change demotes.
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)  # threshold 5000000
    update_limit(session, limit, actor=_ACTOR, threshold_value=Decimal("5000000"))  # same value
    assert limit.status == LIMIT_STATUS_ACTIVE  # unchanged -> stays live, no re-approval churn
    assert len(select_active_limits(session, acting_tenant=tenant)) == 1


def test_update_refuses_combining_status_with_a_governing_change(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)
    with pytest.raises(LimitError):  # ambiguous: a config change may not ride a suspend/resume
        update_limit(
            session,
            limit,
            actor=_ACTOR,
            status=LIMIT_STATUS_SUSPENDED,
            threshold_value=Decimal("9000000"),
        )


def test_suspend_edit_resume_cannot_launder_an_unapproved_change(session: Session) -> None:
    # The bypass 3 finders flagged: a governing edit while SUSPENDED must ALSO demote to DRAFT, so
    # resume cannot relaunch a loosened threshold without a non-maker sign-off (REQ-LIM-001).
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)  # authored A, approved B
    suspend_limit(session, limit, actor=_ACTOR)
    assert limit.status == LIMIT_STATUS_SUSPENDED
    update_limit(session, limit, actor=_ACTOR, threshold_value=Decimal("50000000"))  # loosen
    assert limit.status == LIMIT_STATUS_DRAFT  # demoted, NOT left SUSPENDED
    with pytest.raises(LimitError):  # resume cannot activate a DRAFT (would bypass approval)
        resume_limit(session, limit, actor=_ACTOR)
    approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-9")  # a non-maker must sign off
    assert limit.status == LIMIT_STATUS_ACTIVE


def test_suspend_and_resume_on_a_draft_are_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)  # DRAFT
    with pytest.raises(LimitError):
        suspend_limit(session, limit, actor=_ACTOR)
    with pytest.raises(LimitError):
        resume_limit(session, limit, actor=_ACTOR)


def test_actor_id_canonicalization_closes_case_variance_self_approval(session: Session) -> None:
    # API-2 D1 / verifier F1: the person-level SoD compares actor ids; if one principal presents
    # a different string-form of their UUID at create vs approve, an un-canonicalized compare would
    # let them self-approve (PG-specific — uuid compares case-insensitively there). The LimitActor
    # canonicalizes UUID-shaped ids at construction, so stamp == compare regardless of case.
    tenant = str(uuid.uuid4())
    raw = uuid.uuid4()
    upper = LimitActor(actor_id=str(raw).upper())  # maker, uppercase form
    lower = LimitActor(actor_id=str(raw).lower())  # same human, lowercase form
    assert upper.actor_id == lower.actor_id == str(raw)  # canonicalized to one form
    limit = _mk(session, tenant, actor=upper)
    assert limit.created_by == str(raw)  # stamped canonical
    with pytest.raises(LimitSodError):  # the lowercase form is recognized as the same maker
        approve_limit(session, limit, actor=lower, approval_ref="RC-1")


def test_non_uuid_actor_id_passes_through_unchanged() -> None:
    # A synthesized tick SYSTEM actor / a test fixture id is not UUID-shaped and must pass through
    # (canonicalization is lenient, so nothing breaks).
    assert LimitActor(actor_id="limit-eval:abc").actor_id == "limit-eval:abc"
    assert LimitActor(actor_id="risk-mgr-2l").actor_id == "risk-mgr-2l"


def test_cosmetic_name_change_does_not_demote_an_active_limit(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk_active(session, tenant)
    update_limit(session, limit, actor=_ACTOR, name="renamed ceiling")
    assert limit.status == LIMIT_STATUS_ACTIVE  # name is cosmetic — no re-approval
    assert len(select_active_limits(session, acting_tenant=tenant)) == 1
