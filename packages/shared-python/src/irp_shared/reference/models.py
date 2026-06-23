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

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
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
