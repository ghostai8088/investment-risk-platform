"""Corporate-action binder (ENT-008, EV; OD-P1B-B) — CAPTURE-ONLY reference data.

A thin EV binder mirroring ``reference/issuer.py`` / ``reference/instrument.py``: ``create``
resolves
the affected ``instrument`` tenant-filtered (a cross-tenant/unknown instrument fails closed) and
emits
``REFERENCE.CREATE`` + one MANUAL-source ORIGIN edge; ``update`` is an EV in-place amend
(``REFERENCE.UPDATE``); ``transition_corporate_action_status`` walks the ANNOUNCED → CONFIRMED →
CANCELLED lifecycle behind a guard and emits ``REFERENCE.STATUS_CHANGE`` (EVT-143, P1B-4). **No
application engine, no position/valuation adjustment, no entitlement/tax/roll math** — the binder
records the action only; nothing is ever applied (so "no double-apply" holds trivially).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.reference.instrument import resolve_instrument
from irp_shared.reference.models import CorporateAction
from irp_shared.reference.service import (
    ENTITY_CORPORATE_ACTION,
    ReferenceActor,
    record_reference_create,
    record_reference_status_change,
    record_reference_update,
)

#: The controlled-vocab status lifecycle (single flag; no is_active).
VALID_STATUSES = ("ANNOUNCED", "CONFIRMED", "CANCELLED")

#: Allowed status transitions (CANCELLED is terminal). A no-op or reverse move is illegal.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "ANNOUNCED": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"CANCELLED"},
    "CANCELLED": set(),
}

#: Mutable ATTRIBUTE columns ``update_corporate_action`` will diff/apply. ``code``/``instrument_id``
#: are the stable identity; ``status`` is changed ONLY via ``transition_corporate_action_status``.
_UPDATABLE = (
    "action_type",
    "announcement_date",
    "ex_date",
    "record_date",
    "pay_date",
    "effective_date",
    "ratio",
    "amount",
    "currency_code",
    "description",
    "source",
)


class CorporateActionNotVisible(Exception):
    """Raised when a ``corporate_action_id`` is not visible in the acting tenant scope."""

    def __init__(self, corporate_action_id: str) -> None:
        super().__init__(
            f"corporate_action {corporate_action_id} is not visible in the current tenant context"
        )
        self.corporate_action_id = str(corporate_action_id)


class IllegalStatusTransition(Exception):
    """Raised for an out-of-vocab status or a disallowed lifecycle move (``from_status`` is ``None``
    for an invalid status supplied on create)."""

    def __init__(self, from_status: str | None, to_status: str) -> None:
        super().__init__(f"illegal corporate_action status transition {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


def resolve_corporate_action(
    session: Session, corporate_action_id: str, *, acting_tenant: str
) -> CorporateAction:
    """Resolve a ``corporate_action`` by id with an EXPLICIT ``tenant_id == acting_tenant`` filter
    (fail-closed on SQLite AND PG). Raises :class:`CorporateActionNotVisible` on a hidden id."""
    ca = session.execute(
        select(CorporateAction).where(
            CorporateAction.id == str(corporate_action_id),
            CorporateAction.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if ca is None:
        raise CorporateActionNotVisible(str(corporate_action_id))
    return ca


def create_corporate_action(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    instrument_id: str,
    action_type: str,
    actor: ReferenceActor,
    status: str = "ANNOUNCED",
    announcement_date: date | None = None,
    ex_date: date | None = None,
    record_date: date | None = None,
    pay_date: date | None = None,
    effective_date: date | None = None,
    ratio: Decimal | None = None,
    amount: Decimal | None = None,
    currency_code: str | None = None,
    description: str | None = None,
    source: str | None = None,
) -> CorporateAction:
    """Create a ``corporate_action`` (governed: MANUAL-source lineage + ``REFERENCE.CREATE``).

    The ``instrument_id`` is resolved tenant-filtered (cross-tenant/unknown → fails closed via
    :class:`~irp_shared.reference.instrument.InstrumentNotVisible`). A caller-supplied ``status`` is
    validated against the controlled vocab (out-of-vocab → :class:`IllegalStatusTransition`)."""
    if status not in VALID_STATUSES:
        raise IllegalStatusTransition(None, status)
    resolve_instrument(session, instrument_id, acting_tenant=tenant_id)

    ca = CorporateAction(
        tenant_id=str(tenant_id),
        code=code,
        instrument_id=str(instrument_id),
        action_type=action_type,
        status=status,
        announcement_date=announcement_date,
        ex_date=ex_date,
        record_date=record_date,
        pay_date=pay_date,
        effective_date=effective_date,
        ratio=ratio,
        amount=amount,
        currency_code=currency_code,
        description=description,
        source=source,
        record_version=1,
    )
    session.add(ca)
    session.flush()
    record_reference_create(
        session,
        entity=ca,
        entity_type=ENTITY_CORPORATE_ACTION,
        after_value={
            "code": code,
            "instrument_id": ca.instrument_id,
            "action_type": action_type,
            "status": status,
            "effective_date": effective_date.isoformat() if effective_date else None,
        },
        actor=actor,
    )
    return ca


def update_corporate_action(
    session: Session,
    corporate_action: CorporateAction,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> CorporateAction:
    """Apply mutable ATTRIBUTE changes (NOT ``status`` — use the transition helper), bump
    ``record_version``, emit ``REFERENCE.UPDATE``. EV in-place supersede (one physical row)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable corporate_action attributes: {sorted(unknown)}")

    before = {key: _json_safe(getattr(corporate_action, key)) for key in changes}
    for key, value in changes.items():
        setattr(corporate_action, key, value)
    corporate_action.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=corporate_action,
        entity_type=ENTITY_CORPORATE_ACTION,
        before_value=before,
        after_value={key: _json_safe(getattr(corporate_action, key)) for key in changes},
        actor=actor,
    )
    return corporate_action


def transition_corporate_action_status(
    session: Session,
    corporate_action: CorporateAction,
    *,
    new_status: str,
    actor: ReferenceActor,
    reason: str | None = None,
) -> CorporateAction:
    """Transition the lifecycle ``status`` behind the guard (ANNOUNCED → CONFIRMED → CANCELLED;
    CANCELLED terminal), bump ``record_version``, emit ``REFERENCE.STATUS_CHANGE`` (EVT-143). A
    disallowed move raises :class:`IllegalStatusTransition` with NO DB write."""
    old_status = corporate_action.status
    if new_status not in VALID_STATUSES or new_status not in _ALLOWED_TRANSITIONS[old_status]:
        raise IllegalStatusTransition(old_status, new_status)

    corporate_action.status = new_status
    corporate_action.record_version += 1
    session.flush()
    record_reference_status_change(
        session,
        entity=corporate_action,
        entity_type=ENTITY_CORPORATE_ACTION,
        before_value={"status": old_status},
        after_value={"status": new_status},
        actor=actor,
        reason=reason,
    )
    return corporate_action


def _json_safe(value: Any) -> Any:
    """DC-2 audit metadata must be JSON-serializable: Decimal→str, date→isoformat."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
