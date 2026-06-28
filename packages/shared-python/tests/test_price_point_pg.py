"""PostgreSQL SYMMETRIC-RLS tests for P2-4 price_point (PROPRIETARY, FR — NEVER hybrid).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role. Proves: cross-tenant invisibility + no-context->zero rows; the ``WITH CHECK`` forged-tenant
denial (42501); the POSITIVE symmetric-policy + FORCE-RLS assertion AND the unchanged closed 5-table
hybrid set (price_point is NOT hybrid); a verifiable chain after a governed capture; and that a
foreign tenant's instrument is invisible (the cross-tenant FK fail-closed under real RLS).
(price_point is FR — NOT append-only; no P0001 trigger.)
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import PriceActor, capture_price
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.reference.models import Currency, Instrument

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P2_4 = ("price_point",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_PD = date(2026, 6, 1)
_ACT = PriceActor(actor_id="a")


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
        for table in (*_P2_4, "instrument", "currency", *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_system_currencies(factory) -> None:  # noqa: ANN001
    """Idempotent (the module shares one Postgres DB across tests): insert only missing codes."""
    session = factory()
    try:
        set_tenant_context(session, SYSTEM_TENANT_ID)
        existing = {
            r[0]
            for r in session.execute(
                select(Currency.code).where(Currency.tenant_id == SYSTEM_TENANT_ID)
            )
        }
        for ccy in ("USD", "EUR"):
            if ccy not in existing:
                session.add(
                    Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VA)
                )
        session.commit()
    finally:
        session.close()


def _seed_instrument(factory, tenant: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        inst = Instrument(
            tenant_id=tenant,
            code=f"I-{uuid.uuid4().hex[:8]}",
            name="x",
            asset_class="EQUITY",
            valid_from=_VA,
        )
        session.add(inst)
        session.commit()
        return inst.id
    finally:
        session.close()


def _seed_price(factory, tenant: str, instrument_id: str, source: str = "BLOOMBERG") -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = capture_price(
            session,
            instrument_id=instrument_id,
            price_date=_PD,
            price=Decimal("150.25"),
            currency_code="USD",
            price_source=source,
            acting_tenant=tenant,
            actor=_ACT,
            valid_from=_VA,
        )
        session.commit()
        return row.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_price(factory, a, _seed_instrument(factory, a))
        _seed_price(factory, b, _seed_instrument(factory, b))
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM price_point"))
            }
            assert tenants == {a}
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_price(factory, a, _seed_instrument(factory, a))
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM price_point")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_forged_tenant_insert_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        iid = _seed_instrument(factory, a)  # instrument owned by a (FK valid)
        session = factory()
        try:
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO price_point "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "instrument_id, price_date, price, price_type, currency_code, "
                        "price_source, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "CAST(:iid AS uuid), CURRENT_DATE, 1.0, 'CLOSE', 'USD', 'BLOOMBERG', 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "iid": iid},
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_policy_symmetric_and_force_rls_and_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            qual, with_check = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE schemaname='public' AND tablename='price_point'"
                )
            ).one()
            assert SYSTEM_TENANT_ID not in qual and SYSTEM_TENANT_ID not in with_check  # NOT hybrid
            assert qual == with_check  # symmetric
            enabled, forced = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='price_point' AND relnamespace='public'::regnamespace"
                )
            ).one()
            assert enabled is True and forced is True
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


def test_foreign_instrument_invisible_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        foreign_iid = _seed_instrument(factory, b)  # instrument owned by b
        session = factory()
        try:
            set_tenant_context(session, a)
            with pytest.raises(InstrumentNotVisible):  # b's instrument is invisible to a (RLS)
                capture_price(
                    session,
                    instrument_id=foreign_iid,
                    price_date=_PD,
                    price=Decimal("1"),
                    currency_code="USD",
                    price_source="BLOOMBERG",
                    acting_tenant=a,
                    actor=_ACT,
                    valid_from=_VA,
                )
        finally:
            session.close()
    finally:
        engine.dispose()


def test_audit_chain_after_capture(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_price(factory, a, _seed_instrument(factory, a))
        session = factory()
        try:
            set_tenant_context(session, a)
            n = session.execute(
                text("SELECT count(*) FROM audit_event WHERE event_type = 'MARKET.PRICE_CREATE'")
            ).scalar_one()
            assert n == 1
            assert verify_chain(session, a).ok is True
        finally:
            session.close()
    finally:
        engine.dispose()
