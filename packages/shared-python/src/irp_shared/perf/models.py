"""Portfolio-return-result ORM model (PM-1, ENT-053, IA — the SEVENTH governed number and the
FIRST non-risk one).

``portfolio_return_result`` realizes ENT-053: the chain-linked time-weighted return (Modified-Dietz
within caller-supplied exposure-run valuation boundaries) of a ``calculation_run``. **IA TRUE
append-only** — the ``exposure_aggregate``/``var_result`` precedent (in the migration-0031
``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger, paired with the ORM
``before_update``/``before_delete`` guard below). A row is created once and **never mutated**; a
re-run is a NEW ``calculation_run`` + new rows. PROPRIETARY, tenant-scoped, **NEVER hybrid**
(symmetric RLS only, migration 0031).

**RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** — every row carries a NOT-NULL ``calculation_run_id``
(FK), ``input_snapshot_id`` (FK to a ``RETURN_INPUT`` snapshot pinning the N boundary exposure runs'
atoms + the in-window transactions + the flow FX legs) **and** ``model_version_id`` (FK to a
REGISTERED ``perf.return.twr`` v1 version). The **N-run provenance lives in the snapshot pins** (the
EXPOSURE-atom components carry each boundary run id) — there are no per-run FK columns because N is
variable; ``portfolio_id`` records the measured book.

The realized series is ``n`` ``DIETZ_PERIOD`` rows (one per sub-period; ``return_value = r_i``) +
ONE ``TWR_LINKED`` summary row (``return_value = R = prod(1 + r_i) - 1``). Grain
``(calculation_run_id, metric_type, period_start)`` — a ``DIETZ_PERIOD`` and the ``TWR_LINKED`` row
can share ``period_start`` (the first boundary) because ``metric_type`` differs. ``begin_mv``/
``end_mv``/``net_external_flow`` (base currency, Numeric(28,6)) are the Dietz evidence;
``return_value`` Numeric(20,12) is a FRACTION (a return, NOT currency); ``n_flows``/``n_periods``
are the counts (``n_periods = 1`` for a ``DIETZ_PERIOD`` row, the number of linked sub-periods for
the ``TWR_LINKED`` row).
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

#: The ``metric_type`` controlled vocabulary (plain String; extend by value, never silently).
METRIC_TYPE_DIETZ_PERIOD = "DIETZ_PERIOD"
METRIC_TYPE_TWR_LINKED = "TWR_LINKED"


class PortfolioReturnResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One portfolio-return series row (PM-1, **ENT-053**, IA TRUE append-only). Created once, never
    mutated. ``n`` ``DIETZ_PERIOD`` sub-period rows + one ``TWR_LINKED`` summary row per COMPLETED
    run (grain ``(calculation_run_id, metric_type, period_start)``).

    **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (the ``var_result`` exemplar): NOT-NULL
    ``calculation_run_id`` + ``input_snapshot_id`` (a ``RETURN_INPUT`` snapshot) + a REGISTERED,
    identity-checked ``model_version_id`` (``perf.return.twr`` v1). ``portfolio_id`` is the measured
    book; the N boundary-run provenance lives in the pinned EXPOSURE atoms of the snapshot (N is
    variable — no per-run FK columns). ``begin_mv``/``end_mv``/``net_external_flow`` (base currency)
    are the Modified-Dietz evidence; ``return_value`` is a Numeric(20,12) FRACTION."""

    __tablename__ = "portfolio_return_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # The sub-period grain within a run; a DIETZ_PERIOD row and the TWR_LINKED row can share a
        # period_start (metric_type disambiguates), so metric_type is part of the key.
        UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "period_start",
            name="uq_portfolio_return_result_run_grain",
        ),
    )

    # Run-bound + snapshot-gated + model-bound (all NOT NULL — the AD-014 + CTRL-003 invariant at
    # the DB). FK columns indexed (the exposure_aggregate pattern).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    # The measured book (the N boundary exposure runs share this scope).
    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    # Controlled vocab (plain String): 'DIETZ_PERIOD' (per sub-period) | 'TWR_LINKED' (summary).
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # The sub-period window (a DIETZ_PERIOD row) or the full span (the TWR_LINKED row), half-open
    # (period_start, period_end] in economic (valuation) dates.
    period_start: Mapped[dt_date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt_date] = mapped_column(Date, nullable=False)
    # Modified-Dietz evidence (base currency, money scale): begin/end market value + the signed net
    # external flow. For TWR_LINKED: the first BMV, the last EMV, the total net flow over the span.
    begin_mv: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    end_mv: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    net_external_flow: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    # The return: r_i (DIETZ_PERIOD) or R = prod(1 + r_i) - 1 (TWR_LINKED). A FRACTION, NOT currency
    # — the Numeric(20,12) return scale (PreciseDecimal for cross-engine byte-fidelity).
    return_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    # Counts: external flows in the (sub)period; linked sub-periods (1 for a DIETZ_PERIOD row).
    n_flows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{target.__tablename__} is IA true append-only — UPDATE/DELETE is prohibited "
        f"(a re-run is a new calculation_run + new rows)"
    )


event.listen(PortfolioReturnResult, "before_update", _block_mutation)
event.listen(PortfolioReturnResult, "before_delete", _block_mutation)
