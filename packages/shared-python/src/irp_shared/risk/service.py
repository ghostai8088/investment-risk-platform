"""Sensitivity binder (P3-1, ENT-028) — the first reproducible governed risk number.

``run_sensitivities`` produces ``sensitivity_result`` rows ONLY when bound to a
``dataset_snapshot``
(``SENSITIVITY_INPUT``, pinning the curve(s)) + a complete ``calculation_run`` + a **REGISTERED
``model_version``** (the model-governance hardening vs the model-less exposure rollup; AD-014 /
FW-RUN / TR-15 / CTRL-003). The number is the closed-form curve-node DV01 / spread-DV01 of a unit
zero-coupon claim (``irp_shared.risk.kernel``), curve-intrinsic (OD-P3-1-A) — NO
instrument/position
attribution, NO interpolation, NO pricing engine.

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned
``COMPONENT_KIND_CURVE`` captured content** (curve header + node set) — it makes **NO** live
``reconstruct_curve_as_of`` / ``list_curve_points`` / ``resolve_curve`` read, so a later curve
correction cannot change a historical sensitivity.

Model governance (the load-bearing hardening): ``assert_registered_model_version`` is called in the
**pre-create gate** — an unknown/unregistered ``model_version_id`` raises
``UnregisteredModelError``
BEFORE the run is created ⇒ ZERO run/result/audit. No sensitivity number escapes the model
inventory.

Failure model (the P2-3 precedent, split by timing):
- **Pre-create refusal** (missing
``code_version``/``environment_id``/initiator/``model_version_id``;
  an unregistered model_version; an unbuildable/cross-tenant/missing-curve snapshot): **raise
  BEFORE
  ``create_run``** ⇒ ZERO run + ZERO result + ZERO audit.
- **Post-create FAILED** (the DQ gate failing AFTER RUNNING — a curve with no usable nodes): mark
the
  run FAILED (``outcome='failure'``) and **return** a FAILED result ⇒ a committed FAILED run +
  ``CALC.RUN_STATUS_CHANGE`` + ZERO result rows.
- **Emit-path** raises propagate ⇒ the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``risk -> {snapshot, marketdata(constants/kernel), calc, model, lineage, dq,
audit, db}``; imports NO live curve resolver into the compute; imports no
factor/covariance/VaR/scenario/stress symbol; nothing imports ``risk``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.reads import latest_run_rows, list_governed_results
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.models import (
    VALUE_TYPE_DISCOUNT_FACTOR,
    VALUE_TYPE_SPREAD,
    VALUE_TYPE_ZERO_RATE,
)
from irp_shared.risk.bootstrap import SENSITIVITY_MODEL_CODE, assert_model_version_of
from irp_shared.risk.events import (
    RUN_TYPE_SENSITIVITY,
    SENSITIVITY_TYPE_DV01,
    SENSITIVITY_TYPE_SPREAD_DV01,
    SensitivityActor,
)
from irp_shared.risk.kernel import node_dv01, node_spread_dv01
from irp_shared.risk.models import SensitivityResult
from irp_shared.snapshot import (
    COMPONENT_KIND_CURVE,
    PURPOSE_SENSITIVITY_INPUT,
    CurveSelector,
    SnapshotActor,
    build_curve_snapshot,
    list_components,
    resolve_snapshot,
)

#: The bump convention recorded on each row (1.0000 = 1bp).
_BUMP_BPS = Decimal("1.0000")
#: Per-tenant governed completeness DQ rule (resolve-or-register; the exposure pattern).
_COMPLETENESS_RULE_CODE = "risk.sensitivity.completeness"


class SensitivityInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no audit). Maps to 422."""


class SensitivityNotVisible(Exception):
    """Raised when a ``sensitivity_result`` id is not visible in the acting tenant scope."""

    def __init__(self, sensitivity_id: str) -> None:
        super().__init__(
            f"sensitivity_result {sensitivity_id} is not visible in the current tenant"
        )
        self.sensitivity_id = str(sensitivity_id)


class SensitivityRunNotVisible(Exception):
    """Raised when a sensitivity ``calculation_run`` id is not visible in the acting tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"sensitivity run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class SensitivityRunResult:
    """The outcome of ``run_sensitivities``: the ``calculation_run`` + status + the rows produced.
    ``status`` is ``COMPLETED`` (with ``rows``) or ``FAILED`` (a post-create gate failure: a
    committed FAILED run + ZERO rows + ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[SensitivityResult] = field(default_factory=list)
    failure_reason: str | None = None


def _build_rows(
    comps: list[Any],
    *,
    run: CalculationRun,
    snapshot_id: str,
    model_version_id: str,
    acting_tenant: str,
) -> tuple[list[SensitivityResult], list[str]]:
    """Compute one sensitivity row per usable node of each pinned ``COMPONENT_KIND_CURVE``
    component
    (PURE — reads the captured content, no live curve read). ``ZERO_RATE``/``DISCOUNT_FACTOR`` ->
    ``DV01``; ``SPREAD`` -> ``SPREAD_DV01``; ``PAR_RATE`` (+ unknown) nodes are skipped (deferred).
    Returns ``(rows, gaps)`` — ``gaps`` names every pinned curve with ZERO usable nodes (the
    fail-closed DQ signal; rows are NOT written when gaps exist)."""
    rows: list[SensitivityResult] = []
    gaps: list[str] = []
    for comp in comps:
        if comp.component_kind != COMPONENT_KIND_CURVE:
            continue
        data = json.loads(comp.captured_content)
        curve_id = data["id"]
        usable = 0
        for node in data["nodes"]:
            value_type = node["value_type"]
            tenor_days = int(node["tenor_days"])
            point_value = Decimal(node["point_value"])
            if value_type in (VALUE_TYPE_ZERO_RATE, VALUE_TYPE_DISCOUNT_FACTOR):
                value = node_dv01(tenor_days, value_type, point_value)
                sensitivity_type = SENSITIVITY_TYPE_DV01
            elif value_type == VALUE_TYPE_SPREAD:
                value = node_spread_dv01(tenor_days, point_value)
                sensitivity_type = SENSITIVITY_TYPE_SPREAD_DV01
            else:
                continue  # PAR_RATE (+ any future type): not computed in v1 (deferred)
            usable += 1
            rows.append(
                SensitivityResult(
                    tenant_id=str(acting_tenant),
                    calculation_run_id=run.run_id,
                    input_snapshot_id=str(snapshot_id),
                    model_version_id=str(model_version_id),
                    curve_id=curve_id,
                    curve_type=data["curve_type"],
                    currency_code=data["currency_code"],
                    reference_key=data["reference_key"],
                    value_type=value_type,
                    tenor_days=tenor_days,
                    tenor_label=node["tenor_label"],
                    sensitivity_type=sensitivity_type,
                    sensitivity_value=value,
                    bump_bps=_BUMP_BPS,
                )
            )
        if usable == 0:
            gaps.append(f"no-usable-nodes:{curve_id}")
    return rows, gaps


def run_sensitivities(
    session: Session,
    *,
    acting_tenant: str,
    actor: SensitivityActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    curve_selectors: list[CurveSelector] | None = None,
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
    snapshot_id: str | None = None,
) -> SensitivityRunResult:
    """Run a governed analytic-sensitivity calculation. Build-in-request (default —
    ``curve_selectors``
    + ``as_of_valid_at``: builds a ``SENSITIVITY_INPUT`` snapshot pinning the curve(s)) or
    consume-existing (``snapshot_id``). See the module docstring for the failure model + the AD-014
    /
    CTRL-003 invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/audit) ---
    if not code_version:
        raise SensitivityInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise SensitivityInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise SensitivityInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise SensitivityInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if snapshot_id is not None and (
        curve_selectors is not None or as_of_valid_at is not None or as_of_known_at is not None
    ):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY —
        # an ambiguous request must be refused, never guessed.
        raise SensitivityInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(curve_selectors/as_of_*), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3): a REGISTERED model_version OF THE
    # SENSITIVITY MODEL is MANDATORY. An unknown/unregistered version raises UnregisteredModelError
    # and a version of a DIFFERENT model family raises WrongModelVersionError — both BEFORE the run
    # is created ⇒ zero run/result (the 2026-07 review hardening, reachable once a second model
    # family exists).
    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=SENSITIVITY_MODEL_CODE,
    )

    # --- Bind the curve snapshot (cross-tenant/unknown/missing-curve ⇒ pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_SENSITIVITY_INPUT:
            raise SensitivityInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} "
                f"!= {PURPOSE_SENSITIVITY_INPUT}"
            )
    else:
        if not curve_selectors or as_of_valid_at is None:
            raise SensitivityInputError(
                "curve_selectors + as_of_valid_at are required to build a sensitivity snapshot"
            )
        snapshot = build_curve_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            curve_selectors=list(curve_selectors),
            as_of_valid_at=as_of_valid_at,
            as_of_known_at=as_of_known_at,
        )

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[SensitivityResult], list[str]]:
        return _build_rows(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant),
            run=run,
            snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            acting_tenant=acting_tenant,
        )

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_SENSITIVITY,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="Sensitivity run input completeness (usable curve nodes)",
        rule_target_entity_type="sensitivity_result",
        result_entity_type="sensitivity_result",
        compute=_compute,
        format_reason=lambda gate, gaps: str(gate),  # verbatim P3-1 format
    )
    return SensitivityRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_sensitivities(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[SensitivityResult]:
    """The sensitivity rows of a run (tenant-scoped, stable order)."""
    return list(
        session.execute(
            select(SensitivityResult)
            .where(
                SensitivityResult.calculation_run_id == str(run_id),
                SensitivityResult.tenant_id == str(acting_tenant),
            )
            .order_by(
                SensitivityResult.curve_id,
                SensitivityResult.value_type,
                SensitivityResult.tenor_days,
                SensitivityResult.sensitivity_type,
            )
        )
        .scalars()
        .all()
    )


def latest_sensitivities(
    session: Session,
    *,
    acting_tenant: str,
    curve_id: str | None = None,
    as_of=None,  # noqa: ANN001  (datetime | None — the API-1 run cutoff)
) -> list[SensitivityResult]:
    """API-1 latest-resolver (Class B): the newest COMPLETED sensitivity run's rows, optionally
    row-filtered to a ``curve_id`` (a run may span several curves; the filter narrows to the
    queried curve's own rows within that run; absent = the whole run). Stable
    ``(curve_id, value_type, tenor_days, sensitivity_type)`` order; empty when none.
    ``as_of=None`` = now."""
    return latest_run_rows(
        list_governed_results(
            session,
            SensitivityResult,
            acting_tenant=acting_tenant,
            filters=((SensitivityResult.curve_id, curve_id),),
            as_of=as_of,
            order_by=(
                SensitivityResult.curve_id,
                SensitivityResult.value_type,
                SensitivityResult.tenor_days,
                SensitivityResult.sensitivity_type,
            ),
        )
    )


def resolve_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve a SENSITIVITY ``calculation_run`` by ``run_id`` with an EXPLICIT tenant predicate +
    ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable refusal
    evidence)
    rather than synthesizing it. Raises :class:`SensitivityRunNotVisible` on a hidden/unknown id or
    a
    non-sensitivity run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_SENSITIVITY,
        not_visible=SensitivityRunNotVisible,
    )


def resolve_sensitivity(
    session: Session, sensitivity_id: str, *, acting_tenant: str
) -> SensitivityResult:
    """Resolve one ``sensitivity_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(SensitivityResult).where(
            SensitivityResult.id == str(sensitivity_id),
            SensitivityResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise SensitivityNotVisible(str(sensitivity_id))
    return row
