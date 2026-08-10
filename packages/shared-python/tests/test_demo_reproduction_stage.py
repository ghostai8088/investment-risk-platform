"""REPRO-2 (OQ-REP2-5) — the demo tenant is DISCOVERABLE and has a sweep to run.

Carry (m) asked for the demo/deploy half of "the control is startable". Its v1 wording named a
`deploy.sh` demo seed that does not exist, and the ratification replaced it with two legs against
artifacts that DO: this one (the campaign registers the demo tenant and creates its nightly
schedule) and the deployed second-tenant arm in `prove_reproduction.sh`.

**Where the seeding lives, and why it moved.** It was first written into `run_demo_campaign`'s
body. The full-PG battery refused that: a reproduction schedule existing before stage 15 makes
that stage's tick dispatch TWO schedules where it asserts exactly one, and every downstream count
pin then came up one COMPLETED run short. Adding a schedule to a shared demo tenant is not a local
act — it changes what every subsequent tick does. It is now demo stage 24, seeded LAST, which
leaves every existing stage's meaning untouched.

**What makes this worth a test rather than a line in the campaign.** The schedule alone proves
nothing: under registry discovery a schedule belonging to an UNREGISTERED tenant is a schedule the
worker never visits — a control that exists, is believed, and never runs, which is precisely the
LQ-1 shape this project has already paid for once. So the assertions are paired: the tenant is in
the registry AND ACTIVE, and the schedule exists AND targets the reproduction run type. Either
one alone would be a green test over a dead control.

This runs on the UNIT tier (SQLite) rather than as a `_pg` demo stage, because what it checks is
the stage function's own behaviour, not an end-state of the seeded PG database — and a proof that
runs in `make check` runs on every commit rather than on the nights somebody remembers to bring up
PostgreSQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.demo.campaign import DEMO_TENANT_ID, _register_and_schedule_reproduction
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION
from irp_shared.scheduling.models import Schedule
from irp_shared.tenancy.models import TENANT_STATUS_ACTIVE, Tenant


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _registry_row(db: Session) -> Tenant | None:
    return db.get(Tenant, DEMO_TENANT_ID)


def _reproduction_schedules(db: Session) -> list[Schedule]:
    return list(
        db.execute(
            select(Schedule).where(
                Schedule.tenant_id == DEMO_TENANT_ID,
                Schedule.target_run_type == RUN_TYPE_REPRODUCTION,
            )
        )
        .scalars()
        .all()
    )


def test_the_demo_tenant_becomes_DISCOVERABLE_and_gets_a_sweep(session: Session) -> None:
    """Both halves, because either alone is a control that does not run."""
    assert _registry_row(session) is None, "the fixture started dirty"

    schedule_id = _register_and_schedule_reproduction(session, "registrar-1")
    session.flush()

    registered = _registry_row(session)
    assert registered is not None, (
        "the demo tenant is not in the ENT-074 registry, so the discovering worker will never "
        "tick it — the schedule below would be an inert control"
    )
    assert registered.status == TENANT_STATUS_ACTIVE, (
        f"the demo tenant is registered as {registered.status}, and discovery only ticks ACTIVE "
        "tenants"
    )

    schedules = _reproduction_schedules(session)
    assert len(schedules) == 1, f"expected exactly one reproduction schedule, got {len(schedules)}"
    assert schedule_id == str(schedules[0].id)
    assert schedules[0].status == "ACTIVE", "a paused seed would demo a switched-off control"


def test_the_schedule_is_created_through_the_REAL_service_not_an_INSERT(session: Session) -> None:
    """A demo that seeds around its own service demonstrates nothing about the service.

    The tell is the audit event: `create_schedule` emits a governed `SCHEDULE.CREATE`, and a bare
    `session.add(Schedule(...))` does not. This is the same distinction OPS-1 made when it found a
    demo that could not REACH the control it claimed to demonstrate.
    """
    from irp_shared.audit.models import AuditEvent

    _register_and_schedule_reproduction(session, "registrar-1")
    session.flush()

    events = list(
        session.execute(
            select(AuditEvent.event_type).where(AuditEvent.chain_id == DEMO_TENANT_ID)
        ).scalars()
    )
    assert any("SCHEDULE" in e for e in events), (
        "no SCHEDULE audit event was emitted, so the schedule was inserted rather than created "
        f"through the governed service; events seen: {sorted(set(events))}"
    )


def test_the_stage_ENTRYPOINT_refuses_a_dirty_re_run(session: Session) -> None:
    """The stage wrapper is refuse-not-skip, the campaign's standing rule: a second run of a stage
    that already landed is an operator error, not a no-op to swallow."""
    from irp_shared.demo.repro2_stage24 import (
        DemoRepro2AlreadySeededError,
        run_demo_repro2_stage24,
    )

    summary = run_demo_repro2_stage24(session, registrar_user_id="registrar-1")
    session.flush()
    assert summary.schedule_id
    with pytest.raises(DemoRepro2AlreadySeededError):
        run_demo_repro2_stage24(session, registrar_user_id="registrar-1")


def test_re_running_the_stage_is_IDEMPOTENT(session: Session) -> None:
    """A dirty re-run must not mint a second schedule.

    Two active reproduction schedules would sweep every family twice a night and double the
    verdict rows without checking anything new — and the campaign is re-run against databases in
    unknown states often enough that "it only runs once" is not a safe assumption. The second call
    returns None, which is how the caller can tell it did nothing.
    """
    first = _register_and_schedule_reproduction(session, "registrar-1")
    session.flush()
    second = _register_and_schedule_reproduction(session, "registrar-1")
    session.flush()

    assert first is not None and second is None
    assert len(_reproduction_schedules(session)) == 1, "a re-run minted a second schedule"


def test_a_PRE_EXISTING_registry_row_is_tolerated(session: Session) -> None:
    """The 0067-backfill case, which is not hypothetical.

    Migration 0067 registers every tenant that already holds `app_user` rows, and the demo tenant
    holds several — so on a re-migrated database the row is ALREADY there when the campaign runs.
    Inserting blindly would raise; this proves the stage tolerates it and still schedules.
    """
    session.add(
        Tenant(
            id=DEMO_TENANT_ID,
            code="backfilled-demo",
            display_name="Backfilled",
            status=TENANT_STATUS_ACTIVE,
            provenance="BACKFILLED",
        )
    )
    session.flush()

    schedule_id = _register_and_schedule_reproduction(session, "registrar-1")
    session.flush()

    assert schedule_id is not None, "a pre-existing registry row blocked the schedule"
    # The existing row is left ALONE — the campaign does not restate another process's facts.
    assert _registry_row(session).code == "backfilled-demo"
