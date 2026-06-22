"""Data-quality endpoints (REQ-DQR-001): one gated write + three reads.

`POST /dq/rules` registers a DQ rule (gated `dq.rule.manage`); it **never** reads `tenant_id` from
the body (server-stamped; a forged value is ignored and backstopped by RLS `WITH CHECK`). Reads are
RLS-scoped to the caller's tenant; a cross-tenant/unknown id yields an **indistinguishable 404**.
There is **no** public rule-execution endpoint — running checks is an in-process utility a future
P1A-4 ingestion calls. No reconciliation/override/dashboard surface.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.dq.service import register_dq_rule
from irp_shared.entitlement.service import Principal

router = APIRouter(prefix="/dq", tags=["data-quality"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_manage = require_permission("dq.rule.manage")
_require_view = require_permission("dq.result.view")


class CreateRuleIn(BaseModel):
    code: str
    name: str
    rule_type: str
    params: dict = Field(default_factory=dict)
    target_entity_type: str | None = None
    severity: str = "ERROR"  # recorded; drives raise-vs-flag at run time (non-enforcing on create)


class RuleOut(BaseModel):
    id: str
    code: str
    name: str
    rule_type: str
    severity: str
    is_active: bool
    target_entity_type: str | None
    params: dict


class RuleSummary(BaseModel):
    id: str
    code: str
    name: str
    rule_type: str
    severity: str
    is_active: bool


class ResultOut(BaseModel):
    id: str
    rule_id: str
    outcome: str
    passed: bool
    detail: str | None
    target_entity_type: str | None
    target_entity_id: str | None


@router.post("/rules", status_code=status.HTTP_201_CREATED, response_model=RuleOut)
def create_rule(
    body: CreateRuleIn,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> RuleOut:
    rule = register_dq_rule(
        db,
        tenant_id=principal.tenant_id,  # server-stamped; body tenant_id (if any) is ignored
        code=body.code,
        name=body.name,
        rule_type=body.rule_type,
        actor_id=principal.user_id,
        params=body.params,
        target_entity_type=body.target_entity_type,
        severity=body.severity,
    )
    db.commit()  # end-of-request commit (no further work; honors the single-transaction invariant)
    return _rule_out(rule)


@router.get("/rules", response_model=list[RuleSummary])
def list_rules(
    _: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> list[RuleSummary]:
    rows = db.execute(select(DataQualityRule).order_by(DataQualityRule.code)).scalars().all()
    return [
        RuleSummary(
            id=r.id,
            code=r.code,
            name=r.name,
            rule_type=r.rule_type,
            severity=r.severity,
            is_active=r.is_active,
        )
        for r in rows
    ]


@router.get("/rules/{rule_id}", response_model=RuleOut)
def get_rule(
    rule_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit (no 500 / oracle)
    _: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> RuleOut:
    rule = db.get(DataQualityRule, str(rule_id))
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule not found")
    return _rule_out(rule)


@router.get("/results", response_model=list[ResultOut])
def list_results(
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ResultOut]:
    rows = (
        db.execute(select(DataQualityResult).order_by(DataQualityResult.system_from.desc()))
        .scalars()
        .all()
    )
    return [
        ResultOut(
            id=r.id,
            rule_id=r.rule_id,
            outcome=r.outcome,
            passed=r.passed,
            detail=r.detail,
            target_entity_type=r.target_entity_type,
            target_entity_id=r.target_entity_id,
        )
        for r in rows
    ]


def _rule_out(rule: DataQualityRule) -> RuleOut:
    return RuleOut(
        id=rule.id,
        code=rule.code,
        name=rule.name,
        rule_type=rule.rule_type,
        severity=rule.severity,
        is_active=rule.is_active,
        target_entity_type=rule.target_entity_type,
        params=rule.params,
    )
