"""End-to-end tests of the API-1 F2 read-only audit-trail endpoint (``GET /audit/events``).

SQLite has no RLS; the read's tenant fence here is the EXPLICIT ``tenant_id`` predicate in
``audit/queries.py`` (belt to the PG FORCE-RLS suspenders — the cross-tenant-isolation proof under a
non-superuser role lives in the audit PG suite). This tier pins: tenant isolation (a caller sees
ONLY its own events), the metadata filters (entity_type / entity_id / event_type), the
``[since, until]`` canonical-time window, newest-first ordering + limit/offset pagination, the
METADATA-ONLY response shape (no ``before_value``/``after_value``/``justification`` payload bodies),
the ``lineage.view`` gate (deny-by-default), and the limit bounds (422). The FROZEN
``audit/service.py`` is never touched — events are inserted directly (a read-endpoint fixture
technique; the chain writer is out of scope).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.audit import router as audit_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base

_PERMS = ("lineage.view",)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    tenant_id = str(uuid.uuid4())
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code="r", name="R")
    db.add_all([user, role])
    db.flush()
    for code in _PERMS:
        perm = Permission(code=code, description="d")
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(audit_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _ev(db: Session, tenant: str, *, seq: int, event_time: str, **kw) -> AuditEvent:  # noqa: ANN003
    """Insert one metadata-plausible audit event directly (the frozen chain writer is out of scope
    for this READ test). ``before_value``/``after_value`` are set to prove they are NOT surfaced."""
    ev = AuditEvent(
        chain_id=kw.pop("chain_id", tenant),
        sequence_no=seq,
        tenant_id=tenant,
        event_time=event_time,
        event_type=kw.pop("event_type", "MODEL.REGISTER"),
        actor_type="user",
        actor_id="u",
        source_module="model",
        entity_type=kw.pop("entity_type", "model"),
        entity_id=kw.pop("entity_id", None),
        action="register",
        before_value={"secret": "should-not-surface"},
        after_value={"secret": "should-not-surface"},
        justification="should-not-surface",
        previous_event_hash="0" * 64,
        event_payload_hash="a" * 64,
        event_hash="b" * 64,
    )
    db.add(ev)
    db.flush()
    return ev


def test_audit_read_isolation_filters_window_and_shape(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    ent = str(uuid.uuid4())
    _ev(db, p.tenant_id, seq=1, event_time="2026-07-01T00:00:00+00:00", entity_id=ent)
    _ev(
        db,
        p.tenant_id,
        seq=2,
        event_time="2026-07-10T00:00:00+00:00",
        event_type="MODEL.VALIDATE",
        entity_id=ent,
    )
    _ev(db, p.tenant_id, seq=3, event_time="2026-07-20T00:00:00+00:00")
    # A FOREIGN tenant's event — must never surface for this caller.
    _ev(db, str(uuid.uuid4()), seq=1, event_time="2026-07-15T00:00:00+00:00")
    db.commit()

    # Unfiltered: exactly this tenant's 3 events, newest-first.
    rows = client.get("/audit/events", headers=_h(p)).json()
    assert [r["event_time"] for r in rows] == [
        "2026-07-20T00:00:00+00:00",
        "2026-07-10T00:00:00+00:00",
        "2026-07-01T00:00:00+00:00",
    ]
    # Metadata-only shape: NO payload bodies leak.
    assert "before_value" not in rows[0]
    assert "after_value" not in rows[0]
    assert "justification" not in rows[0]
    assert rows[0]["data_classification"] == "DC-2"

    # event_type filter.
    validate = client.get(
        "/audit/events", params={"event_type": "MODEL.VALIDATE"}, headers=_h(p)
    ).json()
    assert len(validate) == 1 and validate[0]["event_type"] == "MODEL.VALIDATE"

    # entity_id filter (the two events on `ent`).
    by_entity = client.get("/audit/events", params={"entity_id": ent}, headers=_h(p)).json()
    assert len(by_entity) == 2

    # [since, until] canonical-time window (inclusive) — only the middle event.
    windowed = client.get(
        "/audit/events",
        params={"since": "2026-07-05T00:00:00+00:00", "until": "2026-07-15T00:00:00+00:00"},
        headers=_h(p),
    ).json()
    assert len(windowed) == 1 and windowed[0]["event_time"] == "2026-07-10T00:00:00+00:00"

    # Pagination: newest-first, limit + offset.
    page = client.get("/audit/events", params={"limit": 1, "offset": 1}, headers=_h(p)).json()
    assert len(page) == 1 and page[0]["event_time"] == "2026-07-10T00:00:00+00:00"


def test_audit_read_gating_and_limit_bounds(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    _ev(db, p.tenant_id, seq=1, event_time="2026-07-01T00:00:00+00:00")
    db.commit()
    # Deny-by-default: a principal without lineage.view is 403.
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}
    assert client.get("/audit/events", headers=stranger).status_code == 403
    # limit bounds: 0 and 201 are 422 (FastAPI Query ge/le).
    assert client.get("/audit/events", params={"limit": 0}, headers=_h(p)).status_code == 422
    assert client.get("/audit/events", params={"limit": 201}, headers=_h(p)).status_code == 422
    # No mutating verbs on the read router.
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/audit/events", headers=_h(p)).status_code == 405
