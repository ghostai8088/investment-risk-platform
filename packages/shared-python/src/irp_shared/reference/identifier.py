"""Identifier cross-reference binder + deterministic resolver (ENT-004, EV; OD-P1B-G).

``identifier_xref`` uses a POLYMORPHIC ``(entity_type, entity_id)`` reference; P1B-3 writes only
``entity_type='instrument'``. ``create_identifier_xref`` resolves the target instrument
tenant-filtered (a cross-tenant/unknown instrument fails closed) and emits ``REFERENCE.CREATE`` +
one MANUAL-source ORIGIN edge. ``resolve_identifier`` is the OD-P1B-G contract: **exactly one**
instrument, or ``None`` (unknown), or a typed :class:`AmbiguousIdentifier` (multiple distinct
targets) — **never a silent arbitrary match**. Cross-vendor precedence ranking is DEFERRED
(OD-012 → P1C); ``source`` is a provenance hint only. No external validation; value hygiene is trim.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.reference.instrument import InstrumentNotVisible, resolve_instrument
from irp_shared.reference.models import IdentifierXref, Instrument
from irp_shared.reference.service import (
    ENTITY_IDENTIFIER_XREF,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: The only ``entity_type`` written in P1B-3 (scope fence; entity-identifier resolution deferred).
ENTITY_TYPE_INSTRUMENT = "instrument"

#: Mutable EV attributes ``update_identifier_xref`` will diff/apply.
_UPDATABLE = ("source", "is_active")


class AmbiguousIdentifier(Exception):
    """Raised by :func:`resolve_identifier` when a ``(scheme, value)`` matches MORE THAN ONE
    distinct instrument as-of the resolution time — the deterministic contract returns this typed
    error rather than silently picking one (OD-P1B-G / CTRL-029)."""

    def __init__(self, scheme: str, value: str, matched_entity_ids: list[str]) -> None:
        super().__init__(
            f"identifier {scheme}:{value} is ambiguous "
            f"({len(matched_entity_ids)} matching instruments)"
        )
        self.scheme = scheme
        self.value = value
        self.matched_entity_ids = matched_entity_ids


def create_identifier_xref(
    session: Session,
    *,
    tenant_id: str,
    instrument_id: str,
    scheme: str,
    value: str,
    actor: ReferenceActor,
    source: str | None = None,
    valid_from: datetime | None = None,
    is_active: bool = True,
) -> IdentifierXref:
    """Create an ``identifier_xref`` for an instrument (governed: MANUAL-source lineage +
    ``REFERENCE.CREATE``). ``entity_type`` is forced to ``'instrument'``; ``instrument_id`` is
    resolved
    tenant-filtered (cross-tenant/unknown →
    :class:`~irp_shared.reference.instrument.InstrumentNotVisible`).
    The active partial-unique ``(tenant_id, scheme, value) WHERE valid_to IS NULL`` enforces at most
    one active row per identifier (a duplicate raises ``IntegrityError``)."""
    instrument = resolve_instrument(session, instrument_id, acting_tenant=tenant_id)
    now = utcnow()
    xref = IdentifierXref(
        tenant_id=instrument.tenant_id,  # server-stamped from the resolved instrument (== acting)
        entity_type=ENTITY_TYPE_INSTRUMENT,
        entity_id=instrument.id,
        scheme=scheme,
        value=value.strip(),
        source=source,
        valid_from=(valid_from or now),
        valid_to=None,
        is_active=is_active,
        record_version=1,
    )
    session.add(xref)
    session.flush()
    record_reference_create(
        session,
        entity=xref,
        entity_type=ENTITY_IDENTIFIER_XREF,
        after_value={
            "entity_type": xref.entity_type,
            "entity_id": xref.entity_id,
            "scheme": scheme,
            "value": xref.value,
            "source": source,
            "is_active": is_active,
        },
        actor=actor,
    )
    return xref


def resolve_identifier(
    session: Session,
    *,
    scheme: str,
    value: str,
    acting_tenant: str,
    as_of: datetime | None = None,
) -> Instrument | None:
    """Resolve a ``(scheme, value)`` to exactly one instrument as-of ``as_of`` (defaults to now),
    tenant-scoped. Returns ``None`` if nothing matches; raises :class:`AmbiguousIdentifier` if more
    than one distinct instrument matches (never a silent arbitrary pick). A matched-but-not-visible
    target (retired/cross-tenant) fails closed to ``None``."""
    asof = as_of or utcnow()
    rows = (
        session.execute(
            select(IdentifierXref).where(
                IdentifierXref.tenant_id == str(acting_tenant),
                IdentifierXref.entity_type == ENTITY_TYPE_INSTRUMENT,
                IdentifierXref.scheme == scheme,
                IdentifierXref.value == value.strip(),
                IdentifierXref.valid_from <= asof,
                or_(IdentifierXref.valid_to.is_(None), IdentifierXref.valid_to > asof),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    entity_ids = sorted({str(row.entity_id) for row in rows})
    if len(entity_ids) > 1:
        raise AmbiguousIdentifier(scheme, value, entity_ids)
    try:
        return resolve_instrument(session, entity_ids[0], acting_tenant=acting_tenant)
    except InstrumentNotVisible:
        return None  # target not visible (retired/cross-tenant) -> fail closed


def update_identifier_xref(
    session: Session,
    xref: IdentifierXref,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> IdentifierXref:
    """Apply mutable changes (``source`` / ``is_active``), bump ``record_version``, emit
    ``REFERENCE.UPDATE`` (no new lineage edge — the EV row keeps its origin edge)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable identifier_xref attributes: {sorted(unknown)}")

    before = {key: getattr(xref, key) for key in changes}
    for key, value in changes.items():
        setattr(xref, key, value)
    xref.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=xref,
        entity_type=ENTITY_IDENTIFIER_XREF,
        before_value=before,
        after_value={key: getattr(xref, key) for key in changes},
        actor=actor,
    )
    return xref
