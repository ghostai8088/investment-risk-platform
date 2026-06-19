"""Audit-write concurrency control + verify-all-chains tests (BR-18, OD-051; CTRL-026)."""

from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import _advisory_lock_key, record_event, verify_all_chains
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.models import Base


def _emit(session: Session, tenant: str) -> None:
    record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant,
        actor_type="user",
        actor_id="u",
        source_module="test",
        action="create",
    )


def test_advisory_lock_key_deterministic() -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert _advisory_lock_key(a) == _advisory_lock_key(a)
    assert _advisory_lock_key(a) != _advisory_lock_key(b)
    assert -(2**63) <= _advisory_lock_key(a) < 2**63  # fits PostgreSQL bigint


def test_sequential_writes_are_gapless(session: Session) -> None:
    tenant = str(uuid.uuid4())
    for _ in range(10):
        _emit(session, tenant)
    seqs = sorted(
        e.sequence_no for e in session.query(AuditEvent).filter(AuditEvent.chain_id == tenant)
    )
    assert seqs == list(range(1, 11))


def test_verify_all_chains_reports_each_tenant(session: Session) -> None:
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    for tenant in (t1, t2):
        for _ in range(3):
            _emit(session, tenant)
    reports = verify_all_chains(session)
    assert {r.chain_id for r in reports} == {t1, t2}
    assert all(r.result.ok for r in reports)


@pytest.mark.skipif(
    not os.environ.get("IRP_TEST_DATABASE_URL"),
    reason="requires PostgreSQL (set IRP_TEST_DATABASE_URL) — runs in the CI migration job",
)
def test_concurrent_writes_pg_gapless() -> None:
    """N threads writing one tenant's chain concurrently must yield gapless, unique sequence_no."""
    url = os.environ["IRP_TEST_DATABASE_URL"]
    engine = make_engine(url)
    Base.metadata.create_all(engine)  # no-op if the migration already created the schema
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    n = 20
    barrier = threading.Barrier(n)
    errors: list[Exception] = []

    def writer() -> None:
        db = factory()
        try:
            db.execute(text("SET app.current_tenant = :t"), {"t": tenant})  # RLS context
            barrier.wait()
            _emit(db, tenant)
            db.commit()
        except Exception as exc:
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=writer) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    check = factory()
    try:
        check.execute(text("SET app.current_tenant = :t"), {"t": tenant})
        seqs = sorted(
            e.sequence_no for e in check.query(AuditEvent).filter(AuditEvent.chain_id == tenant)
        )
    finally:
        check.close()
        engine.dispose()

    assert not errors, f"writer errors: {errors}"
    assert seqs == list(range(1, n + 1))  # gapless + unique under concurrency
