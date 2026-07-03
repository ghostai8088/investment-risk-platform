"""PostgreSQL SYMMETRIC-RLS tests for P3-2 factor + factor_return (ENT-025, PROPRIETARY).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role. Proves, for BOTH tables: cross-tenant invisibility + no-context->zero rows; the RLS ``WITH
CHECK`` forged-tenant denial (42501); the POSITIVE symmetric-policy + FORCE-RLS assertion per table
AND the unchanged closed 5-table hybrid set (factor is NOT hybrid); that NEITHER table is
append-only (a FR ``factor_return`` close-out UPDATE + an EV ``factor`` in-place UPDATE both
SUCCEED — no P0001 trigger, the difference from ``curve_point``); a cross-tenant factor resolve
fails closed;
and a verifiable audit chain (REFERENCE.* definition + MARKET.FACTOR_RETURN_* series) after a
governed capture.
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
from irp_shared.marketdata import (
    FactorActor,
    FactorNotVisible,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.reference.models import Currency

_ACT = FactorActor(actor_id="a")

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P3_2 = ("factor", "factor_return")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_RD = date(2026, 5, 29)


def _is_rls_violation(error: Exception) -> bool:
    orig = getattr(error, "orig", None)
    return getattr(orig, "sqlstate", None) == "42501" or "row-level security" in str(error).lower()


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
        # GRANT UPDATE/DELETE on factor_return so the FR close-out UPDATE proves NEITHER table is
        # append-only (an UPDATE succeeds — no P0001 trigger, unlike curve_point).
        for table in (*_P3_2, "currency", *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_system_currencies(factory) -> None:  # noqa: ANN001
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
                    Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VF)
                )
        session.commit()
    finally:
        session.close()


def _seed_factor(factory, tenant: str, source: str = "MSCI_BARRA") -> str:  # noqa: ANN001
    """Seed one factor (EV) + one factor_return (FR) for ``tenant``; return the factor id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        f = capture_factor(
            session,
            factor_code="MOMENTUM",
            factor_source=source,
            factor_family="STYLE",
            currency_code="USD",
            acting_tenant=tenant,
            actor=_ACT,
        )
        capture_factor_return(
            session,
            f,
            return_date=_RD,
            return_value=Decimal("0.0123"),
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.commit()
        return f.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_factor(factory, a)
        _seed_factor(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _P3_2:
                tenants = {
                    str(r[0])
                    for r in session.execute(text(f"SELECT DISTINCT tenant_id FROM {table}"))
                }
                assert tenants == {a}, table
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_system_currencies(factory)
        _seed_factor(factory, str(uuid.uuid4()))
        session = factory()
        try:
            for table in _P3_2:
                assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_forged_tenant_insert_denied_both_tables(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        factor_id = _seed_factor(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            # (1) forged-tenant INSERT on the EV header (factor) -> WITH CHECK 42501
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO factor "
                        "(id, tenant_id, valid_from, created_at, updated_at, "
                        "factor_code, factor_source, factor_family, frequency, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), "
                        "'X', 'Y', 'STYLE', 'DAILY', 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b},
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
            # (2) forged-tenant INSERT on the FR series (factor_return) -> 42501
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc2:
                session.execute(
                    text(
                        "INSERT INTO factor_return "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "factor_id, return_date, return_type, return_value, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "CAST(:fid AS uuid), CURRENT_DATE, 'SIMPLE', 0.5, 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "fid": factor_id},
                )
            assert _is_rls_violation(exc2.value)
            session.rollback()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_policy_symmetric_and_force_rls_both_tables_hybrid_unchanged(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P3_2:
                qual, with_check = conn.execute(
                    text(
                        "SELECT qual, with_check FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).one()
                assert SYSTEM_TENANT_ID not in qual and SYSTEM_TENANT_ID not in with_check, table
                assert qual == with_check, table  # symmetric
                enabled, forced = conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname=:t AND relnamespace='public'::regnamespace"
                    ),
                    {"t": table},
                ).one()
                assert enabled is True and forced is True, table
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


def test_neither_table_append_only_fr_close_out_update_succeeds(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        factor_id = _seed_factor(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            # FR close-out UPDATE on factor_return SUCCEEDS (no P0001 trigger / ORM guard) — the
            # difference from curve_point. (Done via raw SQL to bypass the binder protocol.)
            n = session.execute(
                text(
                    "UPDATE factor_return SET valid_to = now() "
                    "WHERE factor_id = CAST(:fid AS uuid)"
                ),
                {"fid": factor_id},
            ).rowcount
            assert n == 1
            # an EV in-place UPDATE on factor also succeeds.
            session.execute(
                text("UPDATE factor SET record_version = 2 WHERE id = CAST(:fid AS uuid)"),
                {"fid": factor_id},
            )
            session.commit()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_resolve_foreign_factor_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        factor_a = _seed_factor(factory, a)  # factor owned by a
        session = factory()
        try:
            set_tenant_context(session, b)
            # tenant b cannot resolve a's factor (fail-closed before any return write).
            with pytest.raises(FactorNotVisible):
                resolve_factor(session, factor_a, acting_tenant=b)
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
        _seed_factor(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            ref = session.execute(
                text("SELECT count(*) FROM audit_event WHERE event_type = 'REFERENCE.CREATE'")
            ).scalar_one()
            mkt = session.execute(
                text(
                    "SELECT count(*) FROM audit_event "
                    "WHERE event_type = 'MARKET.FACTOR_RETURN_CREATE'"
                )
            ).scalar_one()
            assert ref == 1 and mkt == 1  # split family: definition REFERENCE.*, series MARKET.*
            assert verify_chain(session, a).ok is True
        finally:
            session.close()
    finally:
        engine.dispose()
