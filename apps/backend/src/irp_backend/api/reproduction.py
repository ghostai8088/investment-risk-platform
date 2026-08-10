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

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.reproduction.service import alarm_channel_health

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

    #: AMBER — visible, deliberately not red.
    undeliverable_attempts: int
    exhausted_verdicts: int

    #: INFORMATIONAL — facts, not faults.
    queued: int
    no_schedule: bool
    paused_schedules: int
    nothing_to_reproduce: int
    last_terminal_sweep_at: datetime | None


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
        undeliverable_attempts=health.undeliverable_attempts,
        exhausted_verdicts=health.exhausted_verdicts,
        queued=health.queued,
        no_schedule=health.no_schedule,
        paused_schedules=health.paused_schedules,
        nothing_to_reproduce=health.nothing_to_reproduce,
        last_terminal_sweep_at=health.last_terminal_sweep_at,
    )
