"""Legal-entity core binder + tenant-filtered resolution helpers (P1B-2, ENT-002/003 shared core).

``legal_entity`` is the implementation-only shared identity core (OD-P1B-D). This module owns the
**tenant-filtered** resolvers reused by the ``issuer``/``counterparty`` binders:

- ``resolve_legal_entity`` resolves a core by id with an **EXPLICIT ``tenant_id == acting_tenant``
  predicate** (the ``ensure_manual_source`` / ``assert_registered_model_version`` pattern, NOT the
  id-only ``register_model_version`` lookup) — so a cross-tenant/unknown id raises
  ``LegalEntityNotVisible`` and fails closed on **SQLite AND PostgreSQL** (RLS WITH CHECK is the PG
  backstop). This is what keeps proprietary cores from being attached/parented cross-tenant.
- ``resolve_ultimate_parent`` walks the ``parent_legal_entity_id`` adjacency to the root with a
  visited-set (guarantees termination) + a depth cap (defense-in-depth). Each hop carries the same
  explicit tenant predicate, so the walk **terminates at the tenant boundary** and visits no
  other-tenant node. It is a **pure structural traversal — NO exposure/credit math.**
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.reference.models import LegalEntity
from irp_shared.reference.service import (
    ENTITY_LEGAL_ENTITY,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Defense-in-depth bound for the ultimate-parent walk (the visited-set already guarantees
#: termination; exceeding the cap raises ``HierarchyCycleError`` regardless of a true cycle).
MAX_HIERARCHY_DEPTH = 32

#: Mutable attributes ``update_legal_entity`` will diff/apply (``code`` is the stable identity key).
_UPDATABLE = ("name", "lei", "jurisdiction", "entity_type", "parent_legal_entity_id", "is_active")


class LegalEntityNotVisible(Exception):
    """Raised when a ``legal_entity_id`` (a profile core, or a parent) is not visible in the acting
    tenant scope (cross-tenant id hidden, or unknown) — the dependent write fails closed."""

    def __init__(self, legal_entity_id: str) -> None:
        super().__init__(
            f"legal_entity {legal_entity_id} is not visible in the current tenant context"
        )
        self.legal_entity_id = str(legal_entity_id)


class HierarchyCycleError(Exception):
    """Raised when the ``parent_legal_entity_id`` walk cycles or exceeds ``MAX_HIERARCHY_DEPTH``."""

    def __init__(self, legal_entity_id: str) -> None:
        super().__init__(
            f"legal_entity hierarchy from {legal_entity_id} cycles or exceeds the depth cap"
        )
        self.legal_entity_id = str(legal_entity_id)


def resolve_legal_entity(
    session: Session, legal_entity_id: str, *, acting_tenant: str
) -> LegalEntity:
    """Resolve a ``legal_entity`` by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed on SQLite AND PG). Raises :class:`LegalEntityNotVisible` on a hidden/unknown id."""
    core = session.execute(
        select(LegalEntity).where(
            LegalEntity.id == str(legal_entity_id),
            LegalEntity.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if core is None:
        raise LegalEntityNotVisible(str(legal_entity_id))
    return core


def resolve_ultimate_parent(
    session: Session, legal_entity: LegalEntity, *, acting_tenant: str
) -> str:
    """Return the ultimate-parent id by walking ``parent_legal_entity_id`` to a root within the
    acting tenant — bounded (visited-set + depth cap), cycle-safe, boundary-terminating.

    A NULL parent ends the walk (current is the root). A parent not visible in ``acting_tenant``
    (cross-tenant or deleted) ends the walk at the highest visible ancestor ``current``. A repeated
    (cycle) or exceeding the depth cap raises :class:`HierarchyCycleError`."""
    # Defense-in-depth: the starting node must itself belong to the acting tenant (mirrors the
    # explicit-predicate discipline applied to every hop). The endpoint caller always passes an
    # RLS-resolved own-tenant row, but this guards a future caller from walking a foreign root.
    if str(legal_entity.tenant_id) != str(acting_tenant):
        raise LegalEntityNotVisible(str(legal_entity.id))
    current = legal_entity
    visited = {str(current.id)}
    for _ in range(MAX_HIERARCHY_DEPTH):
        parent_id = current.parent_legal_entity_id
        if parent_id is None:
            return str(current.id)
        if str(parent_id) in visited:
            raise HierarchyCycleError(str(legal_entity.id))
        parent = session.execute(
            select(LegalEntity).where(
                LegalEntity.id == str(parent_id),
                LegalEntity.tenant_id
                == str(acting_tenant),  # explicit tenant filter -> boundary stop
            )
        ).scalar_one_or_none()
        if parent is None:
            return str(
                current.id
            )  # boundary: parent not visible -> terminate at the highest visible
        visited.add(str(parent.id))
        current = parent
    raise HierarchyCycleError(str(legal_entity.id))  # exceeded the depth cap


def create_legal_entity(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    actor: ReferenceActor,
    lei: str | None = None,
    jurisdiction: str | None = None,
    entity_type: str | None = None,
    parent_legal_entity_id: str | None = None,
    is_active: bool = True,
) -> LegalEntity:
    """Create a ``legal_entity`` core (governed: MANUAL-source lineage + ``REFERENCE.CREATE``).

    If ``parent_legal_entity_id`` is given it is resolved tenant-filtered (a cross-tenant/unknown
    parent fails closed). Self-parenting is impossible on create (the new id is server-generated
    is server-generated and the parent must pre-exist) — it is guarded on update."""
    if parent_legal_entity_id is not None:
        resolve_legal_entity(session, parent_legal_entity_id, acting_tenant=tenant_id)

    legal_entity = LegalEntity(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        lei=lei,
        jurisdiction=jurisdiction,
        entity_type=entity_type,
        parent_legal_entity_id=(str(parent_legal_entity_id) if parent_legal_entity_id else None),
        is_active=is_active,
        record_version=1,
    )
    session.add(legal_entity)
    session.flush()
    record_reference_create(
        session,
        entity=legal_entity,
        entity_type=ENTITY_LEGAL_ENTITY,
        after_value={
            "code": code,
            "name": name,
            "lei": lei,
            "jurisdiction": jurisdiction,
            "entity_type": entity_type,
            "is_active": is_active,
            "parent_legal_entity_id": legal_entity.parent_legal_entity_id,
        },
        actor=actor,
    )
    return legal_entity


def update_legal_entity(
    session: Session,
    legal_entity: LegalEntity,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> LegalEntity:
    """Apply mutable changes (incl. re-parent / ``is_active`` flip), bump ``record_version``, emit
    ``REFERENCE.UPDATE``. A re-parent rejects **self-parent** (``parent_legal_entity_id == id``) and
    resolves the new parent tenant-filtered (cross-tenant/unknown → :class:`LegalEntityNotVisible`).
    Deep write-time cycle prevention is deferred — the read-time resolver guard handles it."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable legal_entity attributes: {sorted(unknown)}")

    new_parent = changes.get("parent_legal_entity_id")
    if "parent_legal_entity_id" in changes and new_parent is not None:
        if str(new_parent) == str(legal_entity.id):
            raise ValueError("legal_entity cannot be its own parent")
        resolve_legal_entity(session, new_parent, acting_tenant=legal_entity.tenant_id)
        changes["parent_legal_entity_id"] = str(new_parent)

    before = {key: getattr(legal_entity, key) for key in changes}
    for key, value in changes.items():
        setattr(legal_entity, key, value)
    legal_entity.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=legal_entity,
        entity_type=ENTITY_LEGAL_ENTITY,
        before_value=before,
        after_value={key: getattr(legal_entity, key) for key in changes},
        actor=actor,
    )
    return legal_entity
