"""Generic ingestion endpoints (P1A-4, REQ-INT-001): one gated multipart upload + two reads.

`POST /ingest/upload` (gated `data.upload`) accepts a multipart CSV + `data_source_id`, enforces the
byte-size cap **while reading** (never trusting `Content-Length`), and delegates to the shared
`stage_upload` orchestrator (anti-corruption → stage → DQ → lineage → audit) in one tenant-scoped
transaction; `tenant_id` is server-stamped (never from the body). A rejected upload **commits**
its durable evidence (batch + flagged result + audit) and returns a 4xx (never a 200). Reads are
RLS-scoped to the caller's tenant; a cross-tenant/unknown id yields an **indistinguishable 404**.
**W19-S3a adds the MAPPING READS** — `GET /ingest/mappings` and `GET /ingest/mappings/{id}` —
Rule 7's entity/time read surface for ENT-077. They are READS ONLY, and that is a ratified
decision (DS3a-1), not an omission: S3a mints no permission code, and gating a governed
RATIFICATION act behind `data.upload` would put a maker verb and a checker verb behind one code
for a slice — exactly the co-granting S3b's R-07 mint exists to prevent. The propose/ratify HTTP
verbs land at S3b with their own codes; until then those acts run at the service tier, exercised
by the demo walk and by tests.

There is still NO reconciliation / override / adapter surface, and no staged-ROW read: the staged
payload echoes raw client data (DC-2, possibly higher), and widening its audience is a deliberate
decision nobody has taken.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.ingest_mapping.models import IngestionMappingVersion
from irp_shared.ingestion.anticorruption import MAX_UPLOAD_BYTES
from irp_shared.ingestion.models import IngestionBatch
from irp_shared.ingestion.service import IngestionRejected, stage_upload
from irp_shared.lineage.service import DataSourceNotVisible

router = APIRouter(prefix="/ingest", tags=["ingestion"])

#: Module-level guard singleton (deny-by-default; built once, not in argument defaults).
_require_upload = require_permission("data.upload")

_READ_CHUNK = 64 * 1024


class BatchOut(BaseModel):
    id: str
    status: str
    scan_status: str
    filename: str
    content_type: str | None
    byte_size: int
    data_source_id: str
    row_count: int | None
    staged_count: int | None
    failed_count: int | None
    # W19-S3a: which ratified mapping interpreted this batch, and the instant its code-lookups
    # resolved against. NULL on a generic upload and on every batch staged before the spine.
    mapping_version_id: str | None
    lookup_as_of: str | None


def _batch_out(batch: IngestionBatch) -> BatchOut:
    return BatchOut(
        id=batch.id,
        status=batch.status,
        scan_status=batch.scan_status,
        filename=batch.filename,
        content_type=batch.content_type,
        byte_size=batch.byte_size,
        data_source_id=batch.data_source_id,
        row_count=batch.row_count,
        staged_count=batch.staged_count,
        failed_count=batch.failed_count,
        mapping_version_id=batch.mapping_version_id,
        lookup_as_of=batch.lookup_as_of.isoformat() if batch.lookup_as_of else None,
    )


class MappingVersionOut(BaseModel):
    """One ENT-077 version. Carries the operations VERBATIM — a mapping is meant to be readable by
    a non-engineer, and "what did this mapping do?" is the question the closed vocabulary exists to
    keep answerable."""

    id: str
    data_source_id: str
    source_type: str
    version_label: str
    status: str
    operations: list[dict[str, Any]]
    operations_hash: str
    authorship: str
    proposer_model_version_id: str | None
    proposal_prompt_hash: str | None
    proposal_prompt_ref: str | None
    proposal_response_ref: str | None
    proposed_by_actor_id: str
    proposed_at: str
    ratified_by_actor_id: str | None
    ratified_at: str | None
    superseded_at: str | None
    supersedes_id: str | None


def _mapping_out(row: IngestionMappingVersion) -> MappingVersionOut:
    return MappingVersionOut(
        id=row.id,
        data_source_id=row.data_source_id,
        source_type=row.source_type,
        version_label=row.version_label,
        status=row.status,
        operations=list(row.operations),
        operations_hash=row.operations_hash,
        authorship=row.authorship,
        proposer_model_version_id=row.proposer_model_version_id,
        proposal_prompt_hash=row.proposal_prompt_hash,
        proposal_prompt_ref=row.proposal_prompt_ref,
        proposal_response_ref=row.proposal_response_ref,
        proposed_by_actor_id=row.proposed_by_actor_id,
        proposed_at=row.proposed_at.isoformat(),
        ratified_by_actor_id=row.ratified_by_actor_id,
        ratified_at=row.ratified_at.isoformat() if row.ratified_at else None,
        superseded_at=row.superseded_at.isoformat() if row.superseded_at else None,
        supersedes_id=row.supersedes_id,
    )


@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=BatchOut)
def upload(
    data_source_id: str = Form(...),
    file: UploadFile = File(...),
    principal: Principal = Depends(_require_upload),
    db: Session = Depends(get_tenant_session),
) -> BatchOut:
    # Malformed data_source_id -> 422 (mirrors uuid path params; avoids a DB cast error/oracle).
    try:
        uuid.UUID(data_source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid data_source_id"
        ) from exc

    # Read the upload in bounded chunks, counting bytes WHILE reading (do NOT trust Content-Length).
    raw = bytearray()
    while chunk := file.file.read(_READ_CHUNK):
        raw += chunk
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large"
            )

    try:
        batch = stage_upload(
            db,
            tenant_id=principal.tenant_id,  # server-stamped; any body tenant is ignored
            data_source_id=data_source_id,
            filename=file.filename,
            content_type=file.content_type,
            raw_bytes=bytes(raw),
            actor_id=principal.user_id,
        )
    except IngestionRejected:
        db.commit()  # durable evidence: the REJECTED batch + flagged result + audit must survive
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ingestion rejected"
        ) from None
    except DataSourceNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="data_source not found"
        ) from None

    db.commit()  # end-of-request commit (single-transaction invariant)
    return _batch_out(batch)


@router.get("/batches", response_model=list[BatchOut])
def list_batches(
    _: Principal = Depends(_require_upload),
    db: Session = Depends(get_tenant_session),
) -> list[BatchOut]:
    rows = (
        db.execute(select(IngestionBatch).order_by(IngestionBatch.system_from.desc()))
        .scalars()
        .all()
    )
    return [_batch_out(b) for b in rows]


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(
    batch_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit (no 500 / oracle)
    _: Principal = Depends(_require_upload),
    db: Session = Depends(get_tenant_session),
) -> BatchOut:
    batch = db.get(IngestionBatch, str(batch_id))
    if batch is None:  # not found OR RLS-hidden cross-tenant id -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    return _batch_out(batch)


@router.get("/mappings", response_model=list[MappingVersionOut])
def list_mapping_versions(
    _: Principal = Depends(_require_upload),
    db: Session = Depends(get_tenant_session),
) -> list[MappingVersionOut]:
    """Every mapping version visible to the caller's tenant, newest first.

    Deliberately NOT filtered to RATIFIED. A screen that showed only the ratified version would
    hide the proposal awaiting a human — which is the one thing an operator opens this page to
    find.
    """
    rows = (
        db.execute(
            select(IngestionMappingVersion).order_by(IngestionMappingVersion.proposed_at.desc())
        )
        .scalars()
        .all()
    )
    return [_mapping_out(r) for r in rows]


@router.get("/mappings/{mapping_version_id}", response_model=MappingVersionOut)
def get_mapping_version(
    mapping_version_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit (no 500 / oracle)
    _: Principal = Depends(_require_upload),
    db: Session = Depends(get_tenant_session),
) -> MappingVersionOut:
    row = db.get(IngestionMappingVersion, str(mapping_version_id))
    if row is None:  # not found OR RLS-hidden cross-tenant id -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mapping not found")
    return _mapping_out(row)


@router.get("/mappings/{mapping_version_id}/batches", response_model=list[BatchOut])
def list_batches_for_mapping(
    mapping_version_id: uuid.UUID,
    _: Principal = Depends(_require_upload),
    db: Session = Depends(get_tenant_session),
) -> list[BatchOut]:
    """The batches this version loaded — the provenance question read the other way round.

    404s on an unknown/hidden mapping rather than returning an empty list, so "no batches" and
    "not your mapping" stay distinguishable to the caller who is entitled to know.
    """
    if db.get(IngestionMappingVersion, str(mapping_version_id)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mapping not found")
    rows = (
        db.execute(
            select(IngestionBatch)
            .where(IngestionBatch.mapping_version_id == str(mapping_version_id))
            .order_by(IngestionBatch.system_from.desc())
        )
        .scalars()
        .all()
    )
    return [_batch_out(b) for b in rows]
