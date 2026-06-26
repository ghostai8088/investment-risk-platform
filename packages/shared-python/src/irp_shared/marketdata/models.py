"""FX-rate ORM model (P2-2, ENT-024, FR) — captured vendor FX market data.

The platform's first **market-data** entity and the fourth persisted user of
``FullReproducibleMixin``
(after ``instrument_terms`` / ``position`` / ``valuation``). PROPRIETARY, tenant-scoped, **NEVER
hybrid** (symmetric RLS only, migration 0017) — vendor FX data is per-tenant licensed +
MNPI-adjacent
(AD-008/OD-P2-G); a shared-global FX set would be an AD-013-R2 governance event, out of scope. An
``fx_rate`` is a **captured** vendor rate (a value supplied to the platform), **NOT computed** —
there
is no model, no curve-implied rate, no interpolation, no exposure, no ``calculation_run`` (OD-P2-E).

FR keeps full version history in-table on BOTH axes: ``valid_from``/``valid_to`` (valid time) and
``system_from``/``system_to`` (system/knowledge time — a vendor restatement is an as-known
correction). The logical key is ``(base_currency, quote_currency, rate_date, rate_type)``:

- **Direction (QS-08):** ``rate`` means **"1 unit of ``base_currency`` = ``rate`` units of
  ``quote_currency``"** (price-of-base-in-quote). Self-describing; no inversion ambiguity. The
  reciprocal is derived at read time by ``convert`` (1/rate), NOT stored.
- **``rate_date`` (the ``valuation_date`` precedent):** a **separate immutable logical-key
``Date``** —
  the business date the rate is FOR — carried forward verbatim by supersede/correct, **never
  mutated**,
  DISTINCT from the FR ``valid_from`` axis. (If ``rate_date`` were ``valid_from``, a supersede's new
  valid period would change the date the rate is "FOR" — breaking the semantics; hence a separate
  key.)
- **``rate_type`` (QS-09):** controlled-vocab plain String, **``MID`` only in v1** (BID/ASK
reserved,
  not minted).
- **``rate`` is ``Numeric(28, 12)``** — NOT the money scale 6; FX needs >6 dp (small-unit pairs +
  read-time reciprocal/triangulation precision); fixed explicitly (QS-05; no canonical FX scale to
  inherit) so the future P2-3 snapshot pin hashes engine-independently.
- **``rate_source``** is an inert provenance LABEL (e.g. ``"ECB"``), NOT a market-data FK; the
governed
  provenance is the VENDOR ``data_source`` ORIGIN lineage edge.

Current-head partial-unique ``(tenant_id, base_currency, quote_currency, rate_date, rate_type) WHERE
valid_to IS NULL AND system_to IS NULL`` — exactly one open head per pair+date+type. The table is
**NOT** append-only (no ``irp_prevent_mutation`` trigger, no ``APPEND_ONLY_TABLES`` entry — the FR
protocol requires close-out UPDATEs); content-immutability is **service-enforced + tested**.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, text
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

#: Controlled-vocab ``rate_type`` values for P2-2 (app-side allow-list; BID/ASK reserved, not
# minted).
RATE_TYPE_MID = "MID"
FX_RATE_TYPES = (RATE_TYPE_MID,)


class FxRate(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured vendor FX rate (ENT-024, FR bitemporal). PROPRIETARY/symmetric; NOT append-only."""

    __tablename__ = "fx_rate"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Bitemporal current-head invariant: at most one version OPEN ON BOTH axes per logical key
        # (tenant, base, quote, rate_date, rate_type). rate_date + rate_type are KEY dimensions (not
        # temporal axes); the FR axes version the rate for a fixed logical key. Same partial WHERE
        # on
        # both engines so migration 0017 is drift-clean.
        Index(
            "uq_fx_rate_current",
            "tenant_id",
            "base_currency",
            "quote_currency",
            "rate_date",
            "rate_type",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    # ISO-4217 alpha-3 currency CODES (validated via the hybrid-aware resolve_currency; NOT FKs —
    # the
    # currency table is hybrid SYSTEM/tenant, and the code is the natural key, the valuation
    # precedent).
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Immutable logical-key component: the business date the rate is FOR (the valuation_date
    # precedent).
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # The captured rate, "1 base = rate quote" (QS-08); inert (captured, NEVER computed).
    # Numeric(28,12).
    rate: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    # Controlled-vocab rate-type label (MID only in v1; logical-key component).
    rate_type: Mapped[str] = mapped_column(String(20), nullable=False, default=RATE_TYPE_MID)
    # Inert provenance LABEL (e.g. "ECB" / "WMR_4PM_LON"); NOT a market-data FK (the mark_source
    # precedent).
    rate_source: Mapped[str | None] = mapped_column(String(150), nullable=True)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("fx_rate.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # logical version count (create=1; each supersede/correction = prev+1)


# NOTE: fx_rate is FR (NOT append-only) — there is deliberately NO ORM before_update/before_delete
# guard and NO irp_prevent_mutation trigger; the FR protocol REQUIRES close-out UPDATEs to
# valid_to/system_to. Prior-version CONTENT immutability is enforced by the binder protocol + tests.
