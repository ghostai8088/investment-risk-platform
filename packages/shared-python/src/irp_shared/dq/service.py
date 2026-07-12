"""Data-quality write/run/gate utilities (REQ-DQR-001).

- ``register_dq_rule`` / ``update_dq_rule`` — manage the EV rule head, each emitting a taxonomy
  audit event (``DATA.DQ_RULE_DEFINE`` / ``DATA.DQ_RULE_UPDATE``) in the **same transaction**.
- ``run_quality_check`` — evaluate a rule over a dataset, persist an immutable
  ``data_quality_result`` and emit ``DATA.VALIDATE``, co-transactionally; applies no-silent-failure.
- ``assert_passed_quality_checks`` — the gate a **future** P1A-4 ingestion calls (none here).

No-silent-failure (CTRL-029 / QS-15/16/06 / BR-14): a failure ALWAYS persists a flagged result;
``severity=ERROR`` additionally **raises** ``DataQualityError``; ``WARNING`` flags-only; an
evaluator error always propagates (re-raised) and is audited ``outcome='failure'`` — never silent.

Tenant scoping: ``tenant_id`` is stamped server-side from the rule resolved through the RLS-scoped
session; a cross-tenant rule / data_source id fails closed. This package imports no lineage/model/
ingestion/backend module — the ``data_source`` resolution uses a local Core table reference.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Column, MetaData, Table, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_UPDATE, ACTION_VALIDATE
from irp_shared.audit.service import record_event
from irp_shared.db.types import GUID
from irp_shared.dq.models import (
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_WARN,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    DataQualityResult,
    DataQualityRule,
)
from irp_shared.dq.rules import Dataset, DQEvaluation, evaluate_rule

#: Audit taxonomy codes (DATA category). DATA.VALIDATE is existing; the two rule codes are new.
DQ_RULE_DEFINE_EVENT = "DATA.DQ_RULE_DEFINE"
DQ_RULE_UPDATE_EVENT = "DATA.DQ_RULE_UPDATE"
DQ_VALIDATE_EVENT = "DATA.VALIDATE"

#: Mutable attributes ``update_dq_rule`` will diff/apply.
_UPDATABLE = ("name", "rule_type", "params", "target_entity_type", "severity", "is_active")

#: Local Core reference to data_source (ENT-038) for RLS-scoped resolution WITHOUT importing
#: ``irp_shared.lineage`` (keeps the dq package import-clean; separate MetaData, no registration).
_DATA_SOURCE = Table("data_source", MetaData(), Column("id", GUID), Column("tenant_id", GUID))


class DataQualityError(Exception):
    """Raised by ``run_quality_check`` when an ERROR-severity rule fails or an evaluator errors —
    the no-silent-failure surface. Carries the persisted (flagged) result, if any."""

    def __init__(self, result: DataQualityResult | None, detail: str = "") -> None:
        super().__init__(detail or "data quality check failed (severity=ERROR)")
        self.result = result


class QualityCheckFailedError(Exception):
    """Raised by the gate when a target has no recorded checks or any blocking (FAIL) result."""

    def __init__(self, target_entity_type: str, target_entity_id: str, reason: str) -> None:
        super().__init__(
            f"quality gate failed for {target_entity_type}:{target_entity_id} — {reason}"
        )
        self.target_entity_type = target_entity_type
        self.target_entity_id = str(target_entity_id)


class DQReferenceNotVisible(Exception):
    """Raised when a referenced rule / data_source is not visible in the current tenant scope
    (cross-tenant id hidden by RLS, or unknown) — the write fails closed."""

    def __init__(self, kind: str, ref_id: str) -> None:
        super().__init__(f"{kind} {ref_id} is not visible in the current tenant context")
        self.kind = kind
        self.ref_id = str(ref_id)


def register_dq_rule(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    rule_type: str,
    actor_id: str,
    params: Mapping[str, Any] | None = None,
    target_entity_type: str | None = None,
    severity: str = SEVERITY_ERROR,
    actor_type: str = "user",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    on_behalf_of: str | None = None,
    correlation_id: str | None = None,
) -> DataQualityRule:
    """Create a ``data_quality_rule`` and audit it (``DATA.DQ_RULE_DEFINE``), same transaction."""
    rule = DataQualityRule(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        rule_type=rule_type,
        params=dict(params or {}),
        target_entity_type=target_entity_type,
        severity=severity,
        is_active=True,
        record_version=1,
    )
    session.add(rule)
    session.flush()

    record_event(
        session,
        event_type=DQ_RULE_DEFINE_EVENT,
        tenant_id=str(tenant_id),
        actor_type=actor_type,
        actor_id=actor_id,
        source_module="dataquality",
        entity_type="data_quality_rule",
        entity_id=rule.id,
        action=ACTION_CREATE,
        after_value={
            "code": code,
            "name": name,
            "rule_type": rule_type,
            "severity": severity,
            "target_entity_type": target_entity_type,
        },
        correlation_id=correlation_id,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        on_behalf_of=on_behalf_of,
        data_classification="DC-1",
    )
    return rule


def update_dq_rule(
    session: Session,
    rule: DataQualityRule,
    *,
    actor_id: str,
    **changes: Any,
) -> DataQualityRule:
    """Apply mutable changes to a rule, bump ``record_version``, and audit before/after
    (``DATA.DQ_RULE_UPDATE``) in the same transaction (the controlled EV update path)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable data_quality_rule attributes: {sorted(unknown)}")

    before = {key: getattr(rule, key) for key in changes}
    for key, value in changes.items():
        setattr(rule, key, value)
    rule.record_version += 1
    session.flush()

    record_event(
        session,
        event_type=DQ_RULE_UPDATE_EVENT,
        tenant_id=rule.tenant_id,
        actor_type="user",
        actor_id=actor_id,
        source_module="dataquality",
        entity_type="data_quality_rule",
        entity_id=rule.id,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: getattr(rule, key) for key in changes},
        data_classification="DC-1",
    )
    return rule


def run_quality_check(
    session: Session,
    *,
    rule: DataQualityRule,
    dataset: Dataset,
    actor_id: str,
    target_entity_type: str | None = None,
    target_entity_id: str | None = None,
    data_source_id: str | None = None,
    ingestion_batch_id: str | None = None,
    actor_type: str = "user",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    on_behalf_of: str | None = None,
    correlation_id: str | None = None,
) -> DataQualityResult:
    """Evaluate ``rule`` over ``dataset``, persist an immutable ``data_quality_result``, and audit
    ``DATA.VALIDATE`` — all co-transactionally. Applies the no-silent-failure policy (module doc).

    ``ingestion_batch_id`` (P1A-4) populates the reserved no-FK placeholder column **before flush**
    (the result is append-only — it cannot be set after the call returns/raises); it links the
    result to the ingestion batch on BOTH the PASS and the ERROR/raise paths. No schema change.
    """
    resolved = session.execute(
        select(DataQualityRule).where(DataQualityRule.id == str(rule.id))
    ).scalar_one_or_none()
    if resolved is None:
        raise DQReferenceNotVisible("data_quality_rule", str(rule.id))
    tenant = resolved.tenant_id

    if data_source_id is not None:
        visible = session.execute(
            select(_DATA_SOURCE.c.id).where(_DATA_SOURCE.c.id == str(data_source_id))
        ).first()
        if visible is None:
            raise DQReferenceNotVisible("data_source", str(data_source_id))

    error: Exception | None = None
    try:
        evaluation = evaluate_rule(resolved.rule_type, resolved.params or {}, dataset)
    except Exception as exc:  # an evaluator/config error is audited + propagated, never swallowed
        evaluation = DQEvaluation(passed=False, detail=f"evaluation error: {exc}")
        error = exc

    if evaluation.passed:
        outcome = OUTCOME_PASS
    elif error is None and resolved.severity == SEVERITY_WARNING:
        outcome = OUTCOME_WARN  # WARNING failure: flag-only, no raise
    else:
        outcome = OUTCOME_FAIL  # ERROR-severity failure or an evaluator error: will raise

    result = DataQualityResult(
        tenant_id=tenant,
        rule_id=resolved.id,
        target_entity_type=target_entity_type,
        target_entity_id=(str(target_entity_id) if target_entity_id is not None else None),
        passed=evaluation.passed,
        outcome=outcome,
        observed_value=evaluation.observed_value,
        detail=evaluation.detail,
        evaluated_count=evaluation.evaluated_count,
        failed_count=evaluation.failed_count,
        data_source_id=(str(data_source_id) if data_source_id is not None else None),
        ingestion_batch_id=(str(ingestion_batch_id) if ingestion_batch_id is not None else None),
    )
    session.add(result)
    session.flush()

    record_event(
        session,
        event_type=DQ_VALIDATE_EVENT,
        tenant_id=tenant,
        actor_type=actor_type,
        actor_id=actor_id,
        source_module="dataquality",
        entity_type="data_quality_result",
        entity_id=result.id,
        action=ACTION_VALIDATE,
        outcome=("success" if outcome == OUTCOME_PASS else "failure"),
        after_value={
            "rule_id": resolved.id,
            "outcome": outcome,
            "severity": resolved.severity,
            "target_entity_type": target_entity_type,
            "data_source_id": result.data_source_id,
            "ingestion_batch_id": result.ingestion_batch_id,
        },
        correlation_id=correlation_id,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        on_behalf_of=on_behalf_of,
        data_classification="DC-2",  # observed_value/detail may echo client data
    )

    if error is not None:
        raise DataQualityError(result, f"rule evaluation errored: {error}") from error
    if outcome == OUTCOME_FAIL:
        raise DataQualityError(result, f"rule {resolved.code!r} failed (severity=ERROR)")
    return result


def assert_passed_quality_checks(
    session: Session,
    target_entity_type: str,
    target_entity_id: str,
    *,
    tenant_id: str | None = None,
) -> list[DataQualityResult]:
    """Gate (the future-ingestion contract): raise :class:`QualityCheckFailedError` if the target
    has NO recorded checks (fail-closed) or ANY blocking ``FAIL`` result; else return the results.

    Tenant-scoped by RLS on PostgreSQL; pass ``tenant_id`` to also scope explicitly (SQLite tests).
    ``WARN`` results do not block (severity=WARNING is non-blocking by policy)."""
    stmt = select(DataQualityResult).where(
        DataQualityResult.target_entity_type == target_entity_type,
        DataQualityResult.target_entity_id == str(target_entity_id),
    )
    if tenant_id is not None:
        stmt = stmt.where(DataQualityResult.tenant_id == str(tenant_id))
    results = list(session.execute(stmt).scalars().all())
    if not results:
        raise QualityCheckFailedError(
            target_entity_type, target_entity_id, "no quality checks recorded"
        )
    blocking = [r for r in results if r.outcome == OUTCOME_FAIL]
    if blocking:
        raise QualityCheckFailedError(
            target_entity_type, target_entity_id, f"{len(blocking)} failed check(s)"
        )
    return results
