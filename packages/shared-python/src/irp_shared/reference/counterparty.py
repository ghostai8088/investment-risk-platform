"""Counterparty role-profile binder (ENT-003, EV). A 1:1 profile over the ``legal_entity`` core.

Distinct from ``issuer`` (OD-P1B-D). ``create_counterparty`` resolves its core **tenant-filtered**
(fail-closed cross-tenant), stamps ``tenant_id`` from the resolved core, and emits its OWN
``REFERENCE.CREATE`` (``entity_type='counterparty'``) + one MANUAL-source ORIGIN edge. The
``UNIQUE(tenant_id, legal_entity_id)`` constraint enforces the 1:1 contract. **ZERO netting/CSA/
collateral/exposure columns** (OD-015 deferred); no exposure/credit math anywhere.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from irp_shared.reference.legal_entity import resolve_legal_entity
from irp_shared.reference.models import Counterparty
from irp_shared.reference.service import (
    ENTITY_COUNTERPARTY,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Mutable role attributes ``update_counterparty`` will diff/apply.
_UPDATABLE = ("counterparty_type", "is_active")


def create_counterparty(
    session: Session,
    *,
    tenant_id: str,
    legal_entity_id: str,
    actor: ReferenceActor,
    counterparty_type: str | None = None,
    is_active: bool = True,
) -> Counterparty:
    """Create a ``counterparty`` profile over an existing core (governed: MANUAL-source lineage +
    ``REFERENCE.CREATE``). A cross-tenant/unknown ``legal_entity_id`` fails closed."""
    core = resolve_legal_entity(session, legal_entity_id, acting_tenant=tenant_id)
    counterparty = Counterparty(
        tenant_id=core.tenant_id,  # server-stamped from the resolved core
        legal_entity_id=core.id,
        counterparty_type=counterparty_type,
        is_active=is_active,
        record_version=1,
    )
    session.add(counterparty)
    session.flush()
    record_reference_create(
        session,
        entity=counterparty,
        entity_type=ENTITY_COUNTERPARTY,
        after_value={
            "legal_entity_id": core.id,
            "counterparty_type": counterparty_type,
            "is_active": is_active,
        },
        actor=actor,
    )
    return counterparty


def update_counterparty(
    session: Session,
    counterparty: Counterparty,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> Counterparty:
    """Apply mutable role changes, bump ``record_version``, emit ``REFERENCE.UPDATE`` (same txn)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable counterparty attributes: {sorted(unknown)}")

    before = {key: getattr(counterparty, key) for key in changes}
    for key, value in changes.items():
        setattr(counterparty, key, value)
    counterparty.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=counterparty,
        entity_type=ENTITY_COUNTERPARTY,
        before_value=before,
        after_value={key: getattr(counterparty, key) for key in changes},
        actor=actor,
    )
    return counterparty
