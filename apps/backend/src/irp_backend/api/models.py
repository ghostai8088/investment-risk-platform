"""Model-registry endpoints (REQ-MDG-001): one gated write + two reads.

`POST /models` registers a model + its initial immutable version (+ optional assumptions/
limitations) — a legitimate, user-initiated governed write gated by `model.inventory.register`.
It **never** reads `tenant_id` from the body (server-stamped from the principal/context; a forged
value is ignored and backstopped by RLS `WITH CHECK`). Reads are RLS-scoped to the caller's tenant;
a cross-tenant (or unknown) id yields an **indistinguishable 404**. No validation/approval/tiering
workflow exists here — governance fields are recorded as metadata and gate nothing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.model.models import Model, ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.model.service import register_model, register_model_version

router = APIRouter(prefix="/models", tags=["models"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_register = require_permission("model.inventory.register")
_require_view = require_permission("model.inventory.view")


class RegisterModelIn(BaseModel):
    code: str
    name: str
    model_type: str
    description: str | None = None
    owner: str | None = None
    developer: str | None = None
    tier: str | None = None  # recorded as metadata; gates nothing (non-enforcing, P7)
    version_label: str
    methodology_ref: str | None = None
    code_version: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RegisterModelOut(BaseModel):
    id: str
    code: str
    version_id: str
    version_label: str


class ModelSummary(BaseModel):
    id: str
    code: str
    name: str
    model_type: str
    is_active: bool


class ModelVersionOut(BaseModel):
    id: str
    version_label: str
    methodology_ref: str | None
    code_version: str | None
    status: str | None
    assumptions: list[str]
    limitations: list[str]


class ModelDetailOut(BaseModel):
    id: str
    code: str
    name: str
    model_type: str
    is_active: bool
    tier: str | None
    validation_status: str | None
    versions: list[ModelVersionOut]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RegisterModelOut)
def create_model(
    body: RegisterModelIn,
    principal: Principal = Depends(_require_register),
    db: Session = Depends(get_tenant_session),
) -> RegisterModelOut:
    # One correlation id joins MODEL.REGISTER to its MODEL.VERSION for this registration (plan §6).
    cid = str(uuid.uuid4())
    model = register_model(
        db,
        tenant_id=principal.tenant_id,  # server-stamped; body tenant_id (if any) is ignored
        code=body.code,
        name=body.name,
        model_type=body.model_type,
        actor_id=principal.user_id,
        description=body.description,
        owner=body.owner,
        developer=body.developer,
        tier=body.tier,
        correlation_id=cid,
    )
    version = register_model_version(
        db,
        model=model,
        version_label=body.version_label,
        actor_id=principal.user_id,
        methodology_ref=body.methodology_ref,
        code_version=body.code_version,
        assumptions=body.assumptions,
        limitations=body.limitations,
        correlation_id=cid,
    )
    db.commit()  # end-of-request commit (no further work; honors the single-transaction invariant)
    return RegisterModelOut(
        id=model.id, code=model.code, version_id=version.id, version_label=version.version_label
    )


@router.get("", response_model=list[ModelSummary])
def list_models(
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ModelSummary]:
    rows = db.execute(select(Model).order_by(Model.code)).scalars().all()
    return [
        ModelSummary(
            id=m.id, code=m.code, name=m.name, model_type=m.model_type, is_active=m.is_active
        )
        for m in rows
    ]


@router.get("/{model_id}", response_model=ModelDetailOut)
def get_model(
    model_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit (no 500 / oracle)
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ModelDetailOut:
    model = db.get(Model, str(model_id))
    if model is None:
        # Not found AND cross-tenant (RLS-hidden) are intentionally indistinguishable.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found")

    versions = (
        db.execute(
            select(ModelVersion)
            .where(ModelVersion.model_id == model.id)
            .order_by(ModelVersion.version_label)
        )
        .scalars()
        .all()
    )
    out_versions: list[ModelVersionOut] = []
    for v in versions:
        assumptions = (
            db.execute(
                select(ModelAssumption.assumption_text).where(
                    ModelAssumption.model_version_id == v.id
                )
            )
            .scalars()
            .all()
        )
        limitations = (
            db.execute(
                select(ModelLimitation.limitation_text).where(
                    ModelLimitation.model_version_id == v.id
                )
            )
            .scalars()
            .all()
        )
        out_versions.append(
            ModelVersionOut(
                id=v.id,
                version_label=v.version_label,
                methodology_ref=v.methodology_ref,
                code_version=v.code_version,
                status=v.status,
                assumptions=list(assumptions),
                limitations=list(limitations),
            )
        )

    return ModelDetailOut(
        id=model.id,
        code=model.code,
        name=model.name,
        model_type=model.model_type,
        is_active=model.is_active,
        tier=model.tier,
        validation_status=model.validation_status,
        versions=out_versions,
    )
