"""PostgreSQL end-state test for the SR-1 demo stage 17 (Wave-13 slice 2, the 22nd governed number).

Gated on ``IRP_TEST_DATABASE_URL``. Runs the stage ONCE (module-scoped) over the living demo tenant
and asserts the governed end state — the demo PROVES the risk-adjusted return rather than asserting
it.

**The filename is load-bearing** (the standing stage-ordering discipline): local batteries collect
alphabetically and earlier suites pin governed-code sets with set-equality, so each new stage
appends one more ``z``. ``stage9zzzzzzzz`` (EIGHT) collates after RM-1's stage-16 ``stage9zzzzzzz``
(seven) — verified by ``ls`` on the tests directory, not read off the decision record, which is
exactly how RM-1 discovered its own ratified name had gone stale.

**RELAYED AT REF-1: this pin is now INTERMEDIATE.** The final-position pin moved to
``test_demo_stage9zzzzzzzzz_ref1_pg.py`` (nine ``z``), which collates after stage 18. This pin
stays — an intermediate pin at a known collation point is useful — but it is no longer the one
that proves the demo's END state. Original note follows.

**This file also carried the FINAL-POSITION count pin forward.** The 7-z suite's pin was named
"where the counts are actually FINAL" and stopped being final the moment this stage landed; it is
demoted there to an explicitly-intermediate pin, and the final-position pin lives here. That relay
is the point: *a final-position pin is a RELAY BATON, not a monument*, and the platform has already
shipped one merged record claiming "counts unchanged" because an earlier pin collated before the
stage that moved them.
"""

from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, DemoSr1AlreadySeededError, run_demo_sr1_stage17
from irp_shared.marketdata.models import BenchmarkReturn
from irp_shared.perf.events import RUN_TYPE_SHARPE
from irp_shared.perf.models import (
    METRIC_TYPE_SHARPE_RATIO,
    METRIC_TYPE_SHARPE_RATIO_ANN,
    SharpeRatioResult,
)
from irp_shared.perf.sharpe_kernel import ZERO_DISPERSION_REASON

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_Q = Decimal(1).scaleb(-12)


@pytest.fixture(scope="module")
def summary():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_sr1_stage17(session)
            session.commit()
        except DemoSr1AlreadySeededError:
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


def _rows(db) -> list[SharpeRatioResult]:  # noqa: ANN001
    return list(db.execute(select(SharpeRatioResult)).scalars())


def test_the_stage_captured_a_real_risk_free_series_and_ran_a_governed_sharpe(summary) -> None:  # noqa: ANN001
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    assert result.risk_free_row_count == 18
    assert result.sharpe_run_id and result.portfolio_return_run_id
    assert result.risk_free_benchmark_id


def test_the_risk_free_series_is_NOT_constant(summary, db) -> None:  # noqa: ANN001
    """THE FIXTURE'S LOAD-BEARING PROPERTY. Against a CONSTANT risk-free rate,
    ``sigma(excess) == sigma(portfolio)`` identically — so the demo would be unable to distinguish
    the Sharpe (1994) construction this platform implements from the Sharpe (1966) one it refuses,
    and the whole stage would demonstrate nothing about its own crux.

    A demo that cannot REACH a control does not demonstrate it (the OPS-1 standing lesson).

    **SCOPED TO THE RISK-FREE HEAD, and the first version was not.** It counted distinct values over
    EVERY ``benchmark_return`` in the demo tenant — and stage 10 already captured eight rows with
    eight distinct values, so the assertion passed on another stage's data. Replacing this stage's
    entire eighteen-row series with eighteen identical values left it green. A test that reads
    beyond the thing it names is measuring someone else's fixture.
    """
    _factory, result = summary
    rf_id = (
        result.risk_free_benchmark_id
        if result is not None
        else str(db.execute(select(SharpeRatioResult.risk_free_benchmark_id).limit(1)).scalar_one())
    )
    values = {
        r.return_value
        for r in db.execute(
            select(BenchmarkReturn).where(
                BenchmarkReturn.tenant_id == DEMO_TENANT_ID,
                BenchmarkReturn.benchmark_id == rf_id,
            )
        ).scalars()
    }
    assert len(values) > 1, (
        f"the risk-free series carries {len(values)} distinct value(s) — a constant rate makes "
        "sigma(excess) == sigma(portfolio) and the demo demonstrates nothing about its own crux"
    )


def test_the_demo_actually_EXERCISES_the_month_key_join(db) -> None:  # noqa: ANN001
    """THE FIXTURE'S SECOND LOAD-BEARING PROPERTY, added after a review found the first version of
    this stage could not reach the control it claimed to demonstrate.

    Stage 16's book values on the LAST WEEKDAY of each month; this stage dates its risk-free rows on
    the CALENDAR month end. For roughly five months of twelve those differ — so the run only
    COMPLETES because the legs join by MONTH KEY rather than by date. Dating the risk-free rows on
    the book's own boundaries (as the first version did) made the capture tautologically
    date-identical to the pins, and the demo proved nothing about the criterion the decision record
    calls the load-bearing new one.

    A demo that cannot REACH a control does not demonstrate it (the OPS-1 standing lesson).
    """
    from irp_shared.perf.models import METRIC_TYPE_DIETZ_PERIOD, PortfolioReturnResult

    # Wave-13 close fold: BOTH reads are now scoped to the run under test. The first version read
    # EVERY benchmark_return in the demo tenant and every DIETZ period_end — the exact un-scoped
    # read its own SIBLING test (the constant-rate pin, above) was tightened to avoid, in the same
    # file, for the same reason. It discriminated only because stage 10's eight rf dates all
    # coincide with campaign period_ends; a stage-10 fixture change could have satisfied
    # `differing` while THIS stage's series was tautologically date-identical to the book.
    sr = db.execute(select(SharpeRatioResult).limit(1)).scalars().first()
    assert sr is not None, "no Sharpe rows — the stage under test did not run"
    rf_dates = {
        r.return_date
        for r in db.execute(
            select(BenchmarkReturn).where(
                BenchmarkReturn.tenant_id == DEMO_TENANT_ID,
                BenchmarkReturn.benchmark_id == sr.risk_free_benchmark_id,
            )
        ).scalars()
    }
    book_dates = {
        r.period_end
        for r in db.execute(
            select(PortfolioReturnResult).where(
                PortfolioReturnResult.tenant_id == DEMO_TENANT_ID,
                PortfolioReturnResult.metric_type == METRIC_TYPE_DIETZ_PERIOD,
                PortfolioReturnResult.calculation_run_id == sr.portfolio_return_run_id,
            )
        ).scalars()
    }
    assert rf_dates and book_dates
    differing = rf_dates - book_dates
    assert differing, (
        "every risk-free date coincides with a book boundary — the month-key join is not exercised "
        "and this demo demonstrates nothing about it"
    )
    # ... and the two legs must cover the SAME months: differing DATES with matching MONTHS is
    # precisely "the join is exercised"; a month mismatch would mean the difference set came from
    # somewhere other than the date-vs-month distinction this pin exists to prove.
    assert {(d.year, d.month) for d in rf_dates} == {(d.year, d.month) for d in book_dates}


def test_the_twelve_month_window_is_a_GENUINE_rolling_series(db) -> None:  # noqa: ANN001
    """18 monthly observations and a 12-month window give SEVEN evaluation points, not one — the
    difference between a rolling surface and a scalar dressed as one."""
    raw = [
        r for r in _rows(db) if r.window_months == 12 and r.metric_type == METRIC_TYPE_SHARPE_RATIO
    ]
    assert len(raw) == 7
    assert len({r.period_end for r in raw}) == 7
    assert all(not r.suppressed and r.metric_value is not None for r in raw)
    assert all(r.n_observations == 12 for r in raw)


def test_the_annualized_pair_reconciles_on_every_emitted_window(db) -> None:  # noqa: ANN001
    """Consumes the PERSISTED rows, both sides. A consumer must be able to multiply the raw row by
    sqrt(12) and land exactly on the annualized row — which is why the annualizer reads the STORED
    12dp value rather than an unquantized intermediate."""
    raw = {
        (r.window_months, r.period_end): r.metric_value
        for r in _rows(db)
        if r.metric_type == METRIC_TYPE_SHARPE_RATIO and not r.suppressed
    }
    annualized = {
        (r.window_months, r.period_end): r.metric_value
        for r in _rows(db)
        if r.metric_type == METRIC_TYPE_SHARPE_RATIO_ANN and not r.suppressed
    }
    assert raw and raw.keys() == annualized.keys()
    for key, stored in raw.items():
        assert stored is not None
        with localcontext() as ctx:
            ctx.prec = 50
            expected = (stored * Decimal(12).sqrt()).quantize(_Q, rounding=ROUND_HALF_UP)
        assert annualized[key] == expected, f"pair failed to reconcile at {key}"


def test_the_unfillable_36_month_window_emitted_SUPPRESSED_rows_on_real_data(db) -> None:  # noqa: ANN001
    """The nullable-value + explicit-flag encoding, exercised on the real demo book rather than in a
    unit fixture. BOTH members of the pair are suppressed — never one of the two."""
    thirty_six = [r for r in _rows(db) if r.window_months == 36]
    assert len(thirty_six) == 2
    assert {r.metric_type for r in thirty_six} == {
        METRIC_TYPE_SHARPE_RATIO,
        METRIC_TYPE_SHARPE_RATIO_ANN,
    }
    for row in thirty_six:
        assert row.suppressed and row.metric_value is None
        assert row.suppression_reason and "18 monthly observations" in row.suppression_reason
        assert row.n_observations is None  # there IS no sample — distinct from zero dispersion
        assert row.suppression_reason != ZERO_DISPERSION_REASON


def test_the_run_emitted_EXACTLY_the_expected_row_inventory(db) -> None:  # noqa: ANN001
    """A total pin, which RM-1's suite has and the first version of this one lacked: 7 evaluation
    points x 2 metrics at W=12, plus the suppressed pair at W=36. Without it a stray extra
    metric/window row passes unnoticed, since every other test here filters."""
    assert len(_rows(db)) == 16


def test_every_persisted_row_carries_its_risk_free_provenance(db) -> None:  # noqa: ANN001
    """The reason ENT-065 exists rather than an ENT-064 column: a Sharpe ratio that cannot say what
    the excess was measured against is not evidence of anything."""
    rows = _rows(db)
    assert rows
    for row in rows:
        assert row.risk_free_benchmark_id
        assert row.rf_return_basis == "TOTAL"
        assert row.portfolio_return_run_id and row.portfolio_id
        assert row.input_snapshot_id and row.model_version_id


def test_a_second_seed_refuses_rather_than_silently_skipping(db) -> None:  # noqa: ANN001
    with pytest.raises(DemoSr1AlreadySeededError):
        run_demo_sr1_stage17(db)


def test_the_demo_tenant_counts_are_pinned_where_they_are_actually_FINAL(db) -> None:  # noqa: ANN001
    """THE FINAL-POSITION COUNT PIN, relayed from the 7-z suite.

    Measured on a fresh-schema battery, never derived:

    - **25 model codes** — SR-1 adds ``perf.sharpe``, the 22nd governed number's model.
    - **40 validations** — the stage files a tier + an INITIAL APPROVED_WITH_CONDITIONS record, as
      every prior new-code stage does. The perf registrar mints none implicitly, which is why the
      stage must; omitting it (as RM-1's first implementation did) would leave ``perf.sharpe`` the
      only model code in the inventory with no tier and no validation.
    - **133 COMPLETED runs** — 132 after stage 16, plus SR-1's ONE Sharpe run. This stage seeds no
      book and no second PM-1 run: it reuses stage 16's entirely.

    The 7-z suite's equivalent pin is now labelled INTERMEDIATE and still asserts 24/39/132 at its
    own collation point. That is correct and deliberate — it can only ever see the state before this
    stage runs — and it is why the final-position pin has to move with each new stage.
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
        25,
        40,
        133,
    ), f"demo counts drifted: {model_codes}/{validations}/{completed} (expected 25/40/133)"
    # NOTE (REF-1): INTERMEDIATE pin — this suite collates BEFORE stage 18, so it cannot see
    # anything that stage does. The final-position pin lives in the 9-z REF-1 suite.


def test_sr1_contributed_exactly_ONE_completed_run(db) -> None:  # noqa: ANN001
    """The slice's OWN contribution, isolated from the baseline — so a future baseline shift is
    attributed correctly instead of being absorbed into SR-1's number."""
    from irp_shared.calc.models import CalculationRun

    sharpe = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == RUN_TYPE_SHARPE,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert sharpe == 1
