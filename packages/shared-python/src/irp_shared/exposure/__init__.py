"""Exposure package (P2-3, ENT-014) — the first governed derived number (basic signed market value).

Leaf domain package: ``exposure -> {snapshot, marketdata(pure legs), calc, lineage, dq, portfolio,
audit, db}``. **"Nothing imports ``exposure``" was true at P2-3 and is NOT true now** (corrected in
SCH-2, OD-SCH-2-F): ``risk/factor_service.py``, ``snapshot/service.py``, ``scheduling/service.py``,
the top-level ``models.py`` aggregator and the ``demo`` package all import it. The inbound set is
pinned by ``test_scheduler.test_no_new_package_imports_risk_or_exposure``; the OUTBOUND fence below
is the one that still holds strictly. The compute reads ONLY snapshot-pinned captured content
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
    EXPOSURE_TYPE_NOTIONAL,
    EXPOSURE_TYPES,
    ExposureAggregate,
)
from irp_shared.exposure.queries import (
    LIST_LIMIT_DEFAULT,
    ExposureRunQueryError,
    list_exposure_runs,
)
from irp_shared.exposure.service import (
    ExposureInputError,
    ExposureNotVisible,
    ExposureRunNotVisible,
    ExposureRunResult,
    latest_exposure,
    list_exposure,
    list_exposure_by_entity,
    resolve_exposure,
    resolve_run,
    run_exposure,
)

__all__ = [
    "ExposureAggregate",
    "EXPOSURE_TYPE_MARKET_VALUE",
    "EXPOSURE_TYPE_NOTIONAL",
    "EXPOSURE_TYPES",
    "ExposureActor",
    "RUN_TYPE_EXPOSURE_AGGREGATE",
    "run_exposure",
    "latest_exposure",
    "list_exposure",
    "list_exposure_by_entity",
    "list_exposure_runs",
    "ExposureRunQueryError",
    "LIST_LIMIT_DEFAULT",
    "resolve_exposure",
    "resolve_run",
    "ExposureRunResult",
    "ExposureInputError",
    "ExposureNotVisible",
    "ExposureRunNotVisible",
]
