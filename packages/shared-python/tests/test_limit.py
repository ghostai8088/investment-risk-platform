"""LIM-1 limit unit tests (SQLite) — the breach predicate, the metric-selector guards, the audited
EV CRUD, the identity-frozen invariant, and the breach append-only guard."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_BELOW,
    BREACH_STATUS_DETECTED,
    LIMIT_CHANGE_EVENT,
    LIMIT_DEFINE_EVENT,
    LIMIT_KIND_HARD,
    LIMIT_STATUS_ACTIVE,
    LIMIT_STATUS_SUSPENDED,
    THRESHOLD_UNIT_CURRENCY,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.limit.service import (
    LimitError,
    _breaches,
    create_limit,
    resume_limit,
    select_active_limits,
    suspend_limit,
    update_limit,
)

_ACTOR = LimitActor(actor_id="risk-mgr-2l", actor_type="user")


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
    return create_limit(session, **kwargs)  # type: ignore[arg-type]


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
def test_create_limit_emits_define_and_sets_v1(session: Session) -> None:
    tenant = str(uuid.uuid4())
    limit = _mk(session, tenant)
    assert limit.record_version == 1
    assert limit.status == LIMIT_STATUS_ACTIVE
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
    limit = _mk(session, tenant)
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
