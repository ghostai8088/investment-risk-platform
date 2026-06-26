"""Snapshot audit-event constants + caller-side emission (P2-1, SNAPSHOT category, EVT-190 block).

``SNAPSHOT.CREATE`` is a caller-side constant emitted through the **FROZEN** ``record_event`` (the
PORTFOLIO/TRANSACTION/POSITION/VALUATION activation precedent); ``audit/service.py`` is UNTOUCHED.
One event per snapshot create; DC-2 metadata only (``component_count``, ``manifest_hash``, cutoffs —
never the captured payloads). No event on read/verify (OD-023 no-emit-on-read). Per-tenant chain.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.snapshot.models import DatasetSnapshot

#: SNAPSHOT audit category (EVT-190 block; R-07-reserved in the P2 governance ratification).
SNAPSHOT_CREATE_EVENT = "SNAPSHOT.CREATE"


@dataclass(frozen=True)
class SnapshotActor:
    """Who is creating the snapshot (the maker; deny-by-default ``snapshot.create``)."""

    actor_id: str
    actor_type: str = "user"


def record_snapshot_create(
    session: Session,
    *,
    header: DatasetSnapshot,
    actor: SnapshotActor,
) -> None:
    """Emit one ``SNAPSHOT.CREATE`` audit event (DC-2 metadata only) co-transactionally."""
    record_event(
        session,
        event_type=SNAPSHOT_CREATE_EVENT,
        tenant_id=header.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module="snapshot",
        entity_type="dataset_snapshot",
        entity_id=header.id,
        action="create",
        after_value={
            "component_count": header.component_count,
            "manifest_hash": header.manifest_hash,
            "purpose": header.purpose,
            "as_of_valid_at": header.as_of_valid_at.isoformat(),
            "as_of_known_at": header.as_of_known_at.isoformat(),
            "as_of_valuation_date": header.as_of_valuation_date.isoformat(),
            "binding_predicate_version": header.binding_predicate_version,
        },
    )
