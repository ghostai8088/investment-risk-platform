"""PPF-3 stage-13 PG tier: the unified public+private VaR run live on the tenant over a fresh
two-fund book (PE-HARBOR-IV + PC-BRIDGEWATER-II) and the union public chain. GOVERNED-NUMBER — the
counts move by ONE new code + ONE INITIAL validation + the whole chain's runs (22/37/104 →
23/38/109), the CC-2/chain shape. Runs AFTER the PPF-2 (``stage9zzz``) step and BEFORE the downgrade
smoke.

The ``stage9zzzz`` filename collates AFTER ``test_demo_stage9zzz_ppf2*`` (last among the demo stage
suites) so a single-invocation local PG battery seeds this extra chain LAST."""

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
    DemoPpf3AlreadySeededError,
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
    run_demo_ppf3_stage13,
    run_demo_rs1_stage5,
    run_demo_stage10_api1,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.ppf3_stage13 import _PORTFOLIO_CODE
from irp_shared.model.models import Model, ModelValidation
from irp_shared.portfolio.models import Portfolio
from irp_shared.risk import (
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    latest_var_for_portfolio,
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
            (run_demo_ppf1_stage11, DemoPpf1AlreadySeededError),
            (run_demo_ppf2_stage12, DemoPpf2AlreadySeededError),
            (run_demo_ppf3_stage13, DemoPpf3AlreadySeededError),
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


def _portfolio_id(db: Session) -> str:
    return str(
        db.execute(
            select(Portfolio.id).where(
                Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _PORTFOLIO_CODE
            )
        ).scalar_one()
    )


def test_second_ppf3_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoPpf3AlreadySeededError):
        run_demo_ppf3_stage13(db)
    db.rollback()


def test_ppf3_governed_number_counts_moved(db: Session) -> None:
    """The governed-number story: a NEW code + an INITIAL record + the whole public chain (exposure
    + factor-exposure + covariance + total + unified = 5 runs) move 22/37/104 → 23/38/109."""
    codes = db.execute(
        select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert codes == 23
    records = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert records == 38
    runs = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == DEMO_TENANT_ID, CalculationRun.status == "COMPLETED")
    ).scalar_one()
    assert runs == 109


def test_ppf3_headline_unified_differs_from_total(db: Session) -> None:
    """THE HEADLINE: over the SAME two-fund book, the unified number differs from PA-4's total VaR
    by the cross-segment pure-private co-movement — the correlated private risk total VaR misses."""
    pf = _portfolio_id(db)
    unified = latest_var_for_portfolio(
        db,
        acting_tenant=DEMO_TENANT_ID,
        portfolio_id=pf,
        metric_type=METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    )
    total = latest_var_for_portfolio(
        db,
        acting_tenant=DEMO_TENANT_ID,
        portfolio_id=pf,
        metric_type=METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    )
    assert len(unified) == 1 and len(total) == 1
    urow, trow = unified[0], total[0]
    assert urow.sigma != trow.sigma  # the two-fund cross-segment term moved the number
    assert urow.private_variance is not None and urow.private_variance > 0  # leg 2 is real
    # THE REPARTITION: both funds are pure-private members, so leg 3 (residual over NON-private
    # members) is EXACTLY zero on the unified row — their variance lives in leg 2, never twice.
    assert urow.residual_variance == Decimal(0)
    assert trow.residual_variance > 0  # ...while the total row DOES carry the private residual


def test_ppf3_unified_provenance_binds_the_omega_pp_run(db: Session) -> None:
    """The unified row carries its Ω_pp provenance (private_covariance_run_id) + the public Σ run —
    the governed decomposition is fully traceable."""
    pf = _portfolio_id(db)
    urow = latest_var_for_portfolio(
        db,
        acting_tenant=DEMO_TENANT_ID,
        portfolio_id=pf,
        metric_type=METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    )[0]
    assert urow.private_covariance_run_id is not None
    assert urow.covariance_run_id is not None
    assert urow.private_covariance_run_id != urow.covariance_run_id  # Ω_pp != the public Σ
