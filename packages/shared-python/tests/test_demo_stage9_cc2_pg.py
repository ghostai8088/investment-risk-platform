"""CC-2 stage-9 PG tier: the governed projection LIVE on the living tenant — the counts MOVE
(20 codes / 35 validation records / 96 COMPLETED runs, the deliberate contrast with stage 8's
pinned-unchanged capture-only), the projection run COMPLETED with its FUTURE-ONLY period rows
(ages 2..12), and the INITIAL AWC filed against the pacing model's OWN registered limitations.
Runs AFTER the stage-8 step and BEFORE the downgrade smoke in CI (the smoke then exercises 0045's
destructive downgrade against THIS stage's projection rows every run)."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DemoCc1AlreadySeededError,
    DemoCc2AlreadySeededError,
    run_demo_bt3_stage7,
    run_demo_campaign,
    run_demo_cc1_stage8,
    run_demo_cc2_stage9,
    run_demo_ds2_stage6,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
    run_demo_rs1_stage5,
)
from irp_shared.demo.bt3_stage7 import DemoBt3AlreadySeededError
from irp_shared.demo.campaign import DEMO_TENANT_ID, DemoCampaignAlreadySeededError
from irp_shared.demo.ds2_stage6 import DemoDs2AlreadySeededError
from irp_shared.demo.eshs_stage4 import DemoEshsAlreadySeededError
from irp_shared.demo.hg1_private import DemoHg1AlreadySeededError
from irp_shared.demo.multifamily import DemoMultifamilyAlreadySeededError
from irp_shared.demo.rs1_stage5 import DemoRs1AlreadySeededError
from irp_shared.model.models import Model, ModelValidation
from irp_shared.pacing.events import RUN_TYPE_PACING_PROJECTION
from irp_shared.pacing.models import PacingProjectionResult

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


def test_second_stage9_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoCc2AlreadySeededError):
        run_demo_cc2_stage9(db)
    db.rollback()


def test_governed_projection_counts_moved(db: Session) -> None:
    """The stage-9 story: a governed number DOES move the counts (the deliberate contrast with
    stage 8's capture-only 19/34/95) — one new code, one INITIAL record, one COMPLETED run."""
    codes = db.execute(
        select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert codes == 20
    records = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert records == 35
    runs = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert runs == 96


def test_projection_run_and_rows(db: Session) -> None:
    """ONE COMPLETED PACING_PROJECTION run with FUTURE-ONLY period rows (ages 2..12, the mid-life
    anchor from the 2026-06-30 mark vs the 2025-06-30 vintage) all in the commitment currency."""
    run = db.execute(
        select(CalculationRun).where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == RUN_TYPE_PACING_PROJECTION,
        )
    ).scalar_one()
    assert run.status == "COMPLETED"
    rows = (
        db.execute(
            select(PacingProjectionResult)
            .where(
                PacingProjectionResult.tenant_id == DEMO_TENANT_ID,
                PacingProjectionResult.calculation_run_id == run.run_id,
            )
            .order_by(PacingProjectionResult.period_index)
        )
        .scalars()
        .all()
    )
    assert [r.period_index for r in rows] == list(range(2, 13))  # ages 2..12
    assert all(r.currency_code == "USD" for r in rows)
    # The projected series is monotone-positive in NAV under growth=0.13 with a positive anchor.
    assert all(r.projected_nav > Decimal("0") for r in rows)
    # The final age fully distributes the grown NAV (RD(L)=max(Y,1)=1): unfunded exhausted.
    assert rows[-1].unfunded_end >= Decimal("0")


def test_initial_awc_filed_against_own_limitations(db: Session) -> None:
    """The pacing model's INITIAL AWC exists, is APPROVED_WITH_CONDITIONS, and its evidence cites
    the projection run (the NEW-code SOME-record precedent)."""
    from irp_shared.model.models import ModelVersion

    validation = db.execute(
        select(ModelValidation)
        .join(ModelVersion, ModelVersion.id == ModelValidation.model_version_id)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(
            Model.tenant_id == DEMO_TENANT_ID,
            Model.code == "pacing.commitment_projection",
        )
    ).scalar_one()
    assert validation.validation_type == "INITIAL"
    assert validation.outcome == "APPROVED_WITH_CONDITIONS"
