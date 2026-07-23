"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY + OPS-NO-GRANT tests for SCH-1 (ENT-061 schedule EV /
ENT-062 scheduled_run IA).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
(NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant schedule invisibility (RLS); the append-only P0001
TRIGGER on ``scheduled_run`` (irp_app HAS UPDATE/DELETE + a POSITIVE control first, so the rejection
is the trigger, NOT a privilege denial) while the EV ``schedule`` head IS updatable; and — the
load-bearing SCH-1 doctrine invariant (OQ-1=B) — the BYPASSRLS ``irp_ops`` role has NO grant on
either scheduling table (parity with ``test_ops_role_has_no_grant_on_model_tables``).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from datetime import date as dt_date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.risk import register_var_model
from irp_shared.scheduling.events import OUTCOME_DISPATCHED, SchedulingActor
from irp_shared.scheduling.models import Schedule, ScheduledRun
from irp_shared.scheduling.service import create_schedule

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_SCH = ("schedule", "scheduled_run")
_DEPS = (
    "portfolio",
    "model",
    "model_version",
    "model_assumption",
    "model_limitation",
    "calculation_run",
)
_RAILS = ("data_source", "lineage_edge")
_ACTOR = SchedulingActor(actor_id="analyst-1")
_ANCHOR = dt_date(2026, 1, 1)


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
        for table in (*_SCH, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_schedule(factory, tenant: str) -> str:  # noqa: ANN001
    """A portfolio + registered VaR model + an ACTIVE schedule. Returns the schedule id."""
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
        var_mv = register_var_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", confidence_level="0.95"
        )
        schedule = create_schedule(
            session,
            tenant_id=tenant,
            code="daily-var",
            name="Daily VaR",
            target_run_type="VAR",
            scope_portfolio_id=str(portfolio.id),
            model_version_id=var_mv.id,
            environment_id="ci",
            interval_days=1,
            anchor_date=_ANCHOR,
            actor=_ACTOR,
        )
        session.commit()
        return schedule.id
    finally:
        session.close()


def test_cross_tenant_schedule_is_rls_invisible(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_sched = _seed_schedule(factory, a)
    session = factory()
    try:
        set_tenant_context(session, b)
        assert session.get(Schedule, a_sched) is None  # tenant B cannot see tenant A's schedule
    finally:
        session.close()
        engine.dispose()


def test_scheduled_run_append_only_trigger_rejects_update(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    sched_id = _seed_schedule(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = ScheduledRun(
            tenant_id=tenant,
            schedule_id=sched_id,
            scheduled_for=datetime(2026, 1, 5, tzinfo=UTC),
            fired_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
            outcome=OUTCOME_DISPATCHED,
        )
        session.add(row)
        session.flush()  # flush (not commit) — set_tenant_context is txn-local, keeps RLS visible
        # POSITIVE control: irp_app HOLDS UPDATE — so a rejection is the TRIGGER, not a privilege.
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE scheduled_run SET outcome = 'FAILED' WHERE id = :i"),
                {"i": row.id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_schedule_ev_head_is_updatable(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    sched_id = _seed_schedule(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        result = session.execute(
            text("UPDATE schedule SET status = 'PAUSED' WHERE id = :i"), {"i": sched_id}
        )
        assert result.rowcount == 1  # no append-only trigger on the EV head
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_schedule_insert_is_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_sched = _seed_schedule(factory, a)
    session = factory()
    try:
        set_tenant_context(session, b)  # acting as B
        # Forge a scheduled_run under tenant A while RLS context is B -> WITH CHECK denies (42501).
        with pytest.raises(ProgrammingError) as exc:
            session.add(
                ScheduledRun(
                    tenant_id=a,
                    schedule_id=a_sched,
                    scheduled_for=datetime(2026, 1, 5, tzinfo=UTC),
                    fired_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
                    outcome=OUTCOME_DISPATCHED,
                )
            )
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_scheduling_tables() -> None:
    """The load-bearing SCH-1 doctrine invariant (OQ-1=B): the app does ALL scheduling reads/writes
    tenant-scoped non-BYPASSRLS, so the ops role gets NOTHING here (Option A was rejected)."""
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _SCH:
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    has = conn.execute(
                        text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                        {"t": table, "p": priv},
                    ).scalar()
                    assert has is False, f"irp_ops unexpectedly has {priv} on {table}"
    finally:
        engine.dispose()
