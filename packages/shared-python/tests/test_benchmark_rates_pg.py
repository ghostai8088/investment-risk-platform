"""PostgreSQL SYMMETRIC-RLS + savepoint tests for DATA-1 benchmark_rate (ENT-070).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser
``irp_app`` role (NOSUPERUSER NOBYPASSRLS). Proves, for the NEW table BY NAME (the CAL-1a lesson —
the child's own ``WITH CHECK``, not the parent's): cross-tenant invisibility + no-context → zero
rows; the forged-tenant INSERT denial (42501) ON ``benchmark_rate``; the symmetric-policy +
FORCE-RLS assertion + benchmark_rate NOT in the closed hybrid set; an FR close-out UPDATE
SUCCEEDS (not append-only); and the ratified SAVEPOINT semantics on the AUTHORITATIVE engine —
a completeness FAIL leaves ZERO rate rows, an unmoved horizon, and a PERSISTED FAIL result (the
real-PG twin of the unit negative control; savepoint behavior is engine-sensitive).
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import (
    COMPLETENESS_RULE_CODE,
    BenchmarkActor,
    BenchmarkRate,
    capture_benchmark,
    capture_benchmark_rate,
    refresh_benchmark_rates,
    resolve_benchmark,
)
from irp_shared.marketdata.models import (
    OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
    QUOTE_BASIS_DISCOUNT_360,
    RATE_TYPE_BILL_DISCOUNT_YIELD,
    Benchmark,
)
from irp_shared.marketdata.tb3ms_rates import (
    TB3MS_COMPLETE_THROUGH,
    TB3MS_RATES,
    TB3MS_SERIES_START,
)
from irp_shared.reference.models import HYBRID_TABLES, Currency

_ACT = BenchmarkActor(actor_id="a")

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")

_SERIES_KW = dict(
    rate_type=RATE_TYPE_BILL_DISCOUNT_YIELD,
    quote_basis=QUOTE_BASIS_DISCOUNT_360,
    observation_convention=OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
)


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
        for table in ("benchmark_rate", "benchmark", "currency", *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_usd(factory) -> None:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, SYSTEM_TENANT_ID)
        exists = session.execute(
            select(Currency.code).where(
                Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == "USD"
            )
        ).first()
        if not exists:
            session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD"))
        session.commit()
    finally:
        session.close()


def _seed_rate(factory, tenant: str) -> str:  # noqa: ANN001
    """One benchmark head + one captured rate for ``tenant``; returns the benchmark id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        bm = capture_benchmark(
            session,
            benchmark_code="US-TBILL-3M",
            benchmark_source="US-FRB-H15",
            benchmark_currency="USD",
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.flush()
        bm = resolve_benchmark(session, bm.id, acting_tenant=tenant)
        capture_benchmark_rate(
            session,
            bm,
            rate_date=date(2026, 6, 1),
            rate_value=Decimal("0.0366"),
            acting_tenant=tenant,
            actor=_ACT,
            **_SERIES_KW,
        )
        session.commit()
        return bm.id
    finally:
        session.close()


def test_tenant_isolation_and_no_context_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_usd(factory)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_rate(factory, t1)
    session = factory()
    try:
        set_tenant_context(session, t2)
        assert session.execute(select(BenchmarkRate)).scalars().all() == []
    finally:
        session.close()
    bare = factory()
    try:  # no tenant context at all → zero rows (FORCE RLS, no BYPASSRLS)
        assert bare.execute(select(BenchmarkRate)).scalars().all() == []
    finally:
        bare.close()
    engine.dispose()


def test_forged_tenant_insert_denied_on_benchmark_rate_by_name(app_url: str) -> None:
    """The CHILD table's own WITH CHECK, asserted BY NAME (the CAL-1a parent-vs-child lesson)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_usd(factory)
    t1, victim = str(uuid.uuid4()), str(uuid.uuid4())
    bm_id = _seed_rate(factory, t1)
    session = factory()
    try:
        set_tenant_context(session, t1)
        with pytest.raises(ProgrammingError) as excinfo:
            session.execute(
                text(
                    "INSERT INTO benchmark_rate (id, tenant_id, benchmark_id, rate_date, "
                    "rate_type, quote_basis, observation_convention, rate_value, record_version, "
                    "valid_from, system_from, created_at, updated_at) "
                    "VALUES (:id, :forged, :bm, '2026-05-01', 'BILL_DISCOUNT_YIELD', "
                    "'DISCOUNT_360', 'MONTHLY_AVG_BUSINESS_DAYS', 0.0360, 1, now(), now(), "
                    "now(), now())"
                ),
                {"id": str(uuid.uuid4()), "forged": victim, "bm": bm_id},
            )
            session.flush()
        assert _is_rls_violation(excinfo.value)
        assert "benchmark_rate" in str(excinfo.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_policy_symmetric_force_rls_and_not_hybrid(app_url: str) -> None:
    engine = make_engine(URL, poolclass=NullPool)  # superuser: catalog reads
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'benchmark_rate'"
            )
        ).one()
        assert row == (True, True)
        qual, check = conn.execute(
            text(
                "SELECT pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid) "
                "FROM pg_policy WHERE polname = 'tenant_isolation_benchmark_rate'"
            )
        ).one()
        assert qual == check and "app.current_tenant" in qual  # SYMMETRIC (own == own)
    assert "benchmark_rate" not in HYBRID_TABLES  # the closed 7-set is UNCHANGED
    engine.dispose()


def test_fr_close_out_update_succeeds_not_append_only(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_usd(factory)
    tenant = str(uuid.uuid4())
    _seed_rate(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        head = session.execute(select(BenchmarkRate)).scalars().one()
        head.valid_to = head.valid_from  # an FR close-out UPDATE — must NOT hit a P0001 trigger
        session.flush()
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_completeness_fail_savepoint_semantics_on_real_pg(app_url: str) -> None:
    """The ratified OQ-DATA-1-6 semantics on the authoritative engine: a gappy refresh raises,
    leaves ZERO rate rows and an unmoved horizon, and the FAIL evidence PERSISTS."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_usd(factory)
    tenant = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, tenant)
        bm = capture_benchmark(
            session,
            benchmark_code="US-TBILL-3M",
            benchmark_source="US-FRB-H15",
            benchmark_currency="USD",
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.flush()
        bm = resolve_benchmark(session, bm.id, acting_tenant=tenant)
        gappy = {d: v for d, v in TB3MS_RATES if d != date(2025, 3, 1)}
        with pytest.raises(DataQualityError):
            refresh_benchmark_rates(
                session,
                bm,
                rates=gappy,
                series_start=TB3MS_SERIES_START,
                acting_tenant=tenant,
                actor=_ACT,
                complete_through=TB3MS_COMPLETE_THROUGH,
                **_SERIES_KW,
            )
        session.commit()  # the surviving unit: head + FAIL evidence, NO rate rows
    finally:
        session.close()
    verify = factory()
    try:
        set_tenant_context(verify, tenant)
        assert verify.execute(select(BenchmarkRate)).scalars().all() == []
        head = verify.execute(select(Benchmark)).scalars().one()
        assert head.rates_complete_through is None
        rule = verify.execute(
            select(DataQualityRule).where(DataQualityRule.code == COMPLETENESS_RULE_CODE)
        ).scalar_one()
        result = verify.execute(
            select(DataQualityResult).where(DataQualityResult.rule_id == rule.id)
        ).scalar_one()
        assert result.outcome == "FAIL" and "2025-03" in (result.detail or "")
    finally:
        verify.close()
        engine.dispose()
