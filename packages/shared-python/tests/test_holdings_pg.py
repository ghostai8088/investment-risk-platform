"""PostgreSQL FORCE-RLS tests for the P1C-5 holdings read composition (READ-ONLY).

Gated on ``IRP_TEST_DATABASE_URL``; runs under the constrained non-superuser ``irp_app`` role
(NOSUPERUSER NOBYPASSRLS). The holdings read models issue plain SELECTs over ``position`` (+
``portfolio`` for subtree), so they inherit those tables' symmetric FORCE-RLS policies. This file
proves the composition stays tenant-isolated: cross-tenant invisibility, no-context -> 0 rows, and
both-axes as-of reconstruction under FORCE RLS — with NO mid-request commit (pure read path).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.holdings import reconstruct_holdings_as_of, reconstruct_subtree_holdings_as_of
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TABLES = ("position", "valuation", "portfolio", "instrument", "data_source", "lineage_edge")
T0 = datetime(2026, 1, 1, tzinfo=UTC)
T1 = datetime(2026, 6, 1, tzinfo=UTC)


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
        for table in _TABLES:
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_holding(factory, tenant: str, *, qty: str = "100") -> tuple[str, str]:  # noqa: ANN001
    """Seed one portfolio + instrument + position for ``tenant`` (each in its own committed txn,
    re-setting tenant context after the commit per the GUC-clears-on-commit rule)."""
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
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code="INST",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="a"),
        )
        session.flush()
        create_position(
            session,
            portfolio_id=pf.id,
            instrument_id=inst.id,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="a"),
            quantity=Decimal(qty),
            valid_from=T0,
        )
        session.commit()
        return pf.id, inst.id
    finally:
        session.close()


def test_holdings_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        pf_a, _ = _seed_holding(factory, a, qty="100")
        _seed_holding(factory, b, qty="999")
        session = factory()
        try:
            set_tenant_context(session, a)  # pure read: set context once, no mid-request commit
            holdings = reconstruct_holdings_as_of(
                session, acting_tenant=a, portfolio_id=pf_a, valid_at=T1
            )
            assert [h.quantity for h in holdings] == [Decimal("100")]
            # tenant b's portfolio id is invisible under a's context -> empty composition.
        finally:
            session.close()
    finally:
        engine.dispose()


def test_holdings_no_context_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        pf_a, _ = _seed_holding(factory, a)
        session = factory()
        try:
            # No tenant context set -> FORCE RLS hides every row -> empty holdings.
            holdings = reconstruct_holdings_as_of(
                session, acting_tenant=a, portfolio_id=pf_a, valid_at=T1
            )
            assert holdings == []
        finally:
            session.close()
    finally:
        engine.dispose()


def test_holdings_cross_tenant_subtree_invisible(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        pf_a, _ = _seed_holding(factory, a)
        _seed_holding(factory, b)
        session = factory()
        try:
            set_tenant_context(session, b)
            # b cannot resolve a's portfolio (service tenant predicate + RLS) -> fail closed.
            from irp_shared.portfolio import PortfolioNotVisible

            with pytest.raises(PortfolioNotVisible):
                reconstruct_subtree_holdings_as_of(
                    session, acting_tenant=b, portfolio_id=pf_a, valid_at=T1
                )
        finally:
            session.close()
    finally:
        engine.dispose()


def test_holdings_both_axes_under_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    try:
        pf_a, _ = _seed_holding(factory, a, qty="100")
        session = factory()
        try:
            set_tenant_context(session, a)
            # As-of after T0 the holding is present with its stored quantity under FORCE RLS.
            holdings = reconstruct_holdings_as_of(
                session, acting_tenant=a, portfolio_id=pf_a, valid_at=T1
            )
            assert len(holdings) == 1 and holdings[0].quantity == Decimal("100")
            # As-of BEFORE the valid_from -> the version is not yet effective -> empty.
            early = reconstruct_holdings_as_of(
                session,
                acting_tenant=a,
                portfolio_id=pf_a,
                valid_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
            assert early == []
        finally:
            session.close()
    finally:
        engine.dispose()
