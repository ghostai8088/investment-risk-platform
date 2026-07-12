"""Portfolio governed-write core (P1C-1) — co-transactional, fail-closed audit + lineage.

A thin mirror of ``reference.service`` (the established governed-write shape), kept
**self-contained**
so the portfolio package imports only the rails (``lineage`` / ``audit`` / ``db``), never
``reference``
or ``irp_backend`` or ``irp_shared.models`` (one-way deps, enforced by a test):

    add(node) -> flush -> record_lineage(MANUAL source, ORIGIN) -> record_event(PORTFOLIO.*)

- ``ensure_manual_source`` idempotently resolves-or-registers the acting tenant's ``MANUAL``
  ``data_source`` (the same per-tenant ``code='MANUAL'`` provenance root the reference writes use; a
  resolve-or-register so it is shared, not duplicated, when both write in one tenant).
- ``record_portfolio_create`` roots exactly one ORIGIN lineage edge and emits ``PORTFOLIO.CREATE``.
- ``record_portfolio_update`` emits ``PORTFOLIO.UPDATE`` (an in-place EV supersede keeps its single
  origin edge — **no new edge**, the ``reference.record_reference_update`` precedent).

No mid-call commit — the endpoint/caller owns the commit; if the audit or lineage insert is rejected
the whole write rolls back (fail-closed, AUD-04 / CTRL-032). ``before``/``after`` are DC-2 metadata
only (identifying + controlled-vocab fields), never full rows or raw input. ``audit/service.py`` is
**FROZEN** — ``PORTFOLIO.*`` are caller-side ``event_type`` strings only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.service import record_event
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.portfolio.events import PORTFOLIO_CREATE_EVENT, PORTFOLIO_UPDATE_EVENT

#: ``data_source`` provenance for governed portfolio CRUD (the shared per-tenant MANUAL root).
MANUAL_SOURCE_TYPE = "MANUAL"
MANUAL_SOURCE_CODE = "MANUAL"
MANUAL_SOURCE_NAME = "Manual reference entry"

#: ``entity_type`` literal for audit/lineage (the table name).
ENTITY_PORTFOLIO = "portfolio"

#: ``source_module`` for every portfolio audit event.
SOURCE_MODULE = "portfolio"


@dataclass(frozen=True)
class PortfolioActor:
    """The actor/correlation context threaded into every portfolio audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's ``MANUAL`` ``data_source``.

    Resolved through the (RLS-scoped) session AND filtered by ``tenant_id`` explicitly so the lookup
    is correct on SQLite (no RLS) as well as PostgreSQL. Shares the per-tenant ``code='MANUAL'``
    root
    with reference writes (resolve-or-register — whichever governed write happens first registers
    it,
    the rest reuse it)."""
    # Race-safe (MD-H1 review fold): two concurrent FIRST callers both SELECT-miss then
    # INSERT the same key; the loser re-resolves the peer instead of aborting the unit.
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == str(tenant_id),
                DataSource.code == MANUAL_SOURCE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=str(tenant_id),
            code=MANUAL_SOURCE_CODE,
            name=MANUAL_SOURCE_NAME,
            source_type=MANUAL_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def record_portfolio_create(
    session: Session,
    *,
    entity: Any,
    after_value: dict[str, Any],
    actor: PortfolioActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN lineage edge (MANUAL source) and emit ``PORTFOLIO.CREATE`` for a new node.

    Co-transactional, fail-closed; the caller has already ``add``ed + ``flush``ed the node so
    ``entity.id`` / ``entity.tenant_id`` are set. ``after_value`` is DC-2 metadata only. ``now`` is
    the deterministic-injection seam → ``event_time`` (default-None ⇒ server clock)."""
    source = ensure_manual_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_PORTFOLIO,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,  # explicit origin intent (not the rail default)
    )
    record_event(
        session,
        event_type=PORTFOLIO_CREATE_EVENT,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_PORTFOLIO,
        entity_id=entity.id,
        action=ACTION_CREATE,
        after_value=after_value,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
        event_time=now,
    )


def record_portfolio_update(
    session: Session,
    *,
    entity: Any,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: PortfolioActor,
) -> None:
    """Emit ``PORTFOLIO.UPDATE`` for an in-place EV supersede / attribute change of a node.

    No new lineage edge — the node keeps its ORIGIN edge from creation (a status flip rides on this
    event too, no separate STATUS_CHANGE in P1C-1). ``before``/``after`` are the diffed changed keys
    only (DC-2 metadata)."""
    record_event(
        session,
        event_type=PORTFOLIO_UPDATE_EVENT,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_PORTFOLIO,
        entity_id=entity.id,
        action=ACTION_UPDATE,
        before_value=before_value,
        after_value=after_value,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
    )
