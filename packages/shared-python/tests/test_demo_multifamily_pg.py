"""PostgreSQL end-state test for the MF-1 demo multi-family extension (OD-MF-1-A…D).

Gated on ``IRP_TEST_DATABASE_URL``. Seeds the MG-1 base campaign if absent, then runs the
extension ONCE (module-scoped) as the OWNER engine — the runner writes across the whole governed
surface, so the per-suite ``irp_app`` grant-list pattern does not fit (the campaign suite's
recorded pattern); FORCE RLS still applies to the owner, and every session scopes itself to the
DEMO tenant. **CI ORDERING IS LOAD-BEARING (record Part 3 item 12): this suite runs AFTER the
campaign suite** — the campaign's pins (16 codes, exactly-5 AWCs) are false on an extended
tenant, so from MF-1 on the campaign suite is fresh-schema-only and this suite extends the
tenant it left behind.

The end state asserted is the ratified one: 17 registered codes (the loadings family joined),
the loadings head tiered TIER_2, the sleeve chain COMPLETED end-to-end (alpha=1 desmooth -> k=3
OLS -> promoted structural loadings -> loadings-family exposure -> covariance -> the five
flagship evidence runs bound to the demo-mg1 versions), the 5 TRIGGERED AWC re-validations
superseding the flagship AWCs at the version grain (the OQ-MF-1-6 grep flip, both directions on
the CONDITIONS surface), the loadings INITIAL, the alpha=1 EXCEPTION, the mixed-family fence
(legacy instruments carry zero non-CURRENCY head rows), and refuse-not-skip on a second
invocation.

KNOWN EDGE (adversarial finder F7): a STANDALONE fresh-schema run of this suite followed by
``alembic downgrade base`` would hit the 0002 role_permission FK violation — this fixture seeds
the campaign when absent but deliberately carries no role_permission teardown (that guard lives
in the campaign suite, which runs first in every documented sequence: CI and the local battery).
"""

from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoCampaignAlreadySeededError,
    DemoMultifamilyAlreadySeededError,
    run_demo_campaign,
    run_demo_multifamily_extension,
)
from irp_shared.demo.dossiers import MF1_TRIGGERED_DOSSIERS, TIER_DOSSIERS
from irp_shared.demo.multifamily import (
    _INSTRUMENT_SPECS,
    _MF_AS_OF,
    _STRUCTURAL_LOADINGS,
)
from irp_shared.marketdata.models import Factor, ProxyMapping
from irp_shared.model.models import (
    Model,
    ModelValidation,
    ModelValidationEvidence,
    ModelVersion,
)
from irp_shared.reference.models import Instrument
from irp_shared.risk import FACTOR_EXPOSURE_LOADINGS_MODEL_CODE
from irp_shared.risk.models import FactorExposureResult
from irp_shared.valuation.models import Valuation

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_FLAGSHIP_AWC_CODES = tuple(MF1_TRIGGERED_DOSSIERS)  # the 5 re-validated flagships
_LEGACY_INSTRUMENT_CODES = ("EQ-ACME-US", "EQ-EURX-DE", "PE-HARBOR-IV")
_SIX_DP = Decimal("0.000001")


# NOTE: the PREREQ refusal (an unseeded tenant) is deliberately NOT probed here — CI's
# load-bearing ordering seeds the campaign BEFORE this suite, so a PG probe would self-skip in
# every automated environment (the scope finder's MED-2). Both refusal guards get their
# executable coverage at unit tier instead (``test_demo_multifamily.py``, SQLite — the guards
# fire before any PG-specific work).


@pytest.fixture(scope="module")
def factory():  # noqa: ANN201
    """Owner-engine session factory with the base campaign + the extension executed once. An
    already-extended tenant is tolerated (assertions read the DB, never the summary object);
    the refusal semantics get their own test."""
    engine = make_engine(URL, poolclass=NullPool)
    session_factory = make_session_factory(engine)
    session = session_factory()
    try:
        try:
            run_demo_campaign(session)
            session.commit()
        except DemoCampaignAlreadySeededError:
            session.rollback()
        try:
            run_demo_multifamily_extension(session)
            session.commit()
        except DemoMultifamilyAlreadySeededError:
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


def _validations_of(db: Session, code: str) -> list[ModelValidation]:
    return list(
        db.execute(
            select(ModelValidation)
            .join(ModelVersion, ModelVersion.id == ModelValidation.model_version_id)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(Model.tenant_id == DEMO_TENANT_ID, Model.code == code)
            .order_by(ModelValidation.system_from.desc(), ModelValidation.id.desc())
        )
        .scalars()
        .all()
    )


def _instrument_id(db: Session, code: str) -> str:
    return str(
        db.execute(
            select(Instrument.id).where(
                Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == code
            )
        ).scalar_one()
    )


def test_second_extension_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoMultifamilyAlreadySeededError):
        run_demo_multifamily_extension(db)
    db.rollback()


def test_seventeen_codes_and_the_loadings_head_is_tier_2(db: Session) -> None:
    models = {
        m.code: m
        for m in db.execute(select(Model).where(Model.tenant_id == DEMO_TENANT_ID)).scalars().all()
    }
    assert set(models) == set(TIER_DOSSIERS) | {FACTOR_EXPOSURE_LOADINGS_MODEL_CODE}
    assert len(models) == 17
    assert models[FACTOR_EXPOSURE_LOADINGS_MODEL_CODE].tier == "TIER_2"


def test_the_sleeve_chain_completed_end_to_end(db: Session) -> None:
    """Every demo-mf1 governed run COMPLETED: 3 desmooth + 3 estimate + 1 exposure + 1 loadings
    factor-exposure + 1 covariance + 5 flagship evidence runs = 14."""
    runs = (
        db.execute(
            select(CalculationRun).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.code_version == "demo-mf1",
            )
        )
        .scalars()
        .all()
    )
    by_type: dict[str, list[CalculationRun]] = {}
    for r in runs:
        by_type.setdefault(r.run_type, []).append(r)
        assert r.status == RunStatus.COMPLETED.value, (r.run_type, r.failure_reason)
    assert len(by_type["DESMOOTHED_RETURN"]) == 3
    assert len(by_type["PROXY_WEIGHT_ESTIMATE"]) == 3
    assert len(by_type["EXPOSURE_AGGREGATE"]) == 1
    assert len(by_type["FACTOR_EXPOSURE"]) == 1
    assert len(by_type["COVARIANCE"]) == 1
    assert len(by_type["VAR"]) == 5  # plain + HS + total + ES + ES-total
    assert len(runs) == 14

    # The loadings run's snapshot is the LOADINGS-family one (plan Step 7: the predicate pin).
    from irp_shared.snapshot.models import DatasetSnapshot
    from irp_shared.snapshot.service import FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE

    loadings_run = by_type["FACTOR_EXPOSURE"][0]
    row = db.execute(
        select(FactorExposureResult)
        .where(FactorExposureResult.calculation_run_id == loadings_run.run_id)
        .limit(1)
    ).scalar_one()
    snapshot = db.execute(
        select(DatasetSnapshot).where(DatasetSnapshot.id == str(row.input_snapshot_id))
    ).scalar_one()
    assert snapshot.binding_predicate_version == FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE


def test_the_grep_flip_both_directions_on_the_conditions_surface(db: Session) -> None:
    """OQ-MF-1-6: the LATEST validation per flagship version is a token-free TRIGGERED AWC; a
    tenant-wide conditions grep finds 'FL-1' in exactly the 5 HISTORICAL flagship AWC rows."""
    for code in _FLAGSHIP_AWC_CODES:
        rows = _validations_of(db, code)
        latest = rows[0]
        assert latest.validation_type == "TRIGGERED"
        assert latest.outcome == "APPROVED_WITH_CONDITIONS"
        assert latest.conditions and "FL-1" not in latest.conditions
        assert "FL-1" not in latest.scope_summary
        # The historical INITIAL AWC keeps the token forever (append-only visibility), and the
        # supersession is VERSION-grain: both records sit on the SAME model_version_id (the
        # adversarial finder's pin — a TRIGGERED on any other version would leave the AWC live).
        historical = [r for r in rows if r.validation_type == "INITIAL"]
        assert len(historical) == 1
        assert historical[0].conditions and "FL-1" in historical[0].conditions
        assert str(latest.model_version_id) == str(historical[0].model_version_id)

    all_rows = (
        db.execute(
            select(ModelValidation)
            .join(ModelVersion, ModelVersion.id == ModelValidation.model_version_id)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(Model.tenant_id == DEMO_TENANT_ID)
        )
        .scalars()
        .all()
    )
    carrying = [r for r in all_rows if r.conditions and "FL-1" in r.conditions]
    assert len(carrying) == 5
    assert all(r.validation_type == "INITIAL" for r in carrying)


def test_the_mixed_family_fence_holds(db: Session) -> None:
    """OD-MF-1-A: legacy instruments carry ZERO non-CURRENCY head rows (the PA-2 proxy family
    stays runnable on the legacy book); the sleeve instruments carry ONLY REGRESSION rows in the
    three new families, each citing that instrument's single estimate run."""
    factor_families = {
        str(f.id).lower(): f.factor_family
        for f in db.execute(select(Factor).where(Factor.tenant_id == DEMO_TENANT_ID))
        .scalars()
        .all()
    }
    for code in _LEGACY_INSTRUMENT_CODES:
        inst = _instrument_id(db, code)
        heads = (
            db.execute(
                select(ProxyMapping).where(
                    ProxyMapping.tenant_id == DEMO_TENANT_ID,
                    ProxyMapping.private_instrument_id == inst,
                    ProxyMapping.valid_to.is_(None),
                    ProxyMapping.system_to.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert all(
            factor_families[str(r.factor_id).lower()] == "CURRENCY" for r in heads
        ), f"legacy instrument {code} gained a non-CURRENCY loading row — the fence is broken"

    for code, loadings in _STRUCTURAL_LOADINGS.items():
        inst = _instrument_id(db, code)
        heads = (
            db.execute(
                select(ProxyMapping).where(
                    ProxyMapping.tenant_id == DEMO_TENANT_ID,
                    ProxyMapping.private_instrument_id == inst,
                    ProxyMapping.valid_to.is_(None),
                    ProxyMapping.system_to.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert len(heads) == len(loadings)
        assert all(r.mapping_method == "REGRESSION" for r in heads)
        cited = {str(r.source_calculation_run_id) for r in heads}
        assert len(cited) == 1  # the one-estimate-run-per-instrument shape total-VaR requires


def test_the_spot_golden_eq_a_projection_row(db: Session) -> None:
    """The hand-derivable loadings projection: EQ-A's MARKET exposure row equals
    quantize(promoted_weight x (qty x mark), 6dp HALF_UP), and the recovered beta sits near the
    generator's structural 0.9 (the k=3 OLS re-derivation honesty check)."""
    inst = _instrument_id(db, "MF-EQ-A")
    qty = Decimal(next(s[3] for s in _INSTRUMENT_SPECS if s[0] == "MF-EQ-A"))
    mark = db.execute(
        select(Valuation.mark_value).where(
            Valuation.tenant_id == DEMO_TENANT_ID,
            Valuation.instrument_id == inst,
            Valuation.valuation_date == _MF_AS_OF,
            Valuation.valid_to.is_(None),
            Valuation.system_to.is_(None),
        )
    ).scalar_one()
    weight_row = db.execute(
        select(ProxyMapping).where(
            ProxyMapping.tenant_id == DEMO_TENANT_ID,
            ProxyMapping.private_instrument_id == inst,
            ProxyMapping.valid_to.is_(None),
            ProxyMapping.system_to.is_(None),
        )
    ).scalar_one()  # exactly one promoted loading (MARKET)
    beta = Decimal(weight_row.weight)
    assert abs(beta - Decimal("0.9")) < Decimal("0.1")  # the structural loading recovered

    row = db.execute(
        select(FactorExposureResult)
        .join(
            CalculationRun,
            CalculationRun.run_id == FactorExposureResult.calculation_run_id,
        )
        .where(
            FactorExposureResult.tenant_id == DEMO_TENANT_ID,
            FactorExposureResult.instrument_id == inst,
            CalculationRun.code_version == "demo-mf1",
        )
    ).scalar_one()
    atom = qty * Decimal(mark)
    expected = (beta * atom).quantize(_SIX_DP, rounding=ROUND_HALF_UP)
    assert Decimal(row.exposure_amount) == expected
    assert Decimal(row.loading) == beta


def test_the_new_records_evidence_and_the_alpha1_exception(db: Session) -> None:
    """Every TRIGGERED record cites its own COMPLETED in-tenant run + the MF-1 DOCUMENT row; the
    loadings INITIAL exists (AWC); the alpha=1 version's latest record is an unexpired EXCEPTION."""
    for code in _FLAGSHIP_AWC_CODES:
        latest = _validations_of(db, code)[0]
        evidence = (
            db.execute(
                select(ModelValidationEvidence).where(
                    ModelValidationEvidence.validation_id == latest.id
                )
            )
            .scalars()
            .all()
        )
        kinds = sorted(e.evidence_type for e in evidence)
        assert kinds == ["CALCULATION_RUN", "DOCUMENT"]
        run_id = next(e.run_id for e in evidence if e.evidence_type == "CALCULATION_RUN")
        run = db.execute(
            select(CalculationRun).where(CalculationRun.run_id == str(run_id))
        ).scalar_one()
        assert run.status == RunStatus.COMPLETED.value
        assert run.tenant_id == DEMO_TENANT_ID
        assert run.code_version == "demo-mf1"
        doc = next(e for e in evidence if e.evidence_type == "DOCUMENT")
        assert "mf_1_decision_record.md" in str(doc.reference)

    loadings_rows = _validations_of(db, FACTOR_EXPOSURE_LOADINGS_MODEL_CODE)
    assert len(loadings_rows) == 1
    assert loadings_rows[0].validation_type == "INITIAL"
    assert loadings_rows[0].outcome == "APPROVED_WITH_CONDITIONS"

    desmooth_rows = _validations_of(db, "perf.return.desmoothed_geltner")
    # Two records on the ONE head: the campaign's alpha=0.4 EXCEPTION + the alpha=1 EXCEPTION —
    # the version grain distinguishes them.
    versions = {
        str(v.id): v.code_version
        for v in db.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID, Model.code == "perf.return.desmoothed_geltner"
            )
        )
        .scalars()
        .all()
    }
    alpha1_rows = [r for r in desmooth_rows if versions[str(r.model_version_id)] == "demo-mf1"]
    assert len(alpha1_rows) == 1
    assert alpha1_rows[0].validation_type == "EXCEPTION"
    assert alpha1_rows[0].conditions and "FL-1" not in alpha1_rows[0].conditions


def test_the_coverage_gate_refuses_an_unloaded_atom(db: Session) -> None:
    """A THROWAWAY portfolio with one unloaded instrument refuses the loadings run pre-create
    (the sleeve itself never trips the gate — every atom is promoted by construction)."""
    from datetime import UTC, datetime

    from irp_shared.exposure import ExposureActor, run_exposure
    from irp_shared.portfolio import PortfolioActor, create_portfolio
    from irp_shared.position import create_position
    from irp_shared.position.service import PositionActor
    from irp_shared.reference.instrument import create_instrument
    from irp_shared.reference.service import ReferenceActor
    from irp_shared.risk import FactorExposureActor, run_factor_exposure
    from irp_shared.risk.factor_service import FactorExposureInputError
    from irp_shared.valuation import create_valuation
    from irp_shared.valuation.service import ValuationActor

    loadings_version = db.execute(
        select(ModelVersion)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(
            Model.tenant_id == DEMO_TENANT_ID,
            Model.code == FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
        )
    ).scalar_one()
    factor_ids = [
        str(f.id)
        for f in db.execute(
            select(Factor).where(
                Factor.tenant_id == DEMO_TENANT_ID, Factor.factor_family != "CURRENCY"
            )
        )
        .scalars()
        .all()
    ]
    assert len(factor_ids) == 3

    pf = create_portfolio(
        db,
        tenant_id=DEMO_TENANT_ID,
        code="MF1-THROWAWAY",
        name="coverage-gate probe (not the sleeve)",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="probe"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=DEMO_TENANT_ID,
        code="MF-UNLOADED",
        name="Unloaded probe instrument",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="probe"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=DEMO_TENANT_ID,
        actor=PositionActor(actor_id="probe"),
        quantity=Decimal("10"),
        valid_from=datetime(2024, 6, 1, tzinfo=UTC),
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=_MF_AS_OF,
        acting_tenant=DEMO_TENANT_ID,
        actor=ValuationActor(actor_id="probe"),
        mark_value=Decimal("50.00"),
        currency_code="USD",
        valid_from=datetime(2024, 6, 1, tzinfo=UTC),
    )
    db.flush()
    exposure = run_exposure(
        db,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id="probe"),
        code_version="mf1-probe",
        environment_id="demo",
        portfolio_id=pf,
        as_of_valid_at=datetime(_MF_AS_OF.year, _MF_AS_OF.month, _MF_AS_OF.day, tzinfo=UTC),
        base_currency="USD",
    )
    assert exposure.status == RunStatus.COMPLETED.value
    with pytest.raises(FactorExposureInputError, match="requires every atom to carry"):
        run_factor_exposure(
            db,
            acting_tenant=DEMO_TENANT_ID,
            actor=FactorExposureActor(actor_id="probe"),
            code_version="mf1-probe",
            environment_id="demo",
            model_version_id=loadings_version.id,
            exposure_run_id=exposure.run.run_id,
            factor_ids=factor_ids,
        )
    db.rollback()  # the probe leaves nothing behind
