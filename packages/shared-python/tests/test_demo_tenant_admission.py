"""The demo tenant must be ADMITTED, or the demo cannot be opened at all.

**The defect this file exists for.** `run_demo_campaign` seeded a rich governed book — sixteen
models, forty-nine runs, backtests, validations — and never put its tenant in the ENT-074 registry.
That row was written only inside demo stage 24, `_register_and_schedule_reproduction`, so admission
was a SIDE EFFECT of a reproduction-scheduling stage that nobody following the documented entry
point (`scripts/run_demo_campaign.py`) would think to invoke. `get_principal` calls
`assert_tenant_admitted` BEFORE it arms any tenant context, so on a deployed stack every request for
the demo tenant came back with the same opaque "invalid credentials" a bad password gets.

Found by deploying the stack and trying to open the demo.

**Why nothing caught it, and why these tests are here rather than only in the `_pg` file.**
`assert_tenant_admitted` is a documented no-op off PostgreSQL, and every backend endpoint test runs
on SQLite — so the check that would have failed never executed at the unit tier. The `_pg` file
proves the real gate accepts the tenant; THIS file proves the campaign is what created the row.

**And the residue trap, which cost a mutant.** The first version of this proof lived only in
`test_demo_campaign_pg.py`, whose fixture deliberately tolerates an already-seeded demo tenant. Run
it against a database a previous seeding had touched and it passes on the LEFTOVER row — mutation
`M-DEMO-1`, which deletes the campaign's admission call outright, SURVIVED it. A test that asserts a
row exists proves nothing about who wrote it unless the database provably started without one. Every
test below builds its own empty database, and `test_the_fixture_really_starts_EMPTY` is the control
that keeps that true.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.demo.campaign import DEMO_TENANT_ID, admit_demo_tenant, run_demo_campaign
from irp_shared.models import Base
from irp_shared.tenancy.models import ADMITTED_TENANT_STATUSES, Tenant


@pytest.fixture
def fresh() -> Session:
    """A database that provably contains no tenant at all.

    Function-scoped and in-memory on purpose: the point of this file is that the row under test was
    created by the code under test, and a shared or reused database cannot support that claim.
    """
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_the_fixture_really_starts_EMPTY(fresh: Session) -> None:
    """The control that makes every other test in this file causal rather than circumstantial.

    This is the assertion whose absence let `M-DEMO-1` survive. If the fixture ever starts carrying
    a tenant — a shared engine, a module-scoped session, a seeded template — the tests below stop
    proving that the campaign wrote anything and nobody would notice.
    """
    assert fresh.query(Tenant).count() == 0
    assert fresh.get(Tenant, DEMO_TENANT_ID) is None


def test_the_CAMPAIGN_admits_its_own_tenant(fresh: Session) -> None:
    """THE regression. A demo seeded through the documented entry point must be openable.

    Delete the `admit_demo_tenant(session)` call from `run_demo_campaign` and this fails — which is
    exactly what it is for, and exactly what the `_pg`-only version of this proof did not do.
    """
    assert fresh.get(Tenant, DEMO_TENANT_ID) is None  # stated again AT the point of use

    run_demo_campaign(fresh)
    fresh.flush()

    row = fresh.get(Tenant, DEMO_TENANT_ID)
    assert row is not None, (
        "the campaign seeded a whole governed book and left its tenant out of the ENT-074 "
        "registry — every HTTP request for it will 401 at the admission check, and the demo "
        "cannot be opened at all"
    )
    assert row.status in ADMITTED_TENANT_STATUSES, f"registered but NOT admitted: {row.status}"
    assert row.code == "demo"


def test_the_tenant_is_admitted_BEFORE_its_principals_exist(
    fresh: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Order matters, and this test had to be REWRITTEN because its first version could not fire.

    The claim: a tenant is admitted when it is created, not when a later stage happens to need it.
    Asserting only "the row exists after the campaign" would still pass if admission drifted to the
    END of the campaign — the same latent shape this fix exists to kill, just harder to trip over.

    **The first version asserted nothing of the sort.** It called ``admit_demo_tenant`` directly
    and checked that no ``AppUser`` existed — both trivially true on a fresh database, under ANY
    campaign ordering. Four review lanes caught it and each reproduced the same way: move the
    admission call to the end of ``run_demo_campaign`` and all five tests in this file still pass.
    A could-never-fire guard (P9) inside the file whose entire purpose is causal proof, with a
    docstring claiming it prevented exactly the drift it could not see.

    The fix is a SEAM. ``_seed_principals`` is the first thing the campaign does after admitting, so
    wrapping it lets the assertion run AT that moment, inside the real campaign, against the real
    session. If admission moves after it, the wrapper sees no tenant and fails.
    """
    from irp_shared.demo import campaign as campaign_mod

    seen: dict[str, object] = {}
    original = campaign_mod._seed_principals

    def _spy(session: Session):  # noqa: ANN202 - a test seam
        seen["tenant_at_principal_time"] = session.get(Tenant, DEMO_TENANT_ID)
        return original(session)

    monkeypatch.setattr(campaign_mod, "_seed_principals", _spy)
    run_demo_campaign(fresh)
    fresh.flush()

    assert "tenant_at_principal_time" in seen, (
        "the seam never ran — `_seed_principals` is no longer the campaign's first step after "
        "admission, so this test is measuring nothing and must be re-aimed rather than deleted"
    )
    assert seen["tenant_at_principal_time"] is not None, (
        "the campaign created its principals BEFORE admitting its tenant — admission has drifted "
        "back to being a late side effect, which is the exact shape this fix removed"
    )


def test_admission_is_IDEMPOTENT_because_TWO_callers_share_it(fresh: Session) -> None:
    """`run_demo_campaign` and demo stage 24 both call this writer. The second call must be a
    no-op rather than a duplicate-key error — stage 24 exists to be runnable on a database the
    campaign has already touched."""
    assert admit_demo_tenant(fresh) is True  # created
    fresh.flush()
    assert admit_demo_tenant(fresh) is False  # already there
    assert admit_demo_tenant(fresh) is False
    assert fresh.query(Tenant).filter(Tenant.id == DEMO_TENANT_ID).count() == 1


def test_the_REPRO_stage_also_admits_on_a_database_the_campaign_never_touched(
    fresh: Session,
) -> None:
    """The other caller, proven independently.

    Stage 24 is runnable on its own, and it needs the registry row for a different reason: since
    REPRO-2 the supervisor discovers ACTIVE tenants from the registry, so an unregistered tenant is
    one the engine never visits. Centralising the writer must not have taken that away from it.
    """
    from irp_shared.demo.campaign import _register_and_schedule_reproduction

    assert fresh.get(Tenant, DEMO_TENANT_ID) is None
    _register_and_schedule_reproduction(fresh, "registrar-1")
    fresh.flush()

    row = fresh.get(Tenant, DEMO_TENANT_ID)
    assert row is not None, "stage 24 no longer admits the tenant — the worker will never visit it"
    assert row.status in ADMITTED_TENANT_STATUSES
