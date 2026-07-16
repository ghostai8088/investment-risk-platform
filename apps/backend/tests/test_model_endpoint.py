"""End-to-end tests of the model-registry endpoints (POST/GET; 201/200/401/403/404/422).

SQLite has no RLS, so the cross-tenant RLS-hidden 404 is proven in
``packages/shared-python/tests/test_model_registry_pg.py``; here we prove entitlement gating
(deny-by-default), server-side tenant stamping, audit emission, and the read shapes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.models import router as models_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.model.models import Model
from irp_shared.models import Base


@pytest.fixture
def client_and_principal() -> Iterator[tuple[TestClient, Principal, Session]]:
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
    for code in ("model.inventory.view", "model.inventory.register", "model.validate"):
        perm = Permission(code=code, description="d")
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


_BODY = {
    "code": "M1",
    "name": "A model",
    "model_type": "STATISTICAL",
    "version_label": "1.0.0",
    "assumptions": ["a1"],
    "limitations": ["l1"],
}


def test_register_model_201_and_audited(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    resp = client.post("/models", json=_BODY, headers=_headers(principal))
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "M1" and body["version_label"] == "1.0.0"
    # MODEL.REGISTER emitted.
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MODEL.REGISTER")
        ).scalar_one()
        == 1
    )


def test_register_stamps_caller_tenant_ignoring_body(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    forged = {**_BODY, "code": "M2", "tenant_id": str(uuid.uuid4())}  # forged tenant_id is ignored
    resp = client.post("/models", json=forged, headers=_headers(principal))
    assert resp.status_code == 201
    model = db.execute(select(Model).where(Model.code == "M2")).scalar_one()
    assert model.tenant_id == principal.tenant_id  # server-stamped, not the forged value


def test_register_without_permission_403(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    resp = client.post(
        "/models",
        json=_BODY,
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


def test_register_missing_principal_401(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, _, _ = client_and_principal
    assert client.post("/models", json=_BODY).status_code == 401


def test_list_and_get_model(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    created = client.post("/models", json=_BODY, headers=_headers(principal)).json()
    listed = client.get("/models", headers=_headers(principal))
    assert listed.status_code == 200 and any(m["code"] == "M1" for m in listed.json())
    detail = client.get(f"/models/{created['id']}", headers=_headers(principal))
    assert detail.status_code == 200
    body = detail.json()
    assert body["validation_status"] == "UNVALIDATED"
    assert body["versions"][0]["assumptions"] == ["a1"]
    assert body["versions"][0]["limitations"] == ["l1"]


def test_get_unknown_is_404_fixed_body(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    resp = client.get(f"/models/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "model not found"


def test_get_malformed_id_422(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    assert client.get("/models/not-a-uuid", headers=_headers(principal)).status_code == 422


def test_get_without_view_403(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    resp = client.get(
        "/models",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


# --- VW-1 validation endpoints ---


def _seed_registered_version(db: Session, tenant_id: str) -> tuple[str, str]:
    """Seed a Model + a REGISTERED ModelVersion directly (the generic POST /models path mints
    status=None versions, which are deliberately not validatable). Returns (model_id,
    version_id)."""
    from irp_shared.model.models import ModelVersion

    model = Model(tenant_id=tenant_id, code="risk.var.parametric", name="m", model_type="VAR")
    db.add(model)
    db.flush()
    version = ModelVersion(
        tenant_id=tenant_id, model_id=model.id, version_label="1.0.0", status="REGISTERED"
    )
    db.add(version)
    db.commit()
    return model.id, version.id


_VALIDATION_BODY = {
    "validation_type": "INITIAL",
    "outcome": "APPROVED",
    "scope_summary": "Reviewed conceptual soundness, implementation testing, and outcomes.",
    "next_review_due": "2027-06-01",
    "findings": [{"finding_text": "minor documentation gap", "severity": "LOW"}],
}


def test_record_validation_201_and_audited(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    model_id, version_id = _seed_registered_version(db, principal.tenant_id)
    resp = client.post(
        f"/models/{model_id}/versions/{version_id}/validations",
        json=_VALIDATION_BODY,
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["outcome"] == "APPROVED"
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MODEL.VALIDATE")
        ).scalar_one()
        == 1
    )


def test_record_validation_without_validate_permission_403(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    """SOD-03: a 1L holder of register+view but NOT model.validate cannot validate."""
    client, principal, db = client_and_principal
    model_id, version_id = _seed_registered_version(db, principal.tenant_id)
    # A second user granted only register+view (the 1L author profile), not model.validate.
    author = AppUser(tenant_id=principal.tenant_id, display_name="author-1l")
    role = Role(tenant_id=principal.tenant_id, code="r1l", name="1L")
    db.add_all([author, role])
    db.flush()
    for code in ("model.inventory.view", "model.inventory.register"):
        perm = db.execute(select(Permission).where(Permission.code == code)).scalar_one()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=principal.tenant_id, user_id=author.id, role_id=role.id))
    db.commit()
    resp = client.post(
        f"/models/{model_id}/versions/{version_id}/validations",
        json=_VALIDATION_BODY,
        headers={"X-User-Id": author.id, "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


def test_record_validation_on_non_registered_version_422(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    created = client.post("/models", json=_BODY, headers=_headers(principal)).json()
    resp = client.post(
        f"/models/{created['id']}/versions/{created['version_id']}/validations",
        json=_VALIDATION_BODY,
        headers=_headers(principal),
    )
    assert resp.status_code == 422
    assert "not REGISTERED" in resp.json()["detail"]


def test_record_validation_unknown_version_404(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    model_id, _ = _seed_registered_version(db, principal.tenant_id)
    resp = client.post(
        f"/models/{model_id}/versions/{uuid.uuid4()}/validations",
        json=_VALIDATION_BODY,
        headers=_headers(principal),
    )
    assert resp.status_code == 404


def test_record_validation_cross_model_version_404(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    """A real version id that belongs to a DIFFERENT model is 404 (indistinguishable), not a
    cross-model validation write."""
    client, principal, db = client_and_principal
    model_a, _ = _seed_registered_version(db, principal.tenant_id)
    from irp_shared.model.models import ModelVersion

    other = Model(tenant_id=principal.tenant_id, code="other.model", name="m", model_type="VAR")
    db.add(other)
    db.flush()
    other_version = ModelVersion(
        tenant_id=principal.tenant_id, model_id=other.id, version_label="1.0.0", status="REGISTERED"
    )
    db.add(other_version)
    db.commit()
    resp = client.post(
        f"/models/{model_a}/versions/{other_version.id}/validations",  # version_id ∉ model_a
        json=_VALIDATION_BODY,
        headers=_headers(principal),
    )
    assert resp.status_code == 404


def test_list_validations_and_detail_latest_block(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    model_id, version_id = _seed_registered_version(db, principal.tenant_id)
    # An overdue APPROVED validation (next_review_due in the past).
    overdue_body = {**_VALIDATION_BODY, "next_review_due": "2020-01-01"}
    client.post(
        f"/models/{model_id}/versions/{version_id}/validations",
        json=overdue_body,
        headers=_headers(principal),
    )
    listed = client.get(
        f"/models/{model_id}/versions/{version_id}/validations", headers=_headers(principal)
    )
    assert listed.status_code == 200 and len(listed.json()) == 1

    detail = client.get(f"/models/{model_id}", headers=_headers(principal)).json()
    latest = detail["versions"][0]["latest_validation"]
    assert latest is not None
    assert latest["outcome"] == "APPROVED"
    assert latest["overdue"] is True  # next_review_due 2020-01-01 < today


# ---------- MG-1 (OD-MG-1-B/C): the tier endpoint + the closed 1L register-time write ----------

_TIER_BODY = {
    "materiality_rating": "HIGH",
    "complexity_rating": "MEDIUM",
    "rationale": "flagship market-risk exposure",
}


def test_assign_tier_roundtrip_and_derivation(client_and_principal) -> None:  # noqa: ANN001
    client, principal, db = client_and_principal
    created = client.post("/models", json=_BODY, headers=_headers(principal)).json()
    resp = client.post(
        f"/models/{created['id']}/tier", json=_TIER_BODY, headers=_headers(principal)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] == "TIER_1"  # derived server-side; a caller can never post a tier
    detail = client.get(f"/models/{created['id']}", headers=_headers(principal)).json()
    assert detail["tier"] == "TIER_1"


def test_assign_tier_requires_the_2l_permission(client_and_principal) -> None:  # noqa: ANN001
    # OD-MG-1-C: tier assignment rides model.validate. A register-only (1L) principal is refused —
    # the SOD fact the whole OD exists for: the author must not set his own scrutiny level.
    client, principal, db = client_and_principal
    created = client.post("/models", json=_BODY, headers=_headers(principal)).json()
    author = AppUser(tenant_id=principal.tenant_id, display_name="1L author")
    role_1l = Role(tenant_id=principal.tenant_id, code="r1l", name="register-only")
    db.add_all([author, role_1l])
    db.flush()
    perm_id = db.execute(
        select(Permission.id).where(Permission.code == "model.inventory.register")
    ).scalar_one()
    db.add(RolePermission(role_id=role_1l.id, permission_id=perm_id))
    db.add(UserRole(tenant_id=principal.tenant_id, user_id=author.id, role_id=role_1l.id))
    db.commit()
    resp = client.post(
        f"/models/{created['id']}/tier",
        json=_TIER_BODY,
        headers={"X-User-Id": author.id, "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403
    resp = client.post(
        f"/models/{created['id']}/tier",
        json=_TIER_BODY,
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403  # no roles at all


def test_assign_tier_refusals_422_and_404(client_and_principal) -> None:  # noqa: ANN001
    client, principal, _db = client_and_principal
    created = client.post("/models", json=_BODY, headers=_headers(principal)).json()
    bad = {**_TIER_BODY, "materiality_rating": "SEVERE"}
    resp = client.post(f"/models/{created['id']}/tier", json=bad, headers=_headers(principal))
    assert resp.status_code == 422
    resp = client.post(f"/models/{uuid.uuid4()}/tier", json=_TIER_BODY, headers=_headers(principal))
    assert resp.status_code == 404


def test_register_body_tier_is_ignored_and_not_stamped(client_and_principal) -> None:  # noqa: ANN001
    # The ratified API shape (OD-MG-1-B, a planning-verifier fold): a stray `tier` key in the
    # register body is IGNORED-AND-NOT-STAMPED — the 1L cannot set tier, by any route. The head
    # registers untiered (the TIER_1 fail-safe bound applies until the 2L assigns).
    client, principal, _db = client_and_principal
    body = {**_BODY, "code": "M-TIER-SMUGGLE", "tier": "TIER_3"}
    created = client.post("/models", json=body, headers=_headers(principal)).json()
    detail = client.get(f"/models/{created['id']}", headers=_headers(principal)).json()
    assert detail["tier"] is None
