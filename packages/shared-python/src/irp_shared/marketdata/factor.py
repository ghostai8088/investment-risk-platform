"""Factor binder + governed-write provenance (P3-2, ENT-025) — captured factor-return INPUTS.

``factor`` (EV definition header) + ``factor_return`` (FR bitemporal captured series) are
**captured
vendor/external factor-return market data** (P3-2 OD-P3-2-*), reusing the P2 captured-market-data
protocol — the ``benchmark`` EV-definition split (``REFERENCE.*``) + the
``fx_rate``/``curve``-header
single-row FR series (``MARKET.*``). A factor return is a **captured** value supplied to the
platform,
**NEVER computed** — NO price-derived return, NO regression, NO factor model, NO exposure, NO
covariance, NO VaR/ES, NO ``calculation_run``, NO ``model_version`` (an INPUT, not a governed
derived
number — OD-P3-2-A/H/I). Computed factor returns are DEFERRED and would require a registered
``model_version`` + ``methodology_ref``.

- The **EV definition** (``factor``) is reference data → ``REFERENCE.CREATE``/``REFERENCE.UPDATE``
  (entity-versioned in place via ``record_version``; the ``benchmark`` definition precedent).
- The **FR return series** (``factor_return``) is captured market data that re-versions over time →
  ``MARKET.FACTOR_RETURN_CREATE``/``_UPDATE``/``_CORRECTION`` at the EVT-200 block (the
  ``fx_rate``/
  ``curve`` per-op grain: capture=1; supersede=2 (UPDATE close-out + CREATE); correct=2 (UPDATE +
  CORRECTION)). Single-row per ``(factor, return_date, return_type)`` (unlike the set-grained
  benchmark membership).

Entitlement reuses ``marketdata.view``/``.ingest``; lineage is ``VENDOR_FACTOR`` ORIGIN (the
``VENDOR_CURVE``/``VENDOR_BENCHMARK`` sibling). Invariants: ONE ``now = utcnow()`` per op;
CLOSE-FIRST
ordering on a re-version; a prior version's CONTENT is NEVER mutated (only
``valid_to``/``system_to``).
Vocab (``factor_family``/``frequency``/``return_type``) + a **finiteness guard** (``return_value``
is
a finite Decimal — rejects NaN/±Inf BEFORE write; the min-only DQ RANGE ``> -1`` does not catch
+Inf)
are binder-side ``FactorValueError`` (-> 422) BEFORE any write. The **DQ gate** (required-field
NOT_NULL + a ``> -1`` economic-sanity RANGE) is fail-closed + co-transactional; the ``(params,
dataset)`` Protocol is UNTOUCHED. No mid-call commit (CTRL-032). ``audit/service.py`` is FROZEN;
**no
emit on read**.
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
from irp_shared.marketdata.models import (
    FACTOR_FAMILIES,
    FACTOR_FAMILY_PRIVATE,
    FACTOR_FREQUENCIES,
    FACTOR_RETURN_TYPES,
    FREQUENCY_APPRAISAL,
    FREQUENCY_DAILY,
    RETURN_TYPE_SIMPLE,
    Factor,
    FactorReturn,
)
from irp_shared.reference.events import REFERENCE_CREATE_EVENT, REFERENCE_UPDATE_EVENT
from irp_shared.reference.service import resolve_currency

# --- audit / provenance constants ---
# The EV definition uses the REFERENCE.* family (EVT-140/141; imported from reference/events.py —
# the
# benchmark/corporate_action single-source precedent); the FR return series uses the MARKET.*
# family
# (EVT-200; the fifth MARKET.* member after FX/PRICE/CURVE/BENCHMARK_CONSTITUENT). OD-P3-2-J.
MARKET_FACTOR_RETURN_CREATE_EVENT = "MARKET.FACTOR_RETURN_CREATE"
MARKET_FACTOR_RETURN_UPDATE_EVENT = "MARKET.FACTOR_RETURN_UPDATE"
MARKET_FACTOR_RETURN_CORRECTION_EVENT = "MARKET.FACTOR_RETURN_CORRECTION"
VENDOR_FACTOR_SOURCE_TYPE = "VENDOR_FACTOR"
VENDOR_FACTOR_SOURCE_CODE = "VENDOR_FACTOR"
VENDOR_FACTOR_SOURCE_NAME = "Vendor factor-return data"
ENTITY_FACTOR = "factor"
ENTITY_FACTOR_RETURN = "factor_return"
SOURCE_MODULE = "marketdata"

#: Attributes ``update_factor`` may change in place (NOT the identity key code/source).
_UPDATABLE_FACTOR = (
    "factor_family",
    "factor_type",
    "region",
    "currency_code",
    "asset_class",
    "frequency",
    "factor_name",
    "description",
)

#: Per-tenant governed DQ rule codes (resolve-or-register; the ``curve`` pattern).
_REQUIRED_RULE_CODE = "factor_return.required_fields"
_VALUE_RULE_CODE = "factor_return.value_sanity"


@dataclass(frozen=True)
class FactorActor:
    """Actor/correlation context threaded into every factor audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class FactorValueError(Exception):
    """Raised for out-of-vocab family/frequency/return_type, a non-finite ``return_value``, or a
    non-updatable attribute — caught BEFORE any write (fail-closed; maps to 422)."""


class FactorNotVisible(Exception):
    """Raised when a ``factor`` id is not visible in the acting tenant scope (cross-tenant)."""

    def __init__(self, factor_id: str) -> None:
        super().__init__(f"factor {factor_id} is not visible in the current tenant context")
        self.factor_id = str(factor_id)


class NoCurrentFactorReturn(Exception):
    """Raised when a return supersede/correct is requested but the (factor, return_date,
    return_type)
    has no open current head."""

    def __init__(self, factor_id: str, return_date: date, return_type: str) -> None:
        super().__init__(
            f"factor {factor_id} has no current (open) {return_type} return for {return_date}"
        )
        self.factor_id = str(factor_id)
        self.return_date = return_date
        self.return_type = return_type


# --- binder-side value checks (FactorValueError -> 422, BEFORE any write; NOT the DQ Protocol) ---


def _validate_factor_family(factor_family: str) -> None:
    if factor_family not in FACTOR_FAMILIES:
        raise FactorValueError(f"factor_family {factor_family!r} not in {FACTOR_FAMILIES}")


def _validate_frequency(frequency: str, factor_family: str) -> None:
    """Vocab + the PPF-1 family↔frequency coupling (OD-PPF-1-A): APPRAISAL is the pure-private
    cadence and is admitted ONLY on a PRIVATE-family factor; every other family stays DAILY-only.
    A PRIVATE factor MUST be APPRAISAL (its realizations are appraisal-grain — a DAILY private
    segment factor would be a lie and would let the DAILY covariance/VaR gates silently accept an
    appraisal series). Fail-closed BOTH directions."""
    if frequency not in FACTOR_FREQUENCIES:
        raise FactorValueError(f"frequency {frequency!r} not in {FACTOR_FREQUENCIES}")
    if frequency == FREQUENCY_APPRAISAL and factor_family != FACTOR_FAMILY_PRIVATE:
        raise FactorValueError(
            f"frequency {FREQUENCY_APPRAISAL!r} is admitted only on a {FACTOR_FAMILY_PRIVATE!r}"
            f"-family factor (got family {factor_family!r}) — refused"
        )
    if factor_family == FACTOR_FAMILY_PRIVATE and frequency != FREQUENCY_APPRAISAL:
        raise FactorValueError(
            f"a {FACTOR_FAMILY_PRIVATE!r}-family factor must be {FREQUENCY_APPRAISAL!r}-frequency "
            f"(got {frequency!r}) — refused"
        )


def _validate_return_type(return_type: str) -> None:
    if return_type not in FACTOR_RETURN_TYPES:
        raise FactorValueError(f"return_type {return_type!r} not in {FACTOR_RETURN_TYPES}")


def _validate_return_value(return_value: Decimal) -> None:
    """Finiteness guard: reject NaN / +Infinity / -Infinity BEFORE any write (the DQ min-only RANGE
    ``> -1`` does NOT catch +Infinity; the ``fx_rate._validate_pair`` binder-guard precedent)."""
    if not isinstance(return_value, Decimal) or not return_value.is_finite():
        raise FactorValueError(f"return_value must be a finite Decimal (got {return_value!r})")


# --- governed DQ gate (the ``curve`` pattern — Protocol UNTOUCHED) ---


def _ensure_rule(
    session: Session,
    *,
    tenant_id: str,
    actor: FactorActor,
    code: str,
    name: str,
    rule_type: str,
    params: dict[str, Any],
) -> DataQualityRule:
    """Resolve-or-register a per-tenant governed DQ rule (audited; the ``curve`` pattern)."""
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
            target_entity_type=ENTITY_FACTOR_RETURN,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_return_dq_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: FactorActor,
    return_row: FactorReturn,
    return_value: Decimal,
) -> None:
    """Fail-closed DQ gate (co-transactional; ``DATA.VALIDATE``): (1) required-field NOT_NULL
    (factor_id/return_date/return_type/return_value present); (2) an economic-sanity RANGE
    ``return_value > -1`` (a simple return cannot be below -100%). Finiteness is the binder guard
    (BEFORE this gate). A failure -> ``DataQualityError`` -> the caller's whole unit rolls back
    (CTRL-032). The single-column ``(params, dataset)`` Protocol is UNTOUCHED."""
    missing = any(
        getattr(return_row, f) is None
        for f in ("factor_id", "return_date", "return_type", "return_value")
    )
    required_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_REQUIRED_RULE_CODE,
        name="Factor return required fields present",
        rule_type=RULE_TYPE_NOT_NULL,
        params={"column": "present"},
    )
    run_quality_check(
        session,
        rule=required_rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_FACTOR_RETURN,
        target_entity_id=return_row.id,
        actor_type=actor.actor_type,
    )

    value_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_VALUE_RULE_CODE,
        name="Factor return economic sanity (> -1)",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "return_value", "min": -1, "min_inclusive": False},
    )
    run_quality_check(
        session,
        rule=value_rule,
        dataset=[{"return_value": return_value}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_FACTOR_RETURN,
        target_entity_id=return_row.id,
        actor_type=actor.actor_type,
    )


# --- provenance: VENDOR data_source + caller-side emitters ---


def ensure_vendor_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's shared ``VENDOR_FACTOR``
    ``data_source``
    (governed provenance root; the ``VENDOR_CURVE``/``VENDOR_BENCHMARK`` precedent).
    Module-local."""
    # Race-safe (MD-H1 review fold): two concurrent FIRST callers both SELECT-miss then
    # INSERT the same key; the loser re-resolves the peer instead of aborting the unit.
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == str(tenant_id),
                DataSource.code == VENDOR_FACTOR_SOURCE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=str(tenant_id),
            code=VENDOR_FACTOR_SOURCE_CODE,
            name=VENDOR_FACTOR_SOURCE_NAME,
            source_type=VENDOR_FACTOR_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def _origin_edge(
    session: Session, *, tenant_id: str, entity_type: str, entity_id: str, actor: FactorActor
) -> None:
    """Root one ORIGIN lineage edge (VENDOR_FACTOR source) targeting a NEW factor / factor_return
    physical version."""
    source = ensure_vendor_source(session, tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=entity_type,
        target_entity_id=entity_id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: FactorActor,
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
        entity_type=entity_type,
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


def _factor_summary(row: Factor) -> dict[str, Any]:
    """A DC-2 factor-definition-summary dict (metadata only)."""
    return {
        "factor_code": row.factor_code,
        "factor_source": row.factor_source,
        "factor_family": row.factor_family,
        "factor_type": row.factor_type,
        "currency_code": row.currency_code,
        "frequency": row.frequency,
        "record_version": row.record_version,
    }


def _return_summary(factor: Factor, row: FactorReturn) -> dict[str, Any]:
    """A DC-2 factor-return-summary dict (metadata only — never a bulk vendor payload)."""
    return {
        "factor_code": factor.factor_code,
        "factor_source": factor.factor_source,
        "return_date": _json_safe(row.return_date),
        "return_type": row.return_type,
        "record_version": row.record_version,
    }


# --- factor DEFINITION (EV; REFERENCE.* audit; VENDOR_FACTOR lineage) ---


def resolve_factor(session: Session, factor_id: str, *, acting_tenant: str) -> Factor:
    """Resolve a ``factor`` by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed). Raises :class:`FactorNotVisible` on a hidden id."""
    row = session.execute(
        select(Factor).where(Factor.id == str(factor_id), Factor.tenant_id == str(acting_tenant))
    ).scalar_one_or_none()
    if row is None:
        raise FactorNotVisible(str(factor_id))
    return row


def capture_factor(
    session: Session,
    *,
    factor_code: str,
    factor_source: str,
    factor_family: str,
    acting_tenant: str,
    actor: FactorActor,
    factor_type: str | None = None,
    region: str | None = None,
    currency_code: str | None = None,
    asset_class: str | None = None,
    frequency: str = FREQUENCY_DAILY,
    factor_name: str | None = None,
    description: str | None = None,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Factor:
    """Capture a factor DEFINITION (EV): validate vocab + optional currency (hybrid-aware) BEFORE
    any
    write, create the row, root one VENDOR_FACTOR ORIGIN edge + emit ``REFERENCE.CREATE``. A
    captured
    definition — NOT computed. ``entity_id``/``now`` are the deterministic-injection seam."""
    _validate_factor_family(factor_family)
    _validate_frequency(frequency, factor_family)
    if currency_code is not None:
        resolve_currency(session, currency_code, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = Factor(
        tenant_id=str(acting_tenant),
        factor_code=factor_code,
        factor_source=factor_source,
        factor_family=factor_family,
        factor_type=factor_type,
        region=region,
        currency_code=currency_code,
        asset_class=asset_class,
        frequency=frequency,
        factor_name=factor_name,
        description=description,
        valid_from=(valid_from or now),
        valid_to=None,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _origin_edge(
        session, tenant_id=row.tenant_id, entity_type=ENTITY_FACTOR, entity_id=row.id, actor=actor
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_FACTOR,
        entity_id=row.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_factor_summary(row),
        actor=actor,
        now=now,
    )
    return row


def update_factor(
    session: Session,
    factor: Factor,
    *,
    acting_tenant: str,
    actor: FactorActor,
    now: datetime | None = None,
    **changes: Any,
) -> Factor:
    """Apply mutable ATTRIBUTE changes to a factor definition in place (EV — one physical row),
    bump
    ``record_version``, emit ``REFERENCE.UPDATE`` (NO new lineage edge; the identity key
    code/source
    is NOT updatable). ``factor`` must already be tenant-resolved (via ``resolve_factor``)."""
    unknown = set(changes) - set(_UPDATABLE_FACTOR)
    if unknown:
        raise FactorValueError(f"non-updatable factor attributes: {sorted(unknown)}")
    if not changes:
        return factor  # no-op: no version bump, no REFERENCE.UPDATE
    if "factor_family" in changes:
        _validate_factor_family(changes["factor_family"])
    # The family↔frequency coupling must hold on the RESULTING row, so validate the effective pair
    # whenever EITHER attribute changes (a family change can violate an unchanged frequency, and
    # vice versa) — PPF-1 OD-PPF-1-A.
    if "frequency" in changes or "factor_family" in changes:
        _validate_frequency(
            changes.get("frequency", factor.frequency),
            changes.get("factor_family", factor.factor_family),
        )
    if changes.get("currency_code") is not None:
        resolve_currency(session, changes["currency_code"], acting_tenant=acting_tenant)
    now = now or utcnow()
    before = {key: _json_safe(getattr(factor, key)) for key in changes}
    for key, value in changes.items():
        setattr(factor, key, value)
    factor.record_version = factor.record_version + 1
    session.flush()
    _emit(
        session,
        tenant_id=factor.tenant_id,
        entity_type=ENTITY_FACTOR,
        entity_id=factor.id,
        event_type=REFERENCE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: _json_safe(getattr(factor, key)) for key in changes},
        actor=actor,
        now=now,
    )
    return factor


def list_factors(session: Session, *, acting_tenant: str) -> list[Factor]:
    """All current factor definitions for the acting tenant (ordered by code/source)."""
    return list(
        session.execute(
            select(Factor)
            .where(Factor.tenant_id == str(acting_tenant))
            .order_by(Factor.factor_code, Factor.factor_source)
        )
        .scalars()
        .all()
    )


# --- factor_return SERIES (FR single-row; MARKET.FACTOR_RETURN_* audit) ---


def _current_open_return(
    session: Session,
    *,
    acting_tenant: str,
    factor_id: str,
    return_date: date,
    return_type: str,
) -> FactorReturn | None:
    """The single return version OPEN ON BOTH axes for a logical key (the bitemporal current head),
    or ``None``. Tenant-predicated."""
    return session.execute(
        select(FactorReturn).where(
            FactorReturn.tenant_id == str(acting_tenant),
            FactorReturn.factor_id == str(factor_id),
            FactorReturn.return_date == return_date,
            FactorReturn.return_type == return_type,
            FactorReturn.valid_to.is_(None),
            FactorReturn.system_to.is_(None),
        )
    ).scalar_one_or_none()


def capture_factor_return(
    session: Session,
    factor: Factor,
    *,
    return_date: date,
    return_value: Decimal,
    acting_tenant: str,
    actor: FactorActor,
    return_type: str = RETURN_TYPE_SIMPLE,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> FactorReturn:
    """Capture the first open return for a (factor, return_date, return_type) as ONE governed unit
    (FR row + VENDOR ORIGIN edge + ``MARKET.FACTOR_RETURN_CREATE`` + the DQ gate). The return_type
    +
    finiteness are validated BEFORE any write; the value is captured verbatim (NEVER computed).
    ``factor`` must already be tenant-resolved (via ``resolve_factor``)."""
    _validate_return_type(return_type)
    _validate_return_value(return_value)
    now = now or utcnow()
    row = FactorReturn(
        tenant_id=factor.tenant_id,
        factor_id=factor.id,
        return_date=return_date,  # immutable logical-key component (NOT the valid_from axis)
        return_type=return_type,
        return_value=return_value,
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
    _run_return_dq_gate(
        session, acting_tenant=acting_tenant, actor=actor, return_row=row, return_value=return_value
    )
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=row.id,
        event_type=MARKET_FACTOR_RETURN_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_return_summary(factor, row),
        actor=actor,
        now=now,
    )
    return row


def supersede_factor_return(
    session: Session,
    factor: Factor,
    *,
    return_date: date,
    return_value: Decimal,
    acting_tenant: str,
    actor: FactorActor,
    effective_at: datetime,
    return_type: str = RETURN_TYPE_SIMPLE,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> FactorReturn:
    """Effective-dated (valid-time) re-capture for the SAME key: close the head's ``valid_to``
    (``MARKET.FACTOR_RETURN_UPDATE``), then insert a new version (``MARKET.FACTOR_RETURN_CREATE`` +
    its own ORIGIN edge + the DQ gate). The head is sourced via the tenant-predicated
    ``_current_open_return`` (never a caller-supplied id)."""
    _validate_return_type(return_type)
    _validate_return_value(return_value)
    prior = _current_open_return(
        session,
        acting_tenant=acting_tenant,
        factor_id=factor.id,
        return_date=return_date,
        return_type=return_type,
    )
    if prior is None:
        raise NoCurrentFactorReturn(factor.id, return_date, return_type)

    assert_supersede_effective_at(prior.valid_from, effective_at, error=FactorValueError)
    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST (valid-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=prior.id,
        event_type=MARKET_FACTOR_RETURN_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    new = FactorReturn(
        tenant_id=factor.tenant_id,
        factor_id=factor.id,
        return_date=prior.return_date,  # carried verbatim (immutable logical key)
        return_type=prior.return_type,
        return_value=return_value,
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
    _run_return_dq_gate(
        session, acting_tenant=acting_tenant, actor=actor, return_row=new, return_value=return_value
    )
    _origin_edge(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=new.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=new.id,
        event_type=MARKET_FACTOR_RETURN_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_return_summary(factor, new),
        actor=actor,
        now=now,
    )
    return new


def correct_factor_return(
    session: Session,
    factor: Factor,
    *,
    return_date: date,
    return_value: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: FactorActor,
    return_type: str = RETURN_TYPE_SIMPLE,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> FactorReturn:
    """As-known restatement (TR-08): close the prior head's ``system_to = now`` then insert a
    corrected version over the SAME valid period + same key (``MARKET.FACTOR_RETURN_CORRECTION`` +
    its own ORIGIN edge + the DQ gate). The prior version's content columns are NEVER mutated —
    only
    ``system_to``. ``factor`` must already be tenant-resolved (via ``resolve_factor``)."""
    _validate_return_type(return_type)
    _validate_return_value(return_value)
    prior = _current_open_return(
        session,
        acting_tenant=acting_tenant,
        factor_id=factor.id,
        return_date=return_date,
        return_type=return_type,
    )
    if prior is None:
        raise NoCurrentFactorReturn(factor.id, return_date, return_type)

    now = now or utcnow()
    before = {"system_to": _json_safe(prior.system_to)}
    valid_from_prior = prior.valid_from
    valid_to_prior = prior.valid_to
    prior.system_to = now  # CLOSE-FIRST (system-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=prior.id,
        event_type=MARKET_FACTOR_RETURN_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"system_to": _json_safe(prior.system_to)},
        actor=actor,
        now=now,
    )

    corrected = FactorReturn(
        tenant_id=factor.tenant_id,
        factor_id=factor.id,
        return_date=prior.return_date,  # carried verbatim (immutable logical key)
        return_type=prior.return_type,
        return_value=return_value,
        valid_from=valid_from_prior,  # SAME valid period (as-known correction)
        valid_to=valid_to_prior,
        system_from=now,  # one `now` — equals the prior head's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
    )
    if entity_id is not None:
        corrected.id = entity_id
    session.add(corrected)
    session.flush()
    _run_return_dq_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        return_row=corrected,
        return_value=return_value,
    )
    _origin_edge(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=corrected.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_FACTOR_RETURN,
        entity_id=corrected.id,
        event_type=MARKET_FACTOR_RETURN_CORRECTION_EVENT,
        action=ACTION_CORRECT,
        after_value=_return_summary(factor, corrected),
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return corrected


def reconstruct_factor_return_as_of(
    session: Session,
    *,
    acting_tenant: str,
    factor_id: str,
    return_date: date,
    valid_at: datetime,
    return_type: str = RETURN_TYPE_SIMPLE,
    known_at: datetime | None = None,
) -> FactorReturn | None:
    """Bitemporal as-of read: the single factor return true at ``valid_at`` as-known-at
    ``known_at``
    (``known_at`` defaults to now -> the current view), or ``None``, for the given logical key. A
    captured return only — NO factor exposure / covariance / risk."""
    known = known_at or utcnow()
    return session.execute(
        select(FactorReturn).where(
            FactorReturn.tenant_id == str(acting_tenant),
            FactorReturn.factor_id == str(factor_id),
            FactorReturn.return_date == return_date,
            FactorReturn.return_type == return_type,
            FactorReturn.valid_from <= valid_at,
            or_(FactorReturn.valid_to.is_(None), FactorReturn.valid_to > valid_at),
            FactorReturn.system_from <= known,
            or_(FactorReturn.system_to.is_(None), FactorReturn.system_to > known),
        )
    ).scalar_one_or_none()


def list_factor_returns(
    session: Session,
    *,
    acting_tenant: str,
    factor_id: str,
    return_type: str | None = None,
) -> list[FactorReturn]:
    """The current-head (open on both axes) return series for a factor, ordered by return_date. A
    captured series only — NO analytics. Optionally filtered by ``return_type``."""
    stmt = select(FactorReturn).where(
        FactorReturn.tenant_id == str(acting_tenant),
        FactorReturn.factor_id == str(factor_id),
        FactorReturn.valid_to.is_(None),
        FactorReturn.system_to.is_(None),
    )
    if return_type is not None:
        stmt = stmt.where(FactorReturn.return_type == return_type)
    return list(
        session.execute(stmt.order_by(FactorReturn.return_date, FactorReturn.return_type))
        .scalars()
        .all()
    )
