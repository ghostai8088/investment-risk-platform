"""FastAPI application entrypoint (scaffold).

Only system endpoints (health/version) exist. Domain endpoints are NOT permitted until
they bind to the entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks.
The system probes below carry no tenant-scoped or governed data and are exempt.
"""

from __future__ import annotations

from fastapi import FastAPI

from irp_backend.api.dq import router as dq_router
from irp_backend.api.ingest import router as ingest_router
from irp_backend.api.lineage import router as lineage_router
from irp_backend.api.models import router as models_router
from irp_backend.api.reference import router as reference_router
from irp_backend.api.reference_entities import router as reference_entities_router
from irp_backend.api.reference_instruments import router as reference_instruments_router
from irp_backend.api.system import router as system_router

app = FastAPI(title="Investment Risk Platform API (scaffold)")
app.include_router(system_router)
app.include_router(lineage_router)
app.include_router(models_router)
app.include_router(dq_router)
app.include_router(ingest_router)
app.include_router(reference_router)
app.include_router(reference_entities_router)
app.include_router(reference_instruments_router)
