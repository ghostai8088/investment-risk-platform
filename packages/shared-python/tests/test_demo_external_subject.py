"""The demo seed binds the documented OIDC subjects + the read-only viewer grants.

The Keycloak realm (`infra/keycloak/`) and its runbook depend on the exact `external_subject`
strings resolving to the demo principals (SSO-1, closes OD-048). FE-3 adds a read-only 3L
`demo-auditor` — the persona a non-developer walks the governance narrative AS — which must hold
the FULL walk read set (or the demo shows denied panes); the 1L registrar / 2L validator keep
their maker/checker split and must NOT hold the auditor's broad reads. All three are pinned here.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID, _seed_principals
from irp_shared.entitlement.models import AppUser
from irp_shared.entitlement.service import Principal, has_permission
from irp_shared.models import Base

# The reads the FE-3 governance walk traverses; the auditor must hold all of them.
_WALK_READS = (
    "position.view",
    "valuation.view",
    "portfolio.view",
    "risk.view",
    "exposure.view",
    "perf.view",
    "model.inventory.view",
    "snapshot.view",
    "lineage.view",
)


def test_seed_principals_binds_subjects_and_viewer_grants() -> None:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        _seed_principals(db)
        db.commit()
        set_tenant_context(db, DEMO_TENANT_ID)

        by_sub = {
            u.external_subject: u
            for u in db.execute(
                select(AppUser).where(AppUser.tenant_id == DEMO_TENANT_ID)
            ).scalars()
        }
        assert set(by_sub) == {"demo-validator", "demo-registrar", "demo-auditor"}

        def held(sub: str, code: str) -> bool:
            p = Principal(user_id=by_sub[sub].id, tenant_id=DEMO_TENANT_ID)
            return has_permission(db, p, code, DEMO_TENANT_ID)

        # The read-only viewer holds the ENTIRE walk read set.
        assert all(held("demo-auditor", c) for c in _WALK_READS)
        # The maker/checker principals do NOT hold the auditor's broad governance reads (SoD split).
        assert not held("demo-registrar", "model.inventory.view")
        assert not held("demo-registrar", "snapshot.view")
        assert not held("demo-validator", "risk.view")
    finally:
        db.close()
        engine.dispose()
