"""PG-tier proof: the OIDC tenant claim MUST be canonicalized or RLS hides the app_user (SSO-1).

`get_principal` canonicalizes the token's tenant claim (`str(uuid.UUID(...))`) before it arms
`app.current_tenant`, because the `tenant_isolation` policy compares `tenant_id::text` (PostgreSQL
renders a uuid as lowercase-hyphenated) against the raw GUC. This proves, under a constrained
NON-superuser/NON-BYPASSRLS role against the real `app_user` policy, that a canonical context sees
the row while a raw uppercase context does NOT — i.e. why the canonicalization is load-bearing —
and that a cross-tenant context is hidden. `test_oidc_auth.py` (SQLite) proves the code path
canonicalizes; this proves the RLS reason it must.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.models import AppUser

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture
def seeded() -> Iterator[tuple[Session, str, str]]:
    """Seed one active app_user (as superuser) and yield a session on a constrained app role."""
    su_engine = make_engine(URL, poolclass=NullPool)
    tenant = str(uuid.uuid4())  # canonical lowercase-hyphenated
    subject = f"sub-{uuid.uuid4()}"
    with su_engine.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='irp_app') "
                "THEN CREATE ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "ELSE ALTER ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO irp_app"))
        conn.execute(text("GRANT SELECT ON app_user TO irp_app"))
    su_factory = make_session_factory(su_engine)
    seed = su_factory()
    user = AppUser(tenant_id=tenant, display_name="U", external_subject=subject, is_active=True)
    seed.add(user)
    seed.commit()
    user_id = user.id
    seed.close()

    app_url = (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )
    app_engine = make_engine(app_url, poolclass=NullPool)
    app_session = make_session_factory(app_engine)()
    try:
        yield app_session, tenant, subject
    finally:
        app_session.close()
        app_engine.dispose()
        cleanup = su_factory()
        cleanup.execute(text("DELETE FROM app_user WHERE id = :id"), {"id": user_id})
        cleanup.commit()
        cleanup.close()
        su_engine.dispose()


def _lookup(session: Session, subject: str) -> AppUser | None:
    return session.execute(
        select(AppUser).where(AppUser.external_subject == subject)
    ).scalar_one_or_none()


def test_canonical_context_sees_the_row(seeded: tuple[Session, str, str]) -> None:
    session, tenant, subject = seeded
    set_tenant_context(session, tenant)  # canonical, as get_principal arms it
    assert _lookup(session, subject) is not None


def test_raw_uppercase_context_is_rls_hidden_then_canonicalized_restores(
    seeded: tuple[Session, str, str],
) -> None:
    session, tenant, subject = seeded
    set_tenant_context(session, tenant.upper())  # NOT canonicalized — the false-deny bug
    assert _lookup(session, subject) is None
    # Canonicalizing it (exactly what get_principal does) restores visibility in the same txn.
    set_tenant_context(session, str(uuid.UUID(tenant.upper())))
    assert _lookup(session, subject) is not None


def test_cross_tenant_context_is_hidden(seeded: tuple[Session, str, str]) -> None:
    session, _tenant, subject = seeded
    set_tenant_context(session, str(uuid.uuid4()))  # a different tenant
    assert _lookup(session, subject) is None
