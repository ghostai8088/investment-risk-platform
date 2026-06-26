"""SQLite-local unit/behavior tests for the data quality skeleton (P1A-3).

RLS is a no-op on SQLite, so isolation/fail-closed proofs live in ``test_data_quality_pg.py``; here
we prove model/temporal/utility behavior, audit emission, the **no-silent-failure** contract (the
headline), the ``assert_passed_quality_checks`` gate, IA immutability vs the EV rule head,
genericity, and the service-boundary (import-direction) guarantee.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.dq.rules import (
    REGISTRY,
    RULE_TYPE_ALLOWED_VALUES,
    RULE_TYPE_NOT_NULL,
    RULE_TYPE_RANGE,
)
from irp_shared.dq.service import (
    DQ_RULE_DEFINE_EVENT,
    DQ_RULE_UPDATE_EVENT,
    DQ_VALIDATE_EVENT,
    DataQualityError,
    QualityCheckFailedError,
    assert_passed_quality_checks,
    register_dq_rule,
    run_quality_check,
    update_dq_rule,
)
from irp_shared.temporal import TemporalClass


def _tenant() -> str:
    return str(uuid.uuid4())


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _rule(
    session: Session,
    tenant: str,
    *,
    code: str = "R1",
    rule_type: str = RULE_TYPE_NOT_NULL,
    severity: str = "ERROR",
    params: dict | None = None,
) -> DataQualityRule:
    return register_dq_rule(
        session,
        tenant_id=tenant,
        code=code,
        name="A rule",
        rule_type=rule_type,
        actor_id="steward",
        params=params if params is not None else {"column": "x"},
        target_entity_type="synthetic.t",
        severity=severity,
    )


def test_temporal_classes() -> None:
    assert DataQualityRule.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
    assert hasattr(DataQualityRule, "valid_from") and hasattr(DataQualityRule, "record_version")
    assert DataQualityResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    assert hasattr(DataQualityResult, "system_from")
    assert not hasattr(DataQualityResult, "valid_to")  # IA single axis (TR-21)


def test_register_rule_and_constraints(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, code="DUP")
    assert rule.tenant_id == tenant
    assert rule.approval_status is None and rule.made_by is None  # DR-P1-3 hooks default null
    assert rule.params == {"column": "x"}
    _rule(session, _tenant(), code="DUP")  # same code, other tenant OK
    session.flush()
    session.add(DataQualityRule(tenant_id=tenant, code="DUP", name="n", rule_type="NOT_NULL"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_generic_rule_type_needs_no_schema_branch(session: Session) -> None:
    # Genericity: an arbitrary rule_type string persists (no enum/CHECK) — new families by value.
    rule = _rule(session, _tenant(), rule_type="SOME_FUTURE_GENERIC_KIND")
    assert rule.rule_type == "SOME_FUTURE_GENERIC_KIND"


def test_not_null_and_allowed_values_pass(session: Session) -> None:
    tenant = _tenant()
    nn = _rule(session, tenant, code="NN", params={"column": "x"})
    result = run_quality_check(session, rule=nn, dataset=[{"x": 1}, {"x": 2}], actor_id="a")
    assert result.outcome == "PASS" and result.passed is True
    assert session.get(DataQualityResult, result.id) is not None
    av = _rule(
        session,
        tenant,
        code="AV",
        rule_type=RULE_TYPE_ALLOWED_VALUES,
        params={"column": "ccy", "allowed": ["USD", "EUR"]},
    )
    ok = run_quality_check(session, rule=av, dataset=[{"ccy": "USD"}], actor_id="a")
    assert ok.outcome == "PASS"


# --- NO-SILENT-FAILURE (the headline; CTRL-029 / QS-15/16/06 / BR-14) ---


def test_error_severity_failure_persists_and_raises(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})  # severity=ERROR
    with pytest.raises(DataQualityError) as exc:
        run_quality_check(session, rule=rule, dataset=[{"x": 1}, {"x": None}], actor_id="a")
    # A flagged result is persisted (never silently passes) AND the failure is raised.
    result = exc.value.result
    assert result is not None and result.passed is False and result.outcome == "FAIL"
    assert session.get(DataQualityResult, result.id) is not None


def test_allowed_values_failure_raises(session: Session) -> None:
    rule = _rule(
        session,
        _tenant(),
        rule_type=RULE_TYPE_ALLOWED_VALUES,
        params={"column": "ccy", "allowed": ["USD"]},
    )
    with pytest.raises(DataQualityError):
        run_quality_check(session, rule=rule, dataset=[{"ccy": "ZZZ"}], actor_id="a")


def test_warning_severity_flags_without_raising(session: Session) -> None:
    rule = _rule(session, _tenant(), severity="WARNING", params={"column": "x"})
    result = run_quality_check(session, rule=rule, dataset=[{"x": None}], actor_id="a")
    assert result.outcome == "WARN" and result.passed is False  # flagged, not raised


def test_evaluation_error_propagates_and_is_audited(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={})  # missing "column" -> evaluator raises
    before = _events(session, DQ_VALIDATE_EVENT)
    with pytest.raises(DataQualityError):
        run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    assert _events(session, DQ_VALIDATE_EVENT) == before + 1  # audited, not swallowed
    ev = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == DQ_VALIDATE_EVENT)
            .order_by(AuditEvent.sequence_no.desc())
        )
        .scalars()
        .first()
    )
    assert ev.outcome == "failure"


def test_positive_control_clean_target_passes(session: Session) -> None:
    # Pairs with the FAIL tests to defeat a stuck/vacuous PASS or FAIL.
    rule = _rule(session, _tenant(), params={"column": "x"})
    result = run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    assert result.outcome == "PASS" and result.passed is True


# --- assert_passed_quality_checks gate (synthetic target) ---


def test_gate_raises_when_no_checks_recorded(session: Session) -> None:
    with pytest.raises(QualityCheckFailedError):
        assert_passed_quality_checks(session, "synthetic.t", str(uuid.uuid4()))


def test_gate_raises_on_failed_check(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})
    target = str(uuid.uuid4())
    with pytest.raises(DataQualityError):
        run_quality_check(
            session,
            rule=rule,
            dataset=[{"x": None}],
            actor_id="a",
            target_entity_type="synthetic.t",
            target_entity_id=target,
        )
    with pytest.raises(QualityCheckFailedError):
        assert_passed_quality_checks(session, "synthetic.t", target)


def test_gate_passes_after_pass(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})
    target = str(uuid.uuid4())
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"x": 1}],
        actor_id="a",
        target_entity_type="synthetic.t",
        target_entity_id=target,
    )
    assert assert_passed_quality_checks(session, "synthetic.t", target)


def test_gate_is_tenant_scoped(session: Session) -> None:
    tenant_a = _tenant()
    rule = _rule(session, tenant_a, params={"column": "x"})
    target = str(uuid.uuid4())
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"x": 1}],
        actor_id="a",
        target_entity_type="synthetic.t",
        target_entity_id=target,
    )
    with pytest.raises(QualityCheckFailedError):
        assert_passed_quality_checks(session, "synthetic.t", target, tenant_id=_tenant())
    assert assert_passed_quality_checks(session, "synthetic.t", target, tenant_id=tenant_a)


# --- IA immutability + EV mutable contrast + audit + fail-closed + scope fence ---


def test_result_is_append_only(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})
    result = run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    session.commit()
    fetched = session.get(DataQualityResult, result.id)
    fetched.detail = "tampered"
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    fetched = session.get(DataQualityResult, result.id)
    session.delete(fetched)
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_rule_is_mutable_ev(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})
    updated = update_dq_rule(session, rule, actor_id="steward", severity="WARNING", is_active=False)
    assert updated.severity == "WARNING" and updated.is_active is False
    assert updated.record_version == 2


def test_rule_update_rejects_unknown_attribute(session: Session) -> None:
    rule = _rule(session, _tenant(), params={"column": "x"})
    with pytest.raises(ValueError, match="non-updatable"):
        update_dq_rule(session, rule, actor_id="s", tenant_id="other")


def test_audit_define_update_validate(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})
    defs = (
        session.execute(select(AuditEvent).where(AuditEvent.entity_id == rule.id)).scalars().all()
    )
    assert len(defs) == 1 and defs[0].event_type == DQ_RULE_DEFINE_EVENT
    update_dq_rule(session, rule, actor_id="s", severity="WARNING")
    upd = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == rule.id, AuditEvent.event_type == DQ_RULE_UPDATE_EVENT
            )
        )
        .scalars()
        .all()
    )
    assert len(upd) == 1 and upd[0].before_value["severity"] == "ERROR"
    before = _events(session, DQ_VALIDATE_EVENT)
    run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    assert _events(session, DQ_VALIDATE_EVENT) == before + 1
    # Positive control: a PASS run audits outcome='success' (the FAIL path asserts 'failure').
    latest = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == DQ_VALIDATE_EVENT)
            .order_by(AuditEvent.sequence_no.desc())
        )
        .scalars()
        .first()
    )
    assert latest.outcome == "success"
    assert verify_chain(session, tenant).ok is True


def _raise_audit(*_a: object, **_k: object) -> None:
    raise RuntimeError("audit capture failed")


def test_rule_create_rolls_back_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.dq.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    tenant = _tenant()
    with pytest.raises(RuntimeError):
        register_dq_rule(
            session, tenant_id=tenant, code="X", name="n", rule_type="NOT_NULL", actor_id="s"
        )
    session.rollback()
    assert (
        session.execute(
            select(func.count())
            .select_from(DataQualityRule)
            .where(DataQualityRule.tenant_id == tenant)
        ).scalar_one()
        == 0
    )


def test_run_rolls_back_when_audit_fails(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # Fail-closed on the RUN path too (AUD-04/CTRL-032): if the DATA.VALIDATE audit insert fails,
    # the data_quality_result row must NOT persist.
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})  # real audit on define
    session.commit()
    before = session.execute(select(func.count()).select_from(DataQualityResult)).scalar_one()

    import irp_shared.dq.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    session.rollback()
    assert (
        session.execute(select(func.count()).select_from(DataQualityResult)).scalar_one() == before
    )


def test_warning_rule_with_evaluator_error_still_raises(session: Session) -> None:
    # An evaluator error escalates past WARNING (no silent flag-and-continue): it FAILs and raises.
    rule = _rule(session, _tenant(), severity="WARNING", params={})  # missing column -> error
    with pytest.raises(DataQualityError) as exc:
        run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    assert exc.value.result is not None and exc.value.result.outcome == "FAIL"


def test_scope_fence_no_reserved_codes_or_columns(session: Session) -> None:
    tenant = _tenant()
    rule = _rule(session, tenant, params={"column": "x"})
    run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
    for code in ("DATA.RECONCILE", "DATA.CORRECTION", "CONFIG.CHANGE"):
        assert _events(session, code) == 0
    cols = set(DataQualityResult.__table__.columns.keys())
    for forbidden in ("override", "waive", "disposition", "resolution", "acknowledg"):
        assert not any(
            forbidden in c for c in cols
        ), f"unexpected workflow column matching {forbidden}"
    # exactly three generic evaluators (RANGE added P2-2 for strictly-positive FX rates)
    assert set(REGISTRY) == {RULE_TYPE_NOT_NULL, RULE_TYPE_ALLOWED_VALUES, RULE_TYPE_RANGE}


def test_dq_package_has_no_forbidden_imports() -> None:
    # Parse the imported module path and match on dotted-component boundaries so 'irp_shared.model'
    # does NOT false-match the legitimate 'irp_shared.models' aggregator (which is itself forbidden
    # here, but for the right reason). Covers lineage/model/ingestion/backend.
    import irp_shared.dq as dq_pkg

    forbidden = ("irp_shared.lineage", "irp_shared.model", "irp_shared.ingestion", "irp_backend")
    dq_dir = pathlib.Path(dq_pkg.__file__).parent
    for py in sorted(dq_dir.glob("*.py")):
        for line in py.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("from "):
                mod = stripped.split()[1]
            elif stripped.startswith("import "):
                mod = stripped.split()[1].split(",")[0]
            else:
                continue
            for root in forbidden:
                assert mod != root and not mod.startswith(root + "."), f"{py.name} imports {mod}"
