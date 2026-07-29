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
from sqlalchemy import select, text
from sqlalchemy.pool import NullPool

import irp_shared.demo.ops_stage14 as _stage14
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

    # Teardown: drop this stage's role->permission WIRING rows (the campaign fixture's ratified
    # pattern, and REQUIRED here for the same reason).
    #
    # This stage wires FOUR new operator roles onto the migration-seeded `permission` catalog and
    # adds two rows to the existing auditor role. CI's final `alembic downgrade base` deletes that
    # catalog in 0002's downgrade, and any surviving `role_permission` row referencing it fails with
    #     update or delete on table "permission" violates foreign key constraint
    #     "fk_role_permission_permission_id_permission"
    # — which is exactly how this job failed before the teardown existed. The governed end state
    # (limits, the breach, its remediation, the alert evidence) is deliberately LEFT so the
    # downgrade smoke still exercises the destructive migrations against real rows.
    #
    # Clean up ONLY what THIS run seeded (the MG-1 review fold): on an already-seeded tenant those
    # rows are not ours to delete — stripping them would break the living tenant's wiring for the
    # next act. In CI the schema is fresh, so this run always seeds.
    if result is not None:
        cleanup = factory()
        try:
            persistent_tenant_context(cleanup, DEMO_TENANT_ID)
            # NARROWED at OPS-H1 (H1-7): delete ONLY the wiring THIS stage seeded — the four
            # operator roles' 14 rows by role code, plus the TWO auditor additions by (role,
            # permission) pair. The previous form deleted ALL demo-tenant role_permission rows,
            # which its own comment above forbids: on a shared/local DB it stripped the LIVING
            # tenant's wiring (the campaign's own personas) for the next act. CI never noticed
            # because its schema is fresh — the exact class of defect that stays invisible until
            # someone runs the suite against a database they care about.
            cleanup.execute(
                text(
                    "DELETE FROM role_permission WHERE role_id IN "
                    "(SELECT id FROM role WHERE tenant_id = :tenant "
                    "AND code IN (:r1, :r2, :r3, :r4))"
                ),
                {
                    "tenant": DEMO_TENANT_ID,
                    # IMPORTED from the stage, not hand-mirrored (review LOW: a rename would turn
                    # this teardown into a silent no-op on a shared DB — its exact defect class).
                    "r1": _stage14._LIMIT_2L_ROLE,
                    "r2": _stage14._ANALYST_ROLE,
                    "r3": _stage14._MANAGER_ROLE,
                    "r4": _stage14._SUPERVISOR_ROLE,
                },
            )
            cleanup.execute(
                text(
                    "DELETE FROM role_permission WHERE role_id IN "
                    "(SELECT id FROM role WHERE tenant_id = :tenant AND code = :auditor) "
                    "AND permission_id IN "
                    "(SELECT id FROM permission WHERE code IN (:p1, :p2))"
                ),
                {
                    "tenant": DEMO_TENANT_ID,
                    "auditor": _stage14._AUDITOR_ROLE,
                    "p1": _stage14._AUDITOR_ADDITIONS[0],
                    "p2": _stage14._AUDITOR_ADDITIONS[1],
                },
            )
            cleanup.commit()
        finally:
            cleanup.close()
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
            # RELATIVE since OPS-H1 (H1-4): the stage clock is seed-time-relative, so an absolute
            # instant here would drift a day per day. Any current instant works — the SoD refusal
            # fires pre-insert on WHO acts, not WHEN.
            now=datetime.now(tz=UTC),
        )
    db.rollback()


def test_second_run_refuses(db) -> None:  # noqa: ANN001
    """Refuse-not-skip on this module's own footprint (the campaign shim's ratified shape)."""
    with pytest.raises(DemoOpsAlreadySeededError):
        run_demo_ops_stage14(db)


# --- OPS-H1 (H1-8): the FIRST demo-tenant role/permission census pin ------------------------------


def test_the_demo_tenant_role_census_after_stage_14(db) -> None:  # noqa: ANN001
    """The first role/permission census over the LIVING demo tenant — not a re-pin: the register
    called this a 're-pin' and the verifier found no prior census exists anywhere (the set-equality
    locks pin governed MODEL codes; the only role census is template-level). Stage 14's four
    operator roles were therefore structurally outside every census.

    WHAT IS ACTUALLY ASSERTED (docstring narrowed at the Wave-13 close — it previously claimed
    "SET-equality over the role codes", which nothing below asserts; the decision record's own
    Part 6 words the scope correctly and the guard's self-description now matches it): exact
    wired-permission COUNTS for the five named roles (the four ``ops_*`` operators plus
    ``auditor_3l``), and a no-rogue sweep SCOPED to the ``ops_*`` namespace — stage 14's own. A
    drift in a campaign-owned role outside that namespace is the campaign census's concern, not
    this stage's."""
    from sqlalchemy import text as sql

    roles = {
        row[0]: row[1]
        for row in db.execute(
            sql(
                "SELECT r.code, count(rp.permission_id) FROM role r "
                "LEFT JOIN role_permission rp ON rp.role_id = r.id "
                "WHERE r.tenant_id = :t GROUP BY r.code"
            ),
            {"t": DEMO_TENANT_ID},
        )
    }
    stage_roles = {
        _stage14._LIMIT_2L_ROLE: len(_stage14._LIMIT_2L_PERMS),
        _stage14._ANALYST_ROLE: len(_stage14._ANALYST_PERMS),
        _stage14._MANAGER_ROLE: len(_stage14._MANAGER_PERMS),
        _stage14._SUPERVISOR_ROLE: len(_stage14._SUPERVISOR_PERMS),
    }
    for code, wired in stage_roles.items():
        assert (
            roles.get(code) == wired
        ), f"{code}: expected {wired} wired perms, got {roles.get(code)}"
    # Pinned EXACTLY, to the MEASURED truth: the demo tenant's `auditor_3l` ROLE carries exactly
    # this stage's two read additions and nothing else — the campaign's auditor persona is wired
    # through the entitlement bootstrap's template layer, not through demo-tenant role_permission
    # rows. Two claims died here in one day: the draft's `>= 2` was trivially satisfiable, and a
    # reviewer's "the campaign grants auditor_3l 11 perms" was refuted by running the pin against
    # the live battery (it read the source of a different wiring path). Measured beats cited.
    assert roles.get(_stage14._AUDITOR_ROLE) == len(_stage14._AUDITOR_ADDITIONS)
    # No rogue ops_* role beyond the four this stage declares.
    rogue = {c for c in roles if c.startswith("ops_")} - set(stage_roles)
    assert not rogue, f"unexpected ops roles: {rogue}"
