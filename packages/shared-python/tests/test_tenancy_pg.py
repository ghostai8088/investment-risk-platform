"""ONBOARD-1a on real PostgreSQL — the half the unit tier structurally cannot prove.

Two controls in this slice are invisible to SQLite **by mechanism, not by accident**, and saying
which is the whole point of this file existing:

* the **boundary exists-check** is dialect-gated (``tenancy/boundary.py``) — it runs on PostgreSQL
  and is a no-op elsewhere, because the ~2,500 unit-tier suites mint arbitrary uuid4 tenants and
  would otherwise all fail closed against an empty registry;
* the **two-context onboarding transaction** re-arms ``app.current_tenant`` mid-transaction, which
  is a no-op on SQLite — so the unit tier's clone tests pass whether or not the RLS choreography is
  right. On PostgreSQL, reading the SYSTEM templates AFTER the re-arm would silently return
  nothing (``role`` is FORCE-RLS), producing a tenant with no roles and a green test.

That second one is the FK-1 lesson restated: a proof that runs on the engine without the
constraint proves the code runs, not that the constraint holds.

**AND THIS SUITE ALMOST MADE THE SAME MISTAKE ONE LAYER DOWN.** Its first draft connected as the
default ``irp`` role — which is the container superuser and therefore carries **BYPASSRLS**. Every
RLS assertion below would have passed with row-level security switched off entirely: the very
thing being tested, bypassed by the connection testing it. It was caught only because one test
asserted ``rolbypassrls IS FALSE`` about its own connection and went red. So the whole suite now
runs as the constrained ``irp_app`` role (NOSUPERUSER NOBYPASSRLS), the shipped pattern from the
benchmark/active-risk PG suites — and that first assertion stays, as the floor that keeps it
honest. A test that would pass with the control disabled is not a test of the control.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import CLONED_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.entitlement.models import Role, RolePermission
from irp_shared.tenancy.boundary import TenantNotAdmitted, assert_tenant_admitted
from irp_shared.tenancy.models import (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    Tenant,
)
from irp_shared.tenancy.service import onboard_tenant

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


#: Tables this suite touches as the constrained role.
_GRANTED = (
    "tenant",
    "app_user",
    "role",
    "role_permission",
    "user_role",
    "permission",
    "audit_event",
)


@pytest.fixture(scope="module")
def app_url() -> str:
    """A NOSUPERUSER/NOBYPASSRLS login — the shipped pattern, and here it is load-bearing.

    The default ``irp`` role is the container superuser: BYPASSRLS. Running these tests as it would
    switch off the isolation they assert.
    """
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
def db(app_url: str):  # noqa: ANN201
    engine = make_engine(app_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _register(db, tenant_id: str, status: str = TENANT_STATUS_ACTIVE) -> None:
    db.add(
        Tenant(
            id=tenant_id,
            code=f"t-{tenant_id[:8]}",
            display_name="T",
            status=status,
            provenance="ONBOARDED",
        )
    )
    db.flush()


# ------------------------------------------------------------------- the boundary, both arms
def test_an_unregistered_tenant_is_REFUSED(db) -> None:
    stranger = str(uuid.uuid4())
    with pytest.raises(TenantNotAdmitted, match="not registered"):
        assert_tenant_admitted(db, stranger)


def test_a_registered_ACTIVE_tenant_is_ADMITTED(db) -> None:
    """The positive control (P18): without it, 'refused' is equally consistent with a check that
    refuses everything — including a check reading an empty table it can never populate."""
    known = str(uuid.uuid4())
    _register(db, known)
    assert_tenant_admitted(db, known)  # must not raise


def test_a_SUSPENDED_tenant_is_REFUSED(db) -> None:
    """The status ships ENFORCED even though no verb sets it (the setter is a ratified deferral).

    A status the boundary ignores is a comment. This is what makes SUSPENDED a real state the day
    an operator writes it directly, rather than the day someone builds `tenant.suspend`.
    """
    suspended = str(uuid.uuid4())
    _register(db, suspended, status=TENANT_STATUS_SUSPENDED)
    with pytest.raises(TenantNotAdmitted, match="SUSPENDED"):
        assert_tenant_admitted(db, suspended)


def test_the_SYSTEM_tenant_passes_the_boundary(db) -> None:
    """Without its registry row the platform operator's own token fails the check it exists to
    serve — the omission the verifier pass found in the design's first draft."""
    assert_tenant_admitted(db, SYSTEM_TENANT_ID)


def test_the_registry_read_is_not_hidden_by_RLS(db) -> None:
    """``tenant`` is PLATFORM-GLOBAL: the check must work with NO tenant context armed.

    If the registry were tenant-scoped, the check authorizing a context would itself need one — and
    would be hidden by the isolation it is about to grant.
    """
    known = str(uuid.uuid4())
    _register(db, known)
    db.commit()
    db.execute(text("RESET app.current_tenant"))
    assert_tenant_admitted(db, known)
    db.execute(text("DELETE FROM tenant WHERE id = :i"), {"i": known})
    db.commit()


# ------------------------------------------- the two-context transaction, where SQLite is blind
def test_the_clone_reads_SYSTEM_templates_BEFORE_the_re_arm(db) -> None:
    """The ordering the verifier pass corrected, proven where it can actually fail.

    ``role`` and ``role_permission`` are FORCE-RLS tenant-scoped. If the onboarding act re-armed to
    the new tenant BEFORE reading the SYSTEM templates, the read would return zero rows under RLS
    and the tenant would be created with no roles at all — and every SQLite test would still pass,
    because SQLite has no RLS. The assertion is therefore on the CLONE COUNT: a silently-empty read
    is the failure this file exists to catch.
    """
    set_tenant_context(db, SYSTEM_TENANT_ID)
    result = onboard_tenant(
        db,
        code=f"pg-{uuid.uuid4().hex[:8]}",
        display_name="PG Onboarded",
        admin_external_subject=f"auth0|{uuid.uuid4().hex[:8]}",
        admin_display_name="PG Admin",
        actor_id=str(uuid.uuid4()),
    )
    assert set(result.roles_cloned) == set(CLONED_TEMPLATES), (
        "the clone did not copy every template — on PostgreSQL this is what a post-re-arm read of "
        "FORCE-RLS SYSTEM rows looks like: silence, not an error"
    )
    assert result.grants_cloned > 0, (
        "roles were cloned with NO grants — the grant read was RLS-hidden while the role read "
        "was not, which is the half-broken version of the same defect"
    )

    # And the rows are genuinely under the NEW tenant's context, not the SYSTEM one.
    set_tenant_context(db, result.tenant_id)
    codes = {
        str(c)
        for c in db.execute(select(Role.code).where(Role.tenant_id == result.tenant_id))
        .scalars()
        .all()
    }
    assert codes == set(CLONED_TEMPLATES)
    db.rollback()


def test_the_onboarding_transaction_needs_no_BYPASSRLS(db) -> None:
    """The whole authority model rests on this, and it is asserted rather than assumed.

    The connection is the ordinary application role. If any part of the two-context act required
    BYPASSRLS, this would fail — and the CLAUDE.md invariant would have been violated by the slice
    that amended it.
    """
    bypass = db.execute(
        text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).scalar_one()
    assert bypass is False, "the test connection has BYPASSRLS — this suite proves nothing"

    set_tenant_context(db, SYSTEM_TENANT_ID)
    result = onboard_tenant(
        db,
        code=f"norls-{uuid.uuid4().hex[:8]}",
        display_name="No BYPASSRLS",
        admin_external_subject=f"auth0|{uuid.uuid4().hex[:8]}",
        admin_display_name="Admin",
        actor_id=str(uuid.uuid4()),
    )
    assert result.grants_cloned > 0
    db.rollback()


def test_a_refused_onboarding_leaves_the_session_USABLE(db) -> None:
    """The savepointed duplicate-code probe, proven on the engine that poisons transactions.

    On PostgreSQL a raised integrity error leaves the transaction ABORTED, and the request session
    is a single transaction (AD-016) — so a refusal implemented as a caught IntegrityError would
    hand the caller a session on which every later statement fails. REPRO-1 spent three scrutiny
    stages on exactly this class with a unit test that stayed green, because SQLite does not
    poison sessions.
    """
    from irp_shared.tenancy.service import TenantOnboardingError

    set_tenant_context(db, SYSTEM_TENANT_ID)
    code = f"dup-{uuid.uuid4().hex[:8]}"
    onboard_tenant(
        db,
        code=code,
        display_name="First",
        admin_external_subject=f"auth0|{uuid.uuid4().hex[:8]}",
        admin_display_name="A",
        actor_id=str(uuid.uuid4()),
    )
    set_tenant_context(db, SYSTEM_TENANT_ID)
    with pytest.raises(TenantOnboardingError, match="already exists"):
        onboard_tenant(
            db,
            code=code,
            display_name="Second",
            admin_external_subject=f"auth0|{uuid.uuid4().hex[:8]}",
            admin_display_name="B",
            actor_id=str(uuid.uuid4()),
        )
    # THE ASSERTION: the session still works. A poisoned transaction raises InFailedSqlTransaction.
    assert db.execute(text("SELECT 1")).scalar_one() == 1
    db.rollback()


def test_the_platform_catalog_row_is_DELIVERED_by_the_migration(db) -> None:
    """P17 at the database, not at the constant: the operator's grant must actually be there.

    The platform catalog cannot ride ``sync_catalog``'s template machinery — being outside
    ``ROLE_TEMPLATES`` is the design — so migration 0067 inserts it inline, and this asserts the
    delivery landed on a database that has been migrated to head.
    """
    from irp_shared.entitlement.platform_catalog import (
        PLATFORM_CODES,
        PLATFORM_OPERATOR_ROLE,
        platform_permission_id,
        platform_role_id,
    )

    set_tenant_context(db, SYSTEM_TENANT_ID)
    role = db.execute(
        select(Role).where(Role.id == platform_role_id(PLATFORM_OPERATOR_ROLE))
    ).scalar_one_or_none()
    assert role is not None, "migration 0067 did not deliver the platform_operator role"
    granted = {
        str(p)
        for p in db.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
        )
        .scalars()
        .all()
    }
    assert granted == {platform_permission_id(c) for c in PLATFORM_CODES}
