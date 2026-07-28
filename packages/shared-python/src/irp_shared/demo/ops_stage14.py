"""The OPS-1 demo OPERATIONS extension (Wave-12 slice 4) — the data the operations UI opens onto.

EXTENDS the living demo tenant the MG-1 campaign seeded; `campaign.py` stays byte-untouched (its
refuse-not-skip + set-equality locks are ratified integrity checks). Wave 11 and 12 built the whole
limit → breach → remediation → alert chain, but **nothing in the demo ever exercised it**: the
campaign seeds no limit, no breach, no schedule. Pointed at the demo tenant, the operations UI would
render four empty tables and the slice's stated purpose — the first VISIBLE demo of the governed
engine — would be unmet. This module seeds the honest end state instead.

**What it seeds, and why each part is load-bearing (OPS-1 verifier fold H5):**

1. **The two missing READ grants.** The campaign's `auditor_3l` persona — the ratified principal a
   non-developer walks the demo AS — holds 11 `*.view` codes but NOT `limit.view`/`breach.view`
   (it predates LIM-1). Without them a stakeholder gets **403 on every operations screen**. Granted
   here additively onto the existing role, so the campaign is not edited.
2. **Principals shaped so the SoD controls are REACHABLE, not merely present.** MG-3 refuses an
   approver in the limit's maker SET `{created_by, updated_by}`; MG-2 refuses a reviewer who was a
   prior 1L responder. Getting the ROLE shapes wrong makes both undemonstrable: if the maker lacks
   `limit.approve`, self-approval is stopped by the permission guard (403) and the person-level gate
   never fires. So the limit maker and checker SHARE one 2L role (the ratified MG-3 shape), and a
   dual-hat supervisor files the 1L response so their own review is a real 409. See the role
   constants below.
3. **Approval before evaluation.** A limit is born DRAFT and `select_active_limits` filters
   `status == ACTIVE`, so a seeded-but-unapproved limit is evaluated NEVER and can never breach.
   The extension therefore approves (as the checker) before evaluating — otherwise the tables are
   still empty and the maker-checker gate is invisible.
4. **A real breach, produced by evaluation — never hand-minted.** The breaching limit's threshold is
   derived from the demo's actual latest VaR so the breach arithmetic is true, and it is created by
   `evaluate_limit` (the same code path the tick runs), not by inserting a `Breach` row. A
   hand-minted breach would demo a fiction.
5. **An in-appetite limit and a DRAFT awaiting approval**, so the queue shows the three states an
   operator actually triages between: breached, healthy, and pending sign-off.
6. **The alert evidence.** The NOTIF-1 consumer is driven over the `BREACH.DETECT` events just
   emitted, producing the `breach_notification` rows that answer "prove the risk officer was told".

Idempotency is REFUSE-NOT-SKIP on this module's OWN footprint (a demo tenant already holding the
OPS-1 limit codes refuses); a tenant without the base campaign refuses. The caller owns the ONE
commit, so a mid-chain failure rolls back whole and the tenant stays clean and re-runnable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.queries import list_events_since_sequence
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.limit.events import (
    BREACH_ABOVE,
    LIMIT_KIND_HARD,
    LIMIT_KIND_SOFT,
    THRESHOLD_UNIT_CURRENCY,
    BreachActor,
    LimitActor,
)
from irp_shared.limit.lifecycle import assign_breach, respond_breach
from irp_shared.limit.models import LimitDefinition
from irp_shared.limit.service import approve_limit, create_limit, evaluate_limit
from irp_shared.notification.events import NOTIFY_ALARM_EVENT_TYPES
from irp_shared.notification.service import default_sink, notify_for_event
from irp_shared.portfolio.models import Portfolio
from irp_shared.risk.var_service import latest_var_for_portfolio

#: The demo book the campaign builds the flagship VaR over (the same code the FE walk
#: displays as DEMO_PORTFOLIO_CODE).
_PORTFOLIO_CODE = "DEMO-GLOBAL"

#: This extension's OWN footprint — the refuse-not-skip probe.
_BREACHED_CODE = "OPS-VAR-CEILING"
_HEALTHY_CODE = "OPS-VAR-HEADROOM"
_DRAFT_CODE = "OPS-VAR-PROPOSED"

#: The demo operators. The role SHAPES here are not a demo convenience — they mirror the ratified
#: entitlement doctrine exactly, because getting them wrong makes the controls undemonstrable:
#:
#: - **Limits: maker and checker share ONE role.** `bootstrap.py` ratifies (MG-3, OQ-MG-3-2=A) that
#:   `limit.approve` goes to the SAME `risk_manager_2l` as `limit.manage` *"because the gate is
#:   PERSON-level, not role-level … the runtime approver != created_by/updated_by refusal is the
#:   WHOLE gate"*. Splitting them into two roles (as this module first did) means the maker lacks
#:   `limit.approve`, so self-approval is stopped by the PERMISSION guard with a 403 and the
#:   maker-checker gate never fires its 409 — the control would look enforced while being untested.
#:   Two users share `_LIMIT_2L_ROLE` so the real SoD refusal is reachable.
#: - **Breaches: respond and review are NEVER co-granted** (the same doctrine: "a cross-line 1L/2L
#:   partition"). That role partition is the first line, and an analyst attempting a review is
#:   correctly a 403. The PERSON-level backstop (reviewer ∉ prior responders) only bites for a
#:   principal holding both, so the demo also seeds ONE dual-hat supervisor — the platform's own
#:   test suite models exactly this as "the SoD backstop target" — and has THEM file the 1L
#:   response, so their own review is the 409 a demo viewer can actually produce.
_LIMIT_2L_ROLE = "ops_limit_2l"
_ANALYST_ROLE = "ops_breach_analyst_1l"
_MANAGER_ROLE = "ops_breach_manager_2l"
_SUPERVISOR_ROLE = "ops_breach_supervisor"

#: Maker AND checker verbs — one role, two people (the ratified MG-3 shape).
_LIMIT_2L_PERMS = ("limit.manage", "limit.approve", "limit.view", "breach.view")
_ANALYST_PERMS = ("breach.respond", "breach.view", "limit.view")
_MANAGER_PERMS = ("breach.review", "breach.view", "limit.view")
#: The dual-hat principal the person-level backstop exists for (never a normal operating role).
_SUPERVISOR_PERMS = ("breach.respond", "breach.review", "breach.view", "limit.view")

#: The read codes the campaign's auditor persona is missing (it predates LIM-1).
_AUDITOR_ADDITIONS = ("limit.view", "breach.view")
_AUDITOR_ROLE = "auditor_3l"


def _seed_now() -> datetime:
    """The stage clock — SEED-TIME-RELATIVE since OPS-H1 (H1-4), BACKDATED two days.

    The clock was frozen at 2026-07-25 09:00 UTC, which made the seeded overdue breach permanently
    a-year-stale: the first real tick against the demo tenant would have escalated + notified on it
    INSTANTLY, mutating the curated walk into nonsense — the reason the OQ-W12C-3d interim rule
    (`DEMO_TENANT_ID` never enters `IRP_TENANT_IDS`) existed.

    Now every seeded instant is an offset from seed time, truncated to the hour (stable-looking
    demo timestamps), and **backdated by two days so the curated walk is PRESERVED exactly**: the
    assign lands at seed−2d, its HARD-SLA deadline (+1d) at seed−1d, so the breach reads OVERDUE at
    seed just as it always did.

    **What this buys, stated honestly (the verifier caught the draft over-claiming):** regeneration
    removes the ABSURDITY, not the mutation. An overdue breach under a running tick escalates,
    because that is what the platform is FOR — enrolling the demo tenant in `IRP_TENANT_IDS` runs
    its lifecycle as governed, correct behavior, and an operator who wants the pristine walk back
    re-seeds. The prohibition is retired and replaced by that documented consequence.

    Demo timestamps are therefore no longer byte-identical across seed days; the PG suite asserts
    RELATIVE facts only.
    """
    now = datetime.now(tz=UTC).replace(minute=0, second=0, microsecond=0)
    return now - timedelta(days=2)


class DemoOpsError(RuntimeError):
    """An operations-extension step did not produce the required state (fail-loud)."""


class DemoOpsPrereqError(DemoOpsError):
    """The demo tenant is missing the base campaign state this extension extends."""


class DemoOpsAlreadySeededError(RuntimeError):
    """The operations extension already ran for the demo tenant (refuse-not-skip)."""


@dataclass(frozen=True)
class OpsStage14Summary:
    """What the extension landed — asserted by the PG suite, not trusted from this object."""

    breached_limit_id: str
    healthy_limit_id: str
    draft_limit_id: str
    breach_id: str
    notifications: int
    analyst_id: str
    manager_id: str
    supervisor_id: str
    maker_id: str
    checker_id: str


def _permission(session: Session, code: str) -> Permission:
    perm = session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if perm is None:
        # The catalog is migration-seeded; a missing code means the wrong schema, not a demo gap.
        raise DemoOpsPrereqError(f"permission {code!r} is not in the catalog — check the migration")
    return perm


def _make_role(session: Session, role_code: str, perms: tuple[str, ...]) -> Role:
    """A demo role carrying exactly ``perms``. Idempotent within a run so several people can share
    ONE role — required for the limit maker/checker pair, whose gate is person-level."""
    role = session.execute(
        select(Role).where(Role.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).scalar_one_or_none()
    if role is not None:
        return role
    role = Role(tenant_id=DEMO_TENANT_ID, code=role_code, name=role_code)
    session.add(role)
    session.flush()
    for code in perms:
        session.add(RolePermission(role_id=role.id, permission_id=_permission(session, code).id))
    session.flush()
    return role


def _make_operator(session: Session, role_code: str, name: str, perms: tuple[str, ...]) -> str:
    """One demo operator granted ``role_code`` (created on first use, reused thereafter)."""
    user = AppUser(tenant_id=DEMO_TENANT_ID, display_name=name)
    session.add(user)
    session.flush()
    role = _make_role(session, role_code, perms)
    session.add(UserRole(tenant_id=DEMO_TENANT_ID, user_id=user.id, role_id=role.id))
    session.flush()
    return str(user.id)


def _grant_auditor_reads(session: Session) -> int:
    """Add `limit.view` + `breach.view` to the EXISTING auditor role (additive; the campaign is not
    edited). Without this the demo's own viewer persona is 403 on every operations screen."""
    role = session.execute(
        select(Role).where(Role.tenant_id == DEMO_TENANT_ID, Role.code == _AUDITOR_ROLE)
    ).scalar_one_or_none()
    if role is None:
        raise DemoOpsPrereqError(
            f"the demo tenant has no {_AUDITOR_ROLE!r} role — run the MG-1 campaign first"
        )
    added = 0
    for code in _AUDITOR_ADDITIONS:
        perm = _permission(session, code)
        existing = session.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id, RolePermission.permission_id == perm.id
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(RolePermission(role_id=role.id, permission_id=perm.id))
            added += 1
    session.flush()
    return added


def _demo_portfolio_id(session: Session) -> str:
    row = session.execute(
        select(Portfolio.id).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _PORTFOLIO_CODE
        )
    ).first()
    if row is None:
        raise DemoOpsPrereqError(
            f"the demo tenant has no {_PORTFOLIO_CODE!r} portfolio — run the MG-1 campaign first"
        )
    return str(row[0])


def _latest_var(session: Session, portfolio_id: str) -> Decimal:
    """The demo's actual latest parametric VaR — the thresholds are derived FROM it so the seeded
    breach arithmetic is true rather than decorative."""
    rows = latest_var_for_portfolio(
        session,
        acting_tenant=DEMO_TENANT_ID,
        portfolio_id=portfolio_id,
        metric_type="VAR_PARAMETRIC",
    )
    if not rows:
        raise DemoOpsPrereqError(
            "the demo tenant has no COMPLETED parametric VaR run — run the MG-1 campaign first"
        )
    return Decimal(str(rows[0].var_value))


def _already_seeded(session: Session) -> bool:
    row = session.execute(
        select(LimitDefinition.id).where(
            LimitDefinition.tenant_id == DEMO_TENANT_ID,
            LimitDefinition.code.in_((_BREACHED_CODE, _HEALTHY_CODE, _DRAFT_CODE)),
        )
    ).first()
    return row is not None


def run_demo_ops_stage14(session: Session) -> OpsStage14Summary:
    """Seed the operations end state. Caller owns the single commit."""
    now = _seed_now()
    if _already_seeded(session):
        raise DemoOpsAlreadySeededError()

    portfolio_id = _demo_portfolio_id(session)
    var_value = _latest_var(session, portfolio_id)

    _grant_auditor_reads(session)
    # Maker and checker SHARE one 2L role (the ratified MG-3 shape) — so the maker genuinely HOLDS
    # limit.approve and self-approval is refused by the person-level gate (409), not by the
    # permission guard (403). That distinction is the whole demonstration.
    maker = _make_operator(session, _LIMIT_2L_ROLE, "Risk Manager — limit maker", _LIMIT_2L_PERMS)
    checker = _make_operator(
        session, _LIMIT_2L_ROLE, "Risk Manager — limit checker", _LIMIT_2L_PERMS
    )
    analyst = _make_operator(session, _ANALYST_ROLE, "Ops Breach Analyst (1L)", _ANALYST_PERMS)
    manager = _make_operator(session, _MANAGER_ROLE, "Ops Breach Manager (2L)", _MANAGER_PERMS)
    supervisor = _make_operator(
        session, _SUPERVISOR_ROLE, "Ops Breach Supervisor (dual-hat)", _SUPERVISOR_PERMS
    )

    maker_actor = LimitActor(actor_id=maker)
    checker_actor = LimitActor(actor_id=checker)

    def _limit(code: str, name: str, threshold: Decimal, kind: str) -> LimitDefinition:
        return create_limit(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            target_run_type="VAR",
            metric_type="VAR_PARAMETRIC",
            scope_portfolio_id=portfolio_id,
            threshold_value=threshold,
            threshold_unit=THRESHOLD_UNIT_CURRENCY,
            breach_direction=BREACH_ABOVE,
            limit_kind=kind,
            actor=maker_actor,
        )

    # A ceiling the book is genuinely through (half the measured VaR) and one it is comfortably
    # inside (double). Both derived from the real number, so the arithmetic on screen is true.
    breached = _limit(_BREACHED_CODE, "VaR ceiling (firm appetite)", var_value / 2, LIMIT_KIND_HARD)
    healthy = _limit(_HEALTHY_CODE, "VaR headroom monitor", var_value * 2, LIMIT_KIND_SOFT)
    # Left DRAFT on purpose: this is the approval queue's content, and it demonstrates that a
    # limit awaiting sign-off constrains nothing.
    draft = _limit(_DRAFT_CODE, "Proposed tighter VaR ceiling", var_value, LIMIT_KIND_HARD)

    # The maker-checker gate: a DIFFERENT person approves. (Approving as `maker` would raise.)
    approve_limit(
        session, breached, actor=checker_actor, approval_ref="minutes://RISK-COMMITTEE-2026-07"
    )
    approve_limit(
        session, healthy, actor=checker_actor, approval_ref="minutes://RISK-COMMITTEE-2026-07"
    )

    # Detection through the REAL evaluation path (what the tick calls) — never a hand-minted row.
    breach = evaluate_limit(session, breached, now)
    if breach is None:
        raise DemoOpsError(
            "the seeded ceiling did not breach — the demo VaR moved; re-derive the threshold"
        )
    healthy_breach = evaluate_limit(session, healthy, now)
    if healthy_breach is not None:
        raise DemoOpsError("the headroom monitor breached — the demo fixture is not as intended")
    session.flush()

    # Advance the breach into the middle of its lifecycle so the UI opens on a live workflow:
    # assigned by the manager (2L), responded by the DUAL-HAT supervisor (1L act).
    #
    # The 2L REVIEW is deliberately LEFT UNDONE — it is the action a demo viewer performs, and the
    # responder's identity is what makes BOTH controls demonstrable:
    #   - as the supervisor (who holds breach.review AND filed this response) → the person-level
    #     backstop refuses with 409 "separation of duties";
    #   - as the manager (who holds breach.review and did NOT respond) → it legitimately succeeds;
    #   - as the analyst (1L only) → the role partition refuses with 403.
    # Had the analyst filed the response, no seeded principal could ever produce the 409 and the
    # person-level control would be invisible in the demo.
    assign_breach(
        session,
        breach,
        assigned_to=supervisor,
        actor=BreachActor(actor_id=manager),
        now=now,
    )
    respond_breach(
        session,
        breach,
        narrative="Reduced the equity overlay and re-ran the exposure chain; awaiting 2L review.",
        actor=BreachActor(actor_id=supervisor),
        now=now,
    )
    session.flush()

    # The alert leg: drive the NOTIF-1 consumer over the alarm events just emitted, producing the
    # durable proof-of-alert rows the breach detail screen shows.
    sink = default_sink()
    events = list_events_since_sequence(
        session,
        acting_tenant=DEMO_TENANT_ID,
        after_sequence_no=0,
        event_types=NOTIFY_ALARM_EVENT_TYPES,
    )
    notifications = 0
    for event in events:
        notifications += len(notify_for_event(session, event, now, sink=sink))
    session.flush()

    return OpsStage14Summary(
        breached_limit_id=str(breached.id),
        healthy_limit_id=str(healthy.id),
        draft_limit_id=str(draft.id),
        breach_id=str(breach.id),
        notifications=notifications,
        analyst_id=analyst,
        manager_id=manager,
        supervisor_id=supervisor,
        maker_id=maker,
        checker_id=checker,
    )
