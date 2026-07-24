"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY + OPS-NO-GRANT tests for LIM-1 (ENT-031 limit_definition
EV / ENT-033 breach IA).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
(NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant limit invisibility (RLS); the append-only P0001
TRIGGER on ``breach`` (irp_app HAS UPDATE + a POSITIVE control, so the rejection is the trigger, NOT
a privilege) while the EV ``limit_definition`` head IS updatable; a forged-tenant breach insert is
denied (WITH CHECK 42501); the ``uq_breach_limit_run`` double-detect constraint; and — the standing
doctrine invariant — the BYPASSRLS ``irp_ops`` role has NO grant on either limit/breach table.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.calc.service import create_run
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_STATUS_DETECTED,
    LIMIT_KIND_HARD,
    THRESHOLD_UNIT_CURRENCY,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.limit.service import (
    LimitError,
    approve_limit,
    create_limit,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.risk.events import RUN_TYPE_VAR

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_LIM = ("limit_definition", "breach")
_DEPS = ("portfolio", "benchmark", "calculation_run")
_RAILS = ("data_source", "lineage_edge")
_ACTOR = LimitActor(actor_id="risk-mgr-2l")
_APPROVER = LimitActor(actor_id="risk-mgr-2l-b")


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
        for table in (*_LIM, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_draft_limit(factory, tenant: str) -> str:  # noqa: ANN001
    """A portfolio + a DRAFT VaR limit (not yet approved). Returns the limit id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        portfolio = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"ACCT-{uuid.uuid4().hex[:6]}",
            name="acct",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        )
        session.flush()
        limit = create_limit(
            session,
            tenant_id=tenant,
            code="var-ceiling",
            name="VaR ceiling",
            target_run_type="VAR",
            metric_type="VAR_PARAMETRIC",
            scope_portfolio_id=str(portfolio.id),
            threshold_value=Decimal("1000000"),
            threshold_unit=THRESHOLD_UNIT_CURRENCY,
            breach_direction=BREACH_ABOVE,
            limit_kind=LIMIT_KIND_HARD,
            actor=_ACTOR,
        )
        session.commit()
        return limit.id
    finally:
        session.close()


def _seed_limit(factory, tenant: str) -> str:  # noqa: ANN001
    """A portfolio + an ACTIVE VaR limit (DRAFT then approved by a distinct 2L). Returns the id."""
    limit_id = _seed_draft_limit(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        limit = session.get(LimitDefinition, limit_id)
        approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-PG-1")  # DRAFT -> ACTIVE
        session.commit()
        return limit_id
    finally:
        session.close()


def _seed_run(factory, tenant: str) -> str:  # noqa: ANN001
    """A minimal calculation_run (the breach's FK target). Returns run_id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        run = create_run(session, tenant_id=tenant, run_type=RUN_TYPE_VAR, initiated_by="t")
        session.commit()
        return run.run_id
    finally:
        session.close()


def _breach(tenant: str, limit_id: str, run_id: str) -> Breach:
    return Breach(
        tenant_id=tenant,
        limit_definition_id=limit_id,
        calculation_run_id=run_id,
        detected_at=datetime(2026, 1, 5, tzinfo=UTC),
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        benchmark_id=None,
        observed_value=Decimal("2000000"),
        threshold_value=Decimal("1000000"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        severity=LIMIT_KIND_HARD,
        status=BREACH_STATUS_DETECTED,
    )


def test_cross_tenant_limit_is_rls_invisible(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_limit = _seed_limit(factory, a)
    session = factory()
    try:
        set_tenant_context(session, b)
        assert session.get(LimitDefinition, a_limit) is None
    finally:
        session.close()
        engine.dispose()


def test_breach_append_only_trigger_rejects_update(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    limit_id = _seed_limit(factory, tenant)
    run_id = _seed_run(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = _breach(tenant, limit_id, run_id)
        session.add(row)
        session.flush()  # flush (not commit) — set_tenant_context is txn-local, keeps RLS visible
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE breach SET status = 'CLOSED' WHERE id = :i"), {"i": row.id}
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_limit_definition_ev_head_is_updatable(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    limit_id = _seed_limit(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        result = session.execute(
            text("UPDATE limit_definition SET status = 'SUSPENDED' WHERE id = :i"), {"i": limit_id}
        )
        assert result.rowcount == 1  # no append-only trigger on the EV head
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_breach_insert_is_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_limit = _seed_limit(factory, a)
    a_run = _seed_run(factory, a)
    session = factory()
    try:
        set_tenant_context(session, b)  # acting as B
        with pytest.raises(ProgrammingError) as exc:
            session.add(_breach(a, a_limit, a_run))  # forge a breach under tenant A
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_uq_breach_limit_run_blocks_a_double_detect(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    limit_id = _seed_limit(factory, tenant)
    run_id = _seed_run(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(_breach(tenant, limit_id, run_id))
        session.flush()
        with pytest.raises(IntegrityError) as exc:
            session.add(_breach(tenant, limit_id, run_id))  # same (limit, run) → refused
            session.flush()
        assert "uq_breach_limit_run" in str(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_concurrent_double_approve_is_blocked_by_the_lock(app_url: str) -> None:
    """Verifier B-2: the FOR UPDATE lock + ``populate_existing`` re-reads the from-state so a STALE
    identity-map read cannot double-approve. Session B pre-loads the DRAFT into its identity map
    BEFORE A commits its approval — the interleaving a naive ``locked.status`` read would miss.
    With the fix, B re-reads ACTIVE under the lock and refuses; ``record_version`` bumps ONCE."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    limit_id = _seed_draft_limit(factory, tenant)
    session_a = factory()
    session_b = factory()
    try:
        set_tenant_context(session_b, tenant)
        stale = session_b.get(LimitDefinition, limit_id)  # B's stale DRAFT snapshot
        assert stale.status == "DRAFT"

        set_tenant_context(session_a, tenant)
        a_limit = session_a.get(LimitDefinition, limit_id)
        approve_limit(session_a, a_limit, actor=_APPROVER, approval_ref="RC-A")
        session_a.commit()  # A's DRAFT->ACTIVE is now committed; the row lock is released

        # B still holds a DRAFT object in its identity map; the lock must force a fresh re-read.
        with pytest.raises(LimitError):
            approve_limit(
                session_b, stale, actor=LimitActor(actor_id="risk-mgr-2l-c"), approval_ref="RC-B"
            )
        session_b.rollback()

        set_tenant_context(session_b, tenant)  # re-arm (txn-local, cleared by rollback)
        version = session_b.execute(
            text("SELECT record_version FROM limit_definition WHERE id = :i"), {"i": limit_id}
        ).scalar_one()
        assert (
            version == 2
        )  # create (v1) -> A's approve (v2); B did NOT double-approve (would be v3)
    finally:
        session_a.close()
        session_b.close()
        engine.dispose()


def test_cross_tenant_approve_is_refused(app_url: str) -> None:
    """`_lock_limit`'s tenant filter (P3-5 doctrine: PG FK checks bypass RLS) — approving a limit
    while acting as another tenant must surface 'not found', never activate a foreign limit."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_limit = _seed_draft_limit(factory, a)  # tenant A's DRAFT
    session = factory()
    try:
        set_tenant_context(session, b)  # acting as B
        limit = LimitDefinition(id=a_limit, tenant_id=a)  # a hand-built ref to A's limit
        with pytest.raises(LimitError):
            approve_limit(session, limit, actor=_APPROVER, approval_ref="RC-X")
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_limit_tables() -> None:
    """The standing doctrine invariant: the app does ALL limit/breach reads/writes tenant-scoped
    non-BYPASSRLS, so the ops role gets NOTHING here."""
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _LIM:
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    has = conn.execute(
                        text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                        {"t": table, "p": priv},
                    ).scalar()
                    assert has is False, f"irp_ops unexpectedly has {priv} on {table}"
    finally:
        engine.dispose()
