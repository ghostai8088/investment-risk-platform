"""VaR-backtesting binder (BT-1, ENT-055 — the NINTH governed number; the platform's first
executable SR 11-7 "outcomes analysis").

``run_var_backtest`` produces the ``var_backtest_result`` series (``n`` per-pair
``EXCEPTION_INDICATOR`` rows + ``EXCEPTION_COUNT``/``KUPIEC_LR`` summaries + — ONLY on the Basel
(0.99, 250) domain — a ``BASEL_ZONE`` row) ONLY when bound to a ``dataset_snapshot``
(``VAR_BACKTEST_INPUT`` — pinning ALL result rows of ONE COMPLETED ``PORTFOLIO_RETURN`` run + ALL
``var_result`` rows of the listed ``VAR`` runs) + a complete ``calculation_run`` + a **REGISTERED
``model_version`` OF THE VAR-BACKTEST MODEL whose DECLARED ``alpha`` fixed the Kupiec decision
threshold** (AD-014 / FW-RUN / TR-15 / CTRL-003; the P3-5 declared-parameter precedent).

The numbers are the outcomes-analysis statistics (``irp_shared.risk.var_backtest_kernel``): per
aligned pair ``e_i = 1`` iff ``-P&L_i > VaR_i`` (STRICT); ``LR_POF`` (Kupiec 1995, chi-square(1),
TWO-SIDED) with a fixed-critical REJECT/FAIL_TO_REJECT decision; the Basel zone on its defined
domain only. Realized ``P&L_i = end_mv - begin_mv - net_external_flow`` per pinned DIETZ
sub-period — the flow-adjusted ACTUAL-P&L leg (OD-BT-1-D). The binder reads ONLY the pinned
content (PURE — AD-014).

**The perf fence stays INTACT** ("nothing imports perf"): the pinned return rows are read as JSON;
the consumed return run is re-resolved via ``calc.CalculationRun`` with the fence-kept LOCAL
``_RETURN_RUN_TYPE`` constant (+ a sync test) — a REAL cross-package fence, unlike the removed
P3-8 same-package copy. **Plan deviation, recorded:** the ratified plan named the P3-8
exact-linkage cross-check (``prod(1+r_i)-1 == TWR_LINKED``), but that needs perf's compounding
kernel; instead the binder enforces the **MV-CHAIN check** — ``begin_mv_{i+1} == end_mv_i`` for
contiguous sub-periods (the SAME boundary valuation appears on both sides in a well-formed PM-1
output) — which adjudicates exactly the columns THIS number consumes (the MVs and flows, not
``return_value``). Deeper integrity, no fence breach, no duplicated kernel.

**Alignment (OD-BT-1-E, all-or-nothing):** each pinned VaR forecast applies as of its
``window_end`` and pairs with EXACTLY the DIETZ sub-period where ``period_start == window_end``
AND ``period_end == period_start + horizon_days`` CALENDAR days; ANY unpaired forecast refuses the
WHOLE run. Unforecast sub-periods are fine (the run backtests the forecasts provided). Duplicate
``window_end`` refuses, so the pairing is injective.

**Identity (OD-BT-1-H):** each pinned VaR row's ``exposure_run_id`` (the P3-5 column names the
consumed FACTOR-EXPOSURE run) must resolve, acting tenant, to ``factor_exposure_result`` rows of
the SAME ``portfolio_id`` the return run measured; the return run + every pinned VaR run + the
portfolio are re-resolved under the acting tenant BEFORE any id is stamped into a hard-FK column
(PG FK checks bypass RLS — P3-5).

Failure model (the PM-1/P3-8 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing prerequisites; an unregistered or WRONG-MODEL version; a
  non-COMPLETED / cross-tenant / wrong-type run; a wrong-purpose snapshot; **pinned content that
  is not a well-formed v1 input** — no DIETZ rows, not exactly one TWR_LINKED, mixed
  run/portfolio/base, non-contiguous sub-periods, a broken MV chain, mixed VaR methods or
  non-uniform confidence/horizon/currency, duplicate ``window_end``, an unpaired forecast, a
  horizon mismatch, or JSON-null/non-object fields): **raise BEFORE ``create_run``** => ZERO run +
  ZERO rows + ZERO run-audit. **NO imputation, ever.**
- **Post-create FAILED** (a column-legal-but-extreme pin whose metric OR whose
  ``realized_pnl``/``var_value`` echo overflows the ``Numeric(28,6)`` envelope ``|value| < 1E22``
  — the compute gates EVERY persisted Numeric column at ``_MAX_RESULT_ABS`` — the P3-8 HIGH-fold
  lesson): a committed FAILED run (``outcome='failure'``) + ``DATA.VALIDATE`` DQ evidence + ZERO
  rows + a magnitude-naming ``failure_reason``.

One-way imports: ``risk -> {snapshot, calc, model, lineage, dq, audit, db, portfolio.guards}``;
imports NO ``perf`` symbol.
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
from irp_shared.risk.bootstrap import VAR_BACKTEST_MODEL_CODE, declared_var_backtest_alpha
from irp_shared.risk.events import (
    METRIC_TYPE_BASEL_ZONE,
    METRIC_TYPE_ES_HISTORICAL,
    METRIC_TYPE_ES_PARAMETRIC,
    METRIC_TYPE_EXCEPTION_COUNT,
    METRIC_TYPE_EXCEPTION_INDICATOR,
    METRIC_TYPE_KUPIEC_LR,
    METRIC_TYPES,
    RUN_TYPE_VAR,
    RUN_TYPE_VAR_BACKTEST,
    VarBacktestActor,
)
from irp_shared.risk.models import VarBacktestResult
from irp_shared.risk.var_backtest_kernel import (
    VarBacktestKernelError,
    basel_zone,
    exception_indicator,
    kupiec_decision,
    kupiec_lr,
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

#: The PM-1 metric-type strings the pinned portfolio_return rows carry (the ENT-053 column vocab —
#: read from pinned JSON, never imported: the "nothing imports perf" fence).
_DIETZ_PERIOD = "DIETZ_PERIOD"
_TWR_LINKED = "TWR_LINKED"
#: The PORTFOLIO_RETURN run_type the consumed run must carry — a fence-kept LOCAL copy of
#: ``perf.events.RUN_TYPE_PORTFOLIO_RETURN`` (risk must NOT import perf; a sync test pins the two
#: strings equal — the PM-1 ``_EXPOSURE_RUN_TYPE`` precedent, and a REAL fence this time).
_RETURN_RUN_TYPE = "PORTFOLIO_RETURN"
#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "risk.var_backtest.completeness"
#: The Numeric(28,6) column ceiling is |value| < 1E22; this gate sits ONE order inside it and
#: bounds EVERY persisted Numeric(28,6) value — the metric_value AND the realized_pnl/var_value
#: echoes (the P3-8 HIGH-fold lesson baked in from birth).
_MAX_RESULT_ABS = Decimal("1E21")
#: The Basel traffic-light zone's DEFINED domain (OD-BT-1-G) — emitted there, omitted elsewhere.
_BASEL_CONFIDENCE = Decimal("0.99")
_BASEL_PAIRS = 250
#: ... over ONE-DAY observations — a multi-day-horizon VaR version (the recorded sqrt(h) seam)
#: must NOT mint a zone row (review fold: the gate was latently horizon-blind).
_BASEL_HORIZON_DAYS = 1
#: Money quantum for values persisted at Numeric(28,6) (SQLite stores what it is given; PG rounds
#: at the column — quantize in the binder so both engines persist byte-identical values).
_MONEY_QUANTUM = Decimal("0.000001")


class VarBacktestInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class. Maps to 422."""


class VarBacktestNotVisible(Exception):
    """Raised when a ``var_backtest_result`` id is not visible in the acting tenant scope."""

    def __init__(self, result_id: str) -> None:
        super().__init__(f"var_backtest_result {result_id} is not visible in the current tenant")
        self.result_id = str(result_id)


class VarBacktestRunNotVisible(Exception):
    """Raised when a var-backtest ``calculation_run`` id is not visible in the tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"var-backtest run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class VarBacktestRunResult:
    """The outcome of ``run_var_backtest``: the ``calculation_run`` + status + the result rows.
    ``status`` is ``COMPLETED`` (``rows`` = the pair series + the summary rows) or ``FAILED``
    (the magnitude gate: a committed FAILED run + ZERO rows + a naming ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[VarBacktestResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _Pair:
    """One aligned (realized, forecast) pair: the DIETZ sub-period + the VaR forecast whose
    ``window_end`` == ``period_start`` and whose horizon spans the sub-period exactly."""

    period_start: date
    period_end: date
    realized_pnl: Decimal
    var_value: Decimal


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the ordered pairs + the run-uniform descriptors."""

    pairs: list[_Pair]
    portfolio_id: str
    base_currency: str
    var_metric_type: str
    confidence_level: Decimal
    horizon_days: int
    portfolio_return_run_id: str
    var_run_ids: tuple[str, ...]
    exposure_run_ids: tuple[str, ...]


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw return-row / var-row dicts (PURE — no live
    read; the AD-014 invariant)."""
    return_raw: list[dict[str, Any]] = []
    var_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_PORTFOLIO_RETURN:
            return_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_VAR:
            var_raw.append(data)
    return return_raw, var_raw


def _adjudicate_pins(
    return_raw: list[dict[str, Any]], var_raw: list[dict[str, Any]]
) -> _ParsedInput:
    """PRE-CREATE adjudication of the FULL pinned input (both entry paths): a single-run/portfolio/
    base return side with CONTIGUOUS ordered DIETZ sub-periods + exactly one TWR_LINKED row + the
    MV-CHAIN check; a uniform single-method VaR side; the ALL-OR-NOTHING forecast/period alignment.
    Raises :class:`VarBacktestInputError` on any ill-formed input."""
    if not return_raw:
        raise VarBacktestInputError(
            "the snapshot pins no PORTFOLIO_RETURN rows — not a var-backtest input"
        )
    dietz = [r for r in return_raw if r["metric_type"] == _DIETZ_PERIOD]
    linked = [r for r in return_raw if r["metric_type"] == _TWR_LINKED]
    if not dietz:
        raise VarBacktestInputError("the pinned return run has no DIETZ_PERIOD sub-periods")
    if len(linked) != 1:
        raise VarBacktestInputError(
            f"the pinned return run must carry exactly one TWR_LINKED row (got {len(linked)})"
        )

    run_ids = {str(r["calculation_run_id"]).lower() for r in return_raw}
    portfolio_ids = {str(r["portfolio_id"]) for r in return_raw}
    base_currencies = {r["base_currency"] for r in return_raw}
    if len(run_ids) != 1:
        raise VarBacktestInputError("the pinned return rows span multiple runs — refused")
    if len(portfolio_ids) != 1:
        raise VarBacktestInputError(
            f"the pinned return rows span {len(portfolio_ids)} portfolios — refused"
        )
    if len(base_currencies) != 1:
        raise VarBacktestInputError(
            f"the pinned return rows carry mixed base currencies {sorted(base_currencies)}"
        )
    base_currency = next(iter(base_currencies))
    if not isinstance(base_currency, str) or len(base_currency) != 3:
        raise VarBacktestInputError(
            "the pinned return base_currency is not a 3-letter code — refused"
        )

    # Ordered, CONTIGUOUS sub-periods (the P3-8 fold precedent) + the MV-CHAIN integrity check:
    # begin_mv_{i+1} must EQUAL end_mv_i (the same boundary valuation appears on both sides in a
    # well-formed PM-1 output) — this adjudicates exactly the columns the P&L consumes.
    ordered = sorted(dietz, key=lambda r: r["period_start"])
    periods: dict[date, tuple[date, Decimal]] = {}
    prev_end: date | None = None
    prev_end_mv: Decimal | None = None
    for r in ordered:
        start = date.fromisoformat(r["period_start"])
        end = date.fromisoformat(r["period_end"])
        begin_mv = Decimal(r["begin_mv"])
        end_mv = Decimal(r["end_mv"])
        flow = Decimal(r["net_external_flow"])
        if end <= start:
            raise VarBacktestInputError(f"sub-period {start}..{end} is non-positive — refused")
        if prev_end is not None and start != prev_end:
            raise VarBacktestInputError(
                f"the pinned DIETZ sub-periods are not contiguous (a gap or overlap at "
                f"{prev_end}..{start}) — refused"
            )
        if prev_end_mv is not None and begin_mv != prev_end_mv:
            raise VarBacktestInputError(
                f"MV chain broken at {start}: begin_mv {begin_mv} != prior end_mv {prev_end_mv} "
                f"— malformed input; refused"
            )
        periods[start] = (end, end_mv - begin_mv - flow)  # realized flow-adjusted P&L
        prev_end = end
        prev_end_mv = end_mv

    # --- VaR side: >= 1 row, ONE method, uniform confidence/horizon/currency, unique as-ofs. ---
    if not var_raw:
        raise VarBacktestInputError("the snapshot pins no VAR rows — nothing to backtest")
    var_metric_types = {r["metric_type"] for r in var_raw}
    if len(var_metric_types) != 1:
        raise VarBacktestInputError(
            f"the pinned VaR rows mix methods {sorted(var_metric_types)} — one method per "
            f"backtest run; refused"
        )
    var_metric_type = next(iter(var_metric_types))
    if var_metric_type not in METRIC_TYPES:
        # Distinguish "we do not know this value" from "we know it and ratified excluding it"
        # (ES-1, OD-ES-1-F). ES_PARAMETRIC is a REAL, shipped metric deliberately kept out of the
        # backtestable subset — calling that "unknown" would send a validator hunting a vocabulary
        # bug instead of reading the recorded scope-out.
        if var_metric_type == METRIC_TYPE_ES_PARAMETRIC:
            raise VarBacktestInputError(
                f"metric_type {var_metric_type!r} is DELIBERATELY not backtestable (ES-1, "
                f"OD-ES-1-F: FRTB backtests VaR and never ES, and under this leg's normality an "
                f"ES backtest is the VaR backtest with a rescaled threshold) — backtest the VaR "
                f"run instead; refused"
            )
        if var_metric_type == METRIC_TYPE_ES_HISTORICAL:
            raise VarBacktestInputError(
                f"metric_type {var_metric_type!r} is DELIBERATELY not backtestable HERE "
                f"(ES-HS-1, OD-ES-HS-1-D: the Kupiec/Basel exception count is a QUANTILE test "
                f"and is statistically meaningless over a tail-mean series; the genuine "
                f"Acerbi-Szekely ES backtest is the named BT-3 candidate — pairing the ES-HS "
                f"run with its sibling VaR-HS run by shared input_snapshot_id) — backtest the "
                f"sibling VaR-HS run instead; refused"
            )
        raise VarBacktestInputError(f"unknown VaR metric_type {var_metric_type!r} — refused")
    confidences = {Decimal(r["confidence_level"]) for r in var_raw}
    horizons = {int(r["horizon_days"]) for r in var_raw}
    var_currencies = {r["base_currency"] for r in var_raw}
    if len(confidences) != 1 or len(horizons) != 1:
        raise VarBacktestInputError(
            "the pinned VaR rows are not uniform in confidence_level/horizon_days — refused"
        )
    if var_currencies != {base_currency}:
        raise VarBacktestInputError(
            f"VaR base currencies {sorted(var_currencies)} != portfolio base currency "
            f"{base_currency!r} — refused"
        )
    confidence_level = next(iter(confidences))
    horizon_days = next(iter(horizons))
    if not (Decimal(0) < confidence_level < Decimal(1)):
        raise VarBacktestInputError(f"confidence_level {confidence_level} outside (0, 1) — refused")
    if horizon_days < 1:
        raise VarBacktestInputError(f"horizon_days {horizon_days} < 1 — refused")
    window_ends = [date.fromisoformat(r["window_end"]) for r in var_raw]
    if len(set(window_ends)) != len(window_ends):
        raise VarBacktestInputError(
            "duplicate VaR window_end as-ofs — one forecast per as-of; refused"
        )

    # --- ALL-OR-NOTHING alignment (OD-BT-1-E): every forecast pairs; injective by uniqueness. ---
    pairs: list[_Pair] = []
    horizon = timedelta(days=horizon_days)
    for r in var_raw:
        as_of = date.fromisoformat(r["window_end"])
        hit = periods.get(as_of)
        if hit is None:
            raise VarBacktestInputError(
                f"VaR forecast as-of {as_of} has no realized sub-period starting there — "
                f"refused (all-or-nothing alignment; no imputation)"
            )
        period_end, pnl = hit
        if period_end != as_of + horizon:
            raise VarBacktestInputError(
                f"VaR forecast as-of {as_of} (horizon {horizon_days}d) does not span the "
                f"realized sub-period ({as_of}, {period_end}] — refused"
            )
        pairs.append(
            _Pair(
                period_start=as_of,
                period_end=period_end,
                realized_pnl=pnl.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP),
                # Strict-parsed at the money scale INSIDE the pre-create wrapper (MD-H1 annex 5,
                # generalizing the BT-1 fold): a hand-minted NaN is a governed 422, never a
                # post-create 500; the quantum pins the stored echo byte-identical across engines.
                var_value=parse_strict_decimal(
                    r["var_value"],
                    error=VarBacktestInputError,
                    field="var_value",
                    quantum=_MONEY_QUANTUM,
                ),
            )
        )
    pairs.sort(key=lambda p: p.period_start)

    return _ParsedInput(
        pairs=pairs,
        portfolio_id=next(iter(portfolio_ids)),
        base_currency=base_currency,
        var_metric_type=var_metric_type,
        confidence_level=confidence_level,
        horizon_days=horizon_days,
        portfolio_return_run_id=next(iter(run_ids)),
        var_run_ids=tuple(sorted({str(r["calculation_run_id"]).lower() for r in var_raw})),
        exposure_run_ids=tuple(sorted({str(r["exposure_run_id"]).lower() for r in var_raw})),
    )


def _resolve_run(
    session: Session, run_id: str, *, acting_tenant: str, run_type: str, label: str
) -> CalculationRun:
    """Re-resolve a consumed run under the acting tenant (+ run_type + COMPLETED) BEFORE its id is
    stamped into a hard-FK column (PG FK checks bypass RLS — P3-5)."""
    return resolve_completed_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=run_type,
        label=label,
        error=VarBacktestInputError,
    )


def _assert_exposure_runs_portfolio(
    session: Session, exposure_run_ids: tuple[str, ...], *, portfolio_id: str, acting_tenant: str
) -> None:
    """The cross-series IDENTITY gate (OD-BT-1-H): every pinned VaR row's ``exposure_run_id``
    (the P3-5 column NAMES the consumed FACTOR-EXPOSURE run) must resolve — under the acting
    tenant — to ``factor_exposure_result`` rows of the SAME portfolio the return run measured.
    ``var_result`` carries no ``portfolio_id``; the factor-exposure rows are the nearest honest
    source (they stamp the pinned atom's ``portfolio_id`` — self-describing by design). A
    missing/foreign/other-portfolio run refuses pre-create."""
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
            raise VarBacktestInputError(
                f"VaR factor-exposure run {run_id} has no visible result rows — refused"
            )
        if found != {str(portfolio_id)}:
            raise VarBacktestInputError(
                f"VaR factor-exposure run {run_id} measures portfolio(s) {sorted(found)} != the "
                f"return run's portfolio {portfolio_id} — refused (cross-series identity)"
            )


def run_var_backtest(
    session: Session,
    *,
    acting_tenant: str,
    actor: VarBacktestActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    portfolio_return_run_id: str | None = None,
    var_run_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> VarBacktestRunResult:
    """Run a governed VaR backtest. Build-in-request (default — ``portfolio_return_run_id`` +
    ``var_run_ids``: builds a ``VAR_BACKTEST_INPUT`` snapshot) or consume-existing
    (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create. See the module
    docstring for the failure model + the AD-014 / CTRL-003 invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise VarBacktestInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise VarBacktestInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise VarBacktestInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise VarBacktestInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    build_args = (portfolio_return_run_id, var_run_ids)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise VarBacktestInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(portfolio_return_run_id/var_run_ids), not both"
        )
    # Inventory-before-use + model identity + the DECLARED alpha (CTRL-003 / OD-BT-1-A).
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=VAR_BACKTEST_MODEL_CODE,
    )
    alpha = declared_var_backtest_alpha(session, version)

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_VAR_BACKTEST_INPUT:
            raise VarBacktestInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != "
                f"{PURPOSE_VAR_BACKTEST_INPUT}"
            )
    else:
        if portfolio_return_run_id is None or not var_run_ids:
            raise VarBacktestInputError(
                "portfolio_return_run_id + var_run_ids (>= 1) are required to build a "
                "var-backtest snapshot"
            )
        _resolve_run(
            session,
            str(portfolio_return_run_id),
            acting_tenant=acting_tenant,
            run_type=_RETURN_RUN_TYPE,
            label="portfolio-return",
        )
        for run_id in var_run_ids:
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
            var_run_ids=[str(r) for r in var_run_ids],
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        return_raw, var_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(return_raw, var_raw)
    except VarBacktestInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content is the SAME refusal class as a semantically
        # ill-formed input — a governed 422, never a raw parse 500 (the P3-C3 wrapper).
        raise VarBacktestInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Re-resolve every provenance id from the PINNED CONTENT under the acting tenant BEFORE any is
    # stamped into a hard-FK column (PG FK checks bypass RLS — the P3-5 finding).
    _resolve_run(
        session,
        parsed.portfolio_return_run_id,
        acting_tenant=acting_tenant,
        run_type=_RETURN_RUN_TYPE,
        label="portfolio-return",
    )
    for run_id in parsed.var_run_ids:
        _resolve_run(
            session, run_id, acting_tenant=acting_tenant, run_type=RUN_TYPE_VAR, label="VaR"
        )
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=VarBacktestInputError
    )
    _assert_exposure_runs_portfolio(
        session,
        parsed.exposure_run_ids,
        portfolio_id=parsed.portfolio_id,
        acting_tenant=acting_tenant,
    )

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
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
            n_pairs: int,
            n_exceptions: int,
            test_decision: str | None = None,
            zone: str | None = None,
        ) -> VarBacktestResult:
            return VarBacktestResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_return_run_id=parsed.portfolio_return_run_id,
                portfolio_id=parsed.portfolio_id,
                metric_type=metric_type,
                var_metric_type=parsed.var_metric_type,
                period_start=period_start,
                period_end=period_end,
                metric_value=metric_value,
                realized_pnl=realized_pnl,
                var_value=var_value,
                n_pairs=n_pairs,
                n_exceptions=n_exceptions,
                confidence_level=parsed.confidence_level,
                horizon_days=parsed.horizon_days,
                test_decision=test_decision,
                basel_zone=zone,
                base_currency=parsed.base_currency,
            )

        def _out_of_range(*values: Decimal | None) -> bool:
            # EVERY persisted Numeric(28,6) column must clear the envelope — the metric AND the
            # money echoes (the P3-8 HIGH-fold lesson: an ungated echo overflows at the scaffold
            # flush as a raw 500 with the run orphaned in RUNNING).
            return any(v is not None and abs(v) >= _MAX_RESULT_ABS for v in values)

        try:
            exceptions = 0
            for pair in parsed.pairs:
                e = exception_indicator(pair.realized_pnl, pair.var_value)
                exceptions += e
                if _out_of_range(pair.realized_pnl, pair.var_value):
                    gaps.append(f"magnitude-out-of-range:pair:{pair.period_start}")
                    return [], gaps
                rows.append(
                    _mk(
                        METRIC_TYPE_EXCEPTION_INDICATOR,
                        Decimal(e),
                        pair.period_start,
                        pair.period_end,
                        realized_pnl=pair.realized_pnl,
                        var_value=pair.var_value,
                        n_pairs=1,
                        n_exceptions=e,
                    )
                )
            n = len(parsed.pairs)
            first, last = parsed.pairs[0], parsed.pairs[-1]
            rows.append(
                _mk(
                    METRIC_TYPE_EXCEPTION_COUNT,
                    Decimal(exceptions),
                    first.period_start,
                    last.period_end,
                    realized_pnl=None,
                    var_value=None,
                    n_pairs=n,
                    n_exceptions=exceptions,
                )
            )
            coverage_p = Decimal(1) - parsed.confidence_level
            lr = kupiec_lr(n, exceptions, coverage_p).quantize(
                _MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )  # the Numeric(28,6) storage scale — quantized HERE for SQLite/PG byte parity
            if _out_of_range(lr):
                gaps.append(f"magnitude-out-of-range:{METRIC_TYPE_KUPIEC_LR}:{lr:E}")
                return [], gaps
            rows.append(
                _mk(
                    METRIC_TYPE_KUPIEC_LR,
                    lr,
                    first.period_start,
                    last.period_end,
                    realized_pnl=None,
                    var_value=None,
                    n_pairs=n,
                    n_exceptions=exceptions,
                    test_decision=kupiec_decision(lr, alpha),
                )
            )
            if (
                parsed.confidence_level == _BASEL_CONFIDENCE
                and n == _BASEL_PAIRS
                and parsed.horizon_days == _BASEL_HORIZON_DAYS
            ):
                rows.append(
                    _mk(
                        METRIC_TYPE_BASEL_ZONE,
                        Decimal(exceptions),
                        first.period_start,
                        last.period_end,
                        realized_pnl=None,
                        var_value=None,
                        n_pairs=n,
                        n_exceptions=exceptions,
                        zone=basel_zone(exceptions),
                    )
                )
        except VarBacktestKernelError as exc:
            # Defense-in-depth: adjudication makes the structural cases unreachable; a kernel
            # refusal here is a committed FAILED run + DQ evidence, never a raw 500.
            gaps.append(f"kernel-refusal:{exc}")
            return [], gaps
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_VAR_BACKTEST,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="var-backtest run output sanity (values within the Numeric(28,6) scale)",
        rule_target_entity_type="var_backtest_result",
        result_entity_type="var_backtest_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return VarBacktestRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_var_backtests(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[VarBacktestResult]:
    """The ``var_backtest_result`` rows of a run (tenant-scoped; ordered by
    ``(metric_type, period_start)``)."""
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


def resolve_var_backtest_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a var-backtest ``calculation_run`` by ``run_id`` with an EXPLICIT tenant predicate
    + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable refusal
    evidence). Raises :class:`VarBacktestRunNotVisible` on a hidden/unknown/other run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_VAR_BACKTEST,
        not_visible=VarBacktestRunNotVisible,
    )


def resolve_var_backtest(
    session: Session, result_id: str, *, acting_tenant: str
) -> VarBacktestResult:
    """Resolve one ``var_backtest_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(VarBacktestResult).where(
            VarBacktestResult.id == str(result_id),
            VarBacktestResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarBacktestNotVisible(str(result_id))
    return row
