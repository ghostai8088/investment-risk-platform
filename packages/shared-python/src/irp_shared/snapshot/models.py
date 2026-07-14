"""Reproducible input-snapshot ORM models (P2-1, ENT-049/050, IA — AD-014).

``dataset_snapshot`` (header) + ``dataset_snapshot_component`` (per-input physical-version pin) are
the AD-014 reproducibility primitive: an immutable, knowledge-time pin of the exact governed input
record versions a later ``calculation_run`` (P2-3) consumes. Reproducibility **infrastructure** —
it captures input versions and computes **no** derived number.

Both tables are **IA TRUE append-only** (the ``transaction`` precedent, NOT the status-mutable
``calculation_run``/``ingestion_batch`` flavor): in the migration-0016 ``APPEND_ONLY_TABLES`` ->
the ``irp_prevent_mutation`` P0001 trigger, paired with the ORM ``before_update``/``before_delete``
guard below (shared ``audit.models.AppendOnlyViolation``). A snapshot is created once and never
mutated; a new input set is a NEW snapshot. PROPRIETARY, tenant-scoped, **NEVER hybrid** (symmetric
RLS only, migration 0016). No ``valid_*`` axis (the as-of-ness lives in the pinned input versions +
the header cutoffs). **No ``status``; no ``model_version`` component** (model binds at the run,
OD-P2-C). The component captures both a physical-version PIN (``target_entity_id`` + coords) and
the
``captured_content`` (the canonical-serialized value) so the snapshot is self-sufficient (§8).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Controlled-vocab ``purpose`` values (plain String, no enum/CHECK; app-side allow-list in
#: binder).
PURPOSE_EXPOSURE_INPUT = "EXPOSURE_INPUT"
#: P3-1 (OD-P3-1-E): a curve-input snapshot for an analytic-sensitivity run (pins CURVE
#: components).
PURPOSE_SENSITIVITY_INPUT = "SENSITIVITY_INPUT"
#: P3-3 (OD-P3-3-I): a factor-exposure input snapshot (pins EXPOSURE atoms + FACTOR definitions).
PURPOSE_FACTOR_EXPOSURE_INPUT = "FACTOR_EXPOSURE_INPUT"
#: P3-4 (OD-P3-4-I): a covariance input snapshot (pins FACTOR definitions + FACTOR_RETURN windows).
PURPOSE_COVARIANCE_INPUT = "COVARIANCE_INPUT"
#: P3-5 (OD-P3-5-I): a VaR input snapshot (pins the consumed FACTOR_EXPOSURE + COVARIANCE result
#: rows of the two upstream governed runs — the first derived-of-derived input set).
PURPOSE_VAR_INPUT = "VAR_INPUT"
#: VAR-HS-1 (OD-VHS-F): the historical-simulation input purpose — a SIBLING of VAR_INPUT so the
#: wrong-purpose refusal stays sharp (the two shapes are not interchangeable).
PURPOSE_VAR_HS_INPUT = "VAR_HS_INPUT"
#: P3-7 (OD-P3-7-E): the ex-ante active-risk input purpose — pins the FACTOR_EXPOSURE + COVARIANCE
#: result rows, the FACTOR definitions (the currency→factor map), and the BENCHMARK membership.
PURPOSE_ACTIVE_RISK_INPUT = "ACTIVE_RISK_INPUT"
#: PM-1 (OD-PM-1-E): the portfolio-return input purpose — pins the EXPOSURE atoms of N>=2 COMPLETED
#: exposure runs (the sub-period valuation boundaries), the in-window TRANSACTION rows (external
#: flows filtered by the binder), and the FX legs for non-base flow currencies at each flow date.
#: The FIRST non-risk (``perf``-family) snapshot purpose.
PURPOSE_RETURN_INPUT = "RETURN_INPUT"
#: P3-8 (OD-P3-8-G): the ex-post benchmark-relative input purpose — pins ALL portfolio_return_result
#: rows of ONE COMPLETED return run (PORTFOLIO_RETURN kind) + the in-window benchmark_return series
#: (BENCHMARK_RETURN kind). ENT-052's FIRST governed consumer.
PURPOSE_BENCHMARK_RELATIVE_INPUT = "BENCHMARK_RELATIVE_INPUT"
#: BT-1 (OD-BT-1-J): the VaR-backtesting input purpose — pins ALL portfolio_return_result rows
#: of ONE COMPLETED return run (PORTFOLIO_RETURN kind, REUSED) + ALL var_result rows of the
#: listed VAR runs (VAR kind). The SR 11-7 outcomes-analysis input set.
PURPOSE_VAR_BACKTEST_INPUT = "VAR_BACKTEST_INPUT"
#: P3-6 (OD-P3-6-F): the stress/scenario input purpose — pins ALL factor_exposure_result rows of
#: ONE COMPLETED factor-exposure run (FACTOR_EXPOSURE kind, REUSED — the exposures shocked) + the
#: scenario definition header & its OPEN shock set (SCENARIO kind). The tenth governed number's
#: input set. A later shock supersede is invisible to the pin (TR-09).
PURPOSE_SCENARIO_INPUT = "SCENARIO_INPUT"
#: PA-1 desmoothing input: the current-head ``valuation`` marks of ONE (portfolio, instrument)
#: pair over a declared date window. A later mark correction is invisible to the pin (TR-09).
PURPOSE_DESMOOTHING_INPUT = "DESMOOTHING_INPUT"
#: PA-3: pins a consumed DESMOOTHED_RETURN run's per-period rows + the candidate factors' return
#: windows — the OLS proxy-weight estimation input.
PURPOSE_PROXY_WEIGHT_INPUT = "PROXY_WEIGHT_INPUT"
PURPOSE_ADHOC = "ADHOC"
PURPOSE_TEST = "TEST"
SNAPSHOT_PURPOSES = (
    PURPOSE_EXPOSURE_INPUT,
    PURPOSE_SENSITIVITY_INPUT,
    PURPOSE_FACTOR_EXPOSURE_INPUT,
    PURPOSE_COVARIANCE_INPUT,
    PURPOSE_VAR_INPUT,
    PURPOSE_VAR_HS_INPUT,
    PURPOSE_ACTIVE_RISK_INPUT,
    PURPOSE_RETURN_INPUT,
    PURPOSE_BENCHMARK_RELATIVE_INPUT,
    PURPOSE_VAR_BACKTEST_INPUT,
    PURPOSE_SCENARIO_INPUT,
    PURPOSE_DESMOOTHING_INPUT,
    PURPOSE_ADHOC,
    PURPOSE_TEST,
)

#: Controlled-vocab ``component_kind`` values (PRICE/REFERENCE reserved later).
COMPONENT_KIND_PORTFOLIO = "PORTFOLIO"
COMPONENT_KIND_POSITION = "POSITION"
COMPONENT_KIND_VALUATION = "VALUATION"
#: P2-3 (OD-P2-3-E): a pinned ``fx_rate`` (ENT-024) leg — captured so a base-currency exposure run
#: is reproducible from the snapshot alone (the exposure compute reads this captured content, never
#: a live FX read). Minted additively; the tables are unchanged (no schema redesign).
COMPONENT_KIND_FX = "FX"
#: P3-1 (OD-P3-1-E): a pinned ``curve`` (ENT-021) header version + its immutable ``curve_point``
#: node
#: set (captured into one component) — so an analytic-sensitivity run is reproducible from the
#: snapshot alone (the compute reads this captured content, never a live curve read). App-constant;
#: the ``dataset_snapshot``/``component`` tables are UNCHANGED (``component_kind`` is
#: unconstrained).
COMPONENT_KIND_CURVE = "CURVE"
#: P3-3 (OD-P3-3-I): a pinned ``exposure_aggregate`` (ENT-014) atom — the FIRST **IA-row pin
#: flavor** (``pinned_valid_from``/``pinned_record_version`` NULL; ``pinned_system_from`` = the
#: row's append time; the row is immutable, so drift is impossible by construction). App-constant;
#: the tables are UNCHANGED.
COMPONENT_KIND_EXPOSURE = "EXPOSURE"
#: P3-3 (OD-P3-3-I): a pinned ``factor`` EV definition version (the PORTFOLIO EV-pin flavor: NULL
#: system axis; ``record_version`` the drift discriminator). ``COMPONENT_KIND_FACTOR_RETURN`` was
#: readiness-noted here until P3-4 minted it below (OD-P3-2-G / OD-P3-3-I / OD-P3-4-I).
COMPONENT_KIND_FACTOR = "FACTOR"
#: P3-4 (OD-P3-4-I): a pinned per-factor RETURN WINDOW — the ordered ``factor_return`` FR rows of
#: the aligned estimation window, captured as ONE component per factor (the ``curve``
#: header+nodes shape over FR rows; readiness-noted since OD-P3-2-G, MINTED here at its designed
#: first consumer). ``target_entity_type='factor'`` (the series parent; the kind disambiguates
#: from the COMPONENT_KIND_FACTOR definition pin).
COMPONENT_KIND_FACTOR_RETURN = "FACTOR_RETURN"
#: P3-5 (OD-P3-5-I): a pinned ``factor_exposure_result`` row (IA-row pin flavor — the source row
#: is TRUE append-only; drift impossible by construction; the P3-3 EXPOSURE precedent).
COMPONENT_KIND_FACTOR_EXPOSURE = "FACTOR_EXPOSURE"
#: P3-5 (OD-P3-5-I): a pinned ``covariance_result`` row (IA-row pin flavor).
COMPONENT_KIND_COVARIANCE = "COVARIANCE"
#: P3-7 (OD-P3-7-E): a pinned ``benchmark_constituent`` FR row — the captured membership of the
#: declared ``(benchmark_id, effective_date)`` set, ONE component per constituent (the
#: ``factor_return`` per-row FR flavor; a later vendor supersede/correction is invisible to the
#: pin, TR-09). The benchmark HEADER identity is carried in each component's content. Reserved at
#: OD-P3-0-G, MINTED here at its designed first consumer.
COMPONENT_KIND_BENCHMARK = "BENCHMARK"
#: PM-1 (OD-PM-1-E): a pinned ``transaction`` (ENT-011) row — an IA-row pin flavor (the source row
#: is TRUE append-only; drift impossible by construction; the P3-3 EXPOSURE precedent). The
#: portfolio-return binder filters these to the declared external-flow set {TRANSFER_IN,
#: TRANSFER_OUT}; the snapshot pins the full in-window set (staying perf-agnostic — ``snapshot``
#: never imports the flow set). ``target_entity_type='transaction'``.
COMPONENT_KIND_TRANSACTION = "TRANSACTION"
#: P3-8 (OD-P3-8-G): a pinned ``portfolio_return_result`` (ENT-053) row — an IA-row pin flavor (the
#: source row is TRUE append-only; drift impossible). The benchmark-relative binder reads the
#: DIETZ_PERIOD rows as the per-sub-period portfolio returns + the TWR_LINKED row for the exact-
#: linkage cross-check. ``target_entity_type='portfolio_return_result'``.
COMPONENT_KIND_PORTFOLIO_RETURN = "PORTFOLIO_RETURN"
#: P3-8 (OD-P3-8-G): a pinned ``benchmark_return`` (ENT-052) RETURN WINDOW — the ``factor_return``
#: series flavor (ONE component pinning the ordered in-window FR rows + the benchmark HEADER
#: identity + return_type/basis). A later vendor supersede/correction is invisible to the pin
#: (TR-09). ENT-052's FIRST governed consumer. ``target_entity_type='benchmark'``.
COMPONENT_KIND_BENCHMARK_RETURN = "BENCHMARK_RETURN"
#: BT-1 (OD-BT-1-J): a pinned ``var_result`` (ENT-027, IA) row — the P3-3 EXPOSURE
#: true-append-only pin flavor (full immutable column set; byte-identical on re-verify).
#: ``target_entity_type='var_result'``.
COMPONENT_KIND_VAR = "VAR"
#: P3-6 (OD-P3-6-F): a pinned ``scenario_shock`` (ENT-029, FR) row — the ``benchmark_constituent``
#: per-row FR flavor (ONE component per OPEN shock, the scenario definition header identity carried
#: in each component's content; a later shock supersede/correction is invisible to the pin, TR-09).
#: ``target_entity_type='scenario_definition'``.
COMPONENT_KIND_SCENARIO = "SCENARIO"
#: PA-2: a pinned ``proxy_mapping`` FR row (the private->public factor proxy weight consumed by
#: the proxy factor-exposure model; a later supersede is invisible to the pin, TR-09).
COMPONENT_KIND_PROXY_MAPPING = "PROXY_MAPPING"
#: PA-3: a pinned ``desmoothed_return_result`` per-period row (the regression TARGET consumed by
#: the proxy-weight model; the source run's immutable output — a re-run cannot move it, TR-09).
#: ``target_entity_type='desmoothed_return_result'``.
COMPONENT_KIND_DESMOOTHED_RETURN = "DESMOOTHED_RETURN"
#: PA-4: a pinned ``proxy_weight_estimate_result`` ESTIMATION_SUMMARY row (the ``residual_stdev``
#: consumed by total-parametric VaR; the row carries NO period-span dates — the appraisal cadence
#: is the DECLARED ``appraisal_days`` model parameter, OD-PA-4-D as refined. The cited estimate
#: run's immutable output — TR-09). ``target_entity_type='proxy_weight_estimate_result'``.
COMPONENT_KIND_PROXY_WEIGHT = "PROXY_WEIGHT"
SNAPSHOT_COMPONENT_KINDS = (
    COMPONENT_KIND_PORTFOLIO,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_VALUATION,
    COMPONENT_KIND_FX,
    COMPONENT_KIND_CURVE,
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_RETURN,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_BENCHMARK,
    COMPONENT_KIND_TRANSACTION,
    COMPONENT_KIND_PORTFOLIO_RETURN,
    COMPONENT_KIND_BENCHMARK_RETURN,
    COMPONENT_KIND_VAR,
    COMPONENT_KIND_SCENARIO,
    COMPONENT_KIND_PROXY_MAPPING,
    COMPONENT_KIND_DESMOOTHED_RETURN,
    COMPONENT_KIND_PROXY_WEIGHT,
)


class DatasetSnapshot(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, TimestampMixin, Base):
    """Reproducible input-snapshot HEADER (ENT-049, IA true-append-only). Created once, never
    mutated; ``id`` is the future referent of ``calculation_run.input_snapshot_id`` (P2-3)."""

    __tablename__ = "dataset_snapshot"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # controlled-vocab plain str
    as_of_valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # FROZEN at create; both the binder and verify use this concrete instant (never wall-clock
    # now).
    as_of_known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    binding_predicate_version: Mapped[str] = mapped_column(String(50), nullable=False)
    component_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # NO status column (created-complete; immutable). NO model_version (binds at the run, OD-P2-C).


class DatasetSnapshotComponent(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Per-input physical-version pin + captured value of a ``dataset_snapshot`` (ENT-050, IA).

    Polymorphic ``(target_entity_type, target_entity_id)`` — **no domain FK** (mirrors
    lineage_edge/
    identifier_xref). ``target_entity_id`` is the **surrogate row id** (the physical-version
    identity for FR; the current row id for EV). ``captured_content`` is the canonical-serialized
    immutable value; ``content_hash = sha256_hex(captured_content)``. ``pinned_system_from`` is
    NULL
    for the EV ``portfolio`` kind (no system axis); ``record_version`` is the authoritative EV
    drift
    discriminator.
    """

    __tablename__ = "dataset_snapshot_component"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # A physical version is pinned at most once per snapshot.
        UniqueConstraint(
            "snapshot_id",
            "component_kind",
            "target_entity_id",
            name="uq_dataset_snapshot_component_snapshot_kind_target",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    component_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(GUID, nullable=False)
    pinned_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_system_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_record_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# True append-only: the ORM guard (paired with the migration-0016 P0001 trigger) forbids
# update/delete on BOTH the header and the component. A snapshot is never mutated — a new input
# set is a new snapshot.
for _model in (DatasetSnapshot, DatasetSnapshotComponent):
    event.listen(_model, "before_update", _block_mutation)
    event.listen(_model, "before_delete", _block_mutation)
