"""API-1 stage-10 PG tier: the five registered-but-never-run codes EXECUTED live on the tenant so
the API-1 reads render NON-EMPTY. RUNS-ONLY — the counts move by exactly the five COMPLETED runs
(20 codes / 35 records UNCHANGED; 96 → 101 runs), the deliberate contrast with stage 9's
code+record+run mint. Runs AFTER the stage-9 step and BEFORE the downgrade smoke in CI.

The ``stage9z`` filename collates AFTER ``test_demo_stage9_cc2*`` (last among the demo stage suites)
so a single-invocation local PG battery seeds these extra runs LAST — a two-digit ``stage10`` name
sorts before ``stage2``/``stage4`` and would corrupt the earlier stages' exact count pins."""

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
    run_demo_rs1_stage5,
    run_demo_stage10_api1,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.model.models import Model, ModelValidation
from irp_shared.perf import latest_benchmark_relative
from irp_shared.portfolio import Portfolio
from irp_shared.risk import (
    latest_covariances,
    latest_factor_exposure,
    latest_scenario_results,
    latest_sensitivities,
)

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


def _completed_runs_of(db: Session, run_type: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == run_type,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()


def test_second_stage10_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoStage10AlreadySeededError):
        run_demo_stage10_api1(db)
    db.rollback()


def test_stage10_runs_only_counts_moved(db: Session) -> None:
    """The runs-only story: codes + records UNCHANGED (20 / 35), runs +5 (96 → 101) — the contrast
    with stage 9's code+record+run mint."""
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
        .where(CalculationRun.tenant_id == DEMO_TENANT_ID, CalculationRun.status == "COMPLETED")
    ).scalar_one()
    assert runs == 101


def test_stage10_five_governed_runs_completed(db: Session) -> None:
    """One COMPLETED run of each newly-exercised type. FACTOR_EXPOSURE now counts the campaign's
    allocation runs PLUS the stage-10 proxy run (so >= the campaign count + 1)."""
    assert _completed_runs_of(db, "SENSITIVITY") == 1
    assert _completed_runs_of(db, "ACTIVE_RISK") == 1
    assert _completed_runs_of(db, "SCENARIO") == 1
    assert _completed_runs_of(db, "BENCHMARK_RELATIVE") == 1
    assert _completed_runs_of(db, "FACTOR_EXPOSURE") >= 2  # allocation(s) + the stage-10 proxy


def test_stage10_api1_reads_render_nonempty(db: Session) -> None:
    """The point of the stage: the API-1 entity/latest reads now return rows for the exercised
    families (a bare read surface with zero rows would look identical to an un-shipped feature)."""
    # Class-B latest resolvers (no entity filter needed).
    assert len(latest_sensitivities(db, acting_tenant=DEMO_TENANT_ID)) > 0
    assert len(latest_scenario_results(db, acting_tenant=DEMO_TENANT_ID)) > 0
    assert len(latest_covariances(db, acting_tenant=DEMO_TENANT_ID)) > 0
    # Class-A entity reads for the DEMO-GLOBAL flagship book.
    demo_global = db.execute(
        select(Portfolio.id).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == "DEMO-GLOBAL"
        )
    ).scalar_one()
    # The stage-10 proxy run is the newest factor-exposure run over the book.
    assert (
        len(latest_factor_exposure(db, acting_tenant=DEMO_TENANT_ID, portfolio_id=demo_global)) > 0
    )
    assert (
        len(latest_benchmark_relative(db, acting_tenant=DEMO_TENANT_ID, portfolio_id=demo_global))
        > 0
    )
