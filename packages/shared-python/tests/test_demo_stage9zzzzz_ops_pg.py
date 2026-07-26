"""PostgreSQL end-state test for the OPS-1 demo operations extension (Wave-12 slice 4, stage 14).

Gated on ``IRP_TEST_DATABASE_URL``. Runs the extension ONCE (module-scoped) over the living demo
tenant and asserts the state the operations UI actually opens onto.

**The filename is load-bearing** (the standing stage-ordering discipline): local full-PG batteries
collect alphabetically, and the campaign/multifamily suites pin their governed-code sets with
set-equality. A naturally-named ``test_demo_ops_pg.py`` would sort at ``o`` — BEFORE ``stage*`` and
even before ``multifamily`` — and break those pins in a single-invocation run. ``stage9zzzzz``
extends the established one-more-``z`` convention so this stage collates LAST. In CI the step is
inserted after stage 13 and before the downgrade smoke.

This stage mints NO model code and NO governed number, so the 23/38/109 counts are UNCHANGED — it
seeds control-plane rows (limits, a breach, its remediation, alert evidence) plus four operator
principals and two additive read grants.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoOpsAlreadySeededError,
    run_demo_ops_stage14,
)
from irp_shared.entitlement.models import Permission, Role, RolePermission
from irp_shared.entitlement.service import Principal, has_permission
from irp_shared.limit.events import LIMIT_APPROVE_EVENT, BreachActor, LimitActor
from irp_shared.limit.lifecycle import (
    BreachSodError,
    breach_action_timeline,
    current_breach_state,
    list_breaches,
    review_breach,
)
from irp_shared.limit.models import LimitDefinition
from irp_shared.limit.service import LimitSodError, approve_limit, limit_health
from irp_shared.notification.models import BreachNotification

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_BREACHED = "OPS-VAR-CEILING"
_HEALTHY = "OPS-VAR-HEADROOM"
_DRAFT = "OPS-VAR-PROPOSED"


@pytest.fixture(scope="module")
def summary():  # noqa: ANN201
    """Run the extension once over the living demo tenant (tolerating an already-seeded tenant —
    the refusal has its own test) and yield a session factory + the summary."""
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_ops_stage14(session)
            session.commit()
        except DemoOpsAlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(summary):  # noqa: ANN001, ANN201
    factory, _ = summary
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    yield session
    session.close()


def _limit(db, code: str) -> LimitDefinition:  # noqa: ANN001
    return db.execute(
        select(LimitDefinition).where(
            LimitDefinition.tenant_id == DEMO_TENANT_ID, LimitDefinition.code == code
        )
    ).scalar_one()


def test_the_three_limits_exist_in_their_intended_states(db) -> None:  # noqa: ANN001
    # The demo must show all three states an operator triages between, or the screens are not an
    # honest picture: one in force and breached, one in force and healthy, one awaiting sign-off.
    assert _limit(db, _BREACHED).status == "ACTIVE"
    assert _limit(db, _HEALTHY).status == "ACTIVE"
    assert _limit(db, _DRAFT).status == "DRAFT"


def test_the_maker_checker_gate_was_genuinely_exercised(db) -> None:  # noqa: ANN001
    """The approver must not be a maker. If the extension had used one super-user the gate would
    have been vacuous in the demo — which would misrepresent the control as satisfied.

    The approver is asserted from the IMMUTABLE audit row, not the limit: `approve_limit`
    deliberately records `approved_by` + `checked_makers` in the event because the maker columns are
    mutable EV state. That makes the two-person control provable from the ledger alone."""
    breached = _limit(db, _BREACHED)
    assert breached.created_by is not None
    event = db.execute(
        select(AuditEvent).where(
            AuditEvent.tenant_id == DEMO_TENANT_ID,
            AuditEvent.event_type == LIMIT_APPROVE_EVENT,
            AuditEvent.entity_id == breached.id,
        )
    ).scalar_one()
    approved_by = event.after_value["approved_by"]
    checked = set(event.after_value["checked_makers"])
    assert checked, "the SoD must have been checked against a non-empty maker set"
    assert approved_by not in checked
    assert breached.created_by in checked


def test_a_real_breach_exists_and_is_mid_lifecycle(db, summary) -> None:  # noqa: ANN001
    _, result = summary
    rows = list_breaches(db, acting_tenant=DEMO_TENANT_ID, open_only=True)
    codes = {r.limit_code for r in rows}
    assert _BREACHED in codes
    assert _HEALTHY not in codes  # the headroom monitor must NOT have breached

    breach = next(r for r in rows if r.limit_code == _BREACHED)
    # Assigned + 1L-responded, with the 2L review deliberately left for the demo viewer to perform.
    assert breach.state == "RESPONDED"
    assert breach.assigned_to is not None
    assert breach.seq >= 2  # the token the UI sends back as expected_seq


def test_the_breach_arithmetic_is_true_not_decorative(db) -> None:  # noqa: ANN001
    """The seeded threshold is derived from the demo's REAL latest VaR, so observed > threshold is
    an actual arithmetic fact — a hand-minted breach row would demo a fiction."""
    rows = list_breaches(db, acting_tenant=DEMO_TENANT_ID, open_only=True)
    breach = next(r for r in rows if r.limit_code == _BREACHED).breach
    assert breach.observed_value > breach.threshold_value
    assert breach.breach_direction == "ABOVE"
    assert breach.calculation_run_id is not None  # bound to the run it was evaluated against


def test_the_remediation_timeline_shows_two_lines_of_defence(db, summary) -> None:  # noqa: ANN001
    _, result = summary
    rows = list_breaches(db, acting_tenant=DEMO_TENANT_ID, open_only=True)
    breach_id = next(r for r in rows if r.limit_code == _BREACHED).breach.id
    timeline = breach_action_timeline(db, acting_tenant=DEMO_TENANT_ID, breach_id=breach_id)
    kinds = [a.action_type for a in timeline]
    assert kinds == ["ASSIGN", "1L_RESPONSE"]
    assert timeline[0].actor_id != timeline[1].actor_id  # assigner != responder
    assert current_breach_state(db, breach_id, acting_tenant=DEMO_TENANT_ID) == "RESPONDED"


def test_alert_evidence_exists_for_the_breach(db) -> None:  # noqa: ANN001
    """The NOTIF-1 leg: durable proof the risk officer was told."""
    rows = list(
        db.execute(
            select(BreachNotification).where(BreachNotification.tenant_id == DEMO_TENANT_ID)
        ).scalars()
    )
    assert rows, "the operations demo must carry alert evidence"
    assert {r.outcome for r in rows} <= {"SENT", "SUPPRESSED", "FAILED"}
    assert all(r.source_event_type in ("BREACH.DETECT", "BREACH.ESCALATE") for r in rows)


def test_limit_health_covers_only_limits_in_force(db) -> None:  # noqa: ANN001
    """`limit_health` reports on ACTIVE limits only — the DRAFT has no row. The UI must therefore
    render an unmatched limit as NOT IN FORCE rather than defaulting it to healthy (the fail-open
    dishonesty LIM-1 exists to prevent)."""
    health = {h.code: h for h in limit_health(db, acting_tenant=DEMO_TENANT_ID)}
    assert health[_BREACHED].state == "BREACHED"
    assert health[_HEALTHY].state == "IN_APPETITE"
    assert _DRAFT not in health


def test_the_demo_viewer_persona_can_actually_see_the_operations_screens(db) -> None:  # noqa: ANN001
    """The H5 fold: `auditor_3l` is the ratified principal a non-developer walks the demo AS, but
    it predates LIM-1 and held neither read code — so every operations screen returned 403. The
    extension grants them additively."""
    role = db.execute(
        select(Role).where(Role.tenant_id == DEMO_TENANT_ID, Role.code == "auditor_3l")
    ).scalar_one()
    granted = set(
        db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        ).scalars()
    )
    assert "limit.view" in granted
    assert "breach.view" in granted


def test_the_role_partition_holds_for_the_breach_lifecycle(db, summary) -> None:  # noqa: ANN001
    """The FIRST line: breach.respond and breach.review are never co-granted to a normal operating
    role, so an analyst attempting a review is refused by the permission guard (403)."""
    _, result = summary
    if result is None:
        pytest.skip("already-seeded run: the summary's principal ids are not available")
    analyst = Principal(user_id=result.analyst_id, tenant_id=DEMO_TENANT_ID)
    manager = Principal(user_id=result.manager_id, tenant_id=DEMO_TENANT_ID)
    assert has_permission(db, analyst, "breach.respond", DEMO_TENANT_ID)
    assert not has_permission(db, analyst, "breach.review", DEMO_TENANT_ID)
    assert has_permission(db, manager, "breach.review", DEMO_TENANT_ID)
    assert not has_permission(db, manager, "breach.respond", DEMO_TENANT_ID)


def test_the_person_level_sod_refusals_are_actually_REACHABLE(db, summary) -> None:  # noqa: ANN001
    """The review's H-2 fold, and the point of the whole demo.

    A control that can only ever be refused by the PERMISSION guard (403) is never demonstrated —
    the person-level gate would look enforced while being untested. Both 409s must be producible by
    a seeded principal:

      * the limit maker HOLDS `limit.approve` (same 2L role as the checker, the ratified MG-3
        shape), so approving their own draft is refused by SoD, not by entitlement;
      * the dual-hat supervisor HOLDS `breach.review` AND filed the 1L response, so reviewing their
        own response is refused by SoD, not by entitlement.
    """
    _, result = summary
    if result is None:
        pytest.skip("already-seeded run: the summary's principal ids are not available")

    maker = Principal(user_id=result.maker_id, tenant_id=DEMO_TENANT_ID)
    supervisor = Principal(user_id=result.supervisor_id, tenant_id=DEMO_TENANT_ID)
    # Entitlement must NOT be what stops them — otherwise the 409 is unreachable.
    assert has_permission(db, maker, "limit.approve", DEMO_TENANT_ID)
    assert has_permission(db, supervisor, "breach.review", DEMO_TENANT_ID)

    # The maker self-approving the DRAFT → the maker-checker SoD refusal.
    draft = _limit(db, _DRAFT)
    with pytest.raises(LimitSodError):
        approve_limit(
            db, draft, actor=LimitActor(actor_id=result.maker_id), approval_ref="minutes://x"
        )
    db.rollback()

    # The supervisor reviewing their OWN 1L response → the person-level backstop.
    rows = list_breaches(db, acting_tenant=DEMO_TENANT_ID, open_only=True)
    breach = next(r for r in rows if r.limit_code == _BREACHED).breach
    with pytest.raises(BreachSodError):
        review_breach(
            db,
            breach,
            outcome="ACCEPT",
            actor=BreachActor(actor_id=result.supervisor_id),
            now=datetime(2026, 7, 25, 10, 0, tzinfo=UTC),
        )
    db.rollback()


def test_second_run_refuses(db) -> None:  # noqa: ANN001
    """Refuse-not-skip on this module's own footprint (the campaign shim's ratified shape)."""
    with pytest.raises(DemoOpsAlreadySeededError):
        run_demo_ops_stage14(db)
