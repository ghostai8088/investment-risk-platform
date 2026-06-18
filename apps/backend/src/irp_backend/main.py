"""FastAPI application entrypoint (scaffold).

Only system endpoints (health/version) exist. Domain endpoints are NOT permitted until
they bind to the entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks.
The system probes below carry no tenant-scoped or governed data and are exempt.
"""

from __future__ import annotations

from fastapi import FastAPI

from irp_backend.api.system import router as system_router

app = FastAPI(title="Investment Risk Platform API (scaffold)")
app.include_router(system_router)
