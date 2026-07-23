"""LIM-1 worker breach-evaluation phase — the second phase of the per-tenant operational tick.

Runs alongside ``poll_tenant_schedules`` inside ONE tenant's non-BYPASSRLS ``run_in_tenant`` context
(the Fable audit demand #2: breach evaluation is a PHASE of the single per-tenant tick, NOT a
``Schedule`` row). Each limit evaluates in its OWN SAVEPOINT — the SCH-1 isolation pattern: a
concurrent dedup or a per-limit eval failure rolls back only THAT limit; the loop continues;
one limit never starves the others, and nothing escapes to abort the commit.

Fail-open guard (the 4-finder fold): ONLY ``uq_breach_limit_run`` dedup is treated as benign; any
OTHER IntegrityError (or eval exception) is LOGGED (durable evidence) — never silently swallowed as
"no breach". The truth of a limit's state is recomputed by ``limit_health`` from the latest value
(not inferred from the breach table), so a resolvable-but-unwritable breach reads BREACHED.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.limit.service import evaluate_limit, select_active_limits

_LOGGER = logging.getLogger("irp_worker.breaches")

#: The unique constraint that backstops the per-(limit, run) idempotency race. ONLY a violation of
#: THIS constraint is the benign concurrent-double-detect dedup.
_BREACH_DEDUP_CONSTRAINT = "uq_breach_limit_run"


def _is_breach_dedup(exc: IntegrityError) -> bool:
    """True only when ``exc`` is the ``(limit, run)`` unique-constraint race, NOT some other
    governed-write constraint violation (psycopg ``diag.constraint_name`` + message fallback)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    if getattr(diag, "constraint_name", None) == _BREACH_DEDUP_CONSTRAINT:
        return True
    return _BREACH_DEDUP_CONSTRAINT in str(exc)


def poll_tenant_breaches(
    session: Session, now: datetime, *, acting_tenant: str
) -> list[tuple[str, str | None]]:
    """Evaluate every ACTIVE limit for the current tenant; return ``(limit_id, breach_id | None)``.

    ``breach_id`` is non-None ONLY for a breach NEWLY recorded THIS tick (an idempotent re-hit of a
    recorded breach returns None, so a caller counting non-None gets "new breaches this
    tick", not "limits currently breached"). Discovery is ``calculation_run``-driven (MANUAL runs
    are limit-checked too).
    """
    results: list[tuple[str, str | None]] = []
    for limit in select_active_limits(session, acting_tenant=acting_tenant):
        savepoint = session.begin_nested()
        try:
            breach = evaluate_limit(session, limit, now)
            savepoint.commit()
            # non-None only for a breach newly created THIS tick (an idempotent existing breach has
            # an earlier detected_at) — so main()'s count means "new breaches this tick".
            new_id = breach.id if (breach is not None and breach.detected_at == now) else None
            results.append((limit.id, new_id))
        except IntegrityError as exc:
            savepoint.rollback()
            if _is_breach_dedup(exc):
                # A concurrent tick already recorded this (limit, run) — benign dedup.
                results.append((limit.id, None))
                continue
            # A REAL governed-write constraint violation — LOG it, do not mask as "no breach".
            _LOGGER.error(
                "breach eval hit a non-dedup IntegrityError for limit %s: %s", limit.id, exc
            )
            results.append((limit.id, None))
        except Exception as exc:  # noqa: BLE001 - fail-closed per-limit isolation
            # An isolated eval failure — LOG durable evidence; limit_health recomputes the true
            # state from the latest value, so this does NOT read as a silent green.
            savepoint.rollback()
            _LOGGER.error("breach eval failed for limit %s: %s", limit.id, exc)
            results.append((limit.id, None))
    return results
