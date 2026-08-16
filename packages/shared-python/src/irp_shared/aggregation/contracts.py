"""Consumed-measure declarations (STRUCT-1, REQ-PPM-006) — the contract module's first tenant.

**What this is.** Every governed family that consumes ``exposure_aggregate`` rows declares HERE
which exposure measure it reads. The declaration is LOAD-BEARING, not descriptive: the snapshot
pin builders filter atoms through :func:`consumed_exposure_measure` (a family's pins contain ONLY
its declared measure), and every family's pin parser refuses a foreign-measure atom that reaches
it anyway (defense in depth — see the family services). A mutation test proves the wiring: flipping
a declaration below changes the built pin set and makes the parser refusal fire. STRUCT-2 (REQ-
PPM-007) extends this module with the per-field aggregation operators; the shape here is the final
home, not a way-station.

**Why consumers declare ONE measure each today.** All four shipped consumers are market-value
semantics (factor allocation, BMV/EMV returns, concentration buckets, liquidity buckets) — a
NOTIONAL row summed into any of them is an economic category error, which is exactly the
double-count the REQ-PPM-006 amendment exists to prevent.

**Refusals.** :class:`UndeclaredConsumerError` — a family with no declaration asked for exposure
atoms (the census failure, fail-closed). :class:`ForeignMeasureError` — an atom of a measure the
family did not declare reached its parser. Both are P9-governed: each is named in a test that makes
it FIRE.
"""

from __future__ import annotations

from dataclasses import dataclass

from irp_shared.exposure.models import EXPOSURE_TYPE_MARKET_VALUE

#: run_type -> the exposure measure that family consumes. Keys are the CONSUMER families'
#: run-type strings (string literals, not imports: this module must stay import-light — the
#: consumers import it, and importing their events modules back would cycle. The literal-vs-
#: constant drift is pinned by test_aggregation_contracts asserting each key equals the family's
#: RUN_TYPE_* constant).
EXPOSURE_CONSUMER_MEASURES: dict[str, str] = {
    "FACTOR_EXPOSURE": EXPOSURE_TYPE_MARKET_VALUE,
    "PORTFOLIO_RETURN": EXPOSURE_TYPE_MARKET_VALUE,
    "CONCENTRATION": EXPOSURE_TYPE_MARKET_VALUE,
    "LIQUIDITY": EXPOSURE_TYPE_MARKET_VALUE,
}


class UndeclaredConsumerError(Exception):
    """A family requested exposure atoms without a consumed-measure declaration (REQ-PPM-006:
    "a consumer that declares nothing fails the census"). Fail-closed."""

    def __init__(self, run_type: str) -> None:
        super().__init__(
            f"run_type {run_type!r} consumes exposure but declares no measure in "
            "irp_shared.aggregation.contracts.EXPOSURE_CONSUMER_MEASURES"
        )
        self.run_type = str(run_type)


class ForeignMeasureError(Exception):
    """An exposure atom of an undeclared measure reached a family's pin parser (REQ-PPM-006:
    "must REFUSE a row of any other measure")."""

    def __init__(self, *, run_type: str, declared: str, found: str) -> None:
        super().__init__(
            f"run_type {run_type!r} declares measure {declared!r} and was given an atom of "
            f"measure {found!r} — refused, never converted"
        )
        self.run_type = str(run_type)
        self.declared = str(declared)
        self.found = str(found)


def consumed_exposure_measure(run_type: str) -> str:
    """The measure ``run_type`` declared, or :class:`UndeclaredConsumerError` (fail-closed —
    never a default)."""
    try:
        return EXPOSURE_CONSUMER_MEASURES[str(run_type)]
    except KeyError:
        raise UndeclaredConsumerError(str(run_type)) from None


def refuse_foreign_measure(run_type: str, atom_content: dict) -> None:
    """The parser-side refusal (defense in depth behind the builder filter): raise
    :class:`ForeignMeasureError` when a pinned exposure atom's ``exposure_type`` is not the
    measure ``run_type`` declared. An atom whose content carries NO ``exposure_type`` key is
    refused the same way (an unlabeled measure is not the declared one)."""
    declared = consumed_exposure_measure(run_type)
    found = atom_content.get("exposure_type")
    if found != declared:
        raise ForeignMeasureError(run_type=run_type, declared=declared, found=str(found))


# --------------------------------------------------------------------------------------------
# STRUCT-2 (REQ-PPM-007): the per-field aggregation operators.
# --------------------------------------------------------------------------------------------

#: The ratified operator vocabulary (DP-5, per-field). WEIGHTED ships with ZERO fields: its
#: canonical subject is DURATION — "portfolio duration is a number every fixed-income desk
#: quotes", market-value-weighted — and no duration-producing field exists in any result model
#: yet. The classification lands WITH the producer (the row's own trigger); minting a contract
#: entry for a field that does not exist would break the completeness census. IRR stays the
#: documented canonical NOT_AGGREGATABLE example, also with no producer.
OPERATOR_ADDITIVE = "ADDITIVE"
OPERATOR_WEIGHTED = "WEIGHTED"
OPERATOR_NOT_AGGREGATABLE = "NOT_AGGREGATABLE"
AGGREGATION_OPERATORS = (OPERATOR_ADDITIVE, OPERATOR_WEIGHTED, OPERATOR_NOT_AGGREGATABLE)

#: run_type -> {result field: operator} for EVERY family in the run-type registry except
#: RUN_TYPE_REPRODUCTION (DP-13, mirroring the reproduction census's own exclusion). Keys are
#: string literals (the import-light rule above); the census in test_aggregation_contracts pins
#: (a) EXACT set equality of family keys against the registry union and (b) per family, EXACT
#: coverage of the result model's numeric value columns — a field left out is a census failure,
#: never a silent default.
#:
#: Classification notes, stated once (the judgment IS the declaration; the census only proves
#: nothing was skipped):
#: - ADDITIVE is reserved for currency AMOUNTS over a common grain (exposure per measure,
#:   factor-exposure amounts, scenario P&L, pacing cashflows, MV boundary evidence, bucket
#:   amounts). ``exposure_amount`` is additive ONLY within one ``exposure_type`` — the
#:   mixed-measure refusal below is the enforcement.
#: - Returns, ratios, quantiles, volatilities, regression statistics, per-unit prices, FX
#:   composites, run PARAMETERS and observation COUNTS are NOT_AGGREGATABLE. For parameters and
#:   counts this deliberately conflates "economically wrong to sum" with "not a measure at all":
#:   both refuse, which is the fail-closed outcome the row demands. Counts that are additive
#:   only over DISJOINT partitions (n_flows, untiered_instrument_count) are NOT_AGGREGATABLE for
#:   the same fail-closed reason — nothing enforces the disjointness.
#: - VAR carries the ES metric types under one run type (seven model codes, one registry key),
#:   so its fields' operators govern ES values too — all NOT_AGGREGATABLE, so no conflation
#:   arises. VAR_BACKTEST/ES_BACKTEST share ``metric_value`` polymorphic by ``metric_type``
#:   (0/1 indicators, counts, ratios): most-restrictive-per-field = NOT_AGGREGATABLE.
#: - REPORT has no numeric value column: an empty contract IS its declaration (nothing on a
#:   report generation row may be summed).
AGGREGATION_CONTRACTS: dict[str, dict[str, str]] = {
    "EXPOSURE_AGGREGATE": {
        "exposure_amount": OPERATOR_ADDITIVE,  # per exposure_type ONLY — see the measure gate
        "signed_quantity": OPERATOR_NOT_AGGREGATABLE,  # cross-instrument sum is meaningless
        "mark_value": OPERATOR_NOT_AGGREGATABLE,  # a per-unit price (face value on NOTIONAL)
        "fx_rate": OPERATOR_NOT_AGGREGATABLE,  # a composite multiplier
    },
    "FACTOR_EXPOSURE": {
        "exposure_amount": OPERATOR_ADDITIVE,
        "loading": OPERATOR_NOT_AGGREGATABLE,  # v1 indicator; WEIGHTED when betas arrive
    },
    "SENSITIVITY": {
        "sensitivity_value": OPERATOR_ADDITIVE,  # only within one (curve, tenor, type, bump)
        "bump_bps": OPERATOR_NOT_AGGREGATABLE,  # a parameter
        "tenor_days": OPERATOR_NOT_AGGREGATABLE,  # a grain key
    },
    "SCENARIO": {
        "pnl": OPERATOR_ADDITIVE,
        "exposure_amount": OPERATOR_ADDITIVE,
        "shock_value": OPERATOR_NOT_AGGREGATABLE,  # a parameter
        "n_factors_exposed": OPERATOR_NOT_AGGREGATABLE,
        "n_factors_shocked": OPERATOR_NOT_AGGREGATABLE,
        "n_shocks_unmatched": OPERATOR_NOT_AGGREGATABLE,
    },
    "COVARIANCE": {
        "covariance_value": OPERATOR_NOT_AGGREGATABLE,  # a factor-pair statistic
        "n_observations": OPERATOR_NOT_AGGREGATABLE,
    },
    "COVARIANCE_PRIVATE": {
        "covariance_value": OPERATOR_NOT_AGGREGATABLE,
        "n_observations": OPERATOR_NOT_AGGREGATABLE,
    },
    "VAR": {
        "var_value": OPERATOR_NOT_AGGREGATABLE,  # the DP-6 fired subject: a summed VaR is NOT
        # the portfolio VaR (diversification), and the desk asking for it is exactly who the
        # HTTP refusal answers
        "sigma": OPERATOR_NOT_AGGREGATABLE,
        "z_score": OPERATOR_NOT_AGGREGATABLE,
        "residual_variance": OPERATOR_NOT_AGGREGATABLE,  # variances add only under independence
        "private_variance": OPERATOR_NOT_AGGREGATABLE,
        "confidence_level": OPERATOR_NOT_AGGREGATABLE,
        "horizon_days": OPERATOR_NOT_AGGREGATABLE,
        "n_factors": OPERATOR_NOT_AGGREGATABLE,
        "n_observations": OPERATOR_NOT_AGGREGATABLE,
        "estimate_age_days": OPERATOR_NOT_AGGREGATABLE,
    },
    "ACTIVE_RISK": {
        "te_value": OPERATOR_NOT_AGGREGATABLE,  # a volatility
        "portfolio_value": OPERATOR_ADDITIVE,  # a market value
        "n_factors": OPERATOR_NOT_AGGREGATABLE,
        "n_constituents": OPERATOR_NOT_AGGREGATABLE,
    },
    "VAR_BACKTEST": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,  # polymorphic by metric_type
        "var_value": OPERATOR_NOT_AGGREGATABLE,
        "es_value": OPERATOR_NOT_AGGREGATABLE,
        "realized_pnl": OPERATOR_NOT_AGGREGATABLE,  # a portfolio-level time series row
        "n_pairs": OPERATOR_NOT_AGGREGATABLE,
        "n_exceptions": OPERATOR_NOT_AGGREGATABLE,
        "confidence_level": OPERATOR_NOT_AGGREGATABLE,
        "horizon_days": OPERATOR_NOT_AGGREGATABLE,
    },
    "ES_BACKTEST": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,
        "var_value": OPERATOR_NOT_AGGREGATABLE,
        "es_value": OPERATOR_NOT_AGGREGATABLE,
        "realized_pnl": OPERATOR_NOT_AGGREGATABLE,
        "n_pairs": OPERATOR_NOT_AGGREGATABLE,
        "n_exceptions": OPERATOR_NOT_AGGREGATABLE,
        "confidence_level": OPERATOR_NOT_AGGREGATABLE,
        "horizon_days": OPERATOR_NOT_AGGREGATABLE,
    },
    "PORTFOLIO_RETURN": {
        "begin_mv": OPERATOR_ADDITIVE,
        "end_mv": OPERATOR_ADDITIVE,
        "net_external_flow": OPERATOR_ADDITIVE,
        "return_value": OPERATOR_NOT_AGGREGATABLE,  # TWR composition is not a weighted mean
        # under intra-period flows, and REQ-PPM-008's rollup identity excludes ratios
        "n_flows": OPERATOR_NOT_AGGREGATABLE,  # additive only over disjoint children
        "n_periods": OPERATOR_NOT_AGGREGATABLE,
    },
    "BENCHMARK_RELATIVE": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,
        "portfolio_return_value": OPERATOR_NOT_AGGREGATABLE,
        "benchmark_return_value": OPERATOR_NOT_AGGREGATABLE,
        "n_benchmark_obs": OPERATOR_NOT_AGGREGATABLE,
        "n_periods": OPERATOR_NOT_AGGREGATABLE,
    },
    "DESMOOTHED_RETURN": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,
        "observed_return": OPERATOR_NOT_AGGREGATABLE,
        "begin_mark": OPERATOR_NOT_AGGREGATABLE,  # instrument marks, not portfolio amounts
        "end_mark": OPERATOR_NOT_AGGREGATABLE,
        "alpha": OPERATOR_NOT_AGGREGATABLE,
        "alpha_stderr": OPERATOR_NOT_AGGREGATABLE,
        "observed_stdev": OPERATOR_NOT_AGGREGATABLE,
        "n_periods": OPERATOR_NOT_AGGREGATABLE,
    },
    "ROLLING_RISK": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,  # portfolio vol needs correlations
        "n_observations": OPERATOR_NOT_AGGREGATABLE,
        "window_months": OPERATOR_NOT_AGGREGATABLE,  # a parameter
    },
    "SHARPE": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,  # the DP-6 fired subject (a ratio)
        "n_observations": OPERATOR_NOT_AGGREGATABLE,
        "window_months": OPERATOR_NOT_AGGREGATABLE,  # a parameter
    },
    "PURE_PRIVATE_FACTOR": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,  # a pooled factor return
        "member_count": OPERATOR_NOT_AGGREGATABLE,
        "period_count": OPERATOR_NOT_AGGREGATABLE,
        "min_members": OPERATOR_NOT_AGGREGATABLE,
    },
    "PROXY_WEIGHT_ESTIMATE": {
        "metric_value": OPERATOR_NOT_AGGREGATABLE,  # a regression coefficient
        "std_error": OPERATOR_NOT_AGGREGATABLE,
        "residual_stdev": OPERATOR_NOT_AGGREGATABLE,
        "n_observations": OPERATOR_NOT_AGGREGATABLE,
        "n_regressors": OPERATOR_NOT_AGGREGATABLE,
        "min_observations": OPERATOR_NOT_AGGREGATABLE,
    },
    "PACING_PROJECTION": {
        "projected_call": OPERATOR_ADDITIVE,
        "projected_distribution": OPERATOR_ADDITIVE,
        "projected_nav": OPERATOR_ADDITIVE,
        "unfunded_end": OPERATOR_ADDITIVE,
        "period_index": OPERATOR_NOT_AGGREGATABLE,  # a grain key
    },
    "CONCENTRATION": {
        "gross_amount": OPERATOR_ADDITIVE,
        "long_amount": OPERATOR_ADDITIVE,
        "short_amount": OPERATOR_ADDITIVE,
        "net_amount": OPERATOR_ADDITIVE,
        "coverage_classifiable": OPERATOR_ADDITIVE,  # an amount
        "share_invested_long": OPERATOR_NOT_AGGREGATABLE,  # a ratio
        "metric_value": OPERATOR_NOT_AGGREGATABLE,  # HHI / top-N: neither sum nor weighting
        "coverage_ratio": OPERATOR_NOT_AGGREGATABLE,
    },
    "LIQUIDITY": {
        "long_amount": OPERATOR_ADDITIVE,
        "coverage_classifiable": OPERATOR_ADDITIVE,
        "tier_share": OPERATOR_NOT_AGGREGATABLE,
        "metric_value": OPERATOR_NOT_AGGREGATABLE,
        "coverage_ratio": OPERATOR_NOT_AGGREGATABLE,
        "untiered_instrument_count": OPERATOR_NOT_AGGREGATABLE,
    },
    "REPORT": {},  # no numeric value column exists; nothing on this family may be summed
}


# --------------------------------------------------------------------------------------------
# STRUCT-2 (REQ-PPM-007): the EMITTED GRAIN — the second, machine-readable half of the contract.
# The review's BLOCKING finding: the operator alone answers "may I sum this field" with no way
# to say OVER WHAT, which is how a contract-conformant consumer double-counts a stored TOTAL row
# with its own details, or sums across a partition dimension. The grain declaration closes that:
# a conformant ADDITIVE sum must (a) FIX one value of every ``additive_selector`` dimension and
# (b) include only rows matching ``detail_predicate`` where one is declared (the stored-total /
# summary rows are the family's own AGGREGATE output, never a summand).
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EmittedGrain:
    """What one family's result rows are keyed by, and what a conformant additive sum over them
    must respect. ``dimensions`` mirror the model's uniqueness grain (the completeness census
    asserts every named column exists on the model — a renamed column fails the census, never
    silently detaches the declaration)."""

    dimensions: tuple[str, ...]
    #: Dimensions a conformant ADDITIVE sum must FIX to one selected value (summing ACROSS them
    #: is a category error or a double-count): the exposure measure, a concentration dimension.
    additive_selectors: tuple[str, ...] = ()
    #: (column, required value): the summable DETAIL kind. Rows not matching are the family's
    #: own stored aggregate (a TOTAL/SUMMARY row) and must be EXCLUDED from any additive sum.
    detail_predicate: tuple[str, str] | None = None


#: The per-family emitted grain (dimensions from each model's uq_*_run_grain; tenant_id/run id
#: implied on every row and stated explicitly where they are part of the constraint).
EMITTED_GRAINS: dict[str, EmittedGrain] = {
    "EXPOSURE_AGGREGATE": EmittedGrain(
        dimensions=(
            "calculation_run_id",
            "portfolio_id",
            "instrument_id",
            "base_currency",
            "exposure_type",
        ),
        # Summing ACROSS measures adds notionals to market values — refused, never converted.
        additive_selectors=("exposure_type",),
    ),
    "FACTOR_EXPOSURE": EmittedGrain(
        dimensions=("calculation_run_id", "portfolio_id", "instrument_id", "factor_id"),
    ),
    "SENSITIVITY": EmittedGrain(
        dimensions=(
            "calculation_run_id",
            "curve_id",
            "value_type",
            "tenor_days",
            "sensitivity_type",
        ),
        # A curve total across tenors is meaningful; a sum across curves, value types or
        # sensitivity types is not one number.
        additive_selectors=("curve_id", "value_type", "sensitivity_type"),
    ),
    "SCENARIO": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "factor_id"),
        # THE review's double-count: the run stores per-factor SCENARIO_PNL rows AND one
        # SCENARIO_PNL_TOTAL row that IS their sum. A conformant sum includes details only.
        detail_predicate=("metric_type", "SCENARIO_PNL"),
    ),
    "COVARIANCE": EmittedGrain(
        dimensions=("calculation_run_id", "factor_id_1", "factor_id_2"),
    ),
    "COVARIANCE_PRIVATE": EmittedGrain(
        dimensions=("calculation_run_id", "factor_id_1", "factor_id_2"),
    ),
    "VAR": EmittedGrain(dimensions=("calculation_run_id", "metric_type")),
    "ACTIVE_RISK": EmittedGrain(dimensions=("calculation_run_id", "metric_type")),
    "VAR_BACKTEST": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "period_start"),
    ),
    "ES_BACKTEST": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "period_start"),
    ),
    "PORTFOLIO_RETURN": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "period_start"),
        # The additive MV/flow fields sum across NODES at one period — a sum across periods
        # or across DIETZ_PERIOD/TWR_LINKED kinds is a time-series category error.
        additive_selectors=("metric_type", "period_start"),
    ),
    "BENCHMARK_RELATIVE": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "period_start"),
    ),
    "DESMOOTHED_RETURN": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "period_start"),
    ),
    "ROLLING_RISK": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "window_months", "period_start"),
    ),
    "SHARPE": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "window_months", "period_start"),
    ),
    "PURE_PRIVATE_FACTOR": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "period_start"),
    ),
    "PROXY_WEIGHT_ESTIMATE": EmittedGrain(
        dimensions=("calculation_run_id", "metric_type", "factor_id"),
    ),
    "PACING_PROJECTION": EmittedGrain(
        dimensions=("calculation_run_id", "period_index"),
        # Cashflow projections sum meaningfully BOTH across periods (horizon total) and across
        # books at one period — no selector is imposed.
    ),
    "CONCENTRATION": EmittedGrain(
        dimensions=(
            "calculation_run_id",
            "row_kind",
            "dimension_kind",
            "bucket_code",
            "metric_type",
        ),
        # Every dimension partitions the WHOLE book: summing across dimension_kind counts the
        # book once per dimension.
        additive_selectors=("dimension_kind",),
        detail_predicate=("row_kind", "DETAIL"),
    ),
    "LIQUIDITY": EmittedGrain(
        dimensions=(
            "calculation_run_id",
            "portfolio_id",
            "row_kind",
            "bucket_code",
            "metric_type",
        ),
        detail_predicate=("row_kind", "DETAIL"),
    ),
    "REPORT": EmittedGrain(dimensions=("calculation_run_id",)),
}


def emitted_grain(run_type: str) -> EmittedGrain:
    """The declared grain, or :class:`NotAggregatableError` — an undeclared family refuses."""
    grain = EMITTED_GRAINS.get(str(run_type))
    if grain is None:
        raise NotAggregatableError(run_type=str(run_type), field="<grain>", operator=None)
    return grain


def require_additive_selection(run_type: str, provided: dict[str, str | None]) -> None:
    """The conformant-sum precondition a summed read calls BEFORE aggregating: every declared
    ``additive_selector`` must be FIXED by the caller. Raises :class:`NotAggregatableError`
    naming the missing dimension — a sum across it is refused, never converted. The requirement
    comes FROM the declaration (flip the declaration and the requirement moves with it — the
    grain half's result-obedience control)."""
    grain = emitted_grain(run_type)
    for dim in grain.additive_selectors:
        if provided.get(dim) in (None, ""):
            raise NotAggregatableError(run_type=str(run_type), field=dim, operator=None)


class NotAggregatableError(Exception):
    """An aggregation was requested for a field the family declares NOT_AGGREGATABLE (or for a
    family/field with no declaration — fail-closed). REQ-PPM-007: the refusal fires THROUGH the
    public read surface, so the routers map this to 422."""

    def __init__(self, *, run_type: str, field: str, operator: str | None) -> None:
        detail = (
            f"field {field!r} of family {run_type!r} is declared {operator}"
            if operator
            else f"family {run_type!r} declares no aggregation contract for field {field!r}"
        )
        super().__init__(f"aggregation refused: {detail} — it cannot be summed")
        self.run_type = str(run_type)
        self.field = str(field)
        self.operator = operator


def aggregation_operator(run_type: str, field: str) -> str:
    """The declared operator, or :class:`NotAggregatableError` (fail-closed — an undeclared
    family/field refuses, never defaults)."""
    family = AGGREGATION_CONTRACTS.get(str(run_type))
    if family is None:
        raise NotAggregatableError(run_type=str(run_type), field=str(field), operator=None)
    op = family.get(str(field))
    if op is None:
        raise NotAggregatableError(run_type=str(run_type), field=str(field), operator=None)
    return op


def assert_aggregatable(run_type: str, field: str) -> None:
    """The consumption-site precondition (REQ-PPM-007: every place that aggregates looks up the
    contract FIRST, and the lookup's RESULT governs). Raises :class:`NotAggregatableError`
    unless the field's declared operator is ADDITIVE — a WEIGHTED field needs weights the
    plain-sum sites do not carry, so it refuses here too."""
    op = aggregation_operator(run_type, field)
    if op != OPERATOR_ADDITIVE:
        raise NotAggregatableError(run_type=str(run_type), field=str(field), operator=op)
