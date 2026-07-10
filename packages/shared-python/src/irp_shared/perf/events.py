"""Portfolio-return run vocabulary + actor (PM-1, ENT-053 — the perf family's event surface).

The ``calculation_run.run_type`` FAMILY discriminator + the declared external-flow set + the run
initiator. Metric-type values live with the column vocab in ``perf.models``
(``METRIC_TYPE_DIETZ_PERIOD``/``METRIC_TYPE_TWR_LINKED``); ``run_type`` is DISTINCT from them (the
family hosts the reserved money-weighted / ex-post metrics — a run_type must never equal a
metric_type, the P3-7 GS2 rule).
"""

from __future__ import annotations

from dataclasses import dataclass

#: The ``calculation_run.run_type`` FAMILY discriminator for a portfolio-return run (PM-1). Distinct
#: from ``metric_type`` (``DIETZ_PERIOD``/``TWR_LINKED``): the family hosts the reserved money-
#: weighted / IRR (PA-0) and ex-post active-return (P3-8) metrics.
RUN_TYPE_PORTFOLIO_RETURN = "PORTFOLIO_RETURN"

#: RESERVED audit code (the PERF decade) — NOT emitted in PM-1 (OD-PM-1-A: the run reuses
#: ``CALC.RUN_*``; ``PERF.RETURN_CREATE`` is reserved, never minted here).
PERF_RETURN_CREATE_EVENT_RESERVED = "PERF.RETURN_CREATE"

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
