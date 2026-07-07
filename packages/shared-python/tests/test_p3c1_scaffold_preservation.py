"""P3-C1 golden scaffold-preservation proofs (OD-P3-C1-D — the R0 behavior-preservation bar).

For EACH of the four risk binders, one COMPLETED and one FAILED scenario asserting the exact
governed-run lifecycle shape: the ORDERED ``CALC.*`` audit sequence (event type, action,
before/after status, outcome), the lineage-edge sets (exactly one snapshot→run DEPENDS_ON —
present on FAILED runs too; run→result ORIGIN count == result-row count, ZERO on FAILED), the
DQ evidence on FAILED, and each binder's ``failure_reason`` FORMAT verbatim.

**These assertions were written against the PRE-extraction binders and ran green BEFORE
`risk/scaffold.py` existed** (the golden capture the plan mandates); the extraction must keep
them green unchanged. Fixtures are IMPORTED from the per-binder suites (this is the
consolidation slice — no fifth copy of the seeding).
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# The per-binder suites' fixtures (importable — the tests dir is package-less by design).
from test_covariance import _abc as _cov_factors
from test_covariance import _model as _cov_model
from test_covariance import _run as _cov_run
from test_factor_exposure import _ccy as _fx_ccy
from test_factor_exposure import _exposure_run as _fx_exposure_run
from test_factor_exposure import _factor as _fx_factor
from test_factor_exposure import _model as _fx_model
from test_factor_exposure import _run as _fx_run
from test_sensitivity import _curve as _sens_curve
from test_sensitivity import _model as _sens_model
from test_sensitivity import _run as _sens_run
from test_sensitivity import _sel as _sens_sel
from test_sensitivity import _zero_nodes
from test_var import (
    _covariance_content,
    _exposure_content,
    _mint_var_snapshot,
    _var_model,
)
from test_var import _run as _var_run
from test_var import _seed_upstream_runs as _var_seed

from irp_shared.audit.models import AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.models import DataQualityResult
from irp_shared.lineage.models import (
    EDGE_KIND_DEPENDENCY,
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    SOURCE_TYPE_DATA_SNAPSHOT,
    LineageEdge,
)
from irp_shared.marketdata import CurveNode
from irp_shared.models import Base


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


#: The golden lifecycle sequences (captured from the PRE-extraction binders).
_COMPLETED_SEQUENCE = [
    ("CALC.RUN_CREATE", "create", None, "CREATED", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "CREATED", "RUNNING", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "RUNNING", "COMPLETED", "success"),
]
_FAILED_SEQUENCE = [
    ("CALC.RUN_CREATE", "create", None, "CREATED", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "CREATED", "RUNNING", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "RUNNING", "FAILED", "failure"),
]


def _lifecycle(session: Session, run_id: str) -> list[tuple]:
    rows = (
        session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "calculation_run",
                AuditEvent.entity_id == run_id,
            )
            .order_by(AuditEvent.sequence_no)
        )
        .scalars()
        .all()
    )
    out = []
    for e in rows:
        before = (e.before_value or {}).get("status")
        after = (e.after_value or {}).get("status")
        out.append((e.event_type, e.action, before, after, e.outcome))
    return out


def _assert_edges(
    session: Session,
    run_id: str,
    *,
    snapshot_id: str,
    result_entity_type: str,
    expected_row_ids: set[str],
) -> None:
    """Pin lineage CONTENT, not just cardinality (the 2026-07 review fold): the DEPENDS_ON edge
    must source the CONSUMED snapshot and stamp the run; every ORIGIN edge must carry the
    binder's result entity type, the run stamp, and target exactly the persisted row ids."""
    depends = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_DATA_SNAPSHOT,
                LineageEdge.target_entity_type == "calculation_run",
                LineageEdge.target_entity_id == run_id,
                LineageEdge.edge_kind == EDGE_KIND_DEPENDENCY,
            )
        )
        .scalars()
        .all()
    )
    assert len(depends) == 1
    assert depends[0].source_id == snapshot_id and depends[0].run_id == run_id
    origins = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_CALCULATION_RUN,
                LineageEdge.source_id == run_id,
                LineageEdge.edge_kind == EDGE_KIND_ORIGIN,
            )
        )
        .scalars()
        .all()
    )
    assert {e.target_entity_id for e in origins} == expected_row_ids
    assert all(e.target_entity_type == result_entity_type for e in origins)
    assert all(e.run_id == run_id for e in origins)


def _assert_dq_evidence(
    session: Session, run_id: str, *, rule_code: str, rule_name: str, rule_target: str
) -> None:
    """Pin the DQ evidence CONTENT (the 2026-07 review fold): the persisted rows must reference
    THE binder's governed rule — code, name, and target_entity_type verbatim (these strings
    became scaffold call-site parameters in the extraction; a typo would mint a different
    per-tenant rule row with counts unchanged)."""
    from irp_shared.dq.models import DataQualityRule

    results = (
        session.execute(
            select(DataQualityResult).where(
                DataQualityResult.target_entity_type == "calculation_run",
                DataQualityResult.target_entity_id == run_id,
            )
        )
        .scalars()
        .all()
    )
    assert results
    rule_ids = {r.rule_id for r in results}
    assert len(rule_ids) == 1
    rule = session.execute(
        select(DataQualityRule).where(DataQualityRule.id == next(iter(rule_ids)))
    ).scalar_one()
    assert rule.code == rule_code
    assert rule.name == rule_name
    assert rule.target_entity_type == rule_target


def _assert_completed_shape(session: Session, result, *, result_entity_type: str) -> None:  # noqa: ANN001
    run = result.run
    assert _lifecycle(session, run.run_id) == _COMPLETED_SEQUENCE
    _assert_edges(
        session,
        run.run_id,
        snapshot_id=run.input_snapshot_id,
        result_entity_type=result_entity_type,
        expected_row_ids={r.id for r in result.rows},
    )
    # COMPLETED runs carry no persisted reason.
    run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == run.run_id)
    ).scalar_one()
    assert run_row.failure_reason is None


def _assert_failed_shape(
    session: Session,
    result,  # noqa: ANN001
    pattern: str,
    *,
    result_entity_type: str,
    rule_code: str,
    rule_name: str,
    rule_target: str,
) -> None:
    run = result.run
    reason = result.failure_reason
    assert _lifecycle(session, run.run_id) == _FAILED_SEQUENCE
    _assert_edges(  # DEPENDS_ON kept; ZERO result ORIGINs
        session,
        run.run_id,
        snapshot_id=run.input_snapshot_id,
        result_entity_type=result_entity_type,
        expected_row_ids=set(),
    )
    _assert_dq_evidence(
        session, run.run_id, rule_code=rule_code, rule_name=rule_name, rule_target=rule_target
    )
    assert reason and re.search(pattern, reason), (pattern, reason)
    # The reason is PERSISTED verbatim on the run row (OD-C — per binder, the review fold).
    run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == run.run_id)
    ).scalar_one()
    assert run_row.failure_reason == reason


# ---------- sensitivity (P3-1) ----------


def test_golden_sensitivity_completed_and_failed(session: Session) -> None:
    from test_sensitivity import _ccy as _sens_ccy

    tenant = str(uuid.uuid4())
    _sens_ccy(session, "USD")
    _sens_curve(session, tenant, nodes=_zero_nodes())
    mv = _sens_model(session, tenant)
    session.flush()
    ok = _sens_run(session, tenant, mv, [_sens_sel()])
    assert ok.status == RunStatus.COMPLETED.value
    _assert_completed_shape(session, ok, result_entity_type="sensitivity_result")

    tenant2 = str(uuid.uuid4())
    _sens_curve(  # PAR_RATE-only: no usable node -> the fail-closed DQ gate
        session,
        tenant2,
        nodes=[
            CurveNode(
                tenor_label="1Y", tenor_days=365, value_type="PAR_RATE", point_value=Decimal("0.05")
            )
        ],
    )
    mv2 = _sens_model(session, tenant2)
    session.flush()
    bad = _sens_run(session, tenant2, mv2, [_sens_sel()])
    assert bad.status == RunStatus.FAILED.value
    # The P3-1 reason format is str(gate) — the BARE DataQualityError text, pinned precisely
    # (the 2026-07 review fold: the old alternation pattern was vacuous): it must NOT carry the
    # other binders' " — detail" suffix shape.
    assert bad.failure_reason and " — " not in bad.failure_reason
    _assert_failed_shape(
        session,
        bad,
        r"^rule 'risk\.sensitivity\.completeness' failed \(severity=ERROR\)$",
        result_entity_type="sensitivity_result",
        rule_code="risk.sensitivity.completeness",
        rule_name="Sensitivity run input completeness (usable curve nodes)",
        rule_target="sensitivity_result",
    )


# ---------- factor exposure (P3-3) ----------


def test_golden_factor_exposure_completed_and_failed(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _fx_ccy(session, "USD")
    exp_run = _fx_exposure_run(session, tenant, [("100", "10.00", "USD")])
    usd_factor = _fx_factor(session, tenant, "FX_USD", "USD")
    mv = _fx_model(session, tenant)
    session.flush()
    ok = _fx_run(session, tenant, mv, exp_run, [usd_factor])
    assert ok.status == RunStatus.COMPLETED.value
    _assert_completed_shape(session, ok, result_entity_type="factor_exposure_result")

    tenant2 = str(uuid.uuid4())
    _fx_ccy(session, "EUR")
    exp_run2 = _fx_exposure_run(session, tenant2, [("100", "10.00", "USD")])
    eur_factor = _fx_factor(session, tenant2, "FX_EUR", "EUR")  # USD atom unmapped
    mv2 = _fx_model(session, tenant2)
    session.flush()
    bad = _fx_run(session, tenant2, mv2, exp_run2, [eur_factor])
    assert bad.status == RunStatus.FAILED.value
    # The factor-exposure reason format: "{gate} — {detail}{more}" naming unmapped atoms.
    _assert_failed_shape(
        session,
        bad,
        r" — unmapped-atom:.*:USD",
        result_entity_type="factor_exposure_result",
        rule_code="risk.factor_exposure.completeness",
        rule_name=(
            "Factor-exposure run mapping completeness (every atom maps to exactly one factor)"
        ),
        rule_target="factor_exposure_result",
    )


# ---------- covariance (P3-4) ----------


def test_golden_covariance_completed_and_failed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = str(uuid.uuid4())
    factors = _cov_factors(session, tenant)
    mv = _cov_model(session, tenant, window=4)
    ok = _cov_run(session, tenant, mv, factors)
    assert ok.status == RunStatus.COMPLETED.value
    _assert_completed_shape(session, ok, result_entity_type="covariance_result")

    # The covariance defensive gate is unreachable naturally — the kernel seam (the P3-4
    # test pattern) drives the FAILED lifecycle.
    import irp_shared.risk.covariance_service as cs

    real = cs.estimate_covariance

    def poisoned(series):  # noqa: ANN001, ANN202
        out = real(series)
        out[sorted(out)[0]] = Decimal("-1")
        return out

    monkeypatch.setattr(cs, "estimate_covariance", poisoned)
    tenant2 = str(uuid.uuid4())
    factors2 = _cov_factors(session, tenant2)
    mv2 = _cov_model(session, tenant2, window=4)
    bad = _cov_run(session, tenant2, mv2, factors2)
    assert bad.status == RunStatus.FAILED.value
    # The covariance reason format: "{gate} — {detail}{more}" naming the defect class.
    _assert_failed_shape(
        session,
        bad,
        r" — negative-variance:",
        result_entity_type="covariance_result",
        rule_code="risk.covariance.completeness",
        rule_name=(
            "Covariance run output sanity (every element finite; every variance non-negative)"
        ),
        rule_target="covariance_result",
    )


# ---------- VaR (P3-5) ----------


def test_golden_var_completed_and_failed(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _var_seed(session, tenant)
    mv = _var_model(session, tenant)
    ok = _var_run(session, tenant, mv, fx_run, cov_run)
    assert ok.status == RunStatus.COMPLETED.value
    _assert_completed_shape(session, ok, result_entity_type="var_result")

    # The REACHABLE non-PSD FAILED path (a hand-minted snapshot; real provenance runs).
    tenant2 = str(uuid.uuid4())
    exp2, cov2 = _var_seed(session, tenant2)
    mv2 = _var_model(session, tenant2)
    fa, fb = sorted(str(uuid.uuid4()).lower() for _ in range(2))
    snap = _mint_var_snapshot(
        session,
        tenant2,
        [
            _exposure_content(exp2, fa, "A", "1.000000"),
            _exposure_content(exp2, fb, "B", "-1.000000"),
        ],
        [
            _covariance_content(cov2, fa, fa, "0.0001"),
            _covariance_content(cov2, fb, fb, "0.0001"),
            _covariance_content(cov2, fa, fb, "0.0002"),  # non-PSD
        ],
    )
    bad = _var_run(session, tenant2, mv2, None, None, snapshot_id=snap.id)
    assert bad.status == RunStatus.FAILED.value
    # The VaR reason format: "{gate} — {'; '.join(gaps)}" naming the radicand defect.
    _assert_failed_shape(
        session,
        bad,
        r" — non-psd-radicand:",
        result_entity_type="var_result",
        rule_code="risk.var.completeness",
        rule_name="VaR run output sanity (radicand within the declared PSD quantization floor)",
        rule_target="var_result",
    )
