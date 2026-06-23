"""Issuer role-profile binder (ENT-002, EV). A thin 1:1 profile over the ``legal_entity`` core.

``create_issuer`` resolves its ``legal_entity`` core tenant-filtered (fail-closed cross-tenant) and
stamps the profile's ``tenant_id`` from the resolved core, then emits its OWN ``REFERENCE.CREATE``
(``entity_type='issuer'`` — NOT folded into a legal_entity event) + one MANUAL-source ORIGIN edge.
``UNIQUE(tenant_id, legal_entity_id)`` enforces the 1:1 contract (at most one issuer profile
per legal entity per tenant). NO rating-assignment column (assignments are FR, deferred).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.reference.legal_entity import resolve_legal_entity
from irp_shared.reference.models import Issuer
from irp_shared.reference.service import (
    ENTITY_ISSUER,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Mutable role attributes ``update_issuer`` will diff/apply (legal_entity_id is the stable link).
_UPDATABLE = ("issuer_type", "sector", "is_active")


class IssuerNotVisible(Exception):
    """Raised when an ``issuer_id`` is not visible in the acting tenant scope (cross-tenant hidden,
    or unknown) — a dependent write (e.g. an ``instrument.issuer_id``) fails closed."""

    def __init__(self, issuer_id: str) -> None:
        super().__init__(f"issuer {issuer_id} is not visible in the current tenant context")
        self.issuer_id = str(issuer_id)


def resolve_issuer(session: Session, issuer_id: str, *, acting_tenant: str) -> Issuer:
    """Resolve an ``issuer`` profile by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed on SQLite AND PG, the ``resolve_legal_entity`` pattern). Raises
    :class:`IssuerNotVisible` on a hidden/unknown id."""
    issuer = session.execute(
        select(Issuer).where(
            Issuer.id == str(issuer_id),
            Issuer.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if issuer is None:
        raise IssuerNotVisible(str(issuer_id))
    return issuer


def create_issuer(
    session: Session,
    *,
    tenant_id: str,
    legal_entity_id: str,
    actor: ReferenceActor,
    issuer_type: str | None = None,
    sector: str | None = None,
    is_active: bool = True,
) -> Issuer:
    """Create an ``issuer`` profile over an existing core (governed: MANUAL-source lineage +
    ``REFERENCE.CREATE``). A cross-tenant/unknown ``legal_entity_id`` fails closed."""
    core = resolve_legal_entity(session, legal_entity_id, acting_tenant=tenant_id)
    issuer = Issuer(
        tenant_id=core.tenant_id,  # server-stamped from the resolved core (== acting tenant)
        legal_entity_id=core.id,
        issuer_type=issuer_type,
        sector=sector,
        is_active=is_active,
        record_version=1,
    )
    session.add(issuer)
    session.flush()
    record_reference_create(
        session,
        entity=issuer,
        entity_type=ENTITY_ISSUER,
        after_value={
            "legal_entity_id": core.id,
            "issuer_type": issuer_type,
            "sector": sector,
            "is_active": is_active,
        },
        actor=actor,
    )
    return issuer


def update_issuer(
    session: Session,
    issuer: Issuer,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> Issuer:
    """Apply mutable role changes, bump ``record_version``, emit ``REFERENCE.UPDATE`` (same txn)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable issuer attributes: {sorted(unknown)}")

    before = {key: getattr(issuer, key) for key in changes}
    for key, value in changes.items():
        setattr(issuer, key, value)
    issuer.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=issuer,
        entity_type=ENTITY_ISSUER,
        before_value=before,
        after_value={key: getattr(issuer, key) for key in changes},
        actor=actor,
    )
    return issuer
