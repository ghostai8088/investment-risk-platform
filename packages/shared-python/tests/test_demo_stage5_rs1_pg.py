"""RS-1 stage-5 PG end-state suite (OD-RS-1-E): seeds all FIVE stages (refuse-tolerant, the
stage-4-suite shape) and asserts stage 5's footprint — the two estimator VERSIONS on the existing
proxy-weight code (NO new code: the count stays 18), the re-promoted citations (MF-EQ-A → the
shrinkage run, MF-EQ-B → the EWMA run, the bond asserted-raw), the residual-story numbers, the
2 TRIGGERED closures with the 'hostage…' finding FLIPPED to historical (both directions), the
2 INITIAL AWC dossiers, and refuse-not-skip idempotence.

ORDERING: the ``stage5`` filename component is LOAD-BEARING (alpha-sorts AFTER the campaign/hg1/
multifamily/stage4 suites — their pins are false on a stage-5-extended tenant); in CI this suite
runs AFTER the stage-4 step and BEFORE the downgrade smoke."""

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
    DemoRs1AlreadySeededError,
    run_demo_campaign,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
    run_demo_rs1_stage5,
)
from irp_shared.marketdata.models import MAPPING_METHOD_REGRESSION, ProxyMapping
from irp_shared.model.models import (
    Model,
    ModelValidation,
    ModelValidationFinding,
    ModelVersion,
)
from irp_shared.reference.models import Instrument
from irp_shared.risk import (
    METRIC_TYPE_ESTIMATION_SUMMARY,
    PROXY_WEIGHT_MODEL_CODE,
    ProxyWeightEstimateResult,
    declared_proxy_weight_parameters,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_HOSTAGE = "hostage to the PA-3 estimate quality"


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


def _pw_versions(db: Session) -> dict[str, ModelVersion]:
    """The proxy-weight family's versions keyed by declared estimator convention."""
    versions = (
        db.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(Model.tenant_id == DEMO_TENANT_ID, Model.code == PROXY_WEIGHT_MODEL_CODE)
        )
        .scalars()
        .all()
    )
    return {declared_proxy_weight_parameters(db, v).estimator_convention: v for v in versions}


def _instrument(db: Session, code: str) -> str:
    return str(
        db.execute(
            select(Instrument.id).where(
                Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == code
            )
        ).scalar_one()
    )


def _open_citations(db: Session, instrument_id: str) -> set[str]:
    return {
        str(r.source_calculation_run_id).lower()
        for r in db.execute(
            select(ProxyMapping).where(
                ProxyMapping.tenant_id == DEMO_TENANT_ID,
                ProxyMapping.private_instrument_id == instrument_id,
                ProxyMapping.mapping_method == MAPPING_METHOD_REGRESSION,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
        )
        .scalars()
        .all()
        if r.source_calculation_run_id is not None
    }


def _summary_of_version(db: Session, version_id: str) -> ProxyWeightEstimateResult:
    return db.execute(
        select(ProxyWeightEstimateResult).where(
            ProxyWeightEstimateResult.tenant_id == DEMO_TENANT_ID,
            ProxyWeightEstimateResult.model_version_id == version_id,
            ProxyWeightEstimateResult.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
        )
    ).scalar_one()


def test_second_stage5_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoRs1AlreadySeededError):
        run_demo_rs1_stage5(db)
    db.rollback()


def test_no_new_code_and_three_estimator_versions(db: Session) -> None:
    """Stage 5 mints VERSIONS, not a code: the fully-extended tenant still holds 18 codes and
    the proxy-weight family carries the RAW + EWMA + EB conventions."""
    codes = db.execute(select(Model.code).where(Model.tenant_id == DEMO_TENANT_ID)).all()
    assert len(codes) == 18
    by_convention = _pw_versions(db)
    assert set(by_convention) == {"RAW", "EWMA_RISKMETRICS", "SHRINKAGE_CROSS_SECTIONAL_EB"}
    assert by_convention["EWMA_RISKMETRICS"].code_version == "demo-rs1"
    assert by_convention["SHRINKAGE_CROSS_SECTIONAL_EB"].code_version == "demo-rs1"


def test_the_residual_story_and_the_repromoted_citations(db: Session) -> None:
    """MF-EQ-A's open citation is the SHRINKAGE run (shrunk != raw); MF-EQ-B's two citations are
    the EWMA run (residual != raw; identity carried); the bond's citation is NEITHER (the
    comparable-cohort fence, asserted-raw)."""
    by_convention = _pw_versions(db)
    shrunk = _summary_of_version(db, str(by_convention["SHRINKAGE_CROSS_SECTIONAL_EB"].id))
    ewma = _summary_of_version(db, str(by_convention["EWMA_RISKMETRICS"].id))

    eqa = _instrument(db, "MF-EQ-A")
    eqb = _instrument(db, "MF-EQ-B")
    bond = _instrument(db, "MF-CR-A")
    assert str(shrunk.instrument_id) == eqa
    assert str(ewma.instrument_id) == eqb

    assert _open_citations(db, eqa) == {str(shrunk.calculation_run_id).lower()}
    assert _open_citations(db, eqb) == {str(ewma.calculation_run_id).lower()}
    touched = {
        str(shrunk.calculation_run_id).lower(),
        str(ewma.calculation_run_id).lower(),
    }
    bond_citations = _open_citations(db, bond)
    assert bond_citations and not (bond_citations & touched)

    # the transformations bit: each new summary's residual differs from the instrument's RAW one.
    raw_version_id = str(by_convention["RAW"].id)
    for row, inst in ((shrunk, eqa), (ewma, eqb)):
        raw_rows = (
            db.execute(
                select(ProxyWeightEstimateResult)
                .where(
                    ProxyWeightEstimateResult.tenant_id == DEMO_TENANT_ID,
                    ProxyWeightEstimateResult.instrument_id == inst,
                    ProxyWeightEstimateResult.model_version_id == raw_version_id,
                    ProxyWeightEstimateResult.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
                )
                .order_by(ProxyWeightEstimateResult.system_from.desc())
            )
            .scalars()
            .all()
        )
        assert raw_rows and row.residual_stdev != raw_rows[0].residual_stdev
        assert row.metric_value == raw_rows[0].metric_value  # R^2 carried/identical


def test_the_hostage_finding_flipped_to_historical(db: Session) -> None:
    """Closure-by-supersession at the version grain, BOTH directions: the LATEST record on the
    flagship total-VaR version carries the RS-1 closure finding and NO 'hostage…' finding; an
    EARLIER (MF-1) record on the SAME version still carries it."""
    version = db.execute(
        select(ModelVersion)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(
            Model.tenant_id == DEMO_TENANT_ID,
            Model.code == "risk.var.parametric_total",
            ModelVersion.code_version == "demo-mg1",
        )
    ).scalar_one()
    validations = (
        db.execute(
            select(ModelValidation)
            .where(
                ModelValidation.tenant_id == DEMO_TENANT_ID,
                ModelValidation.model_version_id == str(version.id),
            )
            .order_by(ModelValidation.system_from.desc(), ModelValidation.id.desc())
        )
        .scalars()
        .all()
    )
    assert len(validations) >= 2  # the MF-1 TRIGGERED + the RS-1 TRIGGERED at minimum

    def _finding_texts(validation_id: str) -> list[str]:
        return [
            r[0]
            for r in db.execute(
                select(ModelValidationFinding.finding_text).where(
                    ModelValidationFinding.validation_id == validation_id
                )
            ).all()
        ]

    latest = _finding_texts(str(validations[0].id))
    assert any("CLOSED (RS-1)" in t for t in latest)
    assert not any(_HOSTAGE in t for t in latest)
    assert validations[0].conditions is not None and _HOSTAGE not in validations[0].conditions
    # the OTHER direction: some earlier record on the SAME version still carries the rider.
    assert any(any(_HOSTAGE in t for t in _finding_texts(str(v.id))) for v in validations[1:])


def test_the_two_initial_awc_dossiers_filed(db: Session) -> None:
    by_convention = _pw_versions(db)
    for convention in ("EWMA_RISKMETRICS", "SHRINKAGE_CROSS_SECTIONAL_EB"):
        version = by_convention[convention]
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
        assert _HOSTAGE not in (validation.conditions or "")
