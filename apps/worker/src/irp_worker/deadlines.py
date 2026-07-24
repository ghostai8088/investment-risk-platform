"""MG-2 worker breach-deadline phase — the THIRD phase of the per-tenant operational tick.

Runs after ``poll_tenant_breaches`` inside the SAME tenant-scoped non-BYPASSRLS ``run_in_tenant``
context (the DEP-WFL deadline enforcement rides the SCH-1 cadence — a PHASE of the single per-tenant
tick, not a new entrypoint). Auto-ESCALATES any breach whose response deadline has passed.

Mirrors the phase-2 (``breaches.py``) SINGLE-LAYER isolation shape (NOT phase-1's ``_record_failed``
two-layer form — there is no failed-escalation ledger): each breach escalates in its OWN SAVEPOINT;
ONLY a ``uq_breach_escalation`` violation is treated as the benign already-escalated-this-deadline
dedup; any OTHER IntegrityError (or failure) is LOGGED, never masked; nothing escapes to abort the
single terminal commit. The escalate decision is re-checked UNDER the parent-breach lock inside
``escalate_overdue_breach`` — the candidate read here is a pre-filter only.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.limit.lifecycle import escalate_overdue_breach, select_overdue_breaches

_LOGGER = logging.getLogger("irp_worker.deadlines")

#: The partial-unique index that backstops the per-(breach, deadline) escalation idempotency. ONLY a
#: violation of THIS index is the benign already-escalated-this-deadline dedup.
_ESCALATE_DEDUP_CONSTRAINT = "uq_breach_escalation"


def _is_escalate_dedup(exc: IntegrityError) -> bool:
    """True only when ``exc`` is the ``(breach, response_due)`` escalation dedup, NOT some other
    constraint violation (psycopg ``diag.constraint_name`` + message fallback)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    if getattr(diag, "constraint_name", None) == _ESCALATE_DEDUP_CONSTRAINT:
        return True
    return _ESCALATE_DEDUP_CONSTRAINT in str(exc)


def poll_tenant_breach_deadlines(
    session: Session, now: datetime, *, acting_tenant: str
) -> list[str]:
    """Auto-escalate every overdue breach for the current tenant; return the escalated breach ids.

    A breach is escalated at most ONCE per deadline epoch (``uq_breach_escalation``); a long-overdue
    breach re-selects each tick but the repeat is a benign dedup. A post-recovery 2L REJECT stamps a
    fresh deadline (a new epoch) that can legitimately escalate again.
    """
    escalated: list[str] = []
    for breach in select_overdue_breaches(session, now, acting_tenant=acting_tenant):
        savepoint = session.begin_nested()
        try:
            action = escalate_overdue_breach(session, breach, now)
            savepoint.commit()
            if action is not None:
                escalated.append(breach.id)
        except IntegrityError as exc:
            savepoint.rollback()
            if _is_escalate_dedup(exc):
                # Already escalated this deadline epoch — benign concurrent-tick dedup.
                continue
            # A REAL constraint violation — LOG it, do not mask.
            _LOGGER.error(
                "breach escalation hit a non-dedup IntegrityError for breach %s: %s",
                breach.id,
                exc,
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed per-breach isolation
            savepoint.rollback()
            _LOGGER.error("breach escalation failed for breach %s: %s", breach.id, exc)
    return escalated
