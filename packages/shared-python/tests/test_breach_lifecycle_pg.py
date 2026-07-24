"""PostgreSQL RLS + APPEND-ONLY + escalation-uniqueness + OPS-NO-GRANT tests for MG-2 breach_action.

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
(NOSUPERUSER NOBYPASSRLS). Proves: a cross-tenant breach lock is RLS-refused (``_lock_breach`` sees
nothing → BreachTransitionError); the append-only P0001 TRIGGER on ``breach_action`` (irp_app HAS
UPDATE, so the rejection is the trigger, not a privilege); the ``uq_breach_escalation`` partial
unique index rejects a second escalation of the same (breach, epoch_seq) epoch; the FOR UPDATE lock
serializes concurrent transitions; the full lifecycle round-trips under real FKs + RLS; and — the
standing invariant — the BYPASSRLS ``irp_ops``
role has NO grant on ``breach_action``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.calc.service import create_run
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_ACTION_ESCALATE,
    BREACH_LINE_SYSTEM,
    BREACH_REVIEW_ACCEPT,
    BREACH_STATE_ASSIGNED,
    BREACH_STATE_CLOSED,
    BREACH_STATE_DETECTED,
    BREACH_STATE_ESCALATED,
    BREACH_STATUS_DETECTED,
    LIMIT_KIND_HARD,
    THRESHOLD_UNIT_CURRENCY,
    BreachActor,
    LimitActor,
)
from irp_shared.limit.lifecycle import (
    BreachTransitionError,
    _lock_breach,
    assign_breach,
    close_breach,
    current_breach_state,
    respond_breach,
    review_breach,
)
from irp_shared.limit.models import Breach, BreachAction
from irp_shared.limit.service import create_limit
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.risk.events import RUN_TYPE_VAR

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TABLES = ("limit_definition", "breach", "breach_action")
_DEPS = ("portfolio", "benchmark", "calculation_run")
_RAILS = ("data_source", "lineage_edge")
_LIMIT_ACTOR = LimitActor(actor_id="risk-mgr-2l")
_ANALYST = BreachActor(actor_id="analyst-1l")
_MANAGER = BreachActor(actor_id="manager-2l")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


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
        for table in (*_TABLES, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_breach(factory, tenant: str) -> str:  # noqa: ANN001
    """A portfolio + ACTIVE limit + run + a persisted breach (real FKs). Returns the breach id."""
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
            actor=_LIMIT_ACTOR,
        )
        run = create_run(session, tenant_id=tenant, run_type=RUN_TYPE_VAR, initiated_by="t")
        session.flush()
        breach = Breach(
            tenant_id=tenant,
            limit_definition_id=limit.id,
            calculation_run_id=run.run_id,
            detected_at=_T0,
            target_run_type="VAR",
            metric_type="VAR_PARAMETRIC",
            observed_value=Decimal("2000000"),
            threshold_value=Decimal("1000000"),
            threshold_unit=THRESHOLD_UNIT_CURRENCY,
            breach_direction=BREACH_ABOVE,
            limit_kind=LIMIT_KIND_HARD,
            severity=LIMIT_KIND_HARD,
            status=BREACH_STATUS_DETECTED,
        )
        session.add(breach)
        session.commit()
        return breach.id
    finally:
        session.close()


def _get(session, breach_id: str) -> Breach:  # noqa: ANN001
    return session.execute(select(Breach).where(Breach.id == breach_id)).scalar_one()


def test_full_lifecycle_round_trips_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        breach = _get(session, breach_id)
        assert (
            current_breach_state(session, breach_id, acting_tenant=tenant) == BREACH_STATE_DETECTED
        )
        assign_breach(session, breach, assigned_to="analyst-1l", actor=_MANAGER, now=_T0)
        respond_breach(session, breach, narrative="hedged", actor=_ANALYST, now=_T0)
        review_breach(session, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
        close_breach(session, breach, evidence_ref="tkt://1", actor=_MANAGER, now=_T0)
        session.commit()
        set_tenant_context(session, tenant)  # commit cleared the txn-local RLS GUC — re-arm to read
        assert current_breach_state(session, breach_id, acting_tenant=tenant) == BREACH_STATE_CLOSED
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_lock_is_refused(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    breach_id = _seed_breach(factory, a)
    session = factory()
    try:
        # Act under tenant B; a TRANSIENT stub carries A's (id, tenant_id). The tenant-filtered lock
        # under B's RLS finds nothing → refused. (A transient stub, not the persisted A-breach: the
        # A-breach is append-only, so touching it under B would flush-fail on the trigger, not RLS.)
        set_tenant_context(session, b)
        stub = Breach(id=breach_id, tenant_id=a, limit_kind=LIMIT_KIND_HARD)
        with pytest.raises(BreachTransitionError):
            assign_breach(session, stub, assigned_to="x", actor=_MANAGER, now=_T0)
    finally:
        session.close()
        engine.dispose()


def test_breach_action_append_only_trigger_rejects_update(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        breach = _get(session, breach_id)
        action = assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
        session.commit()  # PERSIST the action (a rollback would discard it, dodging the trigger)
        action_id = action.id
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE breach_action SET to_state = 'CLOSED' WHERE id = :i"),
                {"i": action_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as exc2:
            session.execute(text("DELETE FROM breach_action WHERE id = :i"), {"i": action_id})
        assert _is_append_only_violation(exc2.value)
    finally:
        session.close()
        engine.dispose()


def test_escalation_unique_constraint_rejects_same_epoch(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        breach = _get(session, breach_id)
        assign_breach(session, breach, assigned_to="a", actor=_MANAGER, now=_T0)
        session.flush()
        due = _T0 + timedelta(days=1)

        def _escalate_row(seq: int) -> BreachAction:
            return BreachAction(
                tenant_id=tenant,
                breach_id=breach_id,
                seq=seq,
                action_type=BREACH_ACTION_ESCALATE,
                from_state=BREACH_STATE_ASSIGNED,
                to_state=BREACH_STATE_ESCALATED,
                actor_id="breach-deadline:x",
                actor_line=BREACH_LINE_SYSTEM,
                response_due=due,
                epoch_seq=1,  # both escalate the SAME governing epoch → collision
                occurred_at=due + timedelta(days=1),
            )

        session.add(_escalate_row(2))
        session.flush()
        session.add(_escalate_row(3))  # same (breach_id, epoch_seq) epoch
        with pytest.raises(IntegrityError):
            session.flush()
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_breach_action(app_url: str) -> None:
    """The standing doctrine invariant: the BYPASSRLS irp_ops role has NO grant on breach_action."""
    engine = make_engine(URL, poolclass=NullPool)  # superuser to read the catalog
    try:
        with engine.begin() as conn:
            has_ops = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'irp_ops'")).first()
            if not has_ops:
                pytest.skip("irp_ops role not provisioned in this database")
            granted = conn.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'irp_ops' AND table_name = 'breach_action'"
                )
            ).all()
        assert granted == [], f"irp_ops must have NO grant on breach_action, found {granted}"
    finally:
        engine.dispose()


def test_for_update_lock_serializes_concurrent_transitions(app_url: str) -> None:
    """VERIFIER-F3-MED2: prove the ``_lock_breach`` FOR UPDATE row lock is REAL — a second
    connection cannot acquire it while the first holds it (FOR UPDATE NOWAIT → 55P03). A regression
    dropping ``.with_for_update()`` would make this pass silently, so it guards linearizability."""
    engine1 = make_engine(app_url, poolclass=NullPool)
    engine2 = make_engine(app_url, poolclass=NullPool)
    factory1 = make_session_factory(engine1)
    factory2 = make_session_factory(engine2)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory1, tenant)
    s1 = factory1()
    s2 = factory2()
    try:
        set_tenant_context(s1, tenant)
        _lock_breach(s1, breach_id, tenant)  # s1 holds the FOR UPDATE lock (not committed)
        set_tenant_context(s2, tenant)
        with pytest.raises(OperationalError):  # 55P03 lock_not_available — s1 holds it
            s2.execute(
                text("SELECT id FROM breach WHERE id = :i FOR UPDATE NOWAIT"), {"i": breach_id}
            )
        s2.rollback()
        s1.rollback()  # release the lock; s2 can now acquire it
        set_tenant_context(s2, tenant)
        got = s2.execute(
            text("SELECT id FROM breach WHERE id = :i FOR UPDATE NOWAIT"), {"i": breach_id}
        ).scalar_one()
        assert str(got) == breach_id  # lock released → s2 acquires it
    finally:
        s1.close()
        s2.close()
        engine1.dispose()
        engine2.dispose()
