"""PostgreSQL SYMMETRIC-RLS tests for P2-7 benchmark_level + benchmark_return (ENT-052).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role. Proves, for BOTH FR series tables: cross-tenant invisibility + no-context->zero rows; the RLS
``WITH CHECK`` forged-tenant denial (42501); the symmetric-policy + FORCE-RLS assertion per table
AND the unchanged closed 5-table hybrid set (benchmark series is NOT hybrid); that NEITHER table is
append-only (a FR close-out UPDATE SUCCEEDS — no P0001 trigger); a cross-tenant benchmark resolve
fails closed; a verifiable audit chain (MARKET.BENCHMARK_LEVEL_* + _RETURN_*) after a governed
capture; and a 17-significant-digit ``PreciseDecimal`` value round-trips EXACTLY on the
authoritative engine.
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
    LEVEL_TYPE_PRICE_RETURN,
    RETURN_BASIS_PRICE,
    BenchmarkActor,
    BenchmarkNotVisible,
    capture_benchmark,
    capture_benchmark_level,
    capture_benchmark_return,
    reconstruct_benchmark_return_as_of,
    resolve_benchmark,
)
from irp_shared.reference.models import Currency

_ACT = BenchmarkActor(actor_id="a")

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P2_7 = ("benchmark_level", "benchmark_return")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_LD = date(2026, 5, 29)


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
        # GRANT UPDATE/DELETE on the series so an FR close-out UPDATE proves NEITHER is append-only.
        # (SELECT/INSERT/UPDATE/DELETE on the series + benchmark + currency + rails.)
        for table in (*_P2_7, "benchmark", "currency", *_RAILS):
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
        for ccy in ("USD",):
            if ccy not in existing:
                session.add(
                    Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VF)
                )
        session.commit()
    finally:
        session.close()


def _seed_benchmark_series(factory, tenant: str, *, return_value: str = "0.0123") -> str:  # noqa: ANN001
    """Seed one benchmark (EV) + one level (FR) + one return (FR) for ``tenant``; return the
    benchmark id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        bm = capture_benchmark(
            session,
            benchmark_code="SPX",
            benchmark_source="SP_DJI",
            benchmark_currency="USD",
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.flush()
        bm = resolve_benchmark(session, bm.id, acting_tenant=tenant)
        capture_benchmark_level(
            session,
            bm,
            level_date=_LD,
            level_type=LEVEL_TYPE_PRICE_RETURN,
            level_value=Decimal("4500.25"),
            acting_tenant=tenant,
            actor=_ACT,
        )
        capture_benchmark_return(
            session,
            bm,
            return_date=_LD,
            return_basis=RETURN_BASIS_PRICE,
            return_value=Decimal(return_value),
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.commit()
        return bm.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_benchmark_series(factory, a)
        _seed_benchmark_series(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _P2_7:
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
        _seed_benchmark_series(factory, str(uuid.uuid4()))
        session = factory()
        try:
            for table in _P2_7:
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
        bm_id = _seed_benchmark_series(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO benchmark_level "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "benchmark_id, level_date, level_type, level_value, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "CAST(:bm AS uuid), CURRENT_DATE, 'PRICE_RETURN', 4500.25, 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "bm": bm_id},
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc2:
                session.execute(
                    text(
                        "INSERT INTO benchmark_return "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "benchmark_id, return_date, return_type, return_basis, return_value, "
                        "record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "CAST(:bm AS uuid), CURRENT_DATE, 'SIMPLE', 'PRICE', 0.01, 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "bm": bm_id},
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
            for table in _P2_7:
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
        bm_id = _seed_benchmark_series(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _P2_7:
                n = session.execute(
                    text(
                        f"UPDATE {table} SET valid_to = now() "
                        "WHERE benchmark_id = CAST(:bm AS uuid)"
                    ),
                    {"bm": bm_id},
                ).rowcount
                assert n == 1, table  # FR close-out UPDATE succeeds (no P0001 trigger)
            session.commit()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_resolve_foreign_benchmark_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        bm_a = _seed_benchmark_series(factory, a)
        session = factory()
        try:
            set_tenant_context(session, b)
            with pytest.raises(BenchmarkNotVisible):
                resolve_benchmark(session, bm_a, acting_tenant=b)
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
        _seed_benchmark_series(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            lvl = session.execute(
                text(
                    "SELECT count(*) FROM audit_event "
                    "WHERE event_type = 'MARKET.BENCHMARK_LEVEL_CREATE'"
                )
            ).scalar_one()
            ret = session.execute(
                text(
                    "SELECT count(*) FROM audit_event "
                    "WHERE event_type = 'MARKET.BENCHMARK_RETURN_CREATE'"
                )
            ).scalar_one()
            assert lvl == 1 and ret == 1
            assert verify_chain(session, a).ok is True
        finally:
            session.close()
    finally:
        engine.dispose()


def test_precise_decimal_full_width_return_roundtrips_exactly(app_url: str) -> None:
    """A deliberately float64-UNSAFE precision probe (not a representative return — TD-1 boundary
    fixture): a 20-significant-digit value at the FULL NUMERIC(20,12) width (8 integer + 12
    fractional places) round-trips byte-for-byte on PG. float64 carries only ~15-16 significant
    digits, so a plain Numeric column would corrupt this — the PreciseDecimal contract the value
    P3-7 pins depends on."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    # 8 integer + 12 fractional = 20 significant digits (the full column width); float64-unsafe.
    exact = Decimal("12345678.123456789012")
    try:
        _seed_system_currencies(factory)
        bm_id = _seed_benchmark_series(factory, a, return_value=str(exact))
        session = factory()
        try:
            set_tenant_context(session, a)
            row = reconstruct_benchmark_return_as_of(
                session,
                acting_tenant=a,
                benchmark_id=bm_id,
                return_date=_LD,
                return_basis=RETURN_BASIS_PRICE,
                valid_at=datetime(2030, 1, 1, tzinfo=UTC),
            )
            assert row is not None and row.return_value == exact
        finally:
            session.close()
    finally:
        engine.dispose()
