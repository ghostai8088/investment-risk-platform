"""Common-column and temporal mixins.

Temporal mixins implement the ratified selective-bitemporality classes (AD-005 / BR-19,
see ``04_data_model/temporal_reproducibility_standard.md`` §2A):

- ``FullReproducibleMixin``  (FR) — valid time + system time (risk-driving inputs).
- ``ImmutableAppendOnlyMixin`` (IA) — system (knowledge) time only; append-only.
- ``EffectiveDatedMixin`` (EV) — effective-dated reference/config.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.types import GUID


def utcnow() -> datetime:
    """Timezone-aware current UTC time (QS-12: all timestamps stored in UTC)."""
    return datetime.now(tz=UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class PrimaryKeyMixin:
    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TenantMixin:
    """Mandatory tenant scope (BR-17). Enforced in-app by entitlement checks and at the
    database layer by PostgreSQL row-level security (added in the foundation migration)."""

    tenant_id: Mapped[str] = mapped_column(GUID, nullable=False, index=True)


class FullReproducibleMixin:
    """FR — full bitemporal."""

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    system_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    system_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImmutableAppendOnlyMixin:
    """IA — append-only; records only system (knowledge) time."""

    system_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class EffectiveDatedMixin:
    """EV — effective-dated versioned reference/config."""

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
