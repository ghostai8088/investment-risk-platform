"""Scenario run service (P3-6, ENT-030) — the TENTH governed number: deterministic factor-shock P&L.

``run_scenario`` applies a pinned scenario shock set linearly to the pinned per-factor exposures of
ONE COMPLETED factor-exposure run: ``pnl_i = quantize_HALF_UP(exposure_i * shock_i, 6)`` per factor,
``total = Σ`` of the quantized rows. Build-in-request (``factor_exposure_run_id`` +
``scenario_definition_id`` → builds a ``SCENARIO_INPUT`` snapshot) or consume-existing
(``snapshot_id``); BOTH paths adjudicate the PINNED content pre-create (AD-014 — never a live read).

Failure model (the established governed-run shape):
- **Pre-create refusal (422, its own ``ScenarioInputError``)** — missing prerequisite, ambiguous
  input, cross-tenant/wrong-purpose snapshot, structurally malformed pinned content, non-CURRENCY
  scope, multi-portfolio exposure run. NO run, NO result, NO run-audit.
- **Post-create FAILED (magnitude gate)** — a committed FAILED run + ZERO rows + a naming
  ``failure_reason`` (never a RUNNING orphan). Every persisted ``Numeric(28,6)`` value clears
  ``_MAX_RESULT_ABS`` (the P3-8/BT-1 echo lesson).

Partial coverage (OD-P3-6-G): an exposed factor the scenario does NOT name is shock 0 (a
deterministic scenario is a COMPLETE specification — "unnamed = unchanged"); every exposed factor
gets a row; the TOTAL row carries n_factors_exposed / n_factors_shocked / n_shocks_unmatched. One
shock
naming a non-exposed factor produces no row (counted in n_shocks_unmatched). Reuses ``risk.run``/
``risk.view`` (no mint) + ``CALC.RUN_*`` (``RISK.SCENARIO_CREATE`` reserved-not-emitted).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.model.service import assert_model_version_of
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.risk.bootstrap import SCENARIO_MODEL_CODE
from irp_shared.risk.events import (
    METRIC_TYPE_SCENARIO_PNL,
    METRIC_TYPE_SCENARIO_PNL_TOTAL,
    RUN_TYPE_FACTOR_EXPOSURE,
    RUN_TYPE_SCENARIO,
)
from irp_shared.risk.scenario import ScenarioActor, ScenarioNotVisible  # the shared actor dataclass
from irp_shared.risk.scenario_models import ScenarioResult
from irp_shared.snapshot import (
    COMPONENT_KIND_FACTOR_EXPOSURE,
    COMPONENT_KIND_SCENARIO,
    PURPOSE_SCENARIO_INPUT,
    SnapshotActor,
    build_scenario_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "risk.scenario.completeness"
#: Money quantum for Numeric(28,6) (quantize in the binder so SQLite + PG persist identically).
_MONEY_QUANTUM = Decimal("0.000001")
#: The Numeric(28,6) ceiling is |value| < 1E22; this gate sits inside it and bounds EVERY persisted
#: money value — pnl AND the exposure echo (the P3-8/BT-1 echo-overflow lesson baked in from birth).
_MAX_RESULT_ABS = Decimal("1E21")
_CURRENCY_FAMILY = "CURRENCY"


class ScenarioInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class. Maps to 422."""


class ScenarioResultNotVisible(Exception):
    """Raised when a ``scenario_result`` id is not visible in the acting tenant scope."""

    def __init__(self, result_id: str) -> None:
        super().__init__(f"scenario_result {result_id} is not visible in the current tenant")
        self.result_id = str(result_id)


class ScenarioRunNotVisible(Exception):
    """Raised when a scenario ``calculation_run`` id is not visible in the tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"scenario run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class ScenarioRunResult:
    """The outcome of ``run_scenario``: the ``calculation_run`` + status + the result rows.
    ``status`` is ``COMPLETED`` (``rows`` = the per-factor P&L rows + the TOTAL) or ``FAILED``
    (the magnitude gate: a committed FAILED run + ZERO rows + a naming ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[ScenarioResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _FactorExposure:
    """The aggregated pinned exposure for ONE factor (Σ over the run's atoms)."""

    factor_id: str
    factor_code: str
    factor_family: str
    exposure_amount: Decimal


@dataclass(frozen=True)
class _ParsedInput:
    """Adjudicated pinned input: per-factor exposures + the shock map + run-uniform descriptors."""

    exposures: list[_FactorExposure]  # ordered by factor_id
    shocks: dict[str, Decimal]  # factor_id -> shock_value
    scenario_definition_id: str
    scenario_code: str
    portfolio_id: str
    base_currency: str
    factor_exposure_run_id: str


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw exposure-row / shock-row dicts (PURE — no live
    read; the AD-014 invariant)."""
    exposure_raw: list[dict[str, Any]] = []
    shock_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
            exposure_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_SCENARIO:
            shock_raw.append(data)
    return exposure_raw, shock_raw


def _adjudicate_pins(
    exposure_raw: list[dict[str, Any]], shock_raw: list[dict[str, Any]]
) -> _ParsedInput:
    """Adjudicate the pinned content pre-create: aggregate the exposure atoms per factor, enforce a
    uniform portfolio + base currency + CURRENCY family, parse-harden every consumed decimal, and
    build the shock map. Raises :class:`ScenarioInputError` on any ill-formed input."""
    if not exposure_raw:
        raise ScenarioInputError("no pinned factor-exposure rows — nothing to shock")
    if not shock_raw:
        raise ScenarioInputError("no pinned scenario shocks — nothing to apply")

    # --- aggregate exposures per factor (sum the atoms) ---
    agg: dict[str, dict[str, Any]] = {}
    portfolios: set[str] = set()
    base_currencies: set[str] = set()
    run_ids: set[str] = set()
    for row in exposure_raw:
        fid = str(row["factor_id"]).lower()
        family = str(row["factor_family"])
        if family != _CURRENCY_FAMILY:
            raise ScenarioInputError(
                f"exposed factor {fid} family {family!r} is not CURRENCY — outside P3-6 v1 scope"
            )
        amount = parse_strict_decimal(
            row["exposure_amount"], error=ScenarioInputError, field="exposure_amount"
        )
        portfolios.add(str(row["portfolio_id"]).lower())
        base_currencies.add(str(row["base_currency"]))
        run_ids.add(str(row["calculation_run_id"]).lower())
        if fid not in agg:
            agg[fid] = {
                "factor_code": str(row["factor_code"]),
                "factor_family": family,
                "amount": Decimal(0),
            }
        agg[fid]["amount"] += amount
    if len(portfolios) != 1:
        raise ScenarioInputError(
            f"the pinned exposure run spans {len(portfolios)} portfolios (v1 is single-portfolio)"
        )
    if len(base_currencies) != 1:
        raise ScenarioInputError(
            f"the pinned exposures carry {sorted(base_currencies)} base currencies (not uniform)"
        )
    if len(run_ids) != 1:
        raise ScenarioInputError("the pinned exposures span multiple factor-exposure runs")

    exposures = [
        _FactorExposure(
            factor_id=fid,
            factor_code=v["factor_code"],
            factor_family=v["factor_family"],
            exposure_amount=v["amount"].quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        )
        for fid, v in sorted(agg.items())
    ]

    # --- build the shock map (uniform definition; each factor pinned once) ---
    definition_ids: set[str] = set()
    codes: set[str] = set()
    shocks: dict[str, Decimal] = {}
    for row in shock_raw:
        fid = str(row["factor_id"]).lower()
        if fid in shocks:
            raise ScenarioInputError(f"factor {fid} is shocked more than once in the pinned set")
        definition_ids.add(str(row["scenario_definition_id"]).lower())
        codes.add(str(row["scenario_code"]))
        shocks[fid] = parse_strict_decimal(
            row["shock_value"], error=ScenarioInputError, field="shock_value"
        )
    if len(definition_ids) != 1 or len(codes) != 1:
        raise ScenarioInputError("the pinned shocks span more than one scenario definition")

    return _ParsedInput(
        exposures=exposures,
        shocks=shocks,
        scenario_definition_id=next(iter(definition_ids)),
        scenario_code=next(iter(codes)),
        portfolio_id=next(iter(portfolios)),
        base_currency=next(iter(base_currencies)),
        factor_exposure_run_id=next(iter(run_ids)),
    )


def _resolve_run(
    session: Session, run_id: str, *, acting_tenant: str, run_type: str, label: str
) -> CalculationRun:
    """Resolve a COMPLETED run of the expected type under the acting tenant (fail-closed)."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == run_type,
        )
    ).scalar_one_or_none()
    if run is None:
        raise ScenarioInputError(f"{label} run {run_id} is not a visible {run_type} run — refused")
    if run.status != RunStatus.COMPLETED.value:
        raise ScenarioInputError(
            f"{label} run {run_id} status {run.status!r} != COMPLETED — refused"
        )
    return run


def run_scenario(
    session: Session,
    *,
    acting_tenant: str,
    actor: ScenarioActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    factor_exposure_run_id: str | None = None,
    scenario_definition_id: str | None = None,
    snapshot_id: str | None = None,
) -> ScenarioRunResult:
    """Run a governed factor-shock scenario. Build-in-request (default —
    ``factor_exposure_run_id`` + ``scenario_definition_id``: builds a ``SCENARIO_INPUT``) or
    consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise ScenarioInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ScenarioInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ScenarioInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise ScenarioInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    build_args = (factor_exposure_run_id, scenario_definition_id)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise ScenarioInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(factor_exposure_run_id/scenario_definition_id), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / OD-P3-6-D).
    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=SCENARIO_MODEL_CODE,
    )

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_SCENARIO_INPUT:
            raise ScenarioInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_SCENARIO_INPUT}"
            )
    else:
        if factor_exposure_run_id is None or scenario_definition_id is None:
            raise ScenarioInputError(
                "factor_exposure_run_id + scenario_definition_id are required to build a "
                "scenario snapshot"
            )
        _resolve_run(
            session,
            str(factor_exposure_run_id),
            acting_tenant=acting_tenant,
            run_type=RUN_TYPE_FACTOR_EXPOSURE,
            label="factor-exposure",
        )
        try:
            snapshot = build_scenario_snapshot(
                session,
                acting_tenant=acting_tenant,
                actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
                factor_exposure_run_id=str(factor_exposure_run_id),
                scenario_definition_id=str(scenario_definition_id),
            )
        except ScenarioNotVisible as exc:
            # An unknown/cross-tenant definition is a build-input refusal, SYMMETRIC with the
            # unknown factor-exposure run above — a uniform pre-create 422, never a run-time 404.
            raise ScenarioInputError(str(exc)) from exc

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        exposure_raw, shock_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(exposure_raw, shock_raw)
    except ScenarioInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content is the SAME refusal class as a semantically bad
        # input — a governed 422, never a raw parse 500 (the P3-C3 wrapper).
        raise ScenarioInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Re-resolve the exposure run + the portfolio from the PINNED content under the acting tenant
    # BEFORE anything is stamped into a hard-FK / read (PG FK checks bypass RLS — the P3-5 finding).
    _resolve_run(
        session,
        parsed.factor_exposure_run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_FACTOR_EXPOSURE,
        label="factor-exposure",
    )
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=ScenarioInputError
    )

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[ScenarioResult], list[str]]:
        gaps: list[str] = []
        rows: list[ScenarioResult] = []
        shocked_ids = set(parsed.shocks)
        exposed_ids = {e.factor_id for e in parsed.exposures}
        n_exposed = len(parsed.exposures)
        n_shocked = len(shocked_ids & exposed_ids)  # shocks actually applied (exposed AND shocked)
        n_unmatched = len(shocked_ids - exposed_ids)  # shocks naming a non-exposed factor

        total = Decimal(0)
        for e in parsed.exposures:
            shock = parsed.shocks.get(e.factor_id, Decimal(0))  # unnamed => 0 (OD-P3-6-G)
            # Gate the RAW product BEFORE quantizing: quantize() raises InvalidOperation once the
            # result needs > context precision (28 sig digits), and a below-gate exposure (< 1E21)
            # times a Numeric(20,12) shock (< 1E8) can reach ~1E29 — so an unguarded quantize would
            # escape as a raw 500 AFTER the run is RUNNING, defeating this very gate (the BT-1/P3-8
            # echo-overflow class). Decimal multiply only rounds (never raises), so the raw check is
            # safe; gating raw < 1E21 leaves the subsequent quantize within precision.
            raw = e.exposure_amount * shock
            if abs(raw) >= _MAX_RESULT_ABS or abs(e.exposure_amount) >= _MAX_RESULT_ABS:
                gaps.append(f"magnitude-out-of-range:factor:{e.factor_id}")
                return [], gaps
            pnl = raw.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            total += pnl
            rows.append(
                ScenarioResult(
                    tenant_id=str(acting_tenant),
                    calculation_run_id=run.run_id,
                    input_snapshot_id=snapshot.id,
                    model_version_id=str(model_version_id),
                    scenario_definition_id=parsed.scenario_definition_id,
                    scenario_code=parsed.scenario_code,
                    metric_type=METRIC_TYPE_SCENARIO_PNL,
                    factor_id=e.factor_id,
                    factor_code=e.factor_code,
                    factor_family=e.factor_family,
                    pnl=pnl,
                    shock_value=shock,
                    exposure_amount=e.exposure_amount,
                    base_currency=parsed.base_currency,
                )
            )
        if abs(total) >= _MAX_RESULT_ABS:
            gaps.append(f"magnitude-out-of-range:total:{total:E}")
            return [], gaps
        rows.append(
            ScenarioResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                scenario_definition_id=parsed.scenario_definition_id,
                scenario_code=parsed.scenario_code,
                metric_type=METRIC_TYPE_SCENARIO_PNL_TOTAL,
                factor_id=None,  # the single TOTAL row
                factor_code=None,
                factor_family=None,
                pnl=total,
                shock_value=None,
                exposure_amount=None,
                n_factors_exposed=n_exposed,
                n_factors_shocked=n_shocked,
                n_shocks_unmatched=n_unmatched,
                base_currency=parsed.base_currency,
            )
        )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_SCENARIO,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="scenario run output sanity (values within the Numeric(28,6) scale)",
        rule_target_entity_type="scenario_result",
        result_entity_type="scenario_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return ScenarioRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=getattr(outcome, "failure_reason", None),
    )


def list_scenario_results(
    session: Session, run_id: str, *, acting_tenant: str
) -> list[ScenarioResult]:
    """The ``scenario_result`` rows of a run (tenant-scoped; per-factor rows then the TOTAL)."""
    return list(
        session.execute(
            select(ScenarioResult)
            .where(
                ScenarioResult.calculation_run_id == str(run_id),
                ScenarioResult.tenant_id == str(acting_tenant),
            )
            .order_by(ScenarioResult.metric_type, ScenarioResult.factor_id)
        )
        .scalars()
        .all()
    )


def resolve_scenario_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve a SCENARIO ``calculation_run`` by id (tenant + run_type predicated; fail-closed)."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_SCENARIO,
        )
    ).scalar_one_or_none()
    if run is None:
        raise ScenarioRunNotVisible(str(run_id))
    return run
