"""Scheduling service (SCH-1) — cadence math + due-selection + dispatch + audited schedule CRUD.

Two clean layers:

- **Pure cadence functions** (``current_tick`` / ``is_due``) — deterministic functions of
  ``(anchor, interval, cadence, now)`` and the already-fired tick set. They read NO wall clock
  (INV-SCH-1: ``scheduled_for`` is the computed ``current_tick`` grid value, never ``now``), so the
  whole scheduler is testable with an injected ``now`` — no clock abstraction (none exists in the
  repo; ``utcnow()`` is the only time source and reproducibility is the snapshot pin, AD-014).
- **DB layer** (``select_active_due`` / ``dispatch_one`` / schedule CRUD) — all tenant-scoped
  NON-BYPASSRLS (OQ-SCH-1-1=B). ``dispatch_one`` NEVER backfills: it fires the ONE current grid tick
  and leaves missed grid points as honest ledger gaps (OD-SCH-1-F, which folds the two blocking
  verifier defects — the fraudulent-backfill series + the pause/resume storm).

**SCH-2 (Wave-13 slice 0)** retired SCH-1's "v1 = INTERVAL cadence, VAR family, ``run_var`` binder":
the grid is now cadence-dispatched (``INTERVAL`` | ``CALENDAR_MONTH_END``) and the family is
dispatched through ``FAMILY_REGISTRY``, the SINGLE source for what is schedulable and for which
families require a ``model_version``. Reads live in the sibling ``queries.py`` — deliberately NOT
here, because this module imports the risk + exposure compute stack and a read must not drag it in.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import date as dt_date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.service import record_event
from irp_shared.calmath import NO_HOLIDAYS, last_business_day_of_month
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure.events import ExposureActor
from irp_shared.exposure.service import ExposureRunResult, run_exposure
from irp_shared.model.guards import assert_model_version_in_tenant
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.reference.models import Calendar, CalendarHoliday  # models-only (guards precedent)
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION
from irp_shared.reproduction.service import run_reproduction_sweep
from irp_shared.risk.covariance_service import latest_covariances
from irp_shared.risk.events import VarActor
from irp_shared.risk.factor_service import latest_factor_exposure
from irp_shared.risk.var_service import VarRunResult, run_var
from irp_shared.scheduling.events import (
    CADENCE_BUSINESS_MONTH_END,
    CADENCE_CALENDAR_MONTH_END,
    CADENCE_INTERVAL,
    CADENCE_KINDS,
    OUTCOME_DISPATCHED,
    OUTCOME_FAILED,
    SCHEDULE_CREATE_EVENT,
    SCHEDULE_STATUS_ACTIVE,
    SCHEDULE_STATUS_PAUSED,
    SCHEDULE_STATUSES,
    SCHEDULE_UPDATE_EVENT,
    SOURCE_MODULE_SCHEDULING,
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
    TARGET_RUN_TYPE_VAR,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun

_log = logging.getLogger(__name__)

#: The audit ``entity_type`` for a schedule head.
ENTITY_SCHEDULE = "schedule"

#: In-place editable head attributes (config edits — the ``scenario_definition`` EV precedent).
#: v1 allows ONLY name + status (pause/resume); a re-cadence (interval/anchor) or a redefinition
#: (scope/model/environment) is a NEW schedule — this keeps the grid fixed for a schedule's life
#: and sidesteps the re-cadence grid-shift seam (recorded v2).
_UPDATABLE = ("name", "status")


#: Runaway ceiling on ``interval_days`` — an ENVELOPE, not a business rule (the CC-2 pattern: a
#: ceiling plus an envelope BELOW the column capacity). 36,525 days is a century; no real cadence
#: approaches it. Why it must exist at all (SCH-2 4-finder review, grid lens): the column is a
#: 32-bit ``Integer`` (max 2,147,483,647) but ``timedelta`` caps at 999,999,999 days, so every value
#: in between made ``current_tick`` raise **OverflowError** — which is NOT a ``ScheduleError``, so
#: it escaped ``select_active_due``'s skip-and-report, escaped the worker's ``for`` header (outside
#: the per-schedule SAVEPOINT), and aborted all four tick phases for the tenant every cycle. That is
#: precisely the failure class the ratified B3 fold exists to prevent, reached by a different door.
#: Enforced in THREE places, like every other per-family rule here: this bound in
#: ``_validate_config``, the DB CHECK ``ck_schedule_interval_days_by_cadence``, and a defensive
#: ``OverflowError`` catch in ``current_tick`` for any row that predates or bypasses both.
MAX_INTERVAL_DAYS = 36_525


class ScheduleError(ValueError):
    """A schedule config or dispatch precondition failure (fail-closed)."""


# --------------------------------------------------------------------------- pure cadence math ---
def _anchor_dt(anchor_date: dt_date) -> datetime:
    """The anchor grid origin as a UTC-midnight instant."""
    return datetime(anchor_date.year, anchor_date.month, anchor_date.day, tzinfo=UTC)


def _require_aware(now: datetime) -> None:
    """Fail closed (a clean ``ScheduleError``) if ``now`` is tz-naive — the module requires a
    tz-aware UTC instant (the grid anchor is UTC-aware; a naive ``now`` would raise a raw
    ``TypeError`` from the wrong layer). The worker sources ``now`` from ``utcnow()`` (tz-aware)."""
    if now.tzinfo is None:
        raise ScheduleError("now must be tz-aware (UTC)")


def _last_weekday_of_month(year: int, month: int) -> dt_date:
    """The last Mon–Fri date of a calendar month — the QS-11 ``preceding`` roll over a WEEKEND-ONLY
    non-business-day predicate (SCH-2, OD-SCH-2-C; the ``CALENDAR_MONTH_END`` grandfather).

    CAL-1b re-homed the arithmetic onto the pure leaf ``irp_shared.calmath`` (OQ-CAL-1-7) — the
    RM-1-era hand-mirror in ``perf.rolling_kernel`` and its conformance pin dissolved with it.
    Equal by construction to ``last_business_day_of_month(year, month, NO_HOLIDAYS)``."""
    return last_business_day_of_month(year, month, NO_HOLIDAYS)


def _month_end_tick_at_or_before(
    now: datetime, holidays: frozenset[dt_date] = NO_HOLIDAYS
) -> datetime:
    """The most recent CALENDAR_MONTH_END grid point ``<= now``, as an END-OF-DAY instant.

    **The instant is end-of-day, and that is load-bearing** (OD-SCH-2-C): the tick becomes the
    EXPOSURE run's ``as_of_valid_at`` (OD-SCH-2-E), which is a BITEMPORAL CUTOFF, not a label —
    it reaches ``Valuation.valid_from <= valid_at``. An end-of-day mark for day ``T`` is captured
    DURING/AFTER ``T``, so at ``T 00:00Z`` it is not yet visible and the run would fail its
    completeness gate EVERY month. At end-of-day ``valid_from <= tick`` holds for any same-day
    capture, ``tick.date()`` is still ``T`` (so RM-1's month-alignment is satisfied), and trades
    booked on ``T`` are included.
    """
    candidate = _end_of_day(last_business_day_of_month(now.year, now.month, holidays))
    if candidate <= now:
        return candidate
    # Still before this month's grid point — roll back to the previous month.
    year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    return _end_of_day(last_business_day_of_month(year, month, holidays))


def _end_of_day(day: dt_date) -> datetime:
    """The last representable microsecond of ``day`` in UTC."""
    return datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=UTC)


def current_tick(
    anchor_date: dt_date,
    interval_days: int | None,
    now: datetime,
    *,
    cadence_kind: str = CADENCE_INTERVAL,
    holidays: frozenset[dt_date] | None = None,
) -> datetime:
    """The most recent grid point at or before ``now`` (INV-SCH-1 — a PURE grid value).

    Three cadences (SCH-2 + CAL-1b): ``INTERVAL`` = ``anchor_midnight_utc + k·interval_days``,
    clamped to the anchor; ``CALENDAR_MONTH_END`` = the end of the last WEEKDAY of the calendar
    month (the grandfathered v1 grid — it never consults holidays); ``BUSINESS_MONTH_END`` = the
    end of the last BUSINESS day under the caller-resolved ``holidays`` set. Depends ONLY on
    ``(anchor, interval, cadence, now, holidays)`` — the holiday set is a PASSED-IN frozenset
    resolved once per poll cycle by the caller (OQ-CAL-1-5), NEVER a ledger/DB read here — so two
    polls holding the same inputs compute the identical bucket; the cross-refresh race is closed at
    the DB by the period key, not here.

    **Fails CLOSED on an unresolvable cadence** (SCH-2, verifier B3). This function runs on the POLL
    path, and ``select_active_due`` is evaluated in the worker's ``for`` header — OUTSIDE the
    per-schedule SAVEPOINT — so a raw ``TypeError`` here (e.g. a NULL ``interval_days`` reaching the
    INTERVAL branch after a rollback) would escape ``poll_tenant_schedules`` and abort ALL FOUR tick
    phases for the tenant. Every exit from here is a clean ``ScheduleError``.
    """
    _require_aware(now)
    now = now.astimezone(UTC)  # the month-end branch reads calendar fields; normalize explicitly
    if cadence_kind == CADENCE_CALENDAR_MONTH_END:
        return _month_end_tick_at_or_before(now)  # grandfathered: NEVER holiday-aware
    if cadence_kind == CADENCE_BUSINESS_MONTH_END:
        if holidays is None:
            # Fail-closed (the LIM-1 standard, OQ-CAL-1-4): a holiday-blind tick would be silently
            # indistinguishable from the legacy kind — refuse, never degrade to weekday-only.
            raise ScheduleError(
                "BUSINESS_MONTH_END requires a resolved holiday set — refusing a holiday-blind tick"
            )
        try:
            return _month_end_tick_at_or_before(now, holidays)
        except ValueError as exc:
            # calmath's exhausted-month floor raises a RAW ValueError; unconverted it escapes the
            # poll loop's ScheduleError-only skip-and-report and aborts ALL FOUR tick phases for
            # the tenant (the OverflowError/B3 class, re-entered through the holiday door — the
            # CAL-1b review's HIGH). Every exit from here must be a clean ScheduleError.
            raise ScheduleError(
                f"the resolved holiday set is corrupt for this grid: {exc}"
            ) from exc
    if cadence_kind != CADENCE_INTERVAL:
        raise ScheduleError(f"unknown cadence_kind {cadence_kind!r} — cannot compute a grid tick")
    if interval_days is None:
        raise ScheduleError("interval_days is required for the INTERVAL cadence")
    if interval_days <= 0:
        raise ScheduleError("interval_days must be positive")
    anchor = _anchor_dt(anchor_date)
    try:
        step = timedelta(days=interval_days)
        k = (now - anchor) // step
        if k < 0:
            k = 0
        return anchor + k * step
    except OverflowError as exc:
        # The LAST of the three layers guarding MAX_INTERVAL_DAYS, and the only one that protects a
        # row already in the table. Without it an OverflowError is not a ScheduleError, so it
        # escapes the caller's skip-and-report and takes the whole tenant's tick cycle down.
        raise ScheduleError(
            f"interval_days {interval_days} overflows the grid arithmetic — "
            f"the ceiling is {MAX_INTERVAL_DAYS}"
        ) from exc


def _schedule_tick(
    schedule: Schedule, now: datetime, holidays: frozenset[dt_date] | None = None
) -> datetime:
    """``current_tick`` for a schedule row (its cadence, interval and anchor).

    ``holidays`` is required (non-None) for a ``BUSINESS_MONTH_END`` row — ``current_tick``
    refuses fail-closed otherwise — and ignored by the legacy kinds."""
    return current_tick(
        schedule.anchor_date,
        schedule.interval_days,
        now,
        cadence_kind=schedule.cadence_kind,
        holidays=holidays,
    )


def _outside_start_boundary(schedule: Schedule, tick: datetime, now: datetime) -> bool:
    """Is this (tick, now) pair outside the schedule's start boundary? BOTH legs are load-bearing.

    **(a) ``tick >= anchor`` — the leg SCH-2 ADDS.** Under INTERVAL this held STRUCTURALLY, from
    ``current_tick``'s ``if k < 0`` clamp, and the three gates only ever compared ``now`` to the
    anchor. A calendar grid is not anchor-generated, so the clamp has no analogue: a schedule
    anchored 2026-01-05 and polled the next day computes the 2025-12-31 tick — 35 days BEFORE its
    own anchor (across 2026, 93% of anchor dates do this). That is a backfill of a period before the
    schedule existed, and under OD-SCH-2-E it would mint a governed run dated before the book was
    configured.

    **(b) ``now >= anchor`` — the ORIGINAL leg, kept.** Dropping it in favour of (a) alone is a
    regression the shipped suite catches: under INTERVAL with ``now`` before the anchor, the clamp
    returns ``tick == anchor``, which satisfies (a) while being a tick in the FUTURE. A schedule
    must not fire before it starts, and it must not fire a grid point it has not reached.
    """
    anchor = _anchor_dt(schedule.anchor_date)
    return tick < anchor or now < anchor


def _assert_current_tick(
    schedule: Schedule,
    tick: datetime,
    now: datetime,
    holidays: frozenset[dt_date] | None = None,
) -> None:
    """Self-enforce INV-SCH-1 at the write boundary: ``tick`` MUST be the current grid tick for
    ``now`` AND must be at/after the anchor. Guards a mis-caller passing an arbitrary ``tick``
    (e.g. a wall clock), which would violate the invariant AND split the idempotency bucket so
    ``uq(schedule_id, scheduled_for)`` no longer collides (a silent double-fire)."""
    _require_aware(now)
    expected = _schedule_tick(schedule, now, holidays)
    if tick != expected:
        raise ScheduleError(f"tick {tick} is not the current grid tick {expected} (INV-SCH-1)")
    if _outside_start_boundary(schedule, tick, now):
        raise ScheduleError(
            f"tick {tick} is outside the start boundary of anchor {schedule.anchor_date} — "
            "refusing to fire a grid point from before the schedule existed"
        )


def is_due(
    schedule: Schedule,
    now: datetime,
    fired_ticks: set[datetime],
    holidays: frozenset[dt_date] | None = None,
) -> bool:
    """Pure predicate: an ACTIVE schedule whose CURRENT grid tick has not already fired.

    No backfill: only the current tick is ever considered — missed grid points are honest gaps.
    """
    _require_aware(now)
    if schedule.status != SCHEDULE_STATUS_ACTIVE:
        return False
    tick = _schedule_tick(schedule, now, holidays)
    if _outside_start_boundary(schedule, tick, now):
        return False
    return tick not in fired_ticks


def _period_key(tick: datetime) -> str:
    """The month-grain idempotency key for ``BUSINESS_MONTH_END`` rows (OQ-CAL-1-5), e.g.
    ``2027-05`` — stored on ``scheduled_run.period_key`` under the partial unique
    ``uq_scheduled_run_schedule_period`` so one economic month fires at most once even when a
    holiday refresh re-values the tick INSTANT between concurrent polls (the exact-instant uq
    cannot collide across distinct instants; the period key is the DB-grain backstop)."""
    return f"{tick.year:04d}-{tick.month:02d}"


def _resolve_business_calendar(
    session: Session, schedule: Schedule
) -> tuple[Calendar, frozenset[dt_date]]:
    """Resolve a ``BUSINESS_MONTH_END`` schedule's bound calendar + holiday set, FAIL-CLOSED
    (OQ-CAL-1-4: the LIM-1 standard — an empty/invisible set must refuse, never silently compute
    weekday-only answers indistinguishable from the legacy kind).

    Called ONCE per schedule per poll cycle; the returned set threads poll→write so INV-SCH-1's
    write-boundary recompute provably sees the SAME set (G27). Every refusal is a ``ScheduleError``
    (the B3 skip-and-report discipline). The read runs under the worker's tenant session — the
    hybrid RLS USING serves own-tenant OR SYSTEM calendars; an RLS-invisible id resolves to None
    and refuses here rather than degrading."""
    if not schedule.calendar_id:
        raise ScheduleError(
            "BUSINESS_MONTH_END requires a bound calendar (calendar_id is NULL) — refusing"
        )
    calendar = session.execute(
        select(Calendar).where(
            Calendar.id == schedule.calendar_id,
            # Belt-and-suspenders (the CAL-1b review's MED): the explicit own-OR-SYSTEM predicate
            # the platform's pattern demands — RLS alone leaves the foreign-calendar refusal
            # unenforceable on the SQLite tier and in superuser PG contexts (the REF-1 lesson).
            or_(
                Calendar.tenant_id == str(schedule.tenant_id),
                Calendar.tenant_id == SYSTEM_TENANT_ID,
            ),
        )
    ).scalar_one_or_none()
    if calendar is None:
        raise ScheduleError(
            f"calendar {schedule.calendar_id} is not visible to this tenant — refusing a "
            "holiday-blind tick"
        )
    if calendar.holidays_complete_through is None:
        raise ScheduleError(
            f"calendar {calendar.code!r} declares no holiday coverage "
            "(holidays_complete_through is NULL) — a DECLARED horizon is required (OQ-CAL-1-4; "
            "a derived MAX cannot represent a gap)"
        )
    dates = frozenset(
        session.execute(
            select(CalendarHoliday.holiday_date).where(
                CalendarHoliday.calendar_id == calendar.id,
                or_(
                    CalendarHoliday.tenant_id == str(schedule.tenant_id),
                    CalendarHoliday.tenant_id == SYSTEM_TENANT_ID,
                ),
            )
        ).scalars()
    )
    return calendar, dates


# ------------------------------------------------------------------------------- DB due-select ---
def select_active_due(
    session: Session, now: datetime, *, acting_tenant: str
) -> list[tuple[Schedule, datetime, frozenset[dt_date] | None]]:
    """Tenant-scoped: ACTIVE schedules whose current grid tick has no ``scheduled_run`` yet,
    each with its per-cycle resolved holiday set (``None`` for the legacy kinds) — the caller
    threads that set to ``dispatch_one``/``record_failed_dispatch`` so the write boundary sees
    exactly what the poll saw (INV-SCH-1 under CAL-1b).

    Reads ONLY the two scheduling tables. Under OQ-SCH-1-1=B this runs inside ONE tenant's
    non-BYPASSRLS session, so RLS already shows only that tenant's rows — the explicit
    ``tenant_id == acting_tenant`` predicate is defense-in-depth (the platform's belt-and-suspenders
    explicit-predicate + RLS pattern), so a caller outside a forced-RLS session can never sweep
    other tenants' schedules.
    """
    _require_aware(now)
    schedules = list(
        session.execute(
            select(Schedule)
            .where(
                Schedule.status == SCHEDULE_STATUS_ACTIVE,
                Schedule.tenant_id == str(acting_tenant),
            )
            # deterministic cross-tick iteration order (the API-2b 4-finder determinism fold)
            .order_by(Schedule.id)
        ).scalars()
    )
    due: list[tuple[Schedule, datetime, frozenset[dt_date] | None]] = []
    for schedule in schedules:
        try:
            holidays: frozenset[dt_date] | None = None
            calendar: Calendar | None = None
            if schedule.cadence_kind == CADENCE_BUSINESS_MONTH_END:
                calendar, holidays = _resolve_business_calendar(session, schedule)
            tick = _schedule_tick(schedule, now, holidays)
            coverage = calendar.holidays_complete_through if calendar is not None else None
            if coverage is not None and tick.date() > coverage:
                raise ScheduleError(
                    f"tick {tick.date()} exceeds the bound calendar's declared holiday "
                    f"coverage ({coverage}) — refusing an uncovered month (OQ-CAL-1-4)"
                )
        except ScheduleError:
            # SKIP-AND-REPORT, never raise (SCH-2, verifier B3): this loop runs in the worker's
            # `for` HEADER, outside the per-schedule SAVEPOINT, so a raise here would abort ALL
            # FOUR tick phases for the tenant. An unresolvable cadence isolates to its own schedule.
            _log.error(
                "schedule %s has an unresolvable cadence (%s) — skipped this cycle",
                schedule.id,
                schedule.cadence_kind,
            )
            continue
        if _outside_start_boundary(schedule, tick, now):
            continue
        already = session.execute(
            select(ScheduledRun.id).where(
                ScheduledRun.schedule_id == schedule.id,
                ScheduledRun.scheduled_for == tick,
            )
        ).first()
        if already is not None:
            continue
        if schedule.cadence_kind == CADENCE_BUSINESS_MONTH_END:
            # The month-grain polite layer (OQ-CAL-1-5): a holiday refresh that re-values an
            # already-SERVED month's instant finds the month occupied and no-ops here; the DB
            # partial unique is the hard backstop for the concurrent-poll race this read cannot
            # close (READ COMMITTED — two polls straddling a refresh commit).
            served = session.execute(
                select(ScheduledRun.id).where(
                    ScheduledRun.schedule_id == schedule.id,
                    ScheduledRun.period_key == _period_key(tick),
                )
            ).first()
            if served is not None:
                continue
        due.append((schedule, tick, holidays))
    return due


# ------------------------------------------------------------------- the family dispatch registry
@dataclass(frozen=True)
class DispatchOutcome:
    """What a family dispatch produced: the governed run + the family-specific resolved ids."""

    run_id: str
    status: str
    failure_reason: str | None
    resolved_exposure_run_id: str | None = None
    resolved_covariance_run_id: str | None = None


@dataclass(frozen=True)
class ScheduledFamily:
    """One dispatchable family (SCH-2, OD-SCH-2-D — the SCH-1 family-2 deferral discharged).

    Declares exactly what the generic dispatcher cannot infer:

    - ``requires_model_version`` — VaR binds a registered ``model_version``; EXPOSURE is the
      MODEL-LESS deterministic rollup and must NOT carry one. This flag is the single source for
      the DB CHECK, ``_validate_config``, AND the CAD-1 FK guard — each of which is gated on the
      DECLARATION, never on whether the caller happened to supply a value (that would be a CTRL-003
      fail-open: a VAR schedule created with ``None`` would skip inventory-before-use entirely).
    **``produces_run_on_failure`` was REMOVED at the SCH-2 4-finder review (grid lens).** It
    declared that EXPOSURE "has no upstream to resolve and therefore no pre-create gate", so its
    dominant failure was a POST-create FAILED run leaving a committed ``calculation_run`` + audit
    events + a DQ result. **That is false on the only path the scheduler uses.** The pre-create gate
    is not upstream resolution — it is the SNAPSHOT BUILD's completeness gate, and
    ``_dispatch_exposure`` always takes the build path: a missing month-end mark raises
    ``DataQualityError`` from ``build_snapshot`` BEFORE ``execute_governed_run`` mints anything
    (the repo's own ``test_exposure.test_pre_create_refusal_incomplete_snapshot`` proves it — zero
    runs). So the dominant scheduled EXPOSURE failure leaves ``calculation_run_id`` NULL and, after
    the worker's SAVEPOINT rollback, NO durable artefact but the ledger row itself.

    It was removed rather than corrected because the distinction is **not a family property at
    all** — both families can fail on either side of run creation, depending on which gate trips.
    Nothing read the flag; a false declaration with no consumer is worse than no declaration. The
    operator-relevant version of this fact now lives in the burned-month runbook, where it changes
    what someone actually does.
    - ``dispatch`` — the per-family callable. Upstream resolution is genuinely per-family (VaR needs
      two upstream runs from two different resolvers; EXPOSURE needs none), so it is a callback,
      not a shared body.
    """

    target_run_type: str
    requires_model_version: bool
    dispatch: Callable[..., DispatchOutcome]
    #: REPRO-1: whether this family's schedule names a PORTFOLIO. Modelled exactly like
    #: ``requires_model_version`` and for the same reason — VAR and EXPOSURE_AGGREGATE compute a
    #: specific book's number, while the REPRODUCTION sweep is tenant-wide and re-executes families
    #: that are not all portfolio-scoped at all (covariance is tenant-global). Naming a book on a
    #: reproduction schedule would stamp a false scope into a governed config row that the ops UI
    #: renders. Declared here so the DB CHECK, ``_validate_config`` and the cross-tenant FK guard
    #: all read ONE source; never inferred from whether a caller happened to supply a value, which
    #: is the CTRL-003 fail-open shape.
    requires_portfolio_scope: bool = True


def _dispatch_var(
    session: Session, schedule: Schedule, tick: datetime, *, code_version: str
) -> DispatchOutcome:
    """VaR: resolve the latest COMPLETED FACTOR_EXPOSURE run for the scope (tenant-scoped — this is
    what ``run_var`` re-pins as ``x``, NOT a plain EXPOSURE run) + the latest COMPLETED COVARIANCE
    run (tenant-global), then ``run_var`` with build args re-pins a FRESH snapshot over current
    data. Both misses are PRE-create refusals (no ``calculation_run`` is minted).

    ``run_var`` is resolved from the MODULE GLOBAL at call time — ``test_scheduler_dispatch``
    patches ``scheduling.service.run_var``, and capturing the function object in the registry would
    make that patch invisible. The registry must not move out of this module without that test.
    """
    # A REAL guard, not a cast (SCH-2): `model_version_id` became nullable for the model-less
    # family, so the type is now `str | None` here. Three layers should already have refused a VAR
    # schedule without one (the DB CHECK, `_validate_config`, the registry-gated FK guard) — if a
    # row reaches dispatch with NULL anyway, every one of them has failed and firing an unbound run
    # would breach CTRL-003 inventory-before-use. Refuse PRE-create; the caller records FAILED.
    model_version_id = schedule.model_version_id
    if model_version_id is None:
        raise ScheduleError(
            f"schedule {schedule.id} targets {schedule.target_run_type} but carries no "
            "model_version_id — refusing to fire an unbound governed run (CTRL-003)"
        )
    tenant = schedule.tenant_id
    fx_rows = latest_factor_exposure(
        session, acting_tenant=tenant, portfolio_id=schedule.scope_portfolio_id
    )
    if not fx_rows:
        raise ScheduleError("no COMPLETED factor-exposure run for the schedule scope")
    exposure_run_id = fx_rows[0].calculation_run_id
    cov_rows = latest_covariances(session, acting_tenant=tenant)
    if not cov_rows:
        raise ScheduleError("no COMPLETED covariance run for the tenant")
    covariance_run_id = cov_rows[0].calculation_run_id

    result: VarRunResult = run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id=f"scheduler:{schedule.id}", actor_type="SYSTEM"),
        code_version=code_version,
        environment_id=schedule.environment_id,
        model_version_id=model_version_id,
        exposure_run_id=exposure_run_id,
        covariance_run_id=covariance_run_id,
    )
    return DispatchOutcome(
        run_id=result.run.run_id,
        status=result.status,
        failure_reason=result.failure_reason,
        resolved_exposure_run_id=exposure_run_id,
        resolved_covariance_run_id=covariance_run_id,
    )


def _dispatch_exposure(
    session: Session, schedule: Schedule, tick: datetime, *, code_version: str
) -> DispatchOutcome:
    """EXPOSURE_AGGREGATE: no upstream to resolve — the TICK is the economic as-of (OD-SCH-2-E).

    The tick→as-of coupling is declared HERE, per-family, rather than as a structural rule: today
    the tick is otherwise a purely control-plane bucket, and the VaR path deliberately re-pins over
    CURRENT data instead. The tick is an END-OF-DAY instant (OD-SCH-2-C) so same-day marks are
    visible under ``Valuation.valid_from <= valid_at``.

    ``as_of_known_at`` is deliberately LEFT UNSET (it defaults to the fire instant). The verifier
    asked for it to be pinned to the tick, reasoning that two fires of the same tick — minutes vs
    weeks apart — would otherwise differ whenever an input was corrected between. **That scenario
    is unreachable**: ``uq(schedule_id, scheduled_for)`` permits exactly ONE fire per tick, and the
    run is reproducible from its own immutable snapshot regardless (AD-014), which records the
    known-time on its header. Pinning it buys nothing and costs something real — the known-time
    axis means "as the world was RECORDED at T", so ``known_at = tick`` makes every row recorded
    after the tick invisible: a late-arriving month-end mark would be permanently unseen by the
    only fire that tick will ever get, and any replay against back-loaded data yields an EMPTY
    snapshot. The demo stage caught exactly that (an `EmptySnapshotError` on a book whose positions
    were recorded after the modelled month-end), which is why the pin was reverted.
    """
    result: ExposureRunResult = run_exposure(
        session,
        acting_tenant=schedule.tenant_id,
        actor=ExposureActor(actor_id=f"scheduler:{schedule.id}", actor_type="SYSTEM"),
        code_version=code_version,
        environment_id=schedule.environment_id,
        portfolio_id=schedule.scope_portfolio_id,
        as_of_valid_at=tick,
    )
    return DispatchOutcome(
        run_id=result.run.run_id,
        status=result.status,
        failure_reason=result.failure_reason,
    )


def _dispatch_reproduction(
    session: Session, schedule: Schedule, tick: datetime, *, code_version: str
) -> DispatchOutcome:
    """REPRODUCTION (REPRO-1): re-execute every registered family's most recent COMPLETED run over
    that run's OWN pinned snapshot, and record a verdict per subject.

    Unlike the other two families this one resolves NO upstream run and computes no new governed
    number — it re-derives numbers that already exist and judges whether they came back the same.
    It is tenant-wide, so ``schedule.scope_portfolio_id`` is NULL here by declaration.

    ``run_reproduction_sweep`` is resolved from the MODULE GLOBAL at call time, matching the
    ``run_var`` convention above: the dispatch tests patch ``scheduling.service.*``, and capturing
    the function object in the registry would make that patch invisible.

    **No alarm is delivered from here.** This runs inside the tick's phases-1-2 transaction, which
    holds the per-tenant audit advisory lock to COMMIT; a sink call under that lock is the API-2b
    lock-across-I/O anti-pattern. Delivery is its own later phase.
    """
    outcome = run_reproduction_sweep(
        session,
        acting_tenant=schedule.tenant_id,
        actor_id=f"scheduler:{schedule.id}",
        actor_type="SYSTEM",
        code_version=code_version,
        environment_id=schedule.environment_id,
        scope_portfolio_id=schedule.scope_portfolio_id,
    )
    return DispatchOutcome(
        run_id=outcome.run_id,
        status=outcome.status,
        failure_reason=outcome.failure_reason,
    )


#: The dispatch registry — the SINGLE source for which families are schedulable (OD-SCH-2-F). It
#: lives here, not in ``events``: the registry must import the family binders, and ``events`` is a
#: leaf vocabulary module that ``irp_worker`` imports for two string constants — the dispatch
#: outcomes ``OUTCOME_FAILED``/``OUTCOME_SKIPPED_DUPLICATE`` (this comment said "three", a count
#: the 4-finder correction reached in one of its two locations; fixed at the Wave-13 close —
#: putting the registry there would drag the whole risk+exposure compute stack into the worker's
#: import graph, and defining the derived set in ``events`` while the registry lives here is a
#: circular import).
FAMILY_REGISTRY: dict[str, ScheduledFamily] = {
    TARGET_RUN_TYPE_VAR: ScheduledFamily(
        target_run_type=TARGET_RUN_TYPE_VAR,
        requires_model_version=True,
        dispatch=_dispatch_var,
    ),
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE: ScheduledFamily(
        target_run_type=TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
        requires_model_version=False,
        dispatch=_dispatch_exposure,
    ),
    # REPRO-1: the THIRD family, and the first that is neither portfolio-scoped nor model-bound.
    # Admitting it required migration 0065 — 0053's two family CHECKs are TOTAL ENUMERATIONS that
    # PostgreSQL enforces, and 0053's docstring records that as deliberate ("admitting family 3
    # requires a migration"). Note the whole SQLite unit tier would have gone green without it.
    RUN_TYPE_REPRODUCTION: ScheduledFamily(
        target_run_type=RUN_TYPE_REPRODUCTION,
        requires_model_version=False,
        dispatch=_dispatch_reproduction,
        requires_portfolio_scope=False,
    ),
}

#: DERIVED from the registry (SCH-2) — never a hand-maintained second list. ``events`` deliberately
#: no longer defines this; the family gate has exactly ONE source.
SCHEDULABLE_RUN_TYPES = frozenset(FAMILY_REGISTRY)


# --------------------------------------------------------------------------------- dispatch -----
def dispatch_one(
    session: Session,
    schedule: Schedule,
    tick: datetime,
    now: datetime,
    *,
    code_version: str,
    holidays: frozenset[dt_date] | None = None,
) -> ScheduledRun:
    """Fire ONE grid tick: resolve upstream, run the family binder, append the ledger row.

    Idempotent: a pre-existing ``(schedule_id, tick)`` row is returned unchanged (the unique
    constraint is the hard race backstop — a concurrent loser rolls back its phantom run at COMMIT).
    The family binder and its upstream resolution come from ``FAMILY_REGISTRY`` (SCH-2). A
    pre-create refusal RAISES (the caller records a FAILED ledger row); a post-create FAILED
    run returns a row
    with ``outcome=FAILED`` + the failed run id.
    """
    _assert_current_tick(
        schedule, tick, now, holidays
    )  # INV-SCH-1 self-enforcing at the write boundary
    existing = session.execute(
        select(ScheduledRun).where(
            ScheduledRun.schedule_id == schedule.id,
            ScheduledRun.scheduled_for == tick,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    family = FAMILY_REGISTRY.get(schedule.target_run_type)
    if family is None:
        raise ScheduleError(f"target_run_type {schedule.target_run_type!r} is not schedulable")
    # Wave-13 close fold: the dispatch-time CTRL-003 refusal, DECLARATION-driven like its three
    # sibling layers. It previously lived only as a hand-written `is None` check inside
    # `_dispatch_var` — correct for VaR, but a third family registered with
    # `requires_model_version=True` would have inherited NO dispatch-layer inventory gate unless
    # its author hand-copied the pattern, which is exactly the per-family-hand-copy failure the
    # registry exists to end. `_dispatch_var`'s own raise stays as defense-in-depth/type-narrowing.
    if family.requires_model_version and schedule.model_version_id is None:
        raise ScheduleError(
            f"schedule {schedule.id} targets {schedule.target_run_type} but carries no "
            "model_version_id — refusing to fire an unbound governed run (CTRL-003)"
        )

    result = family.dispatch(session, schedule, tick, code_version=code_version)
    outcome = OUTCOME_DISPATCHED if result.status == "COMPLETED" else OUTCOME_FAILED
    row = ScheduledRun(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        scheduled_for=tick,
        period_key=(
            _period_key(tick) if schedule.cadence_kind == CADENCE_BUSINESS_MONTH_END else None
        ),
        fired_at=now,
        calculation_run_id=result.run_id,
        resolved_exposure_run_id=result.resolved_exposure_run_id,
        resolved_covariance_run_id=result.resolved_covariance_run_id,
        outcome=outcome,
        failure_reason=result.failure_reason,
    )
    session.add(row)
    session.flush()
    return row


#: Everything from here on in a SQLAlchemy ``DBAPIError`` string is the statement and its BOUND
#: PARAMETERS; PG additionally appends a ``DETAIL:`` line quoting the failing row's values.
_REASON_CUTS = ("\n[SQL:", "\n[parameters:", "\nDETAIL:", "\nCONTEXT:")


def redact_failure_reason(reason: str) -> str:
    """Keep the diagnostic head of a failure string; drop everything that carries DATA.

    **Why this exists (SCH-2 4-finder review, doctrine lens).** The worker's catch-all records
    ``f"{type(exc).__name__}: {exc}"`` into ``scheduled_run.failure_reason``. For a DB error that
    string embeds the failing statement AND its bound parameters — verified: SQLAlchemy renders
    ``[SQL: INSERT ...]\\n[parameters: (...)]``, and PG adds ``DETAIL: Failing row contains (...)``.
    The values in an EXPOSURE dispatch are marks, quantities and valuations.

    That was write-only until SCH-2 gave the ledger its first reader, and the reader is gated on
    ``schedule.view`` — whose holder set includes ``auditor_3l``, a role deliberately granted NO
    ``valuation.view`` / ``position.view`` / ``marketdata.view``. Surfacing the raw string would
    hand that role, through the back door, the very data its permission set withholds.

    Redaction happens HERE, at the WRITE boundary, not in the worker: every caller is then covered,
    and a redacted ledger cannot be un-redacted by a later reader (the ``_assert_current_tick``
    self-enforcement pattern). The first line survives — that is the driver + constraint name, which
    is what an operator actually needs to act on.
    """
    head = reason
    for cut in _REASON_CUTS:
        head = head.split(cut, 1)[0]
    return head.strip()[:2000]


def record_failed_dispatch(
    session: Session,
    schedule: Schedule,
    tick: datetime,
    now: datetime,
    reason: str,
    holidays: frozenset[dt_date] | None = None,
) -> ScheduledRun:
    """Append a FAILED ledger row for a dispatch that RAISED before a run was created.

    Occupies the ``(schedule_id, tick)`` bucket so the SAME tick is not retried (record + continue,
    OD-SCH-1-J — the NEXT grid tick is the retry, not this one). ``calculation_run_id`` is NULL.
    ``reason`` is REDACTED before it is persisted — see ``redact_failure_reason``.
    """
    _assert_current_tick(schedule, tick, now, holidays)  # INV-SCH-1: FAILED rows use the grid tick
    row = ScheduledRun(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        scheduled_for=tick,
        period_key=(
            _period_key(tick) if schedule.cadence_kind == CADENCE_BUSINESS_MONTH_END else None
        ),
        fired_at=now,
        calculation_run_id=None,
        outcome=OUTCOME_FAILED,
        failure_reason=redact_failure_reason(reason),
    )
    session.add(row)
    session.flush()
    return row


# ------------------------------------------------------------------------------ schedule CRUD ---
def _validate_config(
    *,
    target_run_type: str,
    cadence_kind: str,
    status: str,
    interval_days: int | None,
    environment_id: str,
    model_version_id: str | None,
    calendar_id: str | None = None,
    scope_portfolio_id: str | None = None,
) -> None:
    """Fail-closed config validation, driven by the registry and mirroring the DB CHECKs in BOTH
    directions (SCH-2, verifier B4).

    Why both directions matter: SQLite builds its schema from ORM metadata and this repo creates
    every CHECK imperatively in migrations, so relaxing the two NOT-NULLs would leave the ENTIRE
    unit tier (where every scheduler / limit / breach / notification test runs) with NO enforcement
    of the per-family rule. The service must therefore carry it, or SQLite admits what PG rejects
    at flush with a raw ``IntegrityError`` that the worker records as an opaque FAILED row.
    """
    family = FAMILY_REGISTRY.get(target_run_type)
    if family is None:
        raise ScheduleError(f"target_run_type {target_run_type!r} is not schedulable")
    if cadence_kind not in CADENCE_KINDS:
        raise ScheduleError(f"cadence_kind {cadence_kind!r} is not a supported cadence")
    if status not in SCHEDULE_STATUSES:
        raise ScheduleError(f"status {status!r} is not a valid schedule status")

    # calendar: required XOR forbidden by cadence kind (CAL-1b, OQ-CAL-1-4 — mirrors the
    # ck_schedule_calendar_id_by_cadence total enumeration; SQLite carries no CHECKs, so this
    # service mirror is the unit tier's only enforcement).
    if cadence_kind == CADENCE_BUSINESS_MONTH_END and not calendar_id:
        raise ScheduleError(
            "calendar_id is required for the BUSINESS_MONTH_END cadence (the holiday-aware grid "
            "must name its calendar — OQ-CAL-1-4)"
        )
    if cadence_kind != CADENCE_BUSINESS_MONTH_END and calendar_id is not None:
        raise ScheduleError(f"calendar_id is meaningless under {cadence_kind} — omit it")

    # model_version: required XOR forbidden, per the registry DECLARATION (never per the value).
    if family.requires_model_version and not model_version_id:
        raise ScheduleError(
            f"model_version_id is required for the {target_run_type} family "
            "(CTRL-003 inventory-before-use)"
        )
    if not family.requires_model_version and model_version_id is not None:
        raise ScheduleError(f"{target_run_type} is model-less — model_version_id must be omitted")

    # scope_portfolio_id: required XOR forbidden, per the registry DECLARATION (REPRO-1, mirroring
    # ck_schedule_portfolio_scope_by_family). SQLite carries no CHECKs, so this mirror is the unit
    # tier's ONLY enforcement of the rule — without it the entire unit suite would admit what
    # PostgreSQL rejects at flush with an opaque IntegrityError the worker records as FAILED.
    if family.requires_portfolio_scope and not scope_portfolio_id:
        raise ScheduleError(
            f"scope_portfolio_id is required for the {target_run_type} family — it computes a "
            "specific book's number"
        )
    if not family.requires_portfolio_scope and scope_portfolio_id is not None:
        raise ScheduleError(
            f"{target_run_type} is tenant-wide — scope_portfolio_id must be omitted rather than "
            "naming a book the sweep does not actually scope to"
        )

    # interval_days: required-and-positive for INTERVAL, forbidden otherwise.
    if cadence_kind == CADENCE_INTERVAL:
        if interval_days is None or interval_days <= 0:
            raise ScheduleError("interval_days must be a positive integer for the INTERVAL cadence")
        if interval_days > MAX_INTERVAL_DAYS:
            raise ScheduleError(
                f"interval_days must not exceed {MAX_INTERVAL_DAYS} (a runaway envelope, not a "
                "business rule — the column admits values the grid arithmetic cannot represent)"
            )
    elif interval_days is not None:
        raise ScheduleError(f"interval_days is meaningless under {cadence_kind} — omit it")

    if not environment_id:
        raise ScheduleError("environment_id is required (a governed-run pin)")


def create_schedule(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    target_run_type: str,
    scope_portfolio_id: str | None = None,
    environment_id: str,
    anchor_date: dt_date,
    actor: SchedulingActor,
    model_version_id: str | None = None,
    interval_days: int | None = None,
    cadence_kind: str = CADENCE_INTERVAL,
    status: str = SCHEDULE_STATUS_ACTIVE,
    calendar_id: str | None = None,
) -> Schedule:
    """Create an ACTIVE (by default) schedule head; emit ``SCHEDULE.CREATE`` (governed R-07).

    ``model_version_id`` and ``interval_days`` became optional at SCH-2 (each is required for some
    families/cadences and FORBIDDEN for others — ``_validate_config`` enforces both directions), so
    every existing keyword call site still compiles.
    """
    _validate_config(
        target_run_type=target_run_type,
        cadence_kind=cadence_kind,
        status=status,
        interval_days=interval_days,
        environment_id=environment_id,
        model_version_id=model_version_id,
        calendar_id=calendar_id,
        scope_portfolio_id=scope_portfolio_id,
    )
    # P3-5 cross-tenant FK guard (OQ-W11C-2): re-resolve the HARD FKs under the acting tenant
    # BEFORE they are stamped into FK columns — PG FK checks bypass RLS, so the DB alone would
    # durably admit a foreign portfolio/model_version. ``environment_id`` is a free label
    # (``calculation_run.environment_id``; NOT a security boundary) and correctly needs no guard.
    #
    # REPRO-1 gated this on the registry DECLARATION, matching the model_version guard immediately
    # below. The `is not None` leg is TYPE narrowing, not a second gate: `_validate_config` has
    # already refused a falsy value for a scoping family, so it can never be why the guard is
    # skipped.
    if FAMILY_REGISTRY[target_run_type].requires_portfolio_scope and scope_portfolio_id is not None:
        assert_portfolio_in_tenant(
            session, scope_portfolio_id, acting_tenant=tenant_id, error=ScheduleError
        )
    # Gated on the registry DECLARATION, never on the value (SCH-2, verifier B5). `if
    # model_version_id:` would look equivalent and would be a CTRL-003 FAIL-OPEN: a VAR schedule
    # created with None/"" would skip inventory-before-use entirely. `_validate_config` has already
    # refused a falsy value for a requiring family, so this is never reached with None.
    if FAMILY_REGISTRY[target_run_type].requires_model_version and model_version_id is not None:
        # The `is not None` leg is a TYPE narrowing, not a second gate — `_validate_config` above
        # already raised for a requiring family with a falsy value, so it can never be the reason
        # this guard is skipped. Written as `and` rather than an assert so a future reordering
        # degrades to "the FK guard did not run", which the DB CHECK + `_validate_config` still
        # catch, instead of a raw AssertionError from the wrong layer.
        assert_model_version_in_tenant(
            session, model_version_id, acting_tenant=tenant_id, error=ScheduleError
        )
    # The calendar FK guard (CAL-1b, OQ-CAL-1-4): the SECOND symmetric→hybrid FK (after 0056's
    # assignment→scheme), so the P3-5 own-tenant-only pattern would REFUSE the SYSTEM XNYS
    # calendar — this is the own-OR-SYSTEM variant (the resolve_currency/OQ-REF-1-20 precedent).
    # Gated on the CADENCE declaration, never on the value: `_validate_config` above already
    # refused a falsy calendar_id for BUSINESS_MONTH_END and a present one for the legacy kinds.
    if cadence_kind == CADENCE_BUSINESS_MONTH_END and calendar_id is not None:
        visible = session.execute(
            select(Calendar.id).where(
                Calendar.id == str(calendar_id),
                or_(
                    Calendar.tenant_id == str(tenant_id),
                    Calendar.tenant_id == SYSTEM_TENANT_ID,
                ),
            )
        ).first()
        if visible is None:
            raise ScheduleError(
                f"calendar {calendar_id} is not visible to tenant {tenant_id} (own-OR-SYSTEM) — "
                "refusing a cross-tenant calendar binding (PG FK checks bypass RLS)"
            )
    schedule = Schedule(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        target_run_type=target_run_type,
        # REPRO-1: the same None-stringification trap the line below has carried since SCH-2 now
        # applies here too, because the column became legitimately NULL for the tenant-wide
        # REPRODUCTION family. Caught by EXECUTION, not by reading: SQLite stored the literal
        # 'None' happily and the unit tier would have shipped it; PostgreSQL rejects it as
        # `invalid input syntax for type uuid`, so it would have surfaced first on the deployed
        # stack. The warning was already written, one line down, about the sibling column.
        scope_portfolio_id=str(scope_portfolio_id) if scope_portfolio_id is not None else None,
        # NOT `str(...)` — that stringifies None to the literal "None", which PG then rejects as
        # `invalid input syntax for type uuid`. The column is legitimately NULL for a model-less
        # family (SCH-2), so the None must survive to the bind parameter.
        model_version_id=str(model_version_id) if model_version_id is not None else None,
        environment_id=environment_id,
        cadence_kind=cadence_kind,
        interval_days=interval_days,
        calendar_id=str(calendar_id) if calendar_id is not None else None,
        anchor_date=anchor_date,
        status=status,
        record_version=1,
    )
    session.add(schedule)
    session.flush()
    _record_schedule_event(
        session,
        schedule=schedule,
        event_type=SCHEDULE_CREATE_EVENT,
        action=ACTION_CREATE,
        before_value=None,
        after_value=_schedule_metadata(schedule),
        actor=actor,
    )
    return schedule


def update_schedule(
    session: Session,
    schedule: Schedule,
    *,
    actor: SchedulingActor,
    **changes: Any,
) -> Schedule:
    """Apply an in-place head edit (name / status), bump ``record_version``, emit
    ``SCHEDULE.UPDATE``. Only ``_UPDATABLE`` attributes may change (a re-cadence/redefinition is a
    new schedule — OD-SCH-1-F)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ScheduleError(f"non-updatable schedule attributes: {sorted(unknown)}")
    if "status" in changes and changes["status"] not in SCHEDULE_STATUSES:
        raise ScheduleError(f"status {changes['status']!r} is not a valid schedule status")
    before = {key: getattr(schedule, key) for key in changes}
    for key, value in changes.items():
        setattr(schedule, key, value)
    schedule.record_version += 1
    session.flush()
    _record_schedule_event(
        session,
        schedule=schedule,
        event_type=SCHEDULE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: getattr(schedule, key) for key in changes},
        actor=actor,
    )
    return schedule


def pause_schedule(session: Session, schedule: Schedule, *, actor: SchedulingActor) -> Schedule:
    """Pause a schedule (excluded from ``select_active_due``; missed ticks are NOT backfilled)."""
    return update_schedule(session, schedule, actor=actor, status=SCHEDULE_STATUS_PAUSED)


def resume_schedule(session: Session, schedule: Schedule, *, actor: SchedulingActor) -> Schedule:
    """Resume a schedule; the next poll fires ONLY the current grid tick (no catch-up storm)."""
    return update_schedule(session, schedule, actor=actor, status=SCHEDULE_STATUS_ACTIVE)


def _schedule_metadata(schedule: Schedule) -> dict[str, Any]:
    """DC-2 metadata payload for a ``SCHEDULE.*`` event — identifying/vocab fields only."""
    return {
        "code": schedule.code,
        "target_run_type": schedule.target_run_type,
        "scope_portfolio_id": str(schedule.scope_portfolio_id),
        "cadence_kind": schedule.cadence_kind,
        "interval_days": schedule.interval_days,
        "status": schedule.status,
        "record_version": schedule.record_version,
    }


def _record_schedule_event(
    session: Session,
    *,
    schedule: Schedule,
    event_type: str,
    action: str,
    before_value: dict[str, Any] | None,
    after_value: dict[str, Any],
    actor: SchedulingActor,
) -> None:
    """Emit a ``SCHEDULE.*`` audit event caller-side to the FROZEN ``record_event`` (DC-2 only)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=schedule.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE_SCHEDULING,
        entity_type=ENTITY_SCHEDULE,
        entity_id=schedule.id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        data_classification="DC-2",
    )
