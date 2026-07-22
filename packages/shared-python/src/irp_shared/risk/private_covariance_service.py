"""Governed PRIVATE-factor covariance (Ω_pp) binder (PPF-2, the 19th governed number, §2.1 arc
slice 2 — ``risk.covariance.private``).

A fail-closed SIBLING of the public sample-covariance binder (``covariance_service.py``): it reuses
the GENERIC ``estimate_covariance`` kernel UNCHANGED (the kernel takes aligned ``(date, Decimal)``
series — it never knew about daily-ness) and the SHARED ``covariance_result`` table
(``frequency=APPRAISAL``, ``run_type=COVARIANCE_PRIVATE``). The input is NOT captured factor
returns — it is PPF-1's governed pure-private APPRAISAL return series (``PURE_PRIVATE_PERIOD``
results), consumed from a ``PRIVATE_COVARIANCE_INPUT`` snapshot. The ``run_type`` is the sole table
discriminator; the public reads filter it (PPF-2 step 1), and these private reads filter it too, so
neither family can leak into the other.

The APPRAISAL-aware adjudicator is the ONLY substantive difference from the public binder: it groups
the pinned ``PURE_PRIVATE_RETURN`` components by segment, re-keys each on ``period_end`` (the
appraisal date axis), asserts an IDENTICAL interval vector across segments, and asserts each paired
``COMPONENT_KIND_FACTOR`` pin is a ``PRIVATE``/``APPRAISAL`` segment (the isolation guard — the
public binder's ``DAILY``/``SIMPLE`` check, inverted for this family).

One-way imports: ``risk -> {snapshot, marketdata(constants + the PPF-1 latest read for the BUILD
path only), calc, model}``; imports NO numpy (test-only); the COMPUTE path reads ONLY the pinned
snapshot content (the AD-014 invariant).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.reads import latest_run_rows, list_governed_results
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.models import (
    FACTOR_FAMILY_PRIVATE,
    FREQUENCY_APPRAISAL,
    RETURN_TYPE_SIMPLE,
)
from irp_shared.risk.bootstrap import (
    PRIVATE_COVARIANCE_MODEL_CODE,
    assert_model_version_of,
    declared_private_window_observations,
)
from irp_shared.risk.covariance_kernel import FactorSeriesPin, estimate_covariance
from irp_shared.risk.events import (
    RUN_TYPE_COVARIANCE_PRIVATE,
    STATISTIC_TYPE_COVARIANCE,
    PurePrivateCovarianceActor,
)
from irp_shared.risk.models import CovarianceResult
from irp_shared.risk.private_factor_service import latest_pure_private_factor_for_segment
from irp_shared.snapshot import (
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_PURE_PRIVATE_RETURN,
    PURPOSE_PRIVATE_COVARIANCE_INPUT,
    SnapshotActor,
    build_private_covariance_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the covariance pattern).
_COMPLETENESS_RULE_CODE = "risk.covariance.private.completeness"
#: How many defect identifiers the FAILED ``failure_reason`` names (evidence, bounded).
_MAX_GAPS_IN_REASON = 10


class PrivateCovarianceInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Maps to 422."""


class PrivateCovarianceNotVisible(Exception):
    """Raised when a private ``covariance_result`` id is not visible in the acting tenant scope."""

    def __init__(self, covariance_id: str) -> None:
        super().__init__(
            f"private covariance_result {covariance_id} is not visible in the current tenant"
        )
        self.covariance_id = str(covariance_id)


class PrivateCovarianceRunNotVisible(Exception):
    """Raised when a private-covariance ``calculation_run`` id is not visible in the acting
    tenant (or is not a ``COVARIANCE_PRIVATE`` run)."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"private covariance run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class PrivateCovarianceRunResult:
    """The outcome of :func:`run_private_covariance`: the ``calculation_run`` + status + the matrix
    rows. ``status`` is ``COMPLETED`` (with ``rows``) or ``FAILED`` (a committed FAILED run + ZERO
    rows + a defect-naming ``failure_reason`` — the covariance defensive-gate precedent)."""

    run: CalculationRun
    status: str
    rows: list[CovarianceResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the kernel series + the run-uniform captured descriptors."""

    series: list[FactorSeriesPin]
    return_type: str
    frequency: str
    n_observations: int
    window_start: date
    window_end: date


def _parse_pins(
    comps: list[Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into per-segment pure-private row lists (keyed by the
    lowercase ``segment_factor_id``) + a segment-definition map keyed by (lowercase) factor id
    (PURE — no live read; the AD-014 invariant)."""
    series_by_segment: dict[str, list[dict[str, Any]]] = {}
    factor_pins: dict[str, dict[str, Any]] = {}
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_PURE_PRIVATE_RETURN:
            series_by_segment.setdefault(str(data["segment_factor_id"]).lower(), []).append(data)
        elif comp.component_kind == COMPONENT_KIND_FACTOR:
            factor_pins[str(data["id"]).lower()] = data
    return series_by_segment, factor_pins


def _adjudicate_pins(
    series_by_segment: dict[str, list[dict[str, Any]]],
    factor_pins: dict[str, dict[str, Any]],
    *,
    declared_window: int,
) -> _ParsedInput:
    """PRE-CREATE adjudication of the pinned input (both entry paths): >= 2 segment series; every
    series exactly ``declared_window`` periods; IDENTICAL ``(period_start, period_end)`` interval
    vectors across segments (re-keyed on ``period_end`` for the kernel); a paired
    ``COMPONENT_KIND_FACTOR`` pin per segment that is a ``PRIVATE``/``APPRAISAL`` factor (the
    isolation guard — the public binder's ``DAILY``/``SIMPLE`` check, inverted). Raises
    :class:`PrivateCovarianceInputError`; returns the kernel series + the run-uniform pins."""
    if len(series_by_segment) < 2:
        raise PrivateCovarianceInputError(
            f"the snapshot pins {len(series_by_segment)} pure-private segment series — "
            f"private covariance needs >= 2"
        )
    intervals0: list[tuple[str, str]] | None = None
    pins: list[FactorSeriesPin] = []
    span_starts: list[date] = []
    span_ends: list[date] = []
    for seg_id, rows in sorted(series_by_segment.items()):
        factor_pin = factor_pins.get(seg_id)
        if factor_pin is None:
            raise PrivateCovarianceInputError(
                f"segment {seg_id} has no paired COMPONENT_KIND_FACTOR definition pin"
            )
        code = factor_pin["factor_code"]
        if factor_pin.get("factor_family") != FACTOR_FAMILY_PRIVATE:
            raise PrivateCovarianceInputError(
                f"segment {code!r} factor_family {factor_pin.get('factor_family')!r} != "
                f"{FACTOR_FAMILY_PRIVATE} — a public factor cannot enter Ω_pp"
            )
        if factor_pin.get("frequency") != FREQUENCY_APPRAISAL:
            raise PrivateCovarianceInputError(
                f"segment {code!r} frequency {factor_pin.get('frequency')!r} != "
                f"{FREQUENCY_APPRAISAL}"
            )
        if len(rows) != declared_window:
            raise PrivateCovarianceInputError(
                f"segment {code!r} pins {len(rows)} appraisal periods — the registered model "
                f"declares window_observations={declared_window}"
            )
        rows_sorted = sorted(rows, key=lambda r: r["period_end"])
        intervals = [(r["period_start"], r["period_end"]) for r in rows_sorted]
        if intervals0 is None:
            intervals0 = intervals
        elif intervals != intervals0:
            raise PrivateCovarianceInputError(
                f"misaligned windows: segment {code!r} intervals differ from the first segment"
            )
        pins.append(
            FactorSeriesPin(
                id=seg_id,
                factor_code=code,
                rows=tuple(
                    (date.fromisoformat(r["period_end"]), Decimal(r["metric_value"]))
                    for r in rows_sorted
                ),
            )
        )
        span_starts.append(date.fromisoformat(rows_sorted[0]["period_start"]))
        span_ends.append(date.fromisoformat(rows_sorted[-1]["period_end"]))
    assert intervals0 is not None  # len(series_by_segment) >= 2 guarantees the first iteration ran
    return _ParsedInput(
        series=pins,
        return_type=RETURN_TYPE_SIMPLE,
        frequency=FREQUENCY_APPRAISAL,
        n_observations=declared_window,
        window_start=min(span_starts),  # aligned intervals ⇒ identical across segments
        window_end=max(span_ends),
    )


def _build_rows(
    parsed: _ParsedInput,
    matrix: dict[tuple[str, str], Decimal],
    *,
    run: CalculationRun,
    snapshot_id: str,
    model_version_id: str,
    acting_tenant: str,
) -> tuple[list[CovarianceResult], list[str]]:
    """Materialize the kernel output into ``covariance_result`` rows (deterministic canonical-pair
    order; ``statistic_type=COVARIANCE``, ``frequency=APPRAISAL``) + collect the defensive
    post-compute gaps (non-finite / negative diagonal — unreachable for the sample estimator over
    adjudicated pins; rows are NOT written when gaps exist). The covariance ``_build_rows`` twin."""
    code_of = {pin.id: pin.factor_code for pin in parsed.series}
    rows: list[CovarianceResult] = []
    gaps: list[str] = []
    for (id_1, id_2), value in sorted(matrix.items()):
        if not value.is_finite():
            gaps.append(f"non-finite-covariance:{code_of[id_1]}:{code_of[id_2]}")
            continue
        if id_1 == id_2 and value < 0:
            gaps.append(f"negative-variance:{code_of[id_1]}")
            continue
        rows.append(
            CovarianceResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=str(snapshot_id),
                model_version_id=str(model_version_id),
                factor_id_1=id_1,
                factor_id_2=id_2,
                factor_code_1=code_of[id_1],
                factor_code_2=code_of[id_2],
                statistic_type=STATISTIC_TYPE_COVARIANCE,
                return_type=parsed.return_type,
                frequency=parsed.frequency,
                n_observations=parsed.n_observations,
                window_start=parsed.window_start,
                window_end=parsed.window_end,
                covariance_value=value,
            )
        )
    return rows, gaps


def run_private_covariance(
    session: Session,
    *,
    acting_tenant: str,
    actor: PurePrivateCovarianceActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    segment_factor_ids: list[str] | None = None,
    as_of_valid_at: Any = None,
    as_of_known_at: Any = None,
    snapshot_id: str | None = None,
) -> PrivateCovarianceRunResult:
    """Run a governed private-factor covariance (Ω_pp) estimation. Build-in-request (default —
    ``segment_factor_ids``: resolves each segment's LATEST COMPLETED pure-private run, then builds a
    ``PRIVATE_COVARIANCE_INPUT`` snapshot over their common appraisal grid at the version's DECLARED
    ``window_observations``) or consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned
    content pre-create. Reuses the generic ``estimate_covariance`` kernel + the shared
    ``covariance_result`` table (the covariance failure model + the AD-014/CTRL-003 invariants)."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/run-audit) ---
    if not code_version:
        raise PrivateCovarianceInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise PrivateCovarianceInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise PrivateCovarianceInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise PrivateCovarianceInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    if snapshot_id is not None and (
        segment_factor_ids is not None or as_of_valid_at is not None or as_of_known_at is not None
    ):
        raise PrivateCovarianceInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(segment_factor_ids/as_of_*), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3) + the DECLARED window (the count of
    # common appraisal periods — version identity, parsed from the registered assumptions).
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=PRIVATE_COVARIANCE_MODEL_CODE,
    )
    declared_window = declared_private_window_observations(session, version)

    # --- Bind the pure-private-series snapshot (cross-tenant/unknown/ill-formed ⇒ refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_PRIVATE_COVARIANCE_INPUT:
            raise PrivateCovarianceInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != "
                f"{PURPOSE_PRIVATE_COVARIANCE_INPUT}"
            )
    else:
        if not segment_factor_ids:
            raise PrivateCovarianceInputError(
                "segment_factor_ids are required to build a private covariance snapshot"
            )
        distinct = list(dict.fromkeys(str(sid).lower() for sid in segment_factor_ids))
        if len(distinct) != len(segment_factor_ids):
            raise PrivateCovarianceInputError(
                "duplicate segment factor ids — an ambiguous series set is refused"
            )
        if len(distinct) < 2:
            raise PrivateCovarianceInputError(
                f"private covariance needs >= 2 segments (got {len(distinct)})"
            )
        # Resolve each segment's LATEST COMPLETED pure-private run (the run-bound input the builder
        # pins). A segment with no completed run fails closed BEFORE any write.
        run_ids: list[str] = []
        for sid in distinct:
            latest = latest_pure_private_factor_for_segment(
                session, acting_tenant=acting_tenant, segment_factor_id=sid, as_of=as_of_known_at
            )
            if not latest:
                raise PrivateCovarianceInputError(
                    f"segment {sid} has no COMPLETED pure-private factor run to consume"
                )
            run_ids.append(str(latest[0].calculation_run_id))
        # Fail-closes on < declared_window common appraisal periods BEFORE any write (409).
        snapshot = build_private_covariance_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            pure_private_run_ids=run_ids,
            window_observations=declared_window,
            as_of_valid_at=as_of_valid_at,
            as_of_known_at=as_of_known_at,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths) ---
    series_by_segment, factor_pins = _parse_pins(
        list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    )
    parsed = _adjudicate_pins(series_by_segment, factor_pins, declared_window=declared_window)

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[CovarianceResult], list[str]]:
        matrix = estimate_covariance(parsed.series)  # the pure GENERIC kernel over the pins ONLY
        return _build_rows(
            parsed,
            matrix,
            run=run,
            snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            acting_tenant=acting_tenant,
        )

    def _format_reason(gate: Exception, gaps: list[str]) -> str:
        detail = "; ".join(gaps[:_MAX_GAPS_IN_REASON])
        more = (
            f" (+{len(gaps) - _MAX_GAPS_IN_REASON} more)" if len(gaps) > _MAX_GAPS_IN_REASON else ""
        )
        return f"{gate} — {detail}{more}"

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_COVARIANCE_PRIVATE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=(
            "Private covariance run output sanity (every element finite; every variance "
            "non-negative)"
        ),
        rule_target_entity_type="covariance_result",
        result_entity_type="covariance_result",
        compute=_compute,
        format_reason=_format_reason,
    )
    return PrivateCovarianceRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


# ---------- Rule-7 reads (run_type-filtered against the shared covariance_result table) ----------
def list_private_covariances(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[CovarianceResult]:
    """The Ω_pp matrix rows of a private-covariance run (tenant-scoped, canonical-pair order). The
    run id identifies the run — no ``run_type`` filter needed here (a public run id yields the
    public matrix; use :func:`resolve_private_covariance_run` to family-check an id)."""
    return list(
        session.execute(
            select(CovarianceResult)
            .where(
                CovarianceResult.calculation_run_id == str(run_id),
                CovarianceResult.tenant_id == str(acting_tenant),
            )
            .order_by(CovarianceResult.factor_id_1, CovarianceResult.factor_id_2)
        )
        .scalars()
        .all()
    )


def latest_private_covariances(
    session: Session,
    *,
    acting_tenant: str,
    as_of: Any = None,  # datetime | None — the run cutoff
) -> list[CovarianceResult]:
    """Latest-resolver: the newest COMPLETED ``COVARIANCE_PRIVATE`` run's FULL Ω_pp matrix (empty
    when none). The ``run_type`` filter keeps the PUBLIC covariance out of this shared-table read
    (the mirror of the step-1 public-read fix). A run IS the matrix identity — no entity sub-filter;
    rows in canonical pair order. ``as_of=None`` = now."""
    return latest_run_rows(
        list_governed_results(
            session,
            CovarianceResult,
            acting_tenant=acting_tenant,
            run_type=RUN_TYPE_COVARIANCE_PRIVATE,
            as_of=as_of,
            order_by=(CovarianceResult.factor_id_1, CovarianceResult.factor_id_2),
        )
    )


def resolve_private_covariance_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a ``COVARIANCE_PRIVATE`` ``calculation_run`` by ``run_id`` with an EXPLICIT tenant
    predicate + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run. Raises
    :class:`PrivateCovarianceRunNotVisible` on a hidden/unknown id or a non-private-covariance
    run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_COVARIANCE_PRIVATE,
        not_visible=PrivateCovarianceRunNotVisible,
    )


def resolve_private_covariance(
    session: Session, covariance_id: str, *, acting_tenant: str
) -> CovarianceResult:
    """Resolve one PRIVATE ``covariance_result`` row by id with an EXPLICIT tenant predicate + the
    ``RUN_TYPE_COVARIANCE_PRIVATE`` family filter (a join on the bound run). The run_type filter
    keeps a public covariance row (same table) from resolving through the private by-id surface —
    the ``calc/reads.py`` shared-table contract, mirroring the step-1 public resolver."""
    row = session.execute(
        select(CovarianceResult)
        .join(CalculationRun, CalculationRun.run_id == CovarianceResult.calculation_run_id)
        .where(
            CovarianceResult.id == str(covariance_id),
            CovarianceResult.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_COVARIANCE_PRIVATE,
        )
    ).scalar_one_or_none()
    if row is None:
        raise PrivateCovarianceNotVisible(str(covariance_id))
    return row
