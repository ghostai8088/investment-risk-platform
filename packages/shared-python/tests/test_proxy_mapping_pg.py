"""PostgreSQL SYMMETRIC-RLS tests for PA-0 proxy_mapping (ENT-019, PROPRIETARY, FR).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser
``irp_app`` role. Proves: cross-tenant invisibility + no-context→zero rows; the RLS ``WITH CHECK``
forged-tenant denial (42501); the POSITIVE symmetric-policy + FORCE-RLS assertion AND the unchanged
closed 5-table hybrid set (proxy_mapping is NOT hybrid); that the table is NOT append-only (an FR
close-out UPDATE SUCCEEDS — no P0001 trigger, the factor_return precedent); a cross-tenant resolve
fails closed; and a verifiable audit chain (MARKET.PROXY_MAPPING_*) after a governed capture.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
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
    ProxyMappingActor,
    ProxyMappingNotVisible,
    capture_factor,
    capture_proxy_mapping,
    resolve_proxy_mapping,
    supersede_proxy_mapping,
)
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor

_ACT = ProxyMappingActor(actor_id="a")

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_PA_0 = ("proxy_mapping",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("instrument", "issuer", "legal_entity", "factor")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_VA2 = datetime(2026, 6, 15, tzinfo=UTC)


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
        # GRANT UPDATE/DELETE on proxy_mapping so the FR close-out UPDATE proves the table is NOT
        # append-only (an UPDATE succeeds — no P0001 trigger, unlike var_backtest_result).
        for table in (*_PA_0, *_DEPS, "currency", *_RAILS):
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


def _seed(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    """Seed a private instrument + a factor + a proxy_mapping; return (instrument_id, factor_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"PE-{uuid.uuid4().hex[:6]}",
            name="Fund",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        factor = capture_factor(
            session,
            factor_code=f"EQ-{uuid.uuid4().hex[:6]}",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code="USD",
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
        ).id
        session.flush()
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=factor,
            weight=Decimal("0.7"),
            acting_tenant=tenant,
            actor=_ACT,
            valid_from=_VA,
        )
        session.commit()
        return inst, factor
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed(factory, a)
        _seed(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM proxy_mapping"))
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
        _seed_system_currencies(factory)
        _seed(factory, str(uuid.uuid4()))
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM proxy_mapping")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_forged_tenant_insert_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        inst, factor = _seed(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO proxy_mapping "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "private_instrument_id, factor_id, weight, mapping_method, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "CAST(:inst AS uuid), CAST(:factor AS uuid), 0.5, 'MANUAL', 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "inst": inst, "factor": factor},
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_symmetric_policy_and_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(URL, poolclass=NullPool)  # structural read as the owner
    try:
        with engine.connect() as conn:
            qual, check = conn.execute(
                text("SELECT qual, with_check FROM pg_policies WHERE tablename = 'proxy_mapping'")
            ).one()
            assert "app.current_tenant" in qual and "app.current_tenant" in check
            assert "SYSTEM" not in qual.upper().replace("CURRENT_SETTING", "")  # never hybrid
            forced = conn.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'proxy_mapping'")
            ).scalar_one()
            assert forced is True
            hybrid = conn.execute(
                text("SELECT tablename FROM pg_policies WHERE qual LIKE :pat ORDER BY tablename"),
                {"pat": f"%{SYSTEM_TENANT_ID}%"},
            ).fetchall()
            assert {r[0] for r in hybrid} == set(_P1B1_HYBRID)
    finally:
        engine.dispose()


def test_not_append_only_supersede_updates_succeed(app_url: str) -> None:
    """proxy_mapping is FR (NOT append-only) — an effective-dated supersede's close-out UPDATE to
    the prior head's valid_to SUCCEEDS (no P0001 trigger; the factor_return precedent)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        inst, factor = _seed(factory, tenant)
        session = factory()
        try:
            set_tenant_context(session, tenant)
            supersede_proxy_mapping(
                session,
                private_instrument_id=inst,
                factor_id=factor,
                weight=Decimal("0.75"),
                acting_tenant=tenant,
                actor=_ACT,
                effective_at=_VA2,
            )
            session.commit()  # the FR close-out UPDATE committed — NOT blocked
            set_tenant_context(session, tenant)  # re-arm the GUC (SET LOCAL cleared at commit)
            rows = session.execute(
                text("SELECT count(*) FROM proxy_mapping WHERE valid_to IS NOT NULL")
            ).scalar_one()
            assert rows == 1  # the prior head was closed out
        finally:
            session.close()
    finally:
        engine.dispose()


def test_cross_tenant_resolve_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            row_id = session.execute(text("SELECT id FROM proxy_mapping LIMIT 1")).scalar_one()
        finally:
            session.close()
        session = factory()
        try:
            set_tenant_context(session, b)
            with pytest.raises(ProxyMappingNotVisible):
                resolve_proxy_mapping(session, str(row_id), acting_tenant=b)
        finally:
            session.close()
    finally:
        engine.dispose()


def test_audit_chain_verifies(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed(factory, tenant)
        session = factory()
        try:
            set_tenant_context(session, tenant)
            assert verify_chain(session, tenant).ok is True
        finally:
            session.close()
    finally:
        engine.dispose()
