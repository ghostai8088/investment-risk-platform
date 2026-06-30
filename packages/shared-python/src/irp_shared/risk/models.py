"""Sensitivity-result ORM model (P3-1, ENT-028, IA — the first reproducible governed risk number).

``sensitivity_result`` realizes ENT-028 (``sensitivity``/``exposure_metric``): the analytic
curve-node DV01 / spread-DV01 of a ``calculation_run``. **IA TRUE append-only** — the
``exposure_aggregate`` precedent (in the migration-0022 ``APPEND_ONLY_TABLES`` -> the
``irp_prevent_mutation`` P0001 trigger, paired with the ORM ``before_update``/``before_delete``
guard below). A row is created once and **never mutated**; a re-run is a NEW ``calculation_run`` +
new rows. PROPRIETARY, tenant-scoped, **NEVER hybrid** (symmetric RLS only, migration 0022).

**RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** — every row carries a NOT-NULL ``calculation_run_id``
(FK), ``input_snapshot_id`` (FK) **and** ``model_version_id`` (FK to a REGISTERED model_version —
the model-governance hardening vs the model-less ``exposure_aggregate``). No sensitivity exists
without a complete run over a bound curve snapshot driven by a registered model version. The
**curve-intrinsic** v1 grain (OD-P3-1-B) is the 5-tuple
``(calculation_run_id, curve_id, value_type, tenor_days, sensitivity_type)``; ``input_snapshot_id``
+
``model_version_id`` are carried NON-NULL but functionally determined by the run (out of the key).
``portfolio_id``/``instrument_id`` are deliberately ABSENT (curve-intrinsic — instrument
attribution
is deferred). The captured ``curve_type``/``currency_code``/``reference_key``/``value_type``/
``tenor_days``/``point``-derived ``sensitivity_value`` make each row self-describing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class SensitivityResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One analytic curve-node sensitivity (DV01 / spread-DV01) of a ``calculation_run`` (ENT-028,
    IA true append-only). Created once, never mutated."""

    __tablename__ = "sensitivity_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # The curve-intrinsic per-node grain is unique within a run (OD-P3-1-B 5-tuple).
        UniqueConstraint(
            "calculation_run_id",
            "curve_id",
            "value_type",
            "tenor_days",
            "sensitivity_type",
            name="uq_sensitivity_result_run_grain",
        ),
    )

    # Run-bound + snapshot-gated + model-bound (all NOT NULL — the AD-014 + CTRL-003 invariant at
    # the
    # DB). The FK columns are indexed (the exposure_aggregate pattern).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    # The curve the node belongs to (the pinned snapshot CURVE component's target id) + captured
    # descriptors (self-describing; no live curve read needed to interpret a row).
    curve_id: Mapped[str] = mapped_column(GUID, nullable=False)
    curve_type: Mapped[str] = mapped_column(String(30), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    reference_key: Mapped[str] = mapped_column(String(150), nullable=False)
    # The node + the computed sensitivity.
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    tenor_days: Mapped[int] = mapped_column(Integer, nullable=False)
    tenor_label: Mapped[str] = mapped_column(String(10), nullable=False)
    sensitivity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # = quantize_HALF_UP(-T * DF * 1bp, 12), per unit notional (the kernel result).
    sensitivity_value: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    # The bump convention recorded on the row (1.0000 = 1bp).
    bump_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# True append-only: the ORM guard (paired with the migration-0022 P0001 trigger) forbids
# update/delete. A sensitivity result is a fact of a run — never edited; a re-run is a new run.
event.listen(SensitivityResult, "before_update", _block_mutation)
event.listen(SensitivityResult, "before_delete", _block_mutation)
