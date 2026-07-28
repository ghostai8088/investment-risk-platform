"""PostgreSQL end-state test for the RM-1 demo stage 16 (Wave-13 slice 1, the 21st governed number).

Gated on ``IRP_TEST_DATABASE_URL``. Runs the stage ONCE (module-scoped) over the living demo tenant
and asserts the governed end state — the demo PROVES the rolling series rather than asserting it.

**The filename is load-bearing** (the standing stage-ordering discipline): local batteries collect
alphabetically and earlier suites pin governed-code sets with set-equality, so each new stage
appends one more ``z``. ``stage9zzzzzzz`` (SEVEN) collates after SCH-2's stage-15 ``stage9zzzzzz``
(six). The ratified record specified six — written the day before SCH-2 merged, when six was free.

The assertions target the three things the FIXTURE exists to make reachable. Each would pass
vacuously on a naive book, which is why the fixture is designed rather than arbitrary.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, DemoRm1AlreadySeededError, run_demo_rm1_stage16
from irp_shared.perf.models import (
    METRIC_TYPE_DIETZ_PERIOD,
    METRIC_TYPE_MAX_DRAWDOWN,
    METRIC_TYPE_ROLLING_RETURN_ANN,
    METRIC_TYPE_ROLLING_VOLATILITY,
    METRIC_TYPE_ROLLING_VOLATILITY_ANN,
    PortfolioReturnResult,
    RollingRiskResult,
)

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
            result = run_demo_rm1_stage16(session)
            session.commit()
        except DemoRm1AlreadySeededError:
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


def _rolling_rows(db) -> list[RollingRiskResult]:  # noqa: ANN001
    return list(db.execute(select(RollingRiskResult)).scalars())


def test_the_stage_drove_twenty_boundaries_through_a_real_governed_chain(summary) -> None:  # noqa: ANN001
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    assert len(result.exposure_run_ids) == 20
    assert result.portfolio_return_run_id
    assert result.rolling_risk_run_id


def test_ONE_month_genuinely_relinked_TWO_sub_periods(db) -> None:  # noqa: ANN001
    """**The crux of the slice, and the reason the fixture carries a mid-month boundary.**

    On a pure month-end calendar the within-month relink is the IDENTITY, so a demo built only from
    month-ends would exercise the relink without ever proving it does anything. 20 boundaries give
    19 sub-periods; if exactly one month holds two of them, the monthly series has 18 observations —
    strictly fewer than the sub-period count. That inequality IS the proof.
    """
    run_ids = {r.portfolio_return_run_id for r in _rolling_rows(db)}
    assert len(run_ids) == 1
    sub_periods = list(
        db.execute(
            select(PortfolioReturnResult).where(
                PortfolioReturnResult.calculation_run_id == next(iter(run_ids)),
                PortfolioReturnResult.metric_type == METRIC_TYPE_DIETZ_PERIOD,
            )
        ).scalars()
    )
    assert len(sub_periods) == 19
    distinct_months = {(p.period_end.year, p.period_end.month) for p in sub_periods}
    assert len(distinct_months) == 18, "no month relinked two sub-periods — the crux is untested"


def test_the_twelve_month_window_is_a_GENUINE_rolling_series(db) -> None:  # noqa: ANN001
    """18 monthly observations, a 12-month window => 7 windows. A single scalar would demonstrate
    nothing about a ROLLING statistic — which is precisely why extending the 9-boundary campaign
    was rejected at ratification."""
    volatility = [
        r
        for r in _rolling_rows(db)
        if r.metric_type == METRIC_TYPE_ROLLING_VOLATILITY and r.window_months == 12
    ]
    assert len(volatility) == 7
    assert len({r.period_end for r in volatility}) == 7  # seven DISTINCT evaluation points


def test_the_designed_drawdown_is_NON_ZERO(db) -> None:  # noqa: ANN001
    """Without a designed multi-month decline MDD is identically zero everywhere, and the drawdown
    leg would be indistinguishable from an unimplemented one. The fixture's path peaks then falls
    for five consecutive months to about -23%."""
    drawdowns = [
        r
        for r in _rolling_rows(db)
        if r.metric_type == METRIC_TYPE_MAX_DRAWDOWN and r.window_months == 12
    ]
    assert drawdowns
    worst = max(r.metric_value for r in drawdowns if r.metric_value is not None)
    assert worst > 0, "the drawdown leg is vacuous on this fixture"
    assert worst > Decimal("0.20"), f"the designed drawdown did not survive: {worst}"


def test_the_unfillable_36_month_window_emitted_SUPPRESSED_rows_on_real_data(db) -> None:  # noqa: ANN001
    """The suppression encoding exercised on the demo, not only in a unit fixture: NULL value +
    explicit flag + a reason, one row per metric. A stuffed zero would be indistinguishable from
    the legitimate zeros this same run also emits."""
    suppressed = [r for r in _rolling_rows(db) if r.window_months == 36]
    assert len(suppressed) == 5
    for row in suppressed:
        assert row.suppressed is True
        assert row.metric_value is None
        assert row.suppression_reason
        assert "36-month window" in row.suppression_reason


def test_the_annualized_volatility_pair_reconciles_on_every_emitted_window(db) -> None:  # noqa: ANN001
    """The two-row emission is only honest if a reader can verify one from the other. Checked here
    against PERSISTED rows, so the reconciliation survives the round-trip through PostgreSQL."""
    from irp_shared.perf.rolling_kernel import annualize_volatility

    rows = _rolling_rows(db)
    raw = {
        (r.window_months, r.period_end): r.metric_value
        for r in rows
        if r.metric_type == METRIC_TYPE_ROLLING_VOLATILITY
    }
    annualized = [r for r in rows if r.metric_type == METRIC_TYPE_ROLLING_VOLATILITY_ANN]
    assert annualized
    for row in annualized:
        stored = raw[(row.window_months, row.period_end)]
        if stored is None:
            assert row.metric_value is None
            continue
        assert row.metric_value == annualize_volatility(stored)


def test_the_twelve_month_window_shipped_no_redundant_annualized_return(db) -> None:  # noqa: ANN001
    """At W = 12 the geometric exponent is exactly 1, so the row would equal the cumulative return
    forever."""
    assert not [
        r
        for r in _rolling_rows(db)
        if r.metric_type == METRIC_TYPE_ROLLING_RETURN_ANN and r.window_months == 12
    ]


def test_every_persisted_row_satisfies_the_suppression_CHECK(db) -> None:  # noqa: ANN001
    """The DB constraint is total over the boolean; this asserts the invariant holds on real data
    (a row that violated it could never have been written, so a failure here means the CHECK is
    gone)."""
    total = db.execute(select(func.count()).select_from(RollingRiskResult)).scalar_one()
    assert total == 33  # 7 windows x 4 metrics + 5 suppressed
    for row in _rolling_rows(db):
        if row.suppressed:
            assert row.metric_value is None and row.suppression_reason is not None
        else:
            assert row.metric_value is not None and row.suppression_reason is None


def test_a_second_seed_refuses_rather_than_silently_skipping(db) -> None:  # noqa: ANN001
    with pytest.raises(DemoRm1AlreadySeededError):
        run_demo_rm1_stage16(db)


def test_the_demo_tenant_counts_after_stage_16_are_pinned_INTERMEDIATE(db) -> None:  # noqa: ANN001
    """The count pin at THIS stage's collation point — INTERMEDIATE since SR-1's stage 17 landed.

    **This test was named "...where they are actually FINAL" for exactly one slice.** It collates
    before stage 17, so it can only ever observe the totals as of stage 16 — which is correct and is
    why the numbers below are unchanged. What is NOT correct is calling that position final: the
    final-position pin is a RELAY BATON, and it now lives in
    ``test_demo_stage9zzzzzzzz_sr1_pg.py`` at 25/40/133.

    The platform's other absolute-count pin lives in the stage-13 suite and asserts 109 for the same
    structural reason. That is how SCH-2 shipped a merged record claiming "counts unchanged at
    23/38/109" while its stage 15 added one COMPLETED EXPOSURE_AGGREGATE run — nothing contradicted
    the record, because no pin collated after the stage that moved the number.

    Measured, not derived:
    - **24 model codes** — RM-1 adds `perf.rolling_risk`, the 21st governed number's model.
    - **39 validations** — the stage files a tier + an INITIAL APPROVED_WITH_CONDITIONS record, as
      every prior new-code stage does. The perf REGISTRAR mints none implicitly, which is why the
      stage must; omitting it (as the first implementation did) would leave `perf.rolling_risk` the
      only model code in the inventory with no tier and no validation.
    - **132 COMPLETED runs** — 110 after stage 15 (not the recorded 109), plus RM-1's 22
      (20 boundary exposure runs + 1 PM-1 + 1 RM-1).
    """
    from irp_shared.calc.models import CalculationRun
    from irp_shared.model.models import Model, ModelValidation

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
        24,
        39,
        132,
    ), f"demo counts drifted: {model_codes}/{validations}/{completed} (expected 24/39/132)"


def test_rm1_contributed_exactly_twenty_two_completed_runs(db) -> None:  # noqa: ANN001
    """The slice's OWN contribution, isolated from the baseline — so a future baseline shift is
    attributed correctly instead of being absorbed into RM-1's number."""
    from irp_shared.calc.models import CalculationRun

    rolling = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == "ROLLING_RISK",
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    returns = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == "PORTFOLIO_RETURN",
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert rolling == 1
    assert returns == 2  # the campaign's, plus stage 16's
