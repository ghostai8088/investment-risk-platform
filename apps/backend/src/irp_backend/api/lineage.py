"""Lineage retrieval endpoint (REQ-LIN-001).

The only public lineage surface: retrieve a single edge by id for verification. Lineage is
**recorded by the in-process ``record_lineage()`` utility, never via a write API**; there is no
public ``data_source`` create endpoint. The lookup runs under the P1A-0 tenant session, so RLS
scopes it to the caller's tenant — a cross-tenant (or unknown) id yields an **indistinguishable
404** (no existence/oracle leak). Entitlement (``lineage.view``) is checked first (deny-by-default).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.lineage.models import LineageEdge

router = APIRouter(prefix="/lineage", tags=["lineage"])

#: Module-level guard singleton (deny-by-default; built once, not in the argument default).
_require_lineage_view = require_permission("lineage.view")


class LineageEdgeOut(BaseModel):
    id: str
    source_type: str
    source_id: str
    target_entity_type: str
    target_entity_id: str
    edge_kind: str
    run_id: str | None


@router.get("/edges/{edge_id}", response_model=LineageEdgeOut)
def get_lineage_edge(
    edge_id: uuid.UUID,  # malformed ids -> uniform 422 before any DB hit (no 500 / oracle)
    _: Principal = Depends(_require_lineage_view),
    db: Session = Depends(get_tenant_session),
) -> LineageEdgeOut:
    edge = db.execute(
        select(LineageEdge).where(LineageEdge.id == str(edge_id))
    ).scalar_one_or_none()
    if edge is None:
        # Not found AND cross-tenant (RLS-hidden) are intentionally indistinguishable.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lineage edge not found")
    return LineageEdgeOut(
        id=edge.id,
        source_type=edge.source_type,
        source_id=edge.source_id,
        target_entity_type=edge.target_entity_type,
        target_entity_id=edge.target_entity_id,
        edge_kind=edge.edge_kind,
        run_id=edge.run_id,
    )
