"""SCH-1 end-to-end dispatch test (the living demo) — a schedule fires the flagship VaR on a
simulated cadence, producing a COMPLETED governed VaR run + a scheduled_run ledger row per tick,
idempotent within an interval, and re-pinning FRESH each interval (no backfill).

Reuses the canonical VaR upstream-chain seed from ``tests.test_var`` (factor-exposure + covariance
runs + a registered ``risk.var.parametric`` model) — the same prelude every VaR test builds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from datetime import date as dt_date

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_var import _seed_upstream_runs, _var_model

from irp_shared.calc.models import CalculationRun
from irp_shared.portfolio.models import Portfolio
from irp_shared.scheduling.events import (
    OUTCOME_DISPATCHED,
    SchedulingActor,
)
from irp_shared.scheduling.models import ScheduledRun
from irp_shared.scheduling.service import create_schedule
from irp_worker.scheduler import poll_tenant_schedules  # noqa: E402  (app import after shared)

_ACTOR = SchedulingActor(actor_id="analyst-1", actor_type="user")


def _var_ready_tenant(session: Session) -> tuple[str, str, str]:
    """A tenant with a COMPLETED factor-exposure + covariance run and a registered VaR model."""
    tenant = str(uuid.uuid4())
    _seed_upstream_runs(session, tenant)  # creates the portfolio + fx/cov runs internally
    portfolio = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == tenant)
    ).scalar_one()
    var_mv = _var_model(session, tenant, confidence="0.95")
    return tenant, str(portfolio.id), var_mv


def _ledger(session: Session, schedule_id: str) -> list[ScheduledRun]:
    return list(
        session.execute(
            select(ScheduledRun).where(ScheduledRun.schedule_id == schedule_id)
        ).scalars()
    )


def _naive(value: datetime) -> datetime:
    """Strip tzinfo — SQLite reads DateTime back tz-naive (the column is tz-aware on PG)."""
    return value.replace(tzinfo=None)


def test_scheduler_fires_var_on_a_simulated_daily_cadence(session: Session) -> None:
    tenant, portfolio_id, var_mv = _var_ready_tenant(session)
    sched = create_schedule(
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
        actor=_ACTOR,
    )

    # --- tick 1: a genuine as-of-now fresh VaR is produced + linked ---
    fired = poll_tenant_schedules(
        session, datetime(2026, 1, 5, 9, 0, tzinfo=UTC), code_version="risk-v1"
    )
    assert fired == [(sched.id, OUTCOME_DISPATCHED)]
    rows = _ledger(session, sched.id)
    assert len(rows) == 1
    row = rows[0]
    assert _naive(row.scheduled_for) == datetime(2026, 1, 5)  # current grid tick (1-day)
    assert row.calculation_run_id is not None
    assert row.resolved_exposure_run_id is not None
    assert row.resolved_covariance_run_id is not None
    run = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == row.calculation_run_id)
    ).scalar_one()
    assert run is not None
    assert run.run_type == "VAR"
    assert run.status == "COMPLETED"
    assert run.initiated_by == f"scheduler:{sched.id}"

    # --- idempotency: re-poll within the SAME interval fires nothing ---
    again = poll_tenant_schedules(
        session, datetime(2026, 1, 5, 18, 0, tzinfo=UTC), code_version="risk-v1"
    )
    assert again == []
    assert len(_ledger(session, sched.id)) == 1

    # --- next interval: a SECOND fire (fresh re-pin, a NEW governed run) ---
    nxt = poll_tenant_schedules(
        session, datetime(2026, 1, 6, 9, 0, tzinfo=UTC), code_version="risk-v1"
    )
    assert nxt == [(sched.id, OUTCOME_DISPATCHED)]
    rows_after = _ledger(session, sched.id)
    assert len(rows_after) == 2
    assert sorted(_naive(r.scheduled_for) for r in rows_after) == [
        datetime(2026, 1, 5),
        datetime(2026, 1, 6),
    ]
    # two DISTINCT governed runs (each interval re-pins fresh)
    run_ids = {r.calculation_run_id for r in rows_after}
    assert len(run_ids) == 2


def test_scheduler_overdue_fires_exactly_one_tick(session: Session) -> None:
    tenant, portfolio_id, var_mv = _var_ready_tenant(session)
    sched = create_schedule(
        session,
        tenant_id=tenant,
        code="weekly-var",
        name="Weekly VaR",
        target_run_type="VAR",
        scope_portfolio_id=portfolio_id,
        model_version_id=var_mv,
        environment_id="ci",
        interval_days=7,
        anchor_date=dt_date(2026, 1, 1),
        actor=_ACTOR,
    )
    # ~12 weeks overdue → exactly ONE fire (no backfill of the missed weeks)
    fired = poll_tenant_schedules(
        session, datetime(2026, 3, 30, 9, 0, tzinfo=UTC), code_version="risk-v1"
    )
    assert fired == [(sched.id, OUTCOME_DISPATCHED)]
    assert len(_ledger(session, sched.id)) == 1
