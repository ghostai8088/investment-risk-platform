"""The demo seed binds the documented OIDC subjects (SSO-1, closes OD-048).

The Keycloak realm (`infra/keycloak/`) and its runbook depend on these exact `external_subject`
strings resolving to the demo principals; a typo would silently break the documented `sub` →
`app_user` binding, so it is pinned here.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.demo.campaign import DEMO_TENANT_ID, _seed_principals
from irp_shared.entitlement.models import AppUser
from irp_shared.models import Base


def test_seed_principals_sets_documented_external_subjects() -> None:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        _seed_principals(db)
        subjects = set(
            db.execute(
                select(AppUser.external_subject).where(AppUser.tenant_id == DEMO_TENANT_ID)
            ).scalars()
        )
        assert subjects == {"demo-validator", "demo-registrar"}
    finally:
        db.close()
        engine.dispose()
