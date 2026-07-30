"""CON-1 run family + actor (the perf/risk events convention)."""

from __future__ import annotations

from dataclasses import dataclass

#: The run family. GS2 (family ≠ metric, platform-wide census in ``test_sharpe.py``): no metric
#: in ``CONCENTRATION_METRIC_TYPES`` carries this value.
RUN_TYPE_CONCENTRATION = "CONCENTRATION"


@dataclass(frozen=True)
class ConcentrationActor:
    """The principal initiating a concentration run (mirrors ``SharpeRatioActor``)."""

    actor_id: str
    actor_type: str = "user"
