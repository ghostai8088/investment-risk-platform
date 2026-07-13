"""Perf-family run vocabulary + actors (PM-1 ENT-053 + P3-8 ENT-054 — the perf event surface).

The ``calculation_run.run_type`` FAMILY discriminators + the declared external-flow set + the run
initiators. Metric-type values live with the column vocab in ``perf.models``; ``run_type`` is
DISTINCT from every metric (the GS2 rule). The perf family hosts SEPARATE run families per governed
number: ``PORTFOLIO_RETURN`` (PM-1) and ``BENCHMARK_RELATIVE`` (P3-8, ex-post realized active return
/ TE / TD / IR — a distinct input set, so its OWN family, not a PORTFOLIO_RETURN metric). Money-
weighted / IRR is the reserved PA-0 measure (its own later family).
"""

from __future__ import annotations

from dataclasses import dataclass

#: The ``calculation_run.run_type`` FAMILY discriminator for a portfolio-return run (PM-1). Distinct
#: from ``metric_type`` (``DIETZ_PERIOD``/``TWR_LINKED``). **P3-8 amendment:** the ex-post
#: benchmark-relative metrics are NOT a PORTFOLIO_RETURN metric — they ship under the SEPARATE
#: ``BENCHMARK_RELATIVE`` run family below (a different input set; OD-P3-8-B). Money-weighted/IRR
#: (PA-0) remains reserved for its own later family.
RUN_TYPE_PORTFOLIO_RETURN = "PORTFOLIO_RETURN"

#: RESERVED audit code (the PERF decade) — NOT emitted in PM-1 (OD-PM-1-A: the run reuses
#: ``CALC.RUN_*``; ``PERF.RETURN_CREATE`` is reserved, never minted here).
PERF_RETURN_CREATE_EVENT_RESERVED = "PERF.RETURN_CREATE"

#: The ``calculation_run.run_type`` FAMILY discriminator for an ex-post benchmark-relative run
#: (P3-8). Distinct from every ``metric_type`` (ACTIVE_RETURN/TRACKING_DIFFERENCE/TRACKING_ERROR/
#: INFORMATION_RATIO — the GS2 family≠metric rule). REUSES ``perf.run``/``perf.view`` (no new mint).
RUN_TYPE_BENCHMARK_RELATIVE = "BENCHMARK_RELATIVE"
#: RESERVED audit code (the PERF decade) — NOT emitted in P3-8 (OD-P3-8-A; the run reuses
#: ``CALC.RUN_*``).
PERF_BENCHMARK_RELATIVE_CREATE_EVENT_RESERVED = "PERF.BENCHMARK_RELATIVE_CREATE"

#: The ``calculation_run.run_type`` FAMILY discriminator for a desmoothed-return run (PA-1, the
#: private-asset Geltner AR(1) transform). Distinct from every ``metric_type`` — the per-period
#: metric is deliberately named ``DESMOOTHED_PERIOD`` (the ``DIETZ_PERIOD`` precedent) so the GS2
#: family≠metric rule holds. REUSES ``perf.run``/``perf.view`` (no new mint — OD-PA-1-F).
RUN_TYPE_DESMOOTHED_RETURN = "DESMOOTHED_RETURN"
#: RESERVED audit code (the PERF decade) — NOT emitted in PA-1 (OD-PA-1-F; the run reuses
#: ``CALC.RUN_*``).
PERF_DESMOOTHED_RETURN_CREATE_EVENT_RESERVED = "PERF.DESMOOTHED_RETURN_CREATE"

#: The DECLARED external-flow set (the v1 model identity, OD-PM-1-C): a captured ``transaction`` is
#: an external flow ONLY if its ``txn_type`` is one of these — TRANSFER_IN a +contribution,
#: TRANSFER_OUT a -withdrawal. Every other captured txn_type (BUY/SELL/DIVIDEND/INTEREST/FEE/
#: REVERSAL/...) is INTERNAL to the measured book. Extending the set is a NEW version label, never
#: a silent re-read. Passed as DATA to ``build_return_snapshot`` (the snapshot never imports
#: ``perf``).
FLOW_TXN_TYPE_TRANSFER_IN = "TRANSFER_IN"
FLOW_TXN_TYPE_TRANSFER_OUT = "TRANSFER_OUT"
EXTERNAL_FLOW_TXN_TYPES = (FLOW_TXN_TYPE_TRANSFER_IN, FLOW_TXN_TYPE_TRANSFER_OUT)


@dataclass(frozen=True)
class PortfolioReturnActor:
    """The principal initiating a portfolio-return run (mirrors ``ActiveRiskActor`` /
    ``ExposureActor`` / ``SnapshotActor``)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class BenchmarkRelativeActor:
    """The principal initiating an ex-post benchmark-relative run (mirrors
    ``PortfolioReturnActor``)."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class DesmoothedReturnActor:
    """The principal initiating a desmoothed-return run (mirrors ``PortfolioReturnActor``)."""

    actor_id: str
    actor_type: str = "user"
