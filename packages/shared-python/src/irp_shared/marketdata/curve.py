"""Curve binder + governed-write provenance (P2-5, ENT-021/023) — the FR captured-curve protocol.

``curve`` (FR header) + ``curve_point`` (IA append-only version-pinned nodes) are **captured vendor
yield/spread curve market data** (OD-P2-5-*), reusing the P2-2 ``fx_rate`` / P2-4 ``price_point`` FR
protocol + the P2-1 ``dataset_snapshot``->``dataset_snapshot_component`` header+children
split. The header key is ``(curve_type, currency_code, reference_key, curve_date,
curve_source)``; the per-tenor values live in the version-pinned nodes. A curve **re-versions as a
whole** (the vendor restates the entire curve), so capture/supersede/correct each write the header +
its FULL node set as ONE governed unit:

- ``capture_curve`` — the first open curve for a key (header + nodes; ``MARKET.CURVE_CREATE``).
- ``supersede_curve`` — a new *valid-time* curve for the SAME key: close the head's ``valid_to``
  (``MARKET.CURVE_UPDATE``), then insert a new header version + node set (``MARKET.CURVE_CREATE``).
- ``correct_curve`` — an as-known *system-time* vendor restatement (TR-08): close the prior header's
  ``system_to`` (``MARKET.CURVE_UPDATE``), then insert a corrected version over the SAME valid
  period + same key + a fresh node set (``MARKET.CURVE_CORRECTION``).
- ``reconstruct_curve_as_of`` — the bitemporal header read (+ ``list_curve_points`` for its nodes).

Invariants: ONE ``now = utcnow()`` per op; CLOSE-FIRST ordering; a prior header version's CONTENT is
NEVER mutated (only ``valid_to``/``system_to``) and its nodes are immutable (append-only); the
curve_point ``tenant_id`` stamped from the header. **ONE ``MARKET.CURVE_*`` event per curve**
(header-grained — the nodes fold into the header write). Currency via the hybrid-aware
``resolve_currency``. The ``curve_type`` <-> ``reference_key`` invariant + the ``curve_type``/
``value_type`` vocabs + tenor pattern are binder-side ``CurveValueError`` (-> 422) BEFORE write.
The **DQ gate** (required-field NOT_NULL + tenor-validity + value-conditional RANGE — DF
strictly-positive, ZERO_RATE/PAR_RATE/SPREAD in [-1,1]) is fail-closed + co-transactional; the
``(params, dataset)`` Protocol is UNTOUCHED. **Captured, never computed:** NO interpolation,
bootstrapping, curve construction, discounting, duration, key-rate, pricing/valuation/return/factor/
risk; ``interpolation_method`` is an inert label. A VENDOR (``VENDOR_CURVE``) ``data_source`` ORIGIN
edge per NEW curve version (header-targeted). No mid-call commit (CTRL-032). ``audit/service.py``
is FROZEN; **no emit on read**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL, RULE_TYPE_RANGE
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.marketdata.models import (
    CURVE_TYPES,
    CURVE_VALUE_TYPES,
    RATE_CURVE_TYPES,
    REFERENCE_KEY_NONE,
    SIGNED_VALUE_TYPES,
    VALUE_TYPE_DISCOUNT_FACTOR,
    Curve,
    CurvePoint,
)
from irp_shared.reference.service import resolve_currency

# --- audit / provenance constants (the MARKET.* family at EVT-200; the VENDOR_FX/VENDOR_PRICE
# precedent) ---
MARKET_CURVE_CREATE_EVENT = "MARKET.CURVE_CREATE"
MARKET_CURVE_UPDATE_EVENT = "MARKET.CURVE_UPDATE"
MARKET_CURVE_CORRECTION_EVENT = "MARKET.CURVE_CORRECTION"
VENDOR_CURVE_SOURCE_TYPE = "VENDOR_CURVE"
VENDOR_CURVE_SOURCE_CODE = "VENDOR_CURVE"
VENDOR_CURVE_SOURCE_NAME = "Vendor yield/spread curves"
ENTITY_CURVE = "curve"
SOURCE_MODULE = "marketdata"

#: Required header fields for a governed capture (the required-field DQ gate universe).
REQUIRED_CURVE_FIELDS = (
    "curve_type",
    "currency_code",
    "reference_key",
    "curve_date",
    "curve_source",
)
#: Required node fields.
REQUIRED_NODE_FIELDS = ("tenor_days", "value_type", "point_value")

#: Per-tenant governed DQ rule codes (resolve-or-register; the P2-4 ``price`` pattern).
_REQUIRED_RULE_CODE = "curve.required_fields"
_TENOR_RULE_CODE = "curve.tenor_positive"
_DF_RULE_CODE = "curve.discount_factor_positive"
_RATE_RULE_CODE = "curve.rate_spread_sanity"

#: Canonical tenor-label pattern: {N}{D|W|M|Y} (e.g. "1M", "30Y"). Capture only — NO day-count math.
_TENOR_LABEL_RE = re.compile(r"^[1-9][0-9]*[DWMY]$")


@dataclass(frozen=True)
class CurveNode:
    """One captured tenor node supplied to the binder. ``entity_id`` is the deterministic-injection
    seam (default-None => prod unchanged)."""

    tenor_label: str
    tenor_days: int
    value_type: str
    point_value: Decimal
    entity_id: str | None = None


@dataclass(frozen=True)
class CurveActor:
    """Actor/correlation context threaded into every curve audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class CurveValueError(Exception):
    """Raised for an out-of-vocab ``curve_type``/``value_type``, a bad ``tenor_label``, empty node
    set, or a ``curve_type`` <-> ``reference_key`` invariant breach — an error caught BEFORE any
    write (fail-closed; maps to 422)."""


class CurveNotVisible(Exception):
    """Raised when a ``curve`` id is not visible in the acting tenant scope (cross-tenant)."""

    def __init__(self, curve_id: str) -> None:
        super().__init__(f"curve {curve_id} is not visible in the current tenant context")
        self.curve_id = str(curve_id)


class NoCurrentCurve(Exception):
    """Raised when a supersede is requested but the logical key has no open head."""

    def __init__(
        self, curve_type: str, currency: str, reference_key: str, curve_date: date, source: str
    ) -> None:
        super().__init__(
            f"curve {curve_type}/{currency}/{reference_key}/{source} for {curve_date} "
            f"has no current (open) version"
        )
        self.curve_type, self.currency_code = curve_type, currency
        self.reference_key, self.curve_date, self.curve_source = reference_key, curve_date, source


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _summary(row: Curve, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A DC-2 curve-header-summary dict (metadata only) for the audit after_value (never the full
    node payload — vendor-licensed)."""
    data: dict[str, Any] = {
        "curve_type": row.curve_type,
        "currency_code": row.currency_code,
        "reference_key": row.reference_key,
        "curve_date": _json_safe(row.curve_date),
        "curve_source": row.curve_source,
        "interpolation_method": row.interpolation_method,
        "point_count": row.point_count,
        "valid_from": _json_safe(row.valid_from),
        "valid_to": _json_safe(row.valid_to),
        "system_from": _json_safe(row.system_from),
    }
    if extra:
        data.update(extra)
    return data


# --- binder-side value checks (CurveValueError -> 422, BEFORE any write; NOT the DQ Protocol) ---


def _validate_curve_type(curve_type: str) -> None:
    if curve_type not in CURVE_TYPES:
        raise CurveValueError(f"curve_type {curve_type!r} not in {CURVE_TYPES}")


def _validate_reference_key(curve_type: str, reference_key: str) -> None:
    """The curve_type <-> reference_key invariant (OD-P2-5-K): rate curves require the sentinel;
    CREDIT_SPREAD requires a non-sentinel, non-empty label. Keeps the 6-tuple key unambiguous."""
    if curve_type in RATE_CURVE_TYPES:
        if reference_key != REFERENCE_KEY_NONE:
            raise CurveValueError(
                f"{curve_type} curve requires reference_key == {REFERENCE_KEY_NONE!r} "
                f"(got {reference_key!r})"
            )
    else:  # CREDIT_SPREAD
        if not reference_key or reference_key == REFERENCE_KEY_NONE:
            raise CurveValueError(
                f"CREDIT_SPREAD requires a non-{REFERENCE_KEY_NONE!r}, non-empty reference_key"
            )


def _validate_nodes(nodes: list[CurveNode]) -> None:
    if not nodes:
        raise CurveValueError("a curve must have at least one curve_point node")
    for node in nodes:
        if node.value_type not in CURVE_VALUE_TYPES:
            raise CurveValueError(f"value_type {node.value_type!r} not in {CURVE_VALUE_TYPES}")
        if not isinstance(node.tenor_days, int) or node.tenor_days <= 0:
            raise CurveValueError(f"tenor_days must be a positive int (got {node.tenor_days!r})")
        if not _TENOR_LABEL_RE.match(node.tenor_label or ""):
            raise CurveValueError(f"tenor_label {node.tenor_label!r} not of form {{N}}{{D|W|M|Y}}")


def _resolve_refs(session: Session, currency_code: str, *, acting_tenant: str) -> None:
    """Validate currency (hybrid-aware own OR SYSTEM -> CurrencyNotVisible) — fails closed BEFORE
    any write. (No instrument FK — a curve is keyed by type/currency/reference_key.)"""
    resolve_currency(session, currency_code, acting_tenant=acting_tenant)


def _ensure_rule(
    session: Session,
    *,
    tenant_id: str,
    actor: CurveActor,
    code: str,
    name: str,
    rule_type: str,
    params: dict[str, Any],
) -> DataQualityRule:
    """Resolve-or-register a per-tenant governed DQ rule (audited; the P2-4 pattern)."""
    rule = session.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == str(tenant_id),
            DataQualityRule.code == code,
        )
    ).scalar_one_or_none()
    if rule is not None:
        return rule
    return register_dq_rule(
        session,
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        rule_type=rule_type,
        actor_id=actor.actor_id,
        params=params,
        target_entity_type=ENTITY_CURVE,
        severity=SEVERITY_ERROR,
        actor_type=actor.actor_type,
    )


def _run_curve_dq_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: CurveActor,
    header: Curve,
    nodes: list[CurveNode],
) -> None:
    """Fail-closed DQ gate (co-transactional; ``DATA.VALIDATE``): (1) required-field NOT_NULL
    (header + each node); (2) tenor validity ``tenor_days > 0``; (3) value-type-conditional RANGE,
    realized as TWO RANGE registrations over ``value_type``-filtered sub-datasets (the shipped
    single-column ``evaluate_range`` cannot branch on value_type, so (params,dataset) Protocol is
    UNTOUCHED): DISCOUNT_FACTOR strictly-positive; ZERO_RATE/PAR_RATE/SPREAD in [-1, 1] (negatives
    allowed). A failure -> ``DataQualityError`` -> the caller's whole unit rolls back (CTRL-032).
    Completeness-by-required-tenor-set + staleness are DEFERRED (OQ-P2-5-8)."""
    header_missing = any(getattr(header, f) is None for f in REQUIRED_CURVE_FIELDS)
    node_missing = any(getattr(n, f) is None for n in nodes for f in REQUIRED_NODE_FIELDS)
    required_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_REQUIRED_RULE_CODE,
        name="Curve required fields present",
        rule_type=RULE_TYPE_NOT_NULL,
        params={"column": "present"},
    )
    run_quality_check(
        session,
        rule=required_rule,
        dataset=[{"present": None if (header_missing or node_missing) else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_CURVE,
        target_entity_id=header.id,
        actor_type=actor.actor_type,
    )

    tenor_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_TENOR_RULE_CODE,
        name="Curve tenor_days strictly positive",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "tenor_days", "min": 0, "min_inclusive": False},
    )
    run_quality_check(
        session,
        rule=tenor_rule,
        dataset=[{"tenor_days": n.tenor_days} for n in nodes],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_CURVE,
        target_entity_id=header.id,
        actor_type=actor.actor_type,
    )

    # Value-type-conditional RANGE — two rules over value_type-partitioned sub-datasets.
    df_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_DF_RULE_CODE,
        name="Curve discount factor strictly positive",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "point_value", "min": 0, "min_inclusive": False},
    )
    run_quality_check(
        session,
        rule=df_rule,
        dataset=[
            {"point_value": n.point_value}
            for n in nodes
            if n.value_type == VALUE_TYPE_DISCOUNT_FACTOR
        ],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_CURVE,
        target_entity_id=header.id,
        actor_type=actor.actor_type,
    )
    rate_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_RATE_RULE_CODE,
        name="Curve rate/spread sanity band",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "point_value", "min": -1, "max": 1},
    )
    run_quality_check(
        session,
        rule=rate_rule,
        dataset=[
            {"point_value": n.point_value} for n in nodes if n.value_type in SIGNED_VALUE_TYPES
        ],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_CURVE,
        target_entity_id=header.id,
        actor_type=actor.actor_type,
    )


def _current_open(
    session: Session,
    *,
    acting_tenant: str,
    curve_type: str,
    currency_code: str,
    reference_key: str,
    curve_date: date,
    curve_source: str,
) -> Curve | None:
    """The single header version OPEN ON BOTH axes for a logical key — the bitemporal current head —
    or ``None``. Tenant-predicated."""
    return session.execute(
        select(Curve).where(
            Curve.tenant_id == str(acting_tenant),
            Curve.curve_type == curve_type,
            Curve.currency_code == currency_code,
            Curve.reference_key == reference_key,
            Curve.curve_date == curve_date,
            Curve.curve_source == curve_source,
            Curve.valid_to.is_(None),
            Curve.system_to.is_(None),
        )
    ).scalar_one_or_none()


def resolve_curve(session: Session, curve_id: str, *, acting_tenant: str) -> Curve:
    """Resolve a ``curve`` header version by id with an EXPLICIT ``tenant_id == acting_tenant``
    predicate (fail-closed). Raises :class:`CurveNotVisible` on a hidden id."""
    row = session.execute(
        select(Curve).where(Curve.id == str(curve_id), Curve.tenant_id == str(acting_tenant))
    ).scalar_one_or_none()
    if row is None:
        raise CurveNotVisible(str(curve_id))
    return row


def list_curve_points(session: Session, curve_id: str, *, acting_tenant: str) -> list[CurvePoint]:
    """The immutable node set pinned to a ``curve`` header version (ordered by tenor_days), under an
    explicit tenant predicate."""
    return list(
        session.execute(
            select(CurvePoint)
            .where(
                CurvePoint.curve_id == str(curve_id),
                CurvePoint.tenant_id == str(acting_tenant),
            )
            .order_by(CurvePoint.value_type, CurvePoint.tenor_days)
        )
        .scalars()
        .all()
    )


# --- provenance: VENDOR data_source + the caller-side MARKET.CURVE_* emitters ---


def ensure_vendor_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's shared ``VENDOR_CURVE`` ``data_source``
    (governed provenance root for captured vendor curves; the ``VENDOR_PRICE`` precedent). DISTINCT
    from the row-level ``curve_source`` key label. Module-local to ``marketdata/curve.py``."""
    existing = session.execute(
        select(DataSource).where(
            DataSource.tenant_id == str(tenant_id),
            DataSource.code == VENDOR_CURVE_SOURCE_CODE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return register_data_source(
        session,
        tenant_id=str(tenant_id),
        code=VENDOR_CURVE_SOURCE_CODE,
        name=VENDOR_CURVE_SOURCE_NAME,
        source_type=VENDOR_CURVE_SOURCE_TYPE,
        actor_id=actor_id,
    )


def _origin_edge(session: Session, *, entity: Curve, actor: CurveActor) -> None:
    """Root one ORIGIN lineage edge (VENDOR_CURVE source) for a NEW physical curve HEADER version
    (the nodes are version-pinned children, covered transitively)."""
    source = ensure_vendor_source(session, entity.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_CURVE,
        target_entity_id=entity.id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    entity: Curve,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: CurveActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit a MARKET.CURVE_* event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=entity.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_CURVE,
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


def record_curve_create(
    session: Session,
    *,
    entity: Curve,
    after_value: dict[str, Any],
    actor: CurveActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``MARKET.CURVE_CREATE`` for a captured new curve version."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=MARKET_CURVE_CREATE_EVENT,
        action="create",
        after_value=after_value,
        actor=actor,
        now=now,
    )


def record_curve_update(
    session: Session,
    *,
    entity: Curve,
    before_value: dict[str, Any],
    after_value: dict[str, Any],
    actor: CurveActor,
    now: datetime | None = None,
) -> None:
    """Emit ``MARKET.CURVE_UPDATE`` for a prior-head close-out — NO new lineage edge."""
    _emit(
        session,
        entity=entity,
        event_type=MARKET_CURVE_UPDATE_EVENT,
        action="update",
        before_value=before_value,
        after_value=after_value,
        actor=actor,
        now=now,
    )


def record_curve_correction(
    session: Session,
    *,
    entity: Curve,
    restatement_reason: str,
    after_value: dict[str, Any],
    actor: CurveActor,
    now: datetime | None = None,
) -> None:
    """Root one ORIGIN edge + emit ``MARKET.CURVE_CORRECTION`` for an as-known restatement."""
    _origin_edge(session, entity=entity, actor=actor)
    _emit(
        session,
        entity=entity,
        event_type=MARKET_CURVE_CORRECTION_EVENT,
        action="correct",
        after_value=after_value,
        actor=actor,
        justification=restatement_reason,
        now=now,
    )


# --- the governed binder (capture / supersede / correct / reconstruct) ---


def _write_nodes(session: Session, *, header: Curve, nodes: list[CurveNode], now: datetime) -> None:
    """Insert the immutable version-pinned curve_point set for a header version (tenant_id
    server-stamped from the header)."""
    for node in nodes:
        point = CurvePoint(
            tenant_id=header.tenant_id,
            curve_id=header.id,
            tenor_label=node.tenor_label,
            tenor_days=node.tenor_days,
            value_type=node.value_type,
            point_value=node.point_value,
            system_from=now,
        )
        if node.entity_id is not None:
            point.id = node.entity_id
        session.add(point)
    session.flush()


def capture_curve(
    session: Session,
    *,
    curve_type: str,
    currency_code: str,
    curve_date: date,
    curve_source: str,
    nodes: list[CurveNode],
    acting_tenant: str,
    actor: CurveActor,
    reference_key: str = REFERENCE_KEY_NONE,
    interpolation_method: str | None = None,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Curve:
    """Capture the first open curve for a logical key (header + its full node set as ONE governed
    unit: VENDOR-source ORIGIN lineage + ``MARKET.CURVE_CREATE`` + the DQ gate). The currency is
    resolved hybrid-aware; ``curve_type``/``reference_key``/``value_type``/tenor validated BEFORE
    any write. ``nodes`` are captured verbatim (never computed). ``entity_id``/``now`` are the
    deterministic-injection seam."""
    _validate_curve_type(curve_type)
    _validate_reference_key(curve_type, reference_key)
    _validate_nodes(nodes)
    _resolve_refs(session, currency_code, acting_tenant=acting_tenant)
    now = now or utcnow()
    header = Curve(
        tenant_id=str(acting_tenant),
        curve_type=curve_type,
        currency_code=currency_code,
        reference_key=reference_key,
        curve_date=curve_date,  # immutable logical-key component (NOT the valid_from axis)
        curve_source=curve_source,
        interpolation_method=interpolation_method,  # inert metadata (no engine)
        point_count=len(nodes),
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        record_version=1,
    )
    if entity_id is not None:
        header.id = entity_id
    session.add(header)
    session.flush()
    _write_nodes(session, header=header, nodes=nodes, now=now)
    _run_curve_dq_gate(
        session, acting_tenant=acting_tenant, actor=actor, header=header, nodes=nodes
    )
    record_curve_create(session, entity=header, after_value=_summary(header), actor=actor, now=now)
    return header


def supersede_curve(
    session: Session,
    *,
    curve_type: str,
    currency_code: str,
    curve_date: date,
    curve_source: str,
    nodes: list[CurveNode],
    acting_tenant: str,
    actor: CurveActor,
    effective_at: datetime,
    reference_key: str = REFERENCE_KEY_NONE,
    interpolation_method: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Curve:
    """Effective-dated (valid-time) re-capture for the SAME key: close the head's ``valid_to``
    (``MARKET.CURVE_UPDATE``), then insert a new header version + a FRESH node set
    (``MARKET.CURVE_CREATE`` + its own ORIGIN edge + the DQ gate). The head is sourced via the
    tenant-predicated ``_current_open`` (never a caller-supplied id)."""
    _validate_curve_type(curve_type)
    _validate_reference_key(curve_type, reference_key)
    _validate_nodes(nodes)
    _resolve_refs(session, currency_code, acting_tenant=acting_tenant)
    prior = _current_open(
        session,
        acting_tenant=acting_tenant,
        curve_type=curve_type,
        currency_code=currency_code,
        reference_key=reference_key,
        curve_date=curve_date,
        curve_source=curve_source,
    )
    if prior is None:
        raise NoCurrentCurve(curve_type, currency_code, reference_key, curve_date, curve_source)

    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST
    session.flush()
    record_curve_update(
        session,
        entity=prior,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    new = Curve(
        tenant_id=str(acting_tenant),
        curve_type=prior.curve_type,
        currency_code=prior.currency_code,
        reference_key=prior.reference_key,
        curve_date=prior.curve_date,  # carried verbatim (immutable logical key)
        curve_source=prior.curve_source,
        interpolation_method=interpolation_method,
        point_count=len(nodes),
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
    )
    if entity_id is not None:
        new.id = entity_id
    session.add(new)
    session.flush()
    _write_nodes(session, header=new, nodes=nodes, now=now)
    _run_curve_dq_gate(session, acting_tenant=acting_tenant, actor=actor, header=new, nodes=nodes)
    record_curve_create(session, entity=new, after_value=_summary(new), actor=actor, now=now)
    return new


def correct_curve(
    session: Session,
    curve_header: Curve,
    *,
    restatement_reason: str,
    nodes: list[CurveNode],
    acting_tenant: str,
    actor: CurveActor,
    interpolation_method: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Curve:
    """As-known restatement (TR-08): close the prior header's ``system_to = now`` then insert a
    corrected header version over the SAME valid period + same key + a FRESH node set
    (``MARKET.CURVE_CORRECTION`` + its own ORIGIN edge + the DQ gate). The prior header's content
    columns are NEVER mutated — only its ``system_to`` — and its nodes immutable. ``curve_header``
    must already be tenant-resolved (via ``resolve_curve``)."""
    _validate_nodes(nodes)
    _resolve_refs(session, curve_header.currency_code, acting_tenant=acting_tenant)

    now = now or utcnow()
    before = {"system_to": _json_safe(curve_header.system_to)}
    curve_header.system_to = now  # CLOSE-FIRST
    session.flush()
    record_curve_update(
        session,
        entity=curve_header,
        before_value=before,
        after_value={"system_to": _json_safe(curve_header.system_to)},
        actor=actor,
        now=now,
    )

    corrected = Curve(
        tenant_id=str(acting_tenant),
        curve_type=curve_header.curve_type,
        currency_code=curve_header.currency_code,
        reference_key=curve_header.reference_key,
        curve_date=curve_header.curve_date,  # carried verbatim (immutable logical key)
        curve_source=curve_header.curve_source,
        interpolation_method=interpolation_method,
        point_count=len(nodes),
        valid_from=curve_header.valid_from,  # SAME valid period (as-known correction)
        valid_to=curve_header.valid_to,
        system_from=now,  # one `now` — equals the prior header's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=curve_header.id,
        record_version=curve_header.record_version + 1,
    )
    if entity_id is not None:
        corrected.id = entity_id
    session.add(corrected)
    session.flush()
    _write_nodes(session, header=corrected, nodes=nodes, now=now)
    _run_curve_dq_gate(
        session, acting_tenant=acting_tenant, actor=actor, header=corrected, nodes=nodes
    )
    record_curve_correction(
        session,
        entity=corrected,
        restatement_reason=restatement_reason,
        after_value=_summary(
            corrected,
            extra={
                "restatement_reason": restatement_reason,
                "supersedes_id": corrected.supersedes_id,
            },
        ),
        actor=actor,
        now=now,
    )
    return corrected


def reconstruct_curve_as_of(
    session: Session,
    *,
    acting_tenant: str,
    curve_type: str,
    currency_code: str,
    curve_date: date,
    curve_source: str,
    valid_at: datetime,
    reference_key: str = REFERENCE_KEY_NONE,
    known_at: datetime | None = None,
) -> Curve | None:
    """Bitemporal as-of read: the single curve HEADER true at ``valid_at`` as-known-at ``known_at``
    (``known_at`` defaults to now -> the current view), or ``None``, for the given logical key. The
    caller reads its pinned nodes via ``list_curve_points(header.id)``. Single captured curve
    only — NO interpolation / construction / model (those are later calculations)."""
    known = known_at or utcnow()
    return session.execute(
        select(Curve).where(
            Curve.tenant_id == str(acting_tenant),
            Curve.curve_type == curve_type,
            Curve.currency_code == currency_code,
            Curve.reference_key == reference_key,
            Curve.curve_date == curve_date,
            Curve.curve_source == curve_source,
            Curve.valid_from <= valid_at,
            or_(Curve.valid_to.is_(None), Curve.valid_to > valid_at),
            Curve.system_from <= known,
            or_(Curve.system_to.is_(None), Curve.system_to > known),
        )
    ).scalar_one_or_none()
