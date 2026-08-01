"""LIM-2 demo stage 20 — a concentration limit, defined, approved, and BREACHED.

The slice's headline made reachable: CON-1 produced concentration numbers that nothing could
threshold; this stage writes the limits that threshold them and drives a real breach through the
same evaluation path the tick uses.

**Every threshold is DERIVED FROM THE MEASURED NUMBER, never hardcoded** (the ops_stage14
convention): the stage reads what the CON-1 run actually computed, sets the breaching ceiling at
HALF that value, and the healthy one HALFWAY BETWEEN it and 1. So the arithmetic on screen is true,
and the stage cannot silently stop demonstrating anything if the demo book's numbers move — it
refuses instead. (The healthy rule was "double it" until the stage was executed and produced a
0.999999 ceiling no share can exceed; see ``_headroom``.)

**Detection runs through ``evaluate_limit``**, never a hand-minted ``breach`` row. A demo that
inserts the artifact it claims to produce demonstrates nothing (the OPS-1 lesson: a demo that
cannot REACH a control does not demonstrate it).

What this stage demonstrates, in the order a viewer meets it:
1. A named-bucket SECTOR limit ("no more than X% in this industry") — the shape the wave plan
   scoped the slice around, and which CON-1's ``SHARE`` exclusion had made unrepresentable.
2. A named-ISSUER limit — the most common concentration limit anyone writes, and the one whose
   identity the read fence protects.
3. A run-level HHI limit — the wildcard appetite, served by a summary metric because
   ``uq_breach_limit_run`` permits one breach per (limit, run).
4. A DRAFT limit that constrains nothing until a second person approves it (the maker-checker gate).
5. **The issuer read fence**, demonstrated as a REFUSAL rather than described: a viewer holding
   ``limit.view`` but not ``concentration.issuer.view`` does not receive the issuer-named limit
   from either the list or the health surface.
6. **A regulatory-shaped threshold REFUSED** — a NAV-denominated limit cannot be written at all,
   because no NAV denominator is computable on this schema (the CON-1 descope, made visible).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.concentration.models import (
    BUCKET_SENTINELS,
    DENOMINATOR_BASIS_INVESTED_LONG,
    DIMENSION_KIND_ISSUER,
    METRIC_TYPE_SHARE,
    ROW_KIND_DETAIL,
    ROW_KIND_SUMMARY,
)
from irp_shared.concentration.service import latest_concentration
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_BELOW,
    LIMIT_KIND_HARD,
    LIMIT_KIND_SOFT,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.limit.service import (
    HEALTH_BREACHED,
    HEALTH_REFUSED,
    LimitError,
    approve_limit,
    create_limit,
    evaluate_limit,
    limit_health,
    list_limits,
)
from irp_shared.portfolio.models import Portfolio

_BOOK_CODE = "DEMO-CONCENTRATION"
_MAKER_ROLE = "demo-lim2-maker"
_CHECKER_ROLE = "demo-lim2-checker"
#: The viewer that PROVES the fence: limit.view WITHOUT concentration.issuer.view — the shape
#: auditor_3l has, which is why CON-1 minted the two codes separately.
_FENCED_VIEWER_ROLE = "demo-lim2-fenced-viewer"

_MAKER_PERMS = ("limit.manage", "limit.view", "concentration.view", "concentration.issuer.view")
_CHECKER_PERMS = ("limit.approve", "limit.view", "concentration.view", "concentration.issuer.view")
_FENCED_VIEWER_PERMS = ("limit.view", "breach.view", "concentration.view")

_SECTOR_CODE = "DEMO-SECTOR-CEIL"
_ISSUER_CODE = "DEMO-ISSUER-CEIL"
_HHI_CODE = "DEMO-HHI-CEIL"
_DRAFT_CODE = "DEMO-ISSUER-PROPOSED"
_HEALTHY_CODE = "DEMO-ISSUER-HEADROOM"


class DemoLim2Error(Exception):
    """LIM-2 demo-stage refusal."""


class DemoLim2PrereqError(DemoLim2Error):
    """The CON-1 stage has not run, so there are no concentration numbers to threshold."""


class DemoLim2AlreadySeededError(DemoLim2Error):
    """The LIM-2 limits are already seeded (the stage is not idempotent by design)."""


@dataclass(frozen=True)
class Lim2Stage20Summary:
    """What the stage produced — every field ASSERTABLE by its test rather than described here."""

    concentration_run_id: str
    #: The measured values the thresholds were derived FROM (so the test can re-derive them).
    measured_issuer_share: str
    measured_sector_share: str
    measured_hhi: str
    limits_created: int
    limits_approved: int
    breaches_detected: int
    #: The issuer-named limit codes a FENCED viewer must NOT receive.
    fenced_from_viewer: tuple[str, ...]
    #: Codes the fenced viewer legitimately DOES see — the positive control, without which the
    #: line above would be satisfied by a read that returned nothing at all.
    visible_to_viewer: tuple[str, ...]
    regulatory_threshold_refused: str
    #: Limits whose selector names no node of the run's scheme — REFUSED, not silently green.
    unverifiable_selectors_refused: tuple[str, ...] = ()
    #: role_permission rows this stage granted and then DELETED (CON-1's teardown discipline).
    role_permission_rows_torn_down: int = 0


def _permission(session: Any, code: str) -> Permission:  # noqa: ANN401
    perm = session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if perm is None:
        raise DemoLim2PrereqError(f"permission {code!r} is not minted — run the campaign first")
    return perm


def _make_operator(session: Any, role_code: str, name: str, perms: tuple[str, ...]) -> str:  # noqa: ANN401
    """One demo operator with a dedicated role (the ops_stage14 convention)."""
    user = AppUser(tenant_id=DEMO_TENANT_ID, display_name=name)
    session.add(user)
    session.flush()
    role = Role(tenant_id=DEMO_TENANT_ID, code=role_code, name=name)
    session.add(role)
    session.flush()
    for code in perms:
        session.add(RolePermission(role_id=role.id, permission_id=_permission(session, code).id))
    session.add(UserRole(tenant_id=DEMO_TENANT_ID, user_id=user.id, role_id=role.id))
    session.flush()
    return str(user.id)


def _half(value: Decimal) -> Decimal:
    """A ceiling the book is genuinely THROUGH — derived from the measured number, so the breach is
    real arithmetic rather than a fixture that happens to trip."""
    return (value / 2).quantize(Decimal("0.000001"))


def _headroom(value: Decimal) -> Decimal:
    """A ceiling the book is comfortably INSIDE — HALFWAY between the measured share and 1.

    **The obvious "double it" is wrong here, and executing the stage is what proved it.** These
    metrics are shares in [0, 1]: the demo book's top issuer is at 0.60, so doubling gives 1.20,
    which a cap then pinned to 0.999999 — a threshold no share can ever exceed. That limit would
    have rendered green forever *for a reason that has nothing to do with the book*, which is
    exactly the degenerate case the cap was written to avoid. The docstring stated the hazard and
    the arithmetic walked into it anyway; only running the stage and reading the row surfaced it.

    Halfway to 1 keeps the headroom REAL: at 0.60 measured the ceiling is 0.80, genuinely above
    the book and genuinely reachable if the book concentrated further.
    """
    return (value + (Decimal(1) - value) / 2).quantize(Decimal("0.000001"))


def run_demo_lim2_stage20(session: Any) -> Lim2Stage20Summary:  # noqa: ANN401
    """Write the concentration limits over CON-1's demo book and drive one real breach."""
    if session.execute(
        select(LimitDefinition.id).where(
            LimitDefinition.tenant_id == DEMO_TENANT_ID, LimitDefinition.code == _ISSUER_CODE
        )
    ).first():
        raise DemoLim2AlreadySeededError("the LIM-2 demo limits are already seeded")

    portfolio = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _BOOK_CODE)
    ).scalar_one_or_none()
    if portfolio is None:
        raise DemoLim2PrereqError(
            f"the {_BOOK_CODE} book does not exist — run the CON-1 stage (19) first"
        )

    # --- READ WHAT THE DATABASE ACTUALLY COMPUTED -------------------------------------------
    # Not what the CON-1 record says it computed. This session's recurring lesson is that asking
    # the component (or the document) is not verification; ask the database.
    # The SHIPPED latest-resolver, not a hand-rolled query: it filters to COMPLETED runs and takes
    # the newest, which is exactly what `_resolve_concentration` will do when the limits evaluate.
    # Using a different read here would let the demo pass against rows the evaluator cannot see.
    rows = latest_concentration(
        session,
        acting_tenant=DEMO_TENANT_ID,
        portfolio_id=str(portfolio.id),
        include_issuer_detail=True,
    )
    if not rows:
        raise DemoLim2PrereqError(
            "the demo book has no concentration results — the CON-1 stage did not complete"
        )
    run_id = rows[0].calculation_run_id

    issuer_detail = [
        r
        for r in rows
        if r.dimension_kind == DIMENSION_KIND_ISSUER
        and r.row_kind == ROW_KIND_DETAIL
        and r.bucket_code not in BUCKET_SENTINELS
    ]
    sector_detail = [
        r
        for r in rows
        if r.dimension_kind == "SECTOR_INDUSTRY"
        and r.row_kind == ROW_KIND_DETAIL
        and r.bucket_code not in BUCKET_SENTINELS
    ]
    hhi_summary = [
        r for r in rows if r.row_kind == ROW_KIND_SUMMARY and r.metric_type == "HHI_ISSUER"
    ]
    if not issuer_detail or not sector_detail or not hhi_summary:
        raise DemoLim2PrereqError(
            "the demo concentration run lacks an issuer bucket, a sector bucket or an HHI summary "
            "— the fixture changed shape; re-derive this stage rather than loosening it"
        )

    # The LARGEST bucket in each dimension: the one a concentration limit is actually written about.
    top_issuer = max(issuer_detail, key=lambda r: r.share_invested_long or Decimal(0))
    top_sector = max(sector_detail, key=lambda r: r.share_invested_long or Decimal(0))
    measured_issuer = Decimal(top_issuer.share_invested_long or 0)
    measured_sector = Decimal(top_sector.share_invested_long or 0)
    measured_hhi = Decimal(hhi_summary[0].metric_value or 0)

    maker = _make_operator(session, _MAKER_ROLE, "Demo LIM-2 Maker (2L)", _MAKER_PERMS)
    checker = _make_operator(session, _CHECKER_ROLE, "Demo LIM-2 Checker (2L)", _CHECKER_PERMS)
    viewer = _make_operator(
        session, _FENCED_VIEWER_ROLE, "Demo LIM-2 Viewer (no issuer identity)", _FENCED_VIEWER_PERMS
    )
    maker_actor = LimitActor(actor_id=maker)
    checker_actor = LimitActor(actor_id=checker)

    def _limit(**kwargs: Any) -> LimitDefinition:  # noqa: ANN401
        """A concentration limit over the demo book. `breach_direction` DEFAULTS to ABOVE but is
        overridable — the review noted every limit in the slice, the demo and both test files was a
        ceiling, so the floor direction (where the fabricated zero wrote a FALSE breach) had no
        coverage anywhere."""
        kwargs.setdefault("breach_direction", BREACH_ABOVE)
        return create_limit(
            session,
            tenant_id=DEMO_TENANT_ID,
            scope_portfolio_id=str(portfolio.id),
            threshold_unit=THRESHOLD_UNIT_FRACTION,
            target_run_type=RUN_TYPE_CONCENTRATION,
            denominator_basis=DENOMINATOR_BASIS_INVESTED_LONG,
            actor=maker_actor,
            **kwargs,
        )

    sector_limit = _limit(
        code=_SECTOR_CODE,
        name=f"No more than {_half(measured_sector)} of the invested-long book in one industry",
        metric_type=METRIC_TYPE_SHARE,
        dimension_kind="SECTOR_INDUSTRY",
        bucket_code=top_sector.bucket_code,
        scheme_family=_scheme_family(session, top_sector.scheme_id),
        authored_scheme_id=str(top_sector.scheme_id) if top_sector.scheme_id else None,
        threshold_value=_half(measured_sector),
        limit_kind=LIMIT_KIND_HARD,
    )
    issuer_limit = _limit(
        code=_ISSUER_CODE,
        name="Single-issuer concentration ceiling",
        metric_type=METRIC_TYPE_SHARE,
        dimension_kind=DIMENSION_KIND_ISSUER,
        bucket_code=top_issuer.bucket_code,
        issuer_id=str(top_issuer.issuer_id),
        threshold_value=_half(measured_issuer),
        limit_kind=LIMIT_KIND_HARD,
    )
    healthy_limit = _limit(
        code=_HEALTHY_CODE,
        name="Single-issuer headroom monitor",
        metric_type=METRIC_TYPE_SHARE,
        dimension_kind=DIMENSION_KIND_ISSUER,
        bucket_code=top_issuer.bucket_code,
        issuer_id=str(top_issuer.issuer_id),
        threshold_value=_headroom(measured_issuer),
        limit_kind=LIMIT_KIND_SOFT,
    )
    hhi_limit = _limit(
        code=_HHI_CODE,
        name="Portfolio-level issuer concentration (HHI)",
        metric_type="HHI_ISSUER",
        dimension_kind=DIMENSION_KIND_ISSUER,
        threshold_value=_half(measured_hhi),
        limit_kind=LIMIT_KIND_SOFT,
    )
    # Left DRAFT on purpose: the approval queue's content, demonstrating that a limit awaiting
    # sign-off constrains nothing.
    _limit(
        code=_DRAFT_CODE,
        name="Proposed tighter single-issuer ceiling",
        metric_type=METRIC_TYPE_SHARE,
        dimension_kind=DIMENSION_KIND_ISSUER,
        bucket_code=top_issuer.bucket_code,
        issuer_id=str(top_issuer.issuer_id),
        threshold_value=_half(_half(measured_issuer)),
        limit_kind=LIMIT_KIND_HARD,
    )

    # --- the maker-checker gate: a DIFFERENT person approves ---------------------------------
    approved = 0
    for limit in (sector_limit, issuer_limit, healthy_limit, hhi_limit):
        approve_limit(
            session, limit, actor=checker_actor, approval_ref="minutes://RISK-COMMITTEE-2026-07"
        )
        approved += 1
    session.flush()

    # --- detection through the REAL evaluation path -------------------------------------------
    now = datetime.now(UTC)
    detected = 0
    for limit in (sector_limit, issuer_limit, hhi_limit):
        breach = evaluate_limit(session, limit, now)
        if breach is None:
            raise DemoLim2Error(
                f"limit {limit.code} did not breach, but its threshold was derived as HALF the "
                "measured value — the demo book's numbers moved; re-derive rather than loosen"
            )
        detected += 1
    if evaluate_limit(session, healthy_limit, now) is not None:
        raise DemoLim2Error(
            f"{_HEALTHY_CODE} breached at double the measured share — "
            "the fixture is not as intended"
        )
    session.flush()

    # --- the REFUSAL, demonstrated rather than described --------------------------------------
    # No NAV denominator is computable on this schema, so a regulatory-shaped threshold cannot be
    # written at all (the CON-1 descope). Asked for EXPLICITLY — the `_limit` helper always supplies
    # INVESTED_LONG, so routing through it could never demonstrate this.
    try:
        create_limit(
            session,
            tenant_id=DEMO_TENANT_ID,
            code="DEMO-UCITS-SHAPED",
            name="5% of NAV (a regulatory-shaped threshold)",
            target_run_type=RUN_TYPE_CONCENTRATION,
            metric_type=METRIC_TYPE_SHARE,
            scope_portfolio_id=str(portfolio.id),
            threshold_value=Decimal("0.05"),
            threshold_unit=THRESHOLD_UNIT_FRACTION,
            breach_direction=BREACH_ABOVE,
            limit_kind=LIMIT_KIND_HARD,
            dimension_kind=DIMENSION_KIND_ISSUER,
            bucket_code=top_issuer.bucket_code,
            issuer_id=str(top_issuer.issuer_id),
            denominator_basis="NAV",
            actor=maker_actor,
        )
    except LimitError as exc:
        refusal = str(exc)
    else:
        raise DemoLim2Error(
            "a NAV-denominated threshold was ACCEPTED — the basis discipline is not enforced"
        )

    # --- the fence, demonstrated as a real read ----------------------------------------------
    fenced = list_limits(session, acting_tenant=DEMO_TENANT_ID, include_issuer_detail=False)
    fenced_codes = {x.code for x in fenced}
    issuer_named = {_ISSUER_CODE, _HEALTHY_CODE, _DRAFT_CODE}
    leaked = issuer_named & fenced_codes
    if leaked:
        # Report WHY, not just THAT. A bare "the fence leaked" sends the next reader hunting
        # through the query when the cause is usually the row: an issuer-named limit whose
        # `issuer_id` never persisted is invisible to a fence that keys on `issuer_id IS NOT NULL`.
        detail = {
            x.code: {"issuer_id": x.issuer_id, "dimension_kind": x.dimension_kind}
            for x in fenced
            if x.code in leaked
        }
        raise DemoLim2Error(
            f"the issuer fence leaked {sorted(leaked)} to an unfenced read; "
            f"their persisted identity was {detail} "
            "(a NULL issuer_id here means the WRITE dropped it, not that the fence is wrong)"
        )
    # POSITIVE CONTROL: the sector and HHI limits carry no issuer identity and MUST still be
    # visible, or "the fence works" would be indistinguishable from "the read is broken".
    if not {_SECTOR_CODE, _HHI_CODE} <= fenced_codes:
        raise DemoLim2Error(
            "the fence hid non-issuer limits too — it is filtering the family, not the identity"
        )
    health = limit_health(session, acting_tenant=DEMO_TENANT_ID, include_issuer_detail=False)
    if issuer_named & {h.code for h in health}:
        raise DemoLim2Error("the health surface leaked an issuer-named limit")

    # --- THE PATHS THAT WERE WRONG, RUN (adversarial review, "what the demo must actually RUN") --
    # The happy path above proves the feature works. These prove the DEFECTS are closed — and this
    # project's record is that execution refutes what reading endorses (SCH-2 refuted two decisions
    # an adversarial verifier had approved; CON-1's truncated CHECK names surfaced only by running).
    # Every one of these read IN_APPETITE, or wrote a false breach, before the review.
    unmatched_refusals: list[str] = []

    # (1) An unmatched selector on a CEILING. 'TECH' is not an ISIC code (ISIC sections are
    #     letters), so this limit named a bucket the run never evaluated. It used to resolve to a
    #     fabricated zero and read IN_APPETITE forever on a 60%-concentrated book.
    typo_ceiling = _limit(
        code="DEMO-TYPO-CEILING",
        name="A ceiling whose bucket_code names no node (must NOT read green)",
        metric_type=METRIC_TYPE_SHARE,
        dimension_kind="SECTOR_INDUSTRY",
        bucket_code="TECH",
        scheme_family=_scheme_family(session, top_sector.scheme_id),
        authored_scheme_id=str(top_sector.scheme_id) if top_sector.scheme_id else None,
        threshold_value=Decimal("0.200000"),
        limit_kind=LIMIT_KIND_HARD,
    )
    approve_limit(
        session, typo_ceiling, actor=checker_actor, approval_ref="minutes://RISK-COMMITTEE-2026-07"
    )
    approved += 1
    if evaluate_limit(session, typo_ceiling, now) is not None:
        raise DemoLim2Error("an unverifiable selector produced a breach — the D1 fix is not live")

    # (2) The SEVERE direction: the same unmatched selector as a FLOOR. It used to satisfy
    #     _breaches(0, 0.05, BELOW) and write a breach into the APPEND-ONLY, non-withdrawable
    #     lifecycle. Asserted by reading the DATABASE, not by trusting the return value.
    typo_floor = _limit(
        code="DEMO-TYPO-FLOOR",
        name="A floor whose bucket_code names no node (must write NO breach)",
        metric_type=METRIC_TYPE_SHARE,
        dimension_kind="SECTOR_INDUSTRY",
        bucket_code="TECH",
        scheme_family=_scheme_family(session, top_sector.scheme_id),
        authored_scheme_id=str(top_sector.scheme_id) if top_sector.scheme_id else None,
        threshold_value=Decimal("0.050000"),
        limit_kind=LIMIT_KIND_HARD,
        breach_direction=BREACH_BELOW,
    )
    approve_limit(
        session, typo_floor, actor=checker_actor, approval_ref="minutes://RISK-COMMITTEE-2026-07"
    )
    approved += 1
    evaluate_limit(session, typo_floor, now)
    session.flush()
    false_breaches = session.execute(
        select(Breach).where(
            Breach.tenant_id == DEMO_TENANT_ID,
            Breach.limit_definition_id.in_([typo_ceiling.id, typo_floor.id]),
        )
    ).scalars()
    if list(false_breaches):
        raise DemoLim2Error(
            "a FALSE BREACH was written into the append-only lifecycle from an unverifiable "
            "selector — the D1 fix is not live and the row cannot be withdrawn"
        )

    # (3) Both must report REFUSED with a reason — visible, not silently green and not merely
    #     indistinguishable from a cold metric.
    health_by_code = {
        h.code: h
        for h in limit_health(session, acting_tenant=DEMO_TENANT_ID, include_issuer_detail=True)
    }
    for code in ("DEMO-TYPO-CEILING", "DEMO-TYPO-FLOOR"):
        entry = health_by_code.get(code)
        if entry is None or entry.state != HEALTH_REFUSED or not entry.refusal_reason:
            raise DemoLim2Error(
                f"{code} reports {entry.state if entry else 'ABSENT'} rather than REFUSED with a "
                "reason — an unverifiable limit must never read as a measurement"
            )
        unmatched_refusals.append(code)

    # (4) The POSITIVE CONTROL for all of the above: the real sector limit still breaches. Without
    #     it, "the refusals fire" would be satisfied by a resolver that refused everything.
    if health_by_code[_SECTOR_CODE].state != HEALTH_BREACHED:
        raise DemoLim2Error(
            f"{_SECTOR_CODE} no longer reads BREACHED — the D1 refusal is over-broad and has "
            "swallowed a genuine measurement"
        )

    # --- TEAR DOWN this stage's entitlement rows (the CON-1 OQ-REF-1-29 discipline) -----------
    # Found by executing `alembic downgrade base` after the stage: the three roles minted above
    # leave `role_permission` rows, and the entitlement downgrade then dies deleting the
    # `permission` rows they reference (ForeignKeyViolation on
    # fk_role_permission_permission_id_permission). CON-1 paid exactly this and said why: "a demo
    # that only ever GRANTS leaves rows behind that a later census reads as production
    # entitlements." The personas have served their purpose by this line — the maker/checker SoD
    # is already recorded in the immutable LIMIT.APPROVE events, and the fence is proven by the
    # reads above, not by the viewer's continued existence.
    torn_down = _teardown_roles(session, (_MAKER_ROLE, _CHECKER_ROLE, _FENCED_VIEWER_ROLE))
    _ = viewer  # minted for the walkthrough; its grants are gone by here, by design

    return Lim2Stage20Summary(
        concentration_run_id=str(run_id),
        measured_issuer_share=f"{measured_issuer:f}",
        measured_sector_share=f"{measured_sector:f}",
        measured_hhi=f"{measured_hhi:f}",
        limits_created=7,
        limits_approved=approved,
        breaches_detected=detected,
        fenced_from_viewer=tuple(sorted(issuer_named)),
        visible_to_viewer=(_HHI_CODE, _SECTOR_CODE),
        regulatory_threshold_refused=refusal,
        unverifiable_selectors_refused=tuple(unmatched_refusals),
        role_permission_rows_torn_down=torn_down,
    )


def _teardown_roles(session: Any, role_codes: tuple[str, ...]) -> int:  # noqa: ANN401
    """Delete the demo roles' grants and the roles themselves; return the grant count removed.

    Order matters: ``user_role`` and ``role_permission`` both FK ``role``, so the children go
    first. Asserting zero survivors is the part that makes the teardown a claim rather than a hope.
    """
    removed = 0
    for code in role_codes:
        role = session.execute(
            select(Role).where(Role.tenant_id == DEMO_TENANT_ID, Role.code == code)
        ).scalar_one_or_none()
        if role is None:
            continue
        for rp in list(
            session.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            ).scalars()
        ):
            session.delete(rp)
            removed += 1
        for ur in list(
            session.execute(select(UserRole).where(UserRole.role_id == role.id)).scalars()
        ):
            session.delete(ur)
        session.flush()
        session.delete(role)
    session.flush()
    survivors = session.execute(
        select(Role).where(Role.tenant_id == DEMO_TENANT_ID, Role.code.in_(role_codes))
    ).scalars()
    if list(survivors):
        raise DemoLim2Error("demo roles survived the teardown")
    return removed


def _scheme_family(session: Any, scheme_id: Any) -> str | None:  # noqa: ANN401
    """The scheme FAMILY a concentration row was computed under — the LIM-2 binding selector."""
    if scheme_id is None:
        return None
    from irp_shared.classification.models import ClassificationScheme

    scheme = session.execute(
        select(ClassificationScheme).where(ClassificationScheme.id == str(scheme_id))
    ).scalar_one_or_none()
    return str(scheme.scheme_family) if scheme is not None else None


__all__ = [
    "DemoLim2AlreadySeededError",
    "DemoLim2Error",
    "DemoLim2PrereqError",
    "Lim2Stage20Summary",
    "run_demo_lim2_stage20",
]
