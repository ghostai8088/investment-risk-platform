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

#: The ``calculation_run.run_type`` discriminator for a proxy-weight-estimation run (PA-3). Reuses
#: ``risk.run``/``risk.view`` (no mint) + ``CALC.RUN_*`` (no new audit code).
RUN_TYPE_PROXY_WEIGHT_ESTIMATE = "PROXY_WEIGHT_ESTIMATE"
#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in PA-3.
RISK_PROXY_WEIGHT_ESTIMATE_CREATE_EVENT_RESERVED = "RISK.PROXY_WEIGHT_ESTIMATE_CREATE"

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

#: Controlled-vocab ``var_result.metric_type`` (P3-5; ``ES_PARAMETRIC`` is reserved — the
#: closed-form seam ``ES = sigma * phi(z) / (1 - alpha)`` is recorded, never emitted in v1).
METRIC_TYPE_VAR_PARAMETRIC = "VAR_PARAMETRIC"
#: VAR-HS-1 (OD-VHS-C): the historical-simulation metric on the SAME var_result grain.
METRIC_TYPE_VAR_HISTORICAL = "VAR_HISTORICAL"
METRIC_TYPE_ES_PARAMETRIC_RESERVED = "ES_PARAMETRIC"
METRIC_TYPES = (METRIC_TYPE_VAR_PARAMETRIC, METRIC_TYPE_VAR_HISTORICAL)

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
class ProxyWeightEstimateActor:
    """The principal initiating a proxy-weight-estimation run (PA-3; mirrors :class:`VarActor`)."""

    actor_id: str
    actor_type: str = "user"
