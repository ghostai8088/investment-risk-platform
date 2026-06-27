"""Exposure run actor + run-type constant (P2-3).

The exposure run's audit is the **calculation_run lifecycle** — it reuses the shipped
``CALC.RUN_CREATE`` + ``CALC.RUN_STATUS_CHANGE`` emitters (``calc/service.py``), so P2-3 mints
**NO** new audit code: the ``exposure_aggregate`` rows are run-tracked + lineaged (metadata of the
already-audited run), the ``ingestion_staged_record``/result precedent. ``audit/service.py`` is
FROZEN.

The ``EXPOSURE.AGGREGATE_CREATE`` family (EVT-210) is **RESERVED — NOT minted** (OD-P2-3-H /
OQ-P2-3-5): reserved only for a possible future granular per-result audit if later documented. There
is deliberately no events emitter here.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The ``calculation_run.run_type`` discriminator for an exposure-aggregation run.
RUN_TYPE_EXPOSURE_AGGREGATE = "EXPOSURE_AGGREGATE"

#: RESERVED audit code (EVT-210) — NOT emitted in P2-3 (recorded for the taxonomy only).
EXPOSURE_AGGREGATE_CREATE_EVENT_RESERVED = "EXPOSURE.AGGREGATE_CREATE"


@dataclass(frozen=True)
class ExposureActor:
    """The principal initiating an exposure run (mirrors ``SnapshotActor``/``FxRateActor``)."""

    actor_id: str
    actor_type: str = "user"
