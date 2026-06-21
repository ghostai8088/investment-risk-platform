"""Worker tenant-scoped job path (AD-016). Context-setting is a no-op on SQLite; the PG proof is
in packages/shared-python/tests/test_tenant_context_pg.py."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.models import Base
from irp_worker.jobs import run_tenant_job


def _factory():  # noqa: ANN202 - test helper
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_run_tenant_job_runs_work_and_commits() -> None:
    result = run_tenant_job(
        _factory(), str(uuid.uuid4()), lambda s: s.execute(text("SELECT 42")).scalar()
    )
    assert result == 42
