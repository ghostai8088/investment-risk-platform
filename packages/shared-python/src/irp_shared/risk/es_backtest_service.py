"""ES-backtesting binder (BT-3, ENT-055 extension — the SIXTEENTH governed number: the
Acerbi-Szekely Z statistics).

``run_es_backtest`` produces the ``var_backtest_result`` ES series (``n`` per-pair
``ES_EXCEPTION_INDICATOR`` rows with the ``es_value`` echo + ``ES_PAIR_COUNT``/``AS_Z2``
summaries + — ONLY when the series has >= 1 exception — an ``AS_Z1`` row) ONLY when bound to a
``dataset_snapshot`` (``VAR_BACKTEST_INPUT`` — the BT-1 purpose + builder REUSED byte-unchanged:
the ES rows are ``var_result`` rows and pin as ``COMPONENT_KIND_VAR`` like their VaR siblings; an
adjudicated purpose-only reuse, the ES-HS-1 precedent) + a complete ``calculation_run`` + a
**REGISTERED ``model_version`` OF THE ES-BACKTEST MODEL whose DECLARED significance + stamped
verdict domain fix the decision** (AD-014 / FW-RUN / TR-15 / CTRL-003).

**Sibling pairing (OD-BT-3-C):** the pinned VAR components split by ``metric_type`` into the
VaR-HS leg (``VAR_HISTORICAL``) and the ES-HS leg (``ES_HISTORICAL``). Per ``window_end`` as-of,
the ES row's ``input_snapshot_id`` must EQUAL its VaR sibling's (the shared-snapshot design input
demonstrated live at stage 4); the pairing is a BIJECTION (every ES row has exactly one VaR
sibling and vice versa — all-or-nothing); confidence is uniform ACROSS legs; each leg is
MODEL-VERSION-UNIFORM across pairs (the pinned ``model_version_id`` — a series mixing
code_versions of one declared identity refuses; the gate BT-1 lacks, closed here). The realized
leg + the calendar alignment are BT-1's VERBATIM (:func:`adjudicate_return_side` + the
all-or-nothing ``window_end``/DIETZ pairing).

**The verdict is DOMAIN-GATED (OD-BT-3-B, the planning verifier's HIGH):** the registered
criticals (−0.70 @ 5%, −1.8 @ 0.01%) are valid ONLY at (paired confidence 0.9750, n_pairs 250)
— off-domain runs persist the Z evidence rows + ``ES_PAIR_COUNT`` and NO verdict; the absence is
mechanically derivable from the persisted rows + the version's stamped domain (the BT-2
read-rule doctrine; the Basel-zone domain-gate precedent).

Failure model: the BT-1 UNIFORM two-path model verbatim — pre-create refusal
(:class:`EsBacktestInputError`, 422) for every structural/semantic ill-formedness; post-create
committed FAILED for the magnitude envelope. NO imputation, NO simulation, ever.

One-way imports: ``risk -> {snapshot, calc, model, lineage, dq, audit, db, portfolio.guards}``;
imports NO ``perf`` symbol (the pinned return rows are read as JSON — the BT-1 fence).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.runs import resolve_completed_run_of_type, resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.model.service import assert_model_version_of
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.risk.bootstrap import (
    ES_BACKTEST_MODEL_CODE,
    declared_es_backtest_parameters,
)
from irp_shared.risk.es_backtest_kernel import (
    EsBacktestKernelError,
    as_z_statistics,
    z2_verdict,
)
from irp_shared.risk.events import (
    METRIC_TYPE_AS_Z1,
    METRIC_TYPE_AS_Z2,
    METRIC_TYPE_ES_EXCEPTION_INDICATOR,
    METRIC_TYPE_ES_HISTORICAL,
    METRIC_TYPE_ES_PAIR_COUNT,
    METRIC_TYPE_VAR_HISTORICAL,
    RUN_TYPE_ES_BACKTEST,
    RUN_TYPE_VAR,
    EsBacktestActor,
)
from irp_shared.risk.models import VarBacktestResult
from irp_shared.risk.var_backtest_service import (
    _RETURN_RUN_TYPE,
    adjudicate_return_side,
    exception_indicator,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_PORTFOLIO_RETURN,
    COMPONENT_KIND_VAR,
    PURPOSE_VAR_BACKTEST_INPUT,
    SnapshotActor,
    build_var_backtest_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "risk.es_backtest.completeness"
#: The Numeric(28,6) envelope gate (the BT-1 constant's value, kept local — one order inside).
_MAX_RESULT_ABS = Decimal("1E21")
#: Money quantum for values persisted at Numeric(28,6) (byte parity across engines).
_MONEY_QUANTUM = Decimal("0.000001")


class EsBacktestInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal
    (no run, no result, no run-audit). Its OWN class. Maps to 422."""


class EsBacktestNotVisible(Exception):
    """Raised when an ES-backtest ``var_backtest_result`` id is not visible in the tenant."""

    def __init__(self, result_id: str) -> None:
        super().__init__(f"es-backtest result {result_id} is not visible in the current tenant")
        self.result_id = str(result_id)


class EsBacktestRunNotVisible(Exception):
    """Raised when an es-backtest ``calculation_run`` id is not visible in the tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"es-backtest run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class EsBacktestRunResult:
    """The outcome of ``run_es_backtest`` (the BT-1 result shape)."""

    run: CalculationRun
    status: str
    rows: list[VarBacktestResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _SiblingPair:
    """One aligned (realized, VaR forecast, ES forecast) triple at one as-of."""

    period_start: date
    period_end: date
    realized_pnl: Decimal
    var_value: Decimal
    es_value: Decimal


@dataclass(frozen=True)
class _ParsedEsInput:
    """The adjudicated pinned input: ordered sibling triples + run-uniform descriptors."""

    pairs: list[_SiblingPair]
    portfolio_id: str
    base_currency: str
    confidence_level: Decimal
    horizon_days: int
    portfolio_return_run_id: str
    var_run_ids: tuple[str, ...]
    es_run_ids: tuple[str, ...]
    exposure_run_ids: tuple[str, ...]


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse pinned ``captured_content`` into raw return-row / var-component dicts (PURE)."""
    return_raw: list[dict[str, Any]] = []
    var_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_PORTFOLIO_RETURN:
            return_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_VAR:
            var_raw.append(data)
    return return_raw, var_raw


def _uniform_leg(
    rows: list[dict[str, Any]], *, leg: str
) -> tuple[Decimal, int, dict[date, dict[str, Any]]]:
    """Adjudicate ONE forecast leg: uniform confidence/horizon, unique ``window_end`` as-ofs,
    model-version-UNIFORM across the leg (the pinned ``model_version_id`` — the cross-pair gate
    BT-1 lacks, OD-BT-3-C). Returns (confidence, horizon, {as_of: row})."""
    confidences = {Decimal(r["confidence_level"]) for r in rows}
    horizons = {int(r["horizon_days"]) for r in rows}
    versions = {str(r["model_version_id"]).lower() for r in rows}
    if len(confidences) != 1 or len(horizons) != 1:
        raise EsBacktestInputError(
            f"the pinned {leg} rows are not uniform in confidence_level/horizon_days — refused"
        )
    if len(versions) != 1:
        raise EsBacktestInputError(
            f"the pinned {leg} rows span {len(versions)} model versions — a series must be "
            f"model-version-uniform per leg (cross-pair identity); refused"
        )
    by_asof: dict[date, dict[str, Any]] = {}
    for r in rows:
        as_of = date.fromisoformat(r["window_end"])
        if as_of in by_asof:
            raise EsBacktestInputError(
                f"duplicate {leg} window_end as-of {as_of} — one forecast per as-of; refused"
            )
        by_asof[as_of] = r
    return next(iter(confidences)), next(iter(horizons)), by_asof


def _adjudicate_es_pins(
    return_raw: list[dict[str, Any]], var_raw: list[dict[str, Any]]
) -> _ParsedEsInput:
    """PRE-CREATE adjudication of the FULL pinned input (both entry paths): the BT-1 realized
    leg verbatim; the VAR components split into VaR-HS / ES-HS legs; per-as-of sibling BIJECTION
    with IDENTICAL ``input_snapshot_id``; uniform confidence ACROSS legs; ES_t > 0; the
    all-or-nothing calendar alignment. Raises :class:`EsBacktestInputError`."""
    side = adjudicate_return_side(return_raw, error=EsBacktestInputError)

    if not var_raw:
        raise EsBacktestInputError("the snapshot pins no VAR components — nothing to backtest")
    var_rows = [r for r in var_raw if r["metric_type"] == METRIC_TYPE_VAR_HISTORICAL]
    es_rows = [r for r in var_raw if r["metric_type"] == METRIC_TYPE_ES_HISTORICAL]
    strays = {
        r["metric_type"]
        for r in var_raw
        if r["metric_type"] not in (METRIC_TYPE_VAR_HISTORICAL, METRIC_TYPE_ES_HISTORICAL)
    }
    if strays:
        raise EsBacktestInputError(
            f"the ES backtest pairs VAR_HISTORICAL with ES_HISTORICAL siblings only — pinned "
            f"stray metric_type(s) {sorted(strays)}; refused"
        )
    if not var_rows or not es_rows:
        raise EsBacktestInputError(
            f"the sibling pairing needs BOTH legs (got {len(var_rows)} VAR_HISTORICAL + "
            f"{len(es_rows)} ES_HISTORICAL rows) — refused"
        )

    var_conf, var_horizon, var_by_asof = _uniform_leg(var_rows, leg="VAR_HISTORICAL")
    es_conf, es_horizon, es_by_asof = _uniform_leg(es_rows, leg="ES_HISTORICAL")
    if var_conf != es_conf:
        raise EsBacktestInputError(
            f"sibling confidence mismatch: VaR leg {var_conf} != ES leg {es_conf} — the Z "
            f"statistics are defined at ONE tail; refused"
        )
    if var_horizon != es_horizon:
        raise EsBacktestInputError(
            f"sibling horizon mismatch: VaR leg {var_horizon}d != ES leg {es_horizon}d — refused"
        )
    if not (Decimal(0) < var_conf < Decimal(1)):
        raise EsBacktestInputError(f"confidence_level {var_conf} outside (0, 1) — refused")
    if var_horizon < 1:
        raise EsBacktestInputError(f"horizon_days {var_horizon} < 1 — refused")
    if set(var_by_asof) != set(es_by_asof):
        only_var = sorted(str(d) for d in set(var_by_asof) - set(es_by_asof))
        only_es = sorted(str(d) for d in set(es_by_asof) - set(var_by_asof))
        raise EsBacktestInputError(
            f"the sibling pairing is not a bijection (VaR-only as-ofs {only_var}; ES-only "
            f"as-ofs {only_es}) — all-or-nothing; refused"
        )

    currencies = {r["base_currency"] for r in [*var_rows, *es_rows]}
    if currencies != {side.base_currency}:
        raise EsBacktestInputError(
            f"forecast base currencies {sorted(currencies)} != portfolio base currency "
            f"{side.base_currency!r} — refused"
        )

    pairs: list[_SiblingPair] = []
    horizon = timedelta(days=var_horizon)
    for as_of in sorted(var_by_asof):
        v, e = var_by_asof[as_of], es_by_asof[as_of]
        if str(v["input_snapshot_id"]).lower() != str(e["input_snapshot_id"]).lower():
            raise EsBacktestInputError(
                f"sibling snapshot mismatch at {as_of}: the ES row's input_snapshot_id != its "
                f"VaR sibling's — the pair must share ONE pinned scenario set; refused"
            )
        hit = side.periods.get(as_of)
        if hit is None:
            raise EsBacktestInputError(
                f"forecast as-of {as_of} has no realized sub-period starting there — refused "
                f"(all-or-nothing alignment; no imputation)"
            )
        period_end, pnl = hit
        if period_end != as_of + horizon:
            raise EsBacktestInputError(
                f"forecast as-of {as_of} (horizon {var_horizon}d) does not span the realized "
                f"sub-period ({as_of}, {period_end}] — refused"
            )
        var_value = parse_strict_decimal(
            v["var_value"], error=EsBacktestInputError, field="var_value", quantum=_MONEY_QUANTUM
        )
        es_value = parse_strict_decimal(
            e["var_value"],  # an ES_HISTORICAL row stores its ES in var_value (ES-HS-1)
            error=EsBacktestInputError,
            field="es_value",
            quantum=_MONEY_QUANTUM,
        )
        if es_value <= 0:
            raise EsBacktestInputError(
                f"ES forecast {es_value} at {as_of} is not strictly positive — refused"
            )
        if var_value < 0:
            raise EsBacktestInputError(f"VaR forecast {var_value} at {as_of} is negative — refused")
        pairs.append(
            _SiblingPair(
                period_start=as_of,
                period_end=period_end,
                realized_pnl=pnl.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP),
                var_value=var_value,
                es_value=es_value,
            )
        )

    return _ParsedEsInput(
        pairs=pairs,
        portfolio_id=side.portfolio_id,
        base_currency=side.base_currency,
        confidence_level=var_conf,
        horizon_days=var_horizon,
        portfolio_return_run_id=side.portfolio_return_run_id,
        var_run_ids=tuple(sorted({str(r["calculation_run_id"]).lower() for r in var_rows})),
        es_run_ids=tuple(sorted({str(r["calculation_run_id"]).lower() for r in es_rows})),
        exposure_run_ids=tuple(
            sorted({str(r["exposure_run_id"]).lower() for r in [*var_rows, *es_rows]})
        ),
    )


def _resolve_run(
    session: Session, run_id: str, *, acting_tenant: str, run_type: str, label: str
) -> CalculationRun:
    """Re-resolve a consumed run under the acting tenant (+ run_type + COMPLETED) BEFORE its id
    is stamped into a hard-FK column (PG FK checks bypass RLS — P3-5)."""
    return resolve_completed_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=run_type,
        label=label,
        error=EsBacktestInputError,
    )


def _assert_exposure_runs_portfolio(
    session: Session, exposure_run_ids: tuple[str, ...], *, portfolio_id: str, acting_tenant: str
) -> None:
    """The cross-series IDENTITY gate (the BT-1 OD-BT-1-H shape on BOTH forecast legs)."""
    from irp_shared.risk.models import FactorExposureResult  # local import avoids a module cycle

    for run_id in exposure_run_ids:
        rows = session.execute(
            select(FactorExposureResult.portfolio_id)
            .where(
                FactorExposureResult.calculation_run_id == str(run_id),
                FactorExposureResult.tenant_id == str(acting_tenant),
            )
            .distinct()
        ).all()
        found = {str(r[0]) for r in rows}
        if not found:
            raise EsBacktestInputError(
                f"forecast factor-exposure run {run_id} has no visible result rows — refused"
            )
        if found != {str(portfolio_id)}:
            raise EsBacktestInputError(
                f"forecast factor-exposure run {run_id} measures portfolio(s) {sorted(found)} "
                f"!= the return run's portfolio {portfolio_id} — refused (cross-series identity)"
            )


def run_es_backtest(
    session: Session,
    *,
    acting_tenant: str,
    actor: EsBacktestActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    portfolio_return_run_id: str | None = None,
    var_run_ids: list[str] | None = None,
    es_run_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> EsBacktestRunResult:
    """Run a governed AS ES backtest. Build-in-request (``portfolio_return_run_id`` +
    ``var_run_ids`` + ``es_run_ids``: builds a ``VAR_BACKTEST_INPUT`` snapshot pinning all three
    legs — the ES runs are VAR-type runs and pin through the BT-1 builder byte-unchanged) or
    consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise EsBacktestInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise EsBacktestInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise EsBacktestInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise EsBacktestInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    build_args = (portfolio_return_run_id, var_run_ids, es_run_ids)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise EsBacktestInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(portfolio_return_run_id/var_run_ids/es_run_ids), not both"
        )
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=ES_BACKTEST_MODEL_CODE,
    )
    params = declared_es_backtest_parameters(session, version)

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_VAR_BACKTEST_INPUT:
            raise EsBacktestInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != "
                f"{PURPOSE_VAR_BACKTEST_INPUT}"
            )
    else:
        if portfolio_return_run_id is None or not var_run_ids or not es_run_ids:
            raise EsBacktestInputError(
                "portfolio_return_run_id + var_run_ids (>= 1) + es_run_ids (>= 1) are required "
                "to build an es-backtest snapshot"
            )
        _resolve_run(
            session,
            str(portfolio_return_run_id),
            acting_tenant=acting_tenant,
            run_type=_RETURN_RUN_TYPE,
            label="portfolio-return",
        )
        for run_id in [*var_run_ids, *es_run_ids]:
            _resolve_run(
                session,
                str(run_id),
                acting_tenant=acting_tenant,
                run_type=RUN_TYPE_VAR,
                label="VaR",
            )
        snapshot = build_var_backtest_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            portfolio_return_run_id=str(portfolio_return_run_id),
            var_run_ids=[str(r) for r in [*var_run_ids, *es_run_ids]],
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        return_raw, var_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_es_pins(return_raw, var_raw)
    except EsBacktestInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise EsBacktestInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Re-resolve every provenance id from the PINNED CONTENT under the acting tenant BEFORE any
    # is stamped into a hard-FK column (BOTH forecast legs — the ES-leg battery, OD-BT-3-C).
    _resolve_run(
        session,
        parsed.portfolio_return_run_id,
        acting_tenant=acting_tenant,
        run_type=_RETURN_RUN_TYPE,
        label="portfolio-return",
    )
    for run_id in [*parsed.var_run_ids, *parsed.es_run_ids]:
        _resolve_run(
            session, run_id, acting_tenant=acting_tenant, run_type=RUN_TYPE_VAR, label="VaR"
        )
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=EsBacktestInputError
    )
    _assert_exposure_runs_portfolio(
        session,
        parsed.exposure_run_ids,
        portfolio_id=parsed.portfolio_id,
        acting_tenant=acting_tenant,
    )

    # --- The shared governed-run lifecycle (P3-C1 scaffold) ---
    def _compute(run: CalculationRun) -> tuple[list[VarBacktestResult], list[str]]:
        gaps: list[str] = []
        rows: list[VarBacktestResult] = []

        def _mk(
            metric_type: str,
            metric_value: Decimal,
            period_start: date,
            period_end: date,
            *,
            realized_pnl: Decimal | None,
            var_value: Decimal | None,
            es_value: Decimal | None,
            n_pairs: int,
            n_exceptions: int,
            test_decision: str | None = None,
        ) -> VarBacktestResult:
            return VarBacktestResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_return_run_id=parsed.portfolio_return_run_id,
                portfolio_id=parsed.portfolio_id,
                metric_type=metric_type,
                var_metric_type=METRIC_TYPE_ES_HISTORICAL,
                period_start=period_start,
                period_end=period_end,
                metric_value=metric_value,
                realized_pnl=realized_pnl,
                var_value=var_value,
                es_value=es_value,
                n_pairs=n_pairs,
                n_exceptions=n_exceptions,
                confidence_level=parsed.confidence_level,
                horizon_days=parsed.horizon_days,
                test_decision=test_decision,
                basel_zone=None,
                base_currency=parsed.base_currency,
            )

        def _out_of_range(*values: Decimal | None) -> bool:
            return any(v is not None and abs(v) >= _MAX_RESULT_ABS for v in values)

        try:
            kernel_pairs = [(p.realized_pnl, p.var_value, p.es_value) for p in parsed.pairs]
            tail_a = Decimal(1) - parsed.confidence_level
            stats = as_z_statistics(kernel_pairs, tail_a)
            for pair in parsed.pairs:
                e = exception_indicator(pair.realized_pnl, pair.var_value)
                if _out_of_range(pair.realized_pnl, pair.var_value, pair.es_value):
                    gaps.append(f"magnitude-out-of-range:pair:{pair.period_start}")
                    return [], gaps
                rows.append(
                    _mk(
                        METRIC_TYPE_ES_EXCEPTION_INDICATOR,
                        Decimal(e),
                        pair.period_start,
                        pair.period_end,
                        realized_pnl=pair.realized_pnl,
                        var_value=pair.var_value,
                        es_value=pair.es_value,
                        n_pairs=1,
                        n_exceptions=e,
                    )
                )
            n = stats.n_pairs
            first, last = parsed.pairs[0], parsed.pairs[-1]
            rows.append(
                _mk(
                    METRIC_TYPE_ES_PAIR_COUNT,
                    Decimal(n),
                    first.period_start,
                    last.period_end,
                    realized_pnl=None,
                    var_value=None,
                    es_value=None,
                    n_pairs=n,
                    n_exceptions=stats.n_exceptions,
                )
            )
            z2 = stats.z2.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if _out_of_range(z2):
                gaps.append(f"magnitude-out-of-range:{METRIC_TYPE_AS_Z2}:{z2:E}")
                return [], gaps
            # The DOMAIN GATE (OD-BT-3-B): the verdict exists ONLY inside the criticals'
            # derivation domain — decided on the STORED 6dp value (the BT-1 convention).
            on_domain = (
                parsed.confidence_level == params.verdict_confidence and n == params.verdict_pairs
            )
            rows.append(
                _mk(
                    METRIC_TYPE_AS_Z2,
                    z2,
                    first.period_start,
                    last.period_end,
                    realized_pnl=None,
                    var_value=None,
                    es_value=None,
                    n_pairs=n,
                    n_exceptions=stats.n_exceptions,
                    test_decision=(z2_verdict(z2, params.significance) if on_domain else None),
                )
            )
            if stats.z1 is not None:
                z1 = stats.z1.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
                if _out_of_range(z1):
                    gaps.append(f"magnitude-out-of-range:{METRIC_TYPE_AS_Z1}:{z1:E}")
                    return [], gaps
                rows.append(
                    _mk(
                        METRIC_TYPE_AS_Z1,
                        z1,
                        first.period_start,
                        last.period_end,
                        realized_pnl=None,
                        var_value=None,
                        es_value=None,
                        n_pairs=n,
                        n_exceptions=stats.n_exceptions,
                        # Z1 is EVIDENCE, never a verdict (distribution-unstable criticals).
                    )
                )
        except EsBacktestKernelError as exc:
            gaps.append(f"kernel-refusal:{exc}")
            return [], gaps
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_ES_BACKTEST,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="es-backtest run output sanity (values within the Numeric(28,6) scale)",
        rule_target_entity_type="var_backtest_result",
        result_entity_type="var_backtest_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return EsBacktestRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_es_backtests(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[VarBacktestResult]:
    """The ES-backtest ``var_backtest_result`` rows of a run (tenant-scoped; ordered)."""
    return list(
        session.execute(
            select(VarBacktestResult)
            .where(
                VarBacktestResult.calculation_run_id == str(run_id),
                VarBacktestResult.tenant_id == str(acting_tenant),
            )
            .order_by(VarBacktestResult.metric_type, VarBacktestResult.period_start)
        )
        .scalars()
        .all()
    )


def resolve_es_backtest_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve an es-backtest ``calculation_run`` by ``run_id`` with an EXPLICIT tenant
    predicate + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_ES_BACKTEST,
        not_visible=EsBacktestRunNotVisible,
    )


def resolve_es_backtest(
    session: Session, result_id: str, *, acting_tenant: str
) -> VarBacktestResult:
    """Resolve one ES-backtest ``var_backtest_result`` row by id (EXPLICIT tenant predicate)."""
    row = session.execute(
        select(VarBacktestResult).where(
            VarBacktestResult.id == str(result_id),
            VarBacktestResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise EsBacktestNotVisible(str(result_id))
    return row
