"""PostgreSQL SYMMETRIC-RLS + append-only tests for P2-5 curve + curve_point (PROPRIETARY).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role. Proves, for BOTH tables: cross-tenant invisibility + no-context->zero rows; the RLS ``WITH
CHECK`` forged-tenant denial (42501); the POSITIVE symmetric-policy + FORCE-RLS assertion per table
AND the unchanged closed 5-table hybrid set (curve is NOT hybrid); the ``curve_point`` append-only
P0001 trigger (proven under GRANTED UPDATE/DELETE so it is the trigger, not a privilege denial — the
``dataset_snapshot_component`` precedent); and a verifiable audit chain after a governed capture.
(``curve`` is FR — NOT append-only; no P0001 trigger.)
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import InternalError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import CurveActor, CurveNode, capture_curve, list_curve_points
from irp_shared.reference.models import Currency

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P2_5 = ("curve", "curve_point")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_CD = date(2026, 6, 1)
_ACT = CurveActor(actor_id="a")


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
        # GRANT UPDATE/DELETE on curve_point so append-only proves the P0001 TRIGGER (not a 42501).
        for table in (*_P2_5, "currency", *_RAILS):
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
                    Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VA)
                )
        session.commit()
    finally:
        session.close()


def _seed_curve(factory, tenant: str, source: str = "BLOOMBERG") -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        head = capture_curve(
            session,
            curve_type="TREASURY",
            currency_code="USD",
            curve_date=_CD,
            curve_source=source,
            nodes=[
                CurveNode("3M", 90, "ZERO_RATE", Decimal("0.0425")),
                CurveNode("1Y", 365, "DISCOUNT_FACTOR", Decimal("0.9560")),
            ],
            acting_tenant=tenant,
            actor=_ACT,
            valid_from=_VA,
        )
        session.commit()
        return head.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        _seed_curve(factory, a)
        _seed_curve(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _P2_5:
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
        _seed_curve(factory, str(uuid.uuid4()))
        session = factory()
        try:
            for table in _P2_5:
                assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
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
        curve_id = _seed_curve(factory, a)  # a real curve owned by a (FK target for curve_point)
        session = factory()
        try:
            set_tenant_context(session, a)
            # (1) forged-tenant INSERT on the FR header (curve) -> WITH CHECK 42501
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO curve "
                        "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                        "curve_type, currency_code, reference_key, curve_date, curve_source, "
                        "point_count, record_version) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                        "'TREASURY', 'USD', 'NONE', CURRENT_DATE, 'BLOOMBERG', 1, 1)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b},
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
            # (2) forged-tenant INSERT on the append-only child (curve_point) -> WITH CHECK 42501
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc2:
                session.execute(
                    text(
                        "INSERT INTO curve_point "
                        "(id, tenant_id, system_from, curve_id, tenor_label, tenor_days, "
                        "value_type, point_value) "
                        "VALUES (CAST(:id AS uuid), CAST(:b AS uuid), now(), CAST(:cid AS uuid), "
                        "'5Y', 1825, 'ZERO_RATE', 0.05)"
                    ),
                    {"id": str(uuid.uuid4()), "b": b, "cid": curve_id},
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
            for table in _P2_5:
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


def test_curve_point_append_only_p0001(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        _seed_system_currencies(factory)
        curve_id = _seed_curve(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            point_id = list_curve_points(session, curve_id, acting_tenant=a)[0].id
            # GRANTED UPDATE/DELETE -> the P0001 irp_prevent_mutation trigger fires (not 42501).
            with pytest.raises((InternalError, ProgrammingError)) as exc:
                session.execute(
                    text("UPDATE curve_point SET point_value = 9 WHERE id = CAST(:i AS uuid)"),
                    {"i": point_id},
                )
            assert "P0001" in str(exc.value) or "append-only" in str(exc.value).lower()
            session.rollback()
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
        _seed_curve(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            n = session.execute(
                text("SELECT count(*) FROM audit_event WHERE event_type = 'MARKET.CURVE_CREATE'")
            ).scalar_one()
            assert n == 1  # ONE event per curve (header-grained, not per node)
            assert verify_chain(session, a).ok is True
        finally:
            session.close()
    finally:
        engine.dispose()
