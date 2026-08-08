"""REPRO-1 worker reproduction-alarm phase — the FIFTH phase of the per-tenant operational tick.

Runs AFTER the phases-1-2 commit, in its own top-level transactions, for one reason that is
structural rather than stylistic: the sweep that PRODUCES verdicts runs inside phase 1, and that
transaction holds the per-tenant audit-chain advisory lock (``record_event`` takes it, held to
top-level COMMIT). Delivering to a network sink there would hold that lock across I/O — the API-2b
anti-pattern NOTIF-1's phase-A/phase-B split exists to prevent. So the sweep records and stops, and
this phase alarms.

**The queue is a per-verdict EVENT question, not a cursor.** ``unalarmed_verdicts`` asks, per
verdict, whether a ``NOTIFY.DISPATCH`` event records that the attempt CONCLUDED (SENT or
SUPPRESSED) or that the bounded FAILED retries are exhausted — not merely whether any event
exists, which was the shape that dropped alarms, nor SENT-only, which never terminated.

NOTIF-1 learned the cursor half the hard way: a derived ``MAX(sequence)`` high-water cannot
represent a GAP, so one row jumping ahead permanently hides every earlier unalarmed one. A
per-verdict question has no such failure mode, and the population is a handful of rows per night.

**Per-verdict top-level transactions, fail-CLOSED on error.** A verdict whose alarm transaction
fails is left un-alarmed and is retried next tick — the transaction rolled back, so no attempt was
recorded, so the verdict is still in the queue by the queue's own rule. A failure does NOT stop the
batch (unlike phase 4, whose cursor semantics force head-of-line blocking): a per-verdict question
has no cursor to corrupt, so one poison verdict must not silence the others.

**Note the one path the retry bound does NOT bound**, stated here rather than left to be
rediscovered: ``MAX_ALARM_ATTEMPTS`` counts durably-recorded FAILED attempts, and a verdict whose
alarm TRANSACTION raises records nothing at all. That path retries every tick indefinitely. It is
carried (see carry (q) in the slice record) rather than fixed here, because recording a failure
durably inside the transaction that just failed is not available — the honest fix is an operational
signal on repeated rollback, which belongs to an alerting slice.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from irp_shared.notification.service import default_sink
from irp_shared.notification.sink import NotificationSink
from irp_shared.reproduction.service import alarm_for_verdict, unalarmed_verdicts

_LOGGER = logging.getLogger("irp_worker.reproduction_alarms")


def poll_tenant_reproduction_alarms(
    session: Session,
    now: datetime,
    *,
    acting_tenant: str,
    sink: NotificationSink | None = None,
) -> list[tuple[str, str]]:
    """Alarm every un-alarmed DIVERGED/UNREPRODUCIBLE verdict; return ``(check_id, outcome)``.

    The caller MUST hold a ``persistent_tenant_context`` re-arm: the RLS GUC is transaction-local
    and clears at COMMIT, so an un-re-armed post-commit transaction would read ZERO verdicts and
    alarm NOTHING — the OQ-a fail-open pattern the API-2b verifier caught in phase 3.
    """
    channel = sink or default_sink()
    alarmed: list[tuple[str, str]] = []
    # Snapshot the ids alongside the instances: each commit expires the objects, and the plain
    # string is what survives for the return value (the phase-4 precedent).
    #
    # GUARDED, because this call sits OUTSIDE the per-verdict isolation below and an independent
    # review pointed out what that costs: `unalarmed_verdicts` folds a JSON payload in Python, so a
    # malformed `after_value` raises here rather than inside the loop, and the exception would leave
    # this function, leave `run_operational_tick_for_tenant`, and take the tenant's whole tick with
    # it. No current writer can produce that payload — this is hardening a latent path, not fixing a
    # live defect — but the blast radius was the argument for the per-verdict try in the first
    # place, and a queue that cannot be READ should cost the phase, never the tick.
    try:
        pending = [
            (str(check.id), check)
            for check in unalarmed_verdicts(session, acting_tenant=acting_tenant)
        ]
    except Exception as exc:  # noqa: BLE001 - an unreadable queue is this phase's failure, not the tick's
        session.rollback()
        _LOGGER.error(
            "reproduction alarm queue could not be read for tenant %s; phase 5 is skipped this "
            "tick and every verdict stays queued: %s",
            acting_tenant,
            exc,
        )
        return alarmed
    for check_id, check in pending:
        try:
            outcome = alarm_for_verdict(
                session, check=check, sink=channel, acting_tenant=acting_tenant, now=now
            )
            session.commit()
            alarmed.append((check_id, outcome))
        except Exception as exc:  # noqa: BLE001 - per-verdict isolation, fail CLOSED
            session.rollback()
            # NOT a `break`. Phase 4 stops the batch because its cursor is a derived MAX that a
            # later commit would advance past a failed earlier event. Here the rollback means no
            # attempt was recorded, so the verdict is still queued by the queue's own rule — and
            # stopping would let one poison verdict silence every other divergence that night.
            _LOGGER.error(
                "reproduction alarm failed for verdict %s; it stays queued for the next tick: %s",
                check_id,
                exc,
            )
    return alarmed
