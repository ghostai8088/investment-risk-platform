"""DS-2 stage-6 PG end-state suite (OD-DS-2-E): seeds all SIX stages (refuse-tolerant) and
asserts stage 6's footprint — the two estimator VERSIONS on the existing desmoothing code (NO
new code: the count stays 18), the estimation story (alpha-hat + band persisted; OW rows NULL),
the 2 INITIAL AWCs, NO TRIGGERED on the desmoothing family, and refuse-not-skip idempotence.

ORDERING: the ``stage6`` filename component is LOAD-BEARING (alpha-sorts AFTER every prior
stage's suites); in CI this suite runs AFTER the stage-5 step and BEFORE the downgrade smoke —
whose ``alembic downgrade base`` then exercises 0042's destructive NULL-alpha delete against
THIS suite's OW rows on every run (the 0041 coupling precedent)."""

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
    DemoDs2AlreadySeededError,
    DemoEshsAlreadySeededError,
    DemoHg1AlreadySeededError,
    DemoMultifamilyAlreadySeededError,
    DemoRs1AlreadySeededError,
    run_demo_campaign,
    run_demo_ds2_stage6,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
    run_demo_rs1_stage5,
)
from irp_shared.model.models import Model, ModelValidation, ModelVersion
from irp_shared.perf import (
    DESMOOTHED_RETURN_MODEL_CODE,
    declared_desmoothing_parameters,
)
from irp_shared.perf.models import DesmoothedReturnResult

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


def _dm_versions(db: Session) -> dict[str, ModelVersion]:
    versions = (
        db.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == DESMOOTHED_RETURN_MODEL_CODE,
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, ModelVersion] = {}
    for v in versions:
        conv = declared_desmoothing_parameters(db, v).estimator_convention
        out.setdefault(conv, v)
    return out


def test_second_stage6_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoDs2AlreadySeededError):
        run_demo_ds2_stage6(db)
    db.rollback()


def test_no_new_code_and_the_convention_versions(db: Session) -> None:
    codes = db.execute(select(Model.code).where(Model.tenant_id == DEMO_TENANT_ID)).all()
    assert len(codes) == 18  # UNCHANGED — stage 6 mints versions, not a code
    by_conv = _dm_versions(db)
    assert set(by_conv) == {"DECLARED", "AR1_ESTIMATED", "OKUNEV_WHITE_ITERATIVE"}


def test_the_estimation_story_persisted(db: Session) -> None:
    """The AR1 run's summary carries alpha-hat (in the fixture band) + the band; the OW rows
    carry alpha NULL with the stderr NULL everywhere but the AR1 summary."""
    from decimal import Decimal

    by_conv = _dm_versions(db)
    est_rows = (
        db.execute(
            select(DesmoothedReturnResult).where(
                DesmoothedReturnResult.tenant_id == DEMO_TENANT_ID,
                DesmoothedReturnResult.model_version_id == str(by_conv["AR1_ESTIMATED"].id),
            )
        )
        .scalars()
        .all()
    )
    assert est_rows
    summary = next(r for r in est_rows if r.metric_type == "DESMOOTHING_SUMMARY")
    assert summary.alpha is not None and Decimal("0.45") < summary.alpha < Decimal("0.55")
    assert summary.alpha_stderr is not None
    ow_rows = (
        db.execute(
            select(DesmoothedReturnResult).where(
                DesmoothedReturnResult.tenant_id == DEMO_TENANT_ID,
                DesmoothedReturnResult.model_version_id
                == str(by_conv["OKUNEV_WHITE_ITERATIVE"].id),
            )
        )
        .scalars()
        .all()
    )
    assert ow_rows and all(r.alpha is None and r.alpha_stderr is None for r in ow_rows)


def test_two_initials_and_no_triggered_on_the_family(db: Session) -> None:
    by_conv = _dm_versions(db)
    for conv in ("AR1_ESTIMATED", "OKUNEV_WHITE_ITERATIVE"):
        validation = db.execute(
            select(ModelValidation).where(
                ModelValidation.tenant_id == DEMO_TENANT_ID,
                ModelValidation.model_version_id == str(by_conv[conv].id),
            )
        ).scalar_one()
        assert validation.validation_type == "INITIAL"
        assert validation.outcome == "APPROVED_WITH_CONDITIONS"
        assert validation.next_review_due is not None
    # NO TRIGGERED anywhere on the desmoothing family (the recorded no-closable-condition call).
    family_version_ids = [
        str(v.id)
        for v in db.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == DESMOOTHED_RETURN_MODEL_CODE,
            )
        )
        .scalars()
        .all()
    ]
    triggered = (
        db.execute(
            select(ModelValidation).where(
                ModelValidation.tenant_id == DEMO_TENANT_ID,
                ModelValidation.model_version_id.in_(family_version_ids),
                ModelValidation.validation_type == "TRIGGERED",
            )
        )
        .scalars()
        .all()
    )
    assert triggered == []
