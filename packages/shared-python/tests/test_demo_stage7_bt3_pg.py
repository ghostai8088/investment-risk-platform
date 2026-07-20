"""BT-3 stage-7 PG tier: the seeded end state — the domain-gate honesty LIVE (Z evidence rows +
NO off-domain verdict), the shared-snapshot sibling pairing per as-of, the Christoffersen live
verdicts, the four INITIALs (NO TRIGGERED — the recorded honesty), and the 19-code end state.
Runs AFTER the stage-6 step and BEFORE the downgrade smoke in CI (the smoke then exercises
0043's downgrade against THIS stage's rows every run)."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DemoBt3AlreadySeededError,
    run_demo_bt3_stage7,
    run_demo_campaign,
    run_demo_ds2_stage6,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
    run_demo_rs1_stage5,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID, DemoCampaignAlreadySeededError
from irp_shared.demo.ds2_stage6 import DemoDs2AlreadySeededError
from irp_shared.demo.eshs_stage4 import DemoEshsAlreadySeededError
from irp_shared.demo.hg1_private import DemoHg1AlreadySeededError
from irp_shared.demo.multifamily import DemoMultifamilyAlreadySeededError
from irp_shared.demo.rs1_stage5 import DemoRs1AlreadySeededError
from irp_shared.model.models import Model, ModelValidation, ModelVersion
from irp_shared.risk.models import VarBacktestResult, VarResult

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def factory():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    session_factory = make_session_factory(engine)
    session = session_factory()
    try:
        for runner, refusal in (
            (run_demo_campaign, DemoCampaignAlreadySeededError),
            (run_demo_multifamily_extension, DemoMultifamilyAlreadySeededError),
            (run_demo_hg1_private, DemoHg1AlreadySeededError),
            (run_demo_eshs_stage4, DemoEshsAlreadySeededError),
            (run_demo_rs1_stage5, DemoRs1AlreadySeededError),
            (run_demo_ds2_stage6, DemoDs2AlreadySeededError),
            (run_demo_bt3_stage7, DemoBt3AlreadySeededError),
        ):
            try:
                runner(session)
                session.commit()
            except refusal:
                session.rollback()
    finally:
        session.close()
    yield session_factory
    engine.dispose()


@pytest.fixture()
def db(factory) -> Session:  # noqa: ANN001
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    yield session
    session.close()


def _es_bt_rows(db: Session) -> dict[str, list[VarBacktestResult]]:
    rows = (
        db.execute(
            select(VarBacktestResult).where(
                VarBacktestResult.tenant_id == DEMO_TENANT_ID,
                VarBacktestResult.var_metric_type == "ES_HISTORICAL",
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[VarBacktestResult]] = {}
    for r in rows:
        out.setdefault(r.metric_type, []).append(r)
    return out


def test_second_stage7_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoBt3AlreadySeededError):
        run_demo_bt3_stage7(db)
    db.rollback()


def test_nineteen_codes_and_the_new_versions(db: Session) -> None:
    codes = db.execute(select(Model.code).where(Model.tenant_id == DEMO_TENANT_ID)).all()
    assert len(codes) == 19  # stage 7 mints exactly ONE code: risk.es_backtest
    labels = {
        (m, v)
        for m, v in db.execute(
            select(Model.code, ModelVersion.version_label)
            .join(ModelVersion, ModelVersion.model_id == Model.id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code.in_(
                    (
                        "risk.es_backtest",
                        "risk.var_backtest",
                        "risk.var.historical",
                        "risk.var.historical_es",
                    ),
                ),
            )
        ).all()
    }
    for pair in (
        ("risk.es_backtest", "v1"),
        ("risk.var_backtest", "v2-christoffersen"),
        ("risk.var.historical", "v1-c975"),
        ("risk.var.historical_es", "v1-c975"),
    ):
        assert pair in labels, pair


def test_domain_gate_honesty_live(db: Session) -> None:
    """The LIVE demonstration: Z̄2 = -127.09 at T=3 — enormous, and the verdict is CORRECTLY
    ABSENT (an un-gated -0.70 read would spuriously REJECT the flagship ES; the T-dependence
    HIGH made concrete). The exact pins are the drift tripwire."""
    rows = _es_bt_rows(db)
    (z2,) = rows["AS_Z2"]
    assert z2.metric_value == Decimal("-127.092090")
    assert z2.test_decision is None  # OFF the (0.9750, 250) domain — no verdict, ever
    (z1,) = rows["AS_Z1"]
    assert z1.metric_value == Decimal("-8.606907")
    assert z1.test_decision is None  # Z1 is evidence, never a verdict
    (count,) = rows["ES_PAIR_COUNT"]
    assert count.metric_value == Decimal("3.000000")
    assert count.n_pairs == 3 and count.n_exceptions == 1
    indicators = rows["ES_EXCEPTION_INDICATOR"]
    assert len(indicators) == 3
    breached = [r for r in indicators if r.metric_value == Decimal("1.000000")]
    assert len(breached) == 1
    # The designed 2026-05-22→23 drawdown is the exception, with the es_value echo present.
    assert str(breached[0].period_start) == "2026-05-22"
    assert breached[0].es_value is not None and breached[0].es_value > 0
    for r in indicators:
        if r is not breached[0]:
            assert r.es_value is not None  # every pair row echoes what it tested against


def test_sibling_pairs_share_snapshots_per_asof(db: Session) -> None:
    """The pairing design input LIVE per pair: at each as-of the VaR-HS and ES-HS c975 rows
    share ONE input_snapshot_id."""
    rows = (
        db.execute(
            select(VarResult)
            .join(ModelVersion, ModelVersion.id == VarResult.model_version_id)
            .where(
                VarResult.tenant_id == DEMO_TENANT_ID,
                ModelVersion.version_label == "v1-c975",
            )
        )
        .scalars()
        .all()
    )
    by_asof: dict[str, dict[str, str]] = {}
    for r in rows:
        by_asof.setdefault(str(r.window_end), {})[r.metric_type] = str(r.input_snapshot_id)
    assert sorted(by_asof) == ["2026-05-21", "2026-05-22", "2026-05-23"]
    for as_of, legs in by_asof.items():
        assert set(legs) == {"VAR_HISTORICAL", "ES_HISTORICAL"}, as_of
        assert legs["VAR_HISTORICAL"] == legs["ES_HISTORICAL"], as_of


def test_christoffersen_live_verdicts_and_cc_composition(db: Session) -> None:
    """The v2 rows — the LIVE decomposition lesson: at n=3 NEITHER component alone rejects
    (KUPIEC_LR ~3.66 < 3.841; LR_IND ~2.77 < 3.841) but the JOINT LR_CC (~6.43 > 5.991,
    chi-square(2)) DOES — the conditional-coverage composition genuinely adds power;
    LR_CC == LR_UC + LR_IND on the STORED values."""
    rows = (
        db.execute(
            select(VarBacktestResult)
            .join(ModelVersion, ModelVersion.id == VarBacktestResult.model_version_id)
            .where(
                VarBacktestResult.tenant_id == DEMO_TENANT_ID,
                ModelVersion.version_label == "v2-christoffersen",
            )
        )
        .scalars()
        .all()
    )
    by_type = {r.metric_type: r for r in rows if r.metric_type in ("LR_IND", "LR_CC", "KUPIEC_LR")}
    assert set(by_type) == {"LR_IND", "LR_CC", "KUPIEC_LR"}
    assert by_type["LR_IND"].test_decision == "FAIL_TO_REJECT"
    assert by_type["LR_CC"].test_decision == "REJECT"
    assert by_type["KUPIEC_LR"].test_decision == "FAIL_TO_REJECT"  # the joint test's added power
    assert (
        by_type["LR_CC"].metric_value
        == by_type["KUPIEC_LR"].metric_value + by_type["LR_IND"].metric_value
    )


def test_four_initials_no_triggered(db: Session) -> None:
    """The RS-1 new-version-INITIAL precedent applied UNIFORMLY; NO TRIGGERED (census-proved
    no closable condition names the backtest gap — the DS-2 honesty pattern)."""
    validations = db.execute(
        select(ModelValidation.validation_type, ModelVersion.version_label, Model.code)
        .join(ModelVersion, ModelVersion.id == ModelValidation.model_version_id)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(
            ModelValidation.tenant_id == DEMO_TENANT_ID,
            ModelVersion.code_version == "demo-bt3",
        )
    ).all()
    assert len(validations) == 4
    assert {v[0] for v in validations} == {"INITIAL"}
    assert {(v[2], v[1]) for v in validations} == {
        ("risk.es_backtest", "v1"),
        ("risk.var_backtest", "v2-christoffersen"),
        ("risk.var.historical", "v1-c975"),
        ("risk.var.historical_es", "v1-c975"),
    }
    total = db.execute(
        select(ModelValidation).where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).all()
    assert len(total) == 34  # 30 through stage 6 + the four BT-3 INITIALs


def test_seven_stage_end_state_run_census(db: Session) -> None:
    completed = db.execute(
        select(CalculationRun.run_type).where(
            CalculationRun.tenant_id == DEMO_TENANT_ID, CalculationRun.status == "COMPLETED"
        )
    ).all()
    assert len(completed) == 95  # 87 through stage 6 + 6 sibling forecasts + 2 backtests
    types = [r[0] for r in completed]
    assert types.count("ES_BACKTEST") == 1
    assert types.count("VAR_BACKTEST") == 3  # campaign BT-1 + BT-2 + the stage-7 v2
