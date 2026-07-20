"""The API-1 stage-10 demo runner (OD-API-1, the OQ-W7C-5 demo-completeness rider): EXECUTE the
five governed codes the campaign registered but never ran, so the API-1 entity/time + latest reads
render NON-EMPTY for every family (the read surface is the point of Wave 9).

RUNS-ONLY. Stage 10 mints NO new model code and files NO validation record — these five heads are
already registered (campaign ``_register_models``) and already tiered/validated as part of the
16-code ceremony; running them is exercise, not governance. So the demo counts move by exactly the
five COMPLETED runs (20 codes / 35 records UNCHANGED; 96 → 101 runs) — the deliberate contrast with
the stage-9 code+record+run mint.

The five runs and the ONE prerequisite each still needs (everything else already lives in the tenant
from the campaign + stages 1–9):

  1. ``risk.sensitivity.analytic``   — needs a rate CURVE (none captured anywhere in the demo);
     stage 10 captures one SWAP/USD zero curve, then runs the analytic DV01 sensitivities on it.
  2. ``risk.active_risk.parametric`` — needs a BENCHMARK + membership; reuses the campaign's
     ALLOCATION factor-exposure run + a covariance run.
  3. ``risk.scenario.factor_shock``  — needs a scenario DEFINITION + shocks (on the demo's own
     FX_USD/FX_EUR factors); reuses the campaign's factor-exposure run.
  4. ``perf.benchmark_relative``     — needs a benchmark RETURN series aligned to the PM-1 return
     run's DIETZ sub-periods; reuses the SAME benchmark head as run 2.
  5. ``risk.factor_exposure.proxy``  — needs NOTHING new: the PA-3 promote chain already left a
     PROXY_MAPPING (PE-HARBOR-IV → FX_USD) and the campaign left EXPOSURE_AGGREGATE runs.

One benchmark head carries BOTH the membership (run 2) and the return series (run 4). Idempotency is
REFUSE-NOT-SKIP on stage 10's OWN footprint (a SENSITIVITY run in the demo tenant); the caller owns
the ONE commit; the module bootstraps nothing (it requires the campaign).

Ordering discipline (the CC-2-recorded caveat, ``cc2_stage9`` docstring): a two-digit ``stage10``
suite file sorts lexically BEFORE ``stage2``/``stage4`` and would seed these extra runs before the
earlier stages assert their exact count pins in a single-invocation local PG battery. The suites
that exercise this module are therefore named ``test_demo_stage9z_api1_reads*`` so they collate
AFTER ``test_demo_stage9_cc2*`` (CI orders the PG step explicitly, after the stage-9 step and before
the downgrade smoke).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.exposure import RUN_TYPE_EXPOSURE_AGGREGATE
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.marketdata import (
    RETURN_BASIS_TOTAL,
    BenchmarkActor,
    ConstituentInput,
    CurveActor,
    CurveNode,
    capture_benchmark,
    capture_benchmark_return,
    capture_curve,
    capture_membership,
    resolve_benchmark,
)
from irp_shared.marketdata.factor import Factor
from irp_shared.model.models import Model, ModelVersion
from irp_shared.perf import (
    RUN_TYPE_PORTFOLIO_RETURN,
    BenchmarkRelativeActor,
    run_benchmark_relative,
)
from irp_shared.portfolio import Portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    RUN_TYPE_FACTOR_EXPOSURE,
    RUN_TYPE_SENSITIVITY,
    ActiveRiskActor,
    FactorExposureActor,
    ScenarioActor,
    SensitivityActor,
    capture_scenario_shock,
    create_scenario_definition,
    run_active_risk,
    run_factor_exposure,
    run_scenario,
    run_sensitivities,
)
from irp_shared.risk.bootstrap import FACTOR_EXPOSURE_MODEL_CODE
from irp_shared.risk.models import CovarianceResult
from irp_shared.snapshot import CurveSelector

_CODE_VERSION = "demo-api1"
_ENVIRONMENT_ID = "demo"

_SENSITIVITY_CODE = "risk.sensitivity.analytic"
_ACTIVE_RISK_CODE = "risk.active_risk.parametric"
_SCENARIO_CODE = "risk.scenario.factor_shock"
_BENCHMARK_RELATIVE_CODE = "perf.benchmark_relative"
_PROXY_CODE = "risk.factor_exposure.proxy"

# The demo's 9 daily valuation-boundary dates are date(2026,5,18)+i for i in range(9); the PM-1 TWR
# run's DIETZ sub-periods partition (2026-05-18, 2026-05-26] into 8 windows ending 05-19..05-26.
# ONE benchmark return per sub-period end (the binder requires >=1 per window, none out of span).
_BENCH_EFFECTIVE_DATE = date(2026, 5, 26)
_BENCH_RETURN_DATES: tuple[date, ...] = tuple(
    date(2026, 5, 18) + timedelta(days=i) for i in range(1, 9)
)
_CURVE_DATE = date(2026, 5, 26)
_CURVE_SOURCE = "DEMO_VENDOR"
#: The curve is valid from an early demo instant; the sensitivity run reads it as-of a later one.
_CURVE_VALID_FROM = datetime(2026, 1, 1, tzinfo=UTC)
_AS_OF_VALID_AT = datetime(2026, 5, 26, tzinfo=UTC)
_AS_OF_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)


class DemoStage10Error(RuntimeError):
    """Stage 10 could not complete against the live tenant state."""


class DemoStage10PrereqError(DemoStage10Error):
    """Stage 10 EXERCISES the living tenant — it requires the MG-1 campaign (the five registered
    heads + their evidence chains) and never bootstraps it. Run the prior stages first."""


class DemoStage10AlreadySeededError(RuntimeError):
    """Refuse-not-skip on stage 10's OWN footprint: a SENSITIVITY run already exists in the demo
    tenant. The caller commits atomically, so any committed stage-10 state is complete; reset the
    schema and re-run the stages."""

    def __init__(self) -> None:
        super().__init__(
            f"demo tenant {DEMO_TENANT_ID} already holds a SENSITIVITY run — refusing to re-run "
            f"stage 10 (reset the schema and re-run campaign + stages)."
        )


@dataclass(frozen=True)
class Stage10Api1Summary:
    """Stage 10's end state — the five COMPLETED run ids the API-1 reads now surface."""

    tenant_id: str
    sensitivity_run_id: str
    active_risk_run_id: str
    scenario_run_id: str
    benchmark_relative_run_id: str
    proxy_exposure_run_id: str
    runs_executed: int


def _resolve_principal(session: Session, role_code: str, label: str) -> str:
    from irp_shared.entitlement.models import AppUser, Role, UserRole

    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoStage10PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one from "
            f"the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _resolve_model_version_id(session: Session, code: str) -> str:
    """The registered version of a demo model code (the campaign registers exactly one v1 per code;
    the newest is taken defensively). Refuses if the code was never registered."""
    row = session.execute(
        select(ModelVersion.id)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(Model.tenant_id == DEMO_TENANT_ID, Model.code == code)
        .order_by(ModelVersion.system_from.desc(), ModelVersion.id.desc())
    ).first()
    if row is None:
        raise DemoStage10PrereqError(
            f"the demo tenant holds no registered version of {code!r} — the campaign has not run"
        )
    return str(row[0])


def _resolve_latest_run(session: Session, run_type: str, *, model_code: str | None = None) -> str:
    """The newest COMPLETED run of a type in the demo tenant (optionally pinned to a model code —
    the factor-exposure family shares one run_type across the ALLOCATION and PROXY heads, so
    active-risk/scenario must consume the ALLOCATION run specifically). Refuses if none exists."""
    stmt = (
        select(CalculationRun.run_id)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == run_type,
            CalculationRun.status == RunStatus.COMPLETED.value,
        )
        .order_by(CalculationRun.system_from.desc(), CalculationRun.run_id.desc())
    )
    if model_code is not None:
        stmt = (
            stmt.join(ModelVersion, ModelVersion.id == CalculationRun.model_version_id)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(Model.code == model_code)
        )
    row = session.execute(stmt).first()
    if row is None:
        raise DemoStage10PrereqError(
            f"the demo tenant holds no COMPLETED {run_type} run"
            + (f" for model {model_code!r}" if model_code else "")
            + " — the campaign has not run"
        )
    return str(row[0])


def _resolve_covariance_run_over(session: Session, factor_ids: set[str]) -> str:
    """The newest COMPLETED covariance run whose factor set is EXACTLY ``factor_ids`` — active-risk
    pairs the ALLOCATION exposure run (over FX_USD/FX_EUR) with a covariance over the SAME factors,
    and every such factor carries a currency_code. A bare "latest covariance run" could be a
    later-stage matrix over a currency-less factor (the binder refuses those). Refuses if none."""
    rows = session.execute(
        select(CovarianceResult.calculation_run_id, CovarianceResult.factor_id_1)
        .join(CalculationRun, CalculationRun.run_id == CovarianceResult.calculation_run_id)
        .where(
            CovarianceResult.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == RunStatus.COMPLETED.value,
        )
        .order_by(CalculationRun.system_from.desc(), CalculationRun.run_id.desc())
    ).all()
    by_run: dict[str, set[str]] = {}
    order: list[str] = []
    for run_id, fid1 in rows:
        if run_id not in by_run:
            by_run[run_id] = set()
            order.append(run_id)
        by_run[run_id].add(str(fid1))
    # factor_id_2 too (the off-diagonal partner), so the set is the full matrix factor set.
    for run_id, fid2 in session.execute(
        select(CovarianceResult.calculation_run_id, CovarianceResult.factor_id_2).where(
            CovarianceResult.tenant_id == DEMO_TENANT_ID
        )
    ).all():
        if run_id in by_run:
            by_run[run_id].add(str(fid2))
    for run_id in order:  # newest-first
        if by_run[run_id] == factor_ids:
            return run_id
    raise DemoStage10PrereqError(
        f"the demo tenant holds no COMPLETED covariance run over exactly {factor_ids} — the "
        f"campaign's FX_USD/FX_EUR matrix is missing"
    )


def _resolve_portfolio_id(session: Session, code: str) -> str:
    row = session.execute(
        select(Portfolio.id).where(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == code)
    ).first()
    if row is None:
        raise DemoStage10PrereqError(
            f"the demo tenant holds no portfolio {code!r} — the campaign has not run"
        )
    return str(row[0])


def _resolve_exposure_run_for_portfolio(session: Session, portfolio_id: str) -> str:
    """The newest COMPLETED EXPOSURE_AGGREGATE run that spans a given portfolio's book (its atoms
    carry ``portfolio_id`` rows). The proxy factor-exposure family admits ONLY currency factors, so
    the run MUST be over the campaign's DEMO-GLOBAL book — whose sole proxied private instrument
    (PE-HARBOR-IV) maps to the CURRENCY factor FX_USD — NOT a later RS-1 sleeve run carrying
    RATES-family proxies (which the family refuses)."""
    row = session.execute(
        select(ExposureAggregate.calculation_run_id)
        .join(CalculationRun, CalculationRun.run_id == ExposureAggregate.calculation_run_id)
        .where(
            ExposureAggregate.tenant_id == DEMO_TENANT_ID,
            ExposureAggregate.portfolio_id == str(portfolio_id),
            CalculationRun.status == RunStatus.COMPLETED.value,
            CalculationRun.run_type == RUN_TYPE_EXPOSURE_AGGREGATE,
        )
        .order_by(CalculationRun.system_from.desc(), CalculationRun.run_id.desc())
    ).first()
    if row is None:
        raise DemoStage10PrereqError(
            f"the demo tenant holds no COMPLETED EXPOSURE_AGGREGATE run over portfolio "
            f"{portfolio_id} — the campaign has not run"
        )
    return str(row[0])


def _resolve_factor_id(session: Session, factor_code: str) -> str:
    row = session.execute(
        select(Factor.id).where(
            Factor.tenant_id == DEMO_TENANT_ID, Factor.factor_code == factor_code
        )
    ).first()
    if row is None:
        raise DemoStage10PrereqError(
            f"the demo tenant holds no {factor_code!r} factor — the campaign has not run"
        )
    return str(row[0])


def _require_completed(result, label: str) -> None:  # noqa: ANN001
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoStage10Error(
            f"the stage-10 {label} run did not COMPLETE (status={status!r}, reason={reason!r})"
        )


def run_demo_stage10_api1(session: Session) -> Stage10Api1Summary:
    """Execute stage 10 (build the 3 missing inputs → run the 5 registered-but-unrun codes). The
    caller owns the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Prereq + footprint probes (refuse-not-skip, BEFORE any write) ---
        model_count = session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if model_count == 0:
            raise DemoStage10PrereqError(
                f"demo tenant {DEMO_TENANT_ID} holds no model rows — the campaign has not run"
            )
        seeded = session.execute(
            select(CalculationRun.run_id).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == RUN_TYPE_SENSITIVITY,
            )
        ).first()
        if seeded is not None:
            raise DemoStage10AlreadySeededError()

        registrar = _resolve_principal(session, "risk_analyst_1l", "1L registrar")

        # Resolve the registered heads + the existing evidence runs BEFORE any run write (so run 5's
        # own proxy factor-exposure run cannot shadow the ALLOCATION run resolved for runs 2/3).
        sens_mv = _resolve_model_version_id(session, _SENSITIVITY_CODE)
        active_mv = _resolve_model_version_id(session, _ACTIVE_RISK_CODE)
        scenario_mv = _resolve_model_version_id(session, _SCENARIO_CODE)
        bench_rel_mv = _resolve_model_version_id(session, _BENCHMARK_RELATIVE_CODE)
        proxy_mv = _resolve_model_version_id(session, _PROXY_CODE)

        fx_usd = _resolve_factor_id(session, "FX_USD")
        fx_eur = _resolve_factor_id(session, "FX_EUR")
        allocation_fx_run = _resolve_latest_run(
            session, RUN_TYPE_FACTOR_EXPOSURE, model_code=FACTOR_EXPOSURE_MODEL_CODE
        )
        covariance_run = _resolve_covariance_run_over(session, {fx_usd, fx_eur})
        portfolio_return_run = _resolve_latest_run(session, RUN_TYPE_PORTFOLIO_RETURN)
        # The proxy run must be over the campaign's DEMO-GLOBAL book (currency-only proxies).
        demo_global_id = _resolve_portfolio_id(session, "DEMO-GLOBAL")
        exposure_run = _resolve_exposure_run_for_portfolio(session, demo_global_id)

        # --- Build the three MISSING inputs (captures — no runs) ---
        # (a) A rate curve for the analytic sensitivities.
        capture_curve(
            session,
            curve_type="SWAP",
            currency_code="USD",
            curve_date=_CURVE_DATE,
            curve_source=_CURVE_SOURCE,
            nodes=[
                CurveNode(
                    tenor_label="1Y",
                    tenor_days=365,
                    value_type="ZERO_RATE",
                    point_value=Decimal("0.043"),
                ),
                CurveNode(
                    tenor_label="2Y",
                    tenor_days=730,
                    value_type="ZERO_RATE",
                    point_value=Decimal("0.041"),
                ),
                CurveNode(
                    tenor_label="5Y",
                    tenor_days=1825,
                    value_type="ZERO_RATE",
                    point_value=Decimal("0.040"),
                ),
            ],
            acting_tenant=DEMO_TENANT_ID,
            actor=CurveActor(actor_id=registrar),
            valid_from=_CURVE_VALID_FROM,
        )

        # (b) ONE benchmark head carrying BOTH a two-constituent membership (for active-risk) AND a
        # TOTAL-basis return series aligned to the PM-1 sub-periods (for benchmark-relative).
        benchmark = capture_benchmark(
            session,
            benchmark_code="DEMO-GLOBAL-BM",
            benchmark_source="DEMO_VENDOR",
            benchmark_currency="USD",
            acting_tenant=DEMO_TENANT_ID,
            actor=BenchmarkActor(actor_id=registrar),
            index_family="DEMO",
        )
        constituents: list[ConstituentInput] = []
        for label, ccy, weight in (("BM-US", "USD", "0.60"), ("BM-EU", "EUR", "0.40")):
            inst = create_instrument(
                session,
                tenant_id=DEMO_TENANT_ID,
                code=f"{label}-CONSTITUENT",
                name=f"{label} benchmark constituent",
                asset_class="EQUITY",
                actor=ReferenceActor(actor_id=registrar),
            ).id
            constituents.append(
                ConstituentInput(
                    instrument_id=inst, weight=Decimal(weight), constituent_currency=ccy
                )
            )
        capture_membership(
            session,
            benchmark,
            effective_date=_BENCH_EFFECTIVE_DATE,
            constituents=constituents,
            acting_tenant=DEMO_TENANT_ID,
            actor=BenchmarkActor(actor_id=registrar),
        )
        bench_head = resolve_benchmark(session, benchmark.id, acting_tenant=DEMO_TENANT_ID)
        for rdate, value in zip(
            _BENCH_RETURN_DATES,
            ("0.0011", "-0.0006", "0.0009", "0.0004", "-0.0012", "0.0007", "0.0003", "-0.0005"),
            strict=True,
        ):
            capture_benchmark_return(
                session,
                bench_head,
                return_date=rdate,
                return_basis=RETURN_BASIS_TOTAL,
                return_value=Decimal(value),
                acting_tenant=DEMO_TENANT_ID,
                actor=BenchmarkActor(actor_id=registrar),
            )

        # (c) A scenario definition + shocks on the demo's OWN currency factors (so the shocked set
        # intersects the exposed set the factor-exposure run carries).
        scenario_def = create_scenario_definition(
            session,
            code="DEMO-FX-SHOCK",
            name="Demo FX shock",
            scenario_type="HYPOTHETICAL",
            acting_tenant=DEMO_TENANT_ID,
            actor=ScenarioActor(actor_id=registrar),
        )
        for fid, shock in ((fx_usd, "-0.08"), (fx_eur, "0.05")):
            capture_scenario_shock(
                session,
                scenario_definition_id=scenario_def.id,
                factor_id=fid,
                shock_value=Decimal(shock),
                acting_tenant=DEMO_TENANT_ID,
                actor=ScenarioActor(actor_id=registrar),
            )

        # --- Execute the five governed runs (each creates ONE COMPLETED CalculationRun) ---
        sensitivity = run_sensitivities(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=SensitivityActor(actor_id=registrar),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=sens_mv,
            curve_selectors=[
                CurveSelector(
                    curve_type="SWAP",
                    currency_code="USD",
                    curve_date=_CURVE_DATE,
                    curve_source=_CURVE_SOURCE,
                )
            ],
            as_of_valid_at=_AS_OF_VALID_AT,
            as_of_known_at=_AS_OF_KNOWN_AT,
        )
        _require_completed(sensitivity, "sensitivity")

        active_risk = run_active_risk(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ActiveRiskActor(actor_id=registrar),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=active_mv,
            exposure_run_id=allocation_fx_run,
            covariance_run_id=covariance_run,
            benchmark_id=bench_head.id,
            benchmark_effective_date=_BENCH_EFFECTIVE_DATE,
        )
        _require_completed(active_risk, "active-risk")

        scenario = run_scenario(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ScenarioActor(actor_id=registrar),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=scenario_mv,
            factor_exposure_run_id=allocation_fx_run,
            scenario_definition_id=scenario_def.id,
        )
        _require_completed(scenario, "scenario")

        benchmark_relative = run_benchmark_relative(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=BenchmarkRelativeActor(actor_id=registrar),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=bench_rel_mv,
            portfolio_return_run_id=portfolio_return_run,
            benchmark_id=bench_head.id,
            return_basis=RETURN_BASIS_TOTAL,
        )
        _require_completed(benchmark_relative, "benchmark-relative")

        proxy_exposure = run_factor_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=FactorExposureActor(actor_id=registrar),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=proxy_mv,
            exposure_run_id=exposure_run,
            factor_ids=[fx_usd, fx_eur],  # DEMO-GLOBAL's proxy (PE-HARBOR-IV) maps to FX_USD
        )
        _require_completed(proxy_exposure, "proxy factor-exposure")

        return Stage10Api1Summary(
            tenant_id=DEMO_TENANT_ID,
            sensitivity_run_id=sensitivity.run.run_id,
            active_risk_run_id=active_risk.run.run_id,
            scenario_run_id=scenario.run.run_id,
            benchmark_relative_run_id=benchmark_relative.run.run_id,
            proxy_exposure_run_id=proxy_exposure.run.run_id,
            runs_executed=5,
        )
    finally:
        detach()
