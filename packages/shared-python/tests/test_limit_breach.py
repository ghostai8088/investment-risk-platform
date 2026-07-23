"""LIM-1 end-to-end breach test (the living demo) — a governed VaR run breaches a limit, recorded
as a self-describing ``breach`` + ``BREACH.DETECT``, idempotently; a safe limit stays in appetite;
the limit-health read distinguishes the states; and the operational tick fires a scheduled VaR AND
breaches a limit against it in the SAME tick (the schedules-before-breaches ordering invariant).

Reuses the canonical VaR chain seed from ``tests.test_var`` via the bare sibling import (the CI
convention — ``from test_var``, never ``from tests.test_var``)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from datetime import date as dt_date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_var import _seed_upstream_runs, _var_model

from irp_shared.audit.models import AuditEvent
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_DETECT_EVENT,
    LIMIT_KIND_HARD,
    THRESHOLD_UNIT_CURRENCY,
    LimitActor,
)
from irp_shared.limit.models import Breach
from irp_shared.limit.service import (
    HEALTH_BREACHED,
    HEALTH_IN_APPETITE,
    HEALTH_NEVER_EVALUABLE,
    create_limit,
    evaluate_limit,
    limit_health,
)
from irp_shared.portfolio.models import Portfolio
from irp_shared.risk.events import VarActor
from irp_shared.risk.var_service import latest_var_for_portfolio, run_var
from irp_shared.scheduling.events import SchedulingActor
from irp_shared.scheduling.service import create_schedule
from irp_worker.breaches import poll_tenant_breaches  # noqa: E402
from irp_worker.scheduler import poll_tenant_schedules  # noqa: E402

_ACTOR = LimitActor(actor_id="risk-mgr-2l", actor_type="user")


def _var_ready(session: Session) -> tuple[str, str, Decimal]:
    """Build a VaR chain, run ONE governed VaR, and return (tenant, portfolio_id, var_value)."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    portfolio = session.execute(select(Portfolio).where(Portfolio.tenant_id == tenant)).scalar_one()
    var_mv = _var_model(session, tenant, confidence="0.95")
    run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=var_mv,
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
    )
    var_value = latest_var_for_portfolio(
        session, acting_tenant=tenant, portfolio_id=str(portfolio.id), metric_type="VAR_PARAMETRIC"
    )[0].var_value
    return tenant, str(portfolio.id), Decimal(var_value)


def _var_limit(session: Session, tenant: str, portfolio_id: str, threshold: Decimal, code: str):
    return create_limit(
        session,
        tenant_id=tenant,
        code=code,
        name=code,
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        scope_portfolio_id=portfolio_id,
        threshold_value=threshold,
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        actor=_ACTOR,
    )


def _breaches_of(session: Session, limit_id: str) -> list[Breach]:
    return list(
        session.execute(select(Breach).where(Breach.limit_definition_id == limit_id)).scalars()
    )


def test_a_breaching_var_records_a_self_describing_breach_idempotently(session: Session) -> None:
    tenant, portfolio_id, var_value = _var_ready(session)
    # a ceiling BELOW the VaR → breach
    limit = _var_limit(session, tenant, portfolio_id, var_value / 2, "tight-var")
    now = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)

    breach = evaluate_limit(session, limit, now)
    assert breach is not None
    assert breach.observed_value == var_value  # self-describing echo
    assert breach.threshold_value == var_value / 2
    assert breach.breach_direction == BREACH_ABOVE
    assert breach.target_run_type == "VAR"
    assert breach.metric_type == "VAR_PARAMETRIC"
    assert breach.calculation_run_id is not None
    # BREACH.DETECT emitted
    events = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == BREACH_DETECT_EVENT)
        ).scalars()
    )
    assert len(events) == 1

    # idempotent: re-evaluating the SAME latest run adds no new breach
    again = evaluate_limit(session, limit, now)
    assert again.id == breach.id
    assert len(_breaches_of(session, limit.id)) == 1


def test_a_safe_limit_stays_in_appetite(session: Session) -> None:
    tenant, portfolio_id, var_value = _var_ready(session)
    limit = _var_limit(session, tenant, portfolio_id, var_value * 10, "loose-var")
    breach = evaluate_limit(session, limit, datetime(2026, 1, 5, tzinfo=UTC))
    assert breach is None
    assert _breaches_of(session, limit.id) == []


def test_limit_health_distinguishes_the_states(session: Session) -> None:
    tenant, portfolio_id, var_value = _var_ready(session)
    tight = _var_limit(session, tenant, portfolio_id, var_value / 2, "tight")
    _var_limit(session, tenant, portfolio_id, var_value * 10, "loose")
    # a limit on a portfolio with NO VaR run → never-evaluable
    _var_limit(session, tenant, str(uuid.uuid4()), Decimal("1"), "orphan")
    now = datetime(2026, 1, 5, tzinfo=UTC)
    evaluate_limit(session, tight, now)  # record the breach
    health = {h.code: h.state for h in limit_health(session, acting_tenant=tenant)}
    assert health["tight"] == HEALTH_BREACHED
    assert health["loose"] == HEALTH_IN_APPETITE
    assert health["orphan"] == HEALTH_NEVER_EVALUABLE


def test_schedules_phase_then_breaches_phase_detects_same_tick(session: Session) -> None:
    # The headline: the schedules phase fires a FRESH VaR; the breaches phase (running SECOND, the
    # OD-G ordering invariant) detects it against the limit in the SAME tick/transaction.
    tenant, portfolio_id, var_value = _var_ready(session)
    var_mv = latest_var_for_portfolio(
        session, acting_tenant=tenant, portfolio_id=portfolio_id, metric_type="VAR_PARAMETRIC"
    )[0].model_version_id
    create_schedule(
        session,
        tenant_id=tenant,
        code="daily-var",
        name="Daily VaR",
        target_run_type="VAR",
        scope_portfolio_id=portfolio_id,
        model_version_id=var_mv,
        environment_id="ci",
        interval_days=1,
        anchor_date=dt_date(2026, 1, 1),
        actor=SchedulingActor(actor_id="analyst-1"),
    )
    limit = _var_limit(session, tenant, portfolio_id, var_value / 2, "ceiling")
    now = datetime(2026, 1, 6, 9, tzinfo=UTC)

    scheduled = poll_tenant_schedules(session, now, code_version="risk-v1", acting_tenant=tenant)
    assert len(scheduled) == 1  # phase 1: the fresh VaR fired
    breached = poll_tenant_breaches(session, now, acting_tenant=tenant)
    breached_ids = [lid for lid, bid in breached if bid is not None]
    assert limit.id in breached_ids  # phase 2: its fresh run breached the limit same tick
