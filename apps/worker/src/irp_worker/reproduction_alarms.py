"""REPRO-1 worker reproduction-alarm phase — the FIFTH phase of the per-tenant operational tick.

Runs AFTER the phases-1-2 commit, in its own top-level transactions, for one reason that is
structural rather than stylistic: the sweep that PRODUCES verdicts runs inside phase 1, and that
transaction holds the per-tenant audit-chain advisory lock (``record_event`` takes it, held to
top-level COMMIT). Delivering to a network sink there would hold that lock across I/O — the API-2b
anti-pattern NOTIF-1's phase-A/phase-B split exists to prevent. So the sweep records and stops, and
this phase alarms.

**The queue is an EXISTENCE test, not a cursor.** ``unalarmed_verdicts`` asks, per verdict, whether
a ``NOTIFY.DISPATCH`` audit event already names it. NOTIF-1 learned the alternative the hard way: a
derived ``MAX(sequence)`` high-water cannot represent a GAP, so one row jumping ahead permanently
hides every earlier unalarmed one. Existence has no such failure mode, and the population is a
handful of rows per night.

**Per-verdict top-level transactions, fail-CLOSED on error.** A verdict whose alarm transaction
fails is left un-alarmed and is retried next tick — it stays in the queue precisely because the
queue is defined by the absence of its event. A failure does NOT stop the batch (unlike phase 4,
whose cursor semantics force head-of-line blocking): with an existence queue there is no cursor to
corrupt, so one poison verdict must not silence the others.
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
    pending = [
        (str(check.id), check) for check in unalarmed_verdicts(session, acting_tenant=acting_tenant)
    ]
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
            # later commit would advance past a failed earlier event. This queue is an existence
            # test, so a failed verdict simply stays in it — and stopping would let one poison
            # verdict silence every other divergence that night.
            _LOGGER.error(
                "reproduction alarm failed for verdict %s; it stays queued for the next tick: %s",
                check_id,
                exc,
            )
    return alarmed
