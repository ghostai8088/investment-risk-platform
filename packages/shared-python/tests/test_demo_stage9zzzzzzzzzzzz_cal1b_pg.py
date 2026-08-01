"""PostgreSQL end-state test for the CAL-1b demo stage 21 — the holiday-aware convention live.

Gated on ``IRP_TEST_DATABASE_URL``. Runs the stage ONCE (module-scoped) over the living demo
tenant and asserts the governed end state by READING THE DATABASE, never the stage's own summary
(the PERF-0 lesson).

**The filename is load-bearing** (the standing stage-ordering discipline): TWELVE ``z`` —
verified by ``ls`` on the tests directory (lim2 = eleven), never read off a decision record.

**THE FINAL-POSITION COUNT PIN RELAYS HERE: 26/41/136 → 26/43/139** (MEASURED on a fresh-schema
battery, never derived). The two v2 mints are new VERSIONS of EXISTING codes, so the code count
does NOT move (the RS-1 precedent); +2 INITIAL validations (one per v2 version); +3 COMPLETED
runs (the scheduled BUSINESS_MONTH_END exposure tick + the v2 rolling run + the v2 sharpe run).
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_cal1b_stage21
from irp_shared.demo.cal1b_stage21 import DemoCal1bAlreadySeededError
from irp_shared.model.models import Model, ModelValidation, ModelVersion
from irp_shared.perf.models import RollingRiskResult
from irp_shared.reference.models import Calendar, CalendarHoliday
from irp_shared.scheduling.models import Schedule, ScheduledRun

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def staged():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_cal1b_stage21(session)
            session.commit()
        except DemoCal1bAlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(staged):  # noqa: ANN001, ANN201
    factory, _ = staged
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def test_the_demo_tenant_captured_the_real_xnys_dataset(db) -> None:  # noqa: ANN001
    cal = db.execute(
        select(Calendar).where(Calendar.tenant_id == DEMO_TENANT_ID, Calendar.code == "XNYS")
    ).scalar_one()
    assert cal.holidays_complete_through == date(2035, 12, 31)  # the declared horizon
    n = db.execute(
        select(func.count())
        .select_from(CalendarHoliday)
        .where(CalendarHoliday.calendar_id == cal.id)
    ).scalar_one()
    assert n == 118  # the full shipped dataset, through the governed refresh verb
    dates = set(
        db.execute(
            select(CalendarHoliday.holiday_date).where(CalendarHoliday.calendar_id == cal.id)
        ).scalars()
    )
    assert date(2027, 5, 31) in dates  # Memorial Day — the forcing function
    assert date(2027, 12, 31) not in dates  # the Rule 7.2 negative holds in the demo capture


def test_the_transition_paused_the_legacy_grid_and_the_successor_is_bound(db) -> None:  # noqa: ANN001
    legacy = db.execute(
        select(Schedule).where(
            Schedule.tenant_id == DEMO_TENANT_ID, Schedule.code == "DEMO-MONTH-END-EXPOSURE"
        )
    ).scalar_one()
    assert legacy.status == "PAUSED"  # pause-and-recreate: the legacy grid never moves
    assert legacy.calendar_id is None  # the legacy kind stays calendar-less (grandfathered)
    successor = db.execute(
        select(Schedule).where(
            Schedule.tenant_id == DEMO_TENANT_ID, Schedule.code == "DEMO-BUSINESS-MONTH-END"
        )
    ).scalar_one()
    assert successor.status == "ACTIVE"
    assert successor.cadence_kind == "BUSINESS_MONTH_END"
    assert successor.calendar_id is not None
    assert successor.interval_days is None


def test_the_tick_rolled_past_memorial_day_and_stamped_the_period_key(db) -> None:  # noqa: ANN001
    successor_id = db.execute(
        select(Schedule.id).where(
            Schedule.tenant_id == DEMO_TENANT_ID, Schedule.code == "DEMO-BUSINESS-MONTH-END"
        )
    ).scalar_one()
    row = db.execute(
        select(ScheduledRun).where(ScheduledRun.schedule_id == successor_id)
    ).scalar_one()
    assert row.scheduled_for.date() == date(2027, 5, 28)  # the BUSINESS roll, not the holiday
    assert (row.scheduled_for.hour, row.scheduled_for.minute) == (23, 59)  # end-of-day instant
    assert row.period_key == "2027-05"  # the month-grain idempotency key
    assert row.outcome == "DISPATCHED"
    assert row.calculation_run_id is not None
    run = db.execute(
        select(CalculationRun).where(CalculationRun.run_id == row.calculation_run_id)
    ).scalar_one()
    assert run.status == "COMPLETED"
    # And the legacy schedule fired NOTHING at this poll (it was paused before the boundary) —
    # its single ScheduledRun is still the SCH-2 May-2026 tick.
    legacy_id = db.execute(
        select(Schedule.id).where(
            Schedule.tenant_id == DEMO_TENANT_ID, Schedule.code == "DEMO-MONTH-END-EXPOSURE"
        )
    ).scalar_one()
    legacy_runs = list(
        db.execute(
            select(ScheduledRun.scheduled_for).where(ScheduledRun.schedule_id == legacy_id)
        ).scalars()
    )
    assert [t.date() for t in legacy_runs] == [date(2026, 5, 29)]


def test_both_v2_versions_exist_with_the_declared_literals_and_validations(db) -> None:  # noqa: ANN001
    for code in ("perf.rolling_risk", "perf.sharpe"):
        model = db.execute(
            select(Model).where(Model.tenant_id == DEMO_TENANT_ID, Model.code == code)
        ).scalar_one()
        labels = set(
            db.execute(
                select(ModelVersion.version_label).where(ModelVersion.model_id == model.id)
            ).scalars()
        )
        assert {"v1", "v2"} <= labels  # v1 grandfathered, v2 minted — same code
        v2 = db.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == model.id, ModelVersion.version_label == "v2"
            )
        ).scalar_one()
        validations = db.execute(
            select(func.count())
            .select_from(ModelValidation)
            .where(ModelValidation.model_version_id == v2.id)
        ).scalar_one()
        assert validations >= 1  # the INITIAL AWC (the RS-1 new-version precedent)


def test_grandfather_parity_v2_rows_equal_v1_rows(db) -> None:  # noqa: ANN001
    model = db.execute(
        select(Model).where(Model.tenant_id == DEMO_TENANT_ID, Model.code == "perf.rolling_risk")
    ).scalar_one()
    versions = {
        r.version_label: str(r.id)
        for r in db.execute(select(ModelVersion).where(ModelVersion.model_id == model.id)).scalars()
    }

    def _rows(version_id: str) -> dict[tuple[str, int, date], object]:
        return {
            (r.metric_type, r.window_months, r.period_end): r.metric_value
            for r in db.execute(
                select(RollingRiskResult).where(
                    RollingRiskResult.tenant_id == DEMO_TENANT_ID,
                    RollingRiskResult.model_version_id == version_id,
                )
            ).scalars()
        }

    v1_rows = _rows(versions["v1"])
    v2_rows = _rows(versions["v2"])
    assert v2_rows and v1_rows == v2_rows  # widening cannot move a v1-compliant number


def test_the_final_position_count_pin(db) -> None:  # noqa: ANN001
    """THE FINAL-POSITION PIN, relayed from the 11-z suite: 26/41/136 → **26/43/139** (MEASURED
    on the fresh battery — never derived). The code count HOLDING at 26 while two new versions
    land is itself the assertion: a convention move mints labels, not codes."""
    model_codes = db.execute(
        select(func.count(func.distinct(Model.code))).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    validations = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    completed = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert (model_codes, validations, completed) == (26, 43, 139)
