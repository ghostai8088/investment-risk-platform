"""Instrument identity/master binder (ENT-001 identity, EV; OD-P1B-A).

``instrument`` is the security-master head — identity attributes only (the FR economic/legal terms
live on ``instrument_terms``). ``create_instrument`` resolves a non-null ``issuer_id`` through the
tenant-filtered ``resolve_issuer`` (a cross-tenant/unknown issuer fails closed on SQLite AND PG) and
emits its OWN ``REFERENCE.CREATE`` + one MANUAL-source ORIGIN edge. ``update_instrument`` is an EV
in-place supersede (``REFERENCE.UPDATE``; no new lineage edge). This module owns the
explicit-tenant-predicate ``resolve_instrument`` reused by the terms and identifier binders.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.reference.issuer import resolve_issuer
from irp_shared.reference.models import Instrument
from irp_shared.reference.service import (
    ENTITY_INSTRUMENT,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Mutable identity attributes ``update_instrument`` will diff/apply (``code``/``asset_class`` are
#: the stable identity keys and are not updatable).
_UPDATABLE = ("name", "instrument_type", "issuer_id", "currency_code", "is_active")


class InstrumentNotVisible(Exception):
    """Raised when an ``instrument_id`` is not visible in the acting tenant scope (cross-tenant
    hidden, or unknown) — a dependent write/resolve fails closed."""

    def __init__(self, instrument_id: str) -> None:
        super().__init__(f"instrument {instrument_id} is not visible in the current tenant context")
        self.instrument_id = str(instrument_id)


def resolve_instrument(session: Session, instrument_id: str, *, acting_tenant: str) -> Instrument:
    """Resolve an ``instrument`` by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed on SQLite AND PG). Raises :class:`InstrumentNotVisible` on a hidden/unknown id."""
    instrument = session.execute(
        select(Instrument).where(
            Instrument.id == str(instrument_id),
            Instrument.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if instrument is None:
        raise InstrumentNotVisible(str(instrument_id))
    return instrument


def create_instrument(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    asset_class: str,
    actor: ReferenceActor,
    instrument_type: str | None = None,
    issuer_id: str | None = None,
    currency_code: str | None = None,
    is_active: bool = True,
) -> Instrument:
    """Create an ``instrument`` head (governed: MANUAL-source lineage + ``REFERENCE.CREATE``).

    A non-null ``issuer_id`` is resolved tenant-filtered (cross-tenant/unknown → fails closed via
    :class:`~irp_shared.reference.issuer.IssuerNotVisible`). Instruments WITHOUT an issuer (cash/FX/
    index) are allowed (``issuer_id`` nullable)."""
    if issuer_id is not None:
        resolve_issuer(session, issuer_id, acting_tenant=tenant_id)

    instrument = Instrument(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        asset_class=asset_class,
        instrument_type=instrument_type,
        issuer_id=(str(issuer_id) if issuer_id else None),
        currency_code=currency_code,
        is_active=is_active,
        record_version=1,
    )
    session.add(instrument)
    session.flush()
    record_reference_create(
        session,
        entity=instrument,
        entity_type=ENTITY_INSTRUMENT,
        after_value={
            "code": code,
            "name": name,
            "asset_class": asset_class,
            "instrument_type": instrument_type,
            "issuer_id": instrument.issuer_id,
            "currency_code": currency_code,
            "is_active": is_active,
        },
        actor=actor,
    )
    return instrument


def update_instrument(
    session: Session,
    instrument: Instrument,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> Instrument:
    """Apply mutable identity changes, bump ``record_version``, emit ``REFERENCE.UPDATE``. A
    re-pointed ``issuer_id`` is resolved tenant-filtered (cross-tenant/unknown → fails closed)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable instrument attributes: {sorted(unknown)}")

    new_issuer = changes.get("issuer_id")
    if "issuer_id" in changes and new_issuer is not None:
        resolve_issuer(session, new_issuer, acting_tenant=instrument.tenant_id)
        changes["issuer_id"] = str(new_issuer)

    before = {key: getattr(instrument, key) for key in changes}
    for key, value in changes.items():
        setattr(instrument, key, value)
    instrument.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=instrument,
        entity_type=ENTITY_INSTRUMENT,
        before_value=before,
        after_value={key: getattr(instrument, key) for key in changes},
        actor=actor,
    )
    return instrument
