"""PostgreSQL SYMMETRIC-RLS + FR-bitemporal tests for P1B-3 instrument / instrument_terms /
identifier_xref (PROPRIETARY).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role (NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant invisibility + no-context→zero rows; forged/
no-context write → 42501; the cross-tenant linked-id (issuer_id / instrument_id / entity_id) guard
is
the SERVICE-LAYER ``*NotVisible`` predicate pre-commit (RLS does not tenant-check FK/polymorphic
targets); the POSITIVE symmetric-policy + FORCE-RLS assertion AND the unchanged closed-hybrid-set;
the
FR bitemporal protocol (supersede/correct close-out UPDATEs + reconstruct-as-of) under FORCE RLS;
the
FR table is not append-only (close-out UPDATE succeeds). Native-uuid trap (ORM/GUID inserts; raw
reads
via ``str()``).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.reference.identifier import create_identifier_xref
from irp_shared.reference.instrument import InstrumentNotVisible, create_instrument
from irp_shared.reference.instrument_terms import (
    correct_instrument_terms,
    create_instrument_terms,
    reconstruct_terms_as_of,
    supersede_instrument_terms,
)
from irp_shared.reference.issuer import IssuerNotVisible, create_issuer
from irp_shared.reference.legal_entity import create_legal_entity
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P1B3 = ("instrument", "instrument_terms", "identifier_xref")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("legal_entity", "issuer")  # for issuer-linked instruments
_RAILS = ("data_source", "lineage_edge")

_ACT = ReferenceActor(actor_id="a")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2027, 1, 1, tzinfo=UTC)


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role with grants on the P1B-3 + dep + rail tables."""
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
        for table in (*_P1B3, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_instrument(factory, tenant: str, code: str, **kw) -> str:  # noqa: ANN001, ANN003
    session = factory()
    try:
        set_tenant_context(session, tenant)
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=code,
            name=code,
            asset_class="BOND",
            actor=_ACT,
            **kw,
        )
        session.commit()
        return inst.id
    finally:
        session.close()


def _seed_issuer(factory, tenant: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        le = create_legal_entity(session, tenant_id=tenant, code="LE", name="LE", actor=_ACT)
        iss = create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_ACT)
        session.commit()
        return iss.id
    finally:
        session.close()


# --- symmetric isolation ---


def test_instrument_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_instrument(factory, a, "A_I")
        _seed_instrument(factory, b, "B_I")
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM instrument"))
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
        _seed_instrument(factory, str(uuid.uuid4()), "I")
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM instrument")).scalar_one() == 0
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
        with pytest.raises(ProgrammingError) as exc:
            create_instrument(
                session, tenant_id=b, code="X", name="X", asset_class="BOND", actor=_ACT
            )
        assert _is_rls_violation(exc.value)
        session.rollback()
        set_tenant_context(session, a)
        n = session.execute(
            text("SELECT count(*) FROM audit_event WHERE event_type = 'REFERENCE.CREATE'")
        ).scalar_one()
        assert n == 0
    finally:
        session.close()
        engine.dispose()


# --- cross-tenant linked-id guards are SERVICE-LAYER (not RLS 42501) ---


def test_cross_tenant_issuer_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_issuer = _seed_issuer(factory, b)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(IssuerNotVisible):  # service predicate, NOT a 42501
            create_instrument(
                session,
                tenant_id=a,
                code="X",
                name="X",
                asset_class="BOND",
                actor=_ACT,
                issuer_id=b_issuer,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_instrument_terms_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_inst = _seed_instrument(factory, b, "B_I")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(InstrumentNotVisible):
            create_instrument_terms(
                session, instrument_id=b_inst, acting_tenant=a, actor=_ACT, valid_from=_T0
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_identifier_entity_id_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_inst = _seed_instrument(factory, b, "B_I")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(InstrumentNotVisible):
            create_identifier_xref(
                session, tenant_id=a, instrument_id=b_inst, scheme="ISIN", value="V", actor=_ACT
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


# --- structural RLS assertions ---


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P1B3:
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


# --- FR bitemporal protocol under FORCE RLS ---


def test_fr_bitemporal_as_of_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        inst = create_instrument(
            session, tenant_id=a, code="FR_I", name="FR_I", asset_class="BOND", actor=_ACT
        )
        session.flush()
        from decimal import Decimal

        v1 = create_instrument_terms(
            session,
            instrument_id=inst.id,
            acting_tenant=a,
            actor=_ACT,
            valid_from=_T0,
            coupon_rate=Decimal("5.5"),
        )
        before = datetime.now(UTC)
        # supersede (valid-time close-out UPDATE under FORCE RLS) then correct (system-time close-
        # out)
        supersede_instrument_terms(
            session,
            instrument_id=inst.id,
            acting_tenant=a,
            actor=_ACT,
            effective_at=_T1,
            coupon_rate=Decimal("6.0"),
        )
        current = reconstruct_terms_as_of(session, inst.id, acting_tenant=a, valid_at=_T0)
        assert current is not None and current.id == v1.id  # valid-time pre-T1 = v1
        # correct v1 (as-known) and prove the known-time axis
        correct_instrument_terms(
            session,
            v1,
            restatement_reason="r",
            acting_tenant=a,
            actor=_ACT,
            coupon_rate=Decimal("5.25"),
        )
        as_known_before = reconstruct_terms_as_of(
            session, inst.id, acting_tenant=a, valid_at=_T0, known_at=before
        )
        assert as_known_before is not None and as_known_before.coupon_rate == Decimal("5.5")
        as_known_now = reconstruct_terms_as_of(session, inst.id, acting_tenant=a, valid_at=_T0)
        assert as_known_now is not None and as_known_now.coupon_rate == Decimal("5.25")
        session.commit()
        set_tenant_context(session, a)
        assert verify_chain(session, a).ok is True
    finally:
        session.close()
        engine.dispose()


def test_instrument_terms_not_append_only(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        inst = create_instrument(
            session, tenant_id=a, code="I", name="I", asset_class="BOND", actor=_ACT
        )
        terms = create_instrument_terms(
            session, instrument_id=inst.id, acting_tenant=a, actor=_ACT, valid_from=_T0
        )
        session.commit()
        set_tenant_context(session, a)
        # A close-out UPDATE succeeds (no irp_prevent_mutation trigger -> FR is not append-only).
        result = session.execute(
            text("UPDATE instrument_terms SET valid_to = now() WHERE id = CAST(:i AS uuid)"),
            {"i": terms.id},
        )
        assert result.rowcount == 1
        session.commit()
    finally:
        session.close()
        engine.dispose()
