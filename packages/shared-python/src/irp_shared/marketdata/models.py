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
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    FullReproducibleMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID, PreciseDecimal
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

#: Controlled-vocab ``factor_family`` values for P3-2 (app-side allow-list; OTHER is the catch-all).
#: FL-1 (OD-FL-1-A) adds the three FRTB broad risk classes that had no existing family — RATES,
#: CREDIT_SPREAD, COMMODITY (BCBS d457 MAR33.14, verbatim: "interest rate risk, equity risk,
#: foreign exchange risk, commodity risk and credit spread risk"). The two overlaps are ALIASED,
#: not duplicated: CURRENCY ≡ the FRTB FX class, and MARKET ≡ the FRTB equity class (by declaration
#: — revisited only if a genuine cross-asset "market" factor ever arrives). Minting canonical
#: FX/EQUITY alongside the incumbents would create two labels per concept for zero capability. The
#: Barra-style cross-sectional families (STYLE/INDUSTRY/COUNTRY/MACRO) are orthogonal to FRTB's
#: instrument-sensitivity classes and serve the RBSA estimation side — left as-is. NB: adopting the
#: FRTB *names* classifies factors; it confers NO FRTB *capital* semantics (liquidity horizons,
#: partial-ES aggregation). MAR21's standardised approach uses SEVEN classes (CSR split three ways)
#: — deliberately NOT adopted here; the five broad IMA classes are the vocabulary.
FACTOR_FAMILY_STYLE = "STYLE"
FACTOR_FAMILY_INDUSTRY = "INDUSTRY"
FACTOR_FAMILY_COUNTRY = "COUNTRY"
FACTOR_FAMILY_MACRO = "MACRO"
FACTOR_FAMILY_MARKET = "MARKET"  # ≡ the FRTB equity class (alias, by declaration)
FACTOR_FAMILY_CURRENCY = "CURRENCY"  # ≡ the FRTB FX class (alias, by declaration)
FACTOR_FAMILY_RATES = "RATES"  # FRTB interest-rate risk (FL-1)
FACTOR_FAMILY_CREDIT_SPREAD = "CREDIT_SPREAD"  # FRTB credit-spread risk (FL-1)
FACTOR_FAMILY_COMMODITY = "COMMODITY"  # FRTB commodity risk (FL-1)
FACTOR_FAMILY_OTHER = "OTHER"
FACTOR_FAMILIES = (
    FACTOR_FAMILY_STYLE,
    FACTOR_FAMILY_INDUSTRY,
    FACTOR_FAMILY_COUNTRY,
    FACTOR_FAMILY_MACRO,
    FACTOR_FAMILY_MARKET,
    FACTOR_FAMILY_CURRENCY,
    FACTOR_FAMILY_RATES,
    FACTOR_FAMILY_CREDIT_SPREAD,
    FACTOR_FAMILY_COMMODITY,
    FACTOR_FAMILY_OTHER,
)
#: The FL-1 loadings-family allow-list (OD-FL-1-E): the families a fractional factor-loading may
#: reference — every family EXCEPT the OTHER catch-all (unknown/OTHER stays fail-closed). Shared
#: verbatim by the three relaxed gates (proxy_mapping capture, proxy-weight candidates, the exposure
#: loadings binder) — a contents divergence between them would be a silent capability gap.
LOADING_FACTOR_FAMILIES = (
    FACTOR_FAMILY_CURRENCY,
    FACTOR_FAMILY_MARKET,
    FACTOR_FAMILY_RATES,
    FACTOR_FAMILY_CREDIT_SPREAD,
    FACTOR_FAMILY_COMMODITY,
    FACTOR_FAMILY_STYLE,
    FACTOR_FAMILY_INDUSTRY,
    FACTOR_FAMILY_COUNTRY,
    FACTOR_FAMILY_MACRO,
)
#: Controlled-vocab factor-return ``return_type`` (SIMPLE arithmetic v1; LOG reserved — not minted).
RETURN_TYPE_SIMPLE = "SIMPLE"
FACTOR_RETURN_TYPES = (RETURN_TYPE_SIMPLE,)
#: Controlled-vocab factor ``frequency`` (DAILY v1; WEEKLY/MONTHLY reserved — not minted).
FREQUENCY_DAILY = "DAILY"
FACTOR_FREQUENCIES = (FREQUENCY_DAILY,)

# --- benchmark time series (P2-7, ENT-052) — captured index levels + vendor-published returns ---
#: ``benchmark_level.level_type`` / ``benchmark_return.return_basis`` — WHICH published index
#: variant a captured level/return describes (extend by value — MG-01; the vendor SPX/SPXT
#: convention as separate ``benchmark`` rows also works, one type/basis value each).
LEVEL_TYPE_PRICE_RETURN = "PRICE_RETURN"
LEVEL_TYPE_TOTAL_RETURN = "TOTAL_RETURN"
LEVEL_TYPE_NET_TOTAL_RETURN = "NET_TOTAL_RETURN"
BENCHMARK_LEVEL_TYPES = (
    LEVEL_TYPE_PRICE_RETURN,
    LEVEL_TYPE_TOTAL_RETURN,
    LEVEL_TYPE_NET_TOTAL_RETURN,
)
RETURN_BASIS_PRICE = "PRICE"
RETURN_BASIS_TOTAL = "TOTAL"
RETURN_BASIS_NET_TOTAL = "NET_TOTAL"
BENCHMARK_RETURN_BASES = (RETURN_BASIS_PRICE, RETURN_BASIS_TOTAL, RETURN_BASIS_NET_TOTAL)
#: ``benchmark_return.return_type`` reuses the ENT-025 vocabulary (SIMPLE v1; LOG reserved).
BENCHMARK_RETURN_TYPES = (RETURN_TYPE_SIMPLE,)

# --- private-asset proxy mapping (PA-0, ENT-019) — captured private→public factor proxies ---
#: ``proxy_mapping.mapping_method`` — HOW the proxy weight was derived (recorded provenance, NOT a
#: computation in v1). ``MANUAL`` = a captured governance judgment call; ``PEER_GROUP`` /
#: ``REGRESSION`` reserved-by-value for later (a regression-DERIVED weight is a v2 extension). The
#: v1 weight is CAPTURED, never computed (OD-PA-0-C).
MAPPING_METHOD_MANUAL = "MANUAL"
MAPPING_METHOD_PEER_GROUP_RESERVED = "PEER_GROUP"
#: PA-3 activated REGRESSION: a promoted weight from a governed proxy-weight estimation run (must
#: cite ``source_calculation_run_id``; the analyst-mediated promotion of a model output).
MAPPING_METHOD_REGRESSION = "REGRESSION"
PROXY_MAPPING_METHODS = (MAPPING_METHOD_MANUAL, MAPPING_METHOD_REGRESSION)


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
    rate: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 12), nullable=False)
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
    price: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
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
    point_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)


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


class Benchmark(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Captured benchmark/index DEFINITION header (ENT-009, EV) — the FOURTH market-data entity.

    The index IDENTITY (code / name / family / denomination currency / methodology label). A
    slowly-changing REFERENCE-family entity (the ``corporate_action``/``instrument`` EV precedent):
    entity-versioned in place via ``record_version`` (the drift discriminator), NOT append-only, NO
    system axis (EV records valid time only). PROPRIETARY/symmetric; NEVER hybrid (per-tenant
    vendor-licensed; a shared-global benchmark *definition* would be an AD-013-R2 event, OD-P2-G).

    Audited via ``REFERENCE.CREATE``/``REFERENCE.UPDATE`` (the ENT-009 reference/definition family —
    OQ-P2-6-11 Option A; the constituent *membership* is the captured-market ``MARKET.*`` half). A
    **captured** definition (supplied to the platform), **NOT computed** — no performance, no active
    return/risk, no tracking error, no attribution, no factor model. The time-varying membership +
    weights live in the FR ``benchmark_constituent`` children. Logical identity key
    ``(tenant_id, benchmark_code, benchmark_source)``:

    - **``benchmark_code``:** the tenant's logical code (e.g. ``"SPX"``); a NOT-NULL key component.
    - **``benchmark_source``:** the vendor label (e.g. ``"SP_DJI"``); a NOT-NULL key component
      (multi-vendor coexistence — the ``price_source``/``curve_source`` precedent).
    - **``benchmark_currency``:** the captured index denomination (ISO String(3); validated via the
      hybrid-aware ``resolve_currency``). NO conversion.
    - **``benchmark_name``/``index_family``/``vendor_code``/``methodology_label``:** captured opaque
      attributes (``methodology_label`` is inert — no engine consumes it; NO identifier-resolution).
    """

    __tablename__ = "benchmark"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        # EV current-identity: one row per (tenant, code, vendor) — in-place versioned (the
        # corporate_action uq precedent; NOT a partial-WHERE — EV does not close-out rows).
        UniqueConstraint(
            "tenant_id",
            "benchmark_code",
            "benchmark_source",
            name="uq_benchmark_tenant_code_source",
        ),
    )

    benchmark_code: Mapped[str] = mapped_column(String(150), nullable=False)
    benchmark_source: Mapped[str] = mapped_column(String(150), nullable=False)
    benchmark_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    benchmark_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_family: Mapped[str | None] = mapped_column(String(150), nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Inert captured metadata — NO methodology engine consumes it (the interpolation_method
    # precedent).
    methodology_label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BenchmarkConstituent(
    PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base
):
    """Captured benchmark MEMBERSHIP + weight (ENT-009 detail, FR bitemporal) — the captured-market
    half of the benchmark entity (the ``price_point``/``curve`` FR protocol, set-grained).

    An effective-dated ``(instrument, weight)`` membership row. PROPRIETARY/symmetric; NEVER hybrid;
    **NOT append-only** (the FR protocol requires close-out UPDATEs; content-immutability
    service-enforced + tested). Captured/superseded/corrected **as a set** per
    ``(benchmark_id, effective_date)`` (a vendor publishes/restates the whole constituent set);
    audited via ``MARKET.BENCHMARK_CONSTITUENT_*`` (captured market/index data that re-versions over
    time — OQ-P2-6-11 Option A). Logical key
    ``(benchmark_id, instrument_id, effective_date)``:

    - **``benchmark_id``:** NOT-NULL FK to the ``benchmark`` definition.
    - **``instrument_id``:** NOT-NULL FK (resolved tenant-filtered via ``resolve_instrument`` — a
      mastered instrument; cross-tenant fail-closed at the service layer; the ``price_point``
      precedent).
    - **``effective_date`` (the ``curve_date``/``price_date`` precedent):** a separate immutable
      logical-key ``Date`` — the membership/reconstitution date the set is FOR — carried forward
      verbatim, never mutated, DISTINCT from the FR ``valid_from`` axis.
    - **``weight``:** the captured index weight as a canonical DECIMAL fraction (``0.05`` = 5%, NOT
      percent/bps), ``Numeric(20, 12)`` (the ``curve.point_value`` scale); a non-negative sanity
      ``RANGE [0, 1]`` v1 DQ. **Captured, NEVER computed** — no active weight / return.
    - **``constituent_currency``:** an optional captured per-name denomination (validated via
      ``resolve_currency`` when present). NO conversion.

    The promoted key columns (``effective_date``) are DB-level NOT NULL; current-head partial-unique
    ``(tenant_id, benchmark_id, instrument_id, effective_date) WHERE valid_to IS NULL AND
    system_to IS NULL``.
    """

    __tablename__ = "benchmark_constituent"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        Index(
            "uq_benchmark_constituent_current",
            "tenant_id",
            "benchmark_id",
            "instrument_id",
            "effective_date",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    benchmark_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("benchmark.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Immutable logical-key: the membership/reconstitution date the set is FOR (the curve_date
    # precedent).
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # The captured index weight as a canonical DECIMAL fraction (not %/bps); inert (NEVER computed).
    weight: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    # Optional captured per-name currency (validated via resolve_currency when present); NO
    # conversion.
    constituent_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("benchmark_constituent.id"), nullable=True
    )  # link to the superseded same-instrument row (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# NOTE: benchmark (EV) + benchmark_constituent (FR) are BOTH NOT append-only — no ORM
# before_update/before_delete guard and no irp_prevent_mutation trigger (EV mutates in place;
# FR requires close-out UPDATEs). Content immutability is binder-enforced + tested (a difference
# from curve_point).


class Factor(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Captured risk-factor DEFINITION header (ENT-025 detail, net-new canonical id, EV) — P3-2.

    The FIFTH market-data entity; the ``benchmark`` EV-definition precedent. The IDENTITY of a risk
    factor (code / vendor source / family / type / scope / frequency). A slowly-changing REFERENCE-
    family entity: entity-versioned in place via ``record_version``, NOT append-only, NO system axis
    (EV records valid time only). PROPRIETARY/symmetric; NEVER hybrid (per-tenant vendor-licensed).
    Audited via ``REFERENCE.CREATE``/``REFERENCE.UPDATE`` (the ``benchmark`` definition precedent —
    the captured *returns* are the ``MARKET.*`` half). A **captured** definition (supplied to the
    platform), **NOT computed** — no factor exposure, covariance, VaR/ES, or return computation. The
    dated returns live in the FR ``factor_return`` children. Logical identity key
    ``(tenant_id, factor_code, factor_source)``:

    - **``factor_code``:** the tenant's logical factor code (e.g. ``"MOMENTUM"``); a NOT-NULL key.
    - **``factor_source``:** the vendor label (e.g. ``"MSCI_BARRA"``); a NOT-NULL key component
      (multi-vendor coexistence — the ``benchmark_source`` precedent).
    - **``factor_family``:** a controlled-vocab family
      (STYLE/INDUSTRY/COUNTRY/MACRO/MARKET/CURRENCY/RATES/CREDIT_SPREAD/COMMODITY/OTHER; the last
      three + the CURRENCY≡FX, MARKET≡equity aliases map to FRTB's five broad risk classes — FL-1);
      ``factor_type`` is an optional captured subtype label.
    - **``currency_code``/``region``/``asset_class``:** optional captured scope (currency validated
      via the hybrid-aware ``resolve_currency`` when present). NO conversion.
    - **``frequency``:** the return frequency (``DAILY`` v1); a NOT-NULL controlled-vocab attribute.
    """

    __tablename__ = "factor"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        # EV current-identity: one row per (tenant, code, vendor) — in-place versioned (the
        # benchmark uq precedent; NOT a partial-WHERE — EV does not close-out rows).
        UniqueConstraint(
            "tenant_id", "factor_code", "factor_source", name="uq_factor_tenant_code_source"
        ),
    )

    factor_code: Mapped[str] = mapped_column(String(150), nullable=False)
    factor_source: Mapped[str] = mapped_column(String(150), nullable=False)
    factor_family: Mapped[str] = mapped_column(String(30), nullable=False)
    # Optional captured subtype label (not vocab-enforced v1 — the interpolation_method precedent).
    factor_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Optional captured denomination (validated via resolve_currency when present); NO conversion.
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    asset_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default=FREQUENCY_DAILY)
    factor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FactorReturn(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured factor RETURN observation (ENT-025, FR bitemporal) — the captured-market half; the
    ``fx_rate``/``curve``-header single-row FR protocol.

    A **captured** vendor/external factor return for a business date (a value supplied to the
    platform), **NEVER computed** — no price-derived return, no regression, no factor model, no
    exposure/covariance/VaR. PROPRIETARY/symmetric; NEVER hybrid; **NOT append-only** (the FR
    protocol requires close-out UPDATEs; content-immutability service-enforced + tested). Logical
    key ``(factor_id, return_date, return_type)``:

    - **``factor_id``:** NOT-NULL FK to the ``factor`` definition (resolved tenant-filtered).
    - **``return_date`` (the ``curve_date``/``rate_date`` precedent):** a separate immutable
      logical-key ``Date`` — the business date the return is FOR — carried forward verbatim, never
      mutated, DISTINCT from the FR ``valid_from`` axis.
    - **``return_type``:** controlled-vocab (``SIMPLE`` v1; ``LOG`` reserved); a NOT-NULL key.
    - **``return_value``:** the captured return as a canonical DECIMAL fraction (``0.01`` = 1%, NOT
      percent/bps), ``Numeric(20, 12)`` (the ``curve.point_value``/``weight`` scale); inert (NEVER
      computed). A binder-side finiteness guard rejects NaN/±Inf; a ``> -1`` economic-sanity DQ
      RANGE.

    Current-head partial-unique ``(tenant_id, factor_id, return_date, return_type) WHERE valid_to IS
    NULL AND system_to IS NULL`` — exactly one open head per factor+date+type.
    """

    __tablename__ = "factor_return"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        Index(
            "uq_factor_return_current",
            "tenant_id",
            "factor_id",
            "return_date",
            "return_type",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    factor_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("factor.id"), nullable=False, index=True
    )
    # Immutable logical-key: the business date the return is FOR (the curve_date precedent).
    return_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_type: Mapped[str] = mapped_column(String(20), nullable=False, default=RETURN_TYPE_SIMPLE)
    # The captured return as a canonical DECIMAL fraction (0.01 = 1%); inert (NEVER computed).
    return_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("factor_return.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# NOTE: factor (EV) + factor_return (FR) are BOTH NOT append-only — no ORM
# before_update/before_delete guard and no irp_prevent_mutation trigger (EV mutates in place; FR
# requires close-out UPDATEs).
# Content immutability is binder-enforced + tested (the benchmark precedent, a difference from
# curve_point).


class BenchmarkLevel(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured benchmark/index LEVEL observation (ENT-052, P2-7, FR bitemporal) — the captured
    vendor-published index level for a business date; the ``factor_return`` single-row FR protocol.

    A **captured** vendor index level (a value supplied to the platform), **NEVER computed** — no
    return calculation, no analytics, no ``calculation_run``/``model_version``/snapshot pin (an
    INPUT, not a governed derived number). Child of the existing ENT-009 ``benchmark`` EV header
    (``benchmark_id`` NOT-NULL FK). PROPRIETARY/symmetric; NEVER hybrid; **NOT append-only** (the FR
    protocol requires close-out UPDATEs; content-immutability service-enforced + tested). Logical
    key ``(benchmark_id, level_date, level_type)``:

    - **``level_date``** (the ``return_date``/``rate_date`` precedent): a separate immutable
      logical-key ``Date`` — the business date the level is FOR — carried verbatim, DISTINCT from
      the FR ``valid_from`` axis.
    - **``level_type``:** controlled-vocab (``BENCHMARK_LEVEL_TYPES``); WHICH published variant
      (price / total / net-total return index) — a NOT-NULL key so one ``benchmark`` definition can
      carry its variants without duplicating the constituent membership.
    - **``level_value``:** the captured index level, ``PreciseDecimal(20, 6)`` (the
      ``price_point.price`` money scale; a level is price-like; float53-unsafe → PreciseDecimal from
      birth). Denominated in the header's ``benchmark_currency`` (NO per-row currency). A binder
      finiteness+positivity guard rejects NaN/±Inf/≤0; a ``> 0`` DQ RANGE.

    Current-head partial-unique ``(tenant_id, benchmark_id, level_date, level_type)`` WHERE
    ``valid_to IS NULL AND system_to IS NULL``.
    """

    __tablename__ = "benchmark_level"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        Index(
            "uq_benchmark_level_current",
            "tenant_id",
            "benchmark_id",
            "level_date",
            "level_type",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    benchmark_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("benchmark.id"), nullable=False, index=True
    )
    # Immutable logical-key: the business date the level is FOR (the return_date precedent).
    level_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    level_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # The captured index level (price-like money scale); inert (NEVER computed).
    level_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("benchmark_level.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BenchmarkReturn(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured benchmark/index RETURN observation (ENT-052, P2-7, FR bitemporal) — the captured
    **vendor-published** return for a business date; the ``factor_return`` single-row FR protocol.

    **Captured vendor-published values ONLY — NEVER computed from levels** (OQ-P2-6-9; a
    level-derived return is a methodology choice needing a registered ``model_version``, DEFERRED).
    No analytics, no ``calculation_run``/``model_version``/snapshot pin. Child of the ENT-009
    ``benchmark`` EV header. PROPRIETARY/symmetric; NEVER hybrid; **NOT append-only**. Logical key
    ``(benchmark_id, return_date, return_type, return_basis)``:

    - **``return_date``:** a separate immutable logical-key ``Date`` (the ``rate_date`` precedent).
    - **``return_type``:** controlled-vocab (``BENCHMARK_RETURN_TYPES``: SIMPLE v1; LOG reserved).
    - **``return_basis``:** controlled-vocab (``BENCHMARK_RETURN_BASES``: PRICE/TOTAL/NET_TOTAL) —
      WHICH index variant the vendor return describes; a NOT-NULL key so PR/TR returns for one
      benchmark+date do not collide (captured verbatim, never guessed).
    - **``return_value``:** the captured return as a canonical DECIMAL fraction (``0.01`` = 1%, NOT
      percent/bps — the ENT-025 convention), ``PreciseDecimal(20, 12)``; inert. A binder finiteness
      guard rejects NaN/±Inf; a ``> -1`` economic-sanity DQ RANGE.

    Current-head partial-unique ``(tenant_id, benchmark_id, return_date, return_type, return_basis)
    WHERE valid_to IS NULL AND system_to IS NULL``.
    """

    __tablename__ = "benchmark_return"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        Index(
            "uq_benchmark_return_current",
            "tenant_id",
            "benchmark_id",
            "return_date",
            "return_type",
            "return_basis",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    benchmark_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("benchmark.id"), nullable=False, index=True
    )
    return_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_type: Mapped[str] = mapped_column(String(20), nullable=False, default=RETURN_TYPE_SIMPLE)
    return_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    # The captured vendor-published return as a canonical DECIMAL fraction (0.01 = 1%); inert.
    return_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    restatement_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("benchmark_return.id"), nullable=True
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# NOTE: benchmark_level + benchmark_return (both FR, ENT-052) are NOT append-only — the
# factor_return/benchmark precedent (FR requires close-out UPDATEs). Content-immutability is
# binder-enforced + tested.


class ProxyMapping(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Captured private-asset → public-risk-factor proxy weight (PA-0, **ENT-019**, FR bitemporal).

    The FIRST private-asset foundation (the differentiation-thesis destination §2.1): records that a
    PRIVATE instrument's risk behaves like a loading ``weight`` on a public ``factor`` — so a later
    governed number (PA-1, the desmoothing/proxy transform) can project the private holding onto the
    same public factor substrate the risk engines already consume. **CAPTURED, NEVER computed** — a
    governance judgment call (``mapping_method``), not a runtime regression (a regression-derived
    weight is a v2 extension, OD-PA-0-C). PROPRIETARY/symmetric RLS; NEVER hybrid; NOT append-only
    (the FR protocol requires close-out UPDATEs — a proxy weight is revisited; content-immutability
    is service-enforced + tested, the ``factor_return`` precedent).

    A **multi-row blend** per instrument (a buyout fund proxied by an equity factor + a
    credit-spread factor is normal); the weights are NOT constrained to sum to 1 (a partial proxy —
    the residual left as unmodeled private/idiosyncratic risk — is a legitimate, recorded choice,
    OD-PA-0-D). Logical key ``(private_instrument_id, factor_id)``:

    - **``private_instrument_id``:** NOT-NULL FK to the ``instrument`` head (tenant-filtered;
      a private asset is an ORDINARY instrument with a documented private ``asset_class`` convention
      — OD-PA-0-B, no new schema). **WIDENED AT FL-1: this table is now an instrument→factor
      loading mapping for PUBLIC instruments too** — the column name is a RECORDED MISNOMER for
      public rows; it keeps its name because it is a pin-serializer key (``snapshot/serialize.py``)
      and renaming it would false-drift every historical PROXY_MAPPING pin (the 0038 landmine
      class). ENT-058 ``instrument_factor_loading`` is the reserved clean-schema v2.
    - **``factor_id``:** NOT-NULL FK to the public ``factor`` definition (CURRENCY-family at PA-0;
      **FL-1 widened the capture gate to ``LOADING_FACTOR_FAMILIES``** — the FRTB + Barra families,
      OTHER/unknown still refused; resolved tenant-filtered).
    - **``weight``:** the signed factor loading, a canonical DECIMAL ``Numeric(20, 12)`` (the
      ``factor_return``/``curve`` scale; a loading, NOT currency); inert (NEVER computed). A
      service-side finiteness guard rejects NaN/±Inf.
    - **``mapping_method``:** controlled-vocab (``MANUAL`` v1; ``PEER_GROUP``/``REGRESSION``
      reserved) — HOW the weight was derived (recorded provenance).

    Current-head partial-unique ``(tenant_id, private_instrument_id, factor_id) WHERE valid_to IS
    NULL AND system_to IS NULL`` — exactly one OPEN weight per instrument+factor pair on both axes.
    """

    __tablename__ = "proxy_mapping"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        Index(
            "uq_proxy_mapping_current",
            "tenant_id",
            "private_instrument_id",
            "factor_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    private_instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    factor_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("factor.id"), nullable=False, index=True
    )
    # The signed public-factor loading (a DECIMAL, NOT currency); inert (NEVER computed).
    weight: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    mapping_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default=MAPPING_METHOD_MANUAL
    )
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("proxy_mapping.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    # PA-3 promotion evidence (OD-PA-3-E): a REGRESSION-method weight cites the estimation run it
    # came from; MANUAL captures leave it NULL. Additive (migration 0037); FK to the run.
    source_calculation_run_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=True
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# NOTE: proxy_mapping (FR, ENT-019) is NOT append-only — the factor_return precedent (FR requires
# close-out UPDATEs). Content-immutability is service-enforced + tested.
