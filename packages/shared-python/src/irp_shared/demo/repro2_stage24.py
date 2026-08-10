"""Demo stage 24 (REPRO-2, OQ-REP2-5) — the demo tenant becomes DISCOVERABLE and gets its sweep.

Runs LAST, and the position is load-bearing rather than tidy. The seeding was first written into
`run_demo_campaign`'s body; the full-PG battery refused it, because a reproduction schedule
existing before stage 15 makes that stage's tick dispatch TWO schedules where it asserts exactly
one — and every downstream count pin then came up one COMPLETED run short. Adding a schedule to a
shared demo tenant changes what every subsequent tick does, so it goes last.

What the stage delivers is a PAIR, and either half alone would be a green test over a dead control:
the tenant is registered ACTIVE in the ENT-074 registry (without it the discovering worker never
visits, and the schedule is inert), and the schedule is created through the REAL `create_schedule`
service (a demo that seeds around its own service demonstrates nothing about the service).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from irp_shared.demo.campaign import DEMO_TENANT_ID, _register_and_schedule_reproduction


class DemoRepro2AlreadySeededError(RuntimeError):
    """The demo tenant already has a reproduction schedule — refuse-not-skip, the campaign rule."""


@dataclass(frozen=True)
class Repro2StageSummary:
    tenant_id: str
    schedule_id: str


def run_demo_repro2_stage24(session: Session, *, registrar_user_id: str) -> Repro2StageSummary:
    """Register the demo tenant and create its nightly reproduction schedule."""
    schedule_id = _register_and_schedule_reproduction(session, registrar_user_id)
    if schedule_id is None:
        raise DemoRepro2AlreadySeededError(
            "the demo tenant already has a REPRODUCTION schedule — re-seed from a clean database"
        )
    return Repro2StageSummary(tenant_id=DEMO_TENANT_ID, schedule_id=schedule_id)
