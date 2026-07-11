"""Performance-measurement package (PM-1, ENT-053 — the SEVENTH governed number and the FIRST
non-risk one: a governed portfolio-return series).

Leaf domain package: ``perf -> {snapshot, marketdata, calc, model, lineage, dq, audit, db}`` —
the risk binders' sibling. Nothing imports ``perf``; ``perf`` imports NO ``risk`` symbol (the two
governed-number families are peers, not a chain). Every compute reads ONLY snapshot-pinned captured
content (never a live valuation/transaction read); run-bound + snapshot-gated + model_version-bound
(AD-014 / FW-RUN / TR-15 / CTRL-003).

PM-1 v1: chain-linked **time-weighted return** with **Modified-Dietz** within caller-supplied
valuation boundaries (GIPS 2020), over the market values of N COMPLETED ``exposure_aggregate`` runs
and the pinned external-transfer transactions between them. NO money-weighted/IRR (the private-asset
measure, deferred to PA-0); NO net-of-fees (no fee capture exists); NO attribution/annualization.
"""

from __future__ import annotations

from irp_shared.perf.benchmark_relative_kernel import (
    BenchmarkRelativeKernelError,
    active_series,
    compound_returns,
    information_ratio,
    mean_return,
    sample_stdev,
)
from irp_shared.perf.benchmark_relative_service import (
    BenchmarkRelativeInputError,
    BenchmarkRelativeNotVisible,
    BenchmarkRelativeRunNotVisible,
    BenchmarkRelativeRunResult,
    list_benchmark_relatives,
    resolve_benchmark_relative,
    resolve_benchmark_relative_run,
    run_benchmark_relative,
)
from irp_shared.perf.bootstrap import (
    BENCHMARK_RELATIVE_MODEL_CODE,
    BENCHMARK_RELATIVE_MODEL_NAME,
    BENCHMARK_RELATIVE_MODEL_TYPE,
    BENCHMARK_RELATIVE_VERSION_LABEL,
    PORTFOLIO_RETURN_MODEL_CODE,
    PORTFOLIO_RETURN_MODEL_NAME,
    PORTFOLIO_RETURN_MODEL_TYPE,
    PORTFOLIO_RETURN_VERSION_LABEL,
    register_benchmark_relative_model,
    register_portfolio_return_model,
)
from irp_shared.perf.events import (
    EXTERNAL_FLOW_TXN_TYPES,
    PERF_BENCHMARK_RELATIVE_CREATE_EVENT_RESERVED,
    PERF_RETURN_CREATE_EVENT_RESERVED,
    RUN_TYPE_BENCHMARK_RELATIVE,
    RUN_TYPE_PORTFOLIO_RETURN,
    BenchmarkRelativeActor,
    PortfolioReturnActor,
)
from irp_shared.perf.models import (
    METRIC_TYPE_ACTIVE_RETURN,
    METRIC_TYPE_DIETZ_PERIOD,
    METRIC_TYPE_INFORMATION_RATIO,
    METRIC_TYPE_TRACKING_DIFFERENCE,
    METRIC_TYPE_TRACKING_ERROR,
    METRIC_TYPE_TWR_LINKED,
    BenchmarkRelativeResult,
    PortfolioReturnResult,
)
from irp_shared.perf.queries import (
    LIST_LIMIT_DEFAULT,
    PERF_RUN_TYPES,
    PerfRunQueryError,
    list_perf_runs,
)
from irp_shared.perf.return_kernel import (
    DietzEstimate,
    ReturnKernelError,
    compute_dietz_period,
    dietz_denominator,
    link_periods,
)
from irp_shared.perf.return_service import (
    PortfolioReturnInputError,
    PortfolioReturnNotVisible,
    PortfolioReturnRunNotVisible,
    PortfolioReturnRunResult,
    list_portfolio_returns,
    resolve_portfolio_return,
    resolve_portfolio_return_run,
    run_portfolio_return,
)

__all__ = [
    # kernel
    "DietzEstimate",
    "ReturnKernelError",
    "compute_dietz_period",
    "dietz_denominator",
    "link_periods",
    # registrar
    "PORTFOLIO_RETURN_MODEL_CODE",
    "PORTFOLIO_RETURN_MODEL_NAME",
    "PORTFOLIO_RETURN_MODEL_TYPE",
    "PORTFOLIO_RETURN_VERSION_LABEL",
    "register_portfolio_return_model",
    # events / vocab
    "RUN_TYPE_PORTFOLIO_RETURN",
    "EXTERNAL_FLOW_TXN_TYPES",
    "PERF_RETURN_CREATE_EVENT_RESERVED",
    "PortfolioReturnActor",
    # model + metric vocab
    "PortfolioReturnResult",
    "METRIC_TYPE_DIETZ_PERIOD",
    "METRIC_TYPE_TWR_LINKED",
    # binder
    "run_portfolio_return",
    "list_portfolio_returns",
    "resolve_portfolio_return",
    "resolve_portfolio_return_run",
    "PortfolioReturnRunResult",
    "PortfolioReturnInputError",
    "PortfolioReturnNotVisible",
    "PortfolioReturnRunNotVisible",
    # runs listing
    "list_perf_runs",
    "PerfRunQueryError",
    "PERF_RUN_TYPES",
    "LIST_LIMIT_DEFAULT",
    # P3-8 benchmark-relative — kernel
    "BenchmarkRelativeKernelError",
    "compound_returns",
    "active_series",
    "mean_return",
    "sample_stdev",
    "information_ratio",
    # P3-8 registrar
    "BENCHMARK_RELATIVE_MODEL_CODE",
    "BENCHMARK_RELATIVE_MODEL_NAME",
    "BENCHMARK_RELATIVE_MODEL_TYPE",
    "BENCHMARK_RELATIVE_VERSION_LABEL",
    "register_benchmark_relative_model",
    # P3-8 events / vocab
    "RUN_TYPE_BENCHMARK_RELATIVE",
    "PERF_BENCHMARK_RELATIVE_CREATE_EVENT_RESERVED",
    "BenchmarkRelativeActor",
    # P3-8 model + metric vocab
    "BenchmarkRelativeResult",
    "METRIC_TYPE_ACTIVE_RETURN",
    "METRIC_TYPE_TRACKING_DIFFERENCE",
    "METRIC_TYPE_TRACKING_ERROR",
    "METRIC_TYPE_INFORMATION_RATIO",
    # P3-8 binder
    "run_benchmark_relative",
    "list_benchmark_relatives",
    "resolve_benchmark_relative",
    "resolve_benchmark_relative_run",
    "BenchmarkRelativeRunResult",
    "BenchmarkRelativeInputError",
    "BenchmarkRelativeNotVisible",
    "BenchmarkRelativeRunNotVisible",
]
