"""Proxy-mapping binder + governed-write provenance (PA-0, ENT-019) — captured private→public
factor proxy INPUTS.

``proxy_mapping`` (FR bitemporal) records that a PRIVATE instrument's risk loads on a public
``factor`` with a signed ``weight`` — the FIRST private-asset foundation (the differentiation-thesis
destination §2.1). A proxy weight is a **captured** value (``mapping_method``), **NEVER computed in
this binder** — it is an INPUT, not a governed derived number. A ``MANUAL`` weight is a pure
governance judgment call. A ``REGRESSION`` weight (PA-3) is the deliberate, analyst-mediated
PROMOTION of a governed ``proxy_weight_estimate_result`` run's output: still captured verbatim here,
but it MUST cite the estimation run (``source_calculation_run_id``) as its evidence — the estimate
itself is the governed number (snapshot/run/model-bound), and this capture step is where a human
turns a reviewed model output into a live proxy weight (OD-PA-3-A/E).

The FR series re-versions over time (a proxy weight is revisited) →
``MARKET.PROXY_MAPPING_CREATE``/``_UPDATE``/``_CORRECTION`` at the EVT-200 block (the
``factor_return`` per-op grain: capture=1; supersede=2 = UPDATE close-out + CREATE; correct=2 =
UPDATE + CORRECTION). One OPEN row per ``(private_instrument_id, factor_id)`` — a MULTI-row blend
across factors per instrument is normal, and the weights are NOT constrained to sum to 1 (a partial
proxy, the residual left as unmodeled private risk, is a legitimate recorded choice — OD-PA-0-D).

Entitlement reuses ``marketdata.view``/``.ingest`` (NO mint); lineage is a ``MANUAL_PROXY`` ORIGIN
(the ``VENDOR_FACTOR``/``VENDOR_BENCHMARK`` sibling — a non-vendor manual-judgment source ROW, not a
new lineage KIND). BOTH FK targets (``instrument`` + ``factor``) are re-resolved tenant-filtered
BEFORE any write (fail-closed cross-tenant). Invariants: ONE ``now = utcnow()`` per op; CLOSE-FIRST
ordering on a re-version; a prior version's CONTENT is NEVER mutated (only the temporal axes);
a **finiteness guard** (``weight`` is a finite Decimal — rejects NaN/±Inf BEFORE write) +
``mapping_method`` vocab are binder-side :class:`ProxyMappingValueError` (→ 422) BEFORE any write.
The **DQ gate** (required-field NOT_NULL — an "inputs present" governance leg; NO economic RANGE, a
factor loading has no natural bound, OD-PA-0-D) is fail-closed + co-transactional. No mid-call
commit (CTRL-032). ``audit/service.py`` is FROZEN; **no emit on read**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CORRECT, ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.payload import json_safe as _json_safe
from irp_shared.audit.service import record_event
from irp_shared.db.bitemporal import assert_supersede_effective_at
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.marketdata.models import (
    LOADING_FACTOR_FAMILIES,
    MAPPING_METHOD_MANUAL,
    MAPPING_METHOD_REGRESSION,
    PROXY_MAPPING_METHODS,
    Factor,
    ProxyMapping,
)
from irp_shared.reference.guards import assert_instrument_in_tenant

# --- audit / provenance constants (the MARKET.* EVT-200 family; the factor_return precedent) ---
MARKET_PROXY_MAPPING_CREATE_EVENT = "MARKET.PROXY_MAPPING_CREATE"
MARKET_PROXY_MAPPING_UPDATE_EVENT = "MARKET.PROXY_MAPPING_UPDATE"
MARKET_PROXY_MAPPING_CORRECTION_EVENT = "MARKET.PROXY_MAPPING_CORRECTION"
#: A NON-vendor manual-judgment provenance root (a new data_source ROW, not a new lineage KIND —
#: the VENDOR_FACTOR/VENDOR_BENCHMARK precedent reused for a captured governance judgment call).
MANUAL_PROXY_SOURCE_TYPE = "MANUAL_PROXY"
MANUAL_PROXY_SOURCE_CODE = "MANUAL_PROXY"
MANUAL_PROXY_SOURCE_NAME = "Manual private-asset proxy mapping"
ENTITY_PROXY_MAPPING = "proxy_mapping"
SOURCE_MODULE = "marketdata"

#: Per-tenant governed DQ rule code (resolve-or-register; the factor_return pattern).
_REQUIRED_RULE_CODE = "proxy_mapping.required_fields"


@dataclass(frozen=True)
class ProxyMappingActor:
    """Actor/correlation context threaded into every proxy-mapping audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class ProxyMappingValueError(Exception):
    """Raised for an out-of-vocab ``mapping_method`` or a non-finite ``weight`` — caught BEFORE any
    write (fail-closed; maps to 422)."""


class ProxyMappingNotVisible(Exception):
    """Raised when a ``proxy_mapping`` id is not visible in the acting tenant scope."""

    def __init__(self, proxy_mapping_id: str) -> None:
        super().__init__(
            f"proxy_mapping {proxy_mapping_id} is not visible in the current tenant context"
        )
        self.proxy_mapping_id = str(proxy_mapping_id)


class NoCurrentProxyMapping(Exception):
    """Raised when a supersede/correct is requested but the (private_instrument_id, factor_id) has
    no open current head."""

    def __init__(self, private_instrument_id: str, factor_id: str) -> None:
        super().__init__(
            f"instrument {private_instrument_id} has no current (open) proxy weight for factor "
            f"{factor_id}"
        )
        self.private_instrument_id = str(private_instrument_id)
        self.factor_id = str(factor_id)


def _validate_mapping_method(mapping_method: str) -> None:
    if mapping_method not in PROXY_MAPPING_METHODS:
        raise ProxyMappingValueError(
            f"mapping_method {mapping_method!r} not in {PROXY_MAPPING_METHODS}"
        )


def _validate_promotion(mapping_method: str, source_calculation_run_id: str | None) -> None:
    """The method↔citation blur guard, fail-closed BOTH directions (OD-PA-3-E): a ``REGRESSION``
    capture MUST carry a ``source_calculation_run_id``; a ``MANUAL`` capture must NOT. The run-TYPE
    resolution (a tenant-visible COMPLETED ``PROXY_WEIGHT_ESTIMATE`` run) lives ONE LAYER UP in
    ``risk.promote_proxy_weight_estimate`` — ``marketdata`` imports no ``calc``/``risk`` (the
    captured-INPUT fence). The FK to ``calculation_run`` still guarantees a real run here."""
    if mapping_method == MAPPING_METHOD_REGRESSION:
        if source_calculation_run_id is None:
            raise ProxyMappingValueError(
                "a REGRESSION-method proxy weight must cite its estimation run "
                "(source_calculation_run_id) — refused"
            )
    elif source_calculation_run_id is not None:
        raise ProxyMappingValueError(
            f"source_calculation_run_id is only valid with mapping_method="
            f"{MAPPING_METHOD_REGRESSION!r} (got {mapping_method!r}) — refused"
        )


def _reject_regression_correction(mapping_method: str) -> None:
    """The CORRECTION path cannot mint a ``REGRESSION`` weight in v1 (it carries no
    ``source_calculation_run_id``, so it would drop the estimation-run citation — the OD-PA-3-E
    invariant; a recorded limitation). A REGRESSION weight is REVISED by re-promoting
    (``risk.promote_proxy_weight_estimate`` → a citation-carrying supersede), and a typo'd one is
    corrected by re-promoting the right value from its run."""
    if mapping_method == MAPPING_METHOD_REGRESSION:
        raise ProxyMappingValueError(
            "correct cannot mint a REGRESSION-method proxy weight (it would carry no "
            "estimation-run citation) — re-promote via risk.promote_proxy_weight_estimate; refused"
        )


def _validate_weight(weight: Decimal) -> None:
    """Finiteness guard: reject NaN / ±Infinity BEFORE any write (there is no economic RANGE on a
    factor loading — OD-PA-0-D)."""
    if not isinstance(weight, Decimal) or not weight.is_finite():
        raise ProxyMappingValueError(f"weight must be a finite Decimal (got {weight!r})")


# --- governed DQ gate (required-field NOT_NULL only; the factor_return pattern, no RANGE) ---


def _ensure_required_rule(
    session: Session, *, tenant_id: str, actor: ProxyMappingActor
) -> DataQualityRule:
    """Resolve-or-register the per-tenant required-fields DQ rule (audited; the factor pattern —
    the single-column ``(params, dataset)`` Protocol UNTOUCHED)."""
    # Race-safe (MD-H1 review fold): two concurrent FIRST callers both SELECT-miss then
    # INSERT the same key; the loser re-resolves the peer instead of aborting the unit.
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataQualityRule).where(
                DataQualityRule.tenant_id == str(tenant_id),
                DataQualityRule.code == _REQUIRED_RULE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_dq_rule(
            session,
            tenant_id=str(tenant_id),
            code=_REQUIRED_RULE_CODE,
            name="proxy_mapping required fields present",
            rule_type=RULE_TYPE_NOT_NULL,
            actor_id=actor.actor_id,
            params={"column": "present"},
            target_entity_type=ENTITY_PROXY_MAPPING,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_dq_gate(
    session: Session, *, acting_tenant: str, actor: ProxyMappingActor, row: ProxyMapping
) -> None:
    """Fail-closed DQ gate (co-transactional; ``DATA.VALIDATE``): required-field NOT_NULL
    (private_instrument_id / factor_id / weight / mapping_method present). Finiteness + vocab are
    the binder guards (BEFORE this gate). A failure → ``DataQualityError`` → the caller's whole unit
    rolls back (CTRL-032). NO economic RANGE — a factor loading has no natural sanity bound
    (OD-PA-0-D)."""
    missing = any(
        getattr(row, f) is None
        for f in ("private_instrument_id", "factor_id", "weight", "mapping_method")
    )
    rule = _ensure_required_rule(session, tenant_id=acting_tenant, actor=actor)
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_PROXY_MAPPING,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


# --- provenance (MANUAL_PROXY ORIGIN lineage) + audit emit ---


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's ``MANUAL_PROXY`` ``data_source``
    (governed provenance root; the ``VENDOR_FACTOR`` precedent, non-vendor variant)."""
    # Race-safe (MD-H1 review fold): two concurrent FIRST callers both SELECT-miss then
    # INSERT the same key; the loser re-resolves the peer instead of aborting the unit.
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == str(tenant_id),
                DataSource.code == MANUAL_PROXY_SOURCE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=str(tenant_id),
            code=MANUAL_PROXY_SOURCE_CODE,
            name=MANUAL_PROXY_SOURCE_NAME,
            source_type=MANUAL_PROXY_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def _origin_edge(
    session: Session, *, tenant_id: str, entity_id: str, actor: ProxyMappingActor
) -> None:
    """Root one ORIGIN lineage edge (MANUAL_PROXY source) targeting a NEW proxy_mapping version."""
    source = ensure_manual_source(session, tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_PROXY_MAPPING,
        target_entity_id=entity_id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    tenant_id: str,
    entity_id: str,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: ProxyMappingActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit one audit event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_PROXY_MAPPING,
        entity_id=entity_id,
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


def _summary(row: ProxyMapping) -> dict[str, Any]:
    """A DC-2 proxy-mapping-summary dict (metadata only — provenance, never bulk data)."""
    return {
        "private_instrument_id": _json_safe(row.private_instrument_id),
        "factor_id": _json_safe(row.factor_id),
        "mapping_method": row.mapping_method,
        "record_version": row.record_version,
    }


# --- resolution ---


def resolve_proxy_mapping(
    session: Session, proxy_mapping_id: str, *, acting_tenant: str
) -> ProxyMapping:
    """Resolve a ``proxy_mapping`` version by id with an EXPLICIT ``tenant_id == acting_tenant``
    predicate (fail-closed). Raises :class:`ProxyMappingNotVisible` on a hidden id."""
    row = session.execute(
        select(ProxyMapping).where(
            ProxyMapping.id == str(proxy_mapping_id),
            ProxyMapping.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProxyMappingNotVisible(str(proxy_mapping_id))
    return row


def _resolve_instrument_id(session: Session, instrument_id: str, *, acting_tenant: str) -> str:
    """Re-resolve the private instrument under the acting tenant BEFORE its id is stamped into the
    NOT-NULL FK (PG FK checks bypass RLS — the P3-5 finding). Delegates to the shared
    ``reference/guards.py`` predicate (RD-3 OD-B — this was a byte-equivalent hand-rolled twin);
    message normalizes to the guard's own wording."""
    assert_instrument_in_tenant(
        session, instrument_id, acting_tenant=acting_tenant, error=ProxyMappingValueError
    )
    return str(instrument_id)


def _resolve_factor_id(session: Session, factor_id: str, *, acting_tenant: str) -> str:
    """Re-resolve the public factor under the acting tenant BEFORE its id is stamped into the
    NOT-NULL FK (the P3-5 cross-tenant-FK guard); and enforce the v1 CURRENCY-family scope
    (OD-PA-0-H) fail-closed — a non-CURRENCY factor is out of v1 (a style/sector/rate proxy family
    is a recorded v2 extension), so it is refused at capture, not silently accepted (review fold:
    the doc-stated scope is now an enforced gate). Models-only import."""
    row = session.execute(
        select(Factor.id, Factor.factor_family).where(
            Factor.id == str(factor_id),
            Factor.tenant_id == str(acting_tenant),
        )
    ).one_or_none()
    if row is None:
        raise ProxyMappingValueError(
            f"factor {factor_id} is not visible in the acting tenant — refused"
        )
    if row.factor_family not in LOADING_FACTOR_FAMILIES:
        raise ProxyMappingValueError(
            f"factor {factor_id} family {row.factor_family!r} is not an admitted loading family "
            f"(FL-1 widened PA-0's CURRENCY-only gate to {LOADING_FACTOR_FAMILIES}; OTHER/unknown "
            f"stay refused); refused"
        )
    return str(row.id)


def _current_open(
    session: Session, *, acting_tenant: str, private_instrument_id: str, factor_id: str
) -> ProxyMapping | None:
    """The single version OPEN ON BOTH axes for a logical key (the bitemporal current head), or
    ``None``. Tenant-predicated."""
    return session.execute(
        select(ProxyMapping).where(
            ProxyMapping.tenant_id == str(acting_tenant),
            ProxyMapping.private_instrument_id == str(private_instrument_id),
            ProxyMapping.factor_id == str(factor_id),
            ProxyMapping.valid_to.is_(None),
            ProxyMapping.system_to.is_(None),
        )
    ).scalar_one_or_none()


# --- capture / supersede / correct (the FR bitemporal protocol) ---


def capture_proxy_mapping(
    session: Session,
    *,
    private_instrument_id: str,
    factor_id: str,
    weight: Decimal,
    acting_tenant: str,
    actor: ProxyMappingActor,
    mapping_method: str = MAPPING_METHOD_MANUAL,
    source_calculation_run_id: str | None = None,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ProxyMapping:
    """Capture the first open proxy weight for a (private_instrument, factor) as ONE governed unit
    (FR row + MANUAL_PROXY ORIGIN edge + ``MARKET.PROXY_MAPPING_CREATE`` + the DQ gate). The
    mapping_method + finiteness are validated, and BOTH FK targets re-resolved tenant-filtered,
    BEFORE any write; the weight is captured verbatim (NEVER computed). PA-3: a ``REGRESSION``
    capture PROMOTES a governed estimation run — it MUST cite ``source_calculation_run_id`` (a
    tenant-resolved COMPLETED ``PROXY_WEIGHT_ESTIMATE`` run); a ``MANUAL`` capture must NOT."""
    _validate_mapping_method(mapping_method)
    _validate_weight(weight)
    _validate_promotion(mapping_method, source_calculation_run_id)
    resolved_source = (
        str(source_calculation_run_id) if source_calculation_run_id is not None else None
    )
    resolved_instrument = _resolve_instrument_id(
        session, private_instrument_id, acting_tenant=acting_tenant
    )
    resolved_factor = _resolve_factor_id(session, factor_id, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = ProxyMapping(
        tenant_id=str(acting_tenant),
        private_instrument_id=resolved_instrument,
        factor_id=resolved_factor,
        weight=weight,
        mapping_method=mapping_method,
        source_calculation_run_id=resolved_source,
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _run_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=row)
    _origin_edge(session, tenant_id=row.tenant_id, entity_id=row.id, actor=actor)
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_id=row.id,
        event_type=MARKET_PROXY_MAPPING_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_summary(row),
        actor=actor,
        now=now,
    )
    return row


def supersede_proxy_mapping(
    session: Session,
    *,
    private_instrument_id: str,
    factor_id: str,
    weight: Decimal,
    acting_tenant: str,
    actor: ProxyMappingActor,
    effective_at: datetime,
    mapping_method: str = MAPPING_METHOD_MANUAL,
    source_calculation_run_id: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ProxyMapping:
    """Effective-dated (valid-time) re-capture for the SAME key: close the head's ``valid_to``
    (``MARKET.PROXY_MAPPING_UPDATE``), then insert a new version (``MARKET.PROXY_MAPPING_CREATE`` +
    its own ORIGIN edge + the DQ gate). The head is sourced via the tenant-predicated
    ``_current_open`` (never a caller id) — a proxy REVISION, not an append-only fact. PA-3: a
    ``REGRESSION`` supersede is a RE-promotion (the analyst adopts a newer estimate) — it MUST carry
    ``source_calculation_run_id`` and a ``MANUAL`` one must NOT (the same blur guard as capture);
    the run-TYPE gate lives one layer up in ``risk.promote_proxy_weight_estimate``, which is the
    ONLY path that can supply the citation (the HTTP supersede body deliberately has no such
    field)."""
    _validate_mapping_method(mapping_method)
    _validate_promotion(mapping_method, source_calculation_run_id)
    _validate_weight(weight)
    prior = _current_open(
        session,
        acting_tenant=acting_tenant,
        private_instrument_id=private_instrument_id,
        factor_id=factor_id,
    )
    if prior is None:
        raise NoCurrentProxyMapping(private_instrument_id, factor_id)

    assert_supersede_effective_at(prior.valid_from, effective_at, error=ProxyMappingValueError)
    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST (valid-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_id=prior.id,
        event_type=MARKET_PROXY_MAPPING_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    new = ProxyMapping(
        tenant_id=prior.tenant_id,
        private_instrument_id=prior.private_instrument_id,
        factor_id=prior.factor_id,
        weight=weight,
        mapping_method=mapping_method,
        source_calculation_run_id=(
            str(source_calculation_run_id) if source_calculation_run_id is not None else None
        ),
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
    _run_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=new)
    _origin_edge(session, tenant_id=new.tenant_id, entity_id=new.id, actor=actor)
    _emit(
        session,
        tenant_id=new.tenant_id,
        entity_id=new.id,
        event_type=MARKET_PROXY_MAPPING_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_summary(new),
        actor=actor,
        now=now,
    )
    return new


def correct_proxy_mapping(
    session: Session,
    *,
    private_instrument_id: str,
    factor_id: str,
    weight: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: ProxyMappingActor,
    mapping_method: str = MAPPING_METHOD_MANUAL,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ProxyMapping:
    """As-known (system-time) correction for the SAME key: close the head's ``system_to``
    (``MARKET.PROXY_MAPPING_UPDATE``), then insert a corrected version over the SAME valid window
    with ``restatement_reason`` (``MARKET.PROXY_MAPPING_CORRECTION`` + its own ORIGIN edge + the DQ
    gate). A prior version's CONTENT is never mutated (TR-08)."""
    _validate_mapping_method(mapping_method)
    _reject_regression_correction(mapping_method)
    _validate_weight(weight)
    if not restatement_reason:
        raise ProxyMappingValueError("restatement_reason is required for a correction (TR-08)")
    prior = _current_open(
        session,
        acting_tenant=acting_tenant,
        private_instrument_id=private_instrument_id,
        factor_id=factor_id,
    )
    if prior is None:
        raise NoCurrentProxyMapping(private_instrument_id, factor_id)

    now = now or utcnow()
    before = {"system_to": _json_safe(prior.system_to)}
    prior.system_to = now  # CLOSE-FIRST (system-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_id=prior.id,
        event_type=MARKET_PROXY_MAPPING_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"system_to": _json_safe(prior.system_to)},
        actor=actor,
        now=now,
    )

    corrected = ProxyMapping(
        tenant_id=prior.tenant_id,
        private_instrument_id=prior.private_instrument_id,
        factor_id=prior.factor_id,
        weight=weight,
        mapping_method=mapping_method,
        valid_from=prior.valid_from,  # SAME valid window (a knowledge-time restatement)
        valid_to=prior.valid_to,
        system_from=now,
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
    )
    if entity_id is not None:
        corrected.id = entity_id
    session.add(corrected)
    session.flush()
    _run_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=corrected)
    _origin_edge(session, tenant_id=corrected.tenant_id, entity_id=corrected.id, actor=actor)
    _emit(
        session,
        tenant_id=corrected.tenant_id,
        entity_id=corrected.id,
        event_type=MARKET_PROXY_MAPPING_CORRECTION_EVENT,
        action=ACTION_CORRECT,  # the sibling FR-correction convention (not "update")
        # Symmetric old->new weight on the correction event (a single scalar, NOT the bulk payload
        # the DC-2 rule guards — review fold: before carried the old weight; after now the new)
        before_value={"weight": _json_safe(prior.weight)},
        after_value={**_summary(corrected), "weight": _json_safe(corrected.weight)},
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return corrected


# --- reads (both-axes bitemporal reconstruct + current-head list) ---


def reconstruct_proxy_mapping_as_of(
    session: Session,
    *,
    private_instrument_id: str,
    factor_id: str,
    valid_at: datetime,
    known_at: datetime,
    acting_tenant: str,
) -> ProxyMapping | None:
    """The proxy weight for (instrument, factor) true at ``valid_at`` as KNOWN at ``known_at`` — the
    both-axes bitemporal read (the ``factor_return`` reconstruct precedent; PA-1 pinning needs
    it). Tenant-predicated; ``None`` if no version covers both instants."""
    return session.execute(
        select(ProxyMapping).where(
            ProxyMapping.tenant_id == str(acting_tenant),
            ProxyMapping.private_instrument_id == str(private_instrument_id),
            ProxyMapping.factor_id == str(factor_id),
            ProxyMapping.valid_from <= valid_at,
            (ProxyMapping.valid_to.is_(None)) | (ProxyMapping.valid_to > valid_at),
            ProxyMapping.system_from <= known_at,
            (ProxyMapping.system_to.is_(None)) | (ProxyMapping.system_to > known_at),
        )
        # No order_by: the bitemporal non-overlap invariant guarantees <= 1 covering version
        # (scalar_one_or_none raises on >1 — fail-loud; the reconstruct_factor_return precedent).
    ).scalar_one_or_none()


def list_proxy_mappings(
    session: Session, *, private_instrument_id: str, acting_tenant: str
) -> list[ProxyMapping]:
    """The current-head proxy blend for one private instrument (all OPEN factor loadings on both
    axes; tenant-predicated, ordered by ``factor_id``). The residual (1 − Σweight) is NOT computed —
    a partial proxy is honest (OD-PA-0-D)."""
    return list(
        session.execute(
            select(ProxyMapping)
            .where(
                ProxyMapping.tenant_id == str(acting_tenant),
                ProxyMapping.private_instrument_id == str(private_instrument_id),
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
            .order_by(ProxyMapping.factor_id)
        )
        .scalars()
        .all()
    )
