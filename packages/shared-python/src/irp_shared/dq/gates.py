"""Shared fail-closed presence gate (P3-4-R0 — the parameterized extraction of the four
per-slice ``_ensure_completeness_rule`` + ``_run_completeness_gate`` copies flagged at their
tipping point by the 2026-07-07 adversarial review).

The pattern (unchanged from the P2-1 original): a per-tenant resolve-or-register **NOT_NULL** rule
over ``{'column': 'present'}``, then a governed ``run_quality_check`` over a derived dataset of one
``{'present': None}`` row per GAP (or a single ``{'present': True}`` row when there are none) — a
non-empty gap set fails ERROR-severity ⇒ ``DataQualityError`` ⇒ the caller's fail-closed handling
(whole-unit rollback at snapshot build; post-create FAILED at a governed run). Emits
``DATA.VALIDATE``; the ``(params, dataset)`` evaluator ``Protocol`` is UNTOUCHED.

Behavior-preserving by construction: rule codes/names/targets stay caller-supplied, so the
persisted ``data_quality_rule``/``data_quality_result`` shapes are byte-identical to the previous
per-slice copies.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import register_dq_rule, run_quality_check


def ensure_presence_rule(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    target_entity_type: str,
    actor_id: str,
    actor_type: str = "user",
) -> DataQualityRule:
    """Resolve-or-register the per-tenant presence (NOT_NULL ``present``) rule — governed +
    audited (the ``ensure_manual_source`` resolve-or-register pattern)."""
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
        rule_type=RULE_TYPE_NOT_NULL,
        actor_id=actor_id,
        params={"column": "present"},
        target_entity_type=target_entity_type,
        severity=SEVERITY_ERROR,
        actor_type=actor_type,
    )


def run_presence_gate(
    session: Session,
    *,
    rule: DataQualityRule,
    gaps: list[str],
    target_entity_type: str,
    target_entity_id: str,
    actor_id: str,
    actor_type: str = "user",
) -> None:
    """Run the fail-closed presence gate: one ``{'present': None}`` row per gap (raises
    ``DataQualityError`` via ``run_quality_check`` on a non-empty gap set); a single
    ``{'present': True}`` row otherwise (the recorded PASS evidence)."""
    dataset: list[dict[str, Any]] = (
        [{"present": None} for _ in gaps] if gaps else [{"present": True}]
    )
    run_quality_check(
        session,
        rule=rule,
        dataset=dataset,
        actor_id=actor_id,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        actor_type=actor_type,
    )
