"""The DATA-1 demo-stage suite (stage 22) — the first genuinely EXTERNAL dataset, live on PG.

Runs LAST in the battery (the 13-z name sorts after every earlier demo suite; the CAL-1b relay
precedent) so it sees the FULL demo tenant: the campaign, RM-1/SR-1, CON-1, LIM-2, CAL-1b's
stage 21 — and proves stage 22 adds the real TB3MS series WITHOUT minting a single governed
number.

**THE FINAL-POSITION COUNT PIN RELAYS HERE, UNCHANGED: 26/43/139** (MEASURED on a fresh-schema
battery — a captured input binds no model, no validation, no calculation_run; the pin NOT moving
is the assertion).
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_data1_stage22
from irp_shared.demo.data1_stage22 import (
    DATA1_BENCHMARK_CODE,
    DATA1_BENCHMARK_SOURCE,
    DemoData1AlreadySeededError,
)
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.marketdata import COMPLETENESS_RULE_CODE, BenchmarkRate
from irp_shared.marketdata.models import Benchmark
from irp_shared.marketdata.tb3ms_rates import TB3MS_COMPLETE_THROUGH, TB3MS_RATES
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
            result = run_demo_data1_stage22(session)
            session.commit()
        except DemoData1AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(staged):  # noqa: ANN001, ANN201
    factory, _ = staged
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def _head(db) -> Benchmark:  # noqa: ANN001
    return db.execute(
        select(Benchmark).where(
            Benchmark.tenant_id == DEMO_TENANT_ID,
            Benchmark.benchmark_code == DATA1_BENCHMARK_CODE,
            Benchmark.benchmark_source == DATA1_BENCHMARK_SOURCE,
        )
    ).scalar_one()


def test_the_demo_tenant_captured_the_real_tb3ms_dataset(db) -> None:  # noqa: ANN001
    """The exact 30-observation set, verbatim fractions, under the declared horizon."""
    head = _head(db)
    rows = (
        db.execute(
            select(BenchmarkRate).where(
                BenchmarkRate.tenant_id == DEMO_TENANT_ID,
                BenchmarkRate.benchmark_id == head.id,
                BenchmarkRate.valid_to.is_(None),
                BenchmarkRate.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert {(r.rate_date, r.rate_value) for r in rows} == {
        (d, v.quantize(Decimal("1.000000000000"))) for d, v in TB3MS_RATES
    }
    assert head.rates_complete_through == TB3MS_COMPLETE_THROUGH
    # the coexistence fact: the demo rf head (USD-CASH-1M/DEMO_VENDOR) is untouched
    rf_head = db.execute(
        select(func.count())
        .select_from(Benchmark)
        .where(
            Benchmark.tenant_id == DEMO_TENANT_ID,
            Benchmark.benchmark_code == "USD-CASH-1M",
        )
    ).scalar_one()
    assert rf_head == 1


def test_the_completeness_rule_says_what_was_expected_and_passed(db) -> None:  # noqa: ANN001
    """The REF-1 trigger honored on real data: the persisted rule carries the 30 expected month
    keys; its evidence row is a PASS."""
    rule = db.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == DEMO_TENANT_ID,
            DataQualityRule.code == COMPLETENESS_RULE_CODE,
        )
    ).scalar_one()
    assert rule.rule_type == "COMPLETENESS"
    assert len(rule.params["expected"]) == 30
    assert rule.params["expected"][0] == "2024-01" and rule.params["expected"][-1] == "2026-06"
    outcomes = [
        r[0]
        for r in db.execute(
            select(DataQualityResult.outcome).where(
                DataQualityResult.tenant_id == DEMO_TENANT_ID,
                DataQualityResult.rule_id == rule.id,
            )
        )
    ]
    assert outcomes and all(o == "PASS" for o in outcomes)


def test_no_derived_monthly_return_row_exists_for_the_real_series(db) -> None:  # noqa: ANN001
    """THE capture-first negative pin (OQ-DATA-1-1a): the real series has ZERO benchmark_return
    rows — nothing re-expressed the yield into a return anywhere on the rails."""
    from irp_shared.marketdata.models import BenchmarkReturn

    head = _head(db)
    derived = db.execute(
        select(func.count())
        .select_from(BenchmarkReturn)
        .where(
            BenchmarkReturn.tenant_id == DEMO_TENANT_ID,
            BenchmarkReturn.benchmark_id == head.id,
        )
    ).scalar_one()
    assert derived == 0


def test_the_final_position_count_pin(db) -> None:  # noqa: ANN001
    """THE FINAL-POSITION PIN, relayed from the 12-z suite: **26/43/139 UNCHANGED** (MEASURED on
    the fresh battery — never derived). A captured INPUT minting zero codes, zero validations and
    zero runs IS the assertion (the CLAUDE.md pattern invariant, exercised on real data)."""
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
    assert (model_codes, validations, completed) == (26, 43, 139)


def test_stage22_summary_recorded_the_idempotent_rerun(staged) -> None:  # noqa: ANN001
    """On a fresh battery the stage itself proved the re-run: 30 added, then 0 (silent no-op)."""
    _, result = staged
    if result is None:
        pytest.skip("dirty double-run: the stage's own summary is not available")
    assert result.added == 30 and result.rerun_added == 0
    assert result.rates_complete_through == date(2026, 6, 30)
