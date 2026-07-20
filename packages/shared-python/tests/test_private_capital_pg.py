"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY tests for CC-1 private capital (ENT-015/016).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser
``irp_app`` role (NOSUPERUSER NOBYPASSRLS). Proves, for all THREE tables: cross-tenant
invisibility + no-context→zero rows; the **append-only P0001 TRIGGER** on both event
tables (irp_app HAS UPDATE/DELETE grants so the rejection is the trigger, not a
privilege denial, with a POSITIVE CONTROL first); commitment (FR) close-out UPDATE still
WORKS under the same role (the supersede protocol needs it — the deliberate contrast
with the IA tables); the RLS ``WITH CHECK`` forged-tenant INSERT denial (42501); the
POSITIVE symmetric-policy + FORCE-RLS assertion AND the unchanged closed hybrid set; a
negation reversal under FORCE RLS with the partial-unique double-reversal race fence.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.private_capital.capital_flow_service import (
    CapitalFlowActor,
    capture_capital_call,
    reverse_capital_call,
)
from irp_shared.private_capital.commitment_service import (
    CommitmentActor,
    capture_commitment,
    supersede_commitment,
)
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_CC1 = ("commitment", "capital_call", "distribution")
_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("portfolio", "instrument")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_ACT = CommitmentActor(actor_id="a")
_FLOW = CapitalFlowActor(actor_id="a")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


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
        for table in (*_CC1, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_pf_fund(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code="PF",
            name="pf",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="a"),
        )
        fund = create_instrument(
            session,
            tenant_id=tenant,
            code="FUND",
            name="f",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id="a"),
        )
        session.commit()
        return pf.id, fund.id
    finally:
        session.close()


def _seed_commitment_and_call(factory, tenant: str) -> tuple[str, str, str, str]:  # noqa: ANN001
    pf_id, fund_id = _seed_pf_fund(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        c = capture_commitment(
            session,
            portfolio_id=pf_id,
            instrument_id=fund_id,
            committed_amount=Decimal("25000000.000000"),
            currency_code="USD",
            commitment_date=date(2026, 1, 15),
            acting_tenant=tenant,
            actor=_ACT,
        )
        call = capture_capital_call(
            session,
            portfolio_id=pf_id,
            instrument_id=fund_id,
            event_date=date(2026, 2, 10),
            amount=Decimal("5000000.000000"),
            currency_code="USD",
            call_type="DRAWDOWN",
            acting_tenant=tenant,
            actor=_FLOW,
        )
        session.commit()
        return c.id, call.id, pf_id, fund_id
    finally:
        session.close()


def test_tenant_isolation_all_three(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_commitment_and_call(factory, a)
        _seed_commitment_and_call(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _CC1:
                tenants = {
                    str(r[0])
                    for r in session.execute(text(f"SELECT DISTINCT tenant_id FROM {table}"))
                }
                assert tenants <= {a}, f"{table}: foreign tenant visible"
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_commitment_and_call(factory, str(uuid.uuid4()))
        session = factory()
        try:
            for table in _CC1:
                assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_append_only_trigger_blocks_event_mutation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _, call_id, _, _ = _seed_commitment_and_call(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        # POSITIVE CONTROL: the row is present + RLS-visible (so UPDATE/DELETE reach it).
        assert (
            session.execute(
                text("SELECT count(*) FROM capital_call WHERE id = CAST(:i AS uuid)"),
                {"i": call_id},
            ).scalar_one()
            == 1
        )
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE capital_call SET amount = 1 WHERE id = CAST(:i AS uuid)"),
                {"i": call_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("DELETE FROM capital_call WHERE id = CAST(:i AS uuid)"), {"i": call_id}
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_commitment_close_out_update_works(app_url: str) -> None:
    # The deliberate FR/IA contrast: commitment (FR) has NO append-only trigger — the
    # supersede protocol's close-out UPDATE must WORK under the same constrained role.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _, _, pf_id, fund_id = _seed_commitment_and_call(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        new = supersede_commitment(
            session,
            portfolio_id=pf_id,
            instrument_id=fund_id,
            committed_amount=Decimal("30000000.000000"),
            currency_code="USD",
            commitment_date=date(2026, 1, 15),
            acting_tenant=a,
            actor=_ACT,
            effective_at=session.execute(
                text("SELECT valid_from + interval '1 day' FROM commitment WHERE valid_to IS NULL")
            ).scalar_one(),
        )
        session.commit()
        set_tenant_context(session, a)
        assert session.execute(text("SELECT count(*) FROM commitment")).scalar_one() == 2
        assert new.record_version == 2
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_pf, a_fund = _seed_pf_fund(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "INSERT INTO commitment "
                    "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                    "portfolio_id, instrument_id, committed_amount, currency_code, "
                    "commitment_date, record_version) VALUES "
                    "(CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                    "CAST(:p AS uuid), CAST(:n AS uuid), 1, 'USD', CURRENT_DATE, 1)"
                ),
                {"id": str(uuid.uuid4()), "b": b, "p": a_pf, "n": a_fund},
            )
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_policies_symmetric_force_rls_and_hybrid_set(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _CC1:
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
            assert hybrid == set(_HYBRID), f"hybrid set drifted: {hybrid}"
    finally:
        engine.dispose()


def test_reversal_under_rls_and_double_reversal_race(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _, call_id, _, _ = _seed_commitment_and_call(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        rev = reverse_capital_call(
            session, capital_call_id=call_id, acting_tenant=a, actor=_FLOW, reason="err"
        )
        session.commit()
        set_tenant_context(session, a)
        assert rev.reverses_id == call_id
        total = session.execute(text("SELECT sum(amount) FROM capital_call")).scalar_one()
        assert total == Decimal("0.000000")  # negation Σ self-correction under RLS
        n = session.execute(
            text(
                "SELECT count(*) FROM audit_event "
                "WHERE event_type = 'PRIVATE.CAPITAL_CALL_REVERSE'"
            )
        ).scalar_one()
        assert n == 1
        assert verify_chain(session, a).ok is True
        # The index race fence: a raw second reversal INSERT (bypassing the service
        # validator, as a concurrent loser would) is rejected by the partial-unique.
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO capital_call "
                    "(id, tenant_id, system_from, portfolio_id, instrument_id, "
                    "commitment_version_id, event_date, amount, currency_code, call_type, "
                    "reverses_id) "
                    "SELECT CAST(:id AS uuid), tenant_id, now(), portfolio_id, instrument_id, "
                    "commitment_version_id, event_date, -amount, currency_code, call_type, "
                    "CAST(:t AS uuid) FROM capital_call WHERE id = CAST(:t AS uuid)"
                ),
                {"id": str(uuid.uuid4()), "t": call_id},
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()
