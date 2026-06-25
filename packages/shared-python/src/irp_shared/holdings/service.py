"""As-of holdings read models (P1C-5) — read-only composition over captured FR entities.

This module COMPOSES already-shipped, tenant-predicated reads into a *set* of holdings as-of a
``(valid_at, known_at)`` point in bitemporal space. It is **read-only by construction**: it issues
**no** ``INSERT``/``UPDATE``/``DELETE``, emits **no** audit event, roots **no** lineage edge, runs
**no** data-quality check, and never calls ``session.commit()``. It defines **no** ORM entity (no
``models.py``), **no** event constants (no ``events.py``), and **no** migration — the returned rows
are plain read DTOs carrying the underlying captured columns verbatim.

What it never does (AD-017 capture-only / OD-P1C-F/G/H): NO aggregation / sum / rollup / total /
weight / count-as-measure; NO ``market_value`` or ``quantity x mark_value``; NO exposure measure;
NO ``dataset_snapshot``; NO risk / pricing / valuation model; NO market-data / price lookup; NO
position-from-transaction derivation; NO corporate-action application. Captured marks may be
attached **display-only** (opt-in, deterministic by an explicit ``valuation_date``), never as an
input to a computation.

Subtree composition reuses the bounded, cycle-safe, tenant-predicated ``resolve_descendants`` — it
**shapes the read** (which portfolios' holdings to list), it does **not** enforce ABAC scope
(anchor-not-enforce, OD-P1C-A / OD-P1C-B; portfolio-scope enforcement is deferred to P6+).

One-way imports: ``holdings -> {portfolio, position, valuation, reference, rails}``; nothing imports
``holdings`` (enforced by import-direction tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.portfolio import resolve_descendants, resolve_portfolio
from irp_shared.position import Position, reconstruct_position_as_of  # noqa: F401 (re-export aid)
from irp_shared.valuation import reconstruct_valuation_as_of


@dataclass(frozen=True)
class HoldingRow:
    """A single as-of holding — the **stored** position version, carried verbatim. No computed
    field (no market value, no exposure, no total)."""

    position_id: str
    portfolio_id: str
    instrument_id: str
    quantity: Decimal
    quantity_unit: str | None
    cost_basis: Decimal | None
    position_source: str | None
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    record_version: int


@dataclass(frozen=True)
class MarkView:
    """A **display-only** captured valuation mark for a holding (opt-in). The stored mark, never an
    input to a calculation — there is NO ``quantity x mark_value`` and NO derived measure here."""

    valuation_id: str
    valuation_date: date
    mark_value: Decimal
    currency_code: str | None
    mark_source: str | None
    price_basis: str | None


@dataclass(frozen=True)
class HoldingWithMark:
    """A holding plus its optional display-only mark (``None`` when no mark exists for the requested
    ``valuation_date``). The mark is presentation only — the holding's stored ``quantity`` and the
    mark's stored ``mark_value`` are returned side by side, never multiplied or aggregated."""

    holding: HoldingRow
    mark: MarkView | None


def _holding_row(row: Position) -> HoldingRow:
    return HoldingRow(
        position_id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        quantity=row.quantity,
        quantity_unit=row.quantity_unit,
        cost_basis=row.cost_basis,
        position_source=row.position_source,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        record_version=row.record_version,
    )


def _mark_view(row) -> MarkView:  # noqa: ANN001 - a Valuation row (display-only projection)
    return MarkView(
        valuation_id=row.id,
        valuation_date=row.valuation_date,
        mark_value=row.mark_value,
        currency_code=row.currency_code,
        mark_source=row.mark_source,
        price_basis=row.price_basis,
    )


def _holdings_query(
    *, acting_tenant: str, portfolio_ids: list[str], valid_at: datetime, known: datetime
) -> Select[tuple[Position]]:
    """The set-returning generalization of ``reconstruct_position_as_of``: the SAME half-open
    bitemporal predicate (both axes) filtered to one or more ``portfolio_id``\\ s, yielding the one
    open version per ``(portfolio, instrument)`` at the requested instants. Tenant predicate is
    carried explicitly (defense-in-depth atop RLS)."""
    return (
        select(Position)
        .where(
            Position.tenant_id == str(acting_tenant),
            Position.portfolio_id.in_(portfolio_ids),
            Position.valid_from <= valid_at,
            or_(Position.valid_to.is_(None), Position.valid_to > valid_at),
            Position.system_from <= known,
            or_(Position.system_to.is_(None), Position.system_to > known),
        )
        .order_by(Position.portfolio_id, Position.instrument_id)
    )


def reconstruct_holdings_as_of(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> list[HoldingRow]:
    """Node-level as-of holdings: the set of stored position versions true at ``valid_at``
    as-known-at ``known_at`` (defaults to now -> the current view) for the single ``portfolio_id``.
    Read-only; one row per instrument; NO aggregation, NO derived number."""
    known = known_at or utcnow()
    rows = (
        session.execute(
            _holdings_query(
                acting_tenant=acting_tenant,
                portfolio_ids=[str(portfolio_id)],
                valid_at=valid_at,
                known=known,
            )
        )
        .scalars()
        .all()
    )
    return [_holding_row(r) for r in rows]


def reconstruct_subtree_holdings_as_of(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> list[HoldingRow]:
    """Bounded-subtree as-of holdings: the holdings of ``portfolio_id`` and **all its descendants**.

    Resolves the node (``PortfolioNotVisible`` on unknown/cross-tenant -> caller maps to 404), then
    the bounded, cycle-safe, tenant-predicated descendant set (``HierarchyCycleError`` on a corrupt/
    too-deep hierarchy -> caller maps to 409), unions the node's own id (``resolve_descendants``
    excludes the root), and runs the same as-of predicate over the union. This is read COMPOSITION,
    not ABAC enforcement (OD-P1C-B): it lists what is in the subtree; it does not restrict by scope.
    """
    node = resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
    descendants = resolve_descendants(session, node, acting_tenant=acting_tenant)
    portfolio_ids = [str(node.id), *[str(d.id) for d in descendants]]
    known = known_at or utcnow()
    rows = (
        session.execute(
            _holdings_query(
                acting_tenant=acting_tenant,
                portfolio_ids=portfolio_ids,
                valid_at=valid_at,
                known=known,
            )
        )
        .scalars()
        .all()
    )
    return [_holding_row(r) for r in rows]


def attach_marks_as_of(
    session: Session,
    *,
    acting_tenant: str,
    holdings: list[HoldingRow],
    valuation_date: date,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> list[HoldingWithMark]:
    """Attach the **display-only** captured mark to each holding for an EXPLICIT ``valuation_date``
    (deterministic; no 'latest mark' selection). Looks up each mark via the shipped
    ``reconstruct_valuation_as_of`` at the same ``(valid_at, known_at)``; a holding with no mark for
    that ``valuation_date`` gets ``mark=None``. NO arithmetic — never ``quantity x mark_value``."""
    out: list[HoldingWithMark] = []
    for h in holdings:
        mark = reconstruct_valuation_as_of(
            session,
            acting_tenant=acting_tenant,
            portfolio_id=h.portfolio_id,
            instrument_id=h.instrument_id,
            valuation_date=valuation_date,
            valid_at=valid_at,
            known_at=known_at,
        )
        out.append(HoldingWithMark(holding=h, mark=_mark_view(mark) if mark is not None else None))
    return out
