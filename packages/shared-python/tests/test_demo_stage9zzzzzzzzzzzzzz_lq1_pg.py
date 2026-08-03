"""The LQ-1 demo-stage suite (stage 23) — the 24th governed number family, live on PG.

Runs last AMONG THE DEMO SUITES (the 14-z name sorts after every earlier demo suite; the DATA-1
relay precedent) so it sees the FULL demo tenant.

**THE FINAL-POSITION COUNT PIN RELAYS HERE.** The 13-z DATA-1 suite is demoted to POSITIONAL in
the same commit — exactly one file carries the label. The triple is MEASURED on a fresh-schema
battery, never derived: LQ-1 adds one model code, one INITIAL validation and two COMPLETED runs,
but the *arithmetic* is not the pin. The refusal-control run is FAILED and is pinned by status so
it can never be mistaken for a completed one.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.classification.models import (
    DIMENSION_KIND_LIQUIDITY_TIER,
    LIQUIDITY_TIER_CODES,
    SCHEME_FAMILY_SEC_22E4,
    ClassificationAssignment,
    ClassificationScheme,
)
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_lq1_stage23
from irp_shared.demo.lq1_stage23 import DemoLq1AlreadySeededError
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.liquidity.bootstrap import LIQUIDITY_MODEL_CODE
from irp_shared.liquidity.models import BUCKET_UNCLASSIFIED, LiquidityResult
from irp_shared.model.models import Model, ModelValidation

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def staged():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_lq1_stage23(session)
            session.commit()
        except DemoLq1AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture
def db(staged):  # noqa: ANN001, ANN201
    factory, _ = staged
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def test_the_22e4_ladder_is_system_seeded_with_the_four_named_categories(db) -> None:  # noqa: ANN001
    """The vocabulary is the RULE's, not the platform's, and it is readable by every tenant."""
    scheme = db.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            ClassificationScheme.scheme_family == SCHEME_FAMILY_SEC_22E4,
        )
    ).scalar_one()
    assert scheme.dimension_kind == DIMENSION_KIND_LIQUIDITY_TIER

    codes = {
        r.node_code
        for r in db.execute(
            select(ClassificationAssignment).where(
                ClassificationAssignment.tenant_id == DEMO_TENANT_ID,
                ClassificationAssignment.dimension_kind == DIMENSION_KIND_LIQUIDITY_TIER,
                ClassificationAssignment.valid_to.is_(None),
                ClassificationAssignment.system_to.is_(None),
            )
        ).scalars()
    }
    assert codes <= set(LIQUIDITY_TIER_CODES)
    assert "ILLIQUID" in codes, "the book must actually carry an illiquid holding"


def test_the_flagship_run_reports_the_hand_computed_shares(staged) -> None:  # noqa: ANN001
    """Hand-computed from the seeded book: long = 40,000 + 20,000 + 30,000 + 10,000 = 100,000.

    illiquid 30,000/100,000 = 0.3 · highly liquid 40,000/100,000 = 0.4 · coverage 90,000/100,000
    = 0.9 (the untiered 10,000 is IN the denominator and OUT of coverage).
    """
    _, summary = staged
    if summary is None:
        pytest.skip("stage already seeded in this database")
    assert summary.illiquid_share == Decimal("0.300000")
    assert summary.highly_liquid_share == Decimal("0.400000")
    assert summary.coverage_ratio == Decimal("0.900000")
    assert summary.untiered_instrument_count == 1


def test_the_untiered_holding_is_UNCLASSIFIED_and_stays_in_the_denominator(db) -> None:  # noqa: ANN001
    """The ratified OQ-LQ-1-19 semantics, asserted on persisted rows rather than on the kernel."""
    rows = list(
        db.execute(
            select(LiquidityResult).where(
                LiquidityResult.tenant_id == DEMO_TENANT_ID,
                LiquidityResult.row_kind == "DETAIL",
            )
        ).scalars()
    )
    assert rows, "the flagship run wrote no detail rows"
    by_bucket = {r.bucket_code: r for r in rows}
    assert BUCKET_UNCLASSIFIED in by_bucket, "the residual bucket must be materialised"
    assert by_bucket[BUCKET_UNCLASSIFIED].tier_share == Decimal("0.100000")
    # Every declared tier is present even at zero — a vector with holes is not a vector.
    assert set(LIQUIDITY_TIER_CODES) <= set(by_bucket)
    # The shares sum to exactly 1: nothing was dropped from the denominator.
    assert sum(r.tier_share for r in by_bucket.values()) == Decimal("1.000000")


def test_the_denominator_basis_is_stamped_on_every_row(db) -> None:  # noqa: ANN001
    """The name is the control: a reader must never have to infer which book a share is against."""
    bases = {
        r.denominator_basis
        for r in db.execute(
            select(LiquidityResult).where(LiquidityResult.tenant_id == DEMO_TENANT_ID)
        ).scalars()
    }
    assert bases == {"INVESTED_LONG"}


def test_the_sub_floor_run_COMMITTED_FAILED_WITH_ZERO_ROWS(staged) -> None:  # noqa: ANN001
    """The fail-closed direction that matters.

    A coverage floor above the book's real coverage must produce a committed FAILED run with NO
    rows — not a completed run reporting a confident illiquid share over a book nobody finished
    classifying. Asserted on the DATABASE, not on the return value.
    """
    factory, summary = staged
    if summary is None:
        pytest.skip("stage already seeded in this database")
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        run = session.execute(
            select(CalculationRun).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_id == summary.refused_run_id,
            )
        ).scalar_one()
        assert run.status == "FAILED"
        assert run.failure_reason and "coverage" in run.failure_reason.lower()
        rows = session.execute(
            select(func.count())
            .select_from(LiquidityResult)
            .where(LiquidityResult.calculation_run_id == summary.refused_run_id)
        ).scalar_one()
        assert rows == 0, "a refused run must write NOTHING"
    finally:
        session.close()


def test_the_model_is_registered_with_its_limitations(db) -> None:  # noqa: ANN001
    """The limitation that matters must exist as a ROW, not only as prose in a record."""
    from irp_shared.model.models import ModelLimitation, ModelVersion

    model = db.execute(
        select(Model).where(Model.tenant_id == DEMO_TENANT_ID, Model.code == LIQUIDITY_MODEL_CODE)
    ).scalar_one()
    versions = list(
        db.execute(select(ModelVersion).where(ModelVersion.model_id == model.id)).scalars()
    )
    assert versions
    texts = [
        r.limitation_text
        for r in db.execute(
            select(ModelLimitation).where(
                ModelLimitation.model_version_id.in_([v.id for v in versions])
            )
        ).scalars()
    ]
    joined = " ".join(texts)
    assert "NOT the SEC Rule 22e-4 15% test" in joined
    assert "NOT DETERMINABLE" in joined, "the indeterminate error direction must be recorded"
    assert "22e-4(b)(1)(ii)(B)" in joined, "the position-size gap must be recorded"


def test_the_final_position_count_pin(db) -> None:  # noqa: ANN001
    """FINAL-POSITION pin — MEASURED on a fresh battery, never derived.

    LQ-1 adds one model code, one INITIAL validation and two COMPLETED runs; the FAILED refusal
    run is pinned by status above and is deliberately NOT counted here.
    """
    model_codes = db.execute(
        select(func.count(func.distinct(Model.code))).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    validations = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    completed = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert (model_codes, validations, completed) == (27, 44, 141)
