"""BOOK-1a — the Northlight tenant, seeded end to end on PostgreSQL and read back under RLS.

Independent of the base campaign's stage chain (its own tenant id, so the `(27, 44, 141)` census
filtered to the base tenant does not move) and of the alpha-sort ordering those suites depend on.
The module fixture runs the real orchestrator once on a fresh database and tolerates an
already-seeded tenant only for a dirty double-run of the suite itself; the second-seed refusal is
proven in its own test on a fresh session.

Every proof here reads STORED rows through the tenant's RLS context, the way the read endpoints
do. The three goldens are pinned verbatim; their hand derivations are in the slice record.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo_tenant import (
    TENANT_ID,
    DemoTenantAlreadySeededError,
    SeedSummary,
    book,
    seed_demo_tenant,
)
from irp_shared.entitlement.models import AppUser
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.liquidity.models import LiquidityResult
from irp_shared.marketdata.models import FxRate
from irp_shared.perf.models import RollingRiskResult
from irp_shared.portfolio.models import Portfolio
from irp_shared.reference.models import Instrument
from irp_shared.risk.models import ActiveRiskResult, VarResult
from irp_shared.tenancy.boundary import TenantNotAdmitted, assert_tenant_admitted
from irp_shared.valuation.models import Valuation

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

YEAR_END = date(2026, 6, 30)

#: The three hand-derived goldens (MD-H1; derivations in `w20_book1a_slice_record.md`).
GOLDEN_GMA_MARKET_VALUE_USD = Decimal("157800377.922680")
GOLDEN_EFI_LARGEST_SECTOR = ("O", Decimal("0.669801"))
GOLDEN_EFI_VAR_PARAMETRIC_EUR = Decimal("454548.838555")

#: The exact COMPLETED run count per family the remit's table commits to (Part 2.7, recounted).
EXPECTED_RUNS: dict[str, int] = {
    "EXPOSURE_AGGREGATE": 3 * len(book.BOUNDARIES) + 3 * len(book.MONTH_ENDS),
    "FACTOR_EXPOSURE": 3 * len(book.MONTH_ENDS) * 3,
    "COVARIANCE": 2 * len(book.MONTH_ENDS),
    "VAR": 3 * len(book.MONTH_ENDS) * 3,
    "ACTIVE_RISK": 3 * len(book.MONTH_ENDS),
    "SCENARIO": 3 * len(book.MONTH_ENDS),
    "CONCENTRATION": 3 * len(book.MONTH_ENDS),
    "LIQUIDITY": 3 * len(book.MONTH_ENDS),
    "PORTFOLIO_RETURN": 3,
    "BENCHMARK_RELATIVE": 3,
    "ROLLING_RISK": 3,
    "SHARPE": 3,
    "SENSITIVITY": 1,
}


@pytest.fixture(scope="module")
def seeded():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    summary: SeedSummary | None = None
    try:
        try:
            summary = seed_demo_tenant(session)
            session.commit()
        except DemoTenantAlreadySeededError:
            session.rollback()  # a dirty double-run of this suite: assert the existing end state
    finally:
        session.close()
    yield factory, summary


def _session(factory):  # noqa: ANN001, ANN202
    session = factory()
    persistent_tenant_context(session, TENANT_ID)
    return session


def _fund_ids(session) -> dict[str, str]:  # noqa: ANN001
    rows = session.execute(
        select(Portfolio.code, Portfolio.id).where(
            Portfolio.tenant_id == TENANT_ID, Portfolio.node_type == "FUND"
        )
    ).all()
    return {code: str(pid) for code, pid in rows}


def _latest_run(session, portfolio_id: str, run_type: str) -> CalculationRun:  # noqa: ANN001
    return session.execute(
        select(CalculationRun)
        .where(
            CalculationRun.tenant_id == TENANT_ID,
            CalculationRun.scope_portfolio_id == portfolio_id,
            CalculationRun.run_type == run_type,
            CalculationRun.status == "COMPLETED",
        )
        .order_by(CalculationRun.created_at.desc())
        .limit(1)
    ).scalar_one()


# --- admission, principals, hierarchy -------------------------------------------------------------


def test_the_tenant_is_admitted_through_the_REAL_gate(seeded) -> None:  # noqa: ANN001
    """The 2026-08-25 lesson: a demo seeded through the documented entry point 401'd on every
    request because admission was a side effect of an unrelated stage. The gate is a no-op off
    PostgreSQL, so this is the only tier that can say it."""
    factory, _ = seeded
    with factory() as session:
        assert_tenant_admitted(session, TENANT_ID)
        with pytest.raises(TenantNotAdmitted):
            assert_tenant_admitted(session, str(uuid.uuid4()))


def test_five_principals_exist_and_the_cro_can_read(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        subjects = set(
            session.execute(
                select(AppUser.external_subject).where(AppUser.tenant_id == TENANT_ID)
            ).scalars()
        )
    assert subjects == {
        "northlight-cro",
        "northlight-pm",
        "northlight-rm",
        "northlight-analyst",
        "northlight-auditor",
    }


def test_three_funds_declare_their_base_and_the_tree_has_eleven_accounts(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        rows = session.execute(
            select(Portfolio.code, Portfolio.node_type, Portfolio.base_currency_code).where(
                Portfolio.tenant_id == TENANT_ID
            )
        ).all()
    funds = {code: base for code, kind, base in rows if kind == "FUND"}
    assert funds == {"NL-GMA": "USD", "NL-EFI": "EUR", "NL-PMF": "USD"}
    assert sum(1 for _, kind, _ in rows if kind == "ACCOUNT") == 11
    assert sum(1 for _, kind, _ in rows if kind == "STRATEGY") == 8


# --- the book -------------------------------------------------------------------------------------


def test_the_book_is_a_fund_with_every_mark_and_fx_leg_on_every_boundary(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        n_inst = session.execute(
            select(func.count()).select_from(Instrument).where(Instrument.tenant_id == TENANT_ID)
        ).scalar_one()
        assert n_inst == len(book.INSTRUMENTS)
        assert 50 <= n_inst <= 80
        no_issuer = session.execute(
            select(func.count())
            .select_from(Instrument)
            .where(Instrument.tenant_id == TENANT_ID, Instrument.issuer_id.is_(None))
        ).scalar_one()
        assert no_issuer == 0
        marks_per_date = dict(
            session.execute(
                select(Valuation.valuation_date, func.count())
                .where(Valuation.tenant_id == TENANT_ID)
                .group_by(Valuation.valuation_date)
            ).all()
        )
        assert set(marks_per_date) == set(book.BOUNDARIES)
        assert all(n == len(book.INSTRUMENTS) for n in marks_per_date.values())
        fx_per_date = dict(
            session.execute(
                select(FxRate.rate_date, func.count())
                .where(FxRate.tenant_id == TENANT_ID)
                .group_by(FxRate.rate_date)
            ).all()
        )
        assert set(fx_per_date) == set(book.BOUNDARIES)
        assert all(n == len(book.FX_START) for n in fx_per_date.values())


# --- the runs -------------------------------------------------------------------------------------


def test_every_public_family_ran_the_committed_count_and_nothing_FAILED(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        rows = session.execute(
            select(CalculationRun.run_type, CalculationRun.status, func.count())
            .where(CalculationRun.tenant_id == TENANT_ID)
            .group_by(CalculationRun.run_type, CalculationRun.status)
        ).all()
    by_type: dict[str, int] = {}
    for run_type, status, n in rows:
        assert status == "COMPLETED", (run_type, status, n)
        by_type[run_type] = n
    assert by_type == EXPECTED_RUNS


def test_the_year_end_reads_return_a_row_per_fund(seeded) -> None:  # noqa: ANN001
    """What CRO-1's headline row will call: VaR, ES and historical VaR, tracking error,
    concentration and liquidity, each resolving for each fund at the marked year's end."""
    factory, _ = seeded
    with _session(factory) as session:
        for code, pid in _fund_ids(session).items():
            var_run = _latest_run(session, pid, "VAR")
            metrics = {
                m
                for (m,) in session.execute(
                    select(VarResult.metric_type).where(
                        VarResult.tenant_id == TENANT_ID,
                        VarResult.calculation_run_id.in_(
                            select(CalculationRun.run_id).where(
                                CalculationRun.tenant_id == TENANT_ID,
                                CalculationRun.scope_portfolio_id == pid,
                                CalculationRun.run_type == "VAR",
                            )
                        ),
                        VarResult.window_end == YEAR_END,
                    )
                )
            }
            assert metrics == {"VAR_PARAMETRIC", "ES_PARAMETRIC", "VAR_HISTORICAL"}, code
            assert var_run.status == "COMPLETED"
            te = session.execute(
                select(ActiveRiskResult.te_value).where(
                    ActiveRiskResult.calculation_run_id
                    == _latest_run(session, pid, "ACTIVE_RISK").run_id
                )
            ).scalar_one()
            assert te is not None and te >= 0, code
            con = session.execute(
                select(func.count())
                .select_from(ConcentrationResult)
                .where(
                    ConcentrationResult.calculation_run_id
                    == _latest_run(session, pid, "CONCENTRATION").run_id
                )
            ).scalar_one()
            assert con > 0, code
            lq = session.execute(
                select(func.count())
                .select_from(LiquidityResult)
                .where(
                    LiquidityResult.calculation_run_id
                    == _latest_run(session, pid, "LIQUIDITY").run_id
                )
            ).scalar_one()
            assert lq > 0, code


def test_the_twelve_month_rolling_window_has_a_VALUE_for_every_fund(seeded) -> None:  # noqa: ANN001
    """The remit's BLOCKING finding: a year with twelve month-ends yields a SUPPRESSED row with a
    NULL value for the twelve-month window. Thirteen month-ends, and every fund has a number."""
    factory, _ = seeded
    with _session(factory) as session:
        rows = session.execute(
            select(RollingRiskResult.window_months, RollingRiskResult.metric_value).where(
                RollingRiskResult.tenant_id == TENANT_ID, RollingRiskResult.window_months == 12
            )
        ).all()
    assert len(rows) >= 3
    assert all(value is not None for _, value in rows)


# --- the goldens ----------------------------------------------------------------------------------


def test_golden_the_multi_asset_fund_market_value_at_year_end(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        run = _latest_run(session, _fund_ids(session)["NL-GMA"], "EXPOSURE_AGGREGATE")
        total = session.execute(
            select(func.sum(ExposureAggregate.exposure_amount)).where(
                ExposureAggregate.calculation_run_id == run.run_id,
                ExposureAggregate.exposure_type == "MARKET_VALUE",
            )
        ).scalar_one()
    assert Decimal(total) == GOLDEN_GMA_MARKET_VALUE_USD


def test_golden_the_euro_fund_largest_sector_share_at_year_end(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        run = _latest_run(session, _fund_ids(session)["NL-EFI"], "CONCENTRATION")
        bucket, share = session.execute(
            select(ConcentrationResult.bucket_code, ConcentrationResult.share_invested_long)
            .where(
                ConcentrationResult.calculation_run_id == run.run_id,
                ConcentrationResult.dimension_kind == "SECTOR_INDUSTRY",
                ConcentrationResult.row_kind == "DETAIL",
            )
            .order_by(ConcentrationResult.share_invested_long.desc())
            .limit(1)
        ).one()
    assert (bucket, Decimal(share)) == GOLDEN_EFI_LARGEST_SECTOR


def test_golden_the_euro_fund_parametric_var_at_year_end(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with _session(factory) as session:
        pid = _fund_ids(session)["NL-EFI"]
        value = session.execute(
            select(VarResult.var_value).where(
                VarResult.tenant_id == TENANT_ID,
                VarResult.metric_type == "VAR_PARAMETRIC",
                VarResult.window_end == YEAR_END,
                VarResult.calculation_run_id.in_(
                    select(CalculationRun.run_id).where(
                        CalculationRun.scope_portfolio_id == pid, CalculationRun.run_type == "VAR"
                    )
                ),
            )
        ).scalar_one()
    assert Decimal(value) == GOLDEN_EFI_VAR_PARAMETRIC_EUR


# --- refuse-not-skip ------------------------------------------------------------------------------


def test_a_second_seed_REFUSES_and_writes_nothing(seeded) -> None:  # noqa: ANN001
    factory, _ = seeded
    with factory() as session:
        before = session.execute(
            select(func.count())
            .select_from(CalculationRun)
            .where(CalculationRun.tenant_id == TENANT_ID)
        ).scalar_one()
        with pytest.raises(DemoTenantAlreadySeededError):
            seed_demo_tenant(session)
        session.rollback()
        after = session.execute(
            select(func.count())
            .select_from(CalculationRun)
            .where(CalculationRun.tenant_id == TENANT_ID)
        ).scalar_one()
    assert before == after > 0
