"""System endpoints: health and version. No governed data; no entitlement scope."""

from __future__ import annotations

from fastapi import APIRouter

from irp_backend.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def version() -> dict[str, str]:
    return {"version": settings.app_version, "env": settings.app_env}
