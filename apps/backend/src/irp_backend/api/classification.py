"""Classification endpoints (REF-1): governed writes + entity-filtered reads for ENT-066/067/068.

Thin layer over the ``irp_shared.classification`` binder. Rule 7's captured-input clause is what
this surface satisfies: a capture family ships **entity-filtered list reads from birth**, so a
governed number built on it later (CON-1) is never the first thing that can see the data.

**Two view permissions, not one, and the split is load-bearing.** The scheme/node VOCABULARY is
hybrid SYSTEM-global standard reference, so it rides ``reference.classification.view`` — the
currency/rating_scale precedent, which includes the 3L auditor. ASSIGNMENTS attach to proprietary
issuers/instruments, so they ride ``reference.classification_assignment.view`` — the legal_entity /
identifier precedent, which EXCLUDES the auditor. Gating both with a single code would have handed
the 3L auditor its first proprietary-identity read, and no shipped test would have caught it
because the SoD pins are per-code.

Conventions carried from the reference routers: ``tenant_id`` is server-set from the principal
(never the body); ``uuid.UUID`` path/query params give a uniform 422 before any DB hit; a
cross-tenant or unknown id is an indistinguishable 404; one end-of-request commit; list reads over
the hybrid vocabulary apply the application-layer ``dedupe_tenant_wins`` so a tenant node override
shadows the SYSTEM row (precedence lives HERE, never in RLS).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.classification.models import (
    ClassificationAssignment,
    ClassificationNode,
    ClassificationScheme,
)
from irp_shared.classification.service import (
    ClassificationActor,
    ClassificationNotVisible,
    ClassificationValueError,
    NoCurrentAssignment,
    capture_assignment,
    correct_assignment,
    resolve_ancestors,
    supersede_assignment,
)
from irp_shared.classification.service import list_assignments as service_list_assignments
from irp_shared.entitlement.service import Principal
from irp_shared.reference.service import dedupe_tenant_wins

router = APIRouter(prefix="/classification", tags=["classification"])

#: Module-level guard singletons (deny-by-default; built once, never in argument defaults — B008).
_require_vocab_view = require_permission("reference.classification.view")
_require_assignment_view = require_permission("reference.classification_assignment.view")
_require_edit = require_permission("reference.classification.edit")


def _actor(principal: Principal) -> ClassificationActor:
    return ClassificationActor(
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=str(uuid.uuid4()),
    )


class SchemeOut(BaseModel):
    id: str
    scheme_family: str
    version_label: str
    name: str
    authority: str | None
    dimension_kind: str
    is_active: bool


class NodeOut(BaseModel):
    id: str
    scheme_id: str
    code: str
    name: str
    level: int
    parent_node_id: str | None
    description: str | None


class AssignmentOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    scheme_id: str
    dimension_kind: str
    node_code: str
    basis: str
    valid_from: datetime
    valid_to: datetime | None
    record_version: int


class AssignmentIn(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    scheme_id: uuid.UUID
    dimension_kind: str
    node_code: str
    basis: str = "NOT_APPLICABLE"


class CorrectionIn(AssignmentIn):
    restatement_reason: str


def _scheme_out(s: ClassificationScheme) -> SchemeOut:
    return SchemeOut(
        id=str(s.id),
        scheme_family=s.scheme_family,
        version_label=s.version_label,
        name=s.name,
        authority=s.authority,
        dimension_kind=s.dimension_kind,
        is_active=s.is_active,
    )


def _node_out(n: ClassificationNode) -> NodeOut:
    return NodeOut(
        id=str(n.id),
        scheme_id=str(n.scheme_id),
        code=n.code,
        name=n.name,
        level=n.level,
        parent_node_id=str(n.parent_node_id) if n.parent_node_id else None,
        description=n.description,
    )


def _assignment_out(a: ClassificationAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=str(a.id),
        entity_type=a.entity_type,
        entity_id=str(a.entity_id),
        scheme_id=str(a.scheme_id),
        dimension_kind=a.dimension_kind,
        node_code=a.node_code,
        basis=a.basis,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        record_version=a.record_version,
    )


def _refusal(exc: Exception) -> HTTPException:
    """Binder refusals map to 422 (a governed refusal is not a server error)."""
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


# --------------------------------------------------------------------------- vocabulary (hybrid)


@router.get("/schemes", response_model=list[SchemeOut])
def list_schemes(
    dimension_kind: str | None = Query(default=None),
    principal: Principal = Depends(_require_vocab_view),
    db: Session = Depends(get_tenant_session),
) -> list[SchemeOut]:
    stmt = select(ClassificationScheme)
    if dimension_kind is not None:
        stmt = stmt.where(ClassificationScheme.dimension_kind == dimension_kind)
    rows = db.execute(stmt).scalars().all()
    # A tenant override shadows the SYSTEM scheme of the same (family, version) — schemes carry no
    # `code`, and a revision is a distinct row, so the key is the pair.
    deduped = dedupe_tenant_wins(
        rows, principal.tenant_id, key=lambda r: f"{r.scheme_family}\x00{r.version_label}"
    )
    return [_scheme_out(s) for s in deduped]


@router.get("/schemes/{scheme_id}", response_model=SchemeOut)
def get_scheme(
    scheme_id: uuid.UUID,
    _: Principal = Depends(_require_vocab_view),
    db: Session = Depends(get_tenant_session),
) -> SchemeOut:
    row = db.get(ClassificationScheme, str(scheme_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scheme not found")
    return _scheme_out(row)


@router.get("/schemes/{scheme_id}/nodes", response_model=list[NodeOut])
def list_nodes(
    scheme_id: uuid.UUID,
    level: int | None = Query(default=None),
    principal: Principal = Depends(_require_vocab_view),
    db: Session = Depends(get_tenant_session),
) -> list[NodeOut]:
    stmt = select(ClassificationNode).where(ClassificationNode.scheme_id == str(scheme_id))
    if level is not None:
        stmt = stmt.where(ClassificationNode.level == level)
    rows = db.execute(stmt).scalars().all()
    # Node-grain override: a tenant row wins over the SYSTEM row for the same code. The statement
    # is already scoped to ONE scheme, so `code` is unambiguous within this result set — across
    # schemes it would not be, which is why the key is explicit rather than defaulted.
    return [
        _node_out(n)
        for n in dedupe_tenant_wins(rows, principal.tenant_id, key=lambda r: str(r.code))
    ]


@router.get("/schemes/{scheme_id}/nodes/{code}/ancestors", response_model=list[NodeOut])
def get_ancestors(
    scheme_id: uuid.UUID,
    code: str,
    principal: Principal = Depends(_require_vocab_view),
    db: Session = Depends(get_tenant_session),
) -> list[NodeOut]:
    """Nearest parent first, up to the scheme root — the walk a per-sector bucket needs.

    Shipped in the slice that owns the vocabulary rather than deferred to its first consumer: a
    vendor delivers a LEAF code, so "sector" is an ancestor, and a hierarchy nobody can walk is not
    a hierarchy.
    """
    from irp_shared.classification.service import resolve_node

    try:
        node = resolve_node(
            db, scheme_id=str(scheme_id), code=code, acting_tenant=principal.tenant_id
        )
        chain = resolve_ancestors(db, node=node, acting_tenant=principal.tenant_id)
    except ClassificationNotVisible as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ClassificationValueError as exc:
        raise _refusal(exc) from exc
    return [_node_out(n) for n in chain]


# ------------------------------------------------------------------- assignments (proprietary)


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(
    entity_id: uuid.UUID | None = Query(default=None),
    scheme_id: uuid.UUID | None = Query(default=None),
    dimension_kind: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    principal: Principal = Depends(_require_assignment_view),
    db: Session = Depends(get_tenant_session),
) -> list[AssignmentOut]:
    """Entity- and time-filtered list (rule 7's captured-input clause).

    ``as_of`` selects the versions in force at that valid instant on the current system view;
    omitted, it returns the OPEN versions. Both filters are non-String column classes (uuid and
    timestamp), which is why their binds are pinned in the PG tier — SQLite's affinity makes the
    unit tier structurally blind to a mistyped bind.
    """
    if as_of is None:
        # The current-heads path rides the SERVICE verb (Wave-14 close fold: LQ-1 shipped
        # list_assignments to "pay REF-1's gap" and nothing in production ever called it — the
        # payment was unconsumed). Beyond de-duplication, the verb REFUSES an unknown
        # dimension_kind where this endpoint's hand-rolled filter silently returned [] on a typo:
        # "no such kind" read as "a clean book", the vacuous-read class.
        try:
            rows = service_list_assignments(
                db,
                acting_tenant=principal.tenant_id,
                entity_id=str(entity_id) if entity_id else None,
                scheme_id=str(scheme_id) if scheme_id else None,
                dimension_kind=dimension_kind,
            )
        except ClassificationValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        return [_assignment_out(a) for a in rows]

    # The as_of branch keeps its OWN query deliberately: this endpoint's ratified contract is
    # "versions in force at that VALID instant on the current system view" — a different axis
    # pairing from the service verb's known_at (system-axis reconstruction). Wiring one to the
    # other would silently change a shipped read's meaning.
    stmt = select(ClassificationAssignment).where(ClassificationAssignment.system_to.is_(None))
    if entity_id is not None:
        stmt = stmt.where(ClassificationAssignment.entity_id == str(entity_id))
    if scheme_id is not None:
        stmt = stmt.where(ClassificationAssignment.scheme_id == str(scheme_id))
    if dimension_kind is not None:
        stmt = stmt.where(ClassificationAssignment.dimension_kind == dimension_kind)
    stmt = stmt.where(
        ClassificationAssignment.valid_from <= as_of,
        (ClassificationAssignment.valid_to.is_(None)) | (ClassificationAssignment.valid_to > as_of),
    )
    # A distinct name, not a rebind: the current-heads branch above binds ``rows`` to the service
    # verb's ``list[...]``, and .scalars().all() is a ``Sequence[...]`` — narrower. mypy reads the
    # first binding as the declared type, so reusing the name is an error, and the honest fix is
    # two names rather than a widening annotation that pretends the branches share a type.
    as_of_rows = db.execute(stmt).scalars().all()
    return [_assignment_out(a) for a in as_of_rows]


@router.post("/assignments", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    body: AssignmentIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> AssignmentOut:
    try:
        row = capture_assignment(
            db,
            actor=_actor(principal),
            entity_type=body.entity_type,
            entity_id=str(body.entity_id),
            scheme_id=str(body.scheme_id),
            dimension_kind=body.dimension_kind,
            node_code=body.node_code,
            basis=body.basis,
        )
    except (ClassificationValueError, ClassificationNotVisible) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _assignment_out(row)


@router.put("/assignments", response_model=AssignmentOut)
def reclassify(
    body: AssignmentIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> AssignmentOut:
    """Reclassify (supersede on the VALID axis) — the prior version stays byte-stable."""
    try:
        row = supersede_assignment(
            db,
            actor=_actor(principal),
            entity_type=body.entity_type,
            entity_id=str(body.entity_id),
            scheme_id=str(body.scheme_id),
            dimension_kind=body.dimension_kind,
            node_code=body.node_code,
            basis=body.basis,
        )
    except NoCurrentAssignment as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ClassificationValueError, ClassificationNotVisible) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _assignment_out(row)


@router.post("/assignments/corrections", response_model=AssignmentOut)
def correct(
    body: CorrectionIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> AssignmentOut:
    """As-known restatement (TR-08) — closes the SYSTEM axis, reproduces the valid interval."""
    try:
        row = correct_assignment(
            db,
            actor=_actor(principal),
            entity_type=body.entity_type,
            entity_id=str(body.entity_id),
            scheme_id=str(body.scheme_id),
            dimension_kind=body.dimension_kind,
            node_code=body.node_code,
            basis=body.basis,
            restatement_reason=body.restatement_reason,
        )
    except NoCurrentAssignment as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ClassificationValueError, ClassificationNotVisible) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _assignment_out(row)
