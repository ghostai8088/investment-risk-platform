"""ES-HS-1 stage-4 PG end-state suite (OD-ES-HS-1-F): seeds all FOUR stages (refuse-tolerant,
the hg1-suite shape) and asserts stage 4's footprint — the 18th code, the TIER_1 head, the
shared-snapshot (VaR, ES) pair, the INITIAL AWC dossier, refuse-not-skip idempotence.

ORDERING: the ``stage4`` filename component is LOAD-BEARING (alpha-sorts AFTER the campaign/
hg1/multifamily suites — their pins are false on a stage-4-extended tenant); in CI this suite
runs AFTER the stage-3 step and BEFORE the downgrade smoke, whose ``alembic downgrade base``
then exercises 0041's destructive ES_HISTORICAL delete against THIS suite's rows on every run.
KNOWN EDGE (the recorded stage-3 carry): the role_permission grants this suite's runners need
come from the demo seeding, so it assumes the standalone-fresh sequence, never a partial reset.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoCampaignAlreadySeededError,
    DemoEshsAlreadySeededError,
    DemoHg1AlreadySeededError,
    DemoMultifamilyAlreadySeededError,
    run_demo_campaign,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
)
from irp_shared.model.models import Model, ModelValidation, ModelVersion
from irp_shared.risk import ES_HS_MODEL_CODE, VarResult

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


def _es_version(db: Session) -> ModelVersion:
    return db.execute(
        select(ModelVersion)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(Model.tenant_id == DEMO_TENANT_ID, Model.code == ES_HS_MODEL_CODE)
    ).scalar_one()


def test_second_stage4_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoEshsAlreadySeededError):
        run_demo_eshs_stage4(db)
    db.rollback()


def test_the_18th_code_is_registered_and_tier_1(db: Session) -> None:
    version = _es_version(db)
    assert version.status == "REGISTERED"
    assert version.code_version == "demo-eshs1"
    head = db.get(Model, version.model_id)
    assert head is not None and head.tier == "TIER_1"
    # 18 registered codes on the fully-extended tenant (16 campaign + loadings + this).
    codes = db.execute(select(Model.code).where(Model.tenant_id == DEMO_TENANT_ID)).all()
    assert len(codes) == 18


def test_the_shared_snapshot_pair_and_es_geq_var(db: Session) -> None:
    """The BT-3 pairing design input, live in the tenant: the ES row and the flagship HS row
    it pairs with share ONE input_snapshot_id, and ES >= VaR on the shared scenario set."""
    version = _es_version(db)
    es_row = db.execute(
        select(VarResult).where(
            VarResult.tenant_id == DEMO_TENANT_ID,
            VarResult.model_version_id == str(version.id),
        )
    ).scalar_one()
    assert es_row.metric_type == "ES_HISTORICAL"
    assert es_row.z_score is None and es_row.sigma is None and es_row.covariance_run_id is None
    paired = db.execute(
        select(VarResult).where(
            VarResult.tenant_id == DEMO_TENANT_ID,
            VarResult.metric_type == "VAR_HISTORICAL",
            VarResult.input_snapshot_id == es_row.input_snapshot_id,
        )
    ).scalar_one()
    assert es_row.var_value >= paired.var_value
    assert (es_row.confidence_level, es_row.n_observations) == (
        paired.confidence_level,
        paired.n_observations,
    )


def test_the_initial_awc_dossier_filed(db: Session) -> None:
    version = _es_version(db)
    validation = db.execute(
        select(ModelValidation).where(
            ModelValidation.tenant_id == DEMO_TENANT_ID,
            ModelValidation.model_version_id == str(version.id),
        )
    ).scalar_one()
    assert validation.validation_type == "INITIAL"
    assert validation.outcome == "APPROVED_WITH_CONDITIONS"
    assert validation.conditions is not None
    assert validation.next_review_due is not None
    assert "FL-1" not in (validation.scope_summary or "")
    assert "FL-1" not in (validation.conditions or "")
