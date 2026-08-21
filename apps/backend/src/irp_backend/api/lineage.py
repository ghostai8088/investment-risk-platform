"""Lineage retrieval endpoint (REQ-LIN-001).

Lineage is **recorded by the in-process ``record_lineage()`` utility, never via a write API**; there
is no public ``data_source`` create endpoint. Lookups run under the P1A-0 tenant session, so RLS
scopes them to the caller's tenant — a cross-tenant (or unknown) id yields an **indistinguishable
404** (no existence/oracle leak). Entitlement (``lineage.view``) is checked first (deny-by-default).

**W19-S3b adds the BY-TARGET read**, and the reason is worth stating because it applied for four
waves before anyone noticed. Until this slice the only lineage endpoint was ``GET
/lineage/edges/{edge_id}`` — an id a caller has **no way to obtain**. No endpoint returned an edge
id, nothing listed edges, and lineage ids appear in no other DTO. The surface existed and was
unreachable: an operator asking the ordinary question ("where did this position come from?") had
nowhere to start. ``/lineage`` has been in ``API_PREFIXES`` and the nginx alternation since it
shipped, and the SPA has never fetched it once.

The by-target read is the entry point that makes the by-id read usable: name an entity, get its
inbound edges, follow one. It is a READ of an append-only record and adds no verb.
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


#: The most edges one target may return. A cap rather than a page cursor: a target's inbound edge
#: count is bounded by how many times it was captured, which is small for every entity type this
#: read serves. The response reports whether it was hit, because a silently truncated lineage answer
#: is worse than no answer — it looks complete.
MAX_EDGES_PER_TARGET = 200


class LineageEdgesOut(BaseModel):
    """The inbound edges of one target, plus whether the cap cut the answer short."""

    target_entity_type: str
    target_entity_id: str
    edges: list[LineageEdgeOut]
    truncated: bool


@router.get("/targets/{target_entity_type}/{target_entity_id}", response_model=LineageEdgesOut)
def get_lineage_for_target(
    target_entity_type: str,
    target_entity_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit (no 500 / oracle)
    _: Principal = Depends(_require_lineage_view),
    db: Session = Depends(get_tenant_session),
) -> LineageEdgesOut:
    """Every lineage edge pointing AT one entity — the entry point the by-id read never had.

    **An empty list is a 200, not a 404**, and that is a deliberate difference from the by-id read.
    Asking "what is the lineage of this position?" about an entity with none is a legitimate
    question with the legitimate answer "nothing was recorded". A 404 would additionally claim the
    entity does not exist, which this endpoint has no way to know: it queries ``lineage_edge`` and
    never looks at the target's own table. Answering 404 here would also make the reply an existence
    oracle in the other direction — it would distinguish "no lineage" from "not your tenant", which
    are the same answer under RLS and must stay that way.

    ``target_entity_type`` is a free-text discriminator on an append-only table, not an enum, so it
    is passed through as a filter value and never interpolated.
    """
    rows = (
        db.execute(
            select(LineageEdge)
            .where(
                LineageEdge.target_entity_type == target_entity_type,
                LineageEdge.target_entity_id == str(target_entity_id),
            )
            .order_by(LineageEdge.system_from.desc(), LineageEdge.id)
            .limit(MAX_EDGES_PER_TARGET + 1)
        )
        .scalars()
        .all()
    )
    truncated = len(rows) > MAX_EDGES_PER_TARGET
    return LineageEdgesOut(
        target_entity_type=target_entity_type,
        target_entity_id=str(target_entity_id),
        edges=[_edge_out(edge) for edge in rows[:MAX_EDGES_PER_TARGET]],
        truncated=truncated,
    )


def _edge_out(edge: LineageEdge) -> LineageEdgeOut:
    return LineageEdgeOut(
        id=edge.id,
        source_type=edge.source_type,
        source_id=edge.source_id,
        target_entity_type=edge.target_entity_type,
        target_entity_id=edge.target_entity_id,
        edge_kind=edge.edge_kind,
        run_id=edge.run_id,
    )


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
    return _edge_out(edge)
