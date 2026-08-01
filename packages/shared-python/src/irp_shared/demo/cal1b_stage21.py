"""The CAL-1b demo stage (Wave-14 slice 3b) — the holiday-aware convention, actually exercised at
the REAL 2027-05 boundary (Memorial Day, the recorded forcing function).

**What it demonstrates, end to end.**

1. **The pause-and-recreate transition** (OQ-CAL-1-3's runbook path): the legacy
   ``CALENDAR_MONTH_END`` schedule is PAUSED — its grid never moves (the grandfather doctrine) —
   and a ``BUSINESS_MONTH_END`` successor is created alongside it. This is also load-bearing for
   the poll below: left ACTIVE, the legacy schedule would fire at 2027-05-31 EOD — Memorial Day, a
   non-trading day with no marks — burning a permanent FAILED bucket (the trap the slice retires).
2. **The holiday-aware tick**: one poll at 2027-06-01 discovers and fires the 2027-05-28 EOD tick
   (the last BUSINESS day of May 2027 — the v1 weekday grid computes the holiday itself), stamping
   ``period_key='2027-05'`` under the new month-grain idempotency key.
3. **The v2 convention move on the SHIPPED families**: ``perf.rolling_risk`` v2 and ``perf.sharpe``
   v2 are registered (new labels, assumption-literal conventions), run over the EXISTING RM-1/SR-1
   book with the HOLIDAY_CALENDAR pin, and each receives its INITIAL AWC validation (the RS-1
   new-version precedent — an unvalidated v2 would be the RM-1 4-finder defect class). The
   rolling v2 rows are asserted BYTE-IDENTICAL to v1's — the grandfather-parity proof on real demo
   data (the book's weekend-roll grid is v1-compliant, and widening cannot move it).

**The calendar is a DEMO-TENANT capture of the real XNYS dataset** (the 118 shipped dates + the
declared 2035-12-31 horizon, loaded through the governed refresh verb). A stated refinement of the
ratified "bound to the SYSTEM XNYS calendar" wording (recorded in the CAL-1 record's close): the
demo suites arm the DEMO tenant context, whose own-only ``WITH CHECK`` cannot lawfully write
SYSTEM rows — and a tenant-captured calendar exercises the hybrid override path the reference
acceptance clauses ratify, with the SYSTEM binding proven in the reference/scheduler PG suites.

Counts: +2 model VERSIONS of existing codes (the code count does NOT move), +2 INITIAL
validations, +3 COMPLETED runs (one scheduled EXPOSURE tick + the two v2 perf runs) — MEASURED on
the fresh battery by the 12-z suite, never derived.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.marketdata.models import RETURN_BASIS_TOTAL
from irp_shared.model.models import (
    VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
    VALIDATION_TYPE_INITIAL,
)
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    record_validation,
)
from irp_shared.perf.bootstrap import (
    ROLLING_RISK_WINDOWS,
    SHARPE_WINDOWS,
    register_rolling_risk_model_v2,
    register_sharpe_model_v2,
)
from irp_shared.perf.models import RollingRiskResult, SharpeRatioResult
from irp_shared.perf.rolling_service import RollingRiskActor, run_rolling_risk
from irp_shared.perf.sharpe_service import SharpeRatioActor, run_sharpe_ratio
from irp_shared.portfolio.models import Portfolio
from irp_shared.reference.calendar import HolidaySpec, create_calendar, refresh_calendar_holidays
from irp_shared.reference.models import Instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.reference.xnys_holidays import XNYS_COMPLETE_THROUGH, XNYS_HOLIDAYS
from irp_shared.scheduling.events import (
    CADENCE_BUSINESS_MONTH_END,
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun
from irp_shared.scheduling.service import create_schedule, pause_schedule
from irp_shared.snapshot.service import (
    SnapshotActor,
    build_rolling_risk_snapshot,
    build_sharpe_snapshot,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

#: The May-2027 BUSINESS grid point: Mon 2027-05-31 is Memorial Day AND the last weekday — the
#: shipped v1 grid would tick ON the holiday; the business roll lands Friday the 28th.
_BOUNDARY = date(2027, 5, 28)
_CAPTURED_AT = datetime(2027, 5, 28, 17, 30, tzinfo=UTC)
_POLL_AT = datetime(2027, 6, 1, 6, 5, tzinfo=UTC)
_ANCHOR = date(2027, 1, 1)

_LEGACY_SCHEDULE_CODE = "DEMO-MONTH-END-EXPOSURE"
_SCHEDULE_CODE = "DEMO-BUSINESS-MONTH-END"
_CALENDAR_CODE = "XNYS"
_ENVIRONMENT = "demo"
_ACTOR_ID = "demo-scheduler-admin"
_REGISTRAR = "demo-model-owner"
_VALIDATOR = "demo-validator-2l"
_CODE_VERSION = "cal-1b-demo"

#: The campaign's boundary marks, carried flat (cadence, not new economics — the sch2 convention).
_MARKS: tuple[tuple[str, str, str], ...] = (
    ("EQ-ACME-US", "148.20", "USD"),
    ("EQ-EURX-DE", "94.10", "EUR"),
    ("PE-HARBOR-IV", "10250000.00", "USD"),
)
_FX_EURUSD = "1.0865"

_TIER_MATERIALITY = "MEDIUM"
_TIER_COMPLEXITY = "LOW"
_TIER_RATIONALE = (
    "v2 of a shipped, validated convention family: the holiday-aware month-end grid changes the "
    "acceptance envelope, not the statistics — materiality inherited from v1, complexity low."
)
_INITIAL_SCOPE = (
    "INITIAL validation of the v2 holiday-aware month-end convention: the widened acceptance "
    "(calendar end / last weekday / last business day under the declared calendar), the "
    "HOLIDAY_CALENDAR snapshot pin, and grandfather parity on a v1-compliant book."
)
_INITIAL_CONDITIONS = (
    "the declared holiday calendar's coverage horizon must be maintained ahead of the measured "
    "span (an uncovered month refuses); the v1/v2 parity census in the battery is the standing "
    "regression gate; a past-dated holiday addition inside a pinned span reddens verify_snapshot "
    "by design and must be triaged as reference-data drift, not a compute defect"
)
_REPORT_REF = "10_delivery_backlog/cal_1_decision_record.md"


class DemoCal1bError(RuntimeError):
    """A CAL-1b demo-stage precondition failure."""


class DemoCal1bAlreadySeededError(DemoCal1bError):
    """The stage is already seeded — REFUSE, never silently skip (the ratified demo discipline)."""


class DemoCal1bPrereqError(DemoCal1bError):
    """An upstream stage's state is missing (this stage extends the seeded demo tenant)."""


@dataclass(frozen=True)
class Cal1bStage21Summary:
    """What the stage seeded — the suite asserts against this."""

    calendar_id: str
    schedule_id: str
    scheduled_run_id: str
    tick: datetime
    period_key: str | None
    outcome: str
    rolling_v2_version_id: str
    sharpe_v2_version_id: str
    rolling_v2_run_id: str
    sharpe_v2_run_id: str
    rolling_parity_rows: int


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


def _legacy_schedule(session: Session) -> Schedule:
    row = session.execute(
        select(Schedule).where(
            Schedule.tenant_id == DEMO_TENANT_ID,
            Schedule.code == _LEGACY_SCHEDULE_CODE,
        )
    ).scalar_one_or_none()
    if row is None:
        raise DemoCal1bPrereqError("the SCH-2 legacy schedule is not seeded (stage 15 missing)")
    return row


def _demo_portfolio_id(session: Session) -> str:
    row = session.execute(
        select(Portfolio.id).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == "DEMO-GLOBAL"
        )
    ).first()
    if row is None:
        raise DemoCal1bPrereqError("the demo campaign portfolio DEMO-GLOBAL is not seeded")
    return str(row[0])


def _instrument_ids(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(Instrument.code, Instrument.id).where(Instrument.tenant_id == DEMO_TENANT_ID)
    ).all()
    ids = {str(code): str(iid) for code, iid in rows}
    missing = [code for code, _, _ in _MARKS if code not in ids]
    if missing:
        raise DemoCal1bPrereqError(f"demo instruments not seeded: {missing}")
    return ids


def _pm1_return_run_id(session: Session) -> str:
    """The return run the SHIPPED v1 rolling rows bind — derived from RollingRiskResult, not from
    'any COMPLETED PORTFOLIO_RETURN run' (there are several in the demo tenant: PM-1's own stage
    plus RM-1's; the first battery run found exactly that with MultipleResultsFound). Using the
    v1-bound run is also what makes the grandfather-parity comparison meaningful: v2 must run
    over the SAME book v1 did."""
    rows = list(
        session.execute(
            select(RollingRiskResult.portfolio_return_run_id)
            .where(RollingRiskResult.tenant_id == DEMO_TENANT_ID)
            .distinct()
        ).scalars()
    )
    if not rows:
        raise DemoCal1bPrereqError("the RM-1 rolling rows are not seeded (stage 16 missing)")
    if len(rows) > 1:
        raise DemoCal1bPrereqError(
            f"expected ONE v1-bound return run, found {len(rows)} — the parity baseline is "
            "ambiguous; refusing"
        )
    return str(rows[0])


def _rf_benchmark_id(session: Session) -> str:
    row = session.execute(
        select(SharpeRatioResult.risk_free_benchmark_id).where(
            SharpeRatioResult.tenant_id == DEMO_TENANT_ID
        )
    ).first()
    if row is None:
        raise DemoCal1bPrereqError("the SR-1 sharpe rows are not seeded (stage 17 missing)")
    return str(row[0])


def run_demo_cal1b_stage21(session: Session) -> Cal1bStage21Summary:
    """The transition + the holiday boundary + the v2 convention move. Caller owns the commit."""
    if _already_seeded(session):
        raise DemoCal1bAlreadySeededError()

    portfolio_id = _demo_portfolio_id(session)
    ids = _instrument_ids(session)
    legacy = _legacy_schedule(session)
    return_run_id = _pm1_return_run_id(session)
    rf_benchmark_id = _rf_benchmark_id(session)

    # 1. The demo tenant CAPTURES the real XNYS dataset through the governed verbs (the hybrid
    #    tenant-override path; the 118 shipped dates + the declared horizon).
    calendar = create_calendar(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_CALENDAR_CODE,
        name="New York Stock Exchange (demo capture)",
        actor=ReferenceActor(actor_id=_ACTOR_ID),
        mic=_CALENDAR_CODE,
    )
    refresh_calendar_holidays(
        session,
        calendar,
        actor=ReferenceActor(actor_id=_ACTOR_ID),
        holidays=[HolidaySpec(holiday_date=d, name=n) for d, n in XNYS_HOLIDAYS],
        complete_through=XNYS_COMPLETE_THROUGH,
    )

    # 2. The TRANSITION (OQ-CAL-1-3): pause the legacy grid — left ACTIVE it fires 2027-05-31
    #    (Memorial Day, no marks) into a permanently burned FAILED bucket at the poll below.
    pause_schedule(session, legacy, actor=SchedulingActor(actor_id=_ACTOR_ID))

    # 3. The successor schedule under the new kind, bound to the captured calendar.
    schedule = create_schedule(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_SCHEDULE_CODE,
        name="Business month-end exposure valuation (holiday-aware)",
        target_run_type=TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
        scope_portfolio_id=portfolio_id,
        environment_id=_ENVIRONMENT,
        anchor_date=_ANCHOR,
        cadence_kind=CADENCE_BUSINESS_MONTH_END,
        calendar_id=str(calendar.id),
        actor=SchedulingActor(actor_id=_ACTOR_ID),
    )
    session.flush()

    # 4. The boundary's captured inputs — valid_from at CAPTURE TIME ON the business day (the
    #    sch2 convention; a far-past valid_from would make the EOD-tick convention untestable).
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

    # 5. ONE tick through the REAL worker path (imported in-function: the one-way fence).
    from irp_worker.scheduler import poll_tenant_schedules

    results = poll_tenant_schedules(
        session, _POLL_AT, code_version=_CODE_VERSION, acting_tenant=DEMO_TENANT_ID
    )
    if len(results) != 1:
        raise DemoCal1bError(f"expected exactly one dispatch, got {results!r}")
    _, outcome = results[0]
    run_row = session.execute(
        select(ScheduledRun).where(ScheduledRun.schedule_id == schedule.id)
    ).scalar_one()
    if run_row.scheduled_for.date() != _BOUNDARY:
        raise DemoCal1bError(
            f"the tick fired {run_row.scheduled_for} — expected the {_BOUNDARY} business roll"
        )

    # 6. The v2 convention move on the shipped families (new labels, literals, the pin), each
    #    with its INITIAL AWC (the RS-1 new-version precedent).
    rolling_v2 = register_rolling_risk_model_v2(
        session, tenant_id=DEMO_TENANT_ID, actor_id=_REGISTRAR, code_version=_CODE_VERSION
    )
    sharpe_v2 = register_sharpe_model_v2(
        session, tenant_id=DEMO_TENANT_ID, actor_id=_REGISTRAR, code_version=_CODE_VERSION
    )
    rolling_snap = build_rolling_risk_snapshot(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SnapshotActor(actor_id=_ACTOR_ID),
        portfolio_return_run_id=return_run_id,
        holiday_calendar_code=_CALENDAR_CODE,
    )
    rolling_result = run_rolling_risk(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=RollingRiskActor(actor_id=_ACTOR_ID),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT,
        model_version_id=str(rolling_v2.id),
        window_months=ROLLING_RISK_WINDOWS,
        snapshot_id=str(rolling_snap.id),
    )
    if rolling_result.status != "COMPLETED":
        raise DemoCal1bError(f"the v2 rolling run did not COMPLETE: {rolling_result.status}")
    sharpe_snap = build_sharpe_snapshot(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SnapshotActor(actor_id=_ACTOR_ID),
        portfolio_return_run_id=return_run_id,
        risk_free_benchmark_id=rf_benchmark_id,
        rf_return_basis=RETURN_BASIS_TOTAL,
        holiday_calendar_code=_CALENDAR_CODE,
    )
    sharpe_result = run_sharpe_ratio(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SharpeRatioActor(actor_id=_ACTOR_ID),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT,
        model_version_id=str(sharpe_v2.id),
        window_months=SHARPE_WINDOWS,
        snapshot_id=str(sharpe_snap.id),
    )
    if sharpe_result.status != "COMPLETED":
        raise DemoCal1bError(f"the v2 sharpe run did not COMPLETE: {sharpe_result.status}")

    # 7. GRANDFATHER PARITY on real data: the v1 book's weekend-roll grid is v1-compliant, so the
    #    v2 rows must be BYTE-IDENTICAL to the shipped v1 rows — widening cannot move a compliant
    #    number.
    def _rows(version_ids: list[str]) -> dict[tuple[str, int, date], Decimal | None]:
        rows = session.execute(
            select(RollingRiskResult).where(
                RollingRiskResult.tenant_id == DEMO_TENANT_ID,
                RollingRiskResult.model_version_id.in_(version_ids),
            )
        ).scalars()
        return {(r.metric_type, r.window_months, r.period_end): r.metric_value for r in rows}

    v1_ids = [
        str(i)
        for (i,) in session.execute(
            select(RollingRiskResult.model_version_id)
            .where(RollingRiskResult.tenant_id == DEMO_TENANT_ID)
            .distinct()
        ).all()
        if str(i) != str(rolling_v2.id)
    ]
    v1_rows = _rows(v1_ids)
    v2_rows = _rows([str(rolling_v2.id)])
    if not v2_rows or v1_rows != v2_rows:
        raise DemoCal1bError(
            f"grandfather parity FAILED: v1 has {len(v1_rows)} rows, v2 has {len(v2_rows)} — "
            "the convention move must not move a v1-compliant number"
        )

    # 8. The INITIAL AWC dossiers for both v2 versions (per-VERSION records; the tier is
    #    per-model and already assigned at RM-1/SR-1).
    for version, result_run in (
        (rolling_v2, rolling_result.run.run_id),
        (sharpe_v2, sharpe_result.run.run_id),
    ):
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ModelValidationActor(actor_id=_VALIDATOR),
            request=RecordValidationRequest(
                model_version_id=str(version.id),
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
                scope_summary=_INITIAL_SCOPE,
                conditions=_INITIAL_CONDITIONS,
                report_ref=_REPORT_REF,
                next_review_due=date(2027, 6, 1) + timedelta(days=365),
                findings=(),
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=str(result_run)
                    ),
                ),
            ),
        )

    return Cal1bStage21Summary(
        calendar_id=str(calendar.id),
        schedule_id=str(schedule.id),
        scheduled_run_id=str(run_row.id),
        tick=run_row.scheduled_for,
        period_key=run_row.period_key,
        outcome=outcome,
        rolling_v2_version_id=str(rolling_v2.id),
        sharpe_v2_version_id=str(sharpe_v2.id),
        rolling_v2_run_id=str(rolling_result.run.run_id),
        sharpe_v2_run_id=str(sharpe_result.run.run_id),
        rolling_parity_rows=len(v2_rows),
    )
