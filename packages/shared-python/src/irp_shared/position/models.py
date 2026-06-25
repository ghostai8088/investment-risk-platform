"""Position ORM model (P1C-3, ENT-011, FR) — the captured bitemporal holdings master.

The platform's first **FR domain** entity and the second persisted user of ``FullReproducibleMixin``
(after the P1B-3 ``instrument_terms``). PROPRIETARY, tenant-scoped, **NEVER hybrid** (symmetric RLS
only, migration 0014). A position is **captured directly** (an authoritative as-of holding supplied
to the platform), **NOT derived** from the transaction log (OD-P1C-E) — there is no ``transaction``
FK and no derivation engine.

FR keeps full version history in-table on BOTH axes: ``valid_from``/``valid_to`` (valid time — the
business as-of period) and ``system_from``/``system_to`` (system/knowledge time). Versions are
written by the ``position`` binder protocol (create / effective-dated supersede / as-known
correction); a prior version's content columns are **NEVER** mutated in place — only its
``valid_to``/``system_to`` close-out columns. The table is therefore **NOT** append-only (no
``irp_prevent_mutation`` trigger, no ``APPEND_ONLY_TABLES`` entry — the close-out UPDATEs require
it);
content-immutability is **service-enforced + tested** (the FR contrast with the IA ``transaction``).

Grain = aggregated by ``(portfolio_id, instrument_id)`` (OD-P1C-D), one current-head version open on
both axes per logical key (the partial-unique below). ``quantity`` is **signed** (long > 0, short <
0) and inert (captured, never recomputed); ``cost_basis`` is an **opaque captured reference** value
only (never recomputed; not a market value). NO market_value/price/exposure/valuation column; NO
``transaction_id``/lot column.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    FullReproducibleMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class Position(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured holding (ENT-011, FR bitemporal). PROPRIETARY/symmetric; NOT append-only."""

    __tablename__ = "position"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Bitemporal current-head invariant: at most one version OPEN ON BOTH axes per logical key
        # (tenant, portfolio, instrument) — the OD-P1C-D aggregated grain. As-of correctness comes
        # from the binder's query predicate, not this index. Same partial WHERE on both engines so
        # migration 0014 is drift-clean (the instrument_terms precedent).
        Index(
            "uq_position_current",
            "tenant_id",
            "portfolio_id",
            "instrument_id",
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
    # Signed holding (long > 0, short < 0) — the grain measure; captured, NEVER recomputed (no
    # calc).
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    # Opaque captured reference value only (OD-P1C-3) — never recomputed; NOT a market value.
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    # Controlled-vocab plain string (SHARES/UNITS/PAR/...); extend by value (MG-01).
    quantity_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position_source: Mapped[str | None] = mapped_column(String(150), nullable=True)  # provenance
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("position.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # logical version count (create=1; each supersede/correction = prev+1)


# NOTE: position is FR (NOT append-only) — there is deliberately NO ORM before_update/before_delete
# guard and NO irp_prevent_mutation trigger; the FR protocol REQUIRES close-out UPDATEs to
# valid_to/system_to. Prior-version CONTENT immutability is enforced by the binder protocol + tests.
