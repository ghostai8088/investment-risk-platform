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

from datetime import date as dt_date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID, PreciseDecimal
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
    # PreciseDecimal (P3-C1 parity): 28 significant digits by contract exceed float53 — PG DDL
    # is UNCHANGED (NUMERIC(28,12)); SQLite (test engine) gains exact fixed-scale TEXT.
    sensitivity_value: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 12), nullable=False)
    # The bump convention recorded on the row (1.0000 = 1bp).
    bump_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


class FactorExposureResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One atom's indicator-loading allocation to one factor (P3-3, ENT-028 family — allocation
    v1; IA TRUE append-only). Created once, never mutated; a re-run is a NEW ``calculation_run``.

    **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (the ``sensitivity_result`` exemplar): NOT-NULL
    ``calculation_run_id`` + ``input_snapshot_id`` (a ``FACTOR_EXPOSURE_INPUT`` snapshot pinning
    the consumed ``exposure_aggregate`` atoms + ``factor`` definitions) + a REGISTERED
    ``model_version_id``. Grain = the 4-tuple
    ``(calculation_run_id, portfolio_id, instrument_id, factor_id)`` (OD-P3-3-E);
    ``input_snapshot_id``/``model_version_id`` carried NON-NULL but functionally run-determined
    (out of the key). ``factor_id`` is deliberately **NOT a hard FK** — the EV ``factor`` head is
    supersedable-in-place; the pinned ``COMPONENT_KIND_FACTOR`` component is the authoritative
    version (the ``fx_legs``/``curve_id`` precedent). ``mark_currency`` is the carried mapping
    attribute; ``loading`` (v1 constant 1) is the fractional/beta extension seam
    (extend-by-value, not migration). No stored per-factor TOTAL rows — Σ is deterministic and
    test-asserted (the P2-3 precedent)."""

    __tablename__ = "factor_exposure_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # One allocation per (run, atom, factor) — the OD-P3-3-E 4-tuple.
        UniqueConstraint(
            "calculation_run_id",
            "portfolio_id",
            "instrument_id",
            "factor_id",
            name="uq_factor_exposure_result_run_grain",
        ),
    )

    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    # The pinned atom's identity + the pinned factor (self-describing; no live read to interpret).
    portfolio_id: Mapped[str] = mapped_column(GUID, nullable=False)
    instrument_id: Mapped[str] = mapped_column(GUID, nullable=False)
    factor_id: Mapped[str] = mapped_column(GUID, nullable=False)
    factor_code: Mapped[str] = mapped_column(String(150), nullable=False)
    factor_family: Mapped[str] = mapped_column(String(30), nullable=False)
    # Carried captured attributes: the run-uniform base + the mapping attribute (auditability).
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    mark_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # v1 indicator loading (= 1); the beta-extension seam (Numeric(20,12), the factor scale).
    # PreciseDecimal (P3-C1 parity): contract digits exceed float53; PG DDL unchanged.
    loading: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    # = quantize_HALF_UP(loading * atom.exposure_amount, 6); signed, base currency.
    exposure_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)


class CovarianceResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One element of a sample factor covariance matrix (P3-4, ENT-051 `covariance_matrix`;
    IA TRUE append-only). One row per canonical UNORDERED factor pair INCLUDING the diagonal
    (`factor_id_1 == factor_id_2` rows are the variances); the run is the matrix identity —
    F factors ⇒ exactly F·(F+1)/2 rows per COMPLETED run.

    **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (the P3-3 exemplar): NOT-NULL
    ``calculation_run_id`` + ``input_snapshot_id`` (a ``COVARIANCE_INPUT`` snapshot pinning the
    factor definitions + return windows) + a REGISTERED, identity-checked ``model_version_id``
    whose declared ``window_observations`` fixed the estimation window (OD-P3-4-G). Grain = the
    3-tuple ``(calculation_run_id, factor_id_1, factor_id_2)`` with **binder-enforced canonical
    ordering** ``factor_id_1 <= factor_id_2`` (lowercase-GUID string order; NO CHECK constraint —
    the genericity rule; service-enforced + tested). ``factor_id_*`` are deliberately NOT hard
    FKs (the pinned ``COMPONENT_KIND_FACTOR`` components are authoritative). ``covariance_value``
    is ``quantize_HALF_UP(cov_ij, 20)`` — DAILY, UNANNUALIZED (declared) — carried as
    ``PreciseDecimal``: NUMERIC(38,20) on PG, a fixed-scale TEXT on SQLite (a 20dp value does
    NOT survive SQLite's float roundtrip; AD-011 engine-independence)."""

    __tablename__ = "covariance_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id",
            "factor_id_1",
            "factor_id_2",
            name="uq_covariance_result_run_grain",
        ),
    )

    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    factor_id_1: Mapped[str] = mapped_column(GUID, nullable=False)
    factor_id_2: Mapped[str] = mapped_column(GUID, nullable=False)
    factor_code_1: Mapped[str] = mapped_column(String(150), nullable=False)
    factor_code_2: Mapped[str] = mapped_column(String(150), nullable=False)
    # Controlled vocab (plain String): 'COVARIANCE' v1; 'CORRELATION' reserved (extend by value).
    statistic_type: Mapped[str] = mapped_column(String(30), nullable=False)
    return_type: Mapped[str] = mapped_column(String(30), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[dt_date] = mapped_column(Date, nullable=False)
    window_end: Mapped[dt_date] = mapped_column(Date, nullable=False)
    covariance_value: Mapped[Decimal] = mapped_column(PreciseDecimal(38, 20), nullable=False)


class VarResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One parametric-VaR summary (P3-5, **ENT-027 `risk_result` REALIZED**; IA TRUE append-only)
    — the platform's first SINGLE-SUMMARY-ROW governed result: ONE row per COMPLETED run
    (grain ``(calculation_run_id, metric_type)``; ``VAR_PARAMETRIC``, ``ES_PARAMETRIC`` reserved
    — extend by value) and the first DERIVED-OF-DERIVED number (two upstream governed runs).

    **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (the P3-4 exemplar): NOT-NULL
    ``calculation_run_id`` + ``input_snapshot_id`` (a ``VAR_INPUT`` snapshot pinning the consumed
    ``factor_exposure_result`` + ``covariance_result`` rows) + a REGISTERED, identity-checked
    ``model_version_id`` whose DECLARED confidence/horizon/z fixed the parameters (OD-P3-5-D).
    ``exposure_run_id``/``covariance_run_id`` are hard-FK PROVENANCE columns (``calculation_run.
    run_id`` is unique and never deleted) — which upstream runs fed this number, queryable
    without parsing the snapshot. ``sigma``/``var_value`` = ``quantize_HALF_UP(…, 6)`` in the
    run-uniform ``base_currency`` (positive ``var_value`` = potential loss); the covariance
    window is echoed (``n_observations``/``window_start``/``window_end``) so the row is
    self-describing."""

    __tablename__ = "var_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint("calculation_run_id", "metric_type", name="uq_var_result_run_grain"),
    )

    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    exposure_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    # Nullable since 0028 (VAR-HS-1): a VAR_HISTORICAL run consumes NO covariance run — NULL is
    # the honest provenance (the parametric binder still always writes it).
    covariance_run_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=True, index=True
    )
    # Controlled vocab (plain String): 'VAR_PARAMETRIC' (P3-5), 'VAR_HISTORICAL' (VAR-HS-1);
    # 'ES_PARAMETRIC' reserved.
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    confidence_level: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # PreciseDecimal (2026-07 review: the OD-E contract criterion applied consistently —
    # 20 declared digits exceed float53 even though today's z vocabulary is 13 digits).
    # Nullable since 0028 (VAR-HS-1): VAR_HISTORICAL rows have no normal quantile and no
    # volatility estimate; the parametric binder still ALWAYS writes both (binder-enforced).
    z_score: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 12), nullable=True)
    # PreciseDecimal (PG NUMERIC(28,6) / SQLite fixed-scale TEXT): a 16+-significant-digit
    # currency value does not survive SQLite's float roundtrip (the P3-4 covariance lesson,
    # applied to the NEW columns; the shipped P3-1/P3-3 result columns are a recorded parity
    # deferral).
    sigma: Mapped[Decimal | None] = mapped_column(PreciseDecimal(28, 6), nullable=True)
    var_value: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    n_factors: Mapped[int] = mapped_column(Integer, nullable=False)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[dt_date] = mapped_column(Date, nullable=False)
    window_end: Mapped[dt_date] = mapped_column(Date, nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# True append-only: the ORM guard (paired with the migration-0022/0024 P0001 triggers) forbids
# update/delete. A risk result is a fact of a run — never edited; a re-run is a new run.
event.listen(SensitivityResult, "before_update", _block_mutation)
event.listen(SensitivityResult, "before_delete", _block_mutation)
event.listen(FactorExposureResult, "before_update", _block_mutation)
event.listen(FactorExposureResult, "before_delete", _block_mutation)
event.listen(CovarianceResult, "before_update", _block_mutation)
event.listen(CovarianceResult, "before_delete", _block_mutation)
event.listen(VarResult, "before_update", _block_mutation)
event.listen(VarResult, "before_delete", _block_mutation)
