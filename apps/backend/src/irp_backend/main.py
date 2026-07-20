"""FastAPI application entrypoint (scaffold).

Only system endpoints (health/version) exist. Domain endpoints are NOT permitted until
they bind to the entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks.
The system probes below carry no tenant-scoped or governed data and are exempt.
"""

from __future__ import annotations

from fastapi import FastAPI

from irp_backend.api.dq import router as dq_router
from irp_backend.api.exposure import router as exposure_router
from irp_backend.api.holdings import router as holdings_router
from irp_backend.api.ingest import router as ingest_router
from irp_backend.api.lineage import router as lineage_router
from irp_backend.api.marketdata import benchmark_router as marketdata_benchmark_router
from irp_backend.api.marketdata import curve_router as marketdata_curve_router
from irp_backend.api.marketdata import factor_router as marketdata_factor_router
from irp_backend.api.marketdata import price_router as marketdata_price_router
from irp_backend.api.marketdata import proxy_mapping_router as marketdata_proxy_mapping_router
from irp_backend.api.marketdata import router as marketdata_router
from irp_backend.api.models import router as models_router
from irp_backend.api.perf import router as perf_router
from irp_backend.api.portfolios import router as portfolios_router
from irp_backend.api.positions import router as positions_router
from irp_backend.api.private_capital import router as private_capital_router
from irp_backend.api.reference import router as reference_router
from irp_backend.api.reference_corporate_actions import (
    router as reference_corporate_actions_router,
)
from irp_backend.api.reference_entities import router as reference_entities_router
from irp_backend.api.reference_instruments import router as reference_instruments_router
from irp_backend.api.risk import router as risk_router
from irp_backend.api.snapshots import router as snapshots_router
from irp_backend.api.system import router as system_router
from irp_backend.api.transactions import router as transactions_router
from irp_backend.api.valuations import router as valuations_router

app = FastAPI(title="Investment Risk Platform API (scaffold)")
app.include_router(system_router)
app.include_router(lineage_router)
app.include_router(models_router)
app.include_router(dq_router)
app.include_router(ingest_router)
app.include_router(reference_router)
app.include_router(reference_entities_router)
app.include_router(reference_instruments_router)
app.include_router(reference_corporate_actions_router)
app.include_router(portfolios_router)
app.include_router(transactions_router)
app.include_router(positions_router)
app.include_router(valuations_router)
app.include_router(private_capital_router)
app.include_router(holdings_router)
app.include_router(snapshots_router)
app.include_router(marketdata_router)
app.include_router(marketdata_price_router)
app.include_router(marketdata_curve_router)
app.include_router(marketdata_benchmark_router)
app.include_router(marketdata_factor_router)
app.include_router(marketdata_proxy_mapping_router)
app.include_router(exposure_router)
app.include_router(risk_router)
app.include_router(perf_router)
