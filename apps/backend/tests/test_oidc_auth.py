"""End-to-end auth tests in OIDC mode (SSO-1, AD-007).

Exercises the full request path — ``get_principal`` (oidc branch) → verified claim → ``app_user``
resolution → ``require_permission`` — with a locally-signed RS256 token and an injected verifier
(no network). Proves: a valid token for a granted user is allowed; every token/identity failure is
an opaque 401; a real-but-unentitled user is 403; a tenant-claim mismatch and an inactive user both
deny. The dev-header path is covered by ``test_entitlement_dependency.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.auth import TokenVerifier
from irp_backend.config import settings
from irp_backend.deps import get_db, require_permission
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base

PERMISSION = "foundation.read"
ISS = "https://issuer.example"
AUD = "irp-backend"


def _keypair() -> tuple[bytes, bytes]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


@dataclass
class OidcHarness:
    client: TestClient
    priv: bytes
    tenant_id: str
    subject: str
    user_id: str


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Iterator[OidcHarness]:
    priv, pub = _keypair()
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_id = str(uuid.uuid4())
    subject = "oidc-subject-1"
    user = AppUser(tenant_id=tenant_id, display_name="U", external_subject=subject, is_active=True)
    role = Role(tenant_id=tenant_id, code="r", name="R")
    perm = Permission(code=PERMISSION, description="d")
    db.add_all([user, role, perm])
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    # A second, inactive user in the same tenant (proves is_active gating).
    inactive = AppUser(
        tenant_id=tenant_id, display_name="X", external_subject="inactive-sub", is_active=False
    )
    db.add(inactive)
    db.commit()

    verifier = TokenVerifier(
        issuer=ISS,
        audience=AUD,
        algorithms=["RS256"],
        tenant_claim="tenant_id",
        subject_claim="sub",
        require_mfa=False,
        acr_values=None,
        key_resolver=lambda _token: pub,
    )
    monkeypatch.setattr("irp_backend.deps.get_verifier", lambda: verifier)
    monkeypatch.setattr(settings, "auth_mode", "oidc")

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    guard = require_permission(PERMISSION)

    @app.get("/_test/guarded")
    def guarded(p: Principal = Depends(guard)) -> dict[str, str]:
        return {"user_id": p.user_id}

    app.dependency_overrides[get_db] = _override_db
    try:
        yield OidcHarness(
            client=TestClient(app),
            priv=priv,
            tenant_id=tenant_id,
            subject=subject,
            user_id=user.id,
        )
    finally:
        db.close()
        engine.dispose()


def _token(
    priv: bytes,
    *,
    iss: str = ISS,
    aud: str = AUD,
    sub: str = "oidc-subject-1",
    tenant: str = "",
    exp_delta: int = 3600,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "tenant_id": tenant,
        "iat": now,
        "exp": now + timedelta(seconds=exp_delta),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, priv, algorithm="RS256")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_allows_granted_user(harness: OidcHarness) -> None:
    token = _token(harness.priv, sub=harness.subject, tenant=harness.tenant_id)
    resp = harness.client.get("/_test/guarded", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"user_id": harness.user_id}  # resolved app_user.id, not the sub


def test_no_authorization_header_is_401(harness: OidcHarness) -> None:
    assert harness.client.get("/_test/guarded").status_code == 401


def test_non_bearer_scheme_is_401(harness: OidcHarness) -> None:
    token = _token(harness.priv, tenant=harness.tenant_id)
    resp = harness.client.get("/_test/guarded", headers={"Authorization": f"Basic {token}"})
    assert resp.status_code == 401


def test_token_signed_by_wrong_key_is_401(harness: OidcHarness) -> None:
    other_priv, _ = _keypair()
    token = _token(other_priv, sub=harness.subject, tenant=harness.tenant_id)
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_wrong_issuer_is_401(harness: OidcHarness) -> None:
    token = _token(harness.priv, iss="https://evil.example", tenant=harness.tenant_id)
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_wrong_audience_is_401(harness: OidcHarness) -> None:
    token = _token(harness.priv, aud="other-api", tenant=harness.tenant_id)
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_expired_token_is_401(harness: OidcHarness) -> None:
    token = _token(harness.priv, tenant=harness.tenant_id, exp_delta=-10)
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_unknown_subject_is_401(harness: OidcHarness) -> None:
    token = _token(harness.priv, sub="nobody-here", tenant=harness.tenant_id)
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_tenant_claim_mismatch_is_401(harness: OidcHarness) -> None:
    # A valid subject, but the token asserts a DIFFERENT tenant → the (tenant, sub) lookup misses.
    token = _token(harness.priv, sub=harness.subject, tenant=str(uuid.uuid4()))
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_inactive_user_is_401(harness: OidcHarness) -> None:
    token = _token(harness.priv, sub="inactive-sub", tenant=harness.tenant_id)
    assert harness.client.get("/_test/guarded", headers=_auth(token)).status_code == 401


def test_real_user_without_permission_is_403() -> None:
    # A separate harness where the user holds NO role → the token verifies, the user resolves,
    # but require_permission denies with 403 (distinct from the 401 identity failures above).
    priv, pub = _keypair()
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    tenant_id = str(uuid.uuid4())
    subject = "unentitled-sub"
    db.add(AppUser(tenant_id=tenant_id, display_name="U", external_subject=subject, is_active=True))
    db.add(Permission(code=PERMISSION, description="d"))
    db.commit()

    verifier = TokenVerifier(
        issuer=ISS,
        audience=AUD,
        algorithms=["RS256"],
        tenant_claim="tenant_id",
        subject_claim="sub",
        require_mfa=False,
        acr_values=None,
        key_resolver=lambda _token: pub,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("irp_backend.deps.get_verifier", lambda: verifier)
        mp.setattr(settings, "auth_mode", "oidc")

        def _override_db() -> Iterator[Session]:
            yield db

        app = FastAPI()
        guard = require_permission(PERMISSION)

        @app.get("/_test/guarded")
        def guarded(p: Principal = Depends(guard)) -> dict[str, str]:
            return {"user_id": p.user_id}

        app.dependency_overrides[get_db] = _override_db
        token = _token(priv, sub=subject, tenant=tenant_id)
        resp = TestClient(app).get("/_test/guarded", headers=_auth(token))
    db.close()
    engine.dispose()
    assert resp.status_code == 403
