"""Unit tests for tenant-context helpers on SQLite (PostgreSQL RLS behaviour is in *_pg)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import (
    classify_rls_denied,
    current_tenant,
    run_in_tenant,
    set_tenant_context,
    tenant_session,
)
from irp_shared.models import Base


def _factory():  # noqa: ANN202 - test helper
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_set_tenant_context_is_noop_on_sqlite(session: Session) -> None:
    set_tenant_context(session, str(uuid.uuid4()))  # must not raise (SQLite has no GUC/RLS)


def test_current_tenant_none_on_sqlite(session: Session) -> None:
    assert current_tenant(session) is None


def test_classify_rls_denied_hook_returns_none() -> None:
    assert classify_rls_denied(RuntimeError("x")) is None


def test_tenant_session_yields_and_closes() -> None:
    with tenant_session(_factory(), str(uuid.uuid4())) as session:
        assert session.execute(text("SELECT 1")).scalar() == 1


def test_run_in_tenant_runs_work_and_returns() -> None:
    result = run_in_tenant(
        _factory(), str(uuid.uuid4()), lambda s: s.execute(text("SELECT 7")).scalar()
    )
    assert result == 7


# --- OPS-H1 (H1-6): the L4 seams canonicalize defensively ----------------------------------------


def test_tenant_session_canonicalizes_the_tenant_it_arms(monkeypatch) -> None:  # noqa: ANN001
    """`tenant_session`/`run_in_tenant`/`run_tenant_job` (the last two delegate here) arm the GUC;
    the SSO-1 standing rule does not carve out internal seams. Canonicalized, not refused — the
    canonical form of a valid UUID is correct behavior for an internal seam; a non-UUID raises.

    Observed by SPYING on ``set_tenant_context``'s actual argument (SQLite has no GUC to read
    back — a loop that arms and asserts nothing would be the vacuous-test pattern)."""
    import uuid as _uuid

    import pytest
    from sqlalchemy.pool import StaticPool

    import irp_shared.db.tenant as tenant_mod
    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.db.tenant import tenant_session

    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = make_session_factory(engine)
    received: list[str] = []
    real = tenant_mod.set_tenant_context

    def _spy(session, tenant_id):  # noqa: ANN001, ANN202
        received.append(tenant_id)
        return real(session, tenant_id)

    monkeypatch.setattr(tenant_mod, "set_tenant_context", _spy)

    canonical = str(_uuid.uuid4())
    for form in (canonical, canonical.upper(), "{" + canonical + "}"):
        with tenant_session(factory, form):
            pass
    assert received == [canonical] * 3, received  # EVERY form armed the ONE canonical string

    with pytest.raises(ValueError):
        with tenant_session(factory, "not-a-uuid"):
            pass  # pragma: no cover - the arm must raise before the body
    engine.dispose()
