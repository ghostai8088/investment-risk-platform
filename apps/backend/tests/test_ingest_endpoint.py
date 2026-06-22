"""End-to-end tests of the ingestion endpoints (multipart upload + batch reads).

SQLite has no RLS, so cross-tenant RLS-hidden 404 / isolation are proven in
``packages/shared-python/tests/test_ingestion_pg.py``; here we prove entitlement gating
(deny-by-default), server-side tenant stamping, the size cap, anti-corruption + DQ rejection
(4xx + durable evidence), and audit emission over real HTTP.
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

from irp_backend.api.ingest import router as ingest_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.models import DataQualityResult
from irp_shared.dq.service import register_dq_rule
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.ingestion.anticorruption import MAX_UPLOAD_BYTES
from irp_shared.ingestion.models import IngestionBatch
from irp_shared.ingestion.service import STAGING_ROW_TARGET
from irp_shared.lineage.service import register_data_source
from irp_shared.models import Base


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, str]]:
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
    perm = Permission(code="data.upload", description="d")
    db.add(perm)
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    # Provenance source + one active generic staging rule so the happy path yields a PASS.
    source = register_data_source(
        db, tenant_id=tenant_id, code="S", name="S", source_type="upload", actor_id="a"
    )
    register_dq_rule(
        db,
        tenant_id=tenant_id,
        code="CCY",
        name="r",
        rule_type="ALLOWED_VALUES",
        actor_id="a",
        params={"column": "ccy", "allowed": ["USD", "EUR"]},
        target_entity_type=STAGING_ROW_TARGET,
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(ingest_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, source.id
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _csv(content: bytes = b"ccy\nUSD\nEUR\n", name: str = "p.csv") -> dict:
    return {"file": (name, content, "text/csv")}


def test_upload_happy_201_and_audited(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, db, source_id = ctx
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files=_csv(),
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["staged_count"] == 2
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "DATA.INGEST")
        ).scalar_one()
        == 2
    )


def test_upload_stamps_caller_tenant(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, db, source_id = ctx
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files=_csv(),
        headers=_headers(principal),
    )
    batch = db.execute(select(IngestionBatch)).scalar_one()
    assert batch.tenant_id == principal.tenant_id and resp.json()["id"] == batch.id


def test_upload_without_permission_403(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, source_id = ctx
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files=_csv(),
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


def test_upload_missing_principal_401(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, _, _, source_id = ctx
    assert (
        client.post("/ingest/upload", data={"data_source_id": source_id}, files=_csv()).status_code
        == 401
    )


def test_upload_malformed_source_id_422(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, _ = ctx
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": "not-a-uuid"},
        files=_csv(),
        headers=_headers(principal),
    )
    assert resp.status_code == 422


def test_upload_oversized_413(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, db, source_id = ctx
    big = b"a" * (MAX_UPLOAD_BYTES + 1)
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files={"file": ("big.csv", big, "text/csv")},
        headers=_headers(principal),
    )
    assert resp.status_code == 413
    assert db.execute(select(func.count()).select_from(IngestionBatch)).scalar_one() == 0


def test_upload_dq_failure_422_with_durable_evidence(
    ctx: tuple[TestClient, Principal, Session, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, principal, db, source_id = ctx
    # Spy on commit so the test distinguishes a COMMITTED rejection (durable evidence) from a
    # merely-not-rolled-back one: a regression that swapped the except-branch commit for a rollback
    # would drop `commits` to 0 here and fail (the reject path must commit — invariant 3).
    commits = {"n": 0}
    original_commit = db.commit

    def _spy_commit() -> None:
        commits["n"] += 1
        original_commit()

    monkeypatch.setattr(db, "commit", _spy_commit)
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files=_csv(content=b"ccy\nUSD\nZZZ\n"),  # ZZZ not allowed -> ERROR FAIL
        headers=_headers(principal),
    )
    assert resp.status_code == 422  # never 200
    assert commits["n"] >= 1  # the rejection was COMMITTED, not silently rolled back
    batch = db.execute(select(IngestionBatch)).scalar_one()
    assert batch.status == "REJECTED"
    # The full evidence trail is durable: REJECTED batch + FAIL DQ result + DATA.VALIDATE(failure).
    result = db.execute(select(DataQualityResult)).scalar_one()
    assert result.outcome == "FAIL" and result.ingestion_batch_id == batch.id
    dv = db.execute(select(AuditEvent).where(AuditEvent.event_type == "DATA.VALIDATE")).scalar_one()
    assert dv.outcome == "failure"


def test_upload_bad_filetype_422(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, source_id = ctx
    resp = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files={"file": ("x.exe", b"ccy\nUSD\n", "application/x-msdownload")},
        headers=_headers(principal),
    )
    assert resp.status_code == 422


def test_list_and_get_batch(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, source_id = ctx
    created = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files=_csv(),
        headers=_headers(principal),
    ).json()
    listing = client.get("/ingest/batches", headers=_headers(principal))
    assert listing.status_code == 200 and any(b["id"] == created["id"] for b in listing.json())
    detail = client.get(f"/ingest/batches/{created['id']}", headers=_headers(principal))
    assert detail.status_code == 200 and detail.json()["status"] == "COMPLETED"


def test_get_unknown_404_fixed_body(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, _ = ctx
    resp = client.get(f"/ingest/batches/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 404 and resp.json()["detail"] == "batch not found"


def test_get_malformed_id_422(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, _ = ctx
    assert client.get("/ingest/batches/not-a-uuid", headers=_headers(principal)).status_code == 422


def test_list_without_permission_403(ctx: tuple[TestClient, Principal, Session, str]) -> None:
    client, principal, _, _ = ctx
    resp = client.get(
        "/ingest/batches",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403
