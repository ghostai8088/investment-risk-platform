"""SCH-1 scheduler unit tests (SQLite) — pure cadence, schedule CRUD + audit, append-only,
and the no-backfill / idempotency behavior of ``select_active_due`` (hand-seeded, no real VaR;
the end-to-end dispatch → run_var chain is exercised in the PG/demo tier)."""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as dt_date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.model.models import Model, ModelVersion
from irp_shared.portfolio.models import Portfolio
from irp_shared.scheduling.events import (
    CADENCE_CALENDAR_MONTH_END,
    OUTCOME_DISPATCHED,
    SCHEDULE_CREATE_EVENT,
    SCHEDULE_STATUS_ACTIVE,
    SCHEDULE_STATUS_PAUSED,
    SCHEDULE_UPDATE_EVENT,
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun
from irp_shared.scheduling.service import (
    FAMILY_REGISTRY,
    SCHEDULABLE_RUN_TYPES,
    ScheduleError,
    _assert_current_tick,
    create_schedule,
    current_tick,
    is_due,
    pause_schedule,
    resume_schedule,
    select_active_due,
    update_schedule,
)

_ACTOR = SchedulingActor(actor_id="analyst-1", actor_type="user")
_ANCHOR = dt_date(2026, 1, 1)


def _seed_portfolio(session: Session, tenant: str) -> str:
    """Seed a real in-tenant portfolio — the CAD-1 create_schedule guard re-resolves the FK, so a
    fake random id is (correctly) refused; tests must provide a real referent."""
    p = Portfolio(
        tenant_id=tenant, code=f"pf-{uuid.uuid4().hex[:8]}", name="Book", node_type="BOOK"
    )
    session.add(p)
    session.flush()
    return str(p.id)


def _seed_model_version(session: Session, tenant: str) -> str:
    """Seed a real in-tenant model + model_version — the CAD-1 guard re-resolves this FK too."""
    m = Model(tenant_id=tenant, code=f"m-{uuid.uuid4().hex[:8]}", name="VaR", model_type="RISK")
    session.add(m)
    session.flush()
    mv = ModelVersion(tenant_id=tenant, model_id=str(m.id), version_label="v1")
    session.add(mv)
    session.flush()
    return str(mv.id)


def _mk(session: Session, tenant: str, **over: object) -> Schedule:
    kwargs: dict[str, object] = {
        "tenant_id": tenant,
        "code": f"sched-{uuid.uuid4().hex[:8]}",
        "name": "Daily VaR",
        "target_run_type": "VAR",
        # real in-tenant referents (the CAD-1 P3-5 guard re-resolves both FKs under the tenant)
        "scope_portfolio_id": _seed_portfolio(session, tenant),
        "model_version_id": _seed_model_version(session, tenant),
        "environment_id": "ci",
        "interval_days": 7,
        "anchor_date": _ANCHOR,
        "actor": _ACTOR,
    }
    kwargs.update(over)
    return create_schedule(session, **kwargs)  # type: ignore[arg-type]


def test_create_schedule_refuses_foreign_portfolio(session: Session) -> None:
    """CAD-1 (OQ-W11C-2): a scope_portfolio_id not visible in the acting tenant is refused BEFORE
    it can be stamped into the NOT-NULL FK (PG FK checks bypass RLS)."""
    tenant = str(uuid.uuid4())
    with pytest.raises(ScheduleError, match="portfolio"):
        _mk(session, tenant, scope_portfolio_id=str(uuid.uuid4()))  # random == foreign


def test_create_schedule_refuses_foreign_model_version(session: Session) -> None:
    """CAD-1 (OQ-W11C-2): a model_version_id not visible in the acting tenant is refused."""
    tenant = str(uuid.uuid4())
    with pytest.raises(ScheduleError, match="model version"):
        _mk(session, tenant, model_version_id=str(uuid.uuid4()))  # random == foreign


def test_create_schedule_refuses_cross_tenant_portfolio(session: Session) -> None:
    """A portfolio that exists but belongs to ANOTHER tenant is refused (the real P3-5 threat)."""
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_portfolio = _seed_portfolio(session, tenant_b)  # belongs to B
    with pytest.raises(ScheduleError, match="portfolio"):
        _mk(session, tenant_a, scope_portfolio_id=foreign_portfolio)


# ------------------------------------------------------------------------- pure cadence math ---
def test_current_tick_on_grid_point_returns_itself() -> None:
    now = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)  # anchor + 2*7d exactly
    assert current_tick(_ANCHOR, 7, now) == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def test_current_tick_mid_interval_floors_to_the_last_grid_point() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)  # between Jan15 and Jan22
    assert current_tick(_ANCHOR, 7, now) == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def test_current_tick_overdue_jumps_to_the_single_current_point_no_backfill() -> None:
    # 21 weeks past the anchor — the current tick is ONE point, not a backfilled series.
    now = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    tick = current_tick(_ANCHOR, 7, now)
    assert tick == datetime(2026, 5, 28, 0, 0, tzinfo=UTC)  # the most recent grid point <= now


def test_current_tick_at_anchor_is_the_anchor() -> None:
    assert current_tick(_ANCHOR, 7, datetime(2026, 1, 1, 0, 0, tzinfo=UTC)) == datetime(
        2026, 1, 1, 0, 0, tzinfo=UTC
    )


def test_current_tick_rejects_non_positive_interval() -> None:
    with pytest.raises(ScheduleError):
        current_tick(_ANCHOR, 0, datetime(2026, 1, 2, tzinfo=UTC))


def test_is_due_true_for_active_unfired_current_tick(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    assert is_due(sched, now, fired_ticks=set()) is True


def test_is_due_false_when_paused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant, status=SCHEDULE_STATUS_PAUSED)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    assert is_due(sched, now, fired_ticks=set()) is False


def test_is_due_false_before_anchor(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant, anchor_date=dt_date(2026, 3, 1))
    now = datetime(2026, 1, 15, tzinfo=UTC)
    assert is_due(sched, now, fired_ticks=set()) is False


def test_is_due_false_when_current_tick_already_fired(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    tick = current_tick(_ANCHOR, 7, now)
    assert is_due(sched, now, fired_ticks={tick}) is False


# ----------------------------------------------------------------- schedule CRUD + audit ---
def test_create_schedule_emits_schedule_create_and_sets_v1(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    assert sched.record_version == 1
    assert sched.status == SCHEDULE_STATUS_ACTIVE
    events = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == SCHEDULE_CREATE_EVENT)
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].chain_id == tenant


def test_pause_then_resume_emits_updates_and_bumps_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    pause_schedule(session, sched, actor=_ACTOR)
    assert sched.status == SCHEDULE_STATUS_PAUSED
    assert sched.record_version == 2
    resume_schedule(session, sched, actor=_ACTOR)
    assert sched.status == SCHEDULE_STATUS_ACTIVE
    assert sched.record_version == 3
    updates = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == SCHEDULE_UPDATE_EVENT)
        ).scalars()
    )
    assert len(updates) == 2


def test_create_rejects_unschedulable_run_type(session: Session) -> None:
    with pytest.raises(ScheduleError):
        _mk(session, str(uuid.uuid4()), target_run_type="ACTIVE_RISK")


def test_create_rejects_non_positive_interval_and_empty_environment(session: Session) -> None:
    with pytest.raises(ScheduleError):
        _mk(session, str(uuid.uuid4()), interval_days=0)
    with pytest.raises(ScheduleError):
        _mk(session, str(uuid.uuid4()), environment_id="")


def test_update_rejects_non_updatable_attribute(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    with pytest.raises(ScheduleError):
        update_schedule(session, sched, actor=_ACTOR, interval_days=3)


# ------------------------------------------------------------------------- append-only guard ---
def test_scheduled_run_is_append_only(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    row = ScheduledRun(
        tenant_id=tenant,
        schedule_id=sched.id,
        scheduled_for=datetime(2026, 1, 15, tzinfo=UTC),
        fired_at=datetime(2026, 1, 15, 6, 0, tzinfo=UTC),
        outcome=OUTCOME_DISPATCHED,
    )
    session.add(row)
    session.flush()
    row.outcome = "FAILED"
    with pytest.raises(AppendOnlyViolation):
        session.flush()


# ------------------------------------------------- select_active_due: no-backfill + idem ---
def _seed_fired(session: Session, sched: Schedule, tick: datetime) -> None:
    session.add(
        ScheduledRun(
            tenant_id=sched.tenant_id,
            schedule_id=sched.id,
            scheduled_for=tick,
            fired_at=tick,
            outcome=OUTCOME_DISPATCHED,
        )
    )
    session.flush()


def test_select_active_due_returns_the_current_tick_for_a_fresh_schedule(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 20, tzinfo=UTC)
    due = select_active_due(session, now, acting_tenant=tenant)
    assert len(due) == 1
    got_sched, got_tick = due[0]
    assert got_sched.id == sched.id
    assert got_tick == datetime(2026, 1, 15, tzinfo=UTC)  # current tick, not the anchor


def test_select_active_due_excludes_a_paused_schedule(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _mk(session, tenant, status=SCHEDULE_STATUS_PAUSED)
    assert select_active_due(session, datetime(2026, 1, 20, tzinfo=UTC), acting_tenant=tenant) == []


def test_select_active_due_excludes_an_already_fired_current_tick(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 20, tzinfo=UTC)
    _seed_fired(session, sched, current_tick(_ANCHOR, 7, now))
    assert (
        select_active_due(session, now, acting_tenant=tenant) == []
    )  # idempotent — no re-fire of the same tick


def test_select_active_due_overdue_fires_one_tick_not_a_backfill_series(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    _mk(session, tenant)
    now = datetime(2026, 6, 1, tzinfo=UTC)  # ~21 intervals past the anchor
    due = select_active_due(session, now, acting_tenant=tenant)
    assert len(due) == 1  # exactly ONE due tick, never a burst of the missed intervals
    assert due[0][1] == datetime(2026, 5, 28, tzinfo=UTC)


def test_paused_over_a_window_then_resume_fires_only_the_current_tick(session: Session) -> None:
    # Fire an early tick, pause across many intervals, resume far later: only the CURRENT tick is
    # due — NOT a catch-up storm of the paused window (the OD-SCH-1-F / verifier 3B fold).
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    _seed_fired(session, sched, datetime(2026, 1, 8, tzinfo=UTC))  # an early fire
    pause_schedule(session, sched, actor=_ACTOR)
    assert (
        select_active_due(session, datetime(2026, 4, 1, tzinfo=UTC), acting_tenant=tenant) == []
    )  # paused
    resume_schedule(session, sched, actor=_ACTOR)
    now = datetime(2026, 4, 2, tzinfo=UTC)
    due = select_active_due(session, now, acting_tenant=tenant)
    assert len(due) == 1
    assert due[0][1] == current_tick(_ANCHOR, 7, now)  # the current tick, one fire only


# --- SCH-2: the CALENDAR_MONTH_END cadence + the family registry ---------------------------------
# `cadence_kind` had ZERO test coverage before SCH-2 (`_validate_config`'s cadence branch was never
# exercised and `_mk` never passed the field), so these are the first tests that vocabulary has had.


def _mk_month_end(session: Session, tenant: str, **over: object) -> Schedule:
    """A CALENDAR_MONTH_END + EXPOSURE_AGGREGATE schedule (no model_version, no interval_days)."""
    kwargs: dict[str, object] = {
        "target_run_type": TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
        "cadence_kind": CADENCE_CALENDAR_MONTH_END,
        "model_version_id": None,
        "interval_days": None,
        "name": "Month-end exposure",
    }
    kwargs.update(over)
    return _mk(session, tenant, **kwargs)


def test_month_end_tick_is_the_last_weekday_at_end_of_day() -> None:
    # 2026-01-31 is a SATURDAY, so January's grid point is Friday the 30th — the QS-11 `preceding`
    # roll. The instant is END of day: the tick becomes the exposure run's `as_of_valid_at`, and a
    # midnight tick would sit before every same-day mark's `valid_from` (invisible → FAILED run).
    tick = current_tick(
        _ANCHOR, None, datetime(2026, 2, 3, tzinfo=UTC), cadence_kind=CADENCE_CALENDAR_MONTH_END
    )
    assert tick.date() == dt_date(2026, 1, 30)
    assert (tick.hour, tick.minute, tick.second) == (23, 59, 59)


def test_month_end_tick_is_monotone_and_never_ahead_of_now() -> None:
    # The bucket must be a pure, monotone function of `now` — two concurrent polls in the same
    # bucket MUST agree, or `uq(schedule_id, scheduled_for)` stops colliding (a silent double-fire).
    seen: list[datetime] = []
    probe = datetime(2026, 1, 1, tzinfo=UTC)
    while probe < datetime(2027, 1, 1, tzinfo=UTC):
        tick = current_tick(_ANCHOR, None, probe, cadence_kind=CADENCE_CALENDAR_MONTH_END)
        assert tick <= probe
        if not seen or tick != seen[-1]:
            assert not seen or tick > seen[-1]  # strictly increasing bucket sequence
            seen.append(tick)
        probe += timedelta(hours=6)
    assert len(seen) == 12  # one grid point per calendar month


def test_month_end_grid_refuses_a_tick_from_before_the_anchor(session: Session) -> None:
    """The SCH-2 blocking defect: under INTERVAL, `tick >= anchor` was held STRUCTURALLY by
    `current_tick`'s `k < 0` clamp. A calendar grid is not anchor-generated, so without an explicit
    tick-vs-anchor test a schedule anchored mid-month fires the PREVIOUS month's grid point — a
    backfill of a period before the schedule existed, which under the tick→as-of rule would mint a
    governed run dated before the book was configured. 93% of 2026 anchor dates hit this."""
    tenant = str(uuid.uuid4())
    sched = _mk_month_end(session, tenant, anchor_date=dt_date(2026, 1, 5))
    just_after_creation = datetime(2026, 1, 6, tzinfo=UTC)

    tick = current_tick(
        sched.anchor_date, None, just_after_creation, cadence_kind=CADENCE_CALENDAR_MONTH_END
    )
    assert tick.date() == dt_date(2025, 12, 31)  # the pre-anchor grid point is what the grid yields
    assert is_due(sched, just_after_creation, fired_ticks=set()) is False
    with pytest.raises(ScheduleError, match="outside the start boundary"):
        _assert_current_tick(sched, tick, just_after_creation)

    # ...and the FIRST legitimate fire is January's month-end, discovered in February.
    in_february = datetime(2026, 2, 2, tzinfo=UTC)
    first = current_tick(
        sched.anchor_date, None, in_february, cadence_kind=CADENCE_CALENDAR_MONTH_END
    )
    assert first.date() == dt_date(2026, 1, 30)
    assert is_due(sched, in_february, fired_ticks=set()) is True
    _assert_current_tick(sched, first, in_february)  # must not raise


def test_interval_cadence_still_refuses_a_future_tick_before_the_anchor(session: Session) -> None:
    """The other leg of the start boundary, kept: under INTERVAL the clamp makes `tick == anchor`
    when `now` precedes the anchor — which satisfies the tick-vs-anchor test while being a tick in
    the FUTURE. Both legs are required; replacing rather than adding regressed this."""
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant, anchor_date=dt_date(2026, 3, 1))
    assert is_due(sched, datetime(2026, 1, 15, tzinfo=UTC), fired_ticks=set()) is False


def test_current_tick_fails_closed_on_a_bad_cadence_or_missing_interval() -> None:
    """`current_tick` runs on the POLL path, and `select_active_due` is evaluated in the worker's
    `for` header OUTSIDE the per-schedule SAVEPOINT — so a raw TypeError here would abort ALL FOUR
    tick phases for the tenant. Every exit must be a clean ScheduleError."""
    with pytest.raises(ScheduleError, match="unknown cadence_kind"):
        current_tick(_ANCHOR, 7, datetime(2026, 6, 1, tzinfo=UTC), cadence_kind="NOPE")
    with pytest.raises(ScheduleError, match="interval_days is required"):
        current_tick(_ANCHOR, None, datetime(2026, 6, 1, tzinfo=UTC))


def test_month_end_schedule_forbids_interval_days_and_model_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    with pytest.raises(ScheduleError, match="interval_days is meaningless"):
        _mk_month_end(session, tenant, interval_days=7)
    with pytest.raises(ScheduleError, match="model-less"):
        _mk_month_end(session, tenant, model_version_id=_seed_model_version(session, tenant))


def test_var_family_still_requires_a_model_version(session: Session) -> None:
    """The CTRL-003 inventory-before-use rule is gated on the registry DECLARATION, never on
    whether the caller supplied a value — `if model_version_id:` would be a fail-open."""
    tenant = str(uuid.uuid4())
    with pytest.raises(ScheduleError, match="model_version_id is required"):
        _mk(session, tenant, model_version_id=None)


def test_interval_cadence_still_requires_a_positive_interval(session: Session) -> None:
    tenant = str(uuid.uuid4())
    with pytest.raises(ScheduleError, match="positive integer"):
        _mk(session, tenant, interval_days=None)
    with pytest.raises(ScheduleError, match="positive integer"):
        _mk(session, tenant, interval_days=0)


def test_the_schedulable_set_is_derived_from_the_registry() -> None:
    """One source for the family gate (SCH-2): `events` no longer defines a second list, and the
    schedule's family key IS the real `calculation_run.run_type` (OQ-SCH-2-8)."""
    assert SCHEDULABLE_RUN_TYPES == frozenset(FAMILY_REGISTRY)
    assert SCHEDULABLE_RUN_TYPES == {"VAR", "EXPOSURE_AGGREGATE"}
    assert FAMILY_REGISTRY["VAR"].requires_model_version is True
    assert FAMILY_REGISTRY["EXPOSURE_AGGREGATE"].requires_model_version is False
    # EXPOSURE has no upstream to resolve, so its failures are POST-create (a committed run).
    assert FAMILY_REGISTRY["EXPOSURE_AGGREGATE"].produces_run_on_failure is True


# ------------------------------------------------------------------ the corrected fence sweep ---
#: The REAL inbound importers of ``risk``/``exposure`` (SCH-2, OD-SCH-2-F). The draft claimed
#: `scheduling` was the first violator of those packages' "nothing imports me" docstrings; the
#: verifier refuted it, and an AST scan of the tree confirmed the true set below. Two entries are
#: structural and will never shrink: ``models.py`` is the metadata aggregator (it must import every
#: package), and ``demo`` is the orchestration layer that drives all of them.
_RISK_IMPORTERS = frozenset({"models.py", "demo", "snapshot", "limit", "scheduling"})
_EXPOSURE_IMPORTERS = frozenset({"models.py", "demo", "snapshot", "risk", "scheduling"})


def _inbound_importers(target: str) -> set[str]:
    """Every package (or top-level module) outside ``target`` importing ``irp_shared.<target>``."""
    import ast

    import irp_shared

    root = pathlib.Path(irp_shared.__file__).parent
    found: set[str] = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        owner = rel.parts[0] if len(rel.parts) > 1 else rel.name
        if owner == target:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            for module in modules:
                parts = module.split(".")
                if len(parts) >= 2 and parts[0] == "irp_shared" and parts[1] == target:
                    found.add(owner)
    return found


@pytest.mark.parametrize(
    ("target", "expected"),
    [("risk", _RISK_IMPORTERS), ("exposure", _EXPOSURE_IMPORTERS)],
)
def test_no_new_package_imports_risk_or_exposure(target: str, expected: frozenset[str]) -> None:
    """The narrow-but-true replacement for two docstring claims that had quietly become false
    (OQ-SCH-2-5 = APPROVE, re-scoped).

    **What this closes:** a NEW package reaching into ``risk``/``exposure`` now turns a test red
    instead of silently widening the dependency graph, and the two package docstrings now describe
    the tree that exists.

    **What it does NOT close, stated rather than glossed:** the whitelist is by PACKAGE, so each
    entry blanket-exempts everything inside it — a new module inside ``snapshot`` or ``demo`` may
    still import freely. Set equality (not a subset check) is deliberate: if an importer goes away,
    this test fails and the whitelist shrinks with the truth rather than drifting stale.
    """
    assert _inbound_importers(target) == set(expected)
