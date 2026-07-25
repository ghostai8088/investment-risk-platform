"""MG-2 worker breach-deadline phase — the THIRD phase of the per-tenant operational tick.

Runs after ``poll_tenant_breaches`` inside the SAME tenant-scoped non-BYPASSRLS session (the
DEP-WFL deadline enforcement rides the SCH-1 cadence — a PHASE of the single per-tenant tick, not
a new entrypoint). Auto-ESCALATES any breach whose response deadline has passed.

**Commit topology (API-2b OQ-3=A, the B-F1 deadlock fix):** each breach escalates in its OWN
TOP-LEVEL transaction (per-breach ``commit``/``rollback``, no SAVEPOINT) so every escalation
acquires breach-row → audit-advisory in the SAME order as the HTTP breach verbs — the row-lock
order inversion that made a tick×HTTP deadlock reachable under the old single-transaction shape is
structurally gone. A residual tick×tick unique-INDEX tuple-wait inversion in phases 1–2 is
foreclosed by the deterministic ``ORDER BY id`` iteration in the phase selectors; even unordered
it was benign — SAVEPOINT-recovered and retried next tick.
Escalations are independent and idempotent (``uq_breach_escalation`` + every
condition re-checked UNDER the parent-breach lock inside ``escalate_overdue_breach``), so a
mid-phase crash loses nothing (uncommitted candidates re-select next tick; committed ones dedup).
ONLY a ``uq_breach_escalation`` violation is the benign already-escalated dedup; any OTHER
IntegrityError (or failure) is LOGGED, never masked. The caller MUST hold a
``persistent_tenant_context`` re-arm on the session — the RLS GUC is transaction-local, and an
un-re-armed post-commit transaction would silently see ZERO breaches (fail-open).
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
    # Materialize (id, instance) up front: each loop iteration commits, which EXPIRES the ORM
    # instances — the next iteration's attribute access refreshes the row in the NEW (re-armed)
    # transaction; a hypothetically invisible row raises into the blanket except (fail-closed).
    candidates = [
        (breach.id, breach)
        for breach in select_overdue_breaches(session, now, acting_tenant=acting_tenant)
    ]
    for breach_id, breach in candidates:
        try:
            action = escalate_overdue_breach(session, breach, now)
            session.commit()  # per-breach TOP-LEVEL commit (row→advisory order, OQ-API-2b-3=A)
            if action is not None:
                escalated.append(breach_id)
        except IntegrityError as exc:
            session.rollback()
            if _is_escalate_dedup(exc):
                # Already escalated this deadline epoch — benign concurrent-tick dedup.
                continue
            # A REAL constraint violation — LOG it, do not mask.
            _LOGGER.error(
                "breach escalation hit a non-dedup IntegrityError for breach %s: %s",
                breach_id,
                exc,
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed per-breach isolation
            session.rollback()
            _LOGGER.error("breach escalation failed for breach %s: %s", breach_id, exc)
    return escalated
