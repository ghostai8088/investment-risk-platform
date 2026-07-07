"""Exposure-aggregate ORM model (P2-3, ENT-014, IA — the first governed derived number).

``exposure_aggregate`` is the platform's **first official governed derived number** (AD-018; AD-014
/
FW-RUN §5 / TR-15). **IA TRUE append-only** — the ``transaction``/``dataset_snapshot`` precedent (in
the migration-0018 ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger, paired with
the ORM ``before_update``/``before_delete`` guard below). A row is created once and **never
mutated**;
a re-run is a NEW ``calculation_run`` + new rows. PROPRIETARY, tenant-scoped, **NEVER hybrid**
(symmetric RLS only, migration 0018).

**RUN-BOUND + SNAPSHOT-GATED:** every row carries a NOT-NULL ``calculation_run_id`` (FK) + a
NOT-NULL
``input_snapshot_id`` (FK) — no exposure exists without a complete run over a bound snapshot. Grain
=
the per-holding atom ``(calculation_run_id, portfolio_id, instrument_id, base_currency)``. **Signed
market value v1:** ``exposure_amount = quantize_HALF_UP(signed_quantity x mark_value x fx_rate, 6)``
(``Numeric(28,6)`` money scale, base currency); ``exposure_type = MARKET_VALUE`` only. The captured
inputs (``signed_quantity``/``mark_value``/``fx_rate``/``fx_legs``) make each row self-auditing.
``fx_rate`` is the **effective composite** multiplier (mark->base; a published rate only in the
direct/identity case); ``fx_legs`` is the JSON **leg evidence** (the pinned fx_rate leg ids + rates
+
direction) — captured path provenance, **NOT a hard FK** to a supersedable FR ``fx_rate`` row (the
authoritative version-pin is the snapshot's ``COMPONENT_KIND_FX`` component). **NOT risk** — no
VaR/ES/factor/sensitivity/scenario/stress/P&L/performance column.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass

#: Controlled-vocab ``exposure_type`` (plain String, no enum/CHECK; app-side allow-list). v1 =
#: signed market value only. (Gross/net/absolute views are DEFERRED — not minted.)
EXPOSURE_TYPE_MARKET_VALUE = "MARKET_VALUE"
EXPOSURE_TYPES = (EXPOSURE_TYPE_MARKET_VALUE,)


class ExposureAggregate(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One per-holding base-currency market-value exposure of a ``calculation_run`` (ENT-014, IA
    true append-only). Created once, never mutated."""

    __tablename__ = "exposure_aggregate"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # The per-holding grain is unique within a run (one exposure per portfolio+instrument+base).
        UniqueConstraint(
            "calculation_run_id",
            "portfolio_id",
            "instrument_id",
            "base_currency",
            name="uq_exposure_aggregate_run_grain",
        ),
    )

    # Run-bound + snapshot-gated (both NOT NULL — the AD-014 invariant at the DB). tenant_id is
    # indexed by TenantMixin; the FK columns are indexed here (the dataset_snapshot_component
    # pattern).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    # The grain.
    portfolio_id: Mapped[str] = mapped_column(GUID, nullable=False)
    instrument_id: Mapped[str] = mapped_column(GUID, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    mark_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Captured inputs (for self-auditing + the deterministic recompute).
    # PreciseDecimal (P3-C1 parity): contract digits exceed float53; PG DDL unchanged.
    signed_quantity: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 8), nullable=False)
    mark_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
    # The EFFECTIVE composite multiplier mark_currency -> base_currency (HALF_UP @ 12dp; = 1 for
    # identity). NOT a published rate in general (a product of the convert legs).
    fx_rate: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 12), nullable=False)
    # JSON leg evidence: the ordered pinned fx_rate leg refs used (id/base/quote/rate/direction).
    # Captured path provenance — NOT a hard FK to a supersedable FR row. "[]" for identity.
    fx_legs: Mapped[str] = mapped_column(Text, nullable=False)
    # = quantize_HALF_UP(signed_quantity x mark_value x fx_rate, 6), in base_currency (money scale
    # 6).
    exposure_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    exposure_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=EXPOSURE_TYPE_MARKET_VALUE
    )


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# True append-only: the ORM guard (paired with the migration-0018 P0001 trigger) forbids
# update/delete. An exposure result is a fact of a run — never edited; a re-run is a new run.
event.listen(ExposureAggregate, "before_update", _block_mutation)
event.listen(ExposureAggregate, "before_delete", _block_mutation)
