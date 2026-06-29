"""Market-data ORM models — ``fx_rate`` (P2-2, ENT-024, FR) + ``price_point`` (P2-4, ENT-020, FR).

Both are captured vendor market data on the FR bitemporal protocol (NOT append-only; symmetric RLS;
NEVER hybrid). ``fx_rate`` is documented first; ``price_point`` (the second member) follows the same
protocol verbatim — see its class docstring.

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
from typing import Any

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    FullReproducibleMixin,
    ImmutableAppendOnlyMixin,
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

#: Controlled-vocab ``price_type`` values for P2-4 (app-side allow-list; BID/ASK reserved — paired
#: quotes need a two-sided model, out of scope). CLOSE = exchange close; MID = OTC/quote midpoint;
#: NAV = fund net-asset-value. Single representative prices only.
PRICE_TYPE_CLOSE = "CLOSE"
PRICE_TYPE_MID = "MID"
PRICE_TYPE_NAV = "NAV"
PRICE_TYPES = (PRICE_TYPE_CLOSE, PRICE_TYPE_MID, PRICE_TYPE_NAV)

#: Controlled-vocab ``curve_type`` values for P2-5 (app-side allow-list; MUNI/BASIS/INFLATION
#: reserved). The rate/yield families (TREASURY/GOVT/SWAP/OIS) carry the sentinel ``reference_key``;
#: CREDIT_SPREAD carries an opaque issuer/rating ``reference_key`` (realizes ENT-023 by value).
CURVE_TYPE_TREASURY = "TREASURY"
CURVE_TYPE_GOVT = "GOVT"
CURVE_TYPE_SWAP = "SWAP"
CURVE_TYPE_OIS = "OIS"
CURVE_TYPE_CREDIT_SPREAD = "CREDIT_SPREAD"
CURVE_TYPES = (
    CURVE_TYPE_TREASURY,
    CURVE_TYPE_GOVT,
    CURVE_TYPE_SWAP,
    CURVE_TYPE_OIS,
    CURVE_TYPE_CREDIT_SPREAD,
)
#: The rate/yield curve_types that REQUIRE the sentinel reference_key (no reference entity).
RATE_CURVE_TYPES = (CURVE_TYPE_TREASURY, CURVE_TYPE_GOVT, CURVE_TYPE_SWAP, CURVE_TYPE_OIS)
#: The sentinel ``reference_key`` for rate curves (NOT NULL key column; the credit dimension is
#: ``"NONE"`` for non-credit curves — OD-P2-5-K).
REFERENCE_KEY_NONE = "NONE"

#: Controlled-vocab ``value_type`` values for P2-5 (what ``point_value`` MEANS; canonical decimal).
VALUE_TYPE_ZERO_RATE = "ZERO_RATE"
VALUE_TYPE_PAR_RATE = "PAR_RATE"
VALUE_TYPE_DISCOUNT_FACTOR = "DISCOUNT_FACTOR"
VALUE_TYPE_SPREAD = "SPREAD"
CURVE_VALUE_TYPES = (
    VALUE_TYPE_ZERO_RATE,
    VALUE_TYPE_PAR_RATE,
    VALUE_TYPE_DISCOUNT_FACTOR,
    VALUE_TYPE_SPREAD,
)
#: value_types whose ``point_value`` may be NEGATIVE (bounded sanity RANGE, not strictly-positive).
SIGNED_VALUE_TYPES = (VALUE_TYPE_ZERO_RATE, VALUE_TYPE_PAR_RATE, VALUE_TYPE_SPREAD)


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


class PricePoint(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured vendor security price (ENT-020, FR bitemporal) — the SECOND market-data entity, the
    ``fx_rate`` protocol verbatim. PROPRIETARY/symmetric; NEVER hybrid (per-tenant vendor-licensed,
    MNPI-adjacent); **NOT append-only** (close-out UPDATEs; content-immutability service-enforced).

    A **captured** vendor price (a value supplied to the platform), **NOT computed** — no pricing
    model, no curve-implied/interpolated price, no return, no factor, no exposure, no
    ``calculation_run``. **RAW vendor prices only** (no corporate-action adjustment — no
    ``adjustment_basis``). Logical key ``(instrument_id, price_date, price_type, currency_code,
    price_source)``:

    - **``price_date`` (the ``valuation_date``/``rate_date`` precedent):** a separate immutable
      logical-key ``Date`` — the business date the price is FOR — carried forward verbatim, never
      mutated, DISTINCT from the FR ``valid_from`` axis.
    - **``price_type`` (P2-4 OD-P2-4-E):** controlled-vocab plain String, ``{CLOSE, MID, NAV}`` v1.
    - **``currency_code``:** the captured native currency (ISO String(3); validated via
      ``resolve_currency``); a key component (a dual-listed security priced in >1 currency = >1 open
      head). **NO conversion here** (FX conversion is a later calculation via the P2-2 ``convert``).
    - **``price_source`` (OD-P2-4-C/H — the deliberate departure from inert ``rate_source``):**
      a controlled-vocab String label that **IS a key component** (multiple vendors publish a price
      for the same instrument/date/type/currency and the platform keeps them all). The governed
      provenance is a VENDOR ``data_source`` ORIGIN lineage edge.
    - **``price`` is ``Numeric(20, 6)``** — the ``valuation.mark_value`` money scale (a price IS a
      per-unit money value of the same kind as a mark).

    The promoted key columns (``price_type``/``currency_code``/``price_source``) are DB-level
    ``NOT NULL`` so the current-head partial-unique is not defeasible by a NULL key component.
    """

    __tablename__ = "price_point"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Bitemporal current-head invariant: at most one version OPEN ON BOTH axes per logical key
        # (tenant, instrument, price_date, price_type, currency_code, price_source). Non-temporal
        # key dimensions are NOT NULL; the FR axes version the price for a fixed key. Same partial
        # WHERE on both engines so migration 0019 is drift-clean.
        Index(
            "uq_price_point_current",
            "tenant_id",
            "instrument_id",
            "price_date",
            "price_type",
            "currency_code",
            "price_source",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    # NOT-NULL FK to instrument head (the corporate_action precedent; resolved tenant-filtered via
    # resolve_instrument — cross-tenant fail-closed at the service layer).
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Immutable logical-key component: the business date the price is FOR (the valuation_date
    # precedent).
    price_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # The captured price, in currency_code (money scale 6); inert (captured, NEVER computed).
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    # Controlled-vocab price-type (CLOSE/MID/NAV v1); a NOT-NULL logical-key component.
    price_type: Mapped[str] = mapped_column(String(20), nullable=False, default=PRICE_TYPE_CLOSE)
    # The captured native currency (ISO; validated via resolve_currency); a NOT-NULL key component.
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # The vendor source label (e.g. "BLOOMBERG") — a NOT-NULL KEY component (multi-vendor
    # coexistence), distinct from the governed VENDOR data_source ORIGIN lineage edge.
    price_source: Mapped[str] = mapped_column(String(150), nullable=False)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("price_point.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # logical version count (create=1; each supersede/correction = prev+1)


# NOTE: price_point is FR (NOT append-only) — like fx_rate, deliberately NO ORM
# before_update/before_delete guard and NO irp_prevent_mutation trigger; the FR protocol REQUIRES
# close-out UPDATEs. Prior-version CONTENT immutability is enforced by the binder protocol + tests.


class Curve(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured vendor yield/spread curve HEADER (ENT-021, FR bitemporal) — the THIRD market-data
    entity, the ``fx_rate``/``price_point`` protocol verbatim. PROPRIETARY/symmetric; NEVER hybrid;
    **NOT append-only** (close-out UPDATEs; content-immutability service-enforced).

    A **captured** vendor curve (values supplied to the platform), **NOT computed** — no curve
    construction, no interpolation, no bootstrapping, no discounting, no duration/key-rate, no
    pricing/valuation/return/factor/risk. The header carries the identity; the per-tenor values
    live in the version-pinned ``curve_point`` children (a re-version = a NEW header version + fresh
    node set). The logical key is ``(curve_type, currency_code, reference_key, curve_date,
    curve_source)``:

    - **``curve_type`` (OD-P2-5-F):** vocab ``{TREASURY, GOVT, SWAP, OIS, CREDIT_SPREAD}``;
      ``CREDIT_SPREAD`` realizes ENT-023 by value over the SAME tables (the genericity principle).
    - **``reference_key`` (OD-P2-5-K):** a NOT-NULL opaque String — sentinel ``"NONE"`` for rate
      curves; an opaque issuer/rating/sector label for ``CREDIT_SPREAD``. NOT an FK in v1. The
      ``curve_type`` <-> ``reference_key`` invariant is binder-enforced (rate types => ``"NONE"``;
      ``CREDIT_SPREAD`` => non-``"NONE"``).
    - **``curve_date`` (the ``price_date`` precedent):** a separate immutable logical-key
      ``Date`` — the business date the curve is FOR — carried forward verbatim, DISTINCT from the FR
      ``valid_from`` axis.
    - **``currency_code``:** the captured native currency (ISO String(3); validated via
      ``resolve_currency``); a key component. NO conversion.
    - **``curve_source``:** a controlled-vocab String label (in the key — multi-vendor coexistence);
      the governed provenance is a VENDOR (``VENDOR_CURVE``) ``data_source`` ORIGIN lineage edge.
    - **``interpolation_method``:** a nullable INERT String (OQ-P2-5-9) — captured-but-unused;
      NO interpolation engine consumes it.

    The promoted key columns (``curve_type``/``currency_code``/``reference_key``/``curve_date``/
    ``curve_source``) are DB-level ``NOT NULL`` so current-head partial-unique is not defeasible.
    """

    __tablename__ = "curve"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Bitemporal current-head invariant: at most one version OPEN ON BOTH axes per logical key.
        Index(
            "uq_curve_current",
            "tenant_id",
            "curve_type",
            "currency_code",
            "reference_key",
            "curve_date",
            "curve_source",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    curve_type: Mapped[str] = mapped_column(String(30), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # Opaque credit-spread reference dimension; sentinel "NONE" for rate curves (NOT an FK in v1).
    reference_key: Mapped[str] = mapped_column(
        String(150), nullable=False, default=REFERENCE_KEY_NONE
    )
    # Immutable logical-key: the business date the curve is FOR (the price_date precedent).
    curve_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    curve_source: Mapped[str] = mapped_column(String(150), nullable=False)
    # Inert captured metadata (OQ-P2-5-9) — NO interpolation engine; NOT in the key.
    interpolation_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The number of curve_point nodes pinned to this header version (DC-2 audit metadata).
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("curve.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CurvePoint(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """A single tenor node of a ``curve`` version (ENT-021 "Curve nodes", IA TRUE append-only).

    Immutable, **version-pinned** to ONE ``curve`` physical version via ``curve_id`` (a re-version =
    a new header + a fresh node set; nodes are never updated/deleted — the ENT-050
    ``dataset_snapshot_component`` precedent: in ``APPEND_ONLY_TABLES`` + ``irp_prevent_mutation``
    P0001 trigger + the ORM guard below). NO independent bitemporal axes (the header carries the
    as-of-ness). ``tenant_id`` is server-stamped from the parent header (defense-in-depth RLS key).
    """

    __tablename__ = "curve_point"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # One value per (curve version, value_type, normalized tenor) — keyed on tenor_days so
        # "12M"/"1Y" cannot double-insert.
        UniqueConstraint(
            "curve_id", "value_type", "tenor_days", name="uq_curve_point_curve_value_tenor"
        ),
    )

    curve_id: Mapped[str] = mapped_column(GUID, ForeignKey("curve.id"), nullable=False, index=True)
    # Canonical tenor label ({N}{D|W|M|Y}, e.g. "3M"/"10Y") + the normalized day count (the key).
    tenor_label: Mapped[str] = mapped_column(String(10), nullable=False)
    tenor_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # What point_value MEANS: ZERO_RATE/PAR_RATE/DISCOUNT_FACTOR/SPREAD (controlled-vocab).
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # The captured value as a canonical DECIMAL fraction (not %/bps); inert (NEVER computed).
    point_value: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)


def _block_curve_point_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# True append-only: the ORM guard (paired with the migration-0020 P0001 trigger) forbids
# update/delete on curve_point. A node is never mutated — a re-version is a new header + new nodes.
# NOTE: ``curve`` (the FR header) is deliberately NOT guarded (the FR protocol requires close-out
# UPDATEs to valid_to/system_to; prior-version content immutability is binder-enforced + tested).
event.listen(CurvePoint, "before_update", _block_curve_point_mutation)
event.listen(CurvePoint, "before_delete", _block_curve_point_mutation)
