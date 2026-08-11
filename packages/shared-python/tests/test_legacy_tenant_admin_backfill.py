"""Wave-17 close, D3: the legacy-tenant `tenant_admin` backfill (migration 0069).

**The claim being proven is not "the migration runs".** It is that a tenant which could not reach
its own administration screen now can. So the test builds the legacy shape — a registry row and
principals, and NO `tenant_admin` role, which is exactly what migration `0067` leaves behind and
what the demo campaign creates — asserts the feature is unreachable, runs the backfill, and asserts
it is reachable.

The negative half is the load-bearing half. Without it this file would pass on a migration that
created the role for every tenant unconditionally, or on one that created it and granted nothing.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import (
    ROLE_TEMPLATES,
    permission_id,
    tenant_role_id,
)
from irp_shared.entitlement.models import Permission, Role, RolePermission
from irp_shared.models import Base
from irp_shared.tenancy.models import Tenant

_ROOT = Path(__file__).resolve().parents[3]


def _migration():
    """Import the revision by path — it is not on `sys.path` and has a non-identifier name."""
    path = _ROOT / "migrations" / "versions" / "0069_legacy_tenant_admin.py"
    spec = importlib.util.spec_from_file_location("_m0069", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_m0069"] = module
    spec.loader.exec_module(module)
    return module


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


def _legacy_tenant(session: Session) -> str:
    """A tenant in the shape migration 0067 leaves behind: registered, and role-less."""
    tenant_id = str(uuid.uuid4())
    session.add(
        Tenant(
            id=tenant_id,
            code=f"backfilled-{tenant_id[:8]}",
            display_name="A tenant from before ONBOARD-1",
            status="ACTIVE",
            provenance="BACKFILLED",
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )
    # The four verbs exist as permissions — 0068 delivered them. That is precisely why the gap was
    # invisible: nothing was missing from the CATALOG, only from this tenant's roles.
    for code in ROLE_TEMPLATES.get("tenant_admin", ()):
        if session.get(Permission, permission_id(code)) is None:
            session.add(Permission(id=permission_id(code), code=code, description=code))
    session.flush()
    return tenant_id


def _admin_codes(session: Session, tenant_id: str) -> set[str]:
    """Every permission code reachable through this tenant's own `tenant_admin` role."""
    role = session.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.code == "tenant_admin")
    ).scalar_one_or_none()
    if role is None:
        return set()
    rows = session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
    ).scalars()
    return set(rows)


def test_a_legacy_tenant_cannot_administer_itself_BEFORE_the_backfill(session: Session) -> None:
    """The negative half, and it is not hypothetical — this is the demo tenant's state at HEAD."""
    tenant_id = _legacy_tenant(session)
    assert _admin_codes(session, tenant_id) == set(), (
        "a pre-0067 tenant already has a tenant_admin role, so this whole revision is a no-op and "
        "the test below proves nothing"
    )


def test_the_backfill_gives_a_legacy_tenant_its_OWN_admin_role_with_the_verbs(
    session: Session,
) -> None:
    tenant_id = _legacy_tenant(session)
    session.commit()

    roles, grants = _migration().backfill_legacy_tenant_admin(session.connection())
    session.commit()

    assert roles == 1, "the backfill created no role for a tenant that had none"
    assert grants > 0, "the role was created with no grants — a role that permits nothing"

    expected = set(ROLE_TEMPLATES["tenant_admin"])
    assert expected, "the tenant_admin template is empty; this test would pass vacuously"
    # Set EQUALITY, not containment. The RPT-3 lesson, one slice on: `granted <= expected` is true
    # when the role is empty, which is the exact state this revision exists to end.
    assert _admin_codes(session, tenant_id) == expected

    role = session.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.code == "tenant_admin")
    ).scalar_one()
    assert role.id == tenant_role_id(
        tenant_id, "tenant_admin"
    ), "the role id is not the tenant-namespaced derivation — every tenant would share one role id"


def test_the_backfill_is_idempotent_and_leaves_an_EXISTING_admin_role_alone(
    session: Session,
) -> None:
    """Re-running a migration is normal (a restored backup, a re-applied chain), and a tenant
    onboarded through the REAL path already has this role. Neither may be disturbed."""
    tenant_id = _legacy_tenant(session)
    session.commit()
    module = _migration()

    first_roles, first_grants = module.backfill_legacy_tenant_admin(session.connection())
    session.commit()
    second_roles, second_grants = module.backfill_legacy_tenant_admin(session.connection())
    session.commit()

    assert (first_roles, second_roles) == (1, 0), "the second run created the role again"
    assert first_grants > 0 and second_grants == 0, "the second run re-granted"
    assert _admin_codes(session, tenant_id) == set(ROLE_TEMPLATES["tenant_admin"])


def test_the_backfill_skips_the_SYSTEM_tenant(session: Session) -> None:
    """The SYSTEM tenant holds the TEMPLATES. Cloning a template into the tenant that owns the
    templates would put a second `tenant_admin` row under the same tenant id as the original."""
    module = _migration()
    session.add(
        Tenant(
            id=module.SYSTEM_TENANT_ID,
            code="system",
            display_name="System",
            status="ACTIVE",
            provenance="RESERVED",
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )
    session.commit()

    roles, _ = module.backfill_legacy_tenant_admin(session.connection())
    session.commit()
    assert roles == 0, "the backfill cloned a template into the tenant that OWNS the templates"
