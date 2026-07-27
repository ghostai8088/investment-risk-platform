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

import calendar as _calendar
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import date as dt_date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.service import record_event
from irp_shared.exposure.events import ExposureActor
from irp_shared.exposure.service import ExposureRunResult, run_exposure
from irp_shared.model.guards import assert_model_version_in_tenant
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.risk.covariance_service import latest_covariances
from irp_shared.risk.events import VarActor
from irp_shared.risk.factor_service import latest_factor_exposure
from irp_shared.risk.var_service import VarRunResult, run_var
from irp_shared.scheduling.events import (
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
    non-business-day predicate (SCH-2, OD-SCH-2-C). Pure arithmetic: no holiday substrate exists
    (ENT-006 ``calendar``/``calendar_holiday`` are vocabulary tables with no business-day logic),
    so a month-end landing on a market HOLIDAY is a recorded residual, not a handled case."""
    day = _calendar.monthrange(year, month)[1]
    candidate = dt_date(year, month, day)
    while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
        candidate -= timedelta(days=1)
    return candidate


def _month_end_tick_at_or_before(now: datetime) -> datetime:
    """The most recent CALENDAR_MONTH_END grid point ``<= now``, as an END-OF-DAY instant.

    **The instant is end-of-day, and that is load-bearing** (OD-SCH-2-C): the tick becomes the
    EXPOSURE run's ``as_of_valid_at`` (OD-SCH-2-E), which is a BITEMPORAL CUTOFF, not a label —
    it reaches ``Valuation.valid_from <= valid_at``. An end-of-day mark for day ``T`` is captured
    DURING/AFTER ``T``, so at ``T 00:00Z`` it is not yet visible and the run would fail its
    completeness gate EVERY month. At end-of-day ``valid_from <= tick`` holds for any same-day
    capture, ``tick.date()`` is still ``T`` (so RM-1's month-alignment is satisfied), and trades
    booked on ``T`` are included.
    """
    candidate = _end_of_day(_last_weekday_of_month(now.year, now.month))
    if candidate <= now:
        return candidate
    # Still before this month's grid point — roll back to the previous month.
    year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    return _end_of_day(_last_weekday_of_month(year, month))


def _end_of_day(day: dt_date) -> datetime:
    """The last representable microsecond of ``day`` in UTC."""
    return datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=UTC)


def current_tick(
    anchor_date: dt_date,
    interval_days: int | None,
    now: datetime,
    *,
    cadence_kind: str = CADENCE_INTERVAL,
) -> datetime:
    """The most recent grid point at or before ``now`` (INV-SCH-1 — a PURE grid value).

    Two cadences (SCH-2): ``INTERVAL`` = ``anchor_midnight_utc + k·interval_days``, clamped to the
    anchor; ``CALENDAR_MONTH_END`` = the end of the last weekday of the calendar month. Depends ONLY
    on ``(anchor, interval, cadence, now)`` — never on the ledger or a wall clock — so two
    concurrent polls compute the identical bucket and collide on the unique constraint.

    **Fails CLOSED on an unresolvable cadence** (SCH-2, verifier B3). This function runs on the POLL
    path, and ``select_active_due`` is evaluated in the worker's ``for`` header — OUTSIDE the
    per-schedule SAVEPOINT — so a raw ``TypeError`` here (e.g. a NULL ``interval_days`` reaching the
    INTERVAL branch after a rollback) would escape ``poll_tenant_schedules`` and abort ALL FOUR tick
    phases for the tenant. Every exit from here is a clean ``ScheduleError``.
    """
    _require_aware(now)
    now = now.astimezone(UTC)  # the month-end branch reads calendar fields; normalize explicitly
    if cadence_kind == CADENCE_CALENDAR_MONTH_END:
        return _month_end_tick_at_or_before(now)
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


def _schedule_tick(schedule: Schedule, now: datetime) -> datetime:
    """``current_tick`` for a schedule row (its cadence, interval and anchor)."""
    return current_tick(
        schedule.anchor_date,
        schedule.interval_days,
        now,
        cadence_kind=schedule.cadence_kind,
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


def _assert_current_tick(schedule: Schedule, tick: datetime, now: datetime) -> None:
    """Self-enforce INV-SCH-1 at the write boundary: ``tick`` MUST be the current grid tick for
    ``now`` AND must be at/after the anchor. Guards a mis-caller passing an arbitrary ``tick``
    (e.g. a wall clock), which would violate the invariant AND split the idempotency bucket so
    ``uq(schedule_id, scheduled_for)`` no longer collides (a silent double-fire)."""
    _require_aware(now)
    expected = _schedule_tick(schedule, now)
    if tick != expected:
        raise ScheduleError(f"tick {tick} is not the current grid tick {expected} (INV-SCH-1)")
    if _outside_start_boundary(schedule, tick, now):
        raise ScheduleError(
            f"tick {tick} is outside the start boundary of anchor {schedule.anchor_date} — "
            "refusing to fire a grid point from before the schedule existed"
        )


def is_due(schedule: Schedule, now: datetime, fired_ticks: set[datetime]) -> bool:
    """Pure predicate: an ACTIVE schedule whose CURRENT grid tick has not already fired.

    No backfill: only the current tick is ever considered — missed grid points are honest gaps.
    """
    _require_aware(now)
    if schedule.status != SCHEDULE_STATUS_ACTIVE:
        return False
    tick = _schedule_tick(schedule, now)
    if _outside_start_boundary(schedule, tick, now):
        return False
    return tick not in fired_ticks


# ------------------------------------------------------------------------------- DB due-select ---
def select_active_due(
    session: Session, now: datetime, *, acting_tenant: str
) -> list[tuple[Schedule, datetime]]:
    """Tenant-scoped: ACTIVE schedules whose current grid tick has no ``scheduled_run`` yet.

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
    due: list[tuple[Schedule, datetime]] = []
    for schedule in schedules:
        try:
            tick = _schedule_tick(schedule, now)
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
        if already is None:
            due.append((schedule, tick))
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


#: The dispatch registry — the SINGLE source for which families are schedulable (OD-SCH-2-F). It
#: lives here, not in ``events``: the registry must import the family binders, and ``events`` is a
#: leaf vocabulary module that ``irp_worker`` imports for three string constants (putting it there
#: would drag the whole risk+exposure compute stack into the worker's import graph, and defining
#: the derived set in ``events`` while the registry lives here is a circular import).
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
) -> ScheduledRun:
    """Fire ONE grid tick: resolve upstream, run the family binder, append the ledger row.

    Idempotent: a pre-existing ``(schedule_id, tick)`` row is returned unchanged (the unique
    constraint is the hard race backstop — a concurrent loser rolls back its phantom run at COMMIT).
    The family binder and its upstream resolution come from ``FAMILY_REGISTRY`` (SCH-2). A
    pre-create refusal RAISES (the caller records a FAILED ledger row); a post-create FAILED
    run returns a row
    with ``outcome=FAILED`` + the failed run id.
    """
    _assert_current_tick(schedule, tick, now)  # INV-SCH-1 self-enforcing at the write boundary
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

    result = family.dispatch(session, schedule, tick, code_version=code_version)
    outcome = OUTCOME_DISPATCHED if result.status == "COMPLETED" else OUTCOME_FAILED
    row = ScheduledRun(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        scheduled_for=tick,
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
) -> ScheduledRun:
    """Append a FAILED ledger row for a dispatch that RAISED before a run was created.

    Occupies the ``(schedule_id, tick)`` bucket so the SAME tick is not retried (record + continue,
    OD-SCH-1-J — the NEXT grid tick is the retry, not this one). ``calculation_run_id`` is NULL.
    ``reason`` is REDACTED before it is persisted — see ``redact_failure_reason``.
    """
    _assert_current_tick(schedule, tick, now)  # INV-SCH-1 — the FAILED row uses the grid tick too
    row = ScheduledRun(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        scheduled_for=tick,
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

    # model_version: required XOR forbidden, per the registry DECLARATION (never per the value).
    if family.requires_model_version and not model_version_id:
        raise ScheduleError(
            f"model_version_id is required for the {target_run_type} family "
            "(CTRL-003 inventory-before-use)"
        )
    if not family.requires_model_version and model_version_id is not None:
        raise ScheduleError(f"{target_run_type} is model-less — model_version_id must be omitted")

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
    scope_portfolio_id: str,
    environment_id: str,
    anchor_date: dt_date,
    actor: SchedulingActor,
    model_version_id: str | None = None,
    interval_days: int | None = None,
    cadence_kind: str = CADENCE_INTERVAL,
    status: str = SCHEDULE_STATUS_ACTIVE,
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
    )
    # P3-5 cross-tenant FK guard (OQ-W11C-2): re-resolve the HARD FKs under the acting tenant
    # BEFORE they are stamped into FK columns — PG FK checks bypass RLS, so the DB alone would
    # durably admit a foreign portfolio/model_version. ``environment_id`` is a free label
    # (``calculation_run.environment_id``; NOT a security boundary) and correctly needs no guard.
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
    schedule = Schedule(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        target_run_type=target_run_type,
        scope_portfolio_id=str(scope_portfolio_id),
        # NOT `str(...)` — that stringifies None to the literal "None", which PG then rejects as
        # `invalid input syntax for type uuid`. The column is legitimately NULL for a model-less
        # family (SCH-2), so the None must survive to the bind parameter.
        model_version_id=str(model_version_id) if model_version_id is not None else None,
        environment_id=environment_id,
        cadence_kind=cadence_kind,
        interval_days=interval_days,
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
