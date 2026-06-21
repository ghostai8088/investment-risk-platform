"""Data-source registration and the lineage capture/enforcement contract (BX-LIN).

- ``register_data_source`` / ``update_data_source`` — the internal/admin utility for the
  provenance root (no public write endpoint). Each emits a taxonomy audit event in the **same
  transaction** as the data row (fail-closed: if the audit insert is rejected, the row rolls back).
- ``record_lineage`` — the single capture seam every later governed write calls. It stamps
  ``tenant_id`` **server-side** and resolves the source through the (RLS-scoped) session so a
  cross-tenant source id fails closed. It emits **no** audit event of its own — the edge is
  metadata of the already-audited governed write (DR-P1A0 / plan §6).
- ``assert_has_lineage`` — the no-bypass enforcement check (CTRL-013): a governed write lacking a
  lineage edge raises ``LineageMissingError``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.lineage.models import (
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_DATA_SOURCE,
    DataSource,
    LineageEdge,
)

#: Audit taxonomy codes for data-source provenance writes (audit_event_taxonomy.md, DATA category).
SOURCE_REGISTER_EVENT = "DATA.SOURCE_REGISTER"
SOURCE_UPDATE_EVENT = "DATA.SOURCE_UPDATE"

#: Mutable attributes ``update_data_source`` will diff/apply.
_UPDATABLE = ("name", "source_type", "description", "is_active")


class LineageMissingError(Exception):
    """Raised when a governed target has no lineage edge (CTRL-013 no-bypass)."""

    def __init__(self, target_entity_type: str, target_entity_id: str) -> None:
        super().__init__(
            f"no lineage edge for {target_entity_type}:{target_entity_id} (BX-LIN required)"
        )
        self.target_entity_type = target_entity_type
        self.target_entity_id = str(target_entity_id)


class DataSourceNotVisible(Exception):
    """Raised when ``record_lineage`` cannot resolve the source under the caller's tenant scope
    (cross-tenant id hidden by RLS, or unknown) — the lineage write fails closed."""

    def __init__(self, source_id: str) -> None:
        super().__init__(f"data_source {source_id} is not visible in the current tenant context")
        self.source_id = str(source_id)


def register_data_source(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    source_type: str,
    actor_id: str,
    description: str | None = None,
) -> DataSource:
    """Create a ``data_source`` and audit it (``DATA.SOURCE_REGISTER``), same transaction."""
    source = DataSource(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        source_type=source_type,
        description=description,
        is_active=True,
        record_version=1,
    )
    session.add(source)
    session.flush()

    record_event(
        session,
        event_type=SOURCE_REGISTER_EVENT,
        tenant_id=str(tenant_id),
        actor_type="user",
        actor_id=actor_id,
        source_module="lineage",
        entity_type="data_source",
        entity_id=source.id,
        action="create",
        after_value={"code": code, "name": name, "source_type": source_type},
    )
    return source


def update_data_source(
    session: Session,
    source: DataSource,
    *,
    actor_id: str,
    **changes: Any,
) -> DataSource:
    """Apply mutable changes to a ``data_source``, bump ``record_version``, and audit the
    before/after (``DATA.SOURCE_UPDATE``) in the same transaction."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable data_source attributes: {sorted(unknown)}")

    before = {key: getattr(source, key) for key in changes}
    for key, value in changes.items():
        setattr(source, key, value)
    source.record_version += 1
    session.flush()

    record_event(
        session,
        event_type=SOURCE_UPDATE_EVENT,
        tenant_id=source.tenant_id,
        actor_type="user",
        actor_id=actor_id,
        source_module="lineage",
        entity_type="data_source",
        entity_id=source.id,
        action="update",
        before_value=before,
        after_value={key: getattr(source, key) for key in changes},
    )
    return source


def record_lineage(
    session: Session,
    *,
    source: DataSource,
    target_entity_type: str,
    target_entity_id: str,
    run_id: str | None = None,
    edge_kind: str = EDGE_KIND_ORIGIN,
) -> LineageEdge:
    """Record one ``source → target`` lineage edge (the BX-LIN capture contract).

    Inserts into the **caller's** transaction (co-transactional with the governed write it
    describes). ``tenant_id`` is stamped from the source resolved **through the RLS-scoped
    session**, never from caller input — a cross-tenant source id resolves to zero rows and
    raises :class:`DataSourceNotVisible` (fail closed). Emits no audit event of its own.
    """
    resolved = session.execute(
        select(DataSource).where(DataSource.id == str(source.id))
    ).scalar_one_or_none()
    if resolved is None:
        raise DataSourceNotVisible(str(source.id))

    edge = LineageEdge(
        tenant_id=resolved.tenant_id,  # server-side stamp; RLS WITH CHECK is the backstop
        source_type=SOURCE_TYPE_DATA_SOURCE,
        source_id=resolved.id,
        target_entity_type=target_entity_type,
        target_entity_id=str(target_entity_id),
        edge_kind=edge_kind,
        run_id=(str(run_id) if run_id is not None else None),
    )
    session.add(edge)
    session.flush()
    return edge


def assert_has_lineage(
    session: Session,
    target_entity_type: str,
    target_entity_id: str,
    *,
    tenant_id: str | None = None,
) -> LineageEdge:
    """Return the ``source → target`` edge for a governed output, or raise
    :class:`LineageMissingError` (CTRL-013). Tenant-scoped by RLS on PostgreSQL; pass
    ``tenant_id`` to also scope explicitly (used by SQLite logic-level tests)."""
    stmt = select(LineageEdge).where(
        LineageEdge.target_entity_type == target_entity_type,
        LineageEdge.target_entity_id == str(target_entity_id),
    )
    if tenant_id is not None:
        stmt = stmt.where(LineageEdge.tenant_id == str(tenant_id))
    edge = session.execute(stmt.limit(1)).scalar_one_or_none()
    if edge is None:
        raise LineageMissingError(target_entity_type, target_entity_id)
    return edge
