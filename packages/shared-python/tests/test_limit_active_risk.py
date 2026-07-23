"""LIM-1 active-risk (tracking-error) end-to-end breach test — the SECOND metric family (S2 fold):
a governed ACTIVE_RISK run's ``te_value`` (a FRACTION, not currency) breaches a FRACTION limit,
exercising the ``(ACTIVE_RISK, TRACKING_ERROR) -> te_value`` metric-map entry, the benchmark_id
selector, and a FRACTION-unit self-describing breach.

Reuses the canonical active-risk chain from ``tests.test_active_risk`` via bare sibling imports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_active_risk import _build, _model, _seed_benchmark, _seed_upstream_runs

from irp_shared.limit.events import (
    BREACH_ABOVE,
    LIMIT_KIND_HARD,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach
from irp_shared.limit.service import create_limit, evaluate_limit
from irp_shared.portfolio.models import Portfolio
from irp_shared.risk.active_risk_service import latest_active_risk_for_portfolio

_ACTOR = LimitActor(actor_id="risk-mgr-2l", actor_type="user")


def test_a_tracking_error_limit_breaches_on_te_value(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _factor_ids = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    _build(session, tenant, mv, fx_run, cov_run, bm_id)
    portfolio = session.execute(select(Portfolio).where(Portfolio.tenant_id == tenant)).scalar_one()
    te_rows = latest_active_risk_for_portfolio(
        session, acting_tenant=tenant, portfolio_id=str(portfolio.id), benchmark_id=bm_id
    )
    te_value = Decimal(te_rows[0].te_value)
    assert te_value > 0  # the demo book has a non-zero tracking error

    limit = create_limit(
        session,
        tenant_id=tenant,
        code="te-ceiling",
        name="Tracking-error ceiling",
        target_run_type="ACTIVE_RISK",
        metric_type="TRACKING_ERROR",
        scope_portfolio_id=str(portfolio.id),
        benchmark_id=bm_id,
        threshold_value=te_value / 2,  # a FRACTION ceiling BELOW the observed TE → breach
        threshold_unit=THRESHOLD_UNIT_FRACTION,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        actor=_ACTOR,
    )
    breach = evaluate_limit(session, limit, datetime(2026, 1, 5, tzinfo=UTC))
    assert breach is not None
    assert breach.observed_value == te_value  # the te_value FRACTION, echoed exactly
    assert breach.threshold_unit == THRESHOLD_UNIT_FRACTION
    assert breach.metric_type == "TRACKING_ERROR"
    assert breach.benchmark_id == bm_id
    rows = (
        session.execute(select(Breach).where(Breach.limit_definition_id == limit.id))
        .scalars()
        .all()
    )
    assert len(rows) == 1
