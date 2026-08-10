"""The reproduction alarm-channel health read (ALERT-1, ratified OQ-ALR-2).

**What this exists for.** REPRO-1 built a detective control and the Wave-16 close hardened it, and
between them they left a control that can be broken, degraded, bounded, silenced, or simply STOPPED
with no path by which an operator learns any of it. `AlarmChannelHealth` was computed correctly and
consumed by nothing. This is the route that makes it reachable.

**Counts, booleans and one timestamp — nothing else.** REPRO-1 carry (n) binds a redaction residual
to the moment a read surface appears over ENT-073, because an ``UNREPRODUCIBLE`` reason can embed a
binder's exception text and some binder messages interpolate row identifiers. This payload never
carries a verdict id, a reason, or a ``first_divergence``: it is aggregate control-plane evidence
about whether the ALARM CHANNEL works, not about what any verdict says. The carry stays bound to
REPRO-2's verdict reads, where content actually appears.

**Permission: ``schedule.view``, REUSED.** Channel health is control-plane oversight of the
CTRL-018 chain — the class ``auditor_3l`` is included in rather than excluded from, since the
payload carries no proprietary values and no person data. Holders (recomputed from
``ROLE_TEMPLATES`` at the ratification, not transcribed): ``data_steward``, ``risk_analyst_1l``,
``risk_manager_2l``, ``auditor_3l``, ``platform_admin``. ``tenant_admin`` deliberately does NOT
hold it — a tenant administrator administers PEOPLE, not the risk control plane — and that
exclusion is a ratified decision with a revisit trigger, not an oversight.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.reproduction.events import VERDICT_UNREPRODUCIBLE
from irp_shared.reproduction.models import ReproductionCheck
from irp_shared.reproduction.service import alarm_channel_health

#: What an UNREPRODUCIBLE row's `first_divergence` becomes ON THE WIRE — a FIXED LITERAL, never
#: the stored text (REPRO-2, ratified OQ-REP2-3).
#:
#: **This is carry (n)'s discharge, and it is discharge BY EXCLUSION rather than by redaction.**
#: On the DIVERGED path `first_divergence` names a row KEY and a FIELD — mutation-proven at
#: REPRO-1 to carry no values. On the UNREPRODUCIBLE path it embeds a binder's exception text,
#: `_redact` bounds that text without guaranteeing the absence of every identifier, and the carry
#: bound that residual to "before any read surface is added over ENT-073". This is that surface.
#:
#: The design's first answer was to ship the exception CLASS NAME — which the verifier pass proved
#: unimplementable: the class name is not recoverable from the stored text on the paths that
#: actually produce these rows, and a prefix-parse would have emitted the message body on exactly
#: the rows lacking a prefix. So no read surface transports the stored text at all. It stays in
#: the database for database-grade investigation, which is where an operator with a real
#: divergence to chase is going anyway.
UNREPRODUCIBLE_WIRE_DETAIL = "UNREPRODUCIBLE — detail withheld; investigate at database grade"

#: The page cap. An append-only table's list read must not be unbounded (carry (k)'s class).
_MAX_PAGE = 200

router = APIRouter(tags=["reproduction"])

_require_view = require_permission("schedule.view")


class AlarmHealthOut(BaseModel):
    """The alarm channel's health. Every field is recomputed from source on every read — never
    stored, never inferred from the presence of an evidence row (the LIM-1 rule)."""

    #: RED — the channel is not doing its job.
    healthy: bool
    unreadable_rows: int
    lost_verdicts: int
    failed_sweeps: int
    sweep_overdue: bool
    dead_channel: bool
    #: REPRO-2's amendment to ALERT-1's enumeration: configured, then every schedule paused.
    control_switched_off: bool

    #: AMBER — visible, deliberately not red.
    undeliverable_attempts: int
    exhausted_verdicts: int

    #: INFORMATIONAL — facts, not faults.
    queued: int
    no_schedule: bool
    paused_schedules: int
    nothing_to_reproduce: int
    last_terminal_sweep_at: datetime | None


class ReproductionCheckOut(BaseModel):
    """One verdict, as the wire may see it.

    Counts, keys and ids — plus `first_divergence` under the OQ-ALR-3 rule above. Note what is
    NOT here and never will be without another ratification: the two diverging VALUES. They are
    absent from the stored row for the same reason.
    """

    id: str
    family_key: str
    verdict: str
    rows_compared: int
    rows_diverged: int
    subject_run_id: str
    calculation_run_id: str
    system_from: datetime
    first_divergence: str | None


@router.get("/reproduction/checks", response_model=list[ReproductionCheckOut])
def list_checks(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
    family_key: str | None = Query(default=None),
    verdict: str | None = Query(default=None),
    since_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=_MAX_PAGE),
) -> list[ReproductionCheckOut]:
    """The tenant's reproduction verdicts, newest first.

    Tenant-local by RLS with an explicit predicate underneath (the platform's belt-and-braces
    pattern), bounded by `limit` and a lookback window, and silent-empty rather than 404 on an
    unknown filter value — no existence oracle.
    """
    stmt = select(ReproductionCheck).where(
        ReproductionCheck.tenant_id == principal.tenant_id,
        ReproductionCheck.system_from >= datetime.now(UTC) - timedelta(days=since_days),
    )
    if family_key:
        stmt = stmt.where(ReproductionCheck.family_key == family_key)
    if verdict:
        stmt = stmt.where(ReproductionCheck.verdict == verdict)
    rows = (
        db.execute(stmt.order_by(ReproductionCheck.system_from.desc()).limit(limit)).scalars().all()
    )
    return [
        ReproductionCheckOut(
            id=str(r.id),
            family_key=r.family_key,
            verdict=r.verdict,
            rows_compared=r.rows_compared,
            rows_diverged=r.rows_diverged,
            subject_run_id=str(r.subject_run_id),
            calculation_run_id=str(r.calculation_run_id),
            system_from=r.system_from,
            first_divergence=_wire_divergence(r),
        )
        for r in rows
    ]


def _wire_divergence(row: ReproductionCheck) -> str | None:
    """DIVERGED: the stored field+key label. UNREPRODUCIBLE: the fixed literal. MATCH: nothing.

    Written as an explicit verdict switch rather than as "redact if it looks risky", because the
    property that must hold is not "we tried to clean it" — it is that stored UNREPRODUCIBLE text
    NEVER reaches this response, whatever it happens to contain.
    """
    if row.verdict == VERDICT_UNREPRODUCIBLE:
        return UNREPRODUCIBLE_WIRE_DETAIL
    return row.first_divergence


@router.get("/reproduction/alarm-health", response_model=AlarmHealthOut)
def read_alarm_health(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> AlarmHealthOut:
    """Is the reproduction alarm channel working, for the caller's own tenant?"""
    health = alarm_channel_health(db, acting_tenant=principal.tenant_id)
    return AlarmHealthOut(
        healthy=health.healthy,
        unreadable_rows=health.unreadable_rows,
        lost_verdicts=health.lost_verdicts,
        failed_sweeps=health.failed_sweeps,
        sweep_overdue=health.sweep_overdue,
        dead_channel=health.dead_channel,
        control_switched_off=health.control_switched_off,
        undeliverable_attempts=health.undeliverable_attempts,
        exhausted_verdicts=health.exhausted_verdicts,
        queued=health.queued,
        no_schedule=health.no_schedule,
        paused_schedules=health.paused_schedules,
        nothing_to_reproduce=health.nothing_to_reproduce,
        last_terminal_sweep_at=health.last_terminal_sweep_at,
    )
