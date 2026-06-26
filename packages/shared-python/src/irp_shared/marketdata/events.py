"""FX-rate governed-write provenance layer (P2-2) — caller-side audit + VENDOR lineage.

Mirrors the ``valuation`` emitter shape; the rail layer imports only ``lineage`` / ``audit`` /
``db``:

    add(version) -> flush -> record_lineage(VENDOR source, ORIGIN) -> record_event(MARKET.FX_*)

- ``ensure_vendor_source`` idempotently resolves-or-registers the acting tenant's shared
  ``VENDOR_FX`` ``data_source`` (the governed provenance root for captured vendor FX). DISTINCT from
  the row-level ``rate_source`` inert label.
- ``record_fx_create`` roots one ORIGIN edge + emits ``MARKET.FX_CREATE`` (a captured new rate
  version — initial capture OR the new open row of a supersede).
- ``record_fx_update`` emits ``MARKET.FX_UPDATE`` for a prior-head close-out — **no** new edge.
- ``record_fx_correction`` roots one ORIGIN edge + emits ``MARKET.FX_CORRECTION`` for an as-known
  vendor restatement; ``restatement_reason`` (TR-08) lands on the canonical ``justification`` field.

No mid-call commit — the caller owns the commit; if the audit or lineage insert is rejected the
whole
write rolls back (fail-closed, CTRL-032). ``before``/``after`` are DC-2 metadata only (never a
vendor-licensed payload dump). ``audit/service.py`` is **FROZEN** — ``MARKET.FX_*`` are caller-side
``event_type`` strings only. **No emit on read/``convert``** (OD-023).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source

#: MARKET.* audit category (EVT-200 block; reserved + activated in P2-2, R-07 — the P1B-1
# precedent).
MARKET_FX_CREATE_EVENT = "MARKET.FX_CREATE"
MARKET_FX_UPDATE_EVENT = "MARKET.FX_UPDATE"
MARKET_FX_CORRECTION_EVENT = "MARKET.FX_CORRECTION"

#: VENDOR ``data_source`` provenance for governed FX captures (the shared per-tenant VENDOR_FX
# root).
VENDOR_FX_SOURCE_TYPE = "VENDOR_FX"
VENDOR_FX_SOURCE_CODE = "VENDOR_FX"
VENDOR_FX_SOURCE_NAME = "Vendor FX rates"

#: ``entity_type`` literal for audit/lineage (the table name).
ENTITY_FX_RATE = "fx_rate"
#: ``source_module`` for every FX audit event.
SOURCE_MODULE = "marketdata"


@dataclass(frozen=True)
class FxRateActor:
    """Actor/correlation context threaded into every FX audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


def ensure_vendor_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's shared ``VENDOR_FX`` ``data_source``
    (the governed provenance root for captured vendor FX). Filtered by ``tenant_id`` explicitly so
    the lookup is correct on SQLite AND PG (the ``ensure_manual_source`` precedent)."""
    existing = session.execute(
        select(DataSource).where(
            DataSource.tenant_id == str(tenant_id),
            DataSource.code == VENDOR_FX_SOURCE_CODE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return register_data_source(
        session,
        tenant_id=str(tenant_id),
        code=VENDOR_FX_SOURCE_CODE,
        name=VENDOR_FX_SOURCE_NAME,
        source_type=VENDOR_FX_SOURCE_TYPE,
        actor_id=actor_id,
    )


def _origin_edge(session: Session, *, entity: Any, actor: FxRateActor) -> None:
    """Root one ORIGIN lineage edge (VENDOR_FX source) for a NEW physical version row."""
    source = ensure_vendor_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_FX_RATE,
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
    actor: FxRateActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit one MARKET.FX_* event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_FX_RATE,
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
        event_time=now,
    )


def record_fx_create(
    session: Session,
    *,
    entity: Any,
    after_value: dict[str, Any],
    actor: FxRateActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``MARKET.FX_CREATE`` for a captured new rate version."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=MARKET_FX_CREATE_EVENT,
        action="create",
        after_value=after_value,
        actor=actor,
        now=now,
    )


def record_fx_update(
    session: Session,
    *,
    entity: Any,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: FxRateActor,
    now: datetime | None = None,
) -> None:
    """Emit ``MARKET.FX_UPDATE`` for a prior-head close-out — NO new lineage edge (the version keeps
    its ORIGIN edge); before/after carry the changed boundary column only."""
    _emit(
        session,
        entity=entity,
        event_type=MARKET_FX_UPDATE_EVENT,
        action="update",
        before_value=before_value,
        after_value=after_value,
        actor=actor,
        now=now,
    )


def record_fx_correction(
    session: Session,
    *,
    entity: Any,
    restatement_reason: str,
    after_value: dict[str, Any],
    actor: FxRateActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``MARKET.FX_CORRECTION`` for an as-known vendor restatement (a
    corrected NEW version). ``restatement_reason`` (TR-08) lands on the canonical ``justification``
    audit field AND in the DC-2 ``after_value`` metadata; ``before_value`` is None — the prior row's
    ``system_to`` close-out (a separate ``MARKET.FX_UPDATE``) carries the boundary diff."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=MARKET_FX_CORRECTION_EVENT,
        action="correct",
        after_value=after_value,
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
