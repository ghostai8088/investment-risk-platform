"""Sensitivity run actor + run-type + reserved audit constant (P3-1, ENT-028).

The sensitivity run's audit is the **calculation_run lifecycle** — it reuses the shipped
``CALC.RUN_CREATE`` + ``CALC.RUN_STATUS_CHANGE`` emitters (``calc/service.py``) + the
model-registry
``MODEL.REGISTER``/``MODEL.VERSION`` events, so P3-1 mints **NO** new audit emitter: the
``sensitivity_result`` rows are run-tracked + lineaged (metadata of the already-audited run) — the
``exposure_aggregate``/``ingestion_staged_record`` precedent. ``audit/service.py`` is FROZEN.

The ``RISK.SENSITIVITY_CREATE`` family (the RISK / EVT-220 decade — the next domain decade after
EXPOSURE/EVT-210) is **RESERVED — NOT emitted** (OD-P3-1-H): reserved only for a possible future
granular per-result audit if later documented. There is deliberately no events emitter here.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The ``calculation_run.run_type`` discriminator for a sensitivity run.
RUN_TYPE_SENSITIVITY = "SENSITIVITY"

#: RESERVED audit code (the RISK / EVT-220 decade) — NOT emitted in P3-1 (recorded for the
#: taxonomy).
RISK_SENSITIVITY_CREATE_EVENT_RESERVED = "RISK.SENSITIVITY_CREATE"

#: Controlled-vocab ``sensitivity_type`` (plain String, no enum/CHECK; app-side allow-list).
SENSITIVITY_TYPE_DV01 = "DV01"
SENSITIVITY_TYPE_SPREAD_DV01 = "SPREAD_DV01"
SENSITIVITY_TYPES = (SENSITIVITY_TYPE_DV01, SENSITIVITY_TYPE_SPREAD_DV01)


@dataclass(frozen=True)
class SensitivityActor:
    """The principal initiating a sensitivity run (mirrors ``ExposureActor``/``SnapshotActor``)."""

    actor_id: str
    actor_type: str = "user"
