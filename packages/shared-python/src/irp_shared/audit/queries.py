"""Read-only queries over the audit trail (API-1 F2).

SEPARATE from the FROZEN ``audit/service.py`` (the append-only writer + hash-chain verifier): this
module NEVER writes and NEVER imports that service. Reads are metadata-only (``audit_event``
payloads are DC-2 metadata by construction — no bulk proprietary data, no secrets), tenant-scoped
(the caller's RLS-FORCE session PLUS an explicit tenant predicate — belt-and-suspenders, fail-closed
on SQLite too), and paginated. Ordering is newest-first by canonical ``event_time`` — a fixed-width
UTC ISO-8601 string (``astimezone(UTC).isoformat()``), so lexicographic order IS chronological —
id-tie-broken for determinism.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent


def _iso(dt: datetime) -> str:
    """Canonicalize a bound to the writer's ``event_time`` form so a string ``>=``/``<=`` compares
    chronologically against the stored column (same format = lexicographic order is time order).
    Mirrors the FROZEN writer's ``_iso`` naive-guard EXACTLY (``audit/service.py``): a tz-naive
    bound is treated as ALREADY UTC — NOT as local time. Without this, an offset-less ISO bound
    (which FastAPI parses to a naive ``datetime``) would be shifted by the server's local UTC offset
    before comparison, silently narrowing/widening the ``since``/``until`` window off-UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def list_audit_events(
    session: Session,
    *,
    acting_tenant: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    """The acting tenant's audit events, newest-first, with optional metadata filters + an inclusive
    ``[since, until]`` canonical-time window. ``limit``/``offset`` paginate (the endpoint bounds
    them). Silent-empty on no match. READ-ONLY — never mutates, never touches the frozen writer."""
    stmt = select(AuditEvent).where(AuditEvent.tenant_id == str(acting_tenant))
    if entity_type is not None:
        stmt = stmt.where(AuditEvent.entity_type == str(entity_type))
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == str(entity_id))
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == str(event_type))
    if since is not None:
        stmt = stmt.where(AuditEvent.event_time >= _iso(since))
    if until is not None:
        stmt = stmt.where(AuditEvent.event_time <= _iso(until))
    stmt = (
        stmt.order_by(AuditEvent.event_time.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())
