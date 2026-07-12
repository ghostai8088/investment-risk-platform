"""Price-point binder + governed-write provenance (P2-4, ENT-020) — the FR captured-price protocol.

``price_point`` is **captured vendor security price market data** (OD-P2-4-*), reusing the P2-2
``fx_rate`` / P1C-4 ``valuation`` FR protocol **verbatim**. Full version history in-table on BOTH
axes; ``(instrument_id, price_date, price_type, currency_code, price_source)`` is the logical key
(``price_date``/``price_type``/``currency_code``/``price_source`` are immutable components carried
verbatim; the FR axes version the *price* for a fixed key). Three governed operations + the as-of
read:

- ``capture_price`` — the first open price for an ``(instrument, price_date, price_type, currency,
  source)``.
- ``supersede_price`` — a new *valid-time* price for the SAME key: close the head's ``valid_to``
  (``MARKET.PRICE_UPDATE``), then insert a new open version (``MARKET.PRICE_CREATE``).
- ``correct_price`` — an as-known *system-time* vendor restatement (TR-08): close the prior row's
  ``system_to`` (``MARKET.PRICE_UPDATE``), then insert a corrected version over the SAME period
  + same key (``MARKET.PRICE_CORRECTION``).
- ``reconstruct_price_as_of`` — the bitemporal read (current view when ``known_at`` is now).

Invariants (verbatim from ``fx_rate``): ONE ``now = utcnow()`` per op; CLOSE-FIRST ordering; a prior
version's CONTENT columns are NEVER mutated — only ``valid_to``/``system_to``. The instrument is
resolved via the tenant-predicated ``resolve_instrument`` (cross-tenant fail-closed); currency via
the hybrid-aware ``resolve_currency`` (own OR SYSTEM). ``price`` is captured (never computed); **RAW
vendor prices only** (no corporate-action adjustment). The **DQ gate** (required-field NOT_NULL
+ strictly-positive RANGE, fail-closed, ``DATA.VALIDATE``) co-transactional. NO conversion, NO
pricing/valuation model, NO return/factor/risk, NO exposure, NO ``calculation_run``.

The provenance layer mirrors the ``fx_rate`` emitter shape: one VENDOR (``VENDOR_PRICE``)
``data_source`` ORIGIN lineage edge per NEW version + a caller-side ``MARKET.PRICE_*`` event
to the FROZEN ``record_event``. No mid-call commit (CTRL-032 fail-closed); ``before``/``after`` are
DC-2 metadata only; **no emit on read** (OD-023). ``audit/service.py`` is FROZEN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CORRECT, ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.payload import json_safe as _json_safe
from irp_shared.audit.service import record_event
from irp_shared.db.bitemporal import assert_supersede_effective_at
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL, RULE_TYPE_RANGE
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.marketdata.models import PRICE_TYPE_CLOSE, PRICE_TYPES, PricePoint
from irp_shared.reference.instrument import resolve_instrument
from irp_shared.reference.service import resolve_currency

# --- audit / provenance constants (the MARKET.* family at EVT-200; the VENDOR_FX precedent) ---
MARKET_PRICE_CREATE_EVENT = "MARKET.PRICE_CREATE"
MARKET_PRICE_UPDATE_EVENT = "MARKET.PRICE_UPDATE"
MARKET_PRICE_CORRECTION_EVENT = "MARKET.PRICE_CORRECTION"
VENDOR_PRICE_SOURCE_TYPE = "VENDOR_PRICE"
VENDOR_PRICE_SOURCE_CODE = "VENDOR_PRICE"
VENDOR_PRICE_SOURCE_NAME = "Vendor security prices"
ENTITY_PRICE_POINT = "price_point"
SOURCE_MODULE = "marketdata"

#: The captured content fields the binder carries-forward (the mutable content; ``price`` required).
#: The key components (instrument_id/price_date/price_type/currency_code/price_source) are carried
#: verbatim, NOT here.
PRICE_FIELDS = ("price",)
#: Fields that must be present for a governed capture (the required-field DQ gate universe).
REQUIRED_PRICE_FIELDS = (
    "instrument_id",
    "price_date",
    "price",
    "price_type",
    "currency_code",
    "price_source",
)

#: Per-tenant governed DQ rule codes (resolve-or-register; the P2-2 ``fx`` pattern).
_REQUIRED_RULE_CODE = "price.required_fields"
_POSITIVE_RULE_CODE = "price.positive_price"


@dataclass(frozen=True)
class PriceActor:
    """Actor/correlation context threaded into every price audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class PriceValueError(Exception):
    """Raised for an out-of-vocab ``price_type`` — a value error caught before write (fail-closed;
    maps to 422)."""


class PriceNotVisible(Exception):
    """Raised when a ``price_point`` id is not visible in the acting tenant scope
    (cross-tenant/unknown)."""

    def __init__(self, price_id: str) -> None:
        super().__init__(f"price_point {price_id} is not visible in the current tenant context")
        self.price_id = str(price_id)


class NoCurrentPrice(Exception):
    """Raised when a supersede is requested but the logical key has no open head."""

    def __init__(
        self, instrument_id: str, price_date: date, price_type: str, currency: str, source: str
    ) -> None:
        super().__init__(
            f"price_point {instrument_id} {price_type}/{currency}/{source} for {price_date} "
            f"has no current (open) version"
        )
        self.instrument_id, self.price_date = str(instrument_id), price_date
        self.price_type, self.currency_code, self.price_source = price_type, currency, source


def _summary(row: PricePoint, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A DC-2 price-summary dict (metadata only) for the audit after_value (never a bulk dump)."""
    data: dict[str, Any] = {
        "instrument_id": _json_safe(row.instrument_id),
        "price_date": _json_safe(row.price_date),
        "price_type": row.price_type,
        "currency_code": row.currency_code,
        "price_source": row.price_source,
        "price": _json_safe(row.price),
        "valid_from": _json_safe(row.valid_from),
        "valid_to": _json_safe(row.valid_to),
        "system_from": _json_safe(row.system_from),
    }
    if extra:
        data.update(extra)
    return data


def _check_field_kwargs(fields: dict[str, Any]) -> None:
    unknown = set(fields) - set(PRICE_FIELDS)
    if unknown:
        raise ValueError(f"non-price_point content attributes: {sorted(unknown)}")


def _validate_price_type(price_type: str) -> None:
    if price_type not in PRICE_TYPES:
        raise PriceValueError(f"price_type {price_type!r} not in {PRICE_TYPES} (CLOSE/MID/NAV v1)")


def _resolve_refs(
    session: Session, instrument_id: str, currency_code: str, *, acting_tenant: str
) -> None:
    """Validate the instrument FK (tenant-predicated; cross-tenant/unknown -> InstrumentNotVisible)
    and the currency (hybrid-aware own OR SYSTEM -> CurrencyNotVisible) — both fail closed BEFORE
    any write."""
    resolve_instrument(session, str(instrument_id), acting_tenant=acting_tenant)
    resolve_currency(session, currency_code, acting_tenant=acting_tenant)


def _ensure_rule(
    session: Session,
    *,
    tenant_id: str,
    actor: PriceActor,
    code: str,
    name: str,
    rule_type: str,
    params: dict[str, Any],
) -> DataQualityRule:
    """Resolve-or-register a per-tenant governed DQ rule (audited; the P2-2 pattern)."""
    # Race-safe (MD-H1 review fold): two concurrent FIRST callers both SELECT-miss then
    # INSERT the same key; the loser re-resolves the peer instead of aborting the unit.
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataQualityRule).where(
                DataQualityRule.tenant_id == str(tenant_id),
                DataQualityRule.code == code,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_dq_rule(
            session,
            tenant_id=str(tenant_id),
            code=code,
            name=name,
            rule_type=rule_type,
            actor_id=actor.actor_id,
            params=params,
            target_entity_type=ENTITY_PRICE_POINT,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_price_dq_gate(
    session: Session, *, acting_tenant: str, actor: PriceActor, row: PricePoint
) -> None:
    """Fail-closed DQ gate (co-transactional; ``DATA.VALIDATE``): (1) required-field NOT_NULL
    via the sentinel-null dataset; (2) strictly-positive RANGE on ``price``. A failure raises
    ``DataQualityError`` -> the caller's whole unit rolls back (CTRL-032; no row). Staleness/
    completeness are DEFERRED (OQ-P2-4-4)."""
    missing = any(getattr(row, f) is None for f in REQUIRED_PRICE_FIELDS)
    required_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_REQUIRED_RULE_CODE,
        name="Price required fields present",
        rule_type=RULE_TYPE_NOT_NULL,
        params={"column": "present"},
    )
    run_quality_check(
        session,
        rule=required_rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_PRICE_POINT,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )
    positive_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_POSITIVE_RULE_CODE,
        name="Price strictly positive",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "price", "min": 0, "min_inclusive": False},
    )
    run_quality_check(
        session,
        rule=positive_rule,
        dataset=[{"price": row.price}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_PRICE_POINT,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


def _current_open(
    session: Session,
    *,
    acting_tenant: str,
    instrument_id: str,
    price_date: date,
    price_type: str,
    currency_code: str,
    price_source: str,
) -> PricePoint | None:
    """The single version OPEN ON BOTH axes for a logical key — the bitemporal current head — or
    ``None``. Tenant-predicated."""
    return session.execute(
        select(PricePoint).where(
            PricePoint.tenant_id == str(acting_tenant),
            PricePoint.instrument_id == str(instrument_id),
            PricePoint.price_date == price_date,
            PricePoint.price_type == price_type,
            PricePoint.currency_code == currency_code,
            PricePoint.price_source == price_source,
            PricePoint.valid_to.is_(None),
            PricePoint.system_to.is_(None),
        )
    ).scalar_one_or_none()


def resolve_price(session: Session, price_id: str, *, acting_tenant: str) -> PricePoint:
    """Resolve a ``price_point`` version by id with an EXPLICIT ``tenant_id == acting_tenant``
    predicate (fail-closed on SQLite + PG). Raises :class:`PriceNotVisible` on a hidden id."""
    row = session.execute(
        select(PricePoint).where(
            PricePoint.id == str(price_id),
            PricePoint.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise PriceNotVisible(str(price_id))
    return row


# --- provenance: VENDOR data_source + the caller-side MARKET.PRICE_* emitters ---


def ensure_vendor_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's shared ``VENDOR_PRICE`` ``data_source``
    (the governed provenance root for captured vendor prices; the ``VENDOR_FX`` precedent). DISTINCT
    from the row-level ``price_source`` key label."""
    # Race-safe (MD-H1 review fold): two concurrent FIRST callers both SELECT-miss then
    # INSERT the same key; the loser re-resolves the peer instead of aborting the unit.
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == str(tenant_id),
                DataSource.code == VENDOR_PRICE_SOURCE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=str(tenant_id),
            code=VENDOR_PRICE_SOURCE_CODE,
            name=VENDOR_PRICE_SOURCE_NAME,
            source_type=VENDOR_PRICE_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def _origin_edge(session: Session, *, entity: PricePoint, actor: PriceActor) -> None:
    """Root one ORIGIN lineage edge (VENDOR_PRICE source) for a NEW physical version row."""
    source = ensure_vendor_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_PRICE_POINT,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    entity: PricePoint,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: PriceActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit MARKET.PRICE_* event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_PRICE_POINT,
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


def record_price_create(
    session: Session,
    *,
    entity: PricePoint,
    after_value: dict[str, Any],
    actor: PriceActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``MARKET.PRICE_CREATE`` for a captured new price version."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=MARKET_PRICE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=after_value,
        actor=actor,
        now=now,
    )


def record_price_update(
    session: Session,
    *,
    entity: PricePoint,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: PriceActor,
    now: datetime | None = None,
) -> None:
    """Emit ``MARKET.PRICE_UPDATE`` for a prior-head close-out — NO new lineage edge; before/after
    carry the changed boundary column only."""
    _emit(
        session,
        entity=entity,
        event_type=MARKET_PRICE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before_value,
        after_value=after_value,
        actor=actor,
        now=now,
    )


def record_price_correction(
    session: Session,
    *,
    entity: PricePoint,
    restatement_reason: str,
    after_value: dict[str, Any],
    actor: PriceActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``MARKET.PRICE_CORRECTION`` for an as-known vendor restatement.
    ``restatement_reason`` (TR-08) lands on the canonical ``justification`` field + the DC-2
    ``after_value``."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=MARKET_PRICE_CORRECTION_EVENT,
        action=ACTION_CORRECT,
        after_value=after_value,
        actor=actor,
        justification=restatement_reason,
        now=now,
    )


# --- the governed binder (capture / supersede / correct / reconstruct) ---


def capture_price(
    session: Session,
    *,
    instrument_id: str,
    price_date: date,
    price: Decimal,
    currency_code: str,
    price_source: str,
    acting_tenant: str,
    actor: PriceActor,
    price_type: str = PRICE_TYPE_CLOSE,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> PricePoint:
    """Capture the first price for an ``(instrument, price_date, price_type, currency, source)``
    (governed: VENDOR ORIGIN lineage + ``MARKET.PRICE_CREATE`` + the DQ gate). The instrument FK
    is resolved tenant-predicated (cross-tenant/unknown -> ``InstrumentNotVisible``) and currency
    hybrid-aware (own OR SYSTEM -> ``CurrencyNotVisible``); ``price`` is captured, never computed.
    ``entity_id``/``now`` are the deterministic-injection seam (default-None => prod unchanged)."""
    _validate_price_type(price_type)
    _resolve_refs(session, instrument_id, currency_code, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = PricePoint(
        tenant_id=str(acting_tenant),
        instrument_id=str(instrument_id),
        price_date=price_date,  # immutable logical-key component (NOT the valid_from axis)
        price_type=price_type,
        currency_code=currency_code,
        price_source=price_source,
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        price=price,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id  # seam: deterministic uuid5 id
    session.add(row)
    session.flush()
    _run_price_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=row)
    record_price_create(session, entity=row, after_value=_summary(row), actor=actor, now=now)
    return row


def supersede_price(
    session: Session,
    *,
    instrument_id: str,
    price_date: date,
    price_type: str,
    currency_code: str,
    price_source: str,
    acting_tenant: str,
    actor: PriceActor,
    effective_at: datetime,
    entity_id: str | None = None,
    now: datetime | None = None,
    **new_fields: Any,
) -> PricePoint:
    """Effective-dated (valid-time) re-price for the SAME key: close the head's ``valid_to``
    (``MARKET.PRICE_UPDATE``), then insert a new version (``MARKET.PRICE_CREATE`` + its own ORIGIN
    edge + the DQ gate). Prior fields are carried forward and ``new_fields`` override; the head is
    sourced via the tenant-predicated ``_current_open`` (never a caller-supplied id)."""
    _validate_price_type(price_type)
    _resolve_refs(session, instrument_id, currency_code, acting_tenant=acting_tenant)
    _check_field_kwargs(new_fields)
    prior = _current_open(
        session,
        acting_tenant=acting_tenant,
        instrument_id=instrument_id,
        price_date=price_date,
        price_type=price_type,
        currency_code=currency_code,
        price_source=price_source,
    )
    if prior is None:
        raise NoCurrentPrice(instrument_id, price_date, price_type, currency_code, price_source)

    assert_supersede_effective_at(prior.valid_from, effective_at, error=PriceValueError)
    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST
    session.flush()
    record_price_update(
        session,
        entity=prior,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    carried = {field: getattr(prior, field) for field in PRICE_FIELDS}
    new = PricePoint(
        tenant_id=str(acting_tenant),
        instrument_id=prior.instrument_id,
        price_date=prior.price_date,  # carried verbatim (immutable logical key)
        price_type=prior.price_type,
        currency_code=prior.currency_code,
        price_source=prior.price_source,
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
        **{**carried, **new_fields},
    )
    if entity_id is not None:
        new.id = entity_id
    session.add(new)
    session.flush()
    _run_price_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=new)
    record_price_create(session, entity=new, after_value=_summary(new), actor=actor, now=now)
    return new


def correct_price(
    session: Session,
    price_row: PricePoint,
    *,
    restatement_reason: str,
    acting_tenant: str,
    actor: PriceActor,
    entity_id: str | None = None,
    now: datetime | None = None,
    **corrected: Any,
) -> PricePoint:
    """As-known vendor restatement (TR-08): close the prior row's ``system_to = now`` then insert a
    corrected version over the SAME valid period + same key with ``restatement_reason`` +
    ``supersedes_id`` (``MARKET.PRICE_CORRECTION`` + its own ORIGIN edge + the DQ gate). The prior
    row's content columns are NEVER mutated — only its ``system_to``. ``price_row`` must already be
    tenant-resolved (via ``resolve_price``)."""
    _resolve_refs(
        session, price_row.instrument_id, price_row.currency_code, acting_tenant=acting_tenant
    )
    _check_field_kwargs(corrected)

    now = now or utcnow()
    before = {"system_to": _json_safe(price_row.system_to)}
    price_row.system_to = now  # CLOSE-FIRST
    session.flush()
    record_price_update(
        session,
        entity=price_row,
        before_value=before,
        after_value={"system_to": _json_safe(price_row.system_to)},
        actor=actor,
        now=now,
    )

    carried = {field: getattr(price_row, field) for field in PRICE_FIELDS}
    corrected_row = PricePoint(
        tenant_id=str(acting_tenant),
        instrument_id=price_row.instrument_id,
        price_date=price_row.price_date,  # carried verbatim (immutable logical key)
        price_type=price_row.price_type,
        currency_code=price_row.currency_code,
        price_source=price_row.price_source,
        valid_from=price_row.valid_from,  # SAME valid period (as-known correction)
        valid_to=price_row.valid_to,
        system_from=now,  # one `now` — equals the prior row's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=price_row.id,
        record_version=price_row.record_version + 1,
        **{**carried, **corrected},
    )
    if entity_id is not None:
        corrected_row.id = entity_id
    session.add(corrected_row)
    session.flush()
    _run_price_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=corrected_row)
    record_price_correction(
        session,
        entity=corrected_row,
        restatement_reason=restatement_reason,
        after_value=_summary(
            corrected_row,
            extra={
                "restatement_reason": restatement_reason,
                "supersedes_id": corrected_row.supersedes_id,
            },
        ),
        actor=actor,
        now=now,
    )
    return corrected_row


def reconstruct_price_as_of(
    session: Session,
    *,
    acting_tenant: str,
    instrument_id: str,
    price_date: date,
    price_type: str,
    currency_code: str,
    price_source: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> PricePoint | None:
    """Bitemporal as-of read: the single price true at ``valid_at`` as-known-at ``known_at``
    (``known_at`` defaults to now -> the current view), or ``None``, for the given logical key.
    Half-open intervals on both axes; the resolver carries the explicit tenant predicate. Single
    captured price only — NO conversion / aggregation / model (those are later calculations)."""
    known = known_at or utcnow()
    return session.execute(
        select(PricePoint).where(
            PricePoint.tenant_id == str(acting_tenant),
            PricePoint.instrument_id == str(instrument_id),
            PricePoint.price_date == price_date,
            PricePoint.price_type == price_type,
            PricePoint.currency_code == currency_code,
            PricePoint.price_source == price_source,
            PricePoint.valid_from <= valid_at,
            or_(PricePoint.valid_to.is_(None), PricePoint.valid_to > valid_at),
            PricePoint.system_from <= known,
            or_(PricePoint.system_to.is_(None), PricePoint.system_to > known),
        )
    ).scalar_one_or_none()
