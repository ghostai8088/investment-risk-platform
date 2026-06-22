"""Generic ingestion endpoints (P1A-4, REQ-INT-001): one gated multipart upload + two reads.

`POST /ingest/upload` (gated `data.upload`) accepts a multipart CSV + `data_source_id`, enforces the
byte-size cap **while reading** (never trusting `Content-Length`), and delegates to the shared
`stage_upload` orchestrator (anti-corruption → stage → DQ → lineage → audit) in one tenant-scoped
transaction; `tenant_id` is server-stamped (never from the body). A rejected upload **commits**
its durable evidence (batch + flagged result + audit) and returns a 4xx (never a 200). Reads are
RLS-scoped to the caller's tenant; a cross-tenant/unknown id yields an **indistinguishable 404**.
There is NO canonical-mapping / reconciliation / override / adapter / dashboard surface.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
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
