"""Calculation-run ORM model.

The run record binds the reproducibility inputs (input snapshot, model version,
assumption set, RNG seed, code version) per the calculation-run contract (temporal
standard §5). Those foreign keys are placeholders here — no domain entities exist yet.
The run row carries a current-status projection; every transition is written immutably to
the audit log, so the authoritative history is append-only even though the row updates.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    new_uuid,
    utcnow,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED})


class CalculationRun(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    __tablename__ = "calculation_run"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    run_id: Mapped[str] = mapped_column(GUID, nullable=False, unique=True, default=new_uuid)
    run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RunStatus.CREATED.value)
    initiated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    # Reproducibility bindings — placeholders until the referenced domains exist.
    input_snapshot_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    model_version_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    assumption_set_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    random_seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # P2-3 (OD-P2-3-F): the deployment/region environment the run executed in — part of the FW-RUN
    # §5
    # bind (temporal §5 item 7). Additive, nullable (migration 0018, on this status-mutable table —
    # a
    # free run-environment label, NOT a security boundary).
    environment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # P3-C1 (OD-C, additive - the environment_id precedent): the human-readable reason persisted
    # at a FAILED transition so a later read can answer WHY (the DQ rows stay the durable defect
    # EVIDENCE; this is presentation-persistence). NULL on non-failed runs.
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
