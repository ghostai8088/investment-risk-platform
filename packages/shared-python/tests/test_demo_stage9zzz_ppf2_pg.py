"""PPF-2 stage-12 PG tier: the private covariance block Ω_pp estimated live on the tenant over the
seeded pure-private substrate (ZERO new book data). GOVERNED-NUMBER — the counts move by exactly ONE
new model code + ONE INITIAL validation + ONE COMPLETED run (21/36/103 → 22/37/104), the CC-2 shape.
Runs AFTER the PPF-1 (``stage9zz``) step and BEFORE the downgrade smoke.

The ``stage9zzz`` filename collates AFTER ``test_demo_stage9zz_ppf1*`` (last among the demo stage
suites) so a single-invocation local PG battery seeds this extra run LAST."""

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
    DemoPpf2AlreadySeededError,
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
    run_demo_ppf2_stage12,
    run_demo_rs1_stage5,
    run_demo_stage10_api1,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.model.models import Model, ModelValidation
from irp_shared.risk import latest_covariances, latest_private_covariances, list_private_covariances
from irp_shared.risk.events import RUN_TYPE_COVARIANCE_PRIVATE

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
            (run_demo_ppf2_stage12, DemoPpf2AlreadySeededError),
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


def test_second_ppf2_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoPpf2AlreadySeededError):
        run_demo_ppf2_stage12(db)
    db.rollback()


def test_ppf2_governed_number_counts_moved(db: Session) -> None:
    """The governed-number story: a NEW code + an INITIAL record + ONE run move 21/36/103 →
    22/37/104 (the CC-2 shape)."""
    codes = db.execute(
        select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert codes == 22
    records = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert records == 37
    runs = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == DEMO_TENANT_ID, CalculationRun.status == "COMPLETED")
    ).scalar_one()
    assert runs == 104


def test_ppf2_one_private_covariance_run_completed(db: Session) -> None:
    """Exactly ONE COMPLETED COVARIANCE_PRIVATE run; its matrix is the full K=2 block (3 rows)."""
    run_id = db.execute(
        select(CalculationRun.run_id).where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == RUN_TYPE_COVARIANCE_PRIVATE,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()  # scalar_one asserts EXACTLY one
    rows = list_private_covariances(db, run_id=str(run_id), acting_tenant=DEMO_TENANT_ID)
    assert len(rows) == 3  # K*(K+1)/2 for K=2
    assert all(r.frequency == "APPRAISAL" and r.statistic_type == "COVARIANCE" for r in rows)
    assert all(r.factor_id_1 <= r.factor_id_2 for r in rows)  # canonical pair order


def test_ppf2_isolation_private_matrix_not_in_public_latest(db: Session) -> None:
    """Under FORCE RLS + the run_type filter: the Ω_pp matrix surfaces through the PRIVATE latest
    read but the demo tenant's public latest-covariance read is UNAFFECTED by it (the private run
    never leaks into the public surface — the shared-table isolation doctrine, live)."""
    priv = latest_private_covariances(db, acting_tenant=DEMO_TENANT_ID)
    assert priv and all(r.frequency == "APPRAISAL" for r in priv)
    priv_ids = {str(r.id) for r in priv}
    pub = latest_covariances(db, acting_tenant=DEMO_TENANT_ID)
    # The demo seeds public covariance runs too; whatever the public latest is, it shares NO row id
    # with the private matrix (disjoint families over the shared covariance_result table).
    assert priv_ids.isdisjoint({str(r.id) for r in pub})
    assert all(r.frequency != "APPRAISAL" for r in pub)  # public matrices are DAILY
