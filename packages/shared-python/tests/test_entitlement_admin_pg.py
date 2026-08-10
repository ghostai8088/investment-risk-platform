"""ONBOARD-1b on real PostgreSQL — the concurrency path, and the append-only guarantee.

The unit tier proves three of the orphan invariant's four paths. The fourth is **concurrent**, and
SQLite cannot express it at all: two admins revoking each other, each transaction reading the
other as remaining, both individually-legal checks passing, tenant left with zero administrators.
That is not a logic bug — the logic is correct in each transaction — it is a missing lock, and a
missing lock is only observable where locks exist.

Also here: the ENT-075 append-only trigger, because "an approval that could be edited into
existence" is the one property that would make the whole control decorative, and it is enforced by
the database rather than by the service.

Runs as the constrained ``irp_app`` role (NOSUPERUSER NOBYPASSRLS). The default ``irp`` login is
the container superuser and would switch off the RLS these tests rely on — the ONBOARD-1a lesson,
applied at the start this time rather than discovered by a floor.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.admin_service import (
    AdminActor,
    EntitlementError,
    TenantWouldBeOrphaned,
    approve_entitlement_change,  # noqa: E402
    request_entitlement_change,
    valid_admin_user_ids,
)
from irp_shared.entitlement.models import AppUser, Role, UserRole
from irp_shared.entitlement.request_models import (
    ACTION_REVOKE_ROLE,
    STATUS_PENDING,
    EntitlementRequest,
)
from irp_shared.tenancy.models import Tenant
from irp_shared.tenancy.service import FIRST_ADMIN_ROLE

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_GRANTED = (
    "tenant",
    "app_user",
    "role",
    "role_permission",
    "user_role",
    "permission",
    "audit_event",
    "entitlement_request",
)
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def app_url() -> str:
    superuser = make_engine(URL, poolclass=NullPool)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'irp_app') "
                "THEN CREATE ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "ELSE ALTER ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO irp_app"))
        for table in _GRANTED:
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


@pytest.fixture
def factory(app_url: str):  # noqa: ANN201
    engine = make_engine(app_url, poolclass=NullPool)
    yield make_session_factory(engine)
    engine.dispose()


def _seed_two_admins(factory) -> tuple[str, str, str, str]:  # noqa: ANN001
    """A registered tenant with its admin role and TWO administrators. Committed."""
    tid = str(uuid.uuid4())
    session = factory()
    try:
        session.add(
            Tenant(
                id=tid,
                code=f"c-{tid[:8]}",
                display_name="Concurrent",
                status="ACTIVE",
                provenance="ONBOARDED",
            )
        )
        set_tenant_context(session, tid)
        role = Role(id=str(uuid.uuid4()), tenant_id=tid, code=FIRST_ADMIN_ROLE, name="Tenant Admin")
        session.add(role)
        session.flush()
        ids = []
        for label in ("one", "two"):
            user = AppUser(
                id=str(uuid.uuid4()),
                tenant_id=tid,
                external_subject=f"{label}@{tid[:8]}",
                display_name=label,
                is_active=True,
            )
            session.add(user)
            session.flush()
            session.add(
                UserRole(
                    id=str(uuid.uuid4()),
                    tenant_id=tid,
                    user_id=user.id,
                    role_id=role.id,
                    # EXPLICIT: `valid_from` defaults to wall-clock, and this suite reasons at a
                    # fixed NOW. Leaving it implicit made every seeded admin invisible to
                    # `valid_admin_user_ids(now=NOW)` — the fixture, not the code, and it masked
                    # what the concurrency test was actually measuring.
                    valid_from=NOW - timedelta(days=1),
                )
            )
            ids.append(user.id)
        session.commit()
        return tid, role.id, ids[0], ids[1]
    finally:
        session.close()


def test_TWO_concurrent_APPROVALS_cannot_orphan_the_tenant(factory) -> None:  # noqa: ANN001
    """THE fourth path, and the only one SQLite cannot express.

    **It took a wrong first draft to find where the race actually lives.** The obvious test — two
    admins concurrently REQUESTING each other's revocation — proves nothing: with two admins each
    request is born PENDING, so neither takes effect and four-eyes has already serialized the
    danger into a second phase. The race is one step later:

      1. admin A requests revoke(B) -> PENDING
      2. admin B requests revoke(A) -> PENDING
      3. A approves B's request and B approves A's request, CONCURRENTLY

    Each approval runs the orphan check, each sees two admins minus its own target, each finds one
    remaining, and both commit — leaving zero. Individually legal, jointly fatal, and only the
    per-tenant advisory lock makes the second one see the first one's effect.

    The assertion is on the OUTCOME, not on a winner: at least one administrator must survive, and
    at most one approval may succeed. Asserting which would be asserting a race.
    """
    tid, role_id, one, two = _seed_two_admins(factory)

    # Phase 1+2: both revocations requested, both PENDING (asserted — if they were not, this test
    # would be exercising the harmless path again without saying so).
    setup = factory()
    try:
        set_tenant_context(setup, tid)
        req_a = request_entitlement_change(
            setup,
            tenant_id=tid,
            actor=AdminActor(one),
            action=ACTION_REVOKE_ROLE,
            target_user_id=two,
            target_role_id=role_id,
            now=NOW,
        )
        req_b = request_entitlement_change(
            setup,
            tenant_id=tid,
            actor=AdminActor(two),
            action=ACTION_REVOKE_ROLE,
            target_user_id=one,
            target_role_id=role_id,
            now=NOW,
        )
        assert req_a.status == STATUS_PENDING and req_b.status == STATUS_PENDING
        req_a_id, req_b_id = req_a.id, req_b.id
        setup.commit()
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def approve(approver: str, request_id: str, key: str) -> None:
        session = factory()
        try:
            set_tenant_context(session, tid)
            barrier.wait(timeout=10)
            approve_entitlement_change(
                session,
                tenant_id=tid,
                actor=AdminActor(approver),
                request_id=request_id,
                now=NOW,
            )
            session.commit()
            results[key] = "ok"
        except TenantWouldBeOrphaned:
            session.rollback()
            results[key] = "refused"
        except Exception as exc:  # noqa: BLE001 - surfaced in the assertion below
            session.rollback()
            results[key] = f"error:{type(exc).__name__}"
        finally:
            session.close()

    # A approves B's request (revoking A); B approves A's request (revoking B). Neither approves
    # their own — the person-level gate stays satisfied, which is what makes this reachable.
    threads = [
        threading.Thread(target=approve, args=(one, req_b_id, "a")),
        threading.Thread(target=approve, args=(two, req_a_id, "b")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    check = factory()
    try:
        set_tenant_context(check, tid)
        survivors = valid_admin_user_ids(check, tid, now=NOW)
    finally:
        check.close()

    assert survivors, (
        f"the tenant was ORPHANED by two concurrent approvals (results={results}) — both orphan "
        "checks passed against a state neither could see, which is exactly what the per-tenant "
        "advisory lock exists to serialize"
    )
    assert (
        list(results.values()).count("ok") <= 1
    ), f"both approvals took effect: {results} — they did not serialize"
    assert "refused" in results.values(), (
        f"neither approval was REFUSED: {results} — if both were merely errors, the lock is not "
        "what produced the safe outcome and this test proves nothing about it"
    )


def test_an_ENTITLEMENT_REQUEST_row_cannot_be_edited_after_the_fact(factory) -> None:  # noqa: ANN001
    """IA append-only at the DATABASE. An approval that could be edited in is not an approval."""
    tid, role_id, one, two = _seed_two_admins(factory)
    session = factory()
    try:
        set_tenant_context(session, tid)
        target = AppUser(
            id=str(uuid.uuid4()),
            tenant_id=tid,
            external_subject=f"t@{tid[:8]}",
            display_name="T",
            is_active=True,
        )
        session.add(target)
        session.flush()
        req = request_entitlement_change(
            session,
            tenant_id=tid,
            actor=AdminActor(one),
            action=ACTION_REVOKE_ROLE,
            target_user_id=two,
            target_role_id=role_id,
            now=NOW,
        )
        session.commit()

        set_tenant_context(session, tid)
        with pytest.raises(ProgrammingError) as caught:
            session.execute(
                text("UPDATE entitlement_request SET resolved_by = :r WHERE id = :i"),
                {"r": one, "i": req.id},
            )
            session.flush()
        assert "P0001" in str(caught.value) or "append-only" in str(caught.value).lower()
        session.rollback()
    finally:
        session.close()


def test_the_request_row_is_TENANT_ISOLATED(factory) -> None:  # noqa: ANN001
    """FORCE RLS on ENT-075: another tenant's context sees no entitlement history at all.

    An entitlement request names people and the authority they were given; leaking it across
    tenants would be a disclosure of exactly the kind the roster's auditor exclusion guards.
    """
    tid, role_id, one, two = _seed_two_admins(factory)
    session = factory()
    try:
        set_tenant_context(session, tid)
        request_entitlement_change(
            session,
            tenant_id=tid,
            actor=AdminActor(one),
            action=ACTION_REVOKE_ROLE,
            target_user_id=two,
            target_role_id=role_id,
            now=NOW,
        )
        session.commit()

        set_tenant_context(session, tid)
        mine = session.execute(select(EntitlementRequest.id)).scalars().all()
        assert len(mine) == 1, "the tenant cannot see its OWN request — RLS is too tight"

        set_tenant_context(session, str(uuid.uuid4()))
        theirs = session.execute(select(EntitlementRequest.id)).scalars().all()
        assert theirs == [], "another tenant's context saw entitlement requests"
    finally:
        session.rollback()
        session.close()


def test_a_resolved_request_cannot_be_approved_TWICE(factory) -> None:  # noqa: ANN001
    """Re-approval must be refused, and the check READS the log rather than a flag.

    The request row is immutable, so there is no flag to set — "already resolved" can only mean
    "a resolution row points at this one". A second approval would re-apply an act somebody has
    already decided, which for a revocation means re-running the orphan check against a state the
    first approval already changed.
    """
    tid, role_id, one, two = _seed_two_admins(factory)
    session = factory()
    try:
        set_tenant_context(session, tid)
        target = AppUser(
            id=str(uuid.uuid4()),
            tenant_id=tid,
            external_subject=f"tw@{tid[:8]}",
            display_name="TW",
            is_active=True,
        )
        session.add(target)
        session.flush()
        req = request_entitlement_change(
            session,
            tenant_id=tid,
            actor=AdminActor(one),
            action=ACTION_REVOKE_ROLE,
            target_user_id=two,
            target_role_id=role_id,
            now=NOW,
        )
        assert req.status == STATUS_PENDING
        approve_entitlement_change(
            session, tenant_id=tid, actor=AdminActor(two), request_id=req.id, now=NOW
        )
        session.commit()

        set_tenant_context(session, tid)
        with pytest.raises(EntitlementError, match="already been resolved"):
            approve_entitlement_change(
                session, tenant_id=tid, actor=AdminActor(two), request_id=req.id, now=NOW
            )
    finally:
        session.rollback()
        session.close()
