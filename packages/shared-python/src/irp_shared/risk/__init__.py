"""Risk package (P3-1, ENT-028) — the first reproducible governed risk number (analytic
sensitivities: curve-node DV01 / spread-DV01).

Leaf domain package: ``risk -> {snapshot, marketdata(constants/kernel), calc, model, lineage, dq,
audit, db}``; nothing imports ``risk``. The compute reads ONLY snapshot-pinned captured curve
content (never a live curve read) and imports no factor/covariance/VaR/scenario/stress symbol.
Run-bound + snapshot-gated + **model_version-bound** (AD-014 / FW-RUN / TR-15 / CTRL-003) — no
sensitivity number escapes the model inventory. Curve-intrinsic v1 — NO instrument/position
attribution, NO interpolation, NO pricing engine.
"""

from __future__ import annotations

from irp_shared.risk.bootstrap import (
    SENSITIVITY_METHODOLOGY_REF,
    SENSITIVITY_MODEL_CODE,
    register_sensitivity_model,
)
from irp_shared.risk.events import (
    RISK_SENSITIVITY_CREATE_EVENT_RESERVED,
    RUN_TYPE_SENSITIVITY,
    SENSITIVITY_TYPE_DV01,
    SENSITIVITY_TYPE_SPREAD_DV01,
    SENSITIVITY_TYPES,
    SensitivityActor,
)
from irp_shared.risk.kernel import SensitivityKernelError, node_dv01, node_spread_dv01
from irp_shared.risk.models import SensitivityResult
from irp_shared.risk.service import (
    SensitivityInputError,
    SensitivityNotVisible,
    SensitivityRunNotVisible,
    SensitivityRunResult,
    list_sensitivities,
    resolve_run,
    resolve_sensitivity,
    run_sensitivities,
)

__all__ = [
    "SensitivityResult",
    "SensitivityActor",
    "RUN_TYPE_SENSITIVITY",
    "RISK_SENSITIVITY_CREATE_EVENT_RESERVED",
    "SENSITIVITY_TYPE_DV01",
    "SENSITIVITY_TYPE_SPREAD_DV01",
    "SENSITIVITY_TYPES",
    "node_dv01",
    "node_spread_dv01",
    "SensitivityKernelError",
    "run_sensitivities",
    "list_sensitivities",
    "resolve_run",
    "resolve_sensitivity",
    "SensitivityRunResult",
    "SensitivityInputError",
    "SensitivityNotVisible",
    "SensitivityRunNotVisible",
    "register_sensitivity_model",
    "SENSITIVITY_MODEL_CODE",
    "SENSITIVITY_METHODOLOGY_REF",
]
