"""Valuation governed-write core (P1C-4) — co-transactional, fail-closed audit + lineage.

A self-contained mirror of the P1C-3 ``position.service`` shape; the rail layer imports only
``lineage`` / ``audit`` / ``db`` (the domain resolvers ``resolve_portfolio``/``resolve_instrument``
are imported by the binder, not here):

    add(version) -> flush -> record_lineage(MANUAL source, ORIGIN) -> record_event(VALUATION.*)

- ``ensure_manual_source`` idempotently resolves-or-registers the acting tenant's ``MANUAL``
  ``data_source`` (the shared per-tenant ``code='MANUAL'`` provenance root). NOTE: this is the
  governed-write provenance edge; it is DISTINCT from the row-level ``mark_source`` captured label.
- ``record_valuation_create`` roots one ORIGIN edge + emits ``VALUATION.CREATE`` (a captured new
mark
  version — initial create OR the new open row of a supersede).
- ``record_valuation_update`` emits ``VALUATION.UPDATE`` for a prior-head close-out — **no** new
edge;
  carries the changed boundary column in before/after.
- ``record_valuation_correction`` roots one ORIGIN edge + emits ``VALUATION.CORRECTION`` (EVT-182)
for
  an as-known restatement; ``restatement_reason`` (TR-08) lands on the canonical ``justification``
  field.

No mid-call commit — the endpoint/caller owns the commit; if the audit or lineage insert is rejected
the whole write rolls back (fail-closed, AUD-04 / CTRL-032). ``before``/``after`` are DC-2 metadata
only. ``audit/service.py`` is **FROZEN** — ``VALUATION.*`` are caller-side ``event_type`` strings
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
from irp_shared.valuation.events import (
    VALUATION_CORRECTION_EVENT,
    VALUATION_CREATE_EVENT,
    VALUATION_UPDATE_EVENT,
)

#: ``data_source`` provenance for governed valuation records (the shared per-tenant MANUAL root).
MANUAL_SOURCE_TYPE = "MANUAL"
MANUAL_SOURCE_CODE = "MANUAL"
MANUAL_SOURCE_NAME = "Manual reference entry"

#: ``entity_type`` literal for audit/lineage (the table name).
ENTITY_VALUATION = "valuation"

#: ``source_module`` for every valuation audit event.
SOURCE_MODULE = "valuation"


@dataclass(frozen=True)
class ValuationActor:
    """Actor/correlation context threaded into every valuation audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's ``MANUAL`` ``data_source`` (shared per-
    tenant ``code='MANUAL'`` root; resolve-or-register so it is shared with reference/portfolio/
    transaction/position writes). Filtered by ``tenant_id`` explicitly so the lookup is correct on
    SQLite AND PG."""
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


def _origin_edge(session: Session, *, entity: Any, actor: ValuationActor) -> None:
    """Root one ORIGIN lineage edge (MANUAL source) for a NEW physical version row."""
    source = ensure_manual_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_VALUATION,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    entity: Any,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: ValuationActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
) -> None:
    """Emit one VALUATION.* event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_VALUATION,
        entity_id=entity.id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        justification=justification,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
    )


def record_valuation_create(
    session: Session, *, entity: Any, after_value: dict[str, Any], actor: ValuationActor
) -> None:
    """Root one ORIGIN edge + emit ``VALUATION.CREATE`` (EVT-180) for a captured new mark."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=VALUATION_CREATE_EVENT,
        action="create",
        after_value=after_value,
        actor=actor,
    )


def record_valuation_update(
    session: Session,
    *,
    entity: Any,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: ValuationActor,
) -> None:
    """Emit ``VALUATION.UPDATE`` (EVT-181) for a prior-head close-out — NO new lineage edge (the
    version keeps its ORIGIN edge); before/after carry the changed boundary column only."""
    _emit(
        session,
        entity=entity,
        event_type=VALUATION_UPDATE_EVENT,
        action="update",
        before_value=before_value,
        after_value=after_value,
        actor=actor,
    )


def record_valuation_correction(
    session: Session,
    *,
    entity: Any,
    restatement_reason: str,
    after_value: dict[str, Any],
    actor: ValuationActor,
) -> None:
    """Root one ORIGIN edge + emit ``VALUATION.CORRECTION`` (EVT-182) for an as-known restatement (a
    corrected NEW version). ``restatement_reason`` (TR-08) lands on the canonical ``justification``
    audit field AND in the DC-2 ``after_value`` metadata; ``before_value`` is left None — the prior
    row's ``system_to`` close-out (a separate ``VALUATION.UPDATE``) carries the boundary diff."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=VALUATION_CORRECTION_EVENT,
        action="correct",
        after_value=after_value,
        actor=actor,
        justification=restatement_reason,
    )
