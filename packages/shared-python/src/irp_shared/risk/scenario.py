"""Scenario definition + shock binder (P3-6, ENT-029) — inputs of the tenth governed number.

Two protocols in one cohesive feature:

- **ScenarioDefinition (EV)** — ``create_scenario_definition`` / ``update_scenario_definition`` /
  ``resolve_scenario_definition``: the versioned saved header (BR-8), entity-versioned in place
  (``record_version``), audited ``REFERENCE.*`` (a scenario is authored reference/config data, NOT
  vendor market data — the ``factor`` EV precedent). ``scenario_type`` vocab is binder-ENFORCED.
- **ScenarioShock (FR bitemporal)** — ``capture`` / ``supersede`` / ``correct`` / ``reconstruct`` /
  ``list``: the ``proxy_mapping`` membership protocol exactly (full both-axes history, close-out
  UPDATEs, the MD-H1 window-coherence guard on supersede, the race-safe DQ registration). The
  CURRENCY-family factor scope is ENFORCED at capture (the PA-0 fold — not merely doc-stated); a
  ``shock_value`` finiteness guard rejects NaN/±Inf.

Provenance: a ``MANUAL_SCENARIO`` ORIGIN lineage edge per new version (the ``MANUAL_PROXY``
precedent). Entitlement REUSES ``risk.run``/``risk.view`` (NO mint — defining IS the running
persona's action, OQ-P3-6-2). ``audit/service.py`` stays FROZEN; no emit on read.
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
from irp_shared.marketdata.models import FACTOR_FAMILY_CURRENCY, Factor
from irp_shared.reference.events import (
    REFERENCE_CORRECTION_EVENT,
    REFERENCE_CREATE_EVENT,
    REFERENCE_UPDATE_EVENT,
)
from irp_shared.risk.scenario_models import (
    SCENARIO_TYPES,
    SHOCK_TYPE_RETURN,
    SHOCK_TYPES,
    ScenarioDefinition,
    ScenarioShock,
)

SOURCE_MODULE = "risk"
ENTITY_SCENARIO_DEFINITION = "scenario_definition"
ENTITY_SCENARIO_SHOCK = "scenario_shock"

#: A non-vendor manual-judgment provenance root (the MANUAL_PROXY precedent — an authored scenario).
MANUAL_SCENARIO_SOURCE_TYPE = "MANUAL_SCENARIO"
MANUAL_SCENARIO_SOURCE_CODE = "MANUAL_SCENARIO"
MANUAL_SCENARIO_SOURCE_NAME = "Manual stress/scenario definition"

_SHOCK_REQUIRED_RULE_CODE = "scenario_shock.required_fields"


@dataclass(frozen=True)
class ScenarioActor:
    """Actor/correlation context threaded into every scenario audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class ScenarioValueError(Exception):
    """Out-of-vocab ``scenario_type``/``shock_type``, a non-finite ``shock_value``, a non-CURRENCY
    factor, or a window-incoherent supersede — caught pre-write (fail-closed; maps to 422)."""


class ScenarioNotVisible(Exception):
    """Raised when a scenario_definition/scenario_shock id is not visible in the acting tenant."""

    def __init__(self, kind: str, entity_id: str) -> None:
        super().__init__(f"{kind} {entity_id} is not visible in the current tenant context")
        self.kind = kind
        self.entity_id = str(entity_id)


class NoCurrentScenarioShock(Exception):
    """Raised when a supersede/correct is requested but the (definition, factor) has no open row."""

    def __init__(self, scenario_definition_id: str, factor_id: str) -> None:
        super().__init__(
            f"scenario {scenario_definition_id} has no current (open) shock for factor {factor_id}"
        )
        self.scenario_definition_id = str(scenario_definition_id)
        self.factor_id = str(factor_id)


# --- validators ---


def _validate_scenario_type(scenario_type: str) -> None:
    if scenario_type not in SCENARIO_TYPES:
        raise ScenarioValueError(f"scenario_type {scenario_type!r} not in {sorted(SCENARIO_TYPES)}")


def _validate_shock_type(shock_type: str) -> None:
    if shock_type not in SHOCK_TYPES:
        raise ScenarioValueError(f"shock_type {shock_type!r} not in {sorted(SHOCK_TYPES)}")


#: The magnitude the ``scenario_shock.shock_value`` ``Numeric(20,12)`` column can represent — 8
#: integer digits. A shock is a signed RETURN fraction with no natural economic bound, but the
#: column has a physical one: a caller-supplied value AT/BEYOND this overflows at flush as a PG
#: DataError (a NON-IntegrityError the write handler cannot map) → an opaque 500. We refuse it as a
#: governed 422 BEFORE the write instead (the fail-closed-not-500 principle).
_SHOCK_VALUE_ABS_MAX = Decimal("1E8")


def _validate_shock_value(shock_value: Decimal) -> None:
    """Finiteness + column-capacity guard: reject NaN / ±Infinity and any value the
    ``Numeric(20,12)`` column cannot hold (|value| >= 1E8) BEFORE any write — a governed 422,
    never a flush-time 500."""
    if not isinstance(shock_value, Decimal) or not shock_value.is_finite():
        raise ScenarioValueError(f"shock_value must be a finite Decimal (got {shock_value!r})")
    if abs(shock_value) >= _SHOCK_VALUE_ABS_MAX:
        raise ScenarioValueError(
            f"shock_value magnitude {shock_value!r} exceeds the Numeric(20,12) column capacity "
            f"(|value| must be < 1E8); refused"
        )


def _resolve_factor_id(session: Session, factor_id: str, *, acting_tenant: str) -> str:
    """Re-resolve the factor under the acting tenant BEFORE its id is stamped into the NOT-NULL FK
    (the P3-5 cross-tenant-FK guard) AND enforce the v1 CURRENCY-family scope (OD-P3-6 Part 3;
    the PA-0 fold — an enforced gate, not a doc claim). Models-only import (no cycle)."""
    row = session.execute(
        select(Factor.id, Factor.factor_family).where(
            Factor.id == str(factor_id),
            Factor.tenant_id == str(acting_tenant),
        )
    ).one_or_none()
    if row is None:
        raise ScenarioValueError(
            f"factor {factor_id} is not visible in the acting tenant — refused"
        )
    if row.factor_family != FACTOR_FAMILY_CURRENCY:
        raise ScenarioValueError(
            f"factor {factor_id} family {row.factor_family!r} is not CURRENCY — outside P3-6 v1 "
            f"scope (a style/sector/rate shock family is a v2 extension); refused"
        )
    return str(row.id)


# --- provenance (MANUAL_SCENARIO ORIGIN lineage) + audit emit ---


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the tenant's ``MANUAL_SCENARIO`` ``data_source`` (governed
    provenance root; the MANUAL_PROXY precedent, non-vendor variant). Race-safe (MD-H1)."""
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == str(tenant_id),
                DataSource.code == MANUAL_SCENARIO_SOURCE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=str(tenant_id),
            code=MANUAL_SCENARIO_SOURCE_CODE,
            name=MANUAL_SCENARIO_SOURCE_NAME,
            source_type=MANUAL_SCENARIO_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def _origin_edge(
    session: Session, *, tenant_id: str, entity_type: str, entity_id: str, actor: ScenarioActor
) -> None:
    source = ensure_manual_source(session, tenant_id, actor.actor_id)
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
    actor: ScenarioActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
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


# --- DQ gates (required-field NOT_NULL presence; the proxy_mapping pattern) ---


def _ensure_rule(
    session: Session, *, tenant_id: str, actor: ScenarioActor, code: str, name: str, entity: str
) -> DataQualityRule:
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
            rule_type=RULE_TYPE_NOT_NULL,
            actor_id=actor.actor_id,
            params={"column": "present"},
            target_entity_type=entity,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_shock_dq_gate(
    session: Session, *, acting_tenant: str, actor: ScenarioActor, row: ScenarioShock
) -> None:
    """Fail-closed DQ gate (co-transactional): required-field NOT_NULL (definition/factor/
    shock_value/shock_type present). Vocab + finiteness are the binder guards BEFORE this gate."""
    missing = any(
        getattr(row, f) is None
        for f in ("scenario_definition_id", "factor_id", "shock_value", "shock_type")
    )
    rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_SHOCK_REQUIRED_RULE_CODE,
        name="scenario_shock required fields present",
        entity=ENTITY_SCENARIO_SHOCK,
    )
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_SCENARIO_SHOCK,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


def _def_summary(row: ScenarioDefinition) -> dict[str, Any]:
    return {
        "code": row.code,
        "name": row.name,
        "scenario_type": row.scenario_type,
        "record_version": row.record_version,
    }


def _shock_summary(row: ScenarioShock) -> dict[str, Any]:
    return {
        "scenario_definition_id": _json_safe(row.scenario_definition_id),
        "factor_id": _json_safe(row.factor_id),
        "shock_type": row.shock_type,
        "record_version": row.record_version,
    }


# --- ScenarioDefinition (EV) ---


def resolve_scenario_definition(
    session: Session, scenario_definition_id: str, *, acting_tenant: str
) -> ScenarioDefinition:
    """Resolve a ``scenario_definition`` by id with an EXPLICIT tenant predicate (fail-closed)."""
    row = session.execute(
        select(ScenarioDefinition).where(
            ScenarioDefinition.id == str(scenario_definition_id),
            ScenarioDefinition.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ScenarioNotVisible(ENTITY_SCENARIO_DEFINITION, str(scenario_definition_id))
    return row


def create_scenario_definition(
    session: Session,
    *,
    code: str,
    name: str,
    scenario_type: str,
    acting_tenant: str,
    actor: ScenarioActor,
    description: str | None = None,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ScenarioDefinition:
    """Create the scenario header (EV) as ONE governed unit (row + MANUAL_SCENARIO ORIGIN edge +
    ``REFERENCE.CREATE``). ``scenario_type`` vocab is enforced BEFORE the write."""
    _validate_scenario_type(scenario_type)
    now = now or utcnow()
    row = ScenarioDefinition(
        tenant_id=str(acting_tenant),
        code=code,
        name=name,
        scenario_type=scenario_type,
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
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_SCENARIO_DEFINITION,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_SCENARIO_DEFINITION,
        entity_id=row.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_def_summary(row),
        actor=actor,
        now=now,
    )
    return row


def update_scenario_definition(
    session: Session,
    definition: ScenarioDefinition,
    *,
    acting_tenant: str,
    actor: ScenarioActor,
    name: str | None = None,
    scenario_type: str | None = None,
    description: str | None = None,
    now: datetime | None = None,
) -> ScenarioDefinition:
    """In-place EV re-version of the header (``record_version`` bump; ``REFERENCE.UPDATE``). The
    ``code`` identity key is immutable; the shock set is versioned separately (FR)."""
    row = resolve_scenario_definition(session, definition.id, acting_tenant=acting_tenant)
    if scenario_type is not None:
        _validate_scenario_type(scenario_type)
    before = _def_summary(row)
    now = now or utcnow()
    if name is not None:
        row.name = name
    if scenario_type is not None:
        row.scenario_type = scenario_type
    if description is not None:
        row.description = description
    row.record_version += 1
    session.flush()
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_SCENARIO_DEFINITION,
        entity_id=row.id,
        event_type=REFERENCE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value=_def_summary(row),
        actor=actor,
        now=now,
    )
    return row


def list_scenario_definitions(session: Session, *, acting_tenant: str) -> list[ScenarioDefinition]:
    """All scenario headers for the acting tenant (ordered by code)."""
    return list(
        session.execute(
            select(ScenarioDefinition)
            .where(ScenarioDefinition.tenant_id == str(acting_tenant))
            .order_by(ScenarioDefinition.code)
        )
        .scalars()
        .all()
    )


# --- ScenarioShock (FR bitemporal) — the proxy_mapping membership protocol ---


def _current_open_shock(
    session: Session, *, acting_tenant: str, scenario_definition_id: str, factor_id: str
) -> ScenarioShock | None:
    return session.execute(
        select(ScenarioShock).where(
            ScenarioShock.tenant_id == str(acting_tenant),
            ScenarioShock.scenario_definition_id == str(scenario_definition_id),
            ScenarioShock.factor_id == str(factor_id),
            ScenarioShock.valid_to.is_(None),
            ScenarioShock.system_to.is_(None),
        )
    ).scalar_one_or_none()


def capture_scenario_shock(
    session: Session,
    *,
    scenario_definition_id: str,
    factor_id: str,
    shock_value: Decimal,
    acting_tenant: str,
    actor: ScenarioActor,
    shock_type: str = SHOCK_TYPE_RETURN,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ScenarioShock:
    """Capture the first open shock for a (definition, factor) as ONE governed unit (FR row +
    ORIGIN edge + ``REFERENCE.CREATE`` + the DQ gate). Vocab + finiteness validated, the definition
    + factor re-resolved tenant-filtered (CURRENCY scope enforced), BEFORE any write."""
    _validate_shock_type(shock_type)
    _validate_shock_value(shock_value)
    definition = resolve_scenario_definition(
        session, scenario_definition_id, acting_tenant=acting_tenant
    )
    resolved_factor = _resolve_factor_id(session, factor_id, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = ScenarioShock(
        tenant_id=str(acting_tenant),
        scenario_definition_id=definition.id,
        factor_id=resolved_factor,
        shock_value=shock_value,
        shock_type=shock_type,
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
    _run_shock_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=row)
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=row.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_shock_summary(row),
        actor=actor,
        now=now,
    )
    return row


def supersede_scenario_shock(
    session: Session,
    *,
    scenario_definition_id: str,
    factor_id: str,
    shock_value: Decimal,
    acting_tenant: str,
    actor: ScenarioActor,
    effective_at: datetime,
    shock_type: str = SHOCK_TYPE_RETURN,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ScenarioShock:
    """Effective-dated (valid-time) re-capture for the SAME key: close the head's ``valid_to``
    (``REFERENCE.UPDATE``), then insert a new version (``REFERENCE.CREATE`` + edge + DQ gate).
    The head is sourced via the tenant-predicated ``_current_open_shock`` (never a caller id)."""
    _validate_shock_type(shock_type)
    _validate_shock_value(shock_value)
    prior = _current_open_shock(
        session,
        acting_tenant=acting_tenant,
        scenario_definition_id=scenario_definition_id,
        factor_id=factor_id,
    )
    if prior is None:
        raise NoCurrentScenarioShock(scenario_definition_id, factor_id)

    assert_supersede_effective_at(prior.valid_from, effective_at, error=ScenarioValueError)
    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST (valid-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=prior.id,
        event_type=REFERENCE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    new = ScenarioShock(
        tenant_id=prior.tenant_id,
        scenario_definition_id=prior.scenario_definition_id,
        factor_id=prior.factor_id,
        shock_value=shock_value,
        shock_type=shock_type,
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
    _run_shock_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=new)
    _origin_edge(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=new.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=new.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_shock_summary(new),
        actor=actor,
        now=now,
    )
    return new


def correct_scenario_shock(
    session: Session,
    *,
    scenario_definition_id: str,
    factor_id: str,
    shock_value: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: ScenarioActor,
    shock_type: str = SHOCK_TYPE_RETURN,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> ScenarioShock:
    """As-known (system-time) correction for the SAME key: close the head's ``system_to``
    (``REFERENCE.UPDATE``), then insert a corrected version over the SAME valid window with
    ``restatement_reason`` (``REFERENCE.CORRECTION`` + ORIGIN edge + DQ gate; TR-08)."""
    _validate_shock_type(shock_type)
    _validate_shock_value(shock_value)
    if not restatement_reason:
        raise ScenarioValueError("restatement_reason is required for a correction (TR-08)")
    prior = _current_open_shock(
        session,
        acting_tenant=acting_tenant,
        scenario_definition_id=scenario_definition_id,
        factor_id=factor_id,
    )
    if prior is None:
        raise NoCurrentScenarioShock(scenario_definition_id, factor_id)

    now = now or utcnow()
    before = {"system_to": _json_safe(prior.system_to)}
    prior.system_to = now  # CLOSE-FIRST (system-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=prior.id,
        event_type=REFERENCE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"system_to": _json_safe(prior.system_to)},
        actor=actor,
        now=now,
    )

    corrected = ScenarioShock(
        tenant_id=prior.tenant_id,
        scenario_definition_id=prior.scenario_definition_id,
        factor_id=prior.factor_id,
        shock_value=shock_value,
        shock_type=shock_type,
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
    _run_shock_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=corrected)
    _origin_edge(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=corrected.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_SCENARIO_SHOCK,
        entity_id=corrected.id,
        event_type=REFERENCE_CORRECTION_EVENT,
        action=ACTION_CORRECT,
        before_value={"shock_value": _json_safe(prior.shock_value)},
        after_value={**_shock_summary(corrected), "shock_value": _json_safe(corrected.shock_value)},
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return corrected


def reconstruct_scenario_shock_as_of(
    session: Session,
    *,
    scenario_definition_id: str,
    factor_id: str,
    valid_at: datetime,
    known_at: datetime,
    acting_tenant: str,
) -> ScenarioShock | None:
    """The shock for (definition, factor) true at ``valid_at`` as KNOWN at ``known_at`` — the
    both-axes bitemporal read (the ``proxy_mapping`` precedent). ``None`` if uncovered."""
    return session.execute(
        select(ScenarioShock).where(
            ScenarioShock.tenant_id == str(acting_tenant),
            ScenarioShock.scenario_definition_id == str(scenario_definition_id),
            ScenarioShock.factor_id == str(factor_id),
            ScenarioShock.valid_from <= valid_at,
            (ScenarioShock.valid_to.is_(None)) | (ScenarioShock.valid_to > valid_at),
            ScenarioShock.system_from <= known_at,
            (ScenarioShock.system_to.is_(None)) | (ScenarioShock.system_to > known_at),
        )
    ).scalar_one_or_none()


def list_scenario_shocks(
    session: Session, *, scenario_definition_id: str, acting_tenant: str
) -> list[ScenarioShock]:
    """The current-head shock set for one scenario (all OPEN factor shocks on both axes; ordered by
    ``factor_id``)."""
    return list(
        session.execute(
            select(ScenarioShock)
            .where(
                ScenarioShock.tenant_id == str(acting_tenant),
                ScenarioShock.scenario_definition_id == str(scenario_definition_id),
                ScenarioShock.valid_to.is_(None),
                ScenarioShock.system_to.is_(None),
            )
            .order_by(ScenarioShock.factor_id)
        )
        .scalars()
        .all()
    )
