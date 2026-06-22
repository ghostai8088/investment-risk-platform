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
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
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
