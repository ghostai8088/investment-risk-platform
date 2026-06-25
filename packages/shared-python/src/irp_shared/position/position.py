"""Position binder (P1C-3, ENT-011) — the FR (full-reproducible / bitemporal) protocol.

Positions are **captured directly** (OD-P1C-E) as the authoritative as-of holdings master — NOT
derived from transactions (no ``transaction`` FK, no derivation engine). The platform's second
bitemporal entity, reusing the P1B-3 ``instrument_terms`` protocol verbatim. Full version history
in-table on BOTH axes — ``valid_from``/``valid_to`` (valid time — the business as-of period) and
``system_from``/``system_to`` (system/knowledge time). Three governed operations + the as-of read:

- ``create_position`` — the first open version for a ``(portfolio, instrument)``.
- ``supersede_position`` — a new *valid-time* version effective at ``effective_at``: close the
  current head's ``valid_to`` (``POSITION.UPDATE``), then insert a new open version
  (``POSITION.CREATE``).
- ``correct_position`` — an as-known *system-time* restatement (TR-08): close the prior row's
  ``system_to`` (``POSITION.UPDATE``), then insert a corrected version over the SAME valid period
  with
  ``restatement_reason`` + ``supersedes_id`` (``POSITION.CORRECTION`` / EVT-172).
- ``reconstruct_position_as_of`` — the bitemporal read (current view when ``known_at`` defaults to
  now).

Invariants (verbatim from ``instrument_terms``): ONE ``now = utcnow()`` per supersede/correction;
CLOSE-FIRST ordering (stamp + flush the prior close-out column before adding the new version) so the
dual-open current-head partial-unique is never transiently violated; a prior version's CONTENT
columns are NEVER mutated in place — only ``valid_to``/``system_to``. The prior head is obtained
ONLY
via the tenant-predicated ``_current_open`` / ``resolve_position`` (never a caller-supplied id), and
``supersedes_id`` is set internally. Every resolver carries the explicit ``tenant_id ==
acting_tenant``
predicate (fail-closed cross-tenant). ``valid_from`` IS the as-of date (no separate
``position_date``).
``quantity`` is signed; ``cost_basis`` is an opaque captured reference. NO market-value / exposure /
valuation / transaction-derivation math.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.portfolio import resolve_portfolio
from irp_shared.position.models import Position
from irp_shared.position.service import (
    PositionActor,
    record_position_correction,
    record_position_create,
    record_position_update,
)
from irp_shared.reference.instrument import resolve_instrument

#: The captured holding fields the binder accepts / carries-forward (inert — no math; ``quantity``
#: is signed + required, the rest optional/opaque).
POSITION_FIELDS = ("quantity", "cost_basis", "quantity_unit", "position_source")


class NoCurrentPosition(Exception):
    """Raised when a supersede is requested but the (portfolio, instrument) has no open head."""

    def __init__(self, portfolio_id: str, instrument_id: str) -> None:
        super().__init__(
            f"position for portfolio {portfolio_id} / instrument {instrument_id} "
            "has no current (open) version to supersede"
        )
        self.portfolio_id = str(portfolio_id)
        self.instrument_id = str(instrument_id)


class PositionNotVisible(Exception):
    """Raised when a ``position_id`` is not visible in the acting tenant scope (cross-tenant id
    hidden, or unknown) — the dependent resolve/correct fails closed."""

    def __init__(self, position_id: str) -> None:
        super().__init__(f"position {position_id} is not visible in the current tenant context")
        self.position_id = str(position_id)


def _json_safe(value: Any) -> Any:
    """DC-2 audit metadata must be JSON-serializable: Decimal→str, date/datetime→isoformat."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _summary(row: Position, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A DC-2 position-summary dict (metadata only) for the audit after_value."""
    data: dict[str, Any] = {field: _json_safe(getattr(row, field)) for field in POSITION_FIELDS}
    data["portfolio_id"] = row.portfolio_id
    data["instrument_id"] = row.instrument_id
    data["valid_from"] = _json_safe(row.valid_from)
    data["valid_to"] = _json_safe(row.valid_to)
    data["system_from"] = _json_safe(row.system_from)
    if extra:
        data.update(extra)
    return data


def _check_field_kwargs(fields: dict[str, Any]) -> None:
    unknown = set(fields) - set(POSITION_FIELDS)
    if unknown:
        raise ValueError(f"non-position attributes: {sorted(unknown)}")


def _current_open(
    session: Session, *, acting_tenant: str, portfolio_id: str, instrument_id: str
) -> Position | None:
    """The single version OPEN ON BOTH axes for a (portfolio, instrument) — the bitemporal current
    head (``valid_to IS NULL AND system_to IS NULL``) — or ``None``. Tenant-predicated."""
    return session.execute(
        select(Position).where(
            Position.tenant_id == str(acting_tenant),
            Position.portfolio_id == str(portfolio_id),
            Position.instrument_id == str(instrument_id),
            Position.valid_to.is_(None),
            Position.system_to.is_(None),
        )
    ).scalar_one_or_none()


def resolve_position(session: Session, position_id: str, *, acting_tenant: str) -> Position:
    """Resolve a ``position`` version by id with an EXPLICIT ``tenant_id == acting_tenant``
    predicate (fail-closed on SQLite + PG). Raises :class:`PositionNotVisible` on a hidden id."""
    row = session.execute(
        select(Position).where(
            Position.id == str(position_id),
            Position.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise PositionNotVisible(str(position_id))
    return row


def create_position(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    acting_tenant: str,
    actor: PositionActor,
    quantity: Decimal,
    valid_from: datetime | None = None,
    cost_basis: Decimal | None = None,
    quantity_unit: str | None = None,
    position_source: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Position:
    """Create the first open position version (governed: MANUAL-source ORIGIN lineage +
    ``POSITION.CREATE``). ``portfolio_id`` + ``instrument_id`` are resolved tenant-filtered
    (cross-tenant/unknown → fails closed: ``PortfolioNotVisible`` / ``InstrumentNotVisible``).

    ``entity_id``/``now`` are the **deterministic-injection seam** (keyword-only, default-None):
    when
    None (every production call site) behavior is unchanged (server `uuid4` id + wall-clock `now`);
    only the synthetic seed passes them to obtain `uuid5` ids + a fixed clock (OD-P1C6-1)."""
    resolve_portfolio(session, portfolio_id, acting_tenant=acting_tenant)
    resolve_instrument(session, instrument_id, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = Position(
        tenant_id=str(acting_tenant),
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valid_from=(valid_from or now),  # valid_from IS the as-of date (no separate position_date)
        valid_to=None,
        system_from=now,
        system_to=None,
        quantity=quantity,
        cost_basis=cost_basis,
        quantity_unit=quantity_unit,
        position_source=position_source,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id  # seam: deterministic uuid5 id (skips the `default=new_uuid`)
    session.add(row)
    session.flush()
    record_position_create(session, entity=row, after_value=_summary(row), actor=actor, now=now)
    return row


def supersede_position(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    acting_tenant: str,
    actor: PositionActor,
    effective_at: datetime,
    entity_id: str | None = None,
    now: datetime | None = None,
    **new_fields: Any,
) -> Position:
    """Effective-dated (valid-time) supersede: close the current head's ``valid_to = effective_at``
    (``POSITION.UPDATE``), then insert a new open version effective at ``effective_at``
    (``POSITION.CREATE`` + its own ORIGIN edge). Prior content columns are carried forward and the
    supplied ``new_fields`` override them. The prior head is sourced via the tenant-predicated
    ``_current_open`` (never a caller-supplied id); ``supersedes_id`` is set internally.
    ``entity_id``/``now`` are the deterministic-injection seam (default-None ⇒ prod unchanged)."""
    resolve_portfolio(session, portfolio_id, acting_tenant=acting_tenant)
    resolve_instrument(session, instrument_id, acting_tenant=acting_tenant)
    _check_field_kwargs(new_fields)
    prior = _current_open(
        session, acting_tenant=acting_tenant, portfolio_id=portfolio_id, instrument_id=instrument_id
    )
    if prior is None:
        raise NoCurrentPosition(str(portfolio_id), str(instrument_id))

    now = now or utcnow()
    # CLOSE-FIRST: stamp + flush the prior valid_to close-out before adding the new open row.
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at
    session.flush()
    record_position_update(
        session,
        entity=prior,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    carried = {field: getattr(prior, field) for field in POSITION_FIELDS}
    new = Position(
        tenant_id=str(acting_tenant),
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
        **{**carried, **new_fields},
    )
    if entity_id is not None:
        new.id = entity_id  # seam: deterministic uuid5 id for the new open version
    session.add(new)
    session.flush()
    record_position_create(session, entity=new, after_value=_summary(new), actor=actor, now=now)
    return new


def correct_position(
    session: Session,
    position_row: Position,
    *,
    restatement_reason: str,
    acting_tenant: str,
    actor: PositionActor,
    entity_id: str | None = None,
    now: datetime | None = None,
    **corrected: Any,
) -> Position:
    """As-known restatement (TR-08): close the prior row's ``system_to = now``
    then insert a corrected version over the SAME valid period with ``restatement_reason`` +
    ``supersedes_id`` (``POSITION.CORRECTION`` / EVT-172 + its own ORIGIN edge). The prior row's
    content columns are NEVER mutated — only its ``system_to`` close-out. ``position_row`` must
    already be tenant-resolved (via ``resolve_position``); the FKs are re-resolved fail-closed.
    ``entity_id``/``now`` are the deterministic-injection seam (default-None ⇒ prod unchanged)."""
    resolve_portfolio(session, position_row.portfolio_id, acting_tenant=acting_tenant)
    resolve_instrument(session, position_row.instrument_id, acting_tenant=acting_tenant)
    _check_field_kwargs(corrected)

    now = now or utcnow()
    # CLOSE-FIRST: stamp + flush the prior system_to close-out before adding the corrected row.
    before = {"system_to": _json_safe(position_row.system_to)}
    position_row.system_to = now
    session.flush()
    record_position_update(
        session,
        entity=position_row,
        before_value=before,
        after_value={"system_to": _json_safe(position_row.system_to)},
        actor=actor,
        now=now,
    )

    carried = {field: getattr(position_row, field) for field in POSITION_FIELDS}
    corrected_row = Position(
        tenant_id=str(acting_tenant),
        portfolio_id=position_row.portfolio_id,
        instrument_id=position_row.instrument_id,
        valid_from=position_row.valid_from,  # SAME valid period (as-known correction)
        valid_to=position_row.valid_to,
        system_from=now,  # one `now` — equals the prior row's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=position_row.id,
        record_version=position_row.record_version + 1,
        **{**carried, **corrected},
    )
    if entity_id is not None:
        corrected_row.id = entity_id  # seam: deterministic uuid5 id for the corrected version
    session.add(corrected_row)
    session.flush()
    record_position_correction(
        session,
        entity=corrected_row,
        restatement_reason=restatement_reason,
        after_value=_summary(
            corrected_row,
            extra={
                "restatement_reason": restatement_reason,
                "supersedes_id": corrected_row.supersedes_id,
            },
        ),
        actor=actor,
        now=now,
    )
    return corrected_row


def reconstruct_position_as_of(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    instrument_id: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> Position | None:
    """Bitemporal as-of read: the single position version true at ``valid_at`` as-known-at
    ``known_at`` (``known_at`` defaults to now → the current view), or ``None``. Half-open intervals
    on both axes; the resolver carries the explicit tenant predicate. Single position only — NO
    aggregation / rollup / holdings view (those are P1C-5)."""
    known = known_at or utcnow()
    return session.execute(
        select(Position).where(
            Position.tenant_id == str(acting_tenant),
            Position.portfolio_id == str(portfolio_id),
            Position.instrument_id == str(instrument_id),
            Position.valid_from <= valid_at,
            or_(Position.valid_to.is_(None), Position.valid_to > valid_at),
            Position.system_from <= known,
            or_(Position.system_to.is_(None), Position.system_to > known),
        )
    ).scalar_one_or_none()
