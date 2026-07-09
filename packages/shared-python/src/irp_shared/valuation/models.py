"""Valuation ORM model (P1C-4, ENT-013, FR) — the captured bitemporal mark history.

The platform's second **FR domain** entity and the third persisted user of ``FullReproducibleMixin``
(after the P1B-3 ``instrument_terms`` + the P1C-3 ``position``). PROPRIETARY, tenant-scoped, **NEVER
hybrid** (symmetric RLS only, migration 0015). A valuation is a **captured mark** (a value supplied
to the platform), **NOT computed** by a valuation/pricing model (OD-P1C-F) — there is no valuation
math, no price lookup, no source-precedence engine, and **no relationship to ``position``** (no
``position_id`` FK, no ``quantity``, no ``quantity × mark`` market-value rollup).

FR keeps full version history in-table on BOTH axes: ``valid_from``/``valid_to`` (valid time — the
period this mark version is effective) and ``system_from``/``system_to`` (system/knowledge time).
``valuation_date`` is a **separate immutable logical-key component** (OD-P1C-F) — a peer of
``instrument_id``, the business date the mark is FOR; it is carried forward verbatim by
supersede/correct and **never mutated**, and is **distinct from** the FR ``valid_from`` axis (the FR
axes version the *mark* for a fixed ``valuation_date``). Versions are written by the ``valuation``
binder protocol (create / effective-dated supersede / as-known correction); a prior version's
content
columns are **NEVER** mutated in place — only its ``valid_to``/``system_to`` close-out columns. The
table is therefore **NOT** append-only (no ``irp_prevent_mutation`` trigger, no
``APPEND_ONLY_TABLES``
entry); content-immutability is **service-enforced + tested**.

Grain = ``(portfolio_id, instrument_id, valuation_date)`` (OD-P1C-F), exactly one current-head mark
open on both axes per logical key (the partial-unique below). ``mark_value`` is the captured value,
**inert** (never recomputed); ``currency_code``/``mark_source``/``price_basis`` are nullable
captured
labels (``mark_source`` is a provenance LABEL, **not** a market-data FK). NO market_value/quantity/
exposure/position_id column.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    FullReproducibleMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass


class Valuation(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured mark (ENT-013, FR bitemporal). PROPRIETARY/symmetric; NOT append-only."""

    __tablename__ = "valuation"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Bitemporal current-head invariant: at most one version OPEN ON BOTH axes per logical key
        # (tenant, portfolio, instrument, valuation_date) — the OD-P1C-F grain. valuation_date is a
        # KEY dimension (not a temporal axis); the FR axes version the mark for a fixed
        # valuation_date. Same partial WHERE on both engines so migration 0015 is drift-clean.
        Index(
            "uq_valuation_current",
            "tenant_id",
            "portfolio_id",
            "instrument_id",
            "valuation_date",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Immutable logical-key component (OD-P1C-F): the business date the mark is FOR. A peer of
    # instrument_id, carried forward verbatim by supersede/correct; DISTINCT from the FR valid_from
    # axis (NOT reused as valuation_date). Indexed for the list/as-of filters.
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # The captured mark/value — inert (captured, NEVER recomputed; no valuation/pricing model).
    mark_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
    # Nullable captured labels (capture-not-validate). mark_source is a provenance LABEL, NOT a
    # market-data FK; price_basis is inert metadata (DIRTY/CLEAN/NAV-basis label, not a measure).
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    mark_source: Mapped[str | None] = mapped_column(String(150), nullable=True)
    price_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("valuation.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # logical version count (create=1; each supersede/correction = prev+1)


# NOTE: valuation is FR (NOT append-only) — there is deliberately NO ORM before_update/before_delete
# guard and NO irp_prevent_mutation trigger; the FR protocol REQUIRES close-out UPDATEs to
# valid_to/system_to. Prior-version CONTENT immutability is enforced by the binder protocol + tests.
