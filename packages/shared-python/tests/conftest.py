"""Shared test fixtures: in-memory SQLite session and entitlement seeding helpers."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import (
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@dataclass(frozen=True)
class SeedResult:
    principal: Principal
    tenant_id: str
    permission_code: str


SeedFn = Callable[..., SeedResult]


@pytest.fixture
def seed(session: Session) -> SeedFn:
    """Create a user (and optionally a role/permission/grant) and return a principal."""

    def _seed(
        permission_code: str = "foundation.read",
        *,
        with_permission: bool = True,
        with_grant: bool = True,
    ) -> SeedResult:
        tenant_id = str(uuid.uuid4())
        user = AppUser(
            tenant_id=tenant_id, external_subject=f"sub-{uuid.uuid4()}", display_name="Test User"
        )
        role = Role(tenant_id=tenant_id, code="role-1", name="Role 1")
        session.add_all([user, role])
        session.flush()

        if with_permission:
            permission = Permission(code=permission_code, description="test permission")
            session.add(permission)
            session.flush()
            session.add(RolePermission(role_id=role.id, permission_id=permission.id))
            session.flush()

        if with_grant:
            session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
            session.flush()

        return SeedResult(
            Principal(user_id=user.id, tenant_id=tenant_id), tenant_id, permission_code
        )

    return _seed


@pytest.fixture(scope="module")
def pg_role_permission_guard():  # noqa: ANN201
    """Delete the ``role_permission`` rows a PG suite creates, and ONLY those.

    **Why this exists.** CI's migration job ends with `alembic downgrade base`, and migration 0002's
    downgrade deletes the seeded `permission` catalog. Any surviving `role_permission` row
    referencing it fails with

        update or delete on table "permission" violates foreign key constraint
        "fk_role_permission_permission_id_permission"

    so a suite that grants a permission and leaves the wiring behind breaks the downgrade smoke for
    everything after it. Two suites (`test_breach_lifecycle_pg`, `test_notification_pg`) do exactly
    that; it went unnoticed only because neither suite ran in CI until the CI-parity hardening slice
    added them.

    **Why snapshot-then-delete-new** rather than matching a role-code prefix or a tenant list: it is
    exact by construction. It removes precisely the rows that appeared while this module ran, so it
    can neither miss a row (a code-pattern guess would) nor delete a row it does not own (the
    ratified "clean up only what this run seeded" discipline). Request it from a module-scoped
    fixture so the snapshot is taken before the suite writes anything.
    """
    url = os.environ.get("IRP_TEST_DATABASE_URL")
    if not url:  # non-PG run: nothing to guard
        yield
        return
    from sqlalchemy import text as _text
    from sqlalchemy.pool import NullPool

    engine = make_engine(url, poolclass=NullPool)

    def _ids() -> set[str] | None:
        """Current role_permission ids, or None when the table is absent (an unmigrated database).
        Degrading to a no-op matters: without it this guard raises a confusing
        'relation role_permission does not exist' that masks the suite's own, clearer failure —
        and a guard has no business being the first thing that breaks."""
        try:
            with engine.begin() as conn:
                return {r[0] for r in conn.execute(_text("SELECT id FROM role_permission")).all()}
        except Exception:
            return None

    before = _ids()
    try:
        yield
    finally:
        after = _ids()
        if before is not None and after is not None:
            created = after - before
            if created:
                with engine.begin() as conn:
                    conn.execute(
                        _text("DELETE FROM role_permission WHERE id = ANY(:ids)"),
                        {"ids": list(created)},
                    )
        engine.dispose()
