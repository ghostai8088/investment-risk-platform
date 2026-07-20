"""Pacing-family run vocabulary + actor (CC-2, ENT-059 — the pacing event surface).

The ``calculation_run.run_type`` FAMILY discriminator for a commitment-pacing projection run. The
run reuses ``CALC.RUN_CREATE``/``CALC.RUN_STATUS_CHANGE`` (the governed-run scaffold) — the
``PACING.PROJECTION_CREATE`` audit code is RESERVED at the EVT-250 decade (the next domain decade
after PRIVATE/EVT-240), never minted here (the PM-1/PERF-decade precedent).
"""

from __future__ import annotations

from dataclasses import dataclass

#: The ``calculation_run.run_type`` FAMILY discriminator for a pacing-projection run (CC-2). The
#: pacing_projection_result rows carry no ``metric_type`` in v1 (one row shape per period).
RUN_TYPE_PACING_PROJECTION = "PACING_PROJECTION"

#: RESERVED audit code (the PACING/EVT-250 decade) — NOT emitted in CC-2 (OD-CC-2-F: the run reuses
#: ``CALC.RUN_*``; ``PACING.PROJECTION_CREATE`` is reserved, never minted here).
PACING_PROJECTION_CREATE_EVENT_RESERVED = "PACING.PROJECTION_CREATE"


@dataclass(frozen=True)
class PacingActor:
    """The principal initiating a pacing-projection run (mirrors ``PortfolioReturnActor``)."""

    actor_id: str
    actor_type: str = "user"
