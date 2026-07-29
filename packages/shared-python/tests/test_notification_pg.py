"""PostgreSQL RLS + APPEND-ONLY + OPS-NO-GRANT + tick-loop tests for NOTIF-1 breach_notification.

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
(NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant notification rows are RLS-hidden; the append-only
P0001 trigger rejects an UPDATE (irp_app HAS UPDATE, so the rejection is the trigger); the full
per-event top-level-txn phase-4 loop (``poll_tenant_notifications``) fires under real RLS with the
``persistent_tenant_context`` re-arm; at-least-once + at-most-once (a re-tick re-derives the
high-water from committed rows and dedups); the ``NOTIFY.DISPATCH`` ledger entry is hash-chained;
and the standing invariant — the BYPASSRLS ``irp_ops`` role has NO grant on ``breach_notification``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context, set_tenant_context
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_DETECT_EVENT,
    BREACH_ESCALATE_EVENT,
    LIMIT_KIND_HARD,
    THRESHOLD_UNIT_CURRENCY,
)
from irp_shared.limit.models import Breach
from irp_shared.notification.events import NOTIFY_DISPATCH_EVENT, NOTIFY_OUTCOME_SENT
from irp_shared.notification.models import BreachNotification

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_GRANTED = (
    "breach_notification",
    "breach",
    "limit_definition",
    "portfolio",
    "calculation_run",
    "data_source",
    "lineage_edge",
    "audit_event",
    "app_user",
    "role",
    "permission",
    "role_permission",
    "user_role",
)
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def app_url(pg_role_permission_guard) -> str:  # noqa: ANN001 - fixture guard, value unused
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
        for table in _GRANTED:
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _mk_reviewer(session, tenant: str) -> str:  # noqa: ANN001
    user = AppUser(tenant_id=tenant, display_name="rev")
    session.add(user)
    session.flush()
    role = Role(tenant_id=tenant, code=f"r-{uuid.uuid4().hex[:6]}", name="R")
    session.add(role)
    session.flush()
    perm = session.execute(
        select(Permission).where(Permission.code == "breach.review")
    ).scalar_one_or_none() or Permission(code="breach.review", description="d")
    session.add(perm)
    session.flush()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    session.add(
        UserRole(
            tenant_id=tenant, user_id=user.id, role_id=role.id, valid_from=_T0 - timedelta(days=1)
        )
    )
    session.flush()
    return user.id


def _seed_breach_and_detect(factory, tenant: str, *, with_reviewer: bool = True) -> str:  # noqa: ANN001
    """A breach + its BREACH.DETECT audit event (+ optionally a reviewer). Returns the breach id."""
    from irp_shared.audit.service import record_event
    from irp_shared.calc.service import create_run
    from irp_shared.limit.events import LimitActor
    from irp_shared.limit.service import create_limit
    from irp_shared.portfolio import PortfolioActor, create_portfolio
    from irp_shared.risk.events import RUN_TYPE_VAR

    session = factory()
    try:
        set_tenant_context(session, tenant)
        if with_reviewer:
            _mk_reviewer(session, tenant)
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
            code=f"var-ceiling-{uuid.uuid4().hex[:6]}",
            name="VaR ceiling",
            target_run_type="VAR",
            metric_type="VAR_PARAMETRIC",
            scope_portfolio_id=str(portfolio.id),
            threshold_value=Decimal("1000000"),
            threshold_unit=THRESHOLD_UNIT_CURRENCY,
            breach_direction=BREACH_ABOVE,
            limit_kind=LIMIT_KIND_HARD,
            actor=LimitActor(actor_id="risk-mgr-2l"),
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
            status="DETECTED",
        )
        session.add(breach)
        session.flush()
        record_event(
            session,
            event_type=BREACH_DETECT_EVENT,
            tenant_id=tenant,
            actor_type="SYSTEM",
            actor_id="limit-eval:x",
            source_module="limit",
            entity_type="breach",
            entity_id=breach.id,
            action="record",
            severity="warning",
            after_value={"limit_definition_id": breach.limit_definition_id},
        )
        session.commit()
        return breach.id
    finally:
        session.close()


def _armed(factory, tenant: str):  # noqa: ANN001, ANN202
    session = factory()
    set_tenant_context(session, tenant)
    return session


def test_phase4_loop_notifies_under_rls(app_url: str) -> None:
    from irp_worker.notifications import poll_tenant_notifications

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach_and_detect(factory, tenant)

    session = factory()
    try:
        # The ARMING context. (Wave-13 close: this comment used to claim "the re-arm (else RLS
        # hides all rows)" — refutable by mutation: this single-event test never crosses a commit,
        # so the after-begin RE-ARM listener never fires here and the test passes with the re-arm
        # removed. The re-arm's real regression pins are `test_break_on_failure_prevents_cursor_
        # leapfrog` (multi-event, crosses per-event commits) and the COMPOSED tick assertion in
        # `test_breach_lifecycle_pg.py::test_restructured_tick_escalates_after_midtick_commit`.)
        detach = persistent_tenant_context(session, tenant)
        try:
            notified = poll_tenant_notifications(session, _T0, acting_tenant=tenant)
        finally:
            detach()
    finally:
        session.close()
    assert len(notified) == 1  # the DETECT event was notified

    check = _armed(factory, tenant)
    try:
        rows = list(
            check.execute(
                select(BreachNotification).where(BreachNotification.breach_id == breach_id)
            ).scalars()
        )
        assert len(rows) == 1 and rows[0].outcome == NOTIFY_OUTCOME_SENT
        # the NOTIFY.DISPATCH ledger entry landed (hash-chained proof-of-alert)
        emits = list(
            check.execute(
                select(AuditEvent).where(AuditEvent.event_type == NOTIFY_DISPATCH_EVENT)
            ).scalars()
        )
        assert len(emits) == 1 and emits[0].entity_id == rows[0].id
    finally:
        check.close()
        engine.dispose()


def test_re_tick_is_idempotent_at_least_once(app_url: str) -> None:
    from irp_worker.notifications import poll_tenant_notifications

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_breach_and_detect(factory, tenant)

    def _tick() -> int:
        session = factory()
        try:
            detach = persistent_tenant_context(session, tenant)
            try:
                return len(poll_tenant_notifications(session, _T0, acting_tenant=tenant))
            finally:
                detach()
        finally:
            session.close()

    assert _tick() == 1  # first tick notifies
    assert _tick() == 0  # second tick: the derived high-water excludes the already-notified event

    check = _armed(factory, tenant)
    try:
        n = check.execute(
            select(BreachNotification).where(BreachNotification.tenant_id == tenant)
        ).scalars()
        assert len(list(n)) == 1  # at-most-once: exactly ONE row, no duplicate
    finally:
        check.close()
        engine.dispose()


def test_cross_tenant_notification_is_rls_hidden(app_url: str) -> None:
    from irp_worker.notifications import poll_tenant_notifications

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_breach_and_detect(factory, tenant_a)

    session = factory()
    try:
        detach = persistent_tenant_context(session, tenant_a)
        try:
            poll_tenant_notifications(session, _T0, acting_tenant=tenant_a)
        finally:
            detach()
    finally:
        session.close()

    # tenant B sees NONE of tenant A's notification rows (FORCE RLS)
    sb = _armed(factory, tenant_b)
    try:
        rows = sb.execute(select(BreachNotification)).scalars().all()
        assert rows == []
    finally:
        sb.close()
        engine.dispose()


def test_breach_notification_is_append_only_at_db(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach_and_detect(factory, tenant, with_reviewer=False)

    session = _armed(factory, tenant)
    try:
        row = BreachNotification(
            tenant_id=tenant,
            source_sequence_no=99,
            source_event_type=BREACH_DETECT_EVENT,
            breach_id=breach_id,
            recipient_id="r",
            recipient_reason="breach.review",
            channel="LOG",
            outcome=NOTIFY_OUTCOME_SENT,
            severity="warning",
            notified_at=_T0,
        )
        session.add(row)
        session.flush()  # assign the PK (the GUID default applies at INSERT, not construction)
        row_id = row.id
        session.commit()
        set_tenant_context(session, tenant)  # commit cleared the txn-local RLS GUC — re-arm
        # the P0001 append-only trigger rejects an UPDATE (irp_app HAS UPDATE — it is the trigger)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE breach_notification SET outcome = 'FAILED' WHERE id = :id"),
                {"id": row_id},
            )
            session.flush()
        assert (
            getattr(exc.value.orig, "sqlstate", None) == "P0001"
            or "append-only" in str(exc.value).lower()
        )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_irp_ops_has_no_grant_on_breach_notification(app_url: str) -> None:
    # the standing invariant (SCH-1/LIM-1/MG-2 posture): the BYPASSRLS ops role NEVER touches the
    # governed proprietary table — no grant exists.
    engine = make_engine(URL, poolclass=NullPool)  # superuser to inspect grants
    try:
        with engine.begin() as conn:
            has_ops = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = 'irp_ops'")
            ).scalar_one_or_none()
            if not has_ops:
                pytest.skip("irp_ops role not provisioned in this environment")
            granted = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.role_table_grants "
                    "WHERE grantee = 'irp_ops' AND table_name = 'breach_notification'"
                )
            ).scalar_one_or_none()
            assert granted is None
    finally:
        engine.dispose()


def test_break_on_failure_prevents_cursor_leapfrog(app_url, monkeypatch) -> None:  # noqa: ANN001
    """THE 4-finder HIGH regression: with the DERIVED MAX(source_sequence_no) cursor, a middle event
    that FAILS must NOT be leapfrogged by a later event's commit. The worker BREAKs on the first
    non-dedup failure (fail-closed), so MAX stays below the gap and the failed event + tail retry
    next tick. Pre-fix (continue-past-failure), E3 committing would advance MAX past the failed E2,
    orphaning it forever — the silent no-notify this slice exists to close."""
    from irp_shared.audit.service import record_event
    from irp_worker import notifications as notif_worker

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    breach_id = _seed_breach_and_detect(factory, tenant)  # E1 = BREACH.DETECT

    setup = _armed(factory, tenant)
    try:
        e2 = record_event(
            setup,
            event_type=BREACH_ESCALATE_EVENT,
            tenant_id=tenant,
            actor_type="SYSTEM",
            actor_id="breach-deadline:x",
            source_module="limit",
            entity_type="breach_action",
            entity_id=str(uuid.uuid4()),
            action="record",
            severity="warning",
            after_value={"breach_id": breach_id},
        )
        e3 = record_event(
            setup,
            event_type=BREACH_ESCALATE_EVENT,
            tenant_id=tenant,
            actor_type="SYSTEM",
            actor_id="breach-deadline:x",
            source_module="limit",
            entity_type="breach_action",
            entity_id=str(uuid.uuid4()),
            action="record",
            severity="warning",
            after_value={"breach_id": breach_id},
        )
        setup.commit()
        e1_seq = e2.sequence_no - 1  # E1 (DETECT) immediately precedes E2 (gap-free monotonic)
        e2_seq, e3_seq = e2.sequence_no, e3.sequence_no
    finally:
        setup.close()

    real = notif_worker.notify_for_event

    def _flaky(sess, event, now, *, sink):  # noqa: ANN001, ANN202
        if event.sequence_no == e2_seq:
            raise RuntimeError("injected mid-event DB failure")
        return real(sess, event, now, sink=sink)

    monkeypatch.setattr(notif_worker, "notify_for_event", _flaky)
    session = factory()
    try:
        detach = persistent_tenant_context(session, tenant)
        try:
            notified = notif_worker.poll_tenant_notifications(session, _T0, acting_tenant=tenant)
        finally:
            detach()
    finally:
        session.close()
    assert len(notified) == 1  # only E1 — the batch STOPPED at the failed E2 (no leapfrog to E3)

    check = _armed(factory, tenant)
    try:
        from irp_shared.notification.service import _current_high_water

        assert (
            _current_high_water(check, tenant) == e1_seq
        )  # MAX did NOT advance past the failed E2
    finally:
        check.close()

    # next tick (no injected failure) reprocesses E2 AND E3 — nothing orphaned
    monkeypatch.setattr(notif_worker, "notify_for_event", real)
    session2 = factory()
    try:
        detach = persistent_tenant_context(session2, tenant)
        try:
            notif_worker.poll_tenant_notifications(session2, _T0, acting_tenant=tenant)
        finally:
            detach()
    finally:
        session2.close()
    check2 = _armed(factory, tenant)
    try:
        from irp_shared.notification.service import _current_high_water

        assert _current_high_water(check2, tenant) == e3_seq  # E2 + E3 now covered
        seqs = {
            r.source_sequence_no
            for r in check2.execute(
                select(BreachNotification).where(BreachNotification.tenant_id == tenant)
            ).scalars()
        }
        assert {e1_seq, e2_seq, e3_seq} <= seqs  # every alarm event has evidence
    finally:
        check2.close()
        engine.dispose()
