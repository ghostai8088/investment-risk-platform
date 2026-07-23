"""Risk run actors + run-types + reserved audit constants (P3-1 sensitivities, P3-3 factor
exposures — ENT-028).

A risk run's audit is the **calculation_run lifecycle** — it reuses the shipped
``CALC.RUN_CREATE`` + ``CALC.RUN_STATUS_CHANGE`` emitters (``calc/service.py``) + the
model-registry
``MODEL.REGISTER``/``MODEL.VERSION`` events, so NEITHER slice mints a new audit emitter: the
``sensitivity_result``/``factor_exposure_result`` rows are run-tracked + lineaged (metadata of the
already-audited run) — the ``exposure_aggregate``/``ingestion_staged_record`` precedent.
``audit/service.py`` is FROZEN.

The ``RISK.*`` family (the EVT-220 decade — the next domain decade after EXPOSURE/EVT-210) is
**RESERVED — NOT emitted**: ``RISK.SENSITIVITY_CREATE`` (P3-1, OD-P3-1-H) and
``RISK.FACTOR_EXPOSURE_CREATE`` (P3-3, OD-P3-3-K) are reserved only for a possible future granular
per-result audit if later documented. There is deliberately no events emitter here.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The ``calculation_run.run_type`` discriminator for a sensitivity run.
RUN_TYPE_SENSITIVITY = "SENSITIVITY"

#: The ``calculation_run.run_type`` discriminator for a factor-exposure run (P3-3).
RUN_TYPE_FACTOR_EXPOSURE = "FACTOR_EXPOSURE"

#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-1 (recorded for the
#: taxonomy).
RISK_SENSITIVITY_CREATE_EVENT_RESERVED = "RISK.SENSITIVITY_CREATE"

#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-3 (OD-P3-3-K; the
#: ``RISK.SENSITIVITY_CREATE``/``EXPOSURE.*`` reserved-only precedent).
RISK_FACTOR_EXPOSURE_CREATE_EVENT_RESERVED = "RISK.FACTOR_EXPOSURE_CREATE"

#: The ``calculation_run.run_type`` discriminator for a covariance-estimation run (P3-4).
RUN_TYPE_COVARIANCE = "COVARIANCE"

#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-4 (OD-P3-4-L).
RISK_COVARIANCE_CREATE_EVENT_RESERVED = "RISK.COVARIANCE_CREATE"

#: PPF-2 (OD-PPF-2-A/B): the PRIVATE-covariance run family — the block Ω_pp over ≥2 PRIVATE segment
#: factors' pure-private APPRAISAL return series (PPF-1), a fail-closed SIBLING of ``COVARIANCE``
#: reusing the generic ``estimate_covariance`` kernel + the shared ``covariance_result`` table
#: (frequency=APPRAISAL). The run_type is the sole table discriminator — the public reads filter it
#: (step 1). The 19th governed number (§2.1 arc slice 2). Reuses ``risk.run``/``risk.view`` (no
#: mint) + ``CALC.RUN_*`` (no new audit — the RISK/EVT-220 governed-number precedent).
RUN_TYPE_COVARIANCE_PRIVATE = "COVARIANCE_PRIVATE"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in PPF-2.
RISK_COVARIANCE_PRIVATE_CREATE_EVENT_RESERVED = "RISK.COVARIANCE_PRIVATE_CREATE"

#: The ``calculation_run.run_type`` discriminator for a VaR run (P3-5).
RUN_TYPE_VAR = "VAR"

#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-5 (OD-P3-5-K).
RISK_VAR_CREATE_EVENT_RESERVED = "RISK.VAR_CREATE"

#: The ``calculation_run.run_type`` FAMILY discriminator for an active-risk run (P3-7). Distinct
#: from the ``metric_type`` (``TRACKING_ERROR`` in v1): the family hosts further reserved EX-ANTE
#: active metrics — as ``VAR`` hosts VAR_PARAMETRIC + VAR_HISTORICAL (review: run_type must never
#: equal metric_type). **P3-8 amendment:** the EX-POST (realized) active-return / IR metrics do NOT
#: land here — they ship in the ``perf`` family under ``BENCHMARK_RELATIVE`` (a realized performance
#: statistic is a perf number, and its inputs differ; the P3-7 planning note that parked them here
#: predated the perf family's existence — superseded, OD-P3-8-B).
RUN_TYPE_ACTIVE_RISK = "ACTIVE_RISK"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-7 (OD-P3-7-A).
RISK_ACTIVE_RISK_CREATE_EVENT_RESERVED = "RISK.ACTIVE_RISK_CREATE"

#: BT-1 (OD-BT-1-B): the VaR-backtesting run family — SR 11-7 outcomes analysis of ONE VaR method
#: per run over realized flow-adjusted P&L (PM-1). DISTINCT from every metric (GS2). Reuses
#: ``risk.run``/``risk.view`` (no mint) + ``CALC.RUN_*`` (no new audit code).
RUN_TYPE_VAR_BACKTEST = "VAR_BACKTEST"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in BT-1.
RISK_VAR_BACKTEST_CREATE_EVENT_RESERVED = "RISK.VAR_BACKTEST_CREATE"

#: BT-3 (OD-BT-3-C/D): the ES-backtesting run family — the Acerbi-Szekely Z statistics over
#: sibling (VaR-HS, ES-HS) forecast pairs sharing input_snapshot_id, against realized
#: flow-adjusted P&L (PM-1). DISTINCT from every metric (GS2). Reuses ``risk.run``/``risk.view``
#: (no mint) + ``CALC.RUN_*`` (no new audit code).
RUN_TYPE_ES_BACKTEST = "ES_BACKTEST"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in BT-3.
RISK_ES_BACKTEST_CREATE_EVENT_RESERVED = "RISK.ES_BACKTEST_CREATE"

#: The ``calculation_run.run_type`` discriminator for a proxy-weight-estimation run (PA-3). Reuses
#: ``risk.run``/``risk.view`` (no mint) + ``CALC.RUN_*`` (no new audit code).
RUN_TYPE_PROXY_WEIGHT_ESTIMATE = "PROXY_WEIGHT_ESTIMATE"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in PA-3.
RISK_PROXY_WEIGHT_ESTIMATE_CREATE_EVENT_RESERVED = "RISK.PROXY_WEIGHT_ESTIMATE_CREATE"

#: PPF-1 (OD-PPF-1-D): the pure-private factor-return run family — pools member instruments'
#: desmoothed-minus-proxy residuals into ONE PRIVATE segment factor's appraisal-period return
#: series (the 18th governed number, §2.1 arc slice 1). Reuses ``risk.run``/``risk.view`` (no mint)
#: + ``CALC.RUN_*`` (no new audit — the RISK/EVT-220 governed-number precedent).
RUN_TYPE_PURE_PRIVATE_FACTOR = "PURE_PRIVATE_FACTOR"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in PPF-1.
RISK_PURE_PRIVATE_FACTOR_CREATE_EVENT_RESERVED = "RISK.PURE_PRIVATE_FACTOR_CREATE"

#: P3-6 (OD-P3-6-E): the stress/scenario run family — deterministic linear factor-shock P&L over ONE
#: factor-exposure run x a pinned scenario shock set. DISTINCT from its metric_types (SCENARIO_PNL /
#: SCENARIO_PNL_TOTAL). Reuses ``risk.run``/``risk.view`` (no mint) + ``CALC.RUN_*`` (no new audit).
RUN_TYPE_SCENARIO = "SCENARIO"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-6.
RISK_SCENARIO_CREATE_EVENT_RESERVED = "RISK.SCENARIO_CREATE"

#: Controlled-vocab ``sensitivity_type`` (plain String, no enum/CHECK; app-side allow-list).
SENSITIVITY_TYPE_DV01 = "DV01"
SENSITIVITY_TYPE_SPREAD_DV01 = "SPREAD_DV01"
SENSITIVITY_TYPES = (SENSITIVITY_TYPE_DV01, SENSITIVITY_TYPE_SPREAD_DV01)

#: Controlled-vocab ``covariance_result.statistic_type`` (P3-4; ``CORRELATION`` is reserved —
#: extend by value later, never emitted in v1).
STATISTIC_TYPE_COVARIANCE = "COVARIANCE"
STATISTIC_TYPE_CORRELATION_RESERVED = "CORRELATION"
STATISTIC_TYPES = (STATISTIC_TYPE_COVARIANCE,)

#: Controlled-vocab ``var_result.metric_type`` (P3-5).
METRIC_TYPE_VAR_PARAMETRIC = "VAR_PARAMETRIC"
#: VAR-HS-1 (OD-VHS-C): the historical-simulation metric on the SAME var_result grain.
METRIC_TYPE_VAR_HISTORICAL = "VAR_HISTORICAL"
#: ES-1 (OD-ES-1-C/D): REALIZED 2026-07-15. Reserved BY VALUE since P3-5, whose recorded seam
#: ``ES = sigma * phi(z) / (1 - alpha)`` never defined ``alpha``; ES-1 pins the convention
#: (``alpha`` = the CONFIDENCE level) and emits the number. ONE value for BOTH ES families — the
#: plain ``risk.var.parametric_es`` and the total ``risk.var.parametric_es_total`` — exactly as
#: ``VAR_PARAMETRIC_TOTAL`` is one value with its own model code. The row's ``var_value`` holds
#: the ES (the VAR_HISTORICAL generic-by-metric_type precedent). NO migration was needed: the
#: grain's UNIQUE (calculation_run_id, metric_type) already permitted it and every column existed.
METRIC_TYPE_ES_PARAMETRIC = "ES_PARAMETRIC"
#: PA-4 (OD-PA-4-B): total parametric VaR = factor + idiosyncratic residual variance, on the SAME
#: var_result grain (a NEW registered model dispatched through the parametric binder).
METRIC_TYPE_VAR_PARAMETRIC_TOTAL = "VAR_PARAMETRIC_TOTAL"
#: PPF-3 (OD-PPF-3-A): the UNIFIED public+private parametric VaR = factor variance x'Sigma*x + the
#: pure-private systematic block p'(Omega_pp/d_t)*p + the idiosyncratic residual over the
#: NON-private-segment members (the REPARTITION — a private fund's non-public variance moves from
#: the diagonal residual into PPF-2's correlated Omega_pp block, so the value over total-VaR is
#: exactly the Omega_pp off-diagonal cross-fund co-movement). The §2.1 arc's final slice, the 20th
#: governed number, on the SAME var_result grain (a NEW registered model, its OWN binder path).
#: Backtestability is a future slice's concern (the BT-2 honest-pairing doctrine applies as to
#: VAR_PARAMETRIC_TOTAL) — DELIBERATELY absent from VAR_BACKTEST_METRIC_TYPES in v1.
METRIC_TYPE_VAR_PARAMETRIC_UNIFIED = "VAR_PARAMETRIC_UNIFIED"
#: ES-HS-1 (OD-ES-HS-1-A): the EMPIRICAL Expected Shortfall over the historical-simulation
#: scenario P&L distribution — the Acerbi-Tasche Prop 4.1 α-tail-mean (floor count + fractional
#: boundary weight, ÷ n·a), NEVER the mean of the worst ⌈n·a⌉ (that is the forbidden TCE). The
#: row's var_value holds the ES with the exact VAR_HISTORICAL NULL shape (0041 widened the 0028
#: CHECK for it). NOT in METRIC_TYPES: the Acerbi-Szekely backtest SHIPPED at BT-3
#: (``risk.es_backtest``; pairing via shared input_snapshot_id) — the binder refuses this value
#: DELIBERATELY (a tail-mean series is not a quantile-count backtest input).
METRIC_TYPE_ES_HISTORICAL = "ES_HISTORICAL"
#: The BACKTESTABLE subset of the var_result vocabulary — NOT the full vocabulary. PA-4 excluded
#: ``VAR_PARAMETRIC_TOTAL`` as a recorded v1 scope-out; **BT-2 (2026-07-15, OD-BT-2-A) is the
#: ratified slice that admits it** — with the honest-pairing DOCTRINE attached, not as a constant
#: swap: every VaR here is a hard-enforced 1-DAY forecast (``VAR_HORIZON_DAYS``), so on an
#: appraisal-marked book the daily total-series read is biased TWO WAYS by construction —
#: exceptions are mechanically suppressed between marks (the private leg's realized P&L is flat)
#: and clustered ON mark dates (a whole appraisal period's move lands against a 1-day allowance).
#: The unconditional Kupiec/Basel verdict on such a book is therefore NOT valid evidence of
#: adequacy in EITHER direction (validity degrades with the private-leg share); the dated per-pair
#: EXCEPTION_INDICATOR rows are the honest evidence surface. See ``var_backtesting_v1.md`` (the
#: BT-2 scope amendment) + the registered limitations.
#:
#: **``ES_PARAMETRIC`` is DELIBERATELY ABSENT — a ratified omission (ES-1, OD-ES-1-F), not an
#: oversight and no longer "unbuilt".** ES-1 built it and ratified NOT admitting it. The reason is
#: FRTB precedent + parametric redundancy, NOT non-elicitability ("ES cannot be backtested" is
#: FALSE — Acerbi-Szekely 2014; Fissler-Ziegel 2016): FRTB backtests VaR and never ES
#: (MAR32.4/32.5/32.18), and under the ES leg's own normality an ES backtest is the VaR backtest
#: with a rescaled threshold — no new information. A genuine ES backtest earns its place when a
#: non-elliptical ES-over-historical-simulation leg exists — SHIPPED at ES-HS-1
#: (``risk.var.historical_es``) and backtested at BT-3 (``risk.es_backtest``). The discipline
#: stands for every future method: do NOT "complete the vocabulary" here without a ratified slice
#: that confronts that method's pairing semantics.
METRIC_TYPES = (
    METRIC_TYPE_VAR_PARAMETRIC,
    METRIC_TYPE_VAR_HISTORICAL,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
)

#: Controlled-vocab ``active_risk_result.metric_type`` (P3-7; further active metrics reserved by
#: value — e.g. active return / information ratio ship with the deferred ex-post slice).
METRIC_TYPE_TRACKING_ERROR = "TRACKING_ERROR"
ACTIVE_RISK_METRIC_TYPES = (METRIC_TYPE_TRACKING_ERROR,)

#: Controlled-vocab ``var_backtest_result.metric_type`` (BT-1): the per-pair exception series +
#: the summary statistics. The Basel zone value itself lives in the DEDICATED ``basel_zone``
#: string column (GREEN/YELLOW/RED is not a number); its metric row carries the exception count.
METRIC_TYPE_EXCEPTION_INDICATOR = "EXCEPTION_INDICATOR"
METRIC_TYPE_EXCEPTION_COUNT = "EXCEPTION_COUNT"
METRIC_TYPE_KUPIEC_LR = "KUPIEC_LR"
METRIC_TYPE_BASEL_ZONE = "BASEL_ZONE"
VAR_BACKTEST_METRIC_TYPES = (
    METRIC_TYPE_EXCEPTION_INDICATOR,
    METRIC_TYPE_EXCEPTION_COUNT,
    METRIC_TYPE_KUPIEC_LR,
    METRIC_TYPE_BASEL_ZONE,
)

#: BT-3 (OD-BT-3-E): the Christoffersen Markov-leg metric types, emitted ONLY by a
#: ``risk.var_backtest`` version declaring ``independence=CHRISTOFFERSEN_MARKOV`` (the v2
#: convention; v1 rows byte-preserved). A DEGENERATE 2x2 (no transition leaving a state) emits
#: NEITHER row — the exception-count row makes the absence legible; never coerced to 0.
METRIC_TYPE_LR_IND = "LR_IND"
METRIC_TYPE_LR_CC = "LR_CC"

#: BT-3 (OD-BT-3-A/B): the ES-backtest metric types (ENT-055 grain, the BT-2 zero-schema
#: precedent for the metric_type vocabulary; ``es_value`` is the ONE 0043 column). ``AS_Z1``
#: is emitted ONLY when the series has >= 1 exception (UNDEFINED at zero — no row, never 0);
#: the ``AS_Z2`` row carries the domain-gated verdict ONLY at (confidence 0.9750, n_pairs 250).
METRIC_TYPE_ES_EXCEPTION_INDICATOR = "ES_EXCEPTION_INDICATOR"
METRIC_TYPE_ES_PAIR_COUNT = "ES_PAIR_COUNT"
METRIC_TYPE_AS_Z2 = "AS_Z2"
METRIC_TYPE_AS_Z1 = "AS_Z1"
ES_BACKTEST_METRIC_TYPES = (
    METRIC_TYPE_ES_EXCEPTION_INDICATOR,
    METRIC_TYPE_ES_PAIR_COUNT,
    METRIC_TYPE_AS_Z2,
    METRIC_TYPE_AS_Z1,
)

#: P3-6 scenario metric types: one SCENARIO_PNL per exposed factor + one SCENARIO_PNL_TOTAL
#: (factor_id NULL) carrying the coverage counts. DISTINCT from the run_type (SCENARIO).
METRIC_TYPE_SCENARIO_PNL = "SCENARIO_PNL"
METRIC_TYPE_SCENARIO_PNL_TOTAL = "SCENARIO_PNL_TOTAL"
SCENARIO_METRIC_TYPES = (METRIC_TYPE_SCENARIO_PNL, METRIC_TYPE_SCENARIO_PNL_TOTAL)


@dataclass(frozen=True)
class SensitivityActor:
    """The principal initiating a sensitivity run (mirrors ``ExposureActor``/``SnapshotActor``)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class FactorExposureActor:
    """The principal initiating a factor-exposure run (mirrors :class:`SensitivityActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class CovarianceActor:
    """The principal initiating a covariance-estimation run (mirrors :class:`SensitivityActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class VarActor:
    """The principal initiating a VaR run (mirrors :class:`SensitivityActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class ActiveRiskActor:
    """The principal initiating an active-risk (tracking-error) run (mirrors :class:`VarActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class VarBacktestActor:
    """The principal initiating a VaR-backtesting run (mirrors :class:`VarActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class EsBacktestActor:
    """The principal initiating an ES-backtesting run (BT-3; mirrors :class:`VarBacktestActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class ProxyWeightEstimateActor:
    """The principal initiating a proxy-weight-estimation run (PA-3; mirrors :class:`VarActor`)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class PurePrivateFactorActor:
    """The principal initiating a pure-private factor-return run (PPF-1; mirrors ``VarActor``)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class PurePrivateCovarianceActor:
    """The principal initiating a private-covariance (Ω_pp) run (PPF-2; mirrors covariance)."""

    actor_id: str
    actor_type: str = "user"
