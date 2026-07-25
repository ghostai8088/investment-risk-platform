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
    BREACH_STATE_RESPONDED,
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
    escalate_overdue_breach,
    respond_breach,
    review_breach,
)
from irp_shared.limit.models import Breach, BreachAction
from irp_shared.limit.service import create_limit
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.risk.events import RUN_TYPE_VAR

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TABLES = ("limit_definition", "breach", "breach_action", "breach_notification")
_DEPS = ("portfolio", "benchmark", "calculation_run")
_RAILS = (
    "data_source",
    "lineage_edge",
    "app_user",
    "schedule",
    "scheduled_run",
    "role",
    "permission",
    "role_permission",
    "user_role",
)
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
    """A portfolio + limit + run + a persisted breach (real FKs; the breach is inserted directly, so
    the limit's DRAFT/ACTIVE status is irrelevant here). Returns the breach id."""
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
            code=f"var-ceiling-{uuid.uuid4().hex[:6]}",  # unique per breach (multi-breach tests)
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


def _mk_assignee(session, tenant: str) -> str:  # noqa: ANN001
    """A real ACTIVE app_user to assign to (API-2b D8: assigned_to is resolved in the service)."""
    from irp_shared.entitlement.models import AppUser

    user = AppUser(tenant_id=tenant, display_name="assignee")
    session.add(user)
    session.flush()
    return user.id


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
        assign_breach(
            session, breach, assigned_to=_mk_assignee(session, tenant), actor=_MANAGER, now=_T0
        )
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
        action = assign_breach(
            session, breach, assigned_to=_mk_assignee(session, tenant), actor=_MANAGER, now=_T0
        )
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
        assign_breach(
            session, breach, assigned_to=_mk_assignee(session, tenant), actor=_MANAGER, now=_T0
        )
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


# --- API-2b: the P1 commit-topology + true-concurrency regressions (the audit's proof set) ----


def _armed(factory, tenant: str):  # noqa: ANN001, ANN202
    session = factory()
    set_tenant_context(session, tenant)
    return session


def test_engine_runs_read_committed(app_url: str) -> None:
    """D-B3: the re-derive-under-lock design is isolation-dependent — pin READ COMMITTED (no
    engine-level override; under REPEATABLE READ the post-lock re-read would not see the
    concurrent writer's committed actions → duplicate seq → IntegrityError)."""
    engine = make_engine(app_url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        assert session.execute(text("SHOW transaction_isolation")).scalar() == "read committed"
    finally:
        session.close()
        engine.dispose()


def test_restructured_tick_escalates_after_midtick_commit(app_url: str) -> None:
    """THE P1/verifier GUC-re-arm regression: the restructured tick commits phases 1–2, then runs
    phase 3 in per-breach TOP-LEVEL transactions. The RLS GUC is transaction-local — WITHOUT the
    ``persistent_tenant_context`` re-arm, every post-commit transaction would be RLS-unarmed and
    phase 3 would silently escalate NOTHING (the OQ-a fail-open pattern). 0 escalations here IS
    that fail-open."""
    from irp_worker.scheduler import run_operational_tick_for_tenant

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)
    session = _armed(factory, tenant)
    try:
        breach = _get(session, breach_id)
        assign_breach(
            session, breach, assigned_to=_mk_assignee(session, tenant), actor=_MANAGER, now=_T0
        )
        session.commit()  # due = T0 + 1d (HARD)
    finally:
        session.close()
    results = run_operational_tick_for_tenant(
        factory, tenant, code_version="test", now=_T0 + timedelta(days=2)
    )
    assert results["escalated"] == [breach_id]
    check = _armed(factory, tenant)
    try:
        assert current_breach_state(check, breach_id, acting_tenant=tenant) == (
            BREACH_STATE_ESCALATED
        )
    finally:
        check.close()
        engine.dispose()


def _run_loser(factory, tenant: str, breach_id: str, verb, outcomes: list) -> None:  # noqa: ANN001
    """The blocked-in-flight loser: enters ``_lock_breach`` while the winner holds the row lock
    uncommitted; on unblock it re-derives state from the winner's committed rows (READ COMMITTED
    per-statement snapshot) and must refuse CLEANLY."""
    session = _armed(factory, tenant)
    try:
        breach = _get(session, breach_id)
        try:
            verb(session, breach)
            session.commit()
            outcomes.append("won")
        except BreachTransitionError:
            session.rollback()
            outcomes.append("refused")
    except Exception as exc:  # noqa: BLE001 - the test asserts on the outcome list
        outcomes.append(f"error:{type(exc).__name__}")
    finally:
        session.close()


def test_blocked_in_flight_respond_race_refuses_cleanly(app_url: str) -> None:
    """D-B2 (respond): winner holds the lock uncommitted; loser blocks INSIDE ``_lock_breach``;
    winner commits; loser re-derives RESPONDED → clean refusal; exactly ONE response row with
    contiguous seq. (The old sequential-commit test proved only that the lock exists.)"""
    import threading
    import time as _time

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)
    setup = _armed(factory, tenant)
    try:
        breach = _get(setup, breach_id)
        assign_breach(
            setup, breach, assigned_to=_mk_assignee(setup, tenant), actor=_MANAGER, now=_T0
        )
        setup.commit()
    finally:
        setup.close()

    winner = _armed(factory, tenant)
    outcomes: list[str] = []
    try:
        wb = _get(winner, breach_id)
        respond_breach(winner, wb, narrative="winner", actor=_ANALYST, now=_T0)  # lock HELD
        loser = threading.Thread(
            target=_run_loser,
            args=(
                factory,
                tenant,
                breach_id,
                lambda s, b: respond_breach(s, b, narrative="retry", actor=_ANALYST, now=_T0),
                outcomes,
            ),
        )
        loser.start()
        _time.sleep(0.8)  # the loser is now blocked on the FOR UPDATE row lock
        winner.commit()
        loser.join(timeout=15)
        assert not loser.is_alive()
    finally:
        winner.close()
    assert outcomes == ["refused"]
    check = _armed(factory, tenant)
    try:
        rows = list(
            check.execute(
                select(BreachAction.seq, BreachAction.action_type)
                .where(BreachAction.breach_id == breach_id)
                .order_by(BreachAction.seq)
            )
        )
        assert [r.seq for r in rows] == [1, 2]  # ASSIGN, ONE response — contiguous, no orphan
        assert [r.action_type for r in rows].count("1L_RESPONSE") == 1
    finally:
        check.close()
        engine.dispose()


def test_blocked_in_flight_close_race_refuses_cleanly(app_url: str) -> None:
    """D-B2 (close): double-submitted close — the loser unblocks into CLOSED and refuses."""
    import threading
    import time as _time

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)
    setup = _armed(factory, tenant)
    try:
        breach = _get(setup, breach_id)
        assign_breach(
            setup, breach, assigned_to=_mk_assignee(setup, tenant), actor=_MANAGER, now=_T0
        )
        respond_breach(setup, breach, narrative="fix", actor=_ANALYST, now=_T0)
        review_breach(setup, breach, outcome=BREACH_REVIEW_ACCEPT, actor=_MANAGER, now=_T0)
        setup.commit()  # REVIEWED
    finally:
        setup.close()

    winner = _armed(factory, tenant)
    outcomes: list[str] = []
    try:
        wb = _get(winner, breach_id)
        close_breach(winner, wb, evidence_ref="ev://1", actor=_MANAGER, now=_T0)  # lock HELD
        loser = threading.Thread(
            target=_run_loser,
            args=(
                factory,
                tenant,
                breach_id,
                lambda s, b: close_breach(s, b, evidence_ref="ev://2", actor=_MANAGER, now=_T0),
                outcomes,
            ),
        )
        loser.start()
        _time.sleep(0.8)
        winner.commit()
        loser.join(timeout=15)
        assert not loser.is_alive()
    finally:
        winner.close()
    assert outcomes == ["refused"]
    check = _armed(factory, tenant)
    try:
        assert current_breach_state(check, breach_id, acting_tenant=tenant) == BREACH_STATE_CLOSED
        closes = check.execute(
            select(BreachAction).where(
                BreachAction.breach_id == breach_id, BreachAction.action_type == "CLOSE"
            )
        ).scalars()
        assert len(list(closes)) == 1
    finally:
        check.close()
        engine.dispose()


def test_respond_escalate_order_dependence_pinned(app_url: str) -> None:
    """B-F6 characterized: the respond×escalate race is order-dependent in its terminal DISPLAY
    state — both orders are legal and serialize correctly; the FE brief states the nondeterminism.
    human-first → final ESCALATED (a timely-responded breach still escalates: an unreviewed
    response does not stop the clock — MG-2-ratified); tick-first → final RESPONDED."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    late = _T0 + timedelta(days=2)

    # human-first
    tenant_a = str(uuid.uuid4())
    breach_a = _seed_breach(factory, tenant_a)
    sa = _armed(factory, tenant_a)
    try:
        ba = _get(sa, breach_a)
        assign_breach(sa, ba, assigned_to=_mk_assignee(sa, tenant_a), actor=_MANAGER, now=_T0)
        respond_breach(sa, ba, narrative="late but filed", actor=_ANALYST, now=late)
        assert escalate_overdue_breach(sa, ba, late) is not None  # RESPONDED is escalatable
        sa.commit()
        set_tenant_context(sa, tenant_a)  # the GUC is transaction-local — re-arm post-commit
        assert current_breach_state(sa, breach_a, acting_tenant=tenant_a) == (
            BREACH_STATE_ESCALATED
        )
    finally:
        sa.close()

    # tick-first
    tenant_b = str(uuid.uuid4())
    breach_b = _seed_breach(factory, tenant_b)
    sb = _armed(factory, tenant_b)
    try:
        bb = _get(sb, breach_b)
        assign_breach(sb, bb, assigned_to=_mk_assignee(sb, tenant_b), actor=_MANAGER, now=_T0)
        assert escalate_overdue_breach(sb, bb, late) is not None
        respond_breach(sb, bb, narrative="responding to the alarm", actor=_ANALYST, now=late)
        sb.commit()
        set_tenant_context(sb, tenant_b)  # re-arm (transaction-local GUC)
        assert current_breach_state(sb, breach_b, acting_tenant=tenant_b) == (
            BREACH_STATE_RESPONDED
        )
    finally:
        sb.close()
        engine.dispose()


def test_tick_and_http_verb_complete_without_deadlock(app_url: str) -> None:
    """THE B-F1 regression, CONSTRUCTED to actually cycle on the pre-P1 topology (4-finder MED-1:
    the single-overdue-breach form could not deadlock even unfixed — the tick never held the
    advisory before its ONE row lock).

    The real inversion needs the tick holding the advisory lock BEFORE it takes a second breach's
    row lock: seed TWO overdue breaches (B1, B2 by id order); a human transaction holds B2's ROW
    lock and then wants the tenant audit ADVISORY lock (exactly a verb's row→advisory order). The
    tick escalates B1 (row→advisory) then wants B2's row.
      - PRE-P1 (single tick txn): tick holds advisory across both → wants row(B2) held by human;
        human wants advisory held by tick → 40P01.
      - POST-P1 (per-breach txns): tick commits B1's escalation (releasing advisory) before B2 →
        human's advisory wait clears → both complete, no error.
    """
    import threading

    from irp_shared.audit.service import _advisory_lock_key
    from irp_worker.scheduler import run_operational_tick_for_tenant

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    b1, b2 = sorted([_seed_breach(factory, tenant), _seed_breach(factory, tenant)])
    setup = _armed(factory, tenant)
    try:
        for bid in (b1, b2):
            assign_breach(
                setup,
                _get(setup, bid),
                assigned_to=_mk_assignee(setup, tenant),
                actor=_MANAGER,
                now=_T0,
            )
        setup.commit()  # both overdue at T0+2d
    finally:
        setup.close()

    tick_errors: list[str] = []
    human_errors: list[str] = []

    def _tick() -> None:
        try:
            run_operational_tick_for_tenant(
                factory, tenant, code_version="test", now=_T0 + timedelta(days=2)
            )
        except Exception as exc:  # noqa: BLE001 - asserted via the list
            tick_errors.append(f"{type(exc).__name__}: {exc}")

    # The human transaction: hold B2's row lock, pause so the tick can grab the advisory while
    # escalating B1, THEN want the advisory (the verb's row→advisory order).
    human = _armed(factory, tenant)
    try:
        human.execute(
            select(Breach).where(Breach.id == b2).with_for_update()
        ).scalar_one()  # row(B2) HELD
        t = threading.Thread(target=_tick)
        t.start()
        import time as _time

        _time.sleep(1.0)  # let the tick escalate B1 (acquiring the advisory) and reach B2
        try:
            human.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _advisory_lock_key(tenant)}
            )
            human.commit()  # releases row(B2) → the tick's B2 escalation proceeds
        except Exception as exc:  # noqa: BLE001
            human.rollback()
            human_errors.append(f"{type(exc).__name__}: {exc}")
        t.join(timeout=30)
        assert not t.is_alive()
        assert tick_errors == [], tick_errors  # POST-P1: no 40P01 on the tick
        assert human_errors == [], human_errors  # nor on the human
    finally:
        human.close()
    check = _armed(factory, tenant)
    try:
        for bid in (b1, b2):
            assert current_breach_state(check, bid, acting_tenant=tenant) == BREACH_STATE_ESCALATED
    finally:
        check.close()
        engine.dispose()


def test_case_variance_self_review_refused_through_http_on_pg(app_url: str) -> None:
    """THE twice-carried API-2 → API-2b demand (§5): the PG-tier case-variance defeat replayed on
    the breach 1L→review path THROUGH HTTP. On PG the entitlement gate's uuid cast is
    case-INsensitive, so a responder presenting the UPPERCASE form of their app_user.id passes
    ``require_permission`` — only the person-level SoD (over the CANONICALIZED actor id) stops them
    reviewing their own response. Proven end-to-end against real RLS, the exact vector the SSO-1 /
    D1 lesson targets (SQLite's CHAR-GUID compare is case-sensitive, so this can only be shown on
    PG)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from irp_backend.api.breaches import router as breaches_router
    from irp_backend.config import settings
    from irp_backend.deps import get_db
    from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole

    # This suite lives outside apps/backend/tests, so the dev-header autouse fixture (conftest) does
    # not apply — pin the shim here (app_env=local permits it) so X-User-Id resolves the principal.
    _prev_auth = settings.auth_mode
    settings.auth_mode = "dev_header"

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach(factory, tenant)

    # a dual-hat human (breach.respond + breach.review) + a distinct reviewer, provisioned on PG
    prov = _armed(factory, tenant)
    try:
        dual = AppUser(tenant_id=tenant, display_name="Dual")
        reviewer = AppUser(tenant_id=tenant, display_name="Rev")
        prov.add_all([dual, reviewer])
        prov.flush()
        role = Role(tenant_id=tenant, code=f"r-{uuid.uuid4().hex[:6]}", name="R")
        prov.add(role)
        prov.flush()
        for code in ("breach.respond", "breach.review", "breach.view"):
            perm = prov.execute(
                select(Permission).where(Permission.code == code)
            ).scalar_one_or_none() or Permission(code=code, description="d")
            prov.add(perm)
            prov.flush()
            prov.add(RolePermission(role_id=role.id, permission_id=perm.id))
        prov.add(UserRole(tenant_id=tenant, user_id=dual.id, role_id=role.id))
        prov.add(UserRole(tenant_id=tenant, user_id=reviewer.id, role_id=role.id))
        prov.commit()
        dual_id, reviewer_id = dual.id, reviewer.id
    finally:
        prov.close()

    session = _armed(factory, tenant)

    def _override_db():  # noqa: ANN202
        try:
            set_tenant_context(session, tenant)
            yield session
        finally:
            pass

    app = FastAPI()
    app.include_router(breaches_router)
    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    def hdr(uid: str) -> dict[str, str]:
        return {"X-User-Id": uid, "X-Tenant-Id": tenant}

    try:
        assert (
            client.post(
                f"/breaches/{breach_id}/assign",
                json={"assigned_to": dual_id},
                headers=hdr(reviewer_id),
            ).status_code
            == 200
        )
        # the dual-hat responds under the LOWERCASE (canonical) form
        assert (
            client.post(
                f"/breaches/{breach_id}/respond",
                json={"narrative": "self"},
                headers=hdr(dual_id.lower()),
            ).status_code
            == 200
        )
        # …then tries to review under the UPPERCASE form: the PG uuid cast lets it PAST the gate,
        # but the canonicalized SoD recognizes the same maker → 409 (NOT 403, NOT a silent pass).
        r = client.post(
            f"/breaches/{breach_id}/review",
            json={"outcome": "ACCEPT"},
            headers=hdr(dual_id.upper()),
        )
        assert r.status_code == 409, r.text
    finally:
        settings.auth_mode = _prev_auth
        session.close()
        engine.dispose()
