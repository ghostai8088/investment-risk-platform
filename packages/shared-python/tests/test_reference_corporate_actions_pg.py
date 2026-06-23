"""PostgreSQL SYMMETRIC-RLS tests for P1B-4 corporate_action (PROPRIETARY, EV; capture-only).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role (NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant invisibility + no-context→zero rows; the
cross-tenant ``instrument_id`` guard is the SERVICE-LAYER predicate pre-commit; the RLS ``WITH
CHECK``
backstop denies a forged-tenant write (42501); the POSITIVE symmetric-policy + FORCE-RLS assertion
AND
the unchanged closed-hybrid-set; EVT-143 status transition + EV-mutability under FORCE RLS. Native-
uuid
trap (ORM/GUID inserts; raw reads via ``str()``).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.reference.corporate_action import (
    create_corporate_action,
    transition_corporate_action_status,
)
from irp_shared.reference.instrument import InstrumentNotVisible, create_instrument
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P1B4 = ("corporate_action",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("instrument",)
_RAILS = ("data_source", "lineage_edge")
_ACT = ReferenceActor(actor_id="a")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


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
        for table in (*_P1B4, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_ca(factory, tenant: str, code: str) -> tuple[str, str]:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"INST_{code}",
            name=code,
            asset_class="BOND",
            actor=_ACT,
        )
        ca = create_corporate_action(
            session,
            tenant_id=tenant,
            code=code,
            instrument_id=inst.id,
            action_type="DIVIDEND",
            actor=_ACT,
        )
        session.commit()
        return ca.id, inst.id
    finally:
        session.close()


def _seed_instrument(factory, tenant: str, code: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        inst = create_instrument(
            session, tenant_id=tenant, code=code, name=code, asset_class="BOND", actor=_ACT
        )
        session.commit()
        return inst.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_ca(factory, a, "A_CA")
        _seed_ca(factory, b, "B_CA")
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM corporate_action"))
            }
            assert tenants == {a}
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_ca(factory, str(uuid.uuid4()), "CA")
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM corporate_action")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_cross_tenant_instrument_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_inst = _seed_instrument(factory, b, "B_INST")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(InstrumentNotVisible):  # service predicate, NOT a 42501
            create_corporate_action(
                session,
                tenant_id=a,
                code="CAx",
                instrument_id=b_inst,
                action_type="SPLIT",
                actor=_ACT,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_update_denied(app_url: str) -> None:
    # The RLS WITH CHECK backstop: a raw UPDATE re-stamping tenant_id to a foreign tenant is denied.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ca_id, _ = _seed_ca(factory, a, "CA")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "UPDATE corporate_action SET tenant_id = CAST(:b AS uuid) "
                    "WHERE id = CAST(:i AS uuid)"
                ),
                {"b": b, "i": ca_id},
            )
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P1B4:
                qual, with_check = conn.execute(
                    text(
                        "SELECT qual, with_check FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).one()
                assert SYSTEM_TENANT_ID not in qual, f"{table} must NOT be hybrid"
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


def test_status_change_and_ev_mutable_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        inst = create_instrument(
            session, tenant_id=a, code="INST", name="I", asset_class="BOND", actor=_ACT
        )
        ca = create_corporate_action(
            session,
            tenant_id=a,
            code="CA",
            instrument_id=inst.id,
            action_type="DIVIDEND",
            actor=_ACT,
        )
        # EVT-143 status transition under FORCE RLS (EV-mutable: the status UPDATE succeeds).
        transition_corporate_action_status(session, ca, new_status="CONFIRMED", actor=_ACT)
        session.commit()
        set_tenant_context(session, a)
        n = session.execute(
            text("SELECT count(*) FROM audit_event WHERE event_type = 'REFERENCE.STATUS_CHANGE'")
        ).scalar_one()
        assert n == 1
        assert verify_chain(session, a).ok is True
    finally:
        session.close()
        engine.dispose()
