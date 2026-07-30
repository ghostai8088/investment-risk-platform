"""PostgreSQL end-state test for the CON-1 demo stage 19 — the first CONCENTRATION numbers.

Gated on ``IRP_TEST_DATABASE_URL``. Runs the stage ONCE (module-scoped) over the living demo tenant
and asserts the governed end state against the CON-1 record's Part 2 HAND-DERIVED literals.

**The filename is load-bearing** (the standing stage-ordering discipline): TEN ``z`` — verified by
``ls`` on the tests directory (sr1 = eight, ref1 = nine), never read off a decision record.

**This file takes the FINAL-POSITION count pin, relayed from the 9-z suite: 25/40/133 →
26/41/136** (+1 ``concentration.dimensional`` model code, +1 INITIAL validation, +3 COMPLETED
runs; the DEMO-MULTIASSET refusal is a FAILED run and is additionally pinned BY STATUS — a
refusal that quietly completed, or quietly vanished, would both be defects).
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.concentration.models import (
    BUCKET_SUMMARY,
    BUCKET_UNCLASSIFIABLE,
    BUCKET_UNCLASSIFIED,
    ConcentrationResult,
)
from irp_shared.concentration.service import (
    latest_concentration,
    list_concentration_issuer_detail,
)
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, DemoCon1AlreadySeededError, run_demo_con1_stage19
from irp_shared.model.models import Model, ModelValidation
from irp_shared.portfolio.models import Portfolio

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def summary():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_con1_stage19(session)
            session.commit()
        except DemoCon1AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(summary):  # noqa: ANN001, ANN201
    factory, _ = summary
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def _d(v: str) -> Decimal:
    return Decimal(v)


def _run_rows(db, run_id):  # noqa: ANN001, ANN202
    return list(
        db.execute(
            select(ConcentrationResult).where(
                ConcentrationResult.tenant_id == DEMO_TENANT_ID,
                ConcentrationResult.calculation_run_id == str(run_id),
            )
        ).scalars()
    )


def test_the_stage_ran_and_declared_its_contribution(summary) -> None:  # noqa: ANN001
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    assert result.completed_runs_added == 3
    assert result.validations_added == 1


def test_flagship_issuer_shares_reproduce_the_part2_literals(summary, db) -> None:  # noqa: ANN001
    """The DEMO-GLOBAL boundary book: shares + HHI to six decimals — the record's own numbers."""
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    rows = _run_rows(db, result.global_concentration_run_id)
    issuer_detail = {
        r.bucket_code: r.share_invested_long
        for r in rows
        if r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL"
    }
    # Buckets are keyed by issuer id string; compare the SHARE MULTISET (ids are run-local).
    assert sorted(issuer_detail.values()) == [
        _d("0.212598"),
        _d("0.372980"),
        _d("0.414422"),
    ]
    summary_rows = {
        r.metric_type: r for r in rows if r.row_kind == "SUMMARY" and r.dimension_kind == "ISSUER"
    }
    assert summary_rows["HHI_ISSUER"].metric_value == _d("0.356057")
    assert summary_rows["MAX_SHARE_ISSUER"].metric_value == _d("0.414422")
    assert summary_rows["HHI_ISSUER"].coverage_ratio == _d("1.000000")
    sector = {
        r.bucket_code: r.share_invested_long
        for r in rows
        if r.dimension_kind == "SECTOR_INDUSTRY" and r.row_kind == "DETAIL"
    }
    assert sector == {"C": _d("0.627020"), "K": _d("0.372980")}
    country = {
        r.bucket_code: r.share_invested_long
        for r in rows
        if r.dimension_kind == "COUNTRY_OF_RISK" and r.row_kind == "DETAIL"
    }
    assert country == {"US": _d("0.787402"), "DE": _d("0.212598")}


def test_coverage_book_reproduces_the_v6_per_dimension_literals(summary, db) -> None:  # noqa: ANN001
    """DEMO-CONCENTRATION: BETA-LLC is CLASSIFIED in the issuer dimension (the v6 correction);
    the residual demonstration lives in sector/country."""
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    rows = _run_rows(db, result.book_concentration_run_id)

    issuer_shares = sorted(
        r.share_invested_long
        for r in rows
        if r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL"
    )
    assert issuer_shares == [_d("0.100000"), _d("0.300000"), _d("0.600000")]
    issuer_summary = {
        r.metric_type: r for r in rows if r.row_kind == "SUMMARY" and r.dimension_kind == "ISSUER"
    }
    assert issuer_summary["HHI_ISSUER"].metric_value == _d("0.450000")
    assert issuer_summary["CR_5_ISSUER"].metric_value == _d("0.900000")
    assert issuer_summary["HHI_ISSUER"].coverage_ratio == _d("0.900000")
    assert issuer_summary["HHI_ISSUER"].coverage_classifiable == _d("1.000000")

    sector = {
        r.bucket_code: r.share_invested_long
        for r in rows
        if r.dimension_kind == "SECTOR_INDUSTRY" and r.row_kind == "DETAIL"
    }
    assert sector == {
        "C": _d("0.600000"),
        BUCKET_UNCLASSIFIED: _d("0.300000"),
        BUCKET_UNCLASSIFIABLE: _d("0.100000"),
    }
    sector_summary = {
        r.metric_type: r
        for r in rows
        if r.row_kind == "SUMMARY" and r.dimension_kind == "SECTOR_INDUSTRY"
    }
    assert sector_summary["HHI_SECTOR_INDUSTRY"].metric_value == _d("0.360000")
    assert sector_summary["HHI_SECTOR_INDUSTRY"].coverage_ratio == _d("0.600000")
    assert sector_summary["HHI_SECTOR_INDUSTRY"].coverage_classifiable == _d("0.666667")


def test_multiasset_refusal_is_a_FAILED_run_with_the_00_gap_and_zero_rows(  # noqa: ANN001
    summary, db
) -> None:
    """The v6 re-timing pinned from the DB: the refusal run EXISTS (FAILED), names the 0/0
    all-UNCLASSIFIABLE gap (not the coverage floor), and wrote nothing."""
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    run = db.execute(
        select(CalculationRun).where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_id == result.multiasset_failed_run_id,
        )
    ).scalar_one()
    assert run.status == "FAILED"
    assert "ALL_UNCLASSIFIABLE" in (run.failure_reason or "")
    assert _run_rows(db, run.run_id) == []


def test_the_view_read_never_returns_issuer_identity(summary, db) -> None:  # noqa: ANN001
    """The structural issuer split, proven on demo data: the .view shape carries NO issuer-detail
    rows; the .issuer.view reader carries ONLY them."""
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    view_rows = latest_concentration(db, acting_tenant=DEMO_TENANT_ID)
    assert view_rows, "the latest resolver must see the newest COMPLETED run"
    assert not any(
        r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL" for r in view_rows
    ), "an issuer-identity row leaked into the .view shape"
    assert all(r.bucket_code == BUCKET_SUMMARY for r in view_rows if r.row_kind == "SUMMARY")
    issuer_rows = list_concentration_issuer_detail(db, acting_tenant=DEMO_TENANT_ID)
    assert issuer_rows, "the issuer reader must return the issuer detail"
    assert all(r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL" for r in issuer_rows)
    assert all(
        r.issuer_id is not None or r.bucket_code == BUCKET_UNCLASSIFIABLE for r in issuer_rows
    )


def test_demo_counts_moved_to_the_declared_triple_at_final_position(db) -> None:  # noqa: ANN001
    """THE FINAL-POSITION PIN, relayed from the 9-z suite: 25/40/133 → **26/41/136** (OQ-CON-1-22,
    re-measured here on the fresh battery — never derived)."""
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
    assert (model_codes, validations, completed) == (
        26,
        41,
        136,
    ), f"demo counts drifted: {model_codes}/{validations}/{completed} (expected 26/41/136)"


def test_the_dedicated_book_exists_with_its_three_coverage_classes(db) -> None:  # noqa: ANN001
    pf = db.execute(
        select(Portfolio).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == "DEMO-CONCENTRATION"
        )
    ).scalar_one()
    assert pf.name.startswith("Demo concentration")
