"""PostgreSQL end-state test for the SCH-2 demo cadence extension (Wave-13 slice 0, stage 15).

Gated on ``IRP_TEST_DATABASE_URL``. Runs the extension ONCE (module-scoped) over the living demo
tenant and asserts that the month-end grid actually FIRED — the demo proves the cadence rather than
asserting it.

**The filename is load-bearing** (the standing stage-ordering discipline): local full-PG batteries
collect alphabetically and earlier suites pin their governed-code sets with set-equality, so each
new stage appends one more ``z``. ``stage9zzzzzz`` (six) collates after stage 14's five. In CI the
step is inserted after stage 14 and before the downgrade smoke.

This stage mints NO model code and NO validation record, so only the COMPLETED-run count moves.

**It also exists to give the downgrade smoke something to cascade** (SCH-2 verifier B3): before it,
no demo stage created a schedule at all, so migration 0053's destructive two-table leg deleted ZERO
rows in CI and went green while testing nothing. This stage deliberately LEAVES an unrepresentable
schedule (EXPOSURE ⇒ NULL ``model_version_id``) and its append-only ``scheduled_run`` child
committed, so the smoke exercises the FK cascade and the trigger/RLS sandwich for real.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoSch2AlreadySeededError,
    run_demo_sch2_stage15,
)
from irp_shared.scheduling.events import (
    CADENCE_CALENDAR_MONTH_END,
    OUTCOME_DISPATCHED,
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_SCHEDULE_CODE = "DEMO-MONTH-END-EXPOSURE"


@pytest.fixture(scope="module")
def summary():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_sch2_stage15(session)
            session.commit()
        except DemoSch2AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(summary):  # noqa: ANN001, ANN201
    factory, _ = summary
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def _schedule(db) -> Schedule:  # noqa: ANN001
    return db.execute(
        select(Schedule).where(
            Schedule.tenant_id == DEMO_TENANT_ID, Schedule.code == _SCHEDULE_CODE
        )
    ).scalar_one()


def test_the_month_end_schedule_is_seeded_model_less(db) -> None:  # noqa: ANN001
    """The row the DB CHECK admits ONLY for a model-less family — and the row that makes migration
    0053's downgrade cascade reachable in CI."""
    sched = _schedule(db)
    assert sched.target_run_type == TARGET_RUN_TYPE_EXPOSURE_AGGREGATE
    assert sched.cadence_kind == CADENCE_CALENDAR_MONTH_END
    assert sched.model_version_id is None  # model-less family
    assert sched.interval_days is None  # meaningless under a calendar grid


def test_the_tick_fired_on_the_last_weekday_at_end_of_day(db) -> None:  # noqa: ANN001
    """2026-05-31 is a SUNDAY, so the May grid point is Friday the 29th (the QS-11 `preceding`
    roll), and the instant is END of day so same-day captures are visible to the run."""
    sched = _schedule(db)
    row = db.execute(select(ScheduledRun).where(ScheduledRun.schedule_id == sched.id)).scalar_one()
    assert row.scheduled_for.date() == date(2026, 5, 29)
    assert (row.scheduled_for.hour, row.scheduled_for.minute) == (23, 59)


def test_the_fire_produced_a_completed_exposure_run(db) -> None:  # noqa: ANN001
    """End-to-end proof: the registry dispatched the EXPOSURE family, the run COMPLETED against
    marks captured ON the boundary day, and the ledger row carries its provenance.

    This is the assertion that would FAIL under a midnight tick: a mark for day T is captured
    DURING T, so at T 00:00Z `Valuation.valid_from <= valid_at` excludes it, the completeness gate
    fails, and the run is FAILED instead of COMPLETED.
    """
    sched = _schedule(db)
    row = db.execute(select(ScheduledRun).where(ScheduledRun.schedule_id == sched.id)).scalar_one()
    assert row.outcome == OUTCOME_DISPATCHED
    assert row.calculation_run_id is not None

    run = db.execute(
        select(CalculationRun).where(CalculationRun.run_id == row.calculation_run_id)
    ).scalar_one()
    assert run.run_type == "EXPOSURE_AGGREGATE"  # the family key IS the real run_type (OQ-8)
    assert run.status == "COMPLETED"
    assert run.initiated_by == f"scheduler:{sched.id}"


def test_the_var_named_resolved_columns_are_null_for_an_exposure_fire(db) -> None:  # noqa: ANN001
    """`resolved_exposure_run_id`/`resolved_covariance_run_id` are VaR-shaped. A second family
    simply leaves them NULL — the ledger stays honest rather than stuffing a placeholder."""
    sched = _schedule(db)
    row = db.execute(select(ScheduledRun).where(ScheduledRun.schedule_id == sched.id)).scalar_one()
    assert row.resolved_exposure_run_id is None
    assert row.resolved_covariance_run_id is None


def test_a_second_seed_refuses_rather_than_silently_skipping(db) -> None:  # noqa: ANN001
    with pytest.raises(DemoSch2AlreadySeededError):
        run_demo_sch2_stage15(db)


def test_the_seeded_schedule_would_not_have_fired_before_its_own_anchor(db) -> None:  # noqa: ANN001
    """The start boundary, exercised on REAL SEEDED DATA rather than a unit fixture.

    The stage seeds anchor 2026-05-11 — after April's grid point, before May's. A poll on 2026-05-12
    computes the 2026-04-30 tick, which is 11 days BEFORE the schedule existed; firing it would mint
    a governed EXPOSURE run dated before the book was configured. `is_due` is a PURE predicate, so
    probing it here writes nothing and cannot disturb the stage's end state.

    This assertion exists because the 4-finder review showed the stage's own poll (2026-06-01, after
    the grid point) satisfies the tick leg trivially — the stage demonstrated the happy path while
    its comment claimed it demonstrated the boundary.
    """
    from datetime import UTC, datetime

    from irp_shared.scheduling.service import current_tick, is_due

    sched = _schedule(db)
    mid_may = datetime(2026, 5, 12, 9, 0, tzinfo=UTC)

    tick = current_tick(sched.anchor_date, None, mid_may, cadence_kind=sched.cadence_kind)
    assert tick.date() == date(2026, 4, 30)  # April's grid point — before the anchor
    assert tick.date() < sched.anchor_date

    assert is_due(sched, mid_may, fired_ticks=set()) is False
