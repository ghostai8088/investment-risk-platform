"""REPRO-2 — the worker finds its tenants in the registry, and every disposition is proven.

The ONBOARD-1a carry in one sentence: a tenant created over HTTP did not tick until somebody
hand-edited `IRP_TENANT_IDS` and rolled the worker. This is the slice where that stops being true,
and the reason it needed a ratified supersession rather than a patch is that CAD-1's refuse-on-
empty was protecting something real — *"a silently-idle engine is the exact failure this slice
exists to prevent"*.

So the tests below are organized around that property surviving. Config could not distinguish
"nobody has onboarded yet" from "your config is wrong"; the registry can, and each of those
states now has a named disposition with a test. The one quiet state — a fresh platform with no
tenants — is quiet on purpose and says so at WARNING every cycle.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.models import Base
from irp_shared.tenancy.models import (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    TENANT_STATUS_SYSTEM,
    Tenant,
)
from irp_worker.discovery import (
    DiscoveryConfig,
    TenantDiscoveryError,
    active_tenant_ids,
    resolve_tick_tenants,
)
from irp_worker.supervisor import run_supervisor_discovering


@pytest.fixture
def factory():  # noqa: ANN201
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


def _tenant(session: Session, *, status: str = TENANT_STATUS_ACTIVE) -> str:
    tid = str(uuid.uuid4())
    session.add(
        Tenant(
            id=tid,
            code=f"t{uuid.uuid4().hex[:8]}",
            display_name="T",
            status=status,
            provenance="ONBOARDED",
        )
    )
    session.flush()
    return tid


# ------------------------------------------------------------------- what the registry answers
def test_an_ONBOARDED_tenant_is_discovered_with_NO_config(factory) -> None:  # noqa: ANN001
    """THE carry, discharged. Nothing was configured; the tenant ticks because it EXISTS."""
    with factory() as session:
        tid = _tenant(session)
        session.commit()
        assert active_tenant_ids(session) == [tid]
        assert resolve_tick_tenants(session, DiscoveryConfig()) == [tid]


def test_SUSPENDED_and_SYSTEM_are_never_discovered(factory) -> None:  # noqa: ANN001
    """The discriminating twin: discovery is not "every row in the table"."""
    with factory() as session:
        active = _tenant(session)
        _tenant(session, status=TENANT_STATUS_SUSPENDED)
        _tenant(session, status=TENANT_STATUS_SYSTEM)
        session.commit()
        assert active_tenant_ids(session) == [active]


def test_a_SUSPENDED_tenant_STOPS_being_discovered(factory) -> None:  # noqa: ANN001
    """Suspension is a decision somebody made, and the worker honors it within one cycle."""
    with factory() as session:
        tid = _tenant(session)
        session.commit()
        assert active_tenant_ids(session) == [tid]
        session.get(Tenant, tid).status = TENANT_STATUS_SUSPENDED
        session.commit()
        assert active_tenant_ids(session) == []


# ------------------------------------------------------------------ the restriction filter
def test_the_filter_PINS_a_subset_and_excludes_the_rest(factory) -> None:  # noqa: ANN001
    """The affirmative semantics: a set filter ticks exactly the pinned subset.

    Named because the record's first draft dropped this proof in a rewrite — leaving the filter's
    whole reason for continuing to exist bound by no test at all.
    """
    with factory() as session:
        pinned = _tenant(session)
        unpinned = _tenant(session)
        session.commit()
        got = resolve_tick_tenants(session, DiscoveryConfig(restrict_to=(pinned,)))
        assert got == [pinned]
        assert unpinned not in got, "an unpinned ACTIVE tenant was ticked anyway"


def test_a_filter_naming_an_UNKNOWN_tenant_REFUSES(factory) -> None:  # noqa: ANN001
    """The CAD-1 FOLD-2 behavior, RETAINED where it was actually protecting something.

    A filter that names a tenant the registry does not know is a definite misconfiguration, and
    silently ticking the remainder would be the looks-configured-but-isn't state.
    """
    with factory() as session:
        known = _tenant(session)
        session.commit()
        with pytest.raises(ValueError, match="does not know"):
            resolve_tick_tenants(session, DiscoveryConfig(restrict_to=(known, str(uuid.uuid4()))))


def test_a_filter_intersecting_to_NOTHING_REFUSES(factory) -> None:  # noqa: ANN001
    """A fortiori: every id unknown. This must never read as "no restriction"."""
    with factory() as session:
        _tenant(session)
        session.commit()
        with pytest.raises(ValueError):
            resolve_tick_tenants(session, DiscoveryConfig(restrict_to=(str(uuid.uuid4()),)))


def test_a_pinned_tenant_SUSPENDED_is_dropped_not_a_refusal(factory, caplog) -> None:  # noqa: ANN001
    """The collision input the review caught: SUSPENDED-and-pinned is not UNKNOWN.

    The ratified table keeps two rows apart — "unknown to the registry → refuse to start" and
    "SUSPENDED → never ticked" — and the first draft conflated them by refusing anything not
    listed as ACTIVE. Under that conflation, suspending ONE pinned tenant mid-run (a legitimate
    governed act) raised out of the discovery step and killed the engine for every OTHER pinned
    tenant: a crash-loop bought with a suspension. The known-but-inactive tenant drops out of the
    tick set instead — loudly, every cycle — and comes back within one cycle of reactivation.
    """
    with factory() as session:
        live = _tenant(session)
        pinned_suspended = _tenant(session, status=TENANT_STATUS_SUSPENDED)
        session.commit()
        with caplog.at_level("WARNING"):
            got = resolve_tick_tenants(
                session, DiscoveryConfig(restrict_to=(live, pinned_suspended))
            )
        assert got == [live], "the live pinned tenant must keep ticking through the suspension"
        assert any(
            "does not list as ACTIVE" in r.getMessage() for r in caplog.records
        ), "the dropped pinned tenant was not announced"


def test_a_filter_pinning_ONLY_suspended_tenants_idles_it_does_not_refuse(  # noqa: ANN201
    factory,
    caplog,  # noqa: ANN001
) -> None:
    """All pinned tenants suspended: the tick set is honestly empty, and the loop idles LOUDLY
    with the restriction-specific announcement — reactivation resumes ticking within one cycle,
    which a refusal (a dead process) could never deliver."""
    with factory() as session:
        pinned = _tenant(session, status=TENANT_STATUS_SUSPENDED)
        _tenant(session)  # another ACTIVE tenant exists, so "no ACTIVE tenants" would be false
        session.commit()
        assert resolve_tick_tenants(session, DiscoveryConfig(restrict_to=(pinned,))) == []

    with caplog.at_level("WARNING"):
        run_supervisor_discovering(
            factory,
            DiscoveryConfig(restrict_to=(pinned,)),
            interval_seconds=1,
            code_version="test",
            sleep=lambda _s: None,
            max_cycles=2,
            run_tick=lambda *a, **k: None,  # noqa: ARG005
        )
    assert any(
        "pins no ACTIVE tenant" in r.getMessage() for r in caplog.records
    ), "the restricted-idle state was not announced"


# ----------------------------------------------------------- the read itself, and its failure
def test_an_UNREADABLE_registry_is_NOT_zero_tenants() -> None:
    """The distinction the whole supersession rests on.

    "I asked and the answer was none" and "I could not ask" are opposite facts, and a discovery
    function that returned [] for both would hand the caller a silent idle on a broken database —
    which is precisely the failure CAD-1's refusal existed to prevent, reached by a new road.
    """
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    broken = make_session_factory(engine)()  # no schema created: the table does not exist
    with pytest.raises(TenantDiscoveryError):
        active_tenant_ids(broken)
    broken.close()
    engine.dispose()


# ------------------------------------------------------------------------- the loop's states
def test_zero_ACTIVE_tenants_IDLES_LOUDLY_and_keeps_polling(factory, caplog) -> None:  # noqa: ANN001
    """The one legitimately quiet state — and it is not silent.

    A fresh platform has no tenants. Crash-looping here would make ONBOARD-1's ignition depend on
    restart orchestration; idling SILENTLY would be the defect CAD-1 refused. So it idles and says
    so, every cycle, at WARNING.
    """
    ticked: list[str] = []
    with caplog.at_level("WARNING"):
        cycles = run_supervisor_discovering(
            factory,
            DiscoveryConfig(),
            interval_seconds=1,
            code_version="test",
            sleep=lambda _s: None,
            max_cycles=3,
            run_tick=lambda *a, **k: ticked.append("x"),  # noqa: ARG005
        )
    assert cycles == 3
    assert ticked == [], "an empty registry ticked something"
    idle_lines = [r for r in caplog.records if "idle" in r.getMessage()]
    assert len(idle_lines) == 3, "the idle state was not announced every cycle"


def test_a_tenant_onboarded_MID_RUN_is_picked_up_next_cycle(factory) -> None:  # noqa: ANN001
    """Re-reading per cycle is the carry's actual content: no restart, no config edit."""
    seen: list[list[str]] = []
    created: list[str] = []

    def _tick(session, tenant_id, **_k):  # noqa: ANN001, ANN202
        seen.append(tenant_id)
        # The cycle logs counts off the result, so the shape must be the real one.
        return {"scheduled": [], "breached": [], "escalated": [], "notified": []}

    def _sleep(_s: float) -> None:
        if not created:
            with factory() as session:
                created.append(_tenant(session))
                session.commit()

    run_supervisor_discovering(
        factory,
        DiscoveryConfig(),
        interval_seconds=1,
        code_version="test",
        sleep=_sleep,
        max_cycles=3,
        run_tick=_tick,
    )
    assert created and seen == [created[0], created[0]], (
        "a tenant onboarded between cycles was not picked up — the registry is being read once, "
        "not per cycle"
    )


def test_an_unreadable_registry_SKIPS_the_cycle_and_ticks_NOTHING(factory, caplog) -> None:  # noqa: ANN001
    """Never mistaken for an empty platform: nothing ticks, and the error is distinct."""
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    broken_factory = make_session_factory(engine)  # no schema: reads raise
    ticked: list[str] = []
    with caplog.at_level("ERROR"):
        run_supervisor_discovering(
            broken_factory,
            DiscoveryConfig(),
            interval_seconds=1,
            code_version="test",
            sleep=lambda _s: None,
            max_cycles=2,
            run_tick=lambda *a, **k: ticked.append("x"),  # noqa: ARG005
        )
    engine.dispose()
    assert ticked == []
    assert any("could not be read" in r.getMessage() for r in caplog.records)


def test_a_registry_failure_STREAK_escalates(factory, caplog) -> None:  # noqa: ANN001
    """The scalar counter, and why it is not the per-tenant one: a failed registry read yields no
    tenant id to key a streak on, so the existing machinery had nothing to count."""
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    broken_factory = make_session_factory(engine)
    with caplog.at_level("WARNING"):
        run_supervisor_discovering(
            broken_factory,
            DiscoveryConfig(),
            interval_seconds=1,
            code_version="test",
            sleep=lambda _s: None,
            max_cycles=4,
            run_tick=lambda *a, **k: None,  # noqa: ARG005
        )
    engine.dispose()
    assert any(
        "consecutive cycles" in r.getMessage() for r in caplog.records
    ), "a persistently unreadable registry never escalated"
