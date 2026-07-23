"""LIM-1 worker breach-evaluation phase — the second phase of the per-tenant operational tick.

Runs alongside ``poll_tenant_schedules`` inside ONE tenant's non-BYPASSRLS ``run_in_tenant`` context
(the Fable audit demand #2: breach evaluation is a PHASE of the single per-tenant tick,
NOT a ``Schedule`` row). Each limit evaluates in its OWN SAVEPOINT — the SCH-1 isolation
pattern — a concurrent breach dedup or a per-limit eval failure rolls back only THAT limit; the
loop continues; one limit never starves the others, and nothing escapes to abort the commit.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.limit.service import evaluate_limit, select_active_limits


def poll_tenant_breaches(
    session: Session, now: datetime, *, acting_tenant: str
) -> list[tuple[str, str | None]]:
    """Evaluate every ACTIVE limit for the current tenant; return ``(limit_id, breach_id | None)``.

    A ``None`` breach_id means "evaluated, no breach" (in appetite / never-evaluable / a concurrent
    dedup / an isolated eval failure). Discovery is ``calculation_run``-driven (so a MANUALLY-run
    number is limit-checked too). Idempotent on ``(limit_id, calculation_run_id)`` — the
    ``uq_breach_limit_run`` constraint is the hard race backstop; a losing concurrent detect rolls
    back its phantom breach.
    """
    results: list[tuple[str, str | None]] = []
    for limit in select_active_limits(session, acting_tenant=acting_tenant):
        savepoint = session.begin_nested()
        try:
            breach = evaluate_limit(session, limit, now)
            savepoint.commit()
            results.append((limit.id, breach.id if breach is not None else None))
        except IntegrityError:
            # A concurrent tick already recorded this (limit, run) breach — benign dedup.
            savepoint.rollback()
            results.append((limit.id, None))
        except Exception:  # noqa: BLE001 - fail-closed per-limit isolation
            # An isolated eval failure: skip this limit, re-evaluate next tick (limit_health
            # surfaces a persistently un-evaluable limit — OD-LIM-1-L).
            savepoint.rollback()
            results.append((limit.id, None))
    return results
