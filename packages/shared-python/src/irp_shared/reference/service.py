"""Reference-data write core + hybrid read dedup (P1B-1).

A single generic governed-write core mirroring the ``register_data_source`` body so every reference
create is **co-transactional and fail-closed** (no mid-call commit — the endpoint/caller owns the
commit; if the audit or lineage insert is rejected the whole write rolls back):

    add(parent [+ children]) -> flush -> record_lineage(MANUAL source) -> record_event(REFERENCE.*)

- ``ensure_manual_source`` resolves-or-registers the acting tenant's ``MANUAL`` ``data_source``
  (the provenance root the origin edge needs); the SYSTEM seed path calls it under SYSTEM context.
- ``record_reference_create`` records exactly one ORIGIN lineage edge from that MANUAL source and
  emits ``REFERENCE.CREATE`` (children fold in — no own event); ``record_reference_update`` emits
  ``REFERENCE.UPDATE`` (no new edge — an entity keeps its single origin edge).
- ``dedupe_tenant_wins`` is the **application-layer** "tenant override wins" read dedup (AD-013-R1):
  RLS ``USING`` returns own + SYSTEM rows; this keeps the own-tenant row per ``code``. The override
  precedence lives **here**, never in the RLS policy.

Imports only ``lineage`` / ``audit`` / ``db`` / ``entitlement`` (one-way). No ``irp_backend``, no
``irp_shared.models`` (plural aggregator), no ``irp_shared.ingestion`` — enforced by a test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, TypeVar

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import (
    ACTION_CORRECT,
    ACTION_CREATE,
    ACTION_STATUS_CHANGE,
    ACTION_UPDATE,
)
from irp_shared.audit.service import record_event
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.reference.events import (
    REFERENCE_CORRECTION_EVENT,
    REFERENCE_CREATE_EVENT,
    REFERENCE_STATUS_CHANGE_EVENT,
    REFERENCE_UPDATE_EVENT,
)
from irp_shared.reference.models import Currency

#: ``data_source`` provenance for governed reference CRUD (value-level vocab; no schema change).
MANUAL_SOURCE_TYPE = "MANUAL"
MANUAL_SOURCE_CODE = "MANUAL"
MANUAL_SOURCE_NAME = "Manual reference entry"

#: ``entity_type`` literals for audit/lineage (the table names; P1B-1 children carry none, P1B-2
#: profiles each emit their OWN event).
ENTITY_CURRENCY = "currency"
ENTITY_CALENDAR = "calendar"
ENTITY_RATING_SCALE = "rating_scale"
ENTITY_LEGAL_ENTITY = "legal_entity"
ENTITY_ISSUER = "issuer"
ENTITY_COUNTERPARTY = "counterparty"
ENTITY_INSTRUMENT = "instrument"
ENTITY_INSTRUMENT_TERMS = "instrument_terms"
ENTITY_IDENTIFIER_XREF = "identifier_xref"
ENTITY_CORPORATE_ACTION = "corporate_action"

#: ``source_module`` for every reference audit event.
SOURCE_MODULE = "reference"


@dataclass(frozen=True)
class ReferenceActor:
    """The actor/correlation context threaded into every reference audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class _CodedRow(Protocol):
    """Structural type for an EV row carrying ``code`` + ``tenant_id`` (for read dedup)."""

    code: str
    tenant_id: str


_RowT = TypeVar("_RowT", bound=_CodedRow)


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's ``MANUAL`` ``data_source``.

    Resolved through the (RLS-scoped) session AND filtered by ``tenant_id`` explicitly so the lookup
    is correct on SQLite (no RLS) as well as PostgreSQL. The first reference write for a tenant
    registers the source (emitting ``DATA.SOURCE_REGISTER``); later writes reuse it. SYSTEM seeds
    call this under SYSTEM context, producing the SYSTEM_TENANT MANUAL source."""
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


def record_reference_create(
    session: Session,
    *,
    entity: Any,
    entity_type: str,
    after_value: dict[str, Any],
    actor: ReferenceActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN lineage edge (MANUAL source) and emit ``REFERENCE.CREATE`` for a new head.

    Co-transactional, fail-closed; the caller has already ``add``ed + ``flush``ed the head (and any
    children) so ``entity.id`` / ``entity.tenant_id`` are set. Children fold into THIS event — they
    get no event of their own. ``after_value`` is DC-2 metadata only (identifying + controlled-vocab
    fields + child counts), never full rows or raw input. ``now`` is the deterministic-injection
    seam → ``event_time`` (default-None ⇒ server clock; only the synthetic seed passes it)."""
    source = ensure_manual_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=entity_type,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,  # explicit origin intent (not the rail default)
    )
    record_event(
        session,
        event_type=REFERENCE_CREATE_EVENT,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
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


def record_reference_update(
    session: Session,
    *,
    entity: Any,
    entity_type: str,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: ReferenceActor,
) -> None:
    """Emit ``REFERENCE.UPDATE`` for an effective-dated supersede / attribute change of a head.

    No new lineage edge — the entity keeps its ORIGIN edge from creation. ``before``/``after``
    are the diffed changed keys only (DC-2 metadata)."""
    record_event(
        session,
        event_type=REFERENCE_UPDATE_EVENT,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
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


def record_reference_correction(
    session: Session,
    *,
    entity: Any,
    entity_type: str,
    restatement_reason: str,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any],
    actor: ReferenceActor,
) -> None:
    """Root one ORIGIN edge and emit ``REFERENCE.CORRECTION`` (EVT-142) for an FR as-known restate.

    The corrected row is a NEW physical version (its own lineage origin), so this mirrors
    ``record_reference_create``'s edge rooting; the prior row's ``system_to`` close-out is a
    separate ``record_reference_update`` (no edge). EVT-142 is activated caller-side here
    (OQ-7 / R-07); the FROZEN ``audit.service.record_event`` is unchanged. ``restatement_reason``
    (TR-08) is recorded on the canonical ``justification`` audit field AND in the DC-2
    ``after_value`` metadata; ``approval_ref`` stays ``None`` until BR-7 enforcement (P6/P7)."""
    source = ensure_manual_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=entity_type,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,
    )
    record_event(
        session,
        event_type=REFERENCE_CORRECTION_EVENT,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
        entity_id=entity.id,
        action=ACTION_CORRECT,
        before_value=before_value,
        after_value=after_value,
        justification=restatement_reason,  # TR-08 reason on the canonical audit field
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
    )


def record_reference_status_change(
    session: Session,
    *,
    entity: Any,
    entity_type: str,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: ReferenceActor,
    reason: str | None = None,
) -> None:
    """Emit ``REFERENCE.STATUS_CHANGE`` (EVT-143) for an EV status-lifecycle transition of a head.

    No new lineage edge — a status transition is an in-place EV update (the row keeps its ORIGIN
    edge
    from creation), exactly like ``record_reference_update``. EVT-143 is activated caller-side here
    (OQ-1 / R-07, P1B-4) — the FROZEN ``audit.service.record_event`` is unchanged.
    ``before``/``after``
    isolate the ``status`` transition (DC-2 metadata); an optional ``reason`` lands on the canonical
    ``justification`` audit field."""
    record_event(
        session,
        event_type=REFERENCE_STATUS_CHANGE_EVENT,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
        entity_id=entity.id,
        action=ACTION_STATUS_CHANGE,
        before_value=before_value,
        after_value=after_value,
        justification=reason,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
    )


def dedupe_tenant_wins(rows: Sequence[_RowT], acting_tenant: str) -> list[_RowT]:
    """Application-layer "tenant override wins" dedup (AD-013-R1): keep one row per ``code``, the
    acting tenant's row preferred over the SYSTEM_TENANT row. Deterministic (sorted by code).

    RLS already returned the union (own + SYSTEM); precedence is decided here, not in the policy.
    This is the portable equivalent of ``SELECT DISTINCT ON (code) ... ORDER BY code,
    (tenant_id = :acting) DESC`` and behaves identically on PostgreSQL and SQLite."""
    chosen: dict[str, _RowT] = {}
    ordered = sorted(
        rows,
        key=lambda r: (r.code, 0 if str(r.tenant_id) == str(acting_tenant) else 1),
    )
    for row in ordered:
        chosen.setdefault(row.code, row)  # own-tenant sorts first within a code -> wins
    return [chosen[code] for code in sorted(chosen)]


class CurrencyNotVisible(Exception):
    """Raised when a currency ``code`` is not visible to the acting tenant — neither an own-tenant
    nor a SYSTEM_TENANT row exists (a foreign tenant's currency, or an unknown code). Fails
    closed."""

    def __init__(self, code: str) -> None:
        super().__init__(f"currency {code!r} is not visible in the current tenant context")
        self.code = code


def resolve_currency(session: Session, code: str, *, acting_tenant: str) -> Currency:
    """Resolve an ISO currency ``code`` for the acting tenant under **AD-013-R1 HYBRID** visibility:
    admit an **own-tenant OR SYSTEM_TENANT** row (own wins via ``dedupe_tenant_wins``), reject a
    **foreign tenant's** currency. Raises :class:`CurrencyNotVisible` when neither exists.

    This is deliberately **NOT** the symmetric ``tenant_id == acting_tenant`` by-id resolver
    pattern:
    `currency` is the hybrid SYSTEM/tenant table, so a symmetric predicate would reject the SYSTEM
    `USD`/`EUR` base and break FX triangulation. The explicit ``(own OR SYSTEM)`` predicate is
    correct
    on SQLite (no RLS) and is the RLS ``USING``-arm on PG (defense-in-depth)."""
    rows = list(
        session.execute(
            select(Currency).where(
                Currency.code == code,
                or_(
                    Currency.tenant_id == str(acting_tenant),
                    Currency.tenant_id == SYSTEM_TENANT_ID,
                ),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise CurrencyNotVisible(code)
    return dedupe_tenant_wins(rows, acting_tenant)[0]  # own-tenant override wins over SYSTEM
