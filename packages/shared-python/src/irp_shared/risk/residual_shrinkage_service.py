"""Empirical-Bayes residual-shrinkage run service (RS-1, OD-RS-1-B).

``run_residual_shrinkage`` produces a SHRUNK idiosyncratic residual estimate for ONE target
instrument by cross-sectionally shrinking its raw specific variance toward a COMPARABLE COHORT's
pool (the Efron-Morris empirical-Bayes intensity; the Barra USE4 specific-risk family). It is a
TRANSFORM over already-promoted proxy-weight estimate runs — it runs no OLS.

Grain = PER TARGET INSTRUMENT (the OD-RS-1-B ratified shape): the run pins the WHOLE comparable
cohort's ``ESTIMATION_SUMMARY`` rows as input, recomputes every ``w_i`` from that pinned content,
and persists ONE ``ESTIMATION_SUMMARY`` ``proxy_weight_estimate_result`` row for the TARGET —
carrying the target's own regression identity (portfolio/instrument/provenance/R^2/df) with ONLY
``residual_stdev`` transformed to the shrunk value. So it promotes + feeds total VaR EXACTLY like a
raw estimate (the promotion + total-VaR pin paths are byte-unchanged; each run still has one
summary). The estimator is carried by the bound model VERSION's declared convention
(``SHRINKAGE_CROSS_SECTIONAL_EB``); the run TYPE stays ``PROXY_WEIGHT_ESTIMATE`` (the output
category — a proxy-weight/specific-risk estimate).

Reproducibility (AD-014/TR-09): the fit reads the PINNED cohort content — never a live estimate
read; a later re-estimate cannot move a historical shrinkage. Build-in-request
(``cohort_estimate_run_ids`` -> builds a ``RESIDUAL_SHRINKAGE_INPUT`` snapshot) or consume-existing
(``snapshot_id``); the target is identified within the pinned cohort by ``target_estimate_run_id``.

Reuses ``risk.run``/``risk.view`` (no mint). Fail-closed model: pre-create refusal (422, its OWN
``ResidualShrinkageInputError``) for a wrong/missing version, an absent/ambiguous target, or a
kernel-structural refusal (cohort < 3, non-positive df); the magnitude gate is the only committed-
FAILED outcome.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.model.service import WrongModelVersionError, assert_model_version_of
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.reference.guards import assert_instrument_in_tenant
from irp_shared.risk.bootstrap import (
    PROXY_WEIGHT_MODEL_CODE,
    PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION,
    declared_proxy_weight_parameters,
)
from irp_shared.risk.events import RUN_TYPE_PROXY_WEIGHT_ESTIMATE, ProxyWeightEstimateActor
from irp_shared.risk.models import METRIC_TYPE_ESTIMATION_SUMMARY, ProxyWeightEstimateResult
from irp_shared.risk.residual_shrinkage_kernel import (
    ResidualShrinkageKernelError,
    ShrinkageMemberInput,
    shrink_residual_variances,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_PROXY_WEIGHT,
    PURPOSE_RESIDUAL_SHRINKAGE_INPUT,
    SnapshotActor,
    build_residual_shrinkage_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "risk.residual_shrinkage.completeness"
#: The Numeric(20,12) ceiling is |value| < 1E8 (the shared envelope lesson).
_MAX_RESULT_ABS = Decimal("1E8")
#: Column quantum (quantize at assign so SQLite + PG persist byte-identical values).
_RESULT_QUANTUM = Decimal("1E-12")


class ResidualShrinkageInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class. Maps to 422."""


@dataclass(frozen=True)
class ResidualShrinkageRunResult:
    """The outcome of ``run_residual_shrinkage``: the ``calculation_run`` + status + the ONE shrunk
    ``ESTIMATION_SUMMARY`` row for the target instrument (``FAILED`` => the magnitude gate)."""

    run: CalculationRun
    status: str
    rows: list[ProxyWeightEstimateResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _Member:
    """One adjudicated cohort member (parsed from a pinned ``ESTIMATION_SUMMARY`` content dict)."""

    estimate_run_id: str
    instrument_id: str
    portfolio_id: str
    source_desmoothed_run_id: str
    series_currency: str
    min_observations: int
    n_observations: int
    n_regressors: int
    residual_stdev: Decimal
    r_squared: Decimal


def _parse_cohort(comps: list[Any]) -> list[_Member]:
    """Parse the pinned ``COMPONENT_KIND_PROXY_WEIGHT`` content into cohort members (PURE — no live
    read; AD-014). Each pinned summary must carry a residual_stdev + a residual df."""
    members: list[_Member] = []
    for c in comps:
        if c.component_kind != COMPONENT_KIND_PROXY_WEIGHT:
            continue
        d = json.loads(c.captured_content)
        if d.get("metric_type") != METRIC_TYPE_ESTIMATION_SUMMARY:
            raise ResidualShrinkageInputError(
                "a pinned proxy-weight component is not an ESTIMATION_SUMMARY row — refused"
            )
        if d.get("residual_stdev") is None:
            raise ResidualShrinkageInputError(
                f"cohort member run {d.get('calculation_run_id')} pins a NULL residual_stdev "
                f"(a MANUAL/non-residual estimate cannot be shrunk) — refused"
            )
        if d.get("n_observations") is None or d.get("n_regressors") is None:
            raise ResidualShrinkageInputError(
                f"cohort member run {d.get('calculation_run_id')} pins no regression df — refused"
            )
        members.append(
            _Member(
                estimate_run_id=str(d["calculation_run_id"]).lower(),
                instrument_id=str(d["instrument_id"]).lower(),
                portfolio_id=str(d["portfolio_id"]).lower(),
                source_desmoothed_run_id=str(d["source_desmoothed_run_id"]).lower(),
                series_currency=str(d["series_currency"]),
                min_observations=int(d["min_observations"]),
                n_observations=int(d["n_observations"]),
                n_regressors=int(d["n_regressors"]),
                residual_stdev=parse_strict_decimal(
                    d["residual_stdev"], error=ResidualShrinkageInputError, field="residual_stdev"
                ),
                r_squared=parse_strict_decimal(
                    d["metric_value"], error=ResidualShrinkageInputError, field="metric_value"
                ),
            )
        )
    if not members:
        raise ResidualShrinkageInputError("no pinned cohort ESTIMATION_SUMMARY rows — refused")
    # The cross-sectional units are INSTRUMENTS, not runs (the adversarial review's catch): two
    # estimate runs of the SAME instrument would double-count its s^2 in the pool and defeat the
    # N>=3 floor's distinct-unit rationale — refused, never silently deduped.
    instruments = [m.instrument_id for m in members]
    if len(set(instruments)) != len(instruments):
        raise ResidualShrinkageInputError(
            "the pinned cohort contains multiple estimate runs for the same instrument — the "
            "cross-sectional pool requires DISTINCT instruments; refused"
        )
    return members


def run_residual_shrinkage(
    session: Session,
    *,
    acting_tenant: str,
    actor: ProxyWeightEstimateActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    target_estimate_run_id: str,
    cohort_estimate_run_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> ResidualShrinkageRunResult:
    """Run a governed empirical-Bayes residual shrinkage for ONE target instrument (OD-RS-1-B).
    Build-in-request (``cohort_estimate_run_ids`` — builds a ``RESIDUAL_SHRINKAGE_INPUT`` snapshot
    pinning every member's ``ESTIMATION_SUMMARY``) or consume-existing (``snapshot_id``). The bound
    version MUST declare ``estimator_convention=SHRINKAGE_CROSS_SECTIONAL_EB``."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise ResidualShrinkageInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ResidualShrinkageInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ResidualShrinkageInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise ResidualShrinkageInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    if not target_estimate_run_id:
        raise ResidualShrinkageInputError("target_estimate_run_id is required")
    if snapshot_id is not None and cohort_estimate_run_ids is not None:
        raise ResidualShrinkageInputError(
            "ambiguous input — pass either snapshot_id or cohort_estimate_run_ids, not both"
        )

    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=PROXY_WEIGHT_MODEL_CODE,
    )
    params = declared_proxy_weight_parameters(session, version)
    if params.estimator_convention != PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION:
        # RAW/EWMA versions run the OLS estimate, not the shrinkage transform (the registry-map
        # dispatch — the inverse of run_proxy_weight_estimate's gate).
        raise WrongModelVersionError(str(version.id), PROXY_WEIGHT_MODEL_CODE)

    # --- Bind the snapshot (cross-tenant/unknown/wrong-purpose => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_RESIDUAL_SHRINKAGE_INPUT:
            raise ResidualShrinkageInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} "
                f"!= {PURPOSE_RESIDUAL_SHRINKAGE_INPUT}"
            )
    else:
        if cohort_estimate_run_ids is None:
            raise ResidualShrinkageInputError(
                "cohort_estimate_run_ids is required to build a residual-shrinkage snapshot"
            )
        if str(target_estimate_run_id).lower() not in {
            str(r).lower() for r in cohort_estimate_run_ids
        }:
            raise ResidualShrinkageInputError(
                "target_estimate_run_id must be one of the cohort_estimate_run_ids — refused"
            )
        snapshot = build_residual_shrinkage_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            cohort_estimate_run_ids=list(cohort_estimate_run_ids),
        )

    # --- Adjudicate the PINNED content + run the empirical-Bayes fit (pre-create). ---
    members = _parse_cohort(
        list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    )
    target = next(
        (m for m in members if m.estimate_run_id == str(target_estimate_run_id).lower()), None
    )
    if target is None:
        raise ResidualShrinkageInputError(
            f"target estimate run {target_estimate_run_id} is not a member of the pinned cohort "
            f"— refused"
        )
    try:
        estimate = shrink_residual_variances(
            [
                ShrinkageMemberInput(m.residual_stdev, m.n_observations, m.n_regressors)
                for m in members
            ]
        )
    except ResidualShrinkageKernelError as exc:
        raise ResidualShrinkageInputError(f"shrinkage refused ({exc.reason}): {exc}") from exc
    target_idx = members.index(target)
    shrunk = estimate.members[target_idx].shrunk_residual_stdev

    # Re-resolve the target subject from the PINNED content under the acting tenant BEFORE anything
    # is stamped into a hard-FK column (PG FK checks bypass RLS — the P3-5 finding).
    assert_portfolio_in_tenant(
        session, target.portfolio_id, acting_tenant=acting_tenant, error=ResidualShrinkageInputError
    )
    assert_instrument_in_tenant(
        session,
        target.instrument_id,
        acting_tenant=acting_tenant,
        error=ResidualShrinkageInputError,
    )

    def _compute(run: CalculationRun) -> tuple[list[ProxyWeightEstimateResult], list[str]]:
        gaps: list[str] = []
        if abs(shrunk) >= _MAX_RESULT_ABS:
            gaps.append("magnitude-out-of-range:shrunk-residual-stdev")
            return [], gaps
        # ONE ESTIMATION_SUMMARY row for the target: its own regression identity carried from the
        # pinned raw estimate (R^2/df/provenance UNCHANGED — shrinkage transforms ONLY the
        # residual), residual_stdev = the shrunk value.
        row = ProxyWeightEstimateResult(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            portfolio_id=target.portfolio_id,
            instrument_id=target.instrument_id,
            source_desmoothed_run_id=target.source_desmoothed_run_id,
            min_observations=target.min_observations,
            series_currency=target.series_currency,
            metric_type=METRIC_TYPE_ESTIMATION_SUMMARY,
            factor_id=None,
            metric_value=target.r_squared.quantize(_RESULT_QUANTUM),
            std_error=None,
            n_observations=target.n_observations,
            n_regressors=target.n_regressors,
            residual_stdev=shrunk.quantize(_RESULT_QUANTUM),
        )
        return [row], gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="residual-shrinkage sanity (shrunk residual within the Numeric(20,12) scale)",
        rule_target_entity_type="proxy_weight_estimate_result",
        result_entity_type="proxy_weight_estimate_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return ResidualShrinkageRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=outcome.failure_reason,
    )
