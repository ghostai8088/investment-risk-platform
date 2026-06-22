"""Currency reference binder (ENT-005, EV). Thin create/update over the governed reference core."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from irp_shared.reference.models import Currency
from irp_shared.reference.service import (
    ENTITY_CURRENCY,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Mutable attributes ``update_currency`` will diff/apply (``code`` is the stable identity key).
_UPDATABLE = ("name", "symbol", "minor_units", "numeric_code", "is_active")


def create_currency(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    actor: ReferenceActor,
    symbol: str | None = None,
    minor_units: int | None = None,
    numeric_code: str | None = None,
    is_active: bool = True,
) -> Currency:
    """Create a ``currency`` head (governed: MANUAL-source lineage + ``REFERENCE.CREATE``)."""
    currency = Currency(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        symbol=symbol,
        minor_units=minor_units,
        numeric_code=numeric_code,
        is_active=is_active,
        record_version=1,
    )
    session.add(currency)
    session.flush()
    record_reference_create(
        session,
        entity=currency,
        entity_type=ENTITY_CURRENCY,
        after_value={
            "code": code,
            "name": name,
            "is_active": is_active,
            "minor_units": minor_units,
        },
        actor=actor,
    )
    return currency


def update_currency(
    session: Session,
    currency: Currency,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> Currency:
    """Apply mutable changes (effective-dated supersede), bump ``record_version``, emit
    ``REFERENCE.UPDATE`` — same transaction; stable ``entity_id`` = row id per (tenant, code)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable currency attributes: {sorted(unknown)}")

    before = {key: getattr(currency, key) for key in changes}
    for key, value in changes.items():
        setattr(currency, key, value)
    currency.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=currency,
        entity_type=ENTITY_CURRENCY,
        before_value=before,
        after_value={key: getattr(currency, key) for key in changes},
        actor=actor,
    )
    return currency
