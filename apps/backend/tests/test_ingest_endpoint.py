"""End-to-end tests of the ingestion endpoints (multipart upload + batch reads).

SQLite has no RLS, so cross-tenant RLS-hidden 404 / isolation are proven in
``packages/shared-python/tests/test_ingestion_pg.py``; here we prove entitlement gating
(deny-by-default), server-side tenant stamping, the size cap, anti-corruption + DQ rejection
(4xx + durable evidence), and audit emission over real HTTP.

**W19-S3a correction.** An earlier version of this docstring said the cross-tenant gap was closed
by ``packages/shared-python/tests/test_ingestion_pg.py``. For the MAPPING routes that was false —
that file does not mention mappings at all, and the one PG test that checked cross-tenant hiding
went through ``resolve_mapping_version`` (which carries its own explicit tenant predicate), NOT
through the route's ``db.get``. A slice reviewer caught the claim. The route functions' own
queries are now exercised on PostgreSQL, under the constrained role, in
``test_ingest_mapping_pg.py`` — see
``test_the_mapping_routes_hide_another_tenants_rows``.
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
    # W19-S3b: the reads moved onto `ingest.mapping.view` and the verbs onto their own codes, so
    # this fixture's principal now holds all four. It deliberately holds BOTH sides of the
    # partition — the role-level separation is asserted in test_entitlement_bootstrap.py against
    # the real ROLE_TEMPLATES, and re-asserting it through a synthetic fixture role here would test
    # the fixture rather than the catalog.
    for code in (
        "data.upload",
        "ingest.mapping.propose",
        "ingest.mapping.ratify",
        "ingest.mapping.view",
    ):
        perm = Permission(code=code, description="d")
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


# --- W19-S3a: the ENT-077 mapping READS (Rule 7's entity/time surface) -------------------------


_MAPPING_OPS = [
    {"op": "constant", "target": "portfolio_code", "value": "P"},
    {"op": "code-lookup", "target": "instrument", "source": "SEDOL", "scheme": "SEDOL"},
    {"op": "scale", "target": "quantity", "source": "QTY", "factor": "1000"},
    {"op": "parse-date", "target": "valid_from", "source": "D", "format": "%d/%m/%Y"},
]


def _propose(db: Session, principal: Principal, source_id: str, label: str = "v1"):  # noqa: ANN202
    from irp_shared.ingest_mapping.service import propose_mapping_version

    version = propose_mapping_version(
        db,
        tenant_id=principal.tenant_id,
        data_source_id=source_id,
        source_type="POSITIONS",
        version_label=label,
        operations=list(_MAPPING_OPS),
        actor_id="proposer@irp",
    )
    db.commit()
    return version


def test_mapping_list_shows_a_PROPOSED_version(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """Deliberately NOT filtered to RATIFIED: a screen that hid the proposal awaiting a human
    would hide the one thing an operator opens this page to find."""
    client, principal, db, source_id = ctx
    version = _propose(db, principal, source_id)
    resp = client.get("/ingest/mappings", headers=_headers(principal))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [row["id"] for row in body] == [version.id]
    assert body[0]["status"] == "PROPOSED"
    assert body[0]["ratified_by_actor_id"] is None


def test_mapping_detail_carries_the_operations_verbatim(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """A mapping is meant to be readable by a non-engineer — "what did this mapping do?" is the
    question the closed vocabulary exists to keep answerable, so the screen gets the real list."""
    client, principal, db, source_id = ctx
    version = _propose(db, principal, source_id)
    resp = client.get(f"/ingest/mappings/{version.id}", headers=_headers(principal))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["operations"] == _MAPPING_OPS
    assert body["operations_hash"] == version.operations_hash
    assert body["authorship"] == "HAND_AUTHORED"
    # a HAND_AUTHORED version carries NEITHER piece of model attribution (the symmetric CHECK)
    assert body["proposer_model_version_id"] is None
    assert body["proposal_prompt_hash"] is None


def test_mapping_unknown_404_and_malformed_422(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    client, principal, _, _ = ctx
    unknown = client.get(f"/ingest/mappings/{uuid.uuid4()}", headers=_headers(principal))
    assert unknown.status_code == 404 and unknown.json()["detail"] == "mapping not found"
    assert client.get("/ingest/mappings/not-a-uuid", headers=_headers(principal)).status_code == 422


def test_mapping_batches_404s_on_an_unknown_mapping_rather_than_returning_empty(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """ "No batches" and "not your mapping" must stay distinguishable to a caller entitled to know;
    an empty list for an unknown id conflates them."""
    client, principal, db, source_id = ctx
    version = _propose(db, principal, source_id)
    empty = client.get(f"/ingest/mappings/{version.id}/batches", headers=_headers(principal))
    assert empty.status_code == 200 and empty.json() == []
    missing = client.get(f"/ingest/mappings/{uuid.uuid4()}/batches", headers=_headers(principal))
    assert missing.status_code == 404


def test_the_batch_dto_exposes_its_mapping_binding(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """Clause (2)'s batch half, on the read surface. A generic upload legitimately has none, and
    the DTO says so with a null rather than omitting the field."""
    client, principal, _, source_id = ctx
    created = client.post(
        "/ingest/upload",
        data={"data_source_id": source_id},
        files=_csv(),
        headers=_headers(principal),
    ).json()
    assert created["mapping_version_id"] is None
    assert created["lookup_as_of"] is None


def test_mapping_reads_are_permission_gated(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """Deny-by-default, on every one of the three. The reads sit behind `data.upload` for one
    slice by ratified decision (DS3a-1); S3b mints the dedicated codes."""
    client, principal, db, source_id = ctx
    version = _propose(db, principal, source_id)
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id}
    for path in (
        "/ingest/mappings",
        f"/ingest/mappings/{version.id}",
        f"/ingest/mappings/{version.id}/batches",
    ):
        assert client.get(path, headers=stranger).status_code == 403, path


# --- W19-S3b: the mapping LIFECYCLE verbs over HTTP --------------------------------------------


def _propose_body(source_id: str, label: str = "v1") -> dict:
    return {
        "data_source_id": source_id,
        "source_type": "POSITIONS",
        "version_label": label,
        "operations": _MAPPING_OPS,
    }


def test_propose_then_ratify_over_http(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """The maker's verb and the checker's verb, each behind its own minted code."""
    client, principal, db, source_id = ctx
    created = client.post(
        "/ingest/mappings", json=_propose_body(source_id), headers=_headers(principal)
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "PROPOSED"
    mapping_id = created.json()["id"]

    # a DIFFERENT principal ratifies — the same user would be a 409, asserted below
    other = AppUser(tenant_id=principal.tenant_id, display_name="checker")
    db.add(other)
    db.flush()
    role_id = db.execute(select(Role.id).where(Role.tenant_id == principal.tenant_id)).scalar_one()
    db.add(UserRole(tenant_id=principal.tenant_id, user_id=other.id, role_id=str(role_id)))
    db.commit()

    ratified = client.post(
        f"/ingest/mappings/{mapping_id}/ratify",
        json={"reason": "checked against the custodian's spec"},
        headers={"X-User-Id": other.id, "X-Tenant-Id": principal.tenant_id},
    )
    assert ratified.status_code == 200, ratified.text
    assert ratified.json()["status"] == "RATIFIED"
    assert ratified.json()["ratified_by_actor_id"] == other.id


def test_self_ratification_is_a_409_not_a_403(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """The distinction matters operationally. The caller HAS the ratify permission; the act is
    refused on WHO THEY ARE relative to this proposal. A 403 would send an operator to ask for a
    permission they already hold."""
    client, principal, _, source_id = ctx
    mapping_id = client.post(
        "/ingest/mappings", json=_propose_body(source_id), headers=_headers(principal)
    ).json()["id"]
    same = client.post(
        f"/ingest/mappings/{mapping_id}/ratify", json={}, headers=_headers(principal)
    )
    assert same.status_code == 409, same.text
    assert "may not ratify" in same.json()["detail"]


def test_withdraw_requires_a_reason_and_the_proposer(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """A proposal removed from the queue with no explanation is indistinguishable from one that was
    never made; and withdrawal is the proposer's own act, not a rejection verb for a checker."""
    client, principal, db, source_id = ctx
    mapping_id = client.post(
        "/ingest/mappings", json=_propose_body(source_id), headers=_headers(principal)
    ).json()["id"]

    no_reason = client.post(
        f"/ingest/mappings/{mapping_id}/withdraw", json={}, headers=_headers(principal)
    )
    assert no_reason.status_code == 422

    stranger = AppUser(tenant_id=principal.tenant_id, display_name="someone else")
    db.add(stranger)
    db.flush()
    role_id = db.execute(select(Role.id).where(Role.tenant_id == principal.tenant_id)).scalar_one()
    db.add(UserRole(tenant_id=principal.tenant_id, user_id=stranger.id, role_id=str(role_id)))
    db.commit()
    theirs = client.post(
        f"/ingest/mappings/{mapping_id}/withdraw",
        json={"reason": "not mine"},
        headers={"X-User-Id": stranger.id, "X-Tenant-Id": principal.tenant_id},
    )
    assert theirs.status_code == 409, theirs.text

    mine = client.post(
        f"/ingest/mappings/{mapping_id}/withdraw",
        json={"reason": "the custodian re-issued the file"},
        headers=_headers(principal),
    )
    assert mine.status_code == 200, mine.text
    assert mine.json()["status"] == "WITHDRAWN"


def test_an_incoherent_proposal_is_422_not_500(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """A mapping that could never load anything must not reach a ratification queue — and the
    refusal must be a governed 4xx, not an unhandled exception."""
    client, principal, _, source_id = ctx
    body = _propose_body(source_id, "bad")
    body["operations"] = [dict(op, op="regex_replace") for op in _MAPPING_OPS]
    resp = client.post("/ingest/mappings", json=body, headers=_headers(principal))
    assert resp.status_code == 422, resp.text
    assert "regex_replace" in resp.json()["detail"]


def test_superseding_an_invisible_version_is_an_INDISTINGUISHABLE_404(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """A `supersedes_id` the caller cannot see answers 404 — the same answer an id that does not
    exist gets.

    The first draft of `propose_mapping` caught only `MappingError`, and `MappingNotVisible` is a
    subclass of it, so this case answered **422 with the refusal's message attached**. That is a
    cross-tenant existence oracle: a caller could enumerate another tenant's mapping ids by the
    difference in the reply. The clause ordering in the route is the fix, and clause ordering is
    exactly the kind of thing that gets reshuffled by a later edit — hence a test that pins it.
    """
    client, principal, _, source_id = ctx
    body = _propose_body(source_id, "v-super")
    body["supersedes_id"] = str(uuid.uuid4())  # never existed
    absent = client.post("/ingest/mappings", json=body, headers=_headers(principal))
    assert absent.status_code == 404, absent.text
    assert absent.json()["detail"] == "mapping not found"


def test_the_lifecycle_verbs_are_permission_gated(
    ctx: tuple[TestClient, Principal, Session, str],
) -> None:
    """Deny-by-default on all three, and on the re-gated reads."""
    client, principal, _, source_id = ctx
    mapping_id = client.post(
        "/ingest/mappings", json=_propose_body(source_id), headers=_headers(principal)
    ).json()["id"]
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id}
    assert (
        client.post(
            "/ingest/mappings", json=_propose_body(source_id, "x"), headers=stranger
        ).status_code
        == 403
    )
    assert (
        client.post(f"/ingest/mappings/{mapping_id}/ratify", json={}, headers=stranger).status_code
        == 403
    )
    assert (
        client.post(
            f"/ingest/mappings/{mapping_id}/withdraw", json={"reason": "r"}, headers=stranger
        ).status_code
        == 403
    )
    assert client.get("/ingest/mappings", headers=stranger).status_code == 403
