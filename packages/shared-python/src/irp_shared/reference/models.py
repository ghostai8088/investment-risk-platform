"""Reference-data ORM models (P1B-1, REQ-SMR-005 + REQ-SMR-004 calendar partial).

Five effective-dated (EV) reference vocabularies — ``currency`` (ENT-005), ``calendar`` (ENT-006)
+ ``calendar_holiday``, and ``rating_scale`` (ENT-007 taxonomy only) + ``rating_grade``. All five
are in the closed hybrid set (AD-013-R1): a global row carries ``tenant_id = SYSTEM_TENANT_ID`` and
is readable by every tenant, while a tenant override carries the tenant's own ``tenant_id``; the two
coexist under ``UNIQUE(tenant_id, code)``. The hybrid behaviour itself lives in the **asymmetric RLS
policy** (migration 0008) — there is no ``UNIQUE(code)`` (it would collapse the override pattern)
and **no** override-merge logic in the model. "Tenant override wins" is an application-layer read
dedup in ``reference.service``, never an RLS or schema concern.

All five are EV-mutable: none is append-only — no ``irp_prevent_mutation`` trigger, no ORM guard,
no ``APPEND_ONLY_TABLES`` entry. A ``REFERENCE.UPDATE`` must succeed at the DB. Open-vocabulary
attributes (``agency`` / ``mic`` / ``recurrence`` / ``numeric_code``) are plain ``String`` columns —
no enum, no CHECK, no lookup table — so new values are data, not migrations (the MG-01 genericity
rule). ``rating_scale`` / ``rating_grade`` are taxonomy **only**: zero assignment columns (no
``instrument_id`` / ``issuer_id`` / ``rated_entity`` / ``as_of`` / ``outlook`` / ``watch``) — rating
ASSIGNMENTS are FR and deferred to the credit phase (scope fence).

P1B-2 (REQ-SMR-002) adds three PROPRIETARY, NEVER-hybrid EV entities — ``legal_entity``
(an implementation-only shared core, no ENT id — OD-P1B-D) + the separate 1:1 role profiles
``issuer`` (ENT-002) and ``counterparty`` (ENT-003). Unlike the five above they are NOT hybrid;
they use the symmetric tenant-isolation loop (``USING == WITH CHECK == own-tenant``) and carry no
SYSTEM_TENANT rows (OD-P1B-C: a firm's issuers/counterparties are MNPI-adjacent). The hierarchy is
on the core (``parent_legal_entity_id`` self-FK); the exposure-rollup calc is deferred — and
``counterparty`` carries NO netting/CSA/collateral/exposure column (OD-015 deferred).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    FullReproducibleMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Table names of the closed hybrid set (mirrors ``HYBRID_TABLES`` in migration 0008). Kept here as
#: the single ORM-side source of truth for scope-fence/closed-set tests (proprietary never hybrid).
HYBRID_TABLES: tuple[str, ...] = (
    "currency",
    "calendar",
    "calendar_holiday",
    "rating_scale",
    "rating_grade",
)


class Currency(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """ISO-4217 currency vocabulary (ENT-005, EV). Head, no child. Hybrid (AD-013-R1)."""

    __tablename__ = "currency"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_currency_tenant_code"),)

    code: Mapped[str] = mapped_column(
        String(3), nullable=False
    )  # ISO-4217 alpha-3 (CTRL-004 shape)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(8), nullable=True)
    minor_units: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 2=USD, 0=JPY (DM-N-04)
    numeric_code: Mapped[str | None] = mapped_column(String(3), nullable=True)  # ISO-4217 numeric
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # EV system-time versioning aspect (EffectiveDatedMixin omits it); canonical §4 common column.
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Calendar(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Business / holiday calendar vocabulary (ENT-006, EV). Head; owns ``calendar_holiday``."""

    __tablename__ = "calendar"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_calendar_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mic: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # ISO-10383 MIC, plain string
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CalendarHoliday(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A single holiday of a ``calendar`` (EV-mutable child, NOT append-only). Hybrid (own policy).

    ``tenant_id`` is server-stamped from the RLS-resolved parent (the ``register_model_version``
    precedent). ``recurrence`` is a stored controlled-vocab tag only — there is **no**
    recurrence-expansion / roll / day-count logic in P1B-1 (deferred to P1C+)."""

    __tablename__ = "calendar_holiday"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "calendar_id", "holiday_date", name="uq_calendar_holiday_calendar_date"
        ),
    )

    calendar_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calendar.id"), nullable=False, index=True
    )
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)  # first Date column (DM-N-05)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(20), nullable=True)  # stored tag only
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class RatingScale(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Credit-rating SCALE taxonomy (ENT-007, EV, taxonomy only). Head; owns ``rating_grade``.

    ZERO assignment columns — no ``instrument_id`` / ``issuer_id`` / ``rated_entity`` / ``as_of`` /
    ``outlook`` / ``watch``. Rating ASSIGNMENTS are FR and deferred (scope fence)."""

    __tablename__ = "rating_scale"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_rating_scale_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agency: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # SP/MOODYS/... plain str
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class RatingGrade(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A single grade of a ``rating_scale`` (EV child, not append-only). Hybrid (own policy).

    Only parent FK is ``rating_scale_id`` — NO rated-entity FK (scope fence). ``rank`` is ordinal
    (lower = stronger by convention; enforced only by ``uq_rating_grade_scale_rank``)."""

    __tablename__ = "rating_grade"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "rating_scale_id", "code", name="uq_rating_grade_scale_code"),
        UniqueConstraint("tenant_id", "rating_scale_id", "rank", name="uq_rating_grade_scale_rank"),
    )

    rating_scale_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("rating_scale.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)  # grade symbol AAA/Aaa/BBB-
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # ordinal (deterministic ordering)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# --- P1B-2: legal_entity core + issuer/counterparty role profiles (PROPRIETARY, NEVER hybrid) ---


class LegalEntity(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Implementation-only shared identity core (OD-P1B-D) — NO canonical ENT id; a normalization of
    shared LEI/name/hierarchy that ``issuer`` (ENT-002) + ``counterparty`` (ENT-003) reference 1:1.

    PROPRIETARY, tenant-scoped, NEVER hybrid (symmetric RLS). One physical row per logical entity
    (in-place EV supersede; history via the ``REFERENCE.UPDATE`` audit). ``parent_legal_entity_id``
    is an **intra-tenant** self-FK adjacency hook (the hierarchy structure); the exposure-rollup
    *calculation* is deferred — NO stored ``ultimate_parent_id`` / rollup / exposure column.
    Open-vocab attributes (``entity_type``, ``jurisdiction``) are plain Strings (MG-01)."""

    __tablename__ = "legal_entity"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_legal_entity_tenant_code"),
        # LEI unique per tenant WHEN PRESENT (Postgres partial; nullable so unidentified entities
        # are allowed). On SQLite a plain unique index, but NULL leis are distinct there too, so the
        # behaviour matches. alembic check stays drift-clean because migration 0009 emits the same.
        Index(
            "uq_legal_entity_tenant_lei",
            "tenant_id",
            "lei",
            unique=True,
            postgresql_where=text("lei IS NOT NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(150), nullable=False)  # firm-assigned LE code
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lei: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # ISO-17442; plain str, no FK
    jurisdiction: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO-3166 domicile
    entity_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # CORP/BANK/... plain
    # Intra-tenant self-FK adjacency (hierarchy hook). NULL = a root. Self-parent rejected in the
    # service. NO traversal/rollup logic in the model (deferred); the resolver lives in the binder.
    parent_legal_entity_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("legal_entity.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Issuer(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Issuer role/profile (ENT-002, EV) — a thin 1:1 profile over ``legal_entity`` holding ONLY
    role-specific attributes (NO code/lei/name/jurisdiction/hierarchy — those are on the
    core). PROPRIETARY, NEVER hybrid. ``UNIQUE(tenant_id, legal_entity_id)`` = the 1:1
    contract. NO rating-assignment column (assignments are FR, deferred)."""

    __tablename__ = "issuer"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "legal_entity_id", name="uq_issuer_tenant_legal_entity"),
    )

    legal_entity_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("legal_entity.id"), nullable=False, index=True
    )
    issuer_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # CORPORATE/SOVEREIGN/...
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Role-level activation (independent of the core's is_active; flip rides on REFERENCE.UPDATE).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Counterparty(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Counterparty role/profile (ENT-003, EV) — a 1:1 profile over ``legal_entity``, distinct from
    ``issuer`` (OD-P1B-D). PROPRIETARY, NEVER hybrid. ``UNIQUE(tenant_id, legal_entity_id)``
    = the 1:1 contract. ZERO netting/CSA/collateral/exposure columns (OD-015 deferred to P1C)."""

    __tablename__ = "counterparty"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "legal_entity_id", name="uq_counterparty_tenant_legal_entity"
        ),
    )

    legal_entity_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("legal_entity.id"), nullable=False, index=True
    )
    counterparty_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # BANK/BROKER/CCP/...
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# --- P1B-3: instrument (EV identity) + instrument_terms (FR) + identifier_xref (EV) ---
# All three are PROPRIETARY, tenant-scoped, NEVER hybrid (symmetric RLS, migration 0010).


class Instrument(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Security-master identity / head (ENT-001 identity, EV; OD-P1B-A split).

    Identity/master attributes ONLY — the FR economic/legal terms live on ``instrument_terms``.
    ``issuer_id`` is a NULLABLE intra-tenant FK to the ``issuer`` PROFILE (cash/FX/index carry no
    issuer); a non-null value is resolved tenant-filtered (fail-closed cross-tenant). ``is_active``
    is the SINGLE lifecycle flag (no ``status`` string); the EV active window (``valid_to IS NULL``)
    is the resolution predicate and the flip rides on ``REFERENCE.UPDATE``. ``currency_code`` is a
    plain ISO-4217 string (NOT a FK to the HYBRID ``currency`` table — avoids proprietary→hybrid
    coupling, the ``legal_entity.lei`` precedent). NO price/valuation/holding/risk/terms column."""

    __tablename__ = "instrument"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_instrument_tenant_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)  # firm-assigned instrument key
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # EQUITY/BOND/FX/CASH/... plain
    instrument_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # GOVT_BOND/... plain
    issuer_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("issuer.id"), nullable=True, index=True
    )  # nullable; intra-tenant; resolved tenant-filtered
    currency_code: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )  # ISO-4217 plain str, no FK
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InstrumentTerms(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """Effective-dated economic/legal terms (ENT-001 terms, **FR** — the platform's FIRST real
    bitemporal entity; OD-P1B-A / AD-005 §2A).

    FR keeps full version history in-table on BOTH axes: ``valid_from/valid_to`` (valid time, TR-01)
    and ``system_from/system_to`` (system/knowledge time, TR-02). Versions are written by the
    ``instrument_terms`` binder protocol (create / effective-dated supersede / as-known correction);
    a prior version's economic columns are NEVER mutated in place — only its
    ``valid_to``/``system_to``
    close-out columns. The table is therefore **NOT** append-only (no ``irp_prevent_mutation``
    trigger,
    no ``APPEND_ONLY_TABLES`` entry); content-immutability is service-enforced + tested.
    ``supersedes_id``
    links to the superseded version (TR-08, set on both supersede and correction);
    ``restatement_reason``
    is set ONLY on a correction. Economic columns are inert placeholder strings/numerics — NO
    pricing,
    cashflow, day-count, or valuation math in this slice."""

    __tablename__ = "instrument_terms"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Bitemporal current-head invariant: at most one version OPEN ON BOTH axes per instrument.
        # Correctness of as-of reconstruction comes from the binder's query predicate, NOT this
        # index.
        # SQLite supports partial indexes with WHERE, so the same predicate is emitted for both
        # engines; migration 0010 emits the byte-identical name + postgresql_where (drift-clean).
        Index(
            "uq_instrument_terms_current",
            "tenant_id",
            "instrument_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )  # the logical key (all version rows of one instrument's terms)
    coupon_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    coupon_frequency: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # ANNUAL/SEMI_ANNUAL/... plain
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    day_count: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # ACT/360, 30/360, ... plain
    denomination_currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )  # ISO-4217 plain str
    face_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    term_source: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )  # methodology/source pointer
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("instrument_terms.id"), nullable=True
    )  # link to the superseded version (TR-08)
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # logical version count (create=1; each supersede/correction = prev+1)


class IdentifierXref(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Instrument/entity identifier cross-reference (ENT-004, EV; OD-P1B-G).

    ``(entity_type, entity_id)`` is a POLYMORPHIC reference with NO domain FK (genericity, MG-01) —
    P1B-3 writes only ``entity_type='instrument'``. Referential + tenant integrity of ``entity_id``
    rests solely on the binder's tenant-filtered ``resolve_instrument`` + the RLS ``WITH CHECK`` on
    the
    xref row's own ``tenant_id`` (RLS does not tenant-check the polymorphic target). The active
    partial-unique ``(tenant_id, scheme, value) WHERE valid_to IS NULL`` is the OD-P1B-G structural
    uniqueness for the deterministic-or-``AmbiguousIdentifier`` resolver. ``source`` is a provenance
    hint, NOT precedence authority (cross-vendor precedence deferred to OD-012/P1C)."""

    __tablename__ = "identifier_xref"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        # Active-only structural uniqueness (a plain UNIQUE cannot express "over the active period"
        # and would collide across superseded EV versions). SQLite partial index supported.
        Index(
            "uq_identifier_xref_active",
            "tenant_id",
            "scheme",
            "value",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
        Index("ix_identifier_xref_entity", "entity_type", "entity_id"),
    )

    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # polymorphic; P1B-3 = 'instrument' only
    entity_id: Mapped[str] = mapped_column(GUID, nullable=False)  # polymorphic ref, NO domain FK
    scheme: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # ISIN/CUSIP/SEDOL/FIGI/TICKER/INTERNAL_ID/... plain
    value: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # identifier value (trim hygiene)
    source: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )  # provenance hint, NOT precedence
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# --- P1B-4: corporate_action (PROPRIETARY, EV effective-dated; capture-only) ---


class CorporateAction(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Corporate-action reference data (ENT-008, EV; OD-P1B-B) — CAPTURE-ONLY.

    Effective-dated reference record of a corporate action on an instrument (splits, coupons, calls,
    restructurings). PROPRIETARY, tenant-scoped, NEVER hybrid (symmetric RLS, migration 0011). One
    physical row per logical action; amend/cancel = in-place EV supersede (history via the
    ``REFERENCE.*`` audit trail), NOT IA and NOT FR. **NO application engine, NO position/valuation
    adjustment, NO entitlement/tax calc, NO roll math** (capture-only; application is P1C).

    The EV ``valid_from``/``valid_to`` track the RECORD's version window; the business dates
    (``announcement_date``/``ex_date``/``record_date``/``pay_date``/``effective_date``) are inert
    Date columns — no computation. ``status`` is the SINGLE lifecycle flag (ANNOUNCED -> CONFIRMED
    ->
    CANCELLED; no ``is_active``). ``ratio``/``amount``/``currency_code`` are inert placeholders.
    Open-vocab attributes (``action_type``, ``status``) are plain Strings (MG-01)."""

    __tablename__ = "corporate_action"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_corporate_action_tenant_code"),
    )

    code: Mapped[str] = mapped_column(
        String(150), nullable=False
    )  # firm corporate-action reference
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )  # the affected security; intra-tenant; resolved tenant-filtered
    action_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # DIVIDEND/SPLIT/MERGER/... plain
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ANNOUNCED"
    )  # ANNOUNCED/CONFIRMED/CANCELLED (single lifecycle flag; no is_active)
    announcement_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )  # inert business date
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # inert business date
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # inert business date
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # inert business date
    effective_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )  # stored attribute; nothing applied
    ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)  # inert (no calc)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)  # inert (no calc)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)  # plain ISO, no FK
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )  # provenance hint, NOT a vendor feed
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
