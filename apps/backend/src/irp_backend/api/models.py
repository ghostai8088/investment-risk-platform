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
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.model.models import Model, ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.model.service import (
    ModelNotVisible,
    ModelTierValueError,
    assign_model_tier,
    register_model,
    register_model_version,
)
from irp_shared.model.validation import (
    ModelValidationActor,
    ModelValidationValueError,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    latest_validation,
    list_evidence,
    list_findings,
    list_validations,
    record_validation,
    resolve_validation,
)

router = APIRouter(prefix="/models", tags=["models"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_register = require_permission("model.inventory.register")
_require_view = require_permission("model.inventory.view")
#: VW-1: the 2L independent-validation write (SOD-03 — deliberately NOT the register permission).
_require_validate = require_permission("model.validate")


class RegisterModelIn(BaseModel):
    code: str
    name: str
    model_type: str
    description: str | None = None
    owner: str | None = None
    developer: str | None = None
    # MG-1 (OD-MG-1-B): `tier` was REMOVED from this body — the 1L author must not set the
    # materiality that scales scrutiny of his own model. A stray `tier` key in a request is
    # IGNORED-AND-NOT-STAMPED (the ratified shape, test-pinned); all tier writes flow through the
    # 2L POST /models/{id}/tier verb.
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
    tier: str | None  # the governed model tier (MG-1) — surfaced on the inventory list (API-1 F2)
    validation_status: str | None  # the operative validation posture (placeholder until VW-1 fills)


class LatestValidationOut(BaseModel):
    """The operative (most recent) validation record for a version, surfaced on the detail read."""

    outcome: str
    validation_type: str
    validated_at: str  # the record's system_from (ISO), the "validated on" timestamp
    next_review_due: date | None
    overdue: bool  # next_review_due < today (computed at read; False when no due date)


class ModelVersionOut(BaseModel):
    id: str
    version_label: str
    methodology_ref: str | None
    code_version: str | None
    status: str | None
    assumptions: list[str]
    limitations: list[str]
    latest_validation: LatestValidationOut | None = None


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
            id=m.id,
            code=m.code,
            name=m.name,
            model_type=m.model_type,
            is_active=m.is_active,
            tier=m.tier,
            validation_status=m.validation_status,
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
        latest = latest_validation(db, v.id, acting_tenant=model.tenant_id)
        latest_out = (
            LatestValidationOut(
                outcome=latest.outcome,
                validation_type=latest.validation_type,
                validated_at=latest.system_from.isoformat(),
                next_review_due=latest.next_review_due,
                overdue=(
                    latest.next_review_due is not None
                    # UTC to match the platform's utcnow() convention (finder fold) — avoids a
                    # near-midnight local-vs-UTC boundary flip on a non-UTC server.
                    and latest.next_review_due < datetime.now(UTC).date()
                ),
            )
            if latest is not None
            else None
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
                latest_validation=latest_out,
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


# --- VW-1: model-validation workflow (ENT-037) — one gated write + one read ---


class ValidationFindingIn(BaseModel):
    finding_text: str
    severity: str | None = None
    authored_by: str | None = None


class ValidationEvidenceIn(BaseModel):
    evidence_type: str
    run_id: str | None = None
    reference: str | None = None


class RecordValidationIn(BaseModel):
    validation_type: str
    outcome: str
    scope_summary: str
    conditions: str | None = None
    report_ref: str | None = None
    next_review_due: date | None = None
    findings: list[ValidationFindingIn] = Field(default_factory=list)
    evidence: list[ValidationEvidenceIn] = Field(default_factory=list)


class RecordValidationOut(BaseModel):
    id: str
    model_version_id: str
    outcome: str
    validation_type: str
    validated_at: str


class ValidationSummaryOut(BaseModel):
    id: str
    outcome: str
    validation_type: str
    scope_summary: str
    conditions: str | None
    report_ref: str | None
    next_review_due: date | None
    validated_by: str
    validated_at: str


class ValidationFindingOut(BaseModel):
    id: str
    finding_text: str
    severity: str | None
    authored_by: str | None


class ValidationEvidenceOut(BaseModel):
    id: str
    evidence_type: str
    run_id: str | None
    reference: str | None


class ValidationDetailOut(ValidationSummaryOut):
    """The per-validation detail (API-1 F2): the lean summary fields PLUS the heavy sub-objects
    (``findings`` + ``evidence``) that the summary list deliberately omits."""

    findings: list[ValidationFindingOut]
    evidence: list[ValidationEvidenceOut]


def _resolve_visible_version(
    db: Session, model_id: uuid.UUID, version_id: uuid.UUID
) -> ModelVersion:
    """Resolve a version under the caller's tenant, 404-indistinguishable if the model OR the
    version is hidden/unknown or the version does not belong to the model."""
    model = db.get(Model, str(model_id))
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found")
    version = db.get(ModelVersion, str(version_id))
    if version is None or version.model_id != model.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model_version not found")
    return version


class AssignTierIn(BaseModel):
    # The DUAL ratings (OD-MG-1-A): materiality per SR 26-2 (exposure + purpose), complexity per
    # SS1/23 P1.3(c). The tier is DERIVED server-side by the ratified house matrix — a caller
    # cannot post a tier directly.
    materiality_rating: str
    complexity_rating: str
    rationale: str


class AssignTierOut(BaseModel):
    id: str
    code: str
    tier: str
    materiality_rating: str
    complexity_rating: str


@router.post("/{model_id}/tier", response_model=AssignTierOut)
def assign_tier(
    model_id: uuid.UUID,
    body: AssignTierIn,
    principal: Principal = Depends(_require_validate),
    db: Session = Depends(get_tenant_session),
) -> AssignTierOut:
    """Assign/re-assign the model's tier from the dual ratings (MG-1, OD-MG-1-B/C). A 2L act —
    gated on `model.validate` (HOUSE POLICY per OD-MG-1-C; the 1L register-time write is closed).
    Emits MODEL.TIER_ASSIGN with the ratings + rationale in the payload (their durable home)."""
    try:
        model = assign_model_tier(
            db,
            acting_tenant=principal.tenant_id,
            model_id=str(model_id),
            materiality_rating=body.materiality_rating,
            complexity_rating=body.complexity_rating,
            rationale=body.rationale,
            actor_id=principal.user_id,
        )
    except ModelTierValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ModelNotVisible as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="model not found"
        ) from exc
    db.commit()
    return AssignTierOut(
        id=model.id,
        code=model.code,
        tier=model.tier or "",
        materiality_rating=body.materiality_rating,
        complexity_rating=body.complexity_rating,
    )


@router.post(
    "/{model_id}/versions/{version_id}/validations",
    status_code=status.HTTP_201_CREATED,
    response_model=RecordValidationOut,
)
def create_validation(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    body: RecordValidationIn,
    principal: Principal = Depends(_require_validate),
    db: Session = Depends(get_tenant_session),
) -> RecordValidationOut:
    version = _resolve_visible_version(db, model_id, version_id)
    request = RecordValidationRequest(
        model_version_id=version.id,
        validation_type=body.validation_type,
        outcome=body.outcome,
        scope_summary=body.scope_summary,
        conditions=body.conditions,
        report_ref=body.report_ref,
        next_review_due=body.next_review_due,
        findings=tuple(
            ValidationFindingInput(
                finding_text=f.finding_text, severity=f.severity, authored_by=f.authored_by
            )
            for f in body.findings
        ),
        evidence=tuple(
            ValidationEvidenceInput(
                evidence_type=e.evidence_type, run_id=e.run_id, reference=e.reference
            )
            for e in body.evidence
        ),
    )
    try:
        record = record_validation(
            db,
            acting_tenant=principal.tenant_id,
            actor=ModelValidationActor(actor_id=principal.user_id),
            request=request,
        )
    except ModelValidationValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    return RecordValidationOut(
        id=record.id,
        model_version_id=record.model_version_id,
        outcome=record.outcome,
        validation_type=record.validation_type,
        validated_at=record.system_from.isoformat(),
    )


@router.get(
    "/{model_id}/versions/{version_id}/validations",
    response_model=list[ValidationSummaryOut],
)
def list_version_validations(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ValidationSummaryOut]:
    version = _resolve_visible_version(db, model_id, version_id)
    rows = list_validations(db, version.id, acting_tenant=principal.tenant_id)
    return [
        ValidationSummaryOut(
            id=r.id,
            outcome=r.outcome,
            validation_type=r.validation_type,
            scope_summary=r.scope_summary,
            conditions=r.conditions,
            report_ref=r.report_ref,
            next_review_due=r.next_review_due,
            validated_by=r.validated_by,
            validated_at=r.system_from.isoformat(),
        )
        for r in rows
    ]


@router.get(
    "/{model_id}/validations/{validation_id}",
    response_model=ValidationDetailOut,
)
def get_validation_detail(
    model_id: uuid.UUID,
    validation_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ValidationDetailOut:
    """The per-validation detail read (API-1 F2): the summary fields + its findings + evidence.
    404-indistinguishable if the validation is hidden/unknown OR does not belong to a version of
    the URL's model (no cross-model / existence-oracle leak)."""
    record = resolve_validation(db, str(validation_id), acting_tenant=principal.tenant_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="validation not found")
    version = db.get(ModelVersion, record.model_version_id)
    if version is None or version.model_id != str(model_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="validation not found")
    findings = list_findings(db, record.id, acting_tenant=principal.tenant_id)
    evidence = list_evidence(db, record.id, acting_tenant=principal.tenant_id)
    return ValidationDetailOut(
        id=record.id,
        outcome=record.outcome,
        validation_type=record.validation_type,
        scope_summary=record.scope_summary,
        conditions=record.conditions,
        report_ref=record.report_ref,
        next_review_due=record.next_review_due,
        validated_by=record.validated_by,
        validated_at=record.system_from.isoformat(),
        findings=[
            ValidationFindingOut(
                id=f.id,
                finding_text=f.finding_text,
                severity=f.severity,
                authored_by=f.authored_by,
            )
            for f in findings
        ],
        evidence=[
            ValidationEvidenceOut(
                id=e.id,
                evidence_type=e.evidence_type,
                run_id=e.run_id,
                reference=e.reference,
            )
            for e in evidence
        ],
    )
