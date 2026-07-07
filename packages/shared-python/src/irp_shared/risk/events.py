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

#: Controlled-vocab ``sensitivity_type`` (plain String, no enum/CHECK; app-side allow-list).
SENSITIVITY_TYPE_DV01 = "DV01"
SENSITIVITY_TYPE_SPREAD_DV01 = "SPREAD_DV01"
SENSITIVITY_TYPES = (SENSITIVITY_TYPE_DV01, SENSITIVITY_TYPE_SPREAD_DV01)


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
