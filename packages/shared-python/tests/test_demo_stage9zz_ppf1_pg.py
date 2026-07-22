"""PPF-1 stage-11 PG tier: the pure-private factor return POOLED live on the tenant over the seeded
private substrate (ZERO new book data). GOVERNED-NUMBER — the counts move by exactly ONE new model
code + ONE INITIAL validation + TWO COMPLETED runs (20/35/101 → 21/36/103), the CC-2 contrast with
stage 10's runs-only. Runs AFTER the stage-10 (``stage9z``) step and BEFORE the downgrade smoke.

The ``stage9zz`` filename collates AFTER ``test_demo_stage9z_api1_reads*`` (last among the demo
stage suites) so a single-invocation local PG battery seeds these two extra runs LAST — a two-digit
``stage11`` name sorts before ``stage2``/``stage4`` and would corrupt the earlier stages' pins."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DemoBt3AlreadySeededError,
    DemoCampaignAlreadySeededError,
    DemoCc1AlreadySeededError,
    DemoCc2AlreadySeededError,
    DemoDs2AlreadySeededError,
    DemoEshsAlreadySeededError,
    DemoHg1AlreadySeededError,
    DemoMultifamilyAlreadySeededError,
    DemoPpf1AlreadySeededError,
    DemoRs1AlreadySeededError,
    DemoStage10AlreadySeededError,
    run_demo_bt3_stage7,
    run_demo_campaign,
    run_demo_cc1_stage8,
    run_demo_cc2_stage9,
    run_demo_ds2_stage6,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
    run_demo_ppf1_stage11,
    run_demo_rs1_stage5,
    run_demo_stage10_api1,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.marketdata.models import Factor
from irp_shared.model.models import Model, ModelValidation
from irp_shared.risk import (
    latest_pure_private_factor_for_segment,
    list_pure_private_factor_results_by_segment,
)
from irp_shared.risk.events import RUN_TYPE_PURE_PRIVATE_FACTOR

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
            (run_demo_cc1_stage8, DemoCc1AlreadySeededError),
            (run_demo_cc2_stage9, DemoCc2AlreadySeededError),
            (run_demo_stage10_api1, DemoStage10AlreadySeededError),
            (run_demo_ppf1_stage11, DemoPpf1AlreadySeededError),
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


def _segment_id(db: Session, factor_code: str) -> str:
    return str(
        db.execute(
            select(Factor.id).where(
                Factor.tenant_id == DEMO_TENANT_ID,
                Factor.factor_code == factor_code,
                Factor.factor_family == "PRIVATE",
                Factor.valid_to.is_(None),
            )
        ).scalar_one()
    )


def test_second_ppf1_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoPpf1AlreadySeededError):
        run_demo_ppf1_stage11(db)
    db.rollback()


def test_ppf1_governed_number_counts_moved(db: Session) -> None:
    """The governed-number story: a NEW code + an INITIAL record + TWO runs move 20/35/101 →
    21/36/103 (the CC-2 shape, the contrast with stage 10's runs-only)."""
    codes = db.execute(
        select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert codes == 21
    records = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert records == 36
    runs = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == DEMO_TENANT_ID, CalculationRun.status == "COMPLETED")
    ).scalar_one()
    assert runs == 103


def test_ppf1_two_pure_private_runs_completed(db: Session) -> None:
    """Exactly TWO COMPLETED PURE_PRIVATE_FACTOR runs — one per single-member segment."""
    n = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == RUN_TYPE_PURE_PRIVATE_FACTOR,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert n == 2


def test_ppf1_reads_render_both_segments_at_one_member(db: Session) -> None:
    """The rule-7 reads render each seeded segment's pooled series, each disclosing member_count=1
    (thin, never hidden); latest keeps only the newest run's rows."""
    for code in ("PPF_PRIVATE_EQUITY_GLOBAL", "PPF_PRIVATE_CREDIT_GLOBAL"):
        seg = _segment_id(db, code)
        rows = list_pure_private_factor_results_by_segment(
            db, acting_tenant=DEMO_TENANT_ID, segment_factor_id=seg
        )
        assert rows, f"segment {code} has no pure-private rows"
        assert all(r.member_count == 1 for r in rows)
        assert all(r.pooling_convention == "EQUAL_WEIGHT" for r in rows)
        assert all(r.intercept_convention == "RETAIN_ALPHA" for r in rows)
        latest = latest_pure_private_factor_for_segment(
            db, acting_tenant=DEMO_TENANT_ID, segment_factor_id=seg
        )
        assert len({r.calculation_run_id for r in latest}) == 1
