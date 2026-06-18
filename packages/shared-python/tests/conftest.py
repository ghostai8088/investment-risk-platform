"""Shared test fixtures: in-memory SQLite session and entitlement seeding helpers."""

from __future__ import annotations

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
