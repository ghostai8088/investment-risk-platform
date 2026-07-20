"""Pacing ORM model (CC-2, ENT-059 — pacing_projection_result, IA true append-only).

One projected FUTURE period per row (grain ``(calculation_run_id, period_index)``), created once by
a COMPLETED pacing run and never mutated (a re-projection is a new run + new rows). **RUN-BOUND +
SNAPSHOT-GATED + MODEL-BOUND** (the ``portfolio_return_result`` exemplar): NOT-NULL
``calculation_run_id`` + ``input_snapshot_id`` (a ``PACING_INPUT`` snapshot pinning the
commitment/calls/distributions/mark) + a REGISTERED, identity-checked ``model_version_id``
(``pacing.commitment_projection`` v1). ``portfolio_id``/``instrument_id`` are the projected
(book, fund) pair — the stable commitment identity CC-1 established. ``period_index`` = fund AGE
(t); ``period_start``/``period_end`` are the half-open anniversary window; the four money columns
(``projected_call``/``projected_distribution``/``projected_nav``/``unfunded_end``) are
PreciseDecimal(28,6) in the commitment's chain-immutable ``currency_code``.
"""

from __future__ import annotations

from datetime import date as dt_date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass


class PacingProjectionResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One projected future period of a commitment-pacing run (ENT-059, IA true append-only)."""

    __tablename__ = "pacing_projection_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id",
            "period_index",
            name="uq_pacing_projection_result_run_grain",
        ),
    )

    # Run-bound + snapshot-gated + model-bound (all NOT NULL — the AD-014 + CTRL-003 invariant at
    # the DB). FK columns indexed (the portfolio_return_result pattern).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    # The projected (book, fund) pair — the stable commitment identity.
    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Fund AGE t (1..L); never a projection-step counter (the future-only projection may start at
    # t > 1).
    period_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # The half-open anniversary window [period_start, period_end) for the age-t period.
    period_start: Mapped[dt_date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt_date] = mapped_column(Date, nullable=False)
    # The projected values (money scale, the commitment's currency). QUANTIZE-THEN-ROLL: these
    # persisted 6dp echoes satisfy NAV(t) = NAV(t-1)(1+G) + call - dist EXACTLY.
    projected_call: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    projected_distribution: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    projected_nav: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    unfunded_end: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{target.__tablename__} is IA true append-only — UPDATE/DELETE is prohibited "
        f"(a re-projection is a new calculation_run + new rows)"
    )


event.listen(PacingProjectionResult, "before_update", _block_mutation)
event.listen(PacingProjectionResult, "before_delete", _block_mutation)
