"""Transaction governed-write core (P1C-2) — co-transactional, fail-closed audit + lineage.

A thin mirror of ``portfolio.service`` / ``reference.service`` (the established governed-write
shape),
kept **self-contained** for the rail plumbing so the audit/lineage layer imports only the rails
(``lineage`` / ``audit`` / ``db``); the domain resolvers
(``resolve_portfolio``/``resolve_instrument``)
are imported by the binder, not here:

    add(transaction) -> flush -> record_lineage(MANUAL source, ORIGIN) ->
    record_event(TRANSACTION.*)

- ``ensure_manual_source`` idempotently resolves-or-registers the acting tenant's ``MANUAL``
  ``data_source`` (the shared per-tenant ``code='MANUAL'`` provenance root).
- ``record_transaction_record`` roots one ORIGIN lineage edge + emits ``TRANSACTION.RECORD`` (a
normal
  capture); ``record_transaction_reverse`` roots one ORIGIN edge + emits ``TRANSACTION.REVERSE`` (a
  reversal record — itself a NEW row). Both are append-only creates; there is NO update path.

No mid-call commit — the endpoint/caller owns the commit; if the audit or lineage insert is rejected
the whole write rolls back (fail-closed, AUD-04 / CTRL-032). ``before``/``after`` are DC-2 metadata
only. ``audit/service.py`` is **FROZEN** — ``TRANSACTION.*`` are caller-side ``event_type`` strings
only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.transaction.events import (
    TRANSACTION_RECORD_EVENT,
    TRANSACTION_REVERSE_EVENT,
)

#: ``data_source`` provenance for governed transaction records (the shared per-tenant MANUAL root).
MANUAL_SOURCE_TYPE = "MANUAL"
MANUAL_SOURCE_CODE = "MANUAL"
MANUAL_SOURCE_NAME = "Manual reference entry"

#: ``entity_type`` literal for audit/lineage (the table name).
ENTITY_TRANSACTION = "transaction"

#: ``source_module`` for every transaction audit event.
SOURCE_MODULE = "transaction"


@dataclass(frozen=True)
class TransactionActor:
    """Actor/correlation context threaded into every transaction audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's ``MANUAL`` ``data_source`` (shared per-
    tenant ``code='MANUAL'`` root; resolve-or-register so it is shared with reference/portfolio
    writes). Filtered by ``tenant_id`` explicitly so the lookup is correct on SQLite AND PG."""
    existing = session.execute(
        select(DataSource).where(
            DataSource.tenant_id == str(tenant_id),
            DataSource.code == MANUAL_SOURCE_CODE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return register_data_source(
        session,
        tenant_id=str(tenant_id),
        code=MANUAL_SOURCE_CODE,
        name=MANUAL_SOURCE_NAME,
        source_type=MANUAL_SOURCE_TYPE,
        actor_id=actor_id,
    )


def _emit(
    session: Session,
    *,
    entity: Any,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: TransactionActor,
    justification: str | None = None,
) -> None:
    """Root one ORIGIN lineage edge (MANUAL source) + emit one TRANSACTION.* event for a NEW row.

    Co-transactional, fail-closed; the caller has already ``add``ed + ``flush``ed the row so
    ``entity.id``/``entity.tenant_id`` are set. Every transaction write is a new record (no update),
    so every write roots its own ORIGIN edge."""
    source = ensure_manual_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_TRANSACTION,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,
    )
    record_event(
        session,
        event_type=event_type,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_TRANSACTION,
        entity_id=entity.id,
        action=action,
        after_value=after_value,
        justification=justification,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
    )


def record_transaction_record(
    session: Session, *, entity: Any, after_value: dict[str, Any], actor: TransactionActor
) -> None:
    """Root one ORIGIN edge + emit ``TRANSACTION.RECORD`` (EVT-160) for a normal capture."""
    _emit(
        session,
        entity=entity,
        event_type=TRANSACTION_RECORD_EVENT,
        action="record",
        after_value=after_value,
        actor=actor,
    )


def record_transaction_reverse(
    session: Session,
    *,
    entity: Any,
    after_value: dict[str, Any],
    actor: TransactionActor,
    reason: str | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``TRANSACTION.REVERSE`` (EVT-161) for a reversal record (new row
    with ``reverses_transaction_id``; the original is never mutated). ``reason`` (if any) lands on
    the
    canonical ``justification`` audit field."""
    _emit(
        session,
        entity=entity,
        event_type=TRANSACTION_REVERSE_EVENT,
        action="reverse",
        after_value=after_value,
        actor=actor,
        justification=reason,
    )
