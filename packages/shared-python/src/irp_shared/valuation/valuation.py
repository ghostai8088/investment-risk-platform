"""Valuation binder (P1C-4, ENT-013) — the FR (full-reproducible / bitemporal) protocol.

Valuations are **captured marks** (OD-P1C-F) supplied to the platform, **NOT computed** by a
valuation/pricing model and **NOT derived** from positions (no ``position`` FK, no ``quantity ×
mark``
market-value rollup). The platform's third bitemporal entity, reusing the P1C-3 ``position``
protocol
verbatim. Full version history in-table on BOTH axes — ``valid_from``/``valid_to`` (valid time — the
period this mark version is effective) and ``system_from``/``system_to`` (system/knowledge time).
``valuation_date`` is a **separate immutable logical-key component** (a peer of ``instrument_id``,
the
business date the mark is FOR): it is carried forward verbatim and never mutated; the FR axes
version
the *mark* for a fixed ``valuation_date``. Three governed operations + the as-of read:

- ``create_valuation`` — the first open mark for a ``(portfolio, instrument, valuation_date)``.
- ``supersede_valuation`` — a new *valid-time* mark (re-mark) for the SAME ``valuation_date``: close
  the current head's ``valid_to`` (``VALUATION.UPDATE``), then insert a new open version
  (``VALUATION.CREATE``).
- ``correct_valuation`` — an as-known *system-time* restatement (TR-08): close the prior row's
  ``system_to`` (``VALUATION.UPDATE``), then insert a corrected version over the SAME valid period +
  same ``valuation_date`` with ``restatement_reason`` + ``supersedes_id``
  (``VALUATION.CORRECTION``).
- ``reconstruct_valuation_as_of`` — the bitemporal read (current view when ``known_at`` defaults to
  now).

Invariants (verbatim from ``position``): ONE ``now = utcnow()`` per supersede/correction;
CLOSE-FIRST
ordering (stamp + flush the prior close-out column before adding the new version); a prior version's
CONTENT columns (incl. ``valuation_date``) are NEVER mutated in place — only
``valid_to``/``system_to``.
The prior head is obtained ONLY via the tenant-predicated ``_current_open`` / ``resolve_valuation``
(never a caller-supplied id), and ``supersedes_id`` is set internally. Every resolver carries the
explicit ``tenant_id == acting_tenant`` predicate (fail-closed cross-tenant). ``mark_value`` is a
captured value (never recomputed); ``mark_source`` is an inert provenance LABEL (NOT a market-data
FK).
NO valuation/pricing model, NO price lookup, NO market-value rollup, NO position link.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.portfolio import resolve_portfolio
from irp_shared.reference.instrument import resolve_instrument
from irp_shared.valuation.models import Valuation
from irp_shared.valuation.service import (
    ValuationActor,
    record_valuation_correction,
    record_valuation_create,
    record_valuation_update,
)

#: The captured mark fields the binder accepts / carries-forward (inert — no math; ``mark_value`` is
#: required, the rest optional/nullable). ``valuation_date`` is a LOGICAL-KEY component, NOT here.
VALUATION_FIELDS = ("mark_value", "currency_code", "mark_source", "price_basis")


class NoCurrentValuation(Exception):
    """Raised when a supersede is requested but the (portfolio, instrument, valuation_date) has no
    open head."""

    def __init__(self, portfolio_id: str, instrument_id: str, valuation_date: date) -> None:
        super().__init__(
            f"valuation for portfolio {portfolio_id} / instrument {instrument_id} / "
            f"valuation_date {valuation_date} has no current (open) version to supersede"
        )
        self.portfolio_id = str(portfolio_id)
        self.instrument_id = str(instrument_id)
        self.valuation_date = valuation_date


class ValuationNotVisible(Exception):
    """Raised when a ``valuation_id`` is not visible in the acting tenant scope (cross-tenant id
    hidden, or unknown) — the dependent resolve/correct fails closed."""

    def __init__(self, valuation_id: str) -> None:
        super().__init__(f"valuation {valuation_id} is not visible in the current tenant context")
        self.valuation_id = str(valuation_id)


def _json_safe(value: Any) -> Any:
    """DC-2 audit metadata must be JSON-serializable: Decimal→str, date/datetime→isoformat."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _summary(row: Valuation, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A DC-2 valuation-summary dict (metadata only) for the audit after_value."""
    data: dict[str, Any] = {field: _json_safe(getattr(row, field)) for field in VALUATION_FIELDS}
    data["portfolio_id"] = row.portfolio_id
    data["instrument_id"] = row.instrument_id
    data["valuation_date"] = _json_safe(row.valuation_date)
    data["valid_from"] = _json_safe(row.valid_from)
    data["valid_to"] = _json_safe(row.valid_to)
    data["system_from"] = _json_safe(row.system_from)
    if extra:
        data.update(extra)
    return data


def _check_field_kwargs(fields: dict[str, Any]) -> None:
    unknown = set(fields) - set(VALUATION_FIELDS)
    if unknown:
        raise ValueError(f"non-valuation attributes: {sorted(unknown)}")


def _current_open(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    instrument_id: str,
    valuation_date: date,
) -> Valuation | None:
    """The single version OPEN ON BOTH axes for a (portfolio, instrument, valuation_date) — the
    bitemporal current head (``valid_to IS NULL AND system_to IS NULL``) — or ``None``. Tenant-
    predicated."""
    return session.execute(
        select(Valuation).where(
            Valuation.tenant_id == str(acting_tenant),
            Valuation.portfolio_id == str(portfolio_id),
            Valuation.instrument_id == str(instrument_id),
            Valuation.valuation_date == valuation_date,
            Valuation.valid_to.is_(None),
            Valuation.system_to.is_(None),
        )
    ).scalar_one_or_none()


def resolve_valuation(session: Session, valuation_id: str, *, acting_tenant: str) -> Valuation:
    """Resolve a ``valuation`` version by id with an EXPLICIT ``tenant_id == acting_tenant``
    predicate (fail-closed on SQLite + PG). Raises :class:`ValuationNotVisible` on a hidden id."""
    row = session.execute(
        select(Valuation).where(
            Valuation.id == str(valuation_id),
            Valuation.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValuationNotVisible(str(valuation_id))
    return row


def create_valuation(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    valuation_date: date,
    acting_tenant: str,
    actor: ValuationActor,
    mark_value: Decimal,
    valid_from: datetime | None = None,
    currency_code: str | None = None,
    mark_source: str | None = None,
    price_basis: str | None = None,
) -> Valuation:
    """Create the first open mark for a ``(portfolio, instrument, valuation_date)`` (governed:
    MANUAL-source ORIGIN lineage + ``VALUATION.CREATE``). ``portfolio_id`` + ``instrument_id`` are
    resolved tenant-filtered (cross-tenant/unknown → fails closed: ``PortfolioNotVisible`` /
    ``InstrumentNotVisible``). ``mark_value`` is captured, never computed."""
    resolve_portfolio(session, portfolio_id, acting_tenant=acting_tenant)
    resolve_instrument(session, instrument_id, acting_tenant=acting_tenant)
    now = utcnow()
    row = Valuation(
        tenant_id=str(acting_tenant),
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valuation_date=valuation_date,  # immutable logical-key component (NOT the valid_from axis)
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        mark_value=mark_value,
        currency_code=currency_code,
        mark_source=mark_source,
        price_basis=price_basis,
        record_version=1,
    )
    session.add(row)
    session.flush()
    record_valuation_create(session, entity=row, after_value=_summary(row), actor=actor)
    return row


def supersede_valuation(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    valuation_date: date,
    acting_tenant: str,
    actor: ValuationActor,
    effective_at: datetime,
    **new_fields: Any,
) -> Valuation:
    """Effective-dated (valid-time) re-mark for the SAME ``valuation_date``: close the head's
    ``valid_to = effective_at`` (``VALUATION.UPDATE``), then insert a new open version effective at
    ``effective_at`` (``VALUATION.CREATE`` + its own ORIGIN edge). Prior mark fields are carried
    forward and the supplied ``new_fields`` override them; ``valuation_date`` is carried verbatim.
    The
    prior head is sourced via the tenant-predicated ``_current_open`` (never a caller-supplied id);
    ``supersedes_id`` is set internally."""
    resolve_portfolio(session, portfolio_id, acting_tenant=acting_tenant)
    resolve_instrument(session, instrument_id, acting_tenant=acting_tenant)
    _check_field_kwargs(new_fields)
    prior = _current_open(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        valuation_date=valuation_date,
    )
    if prior is None:
        raise NoCurrentValuation(str(portfolio_id), str(instrument_id), valuation_date)

    now = utcnow()
    # CLOSE-FIRST: stamp + flush the prior valid_to close-out before adding the new open row.
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at
    session.flush()
    record_valuation_update(
        session,
        entity=prior,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
    )

    carried = {field: getattr(prior, field) for field in VALUATION_FIELDS}
    new = Valuation(
        tenant_id=str(acting_tenant),
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valuation_date=prior.valuation_date,  # carried verbatim (immutable logical key)
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
        **{**carried, **new_fields},
    )
    session.add(new)
    session.flush()
    record_valuation_create(session, entity=new, after_value=_summary(new), actor=actor)
    return new


def correct_valuation(
    session: Session,
    valuation_row: Valuation,
    *,
    restatement_reason: str,
    acting_tenant: str,
    actor: ValuationActor,
    **corrected: Any,
) -> Valuation:
    """As-known restatement (TR-08): close the prior row's ``system_to = now``
    then insert a corrected version over the SAME valid period + same ``valuation_date`` with
    ``restatement_reason`` + ``supersedes_id`` (``VALUATION.CORRECTION`` / EVT-182 + its own ORIGIN
    edge). The prior row's content columns are NEVER mutated — only its ``system_to`` close-out.
    ``valuation_row`` must already be tenant-resolved (via ``resolve_valuation``); the FKs are
    re-resolved fail-closed."""
    resolve_portfolio(session, valuation_row.portfolio_id, acting_tenant=acting_tenant)
    resolve_instrument(session, valuation_row.instrument_id, acting_tenant=acting_tenant)
    _check_field_kwargs(corrected)

    now = utcnow()
    # CLOSE-FIRST: stamp + flush the prior system_to close-out before adding the corrected row.
    before = {"system_to": _json_safe(valuation_row.system_to)}
    valuation_row.system_to = now
    session.flush()
    record_valuation_update(
        session,
        entity=valuation_row,
        before_value=before,
        after_value={"system_to": _json_safe(valuation_row.system_to)},
        actor=actor,
    )

    carried = {field: getattr(valuation_row, field) for field in VALUATION_FIELDS}
    corrected_row = Valuation(
        tenant_id=str(acting_tenant),
        portfolio_id=valuation_row.portfolio_id,
        instrument_id=valuation_row.instrument_id,
        valuation_date=valuation_row.valuation_date,  # carried verbatim (immutable logical key)
        valid_from=valuation_row.valid_from,  # SAME valid period (as-known correction)
        valid_to=valuation_row.valid_to,
        system_from=now,  # one `now` — equals the prior row's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=valuation_row.id,
        record_version=valuation_row.record_version + 1,
        **{**carried, **corrected},
    )
    session.add(corrected_row)
    session.flush()
    record_valuation_correction(
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
    )
    return corrected_row


def reconstruct_valuation_as_of(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    instrument_id: str,
    valuation_date: date,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> Valuation | None:
    """Bitemporal as-of read: the single mark true at ``valid_at`` as-known-at ``known_at``
    (``known_at`` defaults to now → the current view), or ``None``, for the given
    ``(portfolio, instrument, valuation_date)``. Half-open intervals on both axes; the resolver
    carries the explicit tenant predicate. Single mark only — NO aggregation / rollup / holdings
    view
    / market value (those are P1C-5 / P2)."""
    known = known_at or utcnow()
    return session.execute(
        select(Valuation).where(
            Valuation.tenant_id == str(acting_tenant),
            Valuation.portfolio_id == str(portfolio_id),
            Valuation.instrument_id == str(instrument_id),
            Valuation.valuation_date == valuation_date,
            Valuation.valid_from <= valid_at,
            or_(Valuation.valid_to.is_(None), Valuation.valid_to > valid_at),
            Valuation.system_from <= known,
            or_(Valuation.system_to.is_(None), Valuation.system_to > known),
        )
    ).scalar_one_or_none()
