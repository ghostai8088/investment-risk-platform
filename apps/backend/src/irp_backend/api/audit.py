"""API-1 F2 — the read-only audit-trail endpoint.

Gated ``lineage.view`` (RATIFIED reuse — no new R-07 mint; the holder set includes makers, an
accepted within-tenant consequence recorded in the API-1 decision record OD-API-1-C). The FROZEN
``audit/service.py`` is untouched — this router reads via ``audit/queries.py``. Responses are
METADATA-ONLY (the chain + descriptive fields; the before/after/justification payload bodies are NOT
surfaced here), tenant-RLS-scoped, and paginated.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.audit.models import AuditEvent
from irp_shared.audit.queries import list_audit_events
from irp_shared.entitlement.service import Principal

router = APIRouter(prefix="/audit", tags=["audit"])

#: Deny-by-default gate (built once). Reuse of ``lineage.view`` — see the module docstring.
_require_audit_view = require_permission("lineage.view")


class AuditEventOut(BaseModel):
    """Metadata-only projection of an ``audit_event`` — the chain identity, the who/what/when, the
    outcome/severity, and the tamper-evidence hash. NO payload bodies."""

    id: str
    chain_id: str
    sequence_no: int
    event_time: str  # canonical UTC ISO-8601
    event_type: str
    actor_type: str
    actor_id: str
    on_behalf_of: str | None
    source_module: str
    entity_type: str | None
    entity_id: str | None
    action: str
    outcome: str
    severity: str
    data_classification: str
    correlation_id: str | None
    event_hash: str


def _event_out(ev: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=ev.id,
        chain_id=ev.chain_id,
        sequence_no=ev.sequence_no,
        event_time=ev.event_time,
        event_type=ev.event_type,
        actor_type=ev.actor_type,
        actor_id=ev.actor_id,
        on_behalf_of=ev.on_behalf_of,
        source_module=ev.source_module,
        entity_type=ev.entity_type,
        entity_id=ev.entity_id,
        action=ev.action,
        outcome=ev.outcome,
        severity=ev.severity,
        data_classification=ev.data_classification,
        correlation_id=ev.correlation_id,
        event_hash=ev.event_hash,
    )


@router.get("/events", response_model=list[AuditEventOut])
def list_audit_events_endpoint(
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(_require_audit_view),
    db: Session = Depends(get_tenant_session),
) -> list[AuditEventOut]:
    """The acting tenant's audit trail (metadata-only), newest-first, filtered + paginated. Gated
    ``lineage.view``; silent-empty; NEVER exposes another tenant's events (tenant RLS + an explicit
    tenant predicate). Read-only — the frozen append-only writer is untouched."""
    rows = list_audit_events(
        db,
        acting_tenant=principal.tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return [_event_out(r) for r in rows]
