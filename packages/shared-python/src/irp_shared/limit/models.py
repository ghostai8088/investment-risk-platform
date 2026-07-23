"""Limit/breach ORM models (LIM-1, ENT-031 `limit_definition` + ENT-033 `breach`).

- ``LimitDefinition`` (ENT-031, **EV**) — the governed limit CONFIG header, entity-versioned in
  place (``record_version``, the ``Schedule``/``scenario_definition`` EV precedent);
  ``LIMIT.DEFINE``/``LIMIT.CHANGE`` audited (a 2L risk-manager function). A threshold + a
  ``(target_run_type, metric_type, benchmark_id?)`` metric-selector + an exact-match
  ``scope_portfolio_id`` + a ``breach_direction`` predicate + a ``limit_kind`` (HARD/SOFT). Logical
  identity ``(tenant_id, code)``.
- ``Breach`` (ENT-033, **IA TRUE append-only**) — one row per detected breach, SELF-DESCRIBING: it
  echoes the metric IDENTITY (``target_run_type``/``metric_type``/``benchmark_id``) AND the
  comparison arithmetic (``observed_value``/``threshold_value``/``threshold_unit``/
  ``breach_direction``/``limit_kind``) at detection, and FKs the evaluated governed
  ``calculation_run`` (Fable demand #1). ``UniqueConstraint(limit_definition_id,
  calculation_run_id)`` = the per-(limit, run) idempotency backstop. NOT a governed number: binds
  NO ``input_snapshot_id``/``model_version_id`` of its own (OD-B).

Both PROPRIETARY, tenant-scoped, symmetric FORCE RLS — NEVER hybrid. Migration ``0050_limit_breach``
(``limit_definition`` gets RLS only; ``breach`` gets RLS + the append-only trigger). NO ops grant.

Threshold/observed values are ``PreciseDecimal(34, 12)`` — unit-agnostic: 34-12 = 22 integer digits
match the source ``var_value`` ``(28, 6)`` range (NO overflow even in a low-unit currency), 12 scale
holds the ``te_value`` fraction — BOTH without loss (OD-C; the 4-finder overflow fold).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass


class LimitDefinition(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A governed limit CONFIG header (ENT-031, EV entity-versioned in place)."""

    __tablename__ = "limit_definition"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_limit_definition_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The metric-selector (OD-C): the governed family + flavor a limit thresholds.
    target_run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    #: REQUIRED for benchmark-relative families (ACTIVE_RISK); NULL otherwise. A nullable HARD FK to
    #: ``benchmark.id`` (parity with ``active_risk_result.benchmark_id``); the selector is
    #: (run_type, metric_type, benchmark_id?).
    benchmark_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("benchmark.id"), nullable=True, index=True
    )
    #: The WITHIN-TENANT portfolio scope; bound by EXACT ``scope_portfolio_id`` match
    #: (OD-E). A hard FK — a limit targets a real book.
    scope_portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    #: The threshold (unit-agnostic precision) + its unit (CURRENCY/FRACTION — the guard, OD-C).
    threshold_value: Mapped[Decimal] = mapped_column(PreciseDecimal(34, 12), nullable=False)
    threshold_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The BREACH predicate (OD-D): ABOVE = breach when observed > threshold (ceiling, the default);
    #: BELOW = breach when observed < threshold (floor). Strict boundary.
    breach_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    #: HARD (binding — a breach is an incident) | SOFT (advisory — a recorded warning).
    limit_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Lifecycle status (only ACTIVE is evaluated).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Breach(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One detected breach of a limit (ENT-033, IA TRUE append-only, self-describing)."""

    __tablename__ = "breach"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint("limit_definition_id", "calculation_run_id", name="uq_breach_limit_run"),
    )

    limit_definition_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("limit_definition.id"), nullable=False, index=True
    )
    #: The evaluated governed run (Fable demand #1 — a breach FKs the run it adjudicated).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    #: The wall-clock detection instant (operational evidence).
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The metric IDENTITY echo (OD-F) — makes the breach self-describing from its own row.
    target_run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    benchmark_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    #: The comparison ARITHMETIC echo (OD-F) — reproduces the breach from its own row.
    observed_value: Mapped[Decimal] = mapped_column(PreciseDecimal(34, 12), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(PreciseDecimal(34, 12), nullable=False)
    threshold_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    breach_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    limit_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: SOFT (advisory) | HARD (incident) — echoes ``limit_kind``.
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Breach lifecycle status (v1 = DETECTED; the lifecycle states are MG-2).
    status: Mapped[str] = mapped_column(String(20), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# breach is IA TRUE append-only (the ORM guard paired with the migration-0050 P0001 trigger).
# limit_definition (EV) is edited in place (record_version bump) and is NOT append-only.
event.listen(Breach, "before_update", _block_mutation)
event.listen(Breach, "before_delete", _block_mutation)
