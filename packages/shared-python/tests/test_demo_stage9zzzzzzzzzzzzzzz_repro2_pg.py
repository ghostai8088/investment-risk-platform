"""The REPRO-2 demo-stage suite (stage 24) — the demo tenant becomes DISCOVERABLE, live on PG.

Runs LAST among the demo suites (the 15-z name sorts after every earlier one), and the position is
load-bearing rather than tidy. The seeding was first written into `run_demo_campaign`'s body; the
full-PG battery refused it, because a reproduction schedule existing before stage 15 makes that
stage's tick dispatch TWO schedules where it asserts exactly one — and every downstream count pin
then came up one COMPLETED run short. Adding a schedule to a shared demo tenant changes what every
subsequent tick does, so it goes last.

**And the SWEEP ITSELF runs here, over the whole seeded book.** That is the point of putting this
on PG at all: sixteen adapters that only ever reproduced purpose-built fixtures would be sixteen
adapters proven against data written to make them pass. The demo tenant's book was seeded by
twenty-three earlier stages for entirely unrelated reasons, and every family with a subject in it
must come back MATCH.
"""

from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_repro2_stage24
from irp_shared.demo.repro2_stage24 import DemoRepro2AlreadySeededError
from irp_shared.reproduction.events import VERDICT_MATCH
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION
from irp_shared.reproduction.registry import REPRODUCIBLE_FAMILIES
from irp_shared.reproduction.service import run_reproduction_sweep
from irp_shared.scheduling.models import Schedule
from irp_shared.tenancy.models import TENANT_STATUS_ACTIVE, Tenant

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def staged():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        from irp_shared.entitlement.models import AppUser

        registrar = session.execute(
            select(AppUser.id).where(AppUser.tenant_id == DEMO_TENANT_ID).limit(1)
        ).scalar_one()
        try:
            run_demo_repro2_stage24(session, registrar_user_id=str(registrar))
            session.commit()
        except DemoRepro2AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory
    engine.dispose()


@pytest.fixture
def db(staged):  # noqa: ANN001, ANN201
    session = staged()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def test_the_demo_tenant_is_REGISTERED_and_ACTIVE(db) -> None:  # noqa: ANN001
    """Without this the schedule below is inert: the discovering supervisor only ticks ACTIVE
    registry tenants, so an unregistered demo tenant is one the engine never visits."""
    row = db.get(Tenant, DEMO_TENANT_ID)
    assert row is not None, "the demo tenant is not in the ENT-074 registry"
    assert row.status == TENANT_STATUS_ACTIVE


def test_the_demo_tenant_has_exactly_ONE_reproduction_schedule(db) -> None:  # noqa: ANN001
    """One, not two: a second active reproduction schedule would sweep every family twice a night
    and double the verdict rows without checking anything new."""
    count = db.execute(
        select(func.count())
        .select_from(Schedule)
        .where(
            Schedule.tenant_id == DEMO_TENANT_ID,
            Schedule.target_run_type == RUN_TYPE_REPRODUCTION,
        )
    ).scalar_one()
    assert count == 1


def test_EVERY_family_reproduces_on_the_REAL_demo_book(db) -> None:  # noqa: ANN001
    """The strongest available proof of the sixteen adapters, and the one a fixture cannot give.

    Each adapter's own unit proof builds a subject run specifically to exercise it. This sweeps a
    book that twenty-three earlier stages built for entirely unrelated reasons — real chains, real
    upstream runs, real model versions — and requires every family with a subject in it to come
    back MATCH. A DIVERGED here would mean a governed number in the demo book genuinely stopped
    reproducing; an UNREPRODUCIBLE would mean an adapter cannot handle data it did not choose.
    """
    outcome = run_reproduction_sweep(
        db,
        acting_tenant=DEMO_TENANT_ID,
        actor_id="demo-stage-24",
        code_version="demo",
        environment_id="demo",
    )
    db.commit()

    assert outcome.checks, "the sweep judged NOTHING — an empty sweep proves nothing about coverage"
    bad = [
        (c.family_key, c.verdict, c.first_divergence)
        for c in outcome.checks
        if c.verdict != VERDICT_MATCH
    ]
    assert not bad, f"families did not reproduce on the seeded demo book: {bad}"
    # Non-vacuity: a MATCH over zero rows agrees with itself. At least one family must have
    # actually compared something, and in practice most of them do.
    assert (
        sum(c.rows_compared for c in outcome.checks) > 0
    ), "every verdict compared ZERO rows — the sweep agreed with itself about nothing"
    assert len(outcome.checks) >= 15, (
        f"only {len(outcome.checks)} families found a subject in the demo book; the sixteen new "
        "adapters are meant to be exercised here, not skipped"
    )


def test_the_full_sweep_completes_well_inside_the_SPLIT_TRIGGER(db) -> None:  # noqa: ANN001
    """The ratified R5 acceptance, measured rather than argued.

    A 19-family sweep re-executes every binder sequentially inside the tick's phases-1-2
    transaction, which holds the per-tenant audit advisory lock until it commits. That cost was
    ACCEPTED against a measured number, with a named trigger: a real tenant's sweep exceeding FIVE
    MINUTES moves the sweep phases out of the single transaction (a PERF-0-carries-inheriting
    change, not this slice's).

    The bound asserted here is deliberately loose — 60s against a measured ~2s on this book. It is
    a REGRESSION tripwire, not a benchmark: a tight bound would fail on a loaded CI runner and
    teach everyone to ignore it, while a 30x margin only trips on a change of kind.
    """
    started = time.monotonic()
    run_reproduction_sweep(
        db,
        acting_tenant=DEMO_TENANT_ID,
        actor_id="demo-stage-24-timing",
        code_version="demo",
        environment_id="demo",
    )
    db.commit()
    elapsed = time.monotonic() - started
    assert elapsed < 60.0, (
        f"the full {len(REPRODUCIBLE_FAMILIES)}-family sweep took {elapsed:.1f}s on the demo book "
        "— that is a change of KIND against the ~2s this was measured at, and the ratified split "
        "trigger (5 minutes on a real tenant) is now in view"
    )
