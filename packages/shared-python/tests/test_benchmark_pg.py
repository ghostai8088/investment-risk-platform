"""PostgreSQL SYMMETRIC-RLS tests for P2-6 benchmark + benchmark_constituent (PROPRIETARY).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role. Proves, for BOTH tables: cross-tenant invisibility + no-context->zero rows; the RLS ``WITH
CHECK`` forged-tenant denial (42501); the POSITIVE symmetric-policy + FORCE-RLS assertion per table
AND the unchanged closed 5-table hybrid set (benchmark is NOT hybrid); that NEITHER table is
append-only (a FR ``benchmark_constituent`` close-out UPDATE SUCCEEDS — no P0001 trigger, the
difference from ``curve_point``); a cross-tenant parent membership fails closed; and a verifiable
audit chain (REFERENCE.* definition + MARKET.BENCHMARK_CONSTITUENT_* membership) after a governed
capture.
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
    BenchmarkActor,
    BenchmarkNotVisible,
    ConstituentInput,
    capture_benchmark,
    capture_membership,
    resolve_benchmark,
)
from irp_shared.reference.models import Currency, Instrument

_ACT = BenchmarkActor(actor_id="a")

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P2_6 = ("benchmark", "benchmark_constituent")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_ED = date(2026, 3, 31)


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
        # GRANT UPDATE/DELETE on benchmark_constituent so the FR close-out UPDATE proves NEITHER
        # table is append-only (an UPDATE succeeds — no P0001 trigger, unlike curve_point).
        for table in (*_P2_6, "instrument", "currency", *_RAILS):
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


def _seed_benchmark(factory, tenant: str, source: str = "SP_DJI") -> tuple[str, str]:  # noqa: ANN001
    """Seed an instrument + a benchmark + one membership for ``tenant``; return (benchmark_id,
    instrument_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        inst = Instrument(
            tenant_id=tenant,
            code="INS0",
            name="I0",
            asset_class="EQUITY",
            instrument_type="EQUITY",
            valid_from=_VF,
            record_version=1,
        )
        session.add(inst)
        session.flush()
        bm = capture_benchmark(
            session,
            benchmark_code="SPX",
            benchmark_source=source,
            benchmark_currency="USD",
            acting_tenant=tenant,
            actor=_ACT,
        )
        capture_membership(
            session,
            bm,
            effective_date=_ED,
            constituents=[ConstituentInput(inst.id, Decimal("1.0"))],
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.commit()
        return bm.id, inst.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_benchmark(factory, a)
        _seed_benchmark(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _P2_6:
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
        _seed_benchmark(factory, str(uuid.uuid4()))
        session = factory()
        try:
            for table in _P2_6:
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
        bm_id, inst_id = _seed_benchmark(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            # (1) forged-tenant INSERT on the EV header (benchmark) -> WITH CHECK 42501
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO benchmark "
                        "(id, tenant_id, valid_from, created_at, updated_at, "
                        "benchmark_code, benchmark_source, benchmark_currency, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), "
                        "'X', 'Y', 'USD', 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b},
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
            # (2) forged-tenant INSERT on the FR membership (benchmark_constituent) -> 42501
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc2:
                session.execute(
                    text(
                        "INSERT INTO benchmark_constituent "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "benchmark_id, instrument_id, effective_date, weight, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "CAST(:bm AS uuid), CAST(:inst AS uuid), CURRENT_DATE, 0.5, 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "bm": bm_id, "inst": inst_id},
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
            for table in _P2_6:
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
        bm_id, _ = _seed_benchmark(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            # FR close-out UPDATE on benchmark_constituent SUCCEEDS (no P0001 trigger / ORM guard) —
            # the difference from curve_point. (Done via raw SQL to bypass the binder protocol.)
            n = session.execute(
                text(
                    "UPDATE benchmark_constituent SET valid_to = now() "
                    "WHERE benchmark_id = CAST(:bm AS uuid)"
                ),
                {"bm": bm_id},
            ).rowcount
            assert n == 1
            # an EV in-place UPDATE on benchmark also succeeds.
            session.execute(
                text("UPDATE benchmark SET record_version = 2 WHERE id = CAST(:bm AS uuid)"),
                {"bm": bm_id},
            )
            session.commit()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_membership_against_foreign_parent_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        bm_a, inst_a = _seed_benchmark(factory, a)  # benchmark owned by a
        session = factory()
        try:
            set_tenant_context(session, b)
            # tenant b cannot resolve a's benchmark (fail-closed before any membership write).
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
        _seed_benchmark(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            ref = session.execute(
                text("SELECT count(*) FROM audit_event WHERE event_type = 'REFERENCE.CREATE'")
            ).scalar_one()
            mkt = session.execute(
                text(
                    "SELECT count(*) FROM audit_event "
                    "WHERE event_type = 'MARKET.BENCHMARK_CONSTITUENT_CREATE'"
                )
            ).scalar_one()
            assert (
                ref == 1 and mkt == 1
            )  # split family: definition REFERENCE.*, membership MARKET.*
            assert verify_chain(session, a).ok is True
        finally:
            session.close()
    finally:
        engine.dispose()
