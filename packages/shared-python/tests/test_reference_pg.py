"""PostgreSQL asymmetric-hybrid-RLS tests for reference (P1B-1; AD-013-R1, BR-17, AD-016/AD-015).

The platform's **first hybrid-tenancy** proof. Gated on ``IRP_TEST_DATABASE_URL`` (a superuser URL);
enforcement runs under the constrained non-superuser, non-BYPASSRLS ``irp_app`` role. Applies the
CI lessons: native ``uuid`` → ORM/``GUID`` for inserts, ``CAST(:i AS uuid)`` for raw by-id writes,
``str()`` for uuid reads; SQLSTATE 42501 (``_is_rls_violation``).

Proves both arms of the asymmetry: a tenant reads own + SYSTEM rows (``USING`` own-OR-SYSTEM) but
cannot write a SYSTEM row (``WITH CHECK`` single-tenant → 42501); no-context reads return ONLY the
global slice; children carry their own hybrid policy; the SYSTEM literal is in ``qual`` but never in
``with_check`` and exists on **only** the five tables (closed set / proprietary-never-hybrid); the
SYSTEM seed + tenant override form two independently-verifiable audit chains.

Isolation note: SYSTEM_TENANT_ID is a FIXED tenant, so its rows would collide across re-runs on
``UNIQUE(tenant_id, code)`` (currency.code is only ``String(3)`` — not randomizable like a tenant
UUID). The module-scoped ``app_url`` fixture therefore DELETEs the five reference tables once as the
superuser (re-run safe), and each test uses a distinct SYSTEM currency code.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.reference.bootstrap import seed_system_reference
from irp_shared.reference.calendar import HolidaySpec, create_calendar
from irp_shared.reference.currency import create_currency
from irp_shared.reference.models import CalendarHoliday, Currency
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role with grants on reference + rail tables; clears the five
    reference tables once (superuser, bypassing RLS) so the module is order/re-run independent."""
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
        for table in (*_HYBRID, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
        # Children first (FK order); superuser DELETE bypasses RLS to clear leftover SYSTEM rows.
        for table in ("rating_grade", "calendar_holiday", "currency", "calendar", "rating_scale"):
            conn.execute(text(f"DELETE FROM {table}"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_currency(factory, tenant: str, code: str, name: str) -> str:  # noqa: ANN001
    """Create a currency under ``tenant`` context (SYSTEM or a real tenant); return its id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        cur = create_currency(
            session, tenant_id=tenant, code=code, name=name, actor=ReferenceActor(actor_id="a")
        )
        session.commit()
        return cur.id
    finally:
        session.close()


def _codes_visible(factory, tenant: str | None) -> set[str]:  # noqa: ANN001
    """Return the set of currency codes visible under ``tenant`` context (None = no context)."""
    session = factory()
    try:
        if tenant is not None:
            set_tenant_context(session, tenant)
        return {r[0] for r in session.execute(text("SELECT code FROM currency"))}
    finally:
        session.close()


# --- both arms of the asymmetry: read own + SYSTEM; cannot write SYSTEM ---


def test_tenant_reads_own_plus_system(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_currency(factory, SYSTEM_TENANT_ID, "GA0", "Global")
        _seed_currency(factory, a, "TA1", "Tenant-A")
        _seed_currency(factory, b, "TB2", "Tenant-B")
        codes = _codes_visible(factory, a)
        assert "GA0" in codes  # SYSTEM global readable (the USING disjunct)
        assert "TA1" in codes  # own row readable
        assert "TB2" not in codes  # tenant B's override hidden (cross-tenant isolation holds)
    finally:
        engine.dispose()


def test_tenant_cannot_write_system_row(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="ZZZ", name="x", record_version=1))
        with pytest.raises(ProgrammingError) as exc:
            session.flush()  # WITH CHECK is single-tenant; SYSTEM disjunct is NOT present
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_and_system_writes_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    for forged in (b, SYSTEM_TENANT_ID):
        session = factory()
        try:
            set_tenant_context(session, a)
            session.add(Currency(tenant_id=forged, code="FXX", name="x", record_version=1))
            with pytest.raises(ProgrammingError) as exc:
                session.flush()
            assert _is_rls_violation(exc.value)
            session.rollback()
        finally:
            session.close()
    engine.dispose()


def test_no_context_read_returns_only_global(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        _seed_currency(factory, SYSTEM_TENANT_ID, "GB0", "Global")
        _seed_currency(factory, a, "TB1", "Tenant-A")
        codes = _codes_visible(factory, None)  # no app.current_tenant set
        # current_setting(...,true) = '' -> own clause false, SYSTEM clause true -> only the global.
        assert "GB0" in codes and "TB1" not in codes
        # Robust global-only invariant: EVERY row visible with no context is a SYSTEM_TENANT row
        # (not merely "TB1 absent" — that could pass spuriously if TB1 were never inserted).
        session = factory()
        try:
            visible_tenants = {
                str(r[0]) for r in session.execute(text("SELECT DISTINCT tenant_id FROM currency"))
            }
            assert visible_tenants <= {
                SYSTEM_TENANT_ID
            }, f"non-global rows leaked: {visible_tenants}"
        finally:
            session.close()
    finally:
        engine.dispose()


def test_currency_is_ev_mutable_at_db(app_url: str) -> None:
    # No irp_prevent_mutation on the five -> a REFERENCE.UPDATE (raw UPDATE) succeeds.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    cid = _seed_currency(factory, a, "TD0", "Mutable")
    session = factory()
    try:
        set_tenant_context(session, a)
        result = session.execute(
            text("UPDATE currency SET name = 'Renamed' WHERE id = CAST(:i AS uuid)"),
            {"i": cid},
        )
        assert result.rowcount == 1
        session.commit()
    finally:
        session.close()
        engine.dispose()


# --- child tables carry their own hybrid policy ---


def test_child_holiday_hybrid_visibility(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())

    def _seed_calendar(tenant: str, code: str) -> str:
        session = factory()
        try:
            set_tenant_context(session, tenant)
            cal = create_calendar(
                session,
                tenant_id=tenant,
                code=code,
                name=code,
                actor=ReferenceActor(actor_id="a"),
                holidays=[HolidaySpec(holiday_date=date(2026, 1, 1), name="NY")],
            )
            session.commit()
            return cal.id
        finally:
            session.close()

    try:
        sys_cal_id = _seed_calendar(SYSTEM_TENANT_ID, "CAL_SYS")
        _seed_calendar(b, "CAL_B")
        session = factory()
        try:
            set_tenant_context(session, a)
            holiday_tenants = {
                str(r[0]) for r in session.execute(text("SELECT tenant_id FROM calendar_holiday"))
            }
            # A sees SYSTEM head's holiday children (own policy admits SYSTEM) but NOT tenant B's.
            assert SYSTEM_TENANT_ID in holiday_tenants and b not in holiday_tenants
            # A cannot write a SYSTEM child either (valid SYSTEM parent FK so the rejection is
            # the hybrid WITH CHECK at 42501, not a 23503 FK violation — FK checks bypass RLS).
            session.add(
                CalendarHoliday(
                    tenant_id=SYSTEM_TENANT_ID,
                    calendar_id=sys_cal_id,
                    holiday_date=date(2026, 7, 4),
                    record_version=1,
                )
            )
            with pytest.raises(ProgrammingError) as exc:
                session.flush()
            assert _is_rls_violation(exc.value)
            session.rollback()
        finally:
            session.close()
    finally:
        engine.dispose()


# --- structural asymmetry + closed set (pg_policies introspection) ---


def test_policy_structure_is_asymmetric_and_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _HYBRID:
                row = conn.execute(
                    text(
                        "SELECT qual, with_check FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).one()
                qual, with_check = row[0], row[1]
                assert SYSTEM_TENANT_ID in qual, f"{table}.USING must contain the SYSTEM literal"
                assert (
                    SYSTEM_TENANT_ID not in with_check
                ), f"{table}.WITH CHECK must NOT contain the SYSTEM literal (cross-tenant breach)"
            # Closed set: the hybrid SYSTEM disjunct exists on ONLY the five tables.
            hybrid_tables = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT tablename FROM pg_policies "
                        "WHERE schemaname='public' AND qual LIKE :p"
                    ),
                    {"p": f"%{SYSTEM_TENANT_ID}%"},
                )
            }
            assert hybrid_tables == set(_HYBRID), f"hybrid set drifted: {hybrid_tables}"
    finally:
        engine.dispose()


def test_force_rls_enabled_on_all_five(app_url: str) -> None:
    # An ENABLEd-but-not-FORCEd policy is bypassed by the table owner — every hybrid table must be
    # both relrowsecurity AND relforcerowsecurity (so even the owner is subject; AD-016 / BR-17).
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _HYBRID:
                enabled, forced = conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
                    ),
                    {"t": table},
                ).one()
                assert enabled is True and forced is True, f"{table}: rls={enabled} force={forced}"
    finally:
        engine.dispose()


def test_data_source_is_not_hybrid(app_url: str) -> None:
    # data_source stays SYMMETRIC (proprietary-never-hybrid): no tenant may read another's source.
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            qual = conn.execute(
                text(
                    "SELECT qual FROM pg_policies "
                    "WHERE schemaname='public' AND tablename='data_source'"
                )
            ).scalar_one()
            assert SYSTEM_TENANT_ID not in qual
    finally:
        engine.dispose()


# --- dual-chain: SYSTEM seed + tenant override, both independently verifiable ---


def test_dual_chain_system_and_tenant(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        sys_id = _seed_currency(factory, SYSTEM_TENANT_ID, "GC0", "Global")
        _seed_currency(factory, a, "GC0", "Tenant-A override")  # override of the same code

        sys_session = factory()
        try:
            set_tenant_context(sys_session, SYSTEM_TENANT_ID)
            assert verify_chain(sys_session, SYSTEM_TENANT_ID).ok is True
            # The seeded global is lineage-rooted on the SYSTEM chain.
            assert_has_lineage(sys_session, "currency", sys_id, tenant_id=SYSTEM_TENANT_ID)
        finally:
            sys_session.close()

        a_session = factory()
        try:
            set_tenant_context(a_session, a)
            assert verify_chain(a_session, a).ok is True
            # Under A, the override + the global coexist (RLS USING returns the union).
            count = a_session.execute(
                text("SELECT count(*) FROM currency WHERE code = 'GC0'")
            ).scalar_one()
            assert count == 2
        finally:
            a_session.close()
    finally:
        engine.dispose()


def test_seed_system_reference_under_system_context(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        set_tenant_context(session, SYSTEM_TENANT_ID)
        seed_system_reference(session, actor_id="system")
        session.commit()
        set_tenant_context(session, SYSTEM_TENANT_ID)
        n_cur = session.execute(
            text("SELECT count(*) FROM currency WHERE tenant_id = CAST(:t AS uuid)"),
            {"t": SYSTEM_TENANT_ID},
        ).scalar_one()
        assert n_cur >= 4  # the representative ISO-4217 slice (USD/EUR/GBP/JPY)
        # A real tenant can read the seeded global slice.
        a = str(uuid.uuid4())
        set_tenant_context(session, a)
        assert session.execute(text("SELECT count(*) FROM currency")).scalar_one() >= n_cur
    finally:
        session.close()
        engine.dispose()
