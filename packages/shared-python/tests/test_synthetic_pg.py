"""PostgreSQL FORCE-RLS tests for the P1C-6 synthetic seed (governed, never BYPASSRLS).

Gated on ``IRP_TEST_DATABASE_URL``; runs under the constrained non-superuser ``irp_app`` role
(NOSUPERUSER NOBYPASSRLS). Proves the synthetic seed writes only the SYNTHETIC tenant's rows under
FORCE ROW LEVEL SECURITY (never BYPASSRLS), that a DIFFERENT tenant sees none of them, that a
no-context session sees zero rows, and that the per-tenant audit chain verifies. The deterministic
seed is **not** idempotent (uuid5 ids), so it is seeded exactly ONCE per module; the tests read it.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.position import Position
from irp_shared.synthetic import SYNTHETIC_TENANT_ID, build_synthetic_dataset

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

#: Every table the governed seed writes (+ the rails it roots audit/lineage on).
_TABLES = (
    "instrument",
    "identifier_xref",
    "portfolio",
    "transaction",
    "position",
    "valuation",
    "data_source",
    "lineage_edge",
)


@pytest.fixture(scope="module")
def seeded_url() -> str:
    """Create the constrained ``irp_app`` role + grants, then seed the synthetic dataset ONCE under
    FORCE RLS as ``irp_app``. Yields the app-role URL; tests open read-only sessions against it."""
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
        for table in _TABLES:
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()

    app_url = (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )
    os.environ["IRP_ALLOW_SYNTHETIC_SEED"] = "1"
    engine = make_engine(app_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        build_synthetic_dataset(session, allow_synthetic_seed=True)  # sets SYNTHETIC context itself
        session.commit()
    finally:
        os.environ.pop("IRP_ALLOW_SYNTHETIC_SEED", None)
        session.close()
        engine.dispose()
    return app_url


def test_seed_writes_only_synthetic_tenant(seeded_url: str) -> None:
    engine = make_engine(seeded_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        set_tenant_context(session, SYNTHETIC_TENANT_ID)
        tenants = {
            str(r[0]) for r in session.execute(text("SELECT DISTINCT tenant_id FROM position"))
        }
        assert tenants == {SYNTHETIC_TENANT_ID}  # only the synthetic tenant's rows are visible
        assert session.execute(select(func.count()).select_from(Position)).scalar_one() == 6
    finally:
        session.close()
        engine.dispose()


def test_other_tenant_sees_no_synthetic_rows(seeded_url: str) -> None:
    engine = make_engine(seeded_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        set_tenant_context(session, str(uuid.uuid4()))  # an unrelated tenant
        assert session.execute(select(func.count()).select_from(Position)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_no_context_sees_zero_rows(seeded_url: str) -> None:
    engine = make_engine(seeded_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        # No tenant context set → FORCE RLS hides every row.
        assert session.execute(text("SELECT count(*) FROM position")).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_seed_audit_chain_verifies_under_force_rls(seeded_url: str) -> None:
    engine = make_engine(seeded_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        set_tenant_context(session, SYNTHETIC_TENANT_ID)
        assert verify_chain(session, SYNTHETIC_TENANT_ID).ok is True
    finally:
        session.close()
        engine.dispose()
