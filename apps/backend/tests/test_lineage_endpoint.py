"""End-to-end test of GET /lineage/edges/{id} (200 / 401 / 403 / 404).

SQLite has no RLS, so the cross-tenant *RLS-hidden* 404 is proven in
``packages/shared-python/tests/test_lineage_pg.py``; here we prove entitlement gating
(deny-by-default) and that a missing edge yields 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.lineage import router as lineage_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.lineage.models import DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.models import Base


@pytest.fixture
def client_and_edge() -> Iterator[tuple[TestClient, Principal, str]]:
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
    perm = Permission(code="lineage.view", description="d")
    db.add_all([user, role, perm])
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))

    src = register_data_source(
        db, tenant_id=tenant_id, code="SRC", name="n", source_type="INTERNAL", actor_id="a"
    )
    edge = record_lineage(
        db, source=src, target_entity_type="synthetic.t", target_entity_id=str(uuid.uuid4())
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(lineage_router)
    app.dependency_overrides[get_db] = _override_db

    try:
        yield TestClient(app), principal, edge.id
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def test_get_edge_allows_granted_principal(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    client, principal, edge_id = client_and_edge
    resp = client.get(f"/lineage/edges/{edge_id}", headers=_headers(principal))
    assert resp.status_code == 200
    assert resp.json()["id"] == edge_id
    assert resp.json()["source_type"] == "data_source"


def test_missing_principal_is_401(client_and_edge: tuple[TestClient, Principal, str]) -> None:
    client, _, edge_id = client_and_edge
    assert client.get(f"/lineage/edges/{edge_id}").status_code == 401


def test_unauthorized_principal_is_403(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    client, principal, edge_id = client_and_edge
    resp = client.get(
        f"/lineage/edges/{edge_id}",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


def test_unknown_edge_is_404(client_and_edge: tuple[TestClient, Principal, str]) -> None:
    client, principal, _ = client_and_edge
    resp = client.get(f"/lineage/edges/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 404
    # Fixed body so a not-found and a (PG) cross-tenant-hidden id stay indistinguishable.
    assert resp.json()["detail"] == "lineage edge not found"


def test_malformed_edge_id_is_422(client_and_edge: tuple[TestClient, Principal, str]) -> None:
    client, principal, _ = client_and_edge
    # A non-UUID id is rejected uniformly (422) before any DB hit — no 500 / oracle distinction.
    resp = client.get("/lineage/edges/not-a-uuid", headers=_headers(principal))
    assert resp.status_code == 422


# --- W19-S3b: the BY-TARGET read -----------------------------------------------------------------
#
# Until this slice `/lineage` had exactly ONE endpoint, keyed on an edge id that NO endpoint
# returned and NO listing produced. It was live, permission-gated, in `API_PREFIXES` and the nginx
# alternation — and unreachable: an operator asking "where did this row come from?" had nowhere to
# start. These tests exercise the entry point that makes the by-id read usable.


def _target_of(client: TestClient, principal: Principal, edge_id: str) -> tuple[str, str]:
    body = client.get(f"/lineage/edges/{edge_id}", headers=_headers(principal)).json()
    return body["target_entity_type"], body["target_entity_id"]


def test_by_target_returns_the_edge_the_by_id_read_needs(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    """The two reads compose: name an entity, get its inbound edges, follow one by id.

    Asserted as a COMPOSITION rather than as two independent 200s, because the defect this read
    fixes was never that the by-id endpoint was broken — it was that nothing produced its argument.
    """
    client, principal, edge_id = client_and_edge
    kind, target_id = _target_of(client, principal, edge_id)

    resp = client.get(f"/lineage/targets/{kind}/{target_id}", headers=_headers(principal))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_entity_id"] == target_id
    assert body["truncated"] is False
    assert [e["id"] for e in body["edges"]] == [edge_id]
    assert body["edges"][0]["source_type"] == "data_source"

    # ...and the id it returned really is usable against the by-id read. That round trip is the
    # whole point of the endpoint.
    followed = client.get(f"/lineage/edges/{body['edges'][0]['id']}", headers=_headers(principal))
    assert followed.status_code == 200
    assert followed.json()["id"] == edge_id


def test_a_target_with_no_lineage_is_an_EMPTY_200_not_a_404(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    """A deliberate difference from the by-id read, and the reasoning is load-bearing.

    "What is the lineage of this entity?" asked about an entity with none is a legitimate question
    with the legitimate answer "nothing was recorded". A 404 would additionally claim the ENTITY
    does not exist — which this endpoint has no way to know, since it queries `lineage_edge` and
    never
    looks at the target's own table. It would also make the reply an oracle in the other direction,
    distinguishing "no lineage" from "not your tenant", which under RLS are the same answer and must
    stay that way.
    """
    client, principal, _ = client_and_edge
    resp = client.get(f"/lineage/targets/synthetic.t/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 200, resp.text
    assert resp.json()["edges"] == []
    assert resp.json()["truncated"] is False


def test_the_TYPE_discriminator_actually_filters(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    """The negative half: a real target id under the WRONG type must return nothing.

    Without this, a read that ignored `target_entity_type` and matched on the id alone would pass
    every test above — and would return another entity family's edges for a colliding id.
    """
    client, principal, edge_id = client_and_edge
    _, target_id = _target_of(client, principal, edge_id)
    resp = client.get(f"/lineage/targets/position/{target_id}", headers=_headers(principal))
    assert resp.status_code == 200
    assert resp.json()["edges"] == []


def test_by_target_is_permission_gated_and_id_validated(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    """Deny-by-default, and a malformed id is a uniform 422 before any DB hit (no 500 / oracle)."""
    client, principal, edge_id = client_and_edge
    kind, target_id = _target_of(client, principal, edge_id)
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id}
    assert client.get(f"/lineage/targets/{kind}/{target_id}", headers=stranger).status_code == 403
    assert client.get(f"/lineage/targets/{kind}/{target_id}").status_code == 401
    assert (
        client.get(f"/lineage/targets/{kind}/not-a-uuid", headers=_headers(principal)).status_code
        == 422
    )


def test_the_cap_reports_TRUNCATION_rather_than_presenting_a_cut_answer_as_whole(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    """The `truncated` flag, EXERCISED — every other assertion in this file sees it False.

    A silently truncated lineage answer is worse than no answer: it looks complete, and lineage is
    exactly the surface where "these are all the edges" is the whole point. The cap and its flag had
    zero execution until a review said so.
    """
    from irp_backend.api.lineage import MAX_EDGES_PER_TARGET

    client, principal, edge_id = client_and_edge
    kind, target_id = _target_of(client, principal, edge_id)

    # One MORE than the cap, so the boundary is crossed rather than merely reached.
    db = _session_of(client)
    src = db.execute(select(DataSource).limit(1)).scalar_one()
    for _ in range(MAX_EDGES_PER_TARGET):
        record_lineage(db, source=src, target_entity_type=kind, target_entity_id=target_id)
    db.commit()

    resp = client.get(f"/lineage/targets/{kind}/{target_id}", headers=_headers(principal))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["edges"]) == MAX_EDGES_PER_TARGET
    assert body["truncated"] is True, (
        "the cap cut the answer short and the reply did not say so — a reader would take a partial "
        "lineage for a complete one"
    )


def _session_of(client: TestClient) -> Session:
    """The SAME session the app writes through — the fixture overrides `get_db` with a generator
    yielding one long-lived session, so a test that opened its own would write into a database the
    app cannot see."""
    gen = client.app.dependency_overrides[get_db]()  # type: ignore[attr-defined]
    session = next(gen)
    assert isinstance(session, Session)
    return session
