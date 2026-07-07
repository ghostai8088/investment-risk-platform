"""Dataset-snapshot endpoints (P2-1, ENT-049/050 — the AD-014 reproducible input snapshot).

Thin layer over the ``irp_shared.snapshot`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), IA
TRUE append-only. ``POST /snapshots`` is gated ``snapshot.create`` (maker/admin); the reads gated
``snapshot.view``. ``tenant_id`` is server-stamped from the principal; the bound scope is resolved
tenant-filtered (cross-tenant/unknown -> indistinguishable 404); a single end-of-request
``db.commit()``. There is **no PUT/PATCH/DELETE** (append-only).

It produces **no derived number** (no ``quantity x mark``, no exposure) and wires **no**
``calculation_run`` (the snapshot id is just the referent for P2-3). ``GET /verify`` re-checks
each pinned component against the live value and reports drift; it emits no audit event (read-only).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, map_refusal, require_permission
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.portfolio import HierarchyCycleError, PortfolioNotVisible
from irp_shared.snapshot import (
    DatasetSnapshot,
    EmptySnapshotError,
    SnapshotActor,
    SnapshotNotFound,
    SnapshotPurposeError,
    build_snapshot,
    list_components,
    resolve_snapshot,
    verify_snapshot,
)

router = APIRouter(prefix="/snapshots", tags=["snapshots"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_create = require_permission("snapshot.create")
_require_view = require_permission("snapshot.view")

#: Fail-closed exception -> (HTTP status, opaque detail). Cross-tenant/unknown scope is an
#: indistinguishable 404; completeness/empty/cycle are 409; out-of-vocab purpose is 422.
_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    SnapshotPurposeError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid snapshot purpose"),
    PortfolioNotVisible: (status.HTTP_404_NOT_FOUND, "portfolio not found"),
    HierarchyCycleError: (status.HTTP_409_CONFLICT, "hierarchy cycle or depth exceeded"),
    EmptySnapshotError: (status.HTTP_409_CONFLICT, "bound scope yields no components"),
    DataQualityError: (
        status.HTTP_409_CONFLICT,
        "bound input set is incomplete (a position lacks a same-as-of mark)",
    ),
}


def _actor(principal: Principal) -> SnapshotActor:
    return SnapshotActor(actor_id=principal.user_id)


class SnapshotIn(BaseModel):
    portfolio_id: uuid.UUID  # the bound scope (subtree root); malformed -> 422
    as_of_valid_at: datetime  # the business as-of (valid-time cutoff)
    purpose: str = "EXPOSURE_INPUT"  # controlled-vocab; out-of-vocab -> 422
    label: str = ""
    as_of_known_at: datetime | None = None  # knowledge cutoff; default now (frozen on the header)
    as_of_valuation_date: date | None = None  # default date(as_of_valid_at)


class ComponentOut(BaseModel):
    id: str
    component_kind: str
    target_entity_type: str
    target_entity_id: str
    pinned_valid_from: datetime | None
    pinned_system_from: datetime | None
    pinned_record_version: int | None
    content_hash: str


class SnapshotHeaderOut(BaseModel):
    id: str
    tenant_id: str
    label: str
    purpose: str
    as_of_valid_at: datetime
    as_of_known_at: datetime
    as_of_valuation_date: date
    binding_predicate_version: str
    component_count: int
    manifest_hash: str
    system_from: datetime


class SnapshotOut(BaseModel):
    snapshot: SnapshotHeaderOut
    components: list[ComponentOut]


class VerifyOut(BaseModel):
    snapshot_id: str
    ok: bool
    component_count: int
    drifted_components: list[str]


def _header_out(row: DatasetSnapshot) -> SnapshotHeaderOut:
    return SnapshotHeaderOut(
        id=row.id,
        tenant_id=row.tenant_id,
        label=row.label,
        purpose=row.purpose,
        as_of_valid_at=row.as_of_valid_at,
        as_of_known_at=row.as_of_known_at,
        as_of_valuation_date=row.as_of_valuation_date,
        binding_predicate_version=row.binding_predicate_version,
        component_count=row.component_count,
        manifest_hash=row.manifest_hash,
        system_from=row.system_from,
    )


def _components_out(db: Session, *, snapshot_id: str, tenant_id: str) -> list[ComponentOut]:
    return [
        ComponentOut(
            id=c.id,
            component_kind=c.component_kind,
            target_entity_type=c.target_entity_type,
            target_entity_id=c.target_entity_id,
            pinned_valid_from=c.pinned_valid_from,
            pinned_system_from=c.pinned_system_from,
            pinned_record_version=c.pinned_record_version,
            content_hash=c.content_hash,
        )
        for c in list_components(db, snapshot_id=snapshot_id, acting_tenant=tenant_id)
    ]


@router.post("", response_model=SnapshotOut, status_code=status.HTTP_201_CREATED)
def create_snapshot(
    body: SnapshotIn,
    principal: Principal = Depends(_require_create),
    db: Session = Depends(get_tenant_session),
) -> SnapshotOut:
    """Build one immutable reproducible input snapshot over the bound portfolio subtree."""
    try:
        header = build_snapshot(
            db,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            purpose=body.purpose,
            portfolio_id=str(body.portfolio_id),
            as_of_valid_at=body.as_of_valid_at,
            label=body.label,
            as_of_known_at=body.as_of_known_at,
            as_of_valuation_date=body.as_of_valuation_date,
        )
    except (
        SnapshotPurposeError,
        PortfolioNotVisible,
        HierarchyCycleError,
        EmptySnapshotError,
        DataQualityError,
    ) as exc:
        # Whole-unit rollback (CTRL-032): discard any partially-flushed header/components/lineage/DQ
        # row before mapping to the HTTP error — the bound unit is all-or-nothing.
        db.rollback()
        code, detail = map_refusal(exc, _ERROR_MAP)
        raise HTTPException(status_code=code, detail=detail) from None

    # Build the response BEFORE commit, while the request's ``app.current_tenant`` GUC is live:
    # ``set_config(..., true)`` is transaction-local and clears at COMMIT, after which a fresh
    # tenant-scoped SELECT (``_components_out`` -> ``list_components``) would run context-less and,
    # under PG ENABLE+FORCE RLS, match zero rows — an empty ``components[]`` beside a non-zero
    # ``component_count`` (the header serializes fine off the in-memory row). The single end-of-
    # request commit then persists the already-serialized unit.
    response = SnapshotOut(
        snapshot=_header_out(header),
        components=_components_out(db, snapshot_id=header.id, tenant_id=principal.tenant_id),
    )
    db.commit()
    return response


@router.get("/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(
    snapshot_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> SnapshotOut:
    """Read a snapshot header + its pinned components (read-only)."""
    try:
        header = resolve_snapshot(db, str(snapshot_id), acting_tenant=principal.tenant_id)
    except SnapshotNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found"
        ) from None
    return SnapshotOut(
        snapshot=_header_out(header),
        components=_components_out(db, snapshot_id=header.id, tenant_id=principal.tenant_id),
    )


@router.get("/{snapshot_id}/verify", response_model=VerifyOut)
def verify_snapshot_endpoint(
    snapshot_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> VerifyOut:
    """Re-resolve every pinned component and report drift (read-only; emits no audit event)."""
    try:
        result = verify_snapshot(
            db, snapshot_id=str(snapshot_id), acting_tenant=principal.tenant_id
        )
    except SnapshotNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found"
        ) from None
    return VerifyOut(
        snapshot_id=str(snapshot_id),
        ok=result.ok,
        component_count=result.component_count,
        drifted_components=result.drifted_components,
    )
