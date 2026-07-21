"""Covariance binder (P3-4, ENT-051 — sample v1, the third governed risk number).

``run_covariance`` produces ``covariance_result`` rows ONLY when bound to a ``dataset_snapshot``
(``COVARIANCE_INPUT``, pinning the ``factor`` EV definitions + the aligned ``factor_return``
windows) + a complete ``calculation_run`` + a **REGISTERED ``model_version`` OF THE COVARIANCE
MODEL whose declared ``window_observations`` fixed the estimation window** (AD-014 / FW-RUN /
TR-15 / CTRL-003 / OD-P3-4-G — the ``run_factor_exposure`` exemplar mirrored step-for-step, plus
the window-as-version-identity tightening: the binder reads the DECLARED window from the version's
assumptions; it is never a free request parameter). The number is the equal-weighted unbiased
sample covariance (``irp_shared.risk.covariance_kernel``): one row per canonical unordered factor
pair INCLUDING the diagonal — ``F·(F+1)/2`` rows per COMPLETED run; PSD by Gram construction.

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned
``COMPONENT_KIND_FACTOR_RETURN``/``COMPONENT_KIND_FACTOR`` captured content** — it makes **NO**
live factor/return read, so a later vendor supersede/correction of a window return cannot change
a historical covariance (TR-09, test-proven).

Failure model (the P3-3 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing ``code_version``/``environment_id``/initiator/
  ``model_version_id``; an unregistered or WRONG-MODEL version; a malformed declared window; a
  sub-two / duplicate / non-DAILY factor list (build path); a wrong-purpose snapshot; **pinned
  content that is not a well-formed v1 input** — fewer than two ``FACTOR_RETURN`` series, a
  series row-count != the declared window, misaligned date sets, a missing paired
  ``COMPONENT_KIND_FACTOR`` pin, or a non-``SIMPLE``/non-``DAILY`` series): **raise BEFORE
  ``create_run``** ⇒ ZERO run + ZERO rows + ZERO run-audit. A snapshot minted elsewhere cannot
  smuggle a short/misaligned/wrong-N window past the gate.
- **Post-create FAILED** (the defensive post-compute gate — a non-finite value or a negative
  diagonal; unreachable for the sample estimator over adjudicated pins, recorded
  defense-in-depth): FAILED run (``outcome='failure'``) + ``DATA.VALIDATE`` DQ evidence + ZERO
  rows + a defect-naming ``failure_reason``.
- **Emit-path** raises propagate ⇒ the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``risk -> {snapshot, marketdata(constants + live resolve_factor for the BUILD
path only), calc, model, lineage, dq, audit, db}``; imports NO live return reader into the
COMPUTE path; imports NO numpy (test-only); no VaR/ES/scenario/stress/shrinkage/EWMA symbol;
nothing imports ``risk``.
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
from irp_shared.marketdata.factor import resolve_factor
from irp_shared.marketdata.models import FREQUENCY_DAILY, RETURN_TYPE_SIMPLE
from irp_shared.risk.bootstrap import (
    COVARIANCE_MODEL_CODE,
    assert_model_version_of,
    declared_window_observations,
)
from irp_shared.risk.covariance_kernel import FactorSeriesPin, estimate_covariance
from irp_shared.risk.events import RUN_TYPE_COVARIANCE, STATISTIC_TYPE_COVARIANCE, CovarianceActor
from irp_shared.risk.models import CovarianceResult
from irp_shared.snapshot import (
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_RETURN,
    PURPOSE_COVARIANCE_INPUT,
    SnapshotActor,
    build_covariance_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the P3-1/P3-3 pattern).
_COMPLETENESS_RULE_CODE = "risk.covariance.completeness"
#: How many defect identifiers the FAILED ``failure_reason`` names (evidence, bounded).
_MAX_GAPS_IN_REASON = 10


class CovarianceInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Maps to 422."""


class CovarianceNotVisible(Exception):
    """Raised when a ``covariance_result`` id is not visible in the acting tenant scope."""

    def __init__(self, covariance_id: str) -> None:
        super().__init__(f"covariance_result {covariance_id} is not visible in the current tenant")
        self.covariance_id = str(covariance_id)


class CovarianceRunNotVisible(Exception):
    """Raised when a covariance ``calculation_run`` id is not visible in the acting tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"covariance run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class CovarianceRunResult:
    """The outcome of ``run_covariance``: the ``calculation_run`` + status + the matrix rows
    produced. ``status`` is ``COMPLETED`` (with ``rows``) or ``FAILED`` (the defensive
    post-create gate: a committed FAILED run + ZERO rows + a defect-naming
    ``failure_reason``)."""

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


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw series dicts + a factor-definition map
    keyed by (lowercase) factor id (PURE — no live read; the AD-014 invariant)."""
    series_raw: list[dict[str, Any]] = []
    factor_pins: dict[str, dict[str, Any]] = {}
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_FACTOR_RETURN:
            series_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_FACTOR:
            factor_pins[str(data["id"]).lower()] = data
    return series_raw, factor_pins


def _adjudicate_pins(
    series_raw: list[dict[str, Any]],
    factor_pins: dict[str, dict[str, Any]],
    *,
    declared_window: int,
) -> _ParsedInput:
    """PRE-CREATE adjudication of the pinned input (both entry paths — the OD-P3-4-H named
    checks): >= 2 ``FACTOR_RETURN`` series; every series exactly ``declared_window`` rows;
    IDENTICAL date sets across series; a paired ``COMPONENT_KIND_FACTOR`` pin per series; the v1
    ``SIMPLE``/``DAILY`` vocabulary. Raises :class:`CovarianceInputError`; returns the kernel
    series + the run-uniform descriptors."""
    if len(series_raw) < 2:
        raise CovarianceInputError(
            f"the snapshot pins {len(series_raw)} FACTOR_RETURN series — covariance needs >= 2"
        )
    dates0: list[str] | None = None
    pins: list[FactorSeriesPin] = []
    seen_fids: set[str] = set()
    for data in series_raw:
        fid = str(data["factor_id"]).lower()
        code = data["factor_code"]
        if fid in seen_fids:  # a duplicate series would silently collapse the matrix shape
            raise CovarianceInputError(
                f"duplicate FACTOR_RETURN series for factor {code!r} — refused"
            )
        seen_fids.add(fid)
        rows = data["rows"]
        if len(rows) != declared_window:
            raise CovarianceInputError(
                f"series {code!r} pins {len(rows)} observations — the registered model "
                f"declares window_observations={declared_window}"
            )
        dates = [r["return_date"] for r in rows]
        if dates0 is None:
            dates0 = dates
        elif dates != dates0:
            raise CovarianceInputError(
                f"misaligned windows: series {code!r} dates differ from the first pinned series"
            )
        factor_pin = factor_pins.get(fid)
        if factor_pin is None:
            raise CovarianceInputError(
                f"series {code!r} has no paired COMPONENT_KIND_FACTOR definition pin"
            )
        if data.get("return_type") != RETURN_TYPE_SIMPLE:
            raise CovarianceInputError(
                f"series {code!r} return_type {data.get('return_type')!r} != "
                f"{RETURN_TYPE_SIMPLE} (v1)"
            )
        if factor_pin.get("frequency") != FREQUENCY_DAILY:
            raise CovarianceInputError(
                f"factor {code!r} frequency {factor_pin.get('frequency')!r} != "
                f"{FREQUENCY_DAILY} (v1)"
            )
        pins.append(
            FactorSeriesPin(
                id=fid,
                factor_code=code,
                rows=tuple(
                    (date.fromisoformat(r["return_date"]), Decimal(r["return_value"])) for r in rows
                ),
            )
        )
    assert dates0 is not None  # len(series_raw) >= 2 guarantees the first iteration ran
    return _ParsedInput(
        series=pins,
        return_type=RETURN_TYPE_SIMPLE,
        frequency=FREQUENCY_DAILY,
        n_observations=declared_window,
        window_start=date.fromisoformat(dates0[0]),
        window_end=date.fromisoformat(dates0[-1]),
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
    """Materialize the kernel output into rows (deterministic order) + collect the defensive
    post-compute gaps (non-finite value / negative diagonal — should be unreachable for the
    sample estimator over adjudicated pins; rows are NOT written when gaps exist)."""
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


def run_covariance(
    session: Session,
    *,
    acting_tenant: str,
    actor: CovarianceActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    factor_ids: list[str] | None = None,
    as_of_valid_at: Any = None,
    as_of_known_at: Any = None,
    snapshot_id: str | None = None,
) -> CovarianceRunResult:
    """Run a governed sample-covariance estimation. Build-in-request (default — ``factor_ids``:
    builds a ``COVARIANCE_INPUT`` snapshot pinning the definitions + aligned windows at the
    version's DECLARED ``window_observations``) or consume-existing (``snapshot_id``). BOTH paths
    adjudicate the pinned content pre-create. See the module docstring for the failure model +
    the AD-014 / CTRL-003 / OD-P3-4-G invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/run-audit) ---
    if not code_version:
        raise CovarianceInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise CovarianceInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise CovarianceInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise CovarianceInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if snapshot_id is not None and (
        factor_ids is not None or as_of_valid_at is not None or as_of_known_at is not None
    ):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY —
        # an ambiguous request must be refused, never guessed.
        raise CovarianceInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(factor_ids/as_of_*), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3) + the DECLARED window (OD-P3-4-G:
    # the estimation window is version identity, parsed from the registered assumptions — never a
    # free request parameter).
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=COVARIANCE_MODEL_CODE,
    )
    declared_window = declared_window_observations(session, version)

    # --- Bind the definitions+windows snapshot (cross-tenant/unknown/ill-formed ⇒ refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_COVARIANCE_INPUT:
            raise CovarianceInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_COVARIANCE_INPUT}"
            )
    else:
        if not factor_ids:
            raise CovarianceInputError("factor_ids are required to build a covariance snapshot")
        # Lowercase-normalized (PG resolves GUIDs case-insensitively — a case-variant duplicate
        # is the same factor; the 2026-07 review fix).
        distinct = list(dict.fromkeys(str(fid).lower() for fid in factor_ids))
        if len(distinct) != len(factor_ids):
            raise CovarianceInputError("duplicate factor ids — an ambiguous series set is refused")
        if len(distinct) < 2:
            raise CovarianceInputError(f"covariance needs >= 2 factors (got {len(distinct)})")
        for fid in distinct:
            factor = resolve_factor(session, fid, acting_tenant=acting_tenant)
            if factor.frequency != FREQUENCY_DAILY:
                raise CovarianceInputError(
                    f"factor {factor.factor_code!r} frequency {factor.frequency!r} != "
                    f"{FREQUENCY_DAILY} (v1)"
                )
        # Fail-closes on < declared_window common dates BEFORE any write
        # (CovarianceSnapshotError, 409).
        snapshot = build_covariance_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            factor_ids=distinct,
            window_observations=declared_window,
            as_of_valid_at=as_of_valid_at,
            as_of_known_at=as_of_known_at,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths; OD-P3-4-H): short /
    # misaligned / wrong-window / unpaired / wrong-vocab pins all refuse HERE — before a run (or
    # any run-audit) can exist.
    series_raw, factor_pins = _parse_pins(
        list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    )
    parsed = _adjudicate_pins(series_raw, factor_pins, declared_window=declared_window)

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[CovarianceResult], list[str]]:
        # The pure kernel over the adjudicated pins ONLY (no live read — the AD-014 invariant).
        matrix = estimate_covariance(parsed.series)
        return _build_rows(
            parsed,
            matrix,
            run=run,
            snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            acting_tenant=acting_tenant,
        )

    def _format_reason(gate: Exception, gaps: list[str]) -> str:  # verbatim P3-4 format
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
        run_type=RUN_TYPE_COVARIANCE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=(
            "Covariance run output sanity (every element finite; every variance non-negative)"
        ),
        rule_target_entity_type="covariance_result",
        result_entity_type="covariance_result",
        compute=_compute,
        format_reason=_format_reason,
    )
    return CovarianceRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_covariances(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[CovarianceResult]:
    """The covariance-matrix rows of a run (tenant-scoped, canonical-pair order)."""
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


def latest_covariances(
    session: Session,
    *,
    acting_tenant: str,
    as_of=None,  # noqa: ANN001  (datetime | None — the API-1 run cutoff)
) -> list[CovarianceResult]:
    """API-1 latest-resolver (Class B): the newest COMPLETED covariance run's FULL matrix (empty
    when none). A covariance run IS the matrix identity — there is no entity sub-filter; the whole
    matrix is the readable unit. Rows present in canonical pair order ``(factor_id_1,
    factor_id_2)``. ``as_of=None`` = now."""
    return latest_run_rows(
        list_governed_results(
            session,
            CovarianceResult,
            acting_tenant=acting_tenant,
            as_of=as_of,
            order_by=(CovarianceResult.factor_id_1, CovarianceResult.factor_id_2),
        )
    )


def resolve_covariance_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve a COVARIANCE ``calculation_run`` by ``run_id`` with an EXPLICIT tenant predicate +
    ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable refusal
    evidence). Raises :class:`CovarianceRunNotVisible` on a hidden/unknown id or a non-covariance
    run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_COVARIANCE,
        not_visible=CovarianceRunNotVisible,
    )


def resolve_covariance(
    session: Session, covariance_id: str, *, acting_tenant: str
) -> CovarianceResult:
    """Resolve one ``covariance_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(CovarianceResult).where(
            CovarianceResult.id == str(covariance_id),
            CovarianceResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise CovarianceNotVisible(str(covariance_id))
    return row
