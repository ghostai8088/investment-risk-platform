"""Exposure package (P2-3, ENT-014) — the first governed derived number (basic signed market value).

Leaf domain package: ``exposure -> {snapshot, marketdata(pure legs), calc, lineage, dq, portfolio,
audit, db}``; nothing imports ``exposure``. The compute reads ONLY snapshot-pinned captured content
(never a live position/valuation/FX read) and imports no risk/factor/scenario symbol. **NOT risk** —
``MARKET_VALUE`` only, run-bound + snapshot-gated (AD-014 / FW-RUN / TR-15).
"""

from __future__ import annotations

from irp_shared.exposure.events import (
    RUN_TYPE_EXPOSURE_AGGREGATE,
    ExposureActor,
)
from irp_shared.exposure.models import (
    EXPOSURE_TYPE_MARKET_VALUE,
    EXPOSURE_TYPES,
    ExposureAggregate,
)
from irp_shared.exposure.service import (
    ExposureInputError,
    ExposureNotVisible,
    ExposureRunNotVisible,
    ExposureRunResult,
    list_exposure,
    resolve_exposure,
    resolve_run,
    run_exposure,
)

__all__ = [
    "ExposureAggregate",
    "EXPOSURE_TYPE_MARKET_VALUE",
    "EXPOSURE_TYPES",
    "ExposureActor",
    "RUN_TYPE_EXPOSURE_AGGREGATE",
    "run_exposure",
    "list_exposure",
    "resolve_exposure",
    "resolve_run",
    "ExposureRunResult",
    "ExposureInputError",
    "ExposureNotVisible",
    "ExposureRunNotVisible",
]
