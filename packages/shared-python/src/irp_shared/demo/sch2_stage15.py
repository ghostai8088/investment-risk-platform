"""The SCH-2 demo CADENCE extension (Wave-13 slice 0) — the month-end grid, actually running.

EXTENDS the living demo tenant; `campaign.py` stays byte-untouched (its refuse-not-skip +
set-equality locks are ratified integrity checks, and its 9-boundary calendar is index-zipped to
hardcoded mark/FX tuples that also drive 8 covariance + 8 VaR + 8 HS runs).

**Why this stage is mandatory scope, not decoration (SCH-2 verifier B3/M9).** `create_schedule` has
ZERO non-test callers and no API router touches schedules, so without this stage nothing outside
unit tests would ever exercise the month-end grid, the EXPOSURE family, the dispatch registry, or
the new per-family CHECKs — the OPS-1 standing lesson verbatim ("a demo that cannot REACH a control
does not demonstrate it"). It also closes a second hole: the CI `alembic downgrade base` smoke runs
against a database whose only schedules are rolled back by their own suite, so migration 0053's
destructive two-table leg would delete ZERO rows and go green while testing nothing. Committing an
unrepresentable schedule (EXPOSURE ⇒ NULL `model_version_id`) plus a real `scheduled_run` child
gives that smoke something to actually cascade.

**What it seeds.** One month-end boundary the campaign's daily window does not cover, and a
`CALENDAR_MONTH_END` + `EXPOSURE_AGGREGATE` schedule over it — then it DRIVES ONE TICK through the
real worker path (`poll_tenant_schedules`), so the demo proves the grid end-to-end rather than
asserting it. The fired run is an ordinary governed `EXPOSURE_AGGREGATE` run: this stage mints NO
model code, NO validation record and NO governed number, so the 23/38/109 counts move only by the
COMPLETED runs it executes.

**The boundary date is chosen, not inherited.** 2026-05-31 is a SUNDAY, so the May grid point is
Friday 2026-05-29 — the QS-11 `preceding` roll, and a date the campaign's 05-18…05-26 window does
not reach. Marks are captured with `valid_from` at CAPTURE TIME ON THAT DAY (not the campaign's
far-past `_T0`), which is deliberate: the tick is an END-OF-DAY instant precisely so same-day
captures satisfy `Valuation.valid_from <= valid_at`, and seeding at `_T0` would make that
invisible — the fixture would pass under a midnight tick too, and the demo would prove nothing
about the convention it exists to demonstrate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.portfolio.models import Portfolio
from irp_shared.reference.models import Instrument
from irp_shared.scheduling.events import (
    CADENCE_CALENDAR_MONTH_END,
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun
from irp_shared.scheduling.service import create_schedule
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

#: The May-2026 grid point: 2026-05-31 is a SUNDAY, so the last weekday is Friday the 29th.
_BOUNDARY = date(2026, 5, 29)

#: Capture time ON the boundary day — see the module docstring. An end-of-day mark is recorded
#: during the day it prices, which is exactly why the tick is an end-of-day instant.
_CAPTURED_AT = datetime(2026, 5, 29, 17, 30, tzinfo=UTC)

#: The poll instant: the first Monday after the grid point (the supervisor discovers the tick on
#: its next cycle, not at the instant itself).
_POLL_AT = datetime(2026, 6, 1, 6, 5, tzinfo=UTC)

#: The schedule's start boundary. Deliberately MID-MONTH and BEFORE the grid point, so the stage
#: exercises the anchor semantics that the SCH-2 verifier pass found broken: a calendar grid is not
#: anchor-generated, so without the tick-vs-anchor test this would have fired April's grid point —
#: a run dated before the schedule existed.
_ANCHOR = date(2026, 5, 11)

_SCHEDULE_CODE = "DEMO-MONTH-END-EXPOSURE"
_ENVIRONMENT = "demo"
_ACTOR_ID = "demo-scheduler-admin"
_CODE_VERSION = "sch-2-demo"

#: The campaign's boundary marks, carried flat to the new boundary date (this stage demonstrates
#: CADENCE, not new economics — inventing a price move here would be fixture noise).
_MARKS: tuple[tuple[str, str, str], ...] = (
    ("EQ-ACME-US", "148.20", "USD"),
    ("EQ-EURX-DE", "94.10", "EUR"),
    ("PE-HARBOR-IV", "10250000.00", "USD"),
)
_FX_EURUSD = "1.0865"


class DemoSch2Error(RuntimeError):
    """A SCH-2 demo-stage precondition failure."""


class DemoSch2AlreadySeededError(DemoSch2Error):
    """The stage is already seeded — REFUSE, never silently skip (the ratified demo discipline)."""


class DemoSch2PrereqError(DemoSch2Error):
    """A campaign prerequisite is missing (the stage extends a seeded demo tenant)."""


@dataclass(frozen=True)
class Sch2Stage15Summary:
    """What the stage seeded — the suite asserts against this."""

    schedule_id: str
    scheduled_run_id: str
    calculation_run_id: str | None
    outcome: str
    tick: datetime


def _already_seeded(session: Session) -> bool:
    return (
        session.execute(
            select(Schedule.id).where(
                Schedule.tenant_id == DEMO_TENANT_ID,
                Schedule.code == _SCHEDULE_CODE,
            )
        ).first()
        is not None
    )


def _demo_portfolio_id(session: Session) -> str:
    row = session.execute(
        select(Portfolio.id).where(
            Portfolio.tenant_id == DEMO_TENANT_ID,
            Portfolio.code == "DEMO-GLOBAL",
        )
    ).first()
    if row is None:
        raise DemoSch2PrereqError("the demo campaign portfolio DEMO-GLOBAL is not seeded")
    return str(row[0])


def _instrument_ids(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(Instrument.code, Instrument.id).where(Instrument.tenant_id == DEMO_TENANT_ID)
    ).all()
    ids = {str(code): str(iid) for code, iid in rows}
    missing = [code for code, _, _ in _MARKS if code not in ids]
    if missing:
        raise DemoSch2PrereqError(f"demo instruments not seeded: {missing}")
    return ids


def run_demo_sch2_stage15(session: Session) -> Sch2Stage15Summary:
    """Seed the month-end boundary + schedule, then DRIVE ONE TICK.

    Caller owns the single commit.
    """
    if _already_seeded(session):
        raise DemoSch2AlreadySeededError()

    portfolio_id = _demo_portfolio_id(session)
    ids = _instrument_ids(session)

    # 1. The boundary's captured inputs. `valid_from` is CAPTURE TIME ON THE DAY — the whole point
    #    (a far-past valid_from would make the end-of-day tick convention untestable).
    for code, value, ccy in _MARKS:
        create_valuation(
            session,
            portfolio_id=portfolio_id,
            instrument_id=ids[code],
            valuation_date=_BOUNDARY,
            acting_tenant=DEMO_TENANT_ID,
            actor=ValuationActor(actor_id=_ACTOR_ID),
            mark_value=Decimal(value),
            currency_code=ccy,
            valid_from=_CAPTURED_AT,
        )
    capture_fx_rate(
        session,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=_BOUNDARY,
        rate=Decimal(_FX_EURUSD),
        acting_tenant=DEMO_TENANT_ID,
        actor=FxRateActor(actor_id=_ACTOR_ID),
        valid_from=_CAPTURED_AT,
    )

    # 2. The schedule. EXPOSURE_AGGREGATE is model-less, so `model_version_id` is OMITTED — the
    #    row the DB CHECK admits only for this family, and the row that makes migration 0053's
    #    downgrade cascade reachable in CI.
    schedule = create_schedule(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_SCHEDULE_CODE,
        name="Month-end exposure valuation",
        target_run_type=TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
        scope_portfolio_id=portfolio_id,
        environment_id=_ENVIRONMENT,
        anchor_date=_ANCHOR,
        cadence_kind=CADENCE_CALENDAR_MONTH_END,
        actor=SchedulingActor(actor_id=_ACTOR_ID),
    )
    session.flush()

    # 3. Drive ONE tick through the REAL worker path — the stage proves the grid, it does not
    #    assert it. Imported here (not at module scope) so the shared package keeps its one-way
    #    fence: `irp_shared` never imports `irp_worker` at import time.
    from irp_worker.scheduler import poll_tenant_schedules

    results = poll_tenant_schedules(
        session,
        _POLL_AT,
        code_version=_CODE_VERSION,
        acting_tenant=DEMO_TENANT_ID,
    )
    if len(results) != 1:
        raise DemoSch2Error(f"expected exactly one dispatch, got {results!r}")
    _, outcome = results[0]

    row = session.execute(
        select(ScheduledRun).where(ScheduledRun.schedule_id == schedule.id)
    ).scalar_one()
    return Sch2Stage15Summary(
        schedule_id=str(schedule.id),
        scheduled_run_id=str(row.id),
        calculation_run_id=row.calculation_run_id,
        outcome=outcome,
        tick=row.scheduled_for,
    )
