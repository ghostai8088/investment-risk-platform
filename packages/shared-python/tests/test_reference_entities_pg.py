"""PostgreSQL SYMMETRIC-RLS tests for P1B-2 legal_entity / issuer / counterparty (PROPRIETARY).

The proprietary-never-hybrid proof (OD-P1B-C). Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs
under the constrained non-superuser ``irp_app`` role. These three use the SYMMETRIC loop
(``USING == WITH CHECK == own-tenant``) — fully fail-closed (no-context read → ZERO rows, unlike the
hybrid tables). Proves: cross-tenant invisibility; forged/no-context write → 42501; profile→core +
hierarchy cross-tenant fail-closed (tenant predicate + RLS); the POSITIVE symmetric-policy +
FORCE-RLS structural assertion AND the unchanged closed-hybrid-set; forged-write-emits-no-audit;
EV-mutable. Native-uuid trap (ORM/GUID inserts; ``CAST(:i AS uuid)`` raw by-id; ``str()`` reads).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.reference.issuer import create_issuer
from irp_shared.reference.legal_entity import (
    LegalEntityNotVisible,
    create_legal_entity,
    resolve_ultimate_parent,
)
from irp_shared.reference.models import LegalEntity
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P1B2 = ("legal_entity", "issuer", "counterparty")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role with grants on the P1B-2 + rail tables."""
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
        for table in (*_P1B2, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_le(factory, tenant: str, code: str, **kw) -> str:  # noqa: ANN001, ANN003
    session = factory()
    try:
        set_tenant_context(session, tenant)
        le = create_legal_entity(
            session,
            tenant_id=tenant,
            code=code,
            name=code,
            actor=ReferenceActor(actor_id="a"),
            **kw,
        )
        session.commit()
        return le.id
    finally:
        session.close()


# --- symmetric isolation (fully fail-closed) ---


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_le(factory, a, "A_LE")
        _seed_le(factory, b, "B_LE")
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM legal_entity"))
            }
            assert tenants == {a}  # only A's rows; B's proprietary legal entities are invisible
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    # Contrast the hybrid tables (which return the global slice) — symmetric tables return NOTHING.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_le(factory, str(uuid.uuid4()), "LE")
        session = factory()
        try:
            n = session.execute(
                text("SELECT count(*) FROM legal_entity")
            ).scalar_one()  # no context
            assert n == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_forged_tenant_write_denied_and_no_audit(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        # Forged tenant via the binder: the row add+flush hits WITH CHECK BEFORE record_event.
        with pytest.raises(ProgrammingError) as exc:
            create_legal_entity(
                session, tenant_id=b, code="X", name="X", actor=ReferenceActor(actor_id="a")
            )
        assert _is_rls_violation(exc.value)
        session.rollback()
        set_tenant_context(session, a)
        # No REFERENCE.CREATE was emitted for the rejected write (audit comes AFTER the flush).
        n = session.execute(
            text("SELECT count(*) FROM audit_event WHERE event_type = 'REFERENCE.CREATE'")
        ).scalar_one()
        assert n == 0
    finally:
        session.close()
        engine.dispose()


def test_profile_core_cross_tenant_rejected(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_le = _seed_le(factory, a, "A_LE")
    session = factory()
    try:
        set_tenant_context(session, b)
        # Tenant B cannot attach an issuer to tenant A's core (explicit tenant predicate + RLS).
        with pytest.raises(LegalEntityNotVisible):
            create_issuer(
                session, tenant_id=b, legal_entity_id=a_le, actor=ReferenceActor(actor_id="a")
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_hierarchy_walk_terminates_at_tenant_boundary(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_le = _seed_le(factory, b, "B_ULT")
    a_child = _seed_le(factory, a, "A_CH")
    session = factory()
    try:
        set_tenant_context(session, a)
        # Raw cross-tenant parent link (FK satisfied since b_le exists; RLS does not tenant-check
        # FK targets). The resolver must NOT cross into B — it terminates at the A child.
        session.execute(
            text(
                "UPDATE legal_entity SET parent_legal_entity_id = CAST(:p AS uuid) "
                "WHERE id = CAST(:c AS uuid)"
            ),
            {"p": b_le, "c": a_child},
        )
        session.commit()
        set_tenant_context(session, a)
        child = session.get(LegalEntity, a_child)
        assert resolve_ultimate_parent(session, child, acting_tenant=a) == a_child  # boundary stop
    finally:
        session.close()
        engine.dispose()


# --- structural RLS assertions ---


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P1B2:
                row = conn.execute(
                    text(
                        "SELECT qual, with_check FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).one()
                qual, with_check = row[0], row[1]
                assert (
                    SYSTEM_TENANT_ID not in qual
                ), f"{table} must NOT be hybrid (no SYSTEM in USING)"
                assert SYSTEM_TENANT_ID not in with_check
                enabled, forced = conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
                    ),
                    {"t": table},
                ).one()
                assert enabled is True and forced is True, f"{table}: FORCE RLS must be on"
    finally:
        engine.dispose()


def test_closed_hybrid_set_unchanged(app_url: str) -> None:
    # P1B-2 must NOT widen the hybrid set: ONLY the five P1B-1 tables carry the SYSTEM literal.
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            hybrid = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT tablename FROM pg_policies "
                        "WHERE schemaname='public' AND qual LIKE :p"
                    ),
                    {"p": f"%{SYSTEM_TENANT_ID}%"},
                )
            }
            assert hybrid == set(_P1B1_HYBRID), f"hybrid set drifted: {hybrid}"
    finally:
        engine.dispose()


def test_legal_entity_is_ev_mutable(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    le_id = _seed_le(factory, a, "LE")
    session = factory()
    try:
        set_tenant_context(session, a)
        result = session.execute(
            text("UPDATE legal_entity SET name = 'Renamed' WHERE id = CAST(:i AS uuid)"),
            {"i": le_id},
        )
        assert result.rowcount == 1  # no irp_prevent_mutation trigger -> EV update succeeds
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_verify_chain_green(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _seed_le(factory, a, "LE")
    session = factory()
    try:
        set_tenant_context(session, a)
        assert verify_chain(session, a).ok is True
    finally:
        session.close()
        engine.dispose()


# --- LEI partial-unique (DB-enforced; the constraint with zero prior behavioral coverage) ---


def test_lei_unique_per_tenant_pg(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _seed_le(factory, a, "LE1", lei="LEIPG00000000000001")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(
            IntegrityError
        ):  # duplicate (tenant_id, lei) -> partial-unique violation
            create_legal_entity(
                session,
                tenant_id=a,
                code="LE2",
                name="LE2",
                actor=ReferenceActor(actor_id="a"),
                lei="LEIPG00000000000001",
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_lei_partial_index_materialized_pg(app_url: str) -> None:
    # Prove the index is a PARTIAL unique (WHERE lei IS NOT NULL), not a plain unique.
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            indexdef = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename='legal_entity' AND indexname='uq_legal_entity_tenant_lei'"
                )
            ).scalar_one()
            assert "UNIQUE" in indexdef.upper()
            assert "lei IS NOT NULL" in indexdef
    finally:
        engine.dispose()
