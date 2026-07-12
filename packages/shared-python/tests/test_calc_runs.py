"""Unit tests for the shared calculation-run resolvers (RD-1 dedup — `irp_shared.calc.runs`).

The eight `resolve_*_run` family wrappers + the two `_resolve_run` guards are each exercised
end-to-end by their own family suites; this pins the SHARED contract directly: the tenant +
run_type predicate, the injectable `not_visible` / `error` classes, and the COMPLETED assertion.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.runs import resolve_completed_run_of_type, resolve_run_of_type
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.models import Base


class _NotVisible(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id} not visible")
        self.run_id = run_id


class _InputError(Exception):
    pass


@pytest.fixture
def session() -> Iterator[Session]:
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


def _mint(db: Session, tenant: str, run_type: str, *, status: str) -> str:
    run = CalculationRun(
        tenant_id=tenant,
        run_type=run_type,
        status=status,
        initiated_by="seed",
        code_version="v1",
        environment_id="test",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db.add(run)
    db.flush()
    return str(run.run_id)


def test_resolve_run_of_type_found_and_fail_closed(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    rid = _mint(session, tenant, "VAR", status="COMPLETED")
    got = resolve_run_of_type(
        session, rid, acting_tenant=tenant, run_type="VAR", not_visible=_NotVisible
    )
    assert str(got.run_id) == rid
    # wrong tenant, wrong run_type, and unknown id each fail closed via the injected class.
    for kwargs in (
        {"acting_tenant": other, "run_type": "VAR"},  # foreign tenant
        {"acting_tenant": tenant, "run_type": "SCENARIO"},  # wrong run_type
    ):
        with pytest.raises(_NotVisible):
            resolve_run_of_type(session, rid, not_visible=_NotVisible, **kwargs)
    with pytest.raises(_NotVisible):
        resolve_run_of_type(
            session,
            str(uuid.uuid4()),
            acting_tenant=tenant,
            run_type="VAR",
            not_visible=_NotVisible,
        )


def test_resolve_run_of_type_surfaces_a_failed_run(session: Session) -> None:
    # A committed FAILED run is SURFACED (the durable refusal evidence), not hidden.
    tenant = str(uuid.uuid4())
    rid = _mint(session, tenant, "VAR", status="FAILED")
    got = resolve_run_of_type(
        session, rid, acting_tenant=tenant, run_type="VAR", not_visible=_NotVisible
    )
    assert str(got.run_id) == rid and got.status == "FAILED"


def test_resolve_completed_run_of_type(session: Session) -> None:
    tenant = str(uuid.uuid4())
    done = _mint(session, tenant, "FACTOR_EXPOSURE", status="COMPLETED")
    running = _mint(session, tenant, "FACTOR_EXPOSURE", status="RUNNING")

    got = resolve_completed_run_of_type(
        session,
        done,
        acting_tenant=tenant,
        run_type="FACTOR_EXPOSURE",
        label="factor-exposure",
        error=_InputError,
    )
    assert str(got.run_id) == done

    # A non-COMPLETED run is refused via the injected error class (the pre-FK guard).
    with pytest.raises(_InputError, match="COMPLETED"):
        resolve_completed_run_of_type(
            session,
            running,
            acting_tenant=tenant,
            run_type="FACTOR_EXPOSURE",
            label="factor-exposure",
            error=_InputError,
        )
    # A missing/wrong-type run is the SAME injected error class (not the not-visible class).
    with pytest.raises(_InputError, match="not a visible"):
        resolve_completed_run_of_type(
            session,
            str(uuid.uuid4()),
            acting_tenant=tenant,
            run_type="FACTOR_EXPOSURE",
            label="factor-exposure",
            error=_InputError,
        )
