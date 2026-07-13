"""Ex-post benchmark-relative binder (P3-8, ENT-054 — the EIGHTH governed number, the SECOND perf-
family one, and the FIRST governed consumer of a captured vendor return series; closes P3-7 OD-G).

``run_benchmark_relative`` produces the ``benchmark_relative_result`` series (``n``
``ACTIVE_RETURN`` sub-period rows + ``TRACKING_DIFFERENCE``/``TRACKING_ERROR``/``INFORMATION_RATIO``
summary rows) ONLY
when bound to a ``dataset_snapshot`` (``BENCHMARK_RELATIVE_INPUT`` — pinning ALL result rows of ONE
COMPLETED ``PORTFOLIO_RETURN`` run + the in-span ``benchmark_return`` series) + a complete
``calculation_run`` + a **REGISTERED ``model_version`` OF THE BENCHMARK-RELATIVE MODEL**
(``perf.benchmark_relative`` v1; AD-014 / FW-RUN / TR-15 / CTRL-003 — the ``run_portfolio_return``
exemplar). The model carries NO free numeric parameter (OD-P3-8-A): the ``code_version`` + the fixed
v1 conventions ARE the identity.

The numbers are the realized performance statistics (``irp_shared.perf.benchmark_relative_kernel``):
per sub-period ``a_i = r_p,i − r_b,i`` (arithmetic active return), ``TD = R_p − R_b`` (compounded
difference), ``TE = sample_stdev_{n-1}(a_i)`` (ESMA ex-post; n ≥ 2), ``IR = mean(a_i)/TE``
(undefined
and OMITTED when TE = 0). The binder's arithmetic reads ONLY the pinned content (PURE — AD-014): the
DIETZ_PERIOD rows ARE ``r_p,i``; ``r_b,i`` is the geometric compounding of the pinned SIMPLE
benchmark rows in the SAME half-open sub-period window ``(period_start_i, period_end_i]``.

**v1 gates:** ``benchmark.benchmark_currency`` must equal the return run's ``base_currency`` (no FX
translation of return series); the caller's ``return_basis`` echoed on every row (gross-vs-basis
comparability recorded); an EXACT-LINKAGE cross-check recomputes ``Π(1+r_p,i)−1`` and requires
equality with the pinned ``TWR_LINKED`` value (a mismatch = a malformed hand-mint → refused).

Failure model (the PM-1 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing prerequisites; an unregistered or WRONG-MODEL version; a
  non-COMPLETED / cross-tenant / non-return run; a wrong-purpose snapshot; **pinned content that is
  not a well-formed v1 input** — no DIETZ rows, not exactly one TWR_LINKED, mixed
  run/portfolio/base,
  overlapping/unordered sub-periods, a benchmark currency ≠ base, a non-SIMPLE / mixed basis, a
  sub-period with ZERO benchmark rows, a linkage mismatch, or JSON-null/non-object fields): **raise
  BEFORE ``create_run``** => ZERO run + ZERO rows + ZERO run-audit. **NO imputation, ever.**
- **Post-create FAILED** (a column-legal-but-extreme pin whose metric OR whose
  portfolio/benchmark return echo overflows the ``Numeric(20,12)`` envelope ``|value| < 1E8`` —
  REACHABLE via a hand-minted snapshot; the kernel's 12dp-quantize guard bounds only the SCALE, so
  the compute checks ``abs(value) >= _MAX_RESULT_ABS`` explicitly for EVERY persisted column — the
  metric AND both echoes — the PM-1 B1 lesson): a committed FAILED run (``outcome='failure'``) +
  ``DATA.VALIDATE`` DQ evidence + ZERO rows + a magnitude-naming ``failure_reason``.

One-way imports: ``perf -> {snapshot, marketdata, calc, model, lineage, dq, audit, db}`` + a
models-only ``portfolio.models`` read (the measured-book tenant re-resolution — the PM-1 precedent);
imports NO ``risk`` symbol and NO ``exposure`` symbol; nothing imports ``perf``.
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
from irp_shared.calc.runs import resolve_completed_run_of_type, resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata import BenchmarkNotVisible, resolve_benchmark
from irp_shared.marketdata.models import BENCHMARK_RETURN_BASES, RETURN_TYPE_SIMPLE
from irp_shared.model.service import assert_model_version_of
from irp_shared.perf.benchmark_relative_kernel import (
    BenchmarkRelativeKernelError,
    active_series,
    compound_returns,
    information_ratio,
    mean_return,
    sample_stdev,
)
from irp_shared.perf.bootstrap import BENCHMARK_RELATIVE_MODEL_CODE
from irp_shared.perf.events import (
    RUN_TYPE_BENCHMARK_RELATIVE,
    RUN_TYPE_PORTFOLIO_RETURN,
    BenchmarkRelativeActor,
)
from irp_shared.perf.models import (
    METRIC_TYPE_ACTIVE_RETURN,
    METRIC_TYPE_INFORMATION_RATIO,
    METRIC_TYPE_TRACKING_DIFFERENCE,
    METRIC_TYPE_TRACKING_ERROR,
    BenchmarkRelativeResult,
)
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.snapshot import (
    COMPONENT_KIND_BENCHMARK_RETURN,
    COMPONENT_KIND_PORTFOLIO_RETURN,
    PURPOSE_BENCHMARK_RELATIVE_INPUT,
    SnapshotActor,
    build_benchmark_relative_snapshot,
    list_components,
    resolve_snapshot,
)

#: The PM-1 metric-type strings the pinned portfolio_return rows carry (read, not imported as the
#: perf return SERVICE — these are the ENT-053 column vocab; the binder distinguishes the sub-period
#: series from the summary row).
_DIETZ_PERIOD = "DIETZ_PERIOD"
_TWR_LINKED = "TWR_LINKED"

#: Per-tenant governed completeness DQ rule (resolve-or-register; the P3-1/3/4/5/7 + PM-1 pattern).
_COMPLETENESS_RULE_CODE = "perf.benchmark_relative.completeness"
#: The Numeric(20,12) column ceiling is |value| < 1E8; this gate sits deliberately ONE order inside
#: it (1E7) and bounds EVERY persisted Numeric(20,12) value — the metric_value AND the
#: portfolio_return_value / benchmark_return_value echoes. A column-legal-but-extreme pin
#: can drive a value past the column WITHOUT the kernel's 12dp-quantize guard firing (~1E38); this
#: gate turns that into a committed FAILED run (the PM-1 _MAX_RESULT_ABS precedent), never a PG
#: overflow 500. (The evidence echoes share the metric's Numeric(20,12) scale, so one constant gates
#: both — unlike PM-1, whose money evidence has a wider _MAX_EVIDENCE_ABS envelope.)
_MAX_RESULT_ABS = Decimal("1E7")


class BenchmarkRelativeInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class (a perf number never borrows a risk error). Maps to
    422."""


class BenchmarkRelativeNotVisible(Exception):
    """Raised when a ``benchmark_relative_result`` id is not visible in the acting tenant scope."""

    def __init__(self, result_id: str) -> None:
        super().__init__(
            f"benchmark_relative_result {result_id} is not visible in the current tenant"
        )
        self.result_id = str(result_id)


class BenchmarkRelativeRunNotVisible(Exception):
    """Raised when a benchmark-relative ``calculation_run`` id is not visible in the tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"benchmark-relative run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class BenchmarkRelativeRunResult:
    """The outcome of ``run_benchmark_relative``: the ``calculation_run`` + status + the series
    rows. ``status`` is ``COMPLETED`` (``rows`` = the ACTIVE_RETURN series + the summary rows) or
    ``FAILED``
    (the magnitude gate: a committed FAILED run + ZERO rows + a naming ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[BenchmarkRelativeResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _SubPeriod:
    """One adjudicated sub-period: the portfolio return (from a pinned DIETZ_PERIOD row) + the
    benchmark return values whose ``return_date`` falls in ``(period_start, period_end]``."""

    period_start: date
    period_end: date
    portfolio_return: Decimal
    benchmark_returns: list[Decimal]
    n_benchmark_obs: int


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the ordered sub-periods + the run-uniform descriptors + the
    pinned TWR_LINKED value (the exact-linkage reference)."""

    sub_periods: list[_SubPeriod]
    portfolio_id: str
    base_currency: str
    benchmark_id: str
    return_basis: str
    portfolio_return_run_id: str
    twr_linked: Decimal


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw portfolio-return / benchmark-series dicts
    (PURE — no live read; the AD-014 invariant)."""
    portfolio_raw: list[dict[str, Any]] = []
    benchmark_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_PORTFOLIO_RETURN:
            portfolio_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_BENCHMARK_RETURN:
            benchmark_raw.append(data)
    return portfolio_raw, benchmark_raw


def _adjudicate_pins(
    portfolio_raw: list[dict[str, Any]], benchmark_raw: list[dict[str, Any]]
) -> _ParsedInput:
    """PRE-CREATE adjudication of the FULL pinned input (both entry paths): a single-run/portfolio/
    base portfolio side; ordered non-overlapping DIETZ sub-periods + exactly one TWR_LINKED row; the
    exact-linkage cross-check; a single benchmark series of the SAME base currency, uniform
    SIMPLE/basis; per sub-period ≥ 1 benchmark row bucketed by the SAME half-open windows. Raises
    :class:`BenchmarkRelativeInputError` on any ill-formed input."""
    if not portfolio_raw:
        raise BenchmarkRelativeInputError(
            "the snapshot pins no PORTFOLIO_RETURN rows — not a benchmark-relative input"
        )
    dietz = [r for r in portfolio_raw if r["metric_type"] == _DIETZ_PERIOD]
    linked = [r for r in portfolio_raw if r["metric_type"] == _TWR_LINKED]
    if not dietz:
        raise BenchmarkRelativeInputError("the pinned return run has no DIETZ_PERIOD sub-periods")
    if len(linked) != 1:
        raise BenchmarkRelativeInputError(
            f"the pinned return run must carry exactly one TWR_LINKED row (got {len(linked)})"
        )

    run_ids = {str(r["calculation_run_id"]).lower() for r in portfolio_raw}
    portfolio_ids = {str(r["portfolio_id"]) for r in portfolio_raw}
    base_currencies = {r["base_currency"] for r in portfolio_raw}
    if len(run_ids) != 1:
        raise BenchmarkRelativeInputError("the pinned return rows span multiple runs — refused")
    if len(portfolio_ids) != 1:
        raise BenchmarkRelativeInputError(
            f"the pinned return rows span {len(portfolio_ids)} portfolios — refused"
        )
    if len(base_currencies) != 1:
        raise BenchmarkRelativeInputError(
            f"the pinned return rows carry mixed base currencies {sorted(base_currencies)}"
        )
    base_currency = next(iter(base_currencies))
    if not isinstance(base_currency, str) or len(base_currency) != 3:
        raise BenchmarkRelativeInputError(
            "the pinned return base_currency is not a 3-letter code — refused"
        )

    # Sub-periods from the DIETZ rows, ordered by period_start; strictly increasing + CONTIGUOUS
    # (period_end_i == period_start_{i+1}) so the sub-periods PARTITION the span exactly — every
    # benchmark row lands in exactly one window, none in an inter-window gap. A well-formed PM-1 run
    # is always contiguous (consecutive boundary valuations); a hand-minted GAP would silently drop
    # any benchmark return dated inside it, understating R_b/TD — so a gap is refused, not tolerated
    # (review fold: enforce contiguity, not merely non-overlap).
    ordered = sorted(dietz, key=lambda r: r["period_start"])
    periods: list[tuple[date, date, Decimal]] = []
    prev_end: date | None = None
    for r in ordered:
        start = date.fromisoformat(r["period_start"])
        end = date.fromisoformat(r["period_end"])
        if end <= start:
            raise BenchmarkRelativeInputError(
                f"sub-period {start}..{end} is non-positive — refused"
            )
        if prev_end is not None and start != prev_end:
            raise BenchmarkRelativeInputError(
                "the pinned DIETZ sub-periods are not contiguous (a gap or overlap at "
                f"{prev_end}..{start}) — refused"
            )
        periods.append((start, end, Decimal(r["return_value"])))
        prev_end = end

    # Exact-linkage cross-check: the recomputed geometric link of the DIETZ returns must EQUAL the
    # pinned TWR_LINKED value (PM-1 computed the link from these same 12dp inputs).
    twr_linked = Decimal(linked[0]["return_value"])
    if compound_returns([p[2] for p in periods]) != twr_linked:
        raise BenchmarkRelativeInputError(
            "the pinned DIETZ returns do not geometrically link to the pinned TWR_LINKED value "
            "— malformed input; refused"
        )

    # --- Benchmark side: one series component, same base currency, uniform SIMPLE/basis. ---
    if len(benchmark_raw) != 1:
        raise BenchmarkRelativeInputError(
            f"the snapshot must pin exactly one benchmark series (got {len(benchmark_raw)})"
        )
    bench = benchmark_raw[0]
    benchmark_id = str(bench["benchmark_id"]).lower()
    if bench["benchmark_currency"] != base_currency:
        raise BenchmarkRelativeInputError(
            f"benchmark currency {bench['benchmark_currency']!r} != portfolio base currency "
            f"{base_currency!r} — no FX translation in v1; refused"
        )
    if bench["return_type"] != RETURN_TYPE_SIMPLE:
        raise BenchmarkRelativeInputError(
            f"the pinned benchmark series return_type {bench['return_type']!r} is not SIMPLE"
        )
    return_basis = bench["return_basis"]
    if return_basis not in BENCHMARK_RETURN_BASES:
        raise BenchmarkRelativeInputError(f"unknown benchmark return_basis {return_basis!r}")
    bench_rows = bench["rows"]
    if any(
        r["return_type"] != RETURN_TYPE_SIMPLE or r["return_basis"] != return_basis
        for r in bench_rows
    ):
        raise BenchmarkRelativeInputError(
            "the pinned benchmark rows are not uniform SIMPLE/return_basis — refused"
        )
    dated_bench = [
        (date.fromisoformat(r["return_date"]), Decimal(r["return_value"])) for r in bench_rows
    ]

    # Bucket the benchmark rows into the sub-period windows; each sub-period needs >= 1 row.
    sub_periods: list[_SubPeriod] = []
    for start, end, r_p in periods:
        window = [v for (d, v) in dated_bench if start < d <= end]
        if not window:
            raise BenchmarkRelativeInputError(
                f"sub-period ({start}, {end}] has no benchmark returns — refused (no imputation)"
            )
        sub_periods.append(
            _SubPeriod(
                period_start=start,
                period_end=end,
                portfolio_return=r_p,
                benchmark_returns=window,
                n_benchmark_obs=len(window),
            )
        )

    # Every pinned benchmark row must map to exactly one sub-period window (defense-in-depth beyond
    # contiguity: catches a hand-minted row dated <= the first boundary or > the last boundary,
    # would otherwise be silently dropped from the compounding). The build path pins exactly the
    # in-span rows, so this always holds there.
    consumed = sum(sp.n_benchmark_obs for sp in sub_periods)
    if consumed != len(dated_bench):
        raise BenchmarkRelativeInputError(
            f"{len(dated_bench) - consumed} pinned benchmark return(s) fall outside the sub-period "
            "span — refused (every pinned benchmark row must map to exactly one sub-period)"
        )

    return _ParsedInput(
        sub_periods=sub_periods,
        portfolio_id=next(iter(portfolio_ids)),
        base_currency=base_currency,
        benchmark_id=benchmark_id,
        return_basis=return_basis,
        portfolio_return_run_id=next(iter(run_ids)),
        twr_linked=twr_linked,
    )


def _resolve_return_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Re-resolve the consumed PORTFOLIO_RETURN run under the acting tenant (+ run_type + COMPLETED)
    BEFORE its id is stamped into the ``portfolio_return_run_id`` hard FK — PG FK checks bypass RLS,
    so a hand-minted snapshot could otherwise reference a FOREIGN tenant's run (P3-5)."""
    return resolve_completed_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_PORTFOLIO_RETURN,
        label="portfolio-return",
        error=BenchmarkRelativeInputError,
    )


def run_benchmark_relative(
    session: Session,
    *,
    acting_tenant: str,
    actor: BenchmarkRelativeActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    portfolio_return_run_id: str | None = None,
    benchmark_id: str | None = None,
    return_basis: str | None = None,
    snapshot_id: str | None = None,
) -> BenchmarkRelativeRunResult:
    """Run a governed ex-post benchmark-relative calculation. Build-in-request (default —
    ``portfolio_return_run_id`` + ``benchmark_id`` + ``return_basis``: builds a
    ``BENCHMARK_RELATIVE_INPUT`` snapshot) or consume-existing (``snapshot_id``). BOTH paths
    adjudicate the pinned content pre-create. See the module docstring for the failure model + the
    AD-014 / CTRL-003 invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise BenchmarkRelativeInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise BenchmarkRelativeInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise BenchmarkRelativeInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise BenchmarkRelativeInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    build_args = (portfolio_return_run_id, benchmark_id, return_basis)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise BenchmarkRelativeInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(portfolio_return_run_id/benchmark_id/return_basis), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3).
    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=BENCHMARK_RELATIVE_MODEL_CODE,
    )

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_BENCHMARK_RELATIVE_INPUT:
            raise BenchmarkRelativeInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != "
                f"{PURPOSE_BENCHMARK_RELATIVE_INPUT}"
            )
    else:
        if not all(a is not None for a in build_args):
            raise BenchmarkRelativeInputError(
                "portfolio_return_run_id + benchmark_id + return_basis are required to build a "
                "benchmark-relative snapshot"
            )
        if return_basis not in BENCHMARK_RETURN_BASES:
            raise BenchmarkRelativeInputError(f"unknown benchmark return_basis {return_basis!r}")
        _resolve_return_run(session, str(portfolio_return_run_id), acting_tenant=acting_tenant)
        # Uniform pre-create refusal: an unknown benchmark_id is a 422 BenchmarkRelativeInputError
        # (matching _resolve_return_run on the same path + the PM-1 exposure-run precedent), NOT a
        # bare 404 BenchmarkNotVisible — the benchmark_id is a request-body prerequisite, not the
        # addressed resource (review fold: honor the module's uniform-refusal contract).
        try:
            resolve_benchmark(session, str(benchmark_id), acting_tenant=acting_tenant)
        except BenchmarkNotVisible as exc:
            raise BenchmarkRelativeInputError(
                f"benchmark {benchmark_id} is not visible in the acting tenant — refused"
            ) from exc
        snapshot = build_benchmark_relative_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            portfolio_return_run_id=str(portfolio_return_run_id),
            benchmark_id=str(benchmark_id),
            return_basis=str(return_basis),
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        portfolio_raw, benchmark_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(portfolio_raw, benchmark_raw)
    except BenchmarkRelativeInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content is the SAME refusal class as a semantically ill-
        # formed input — a governed 422, never a raw parse 500 (the P3-7/P3-C3 TypeError wrapper).
        raise BenchmarkRelativeInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Re-resolve the provenance ids from the PINNED CONTENT under the acting tenant BEFORE they are
    # stamped into hard-FK columns (PG FK checks bypass RLS — the P3-5 finding).
    _resolve_return_run(session, parsed.portfolio_return_run_id, acting_tenant=acting_tenant)
    try:
        resolve_benchmark(session, parsed.benchmark_id, acting_tenant=acting_tenant)
    except BenchmarkNotVisible as exc:
        raise BenchmarkRelativeInputError(
            f"the pinned benchmark {parsed.benchmark_id} is not visible — refused"
        ) from exc
    assert_portfolio_in_tenant(
        session,
        parsed.portfolio_id,
        acting_tenant=acting_tenant,
        error=BenchmarkRelativeInputError,
    )

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[BenchmarkRelativeResult], list[str]]:
        gaps: list[str] = []
        rows: list[BenchmarkRelativeResult] = []

        def _mk(
            metric_type: str,
            metric_value: Decimal,
            period_start: date,
            period_end: date,
            n_periods: int,
            n_obs: int,
            portfolio_return_value: Decimal | None,
            benchmark_return_value: Decimal | None,
        ) -> BenchmarkRelativeResult:
            return BenchmarkRelativeResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_return_run_id=parsed.portfolio_return_run_id,
                benchmark_id=parsed.benchmark_id,
                portfolio_id=parsed.portfolio_id,
                metric_type=metric_type,
                period_start=period_start,
                period_end=period_end,
                metric_value=metric_value,
                portfolio_return_value=portfolio_return_value,
                benchmark_return_value=benchmark_return_value,
                n_benchmark_obs=n_obs,
                n_periods=n_periods,
                base_currency=parsed.base_currency,
                return_basis=parsed.return_basis,
            )

        def _out_of_range(*values: Decimal | None) -> bool:
            # EVERY persisted Numeric(20,12) column — the metric AND the portfolio/benchmark return
            # echoes — must clear the envelope, not just the metric: a hand-minted pin can drive an
            # echo past the column while the (differenced) metric stays in range, and the scaffold's
            # flush is OUTSIDE the caught DataQualityError, so an ungated echo overflows as a 500
            # with the run orphaned in RUNNING (review fold: gate the evidence columns too).
            return any(v is not None and abs(v) >= _MAX_RESULT_ABS for v in values)

        try:
            benchmark_returns = [
                compound_returns(sp.benchmark_returns) for sp in parsed.sub_periods
            ]
            portfolio_returns = [sp.portfolio_return for sp in parsed.sub_periods]
            active = active_series(portfolio_returns, benchmark_returns)
            for sp, r_b, a in zip(parsed.sub_periods, benchmark_returns, active, strict=True):
                if _out_of_range(a, sp.portfolio_return, r_b):
                    gaps.append(f"magnitude-out-of-range:active:{a:E}")
                    return [], gaps
                rows.append(
                    _mk(
                        METRIC_TYPE_ACTIVE_RETURN,
                        a,
                        sp.period_start,
                        sp.period_end,
                        1,
                        sp.n_benchmark_obs,
                        sp.portfolio_return,
                        r_b,
                    )
                )
            r_b_total = compound_returns(benchmark_returns)
            tracking_difference = parsed.twr_linked - r_b_total
            tracking_error = sample_stdev(active) if len(active) >= 2 else None
            info_ratio = (
                information_ratio(mean_return(active), tracking_error)
                if tracking_error is not None and tracking_error != 0
                else None
            )
        except BenchmarkRelativeKernelError as exc:
            # A column-legal-but-extreme pin can drive a compounded/statistic value past the
            # Numeric(20,12) scale: a committed FAILED run + DQ evidence, never a PG overflow 500.
            gaps.append(f"magnitude-out-of-range:{exc}")
            return [], gaps

        first, last = parsed.sub_periods[0], parsed.sub_periods[-1]
        total_obs = sum(sp.n_benchmark_obs for sp in parsed.sub_periods)
        n = len(parsed.sub_periods)
        for metric_type, value, p_ev, b_ev in (
            (METRIC_TYPE_TRACKING_DIFFERENCE, tracking_difference, parsed.twr_linked, r_b_total),
            (METRIC_TYPE_TRACKING_ERROR, tracking_error, None, None),
            (METRIC_TYPE_INFORMATION_RATIO, info_ratio, None, None),
        ):
            if value is None:  # TE omitted when n<2; IR omitted when TE==0 (or TE absent)
                continue
            if _out_of_range(value, p_ev, b_ev):
                gaps.append(f"magnitude-out-of-range:{metric_type}:{value:E}")
                return [], gaps
            rows.append(
                _mk(
                    metric_type,
                    value,
                    first.period_start,
                    last.period_end,
                    n,
                    total_obs,
                    p_ev,
                    b_ev,
                )
            )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_BENCHMARK_RELATIVE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="benchmark-relative run output sanity (metrics within the Numeric(20,12) scale)",
        rule_target_entity_type="benchmark_relative_result",
        result_entity_type="benchmark_relative_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return BenchmarkRelativeRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_benchmark_relatives(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[BenchmarkRelativeResult]:
    """The ``benchmark_relative_result`` rows of a run (tenant-scoped; ordered by
    ``(metric_type, period_start)``)."""
    return list(
        session.execute(
            select(BenchmarkRelativeResult)
            .where(
                BenchmarkRelativeResult.calculation_run_id == str(run_id),
                BenchmarkRelativeResult.tenant_id == str(acting_tenant),
            )
            .order_by(BenchmarkRelativeResult.metric_type, BenchmarkRelativeResult.period_start)
        )
        .scalars()
        .all()
    )


def resolve_benchmark_relative_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a benchmark-relative ``calculation_run`` by ``run_id`` with an EXPLICIT tenant
    predicate + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable
    refusal evidence). Raises :class:`BenchmarkRelativeRunNotVisible` on a hidden/unknown/other
    run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_BENCHMARK_RELATIVE,
        not_visible=BenchmarkRelativeRunNotVisible,
    )


def resolve_benchmark_relative(
    session: Session, result_id: str, *, acting_tenant: str
) -> BenchmarkRelativeResult:
    """Resolve one ``benchmark_relative_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(BenchmarkRelativeResult).where(
            BenchmarkRelativeResult.id == str(result_id),
            BenchmarkRelativeResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise BenchmarkRelativeNotVisible(str(result_id))
    return row
