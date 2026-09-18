"""BOOK-1a — the Northlight seed on a FRESH in-memory database (the causality half).

The PostgreSQL suite proves the end state under RLS and through the real admission gate; it
tolerates an already-seeded tenant, so a row it finds could have been written by anything (the
M-DEMO-1 lesson). This file seeds a database that did not exist a moment ago, so every row it
finds was written by the code under test. It is also the mutation battery's unit-tier host for the
seed: RLS is a no-op here, the whole seed takes about half a minute, and no shared database can
mask a mutant behind a leftover row.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun
from irp_shared.classification.models import SCHEME_FAMILY_ISIC, ClassificationScheme
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.demo_tenant import (
    TENANT_CODE,
    TENANT_ID,
    DemoTenantAlreadySeededError,
    SeedSummary,
    book,
    seed_demo_tenant,
)
from irp_shared.demo_tenant.seed import DemoTenantError
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.models import Base
from irp_shared.risk.models import VarResult
from irp_shared.tenancy.models import TENANT_STATUS_ACTIVE, Tenant
from irp_shared.valuation.models import Valuation

_FUNDS = len(book.FUNDS)
_ME = len(book.MONTH_ENDS)
_SCENARIO_FUNDS = sum(1 for f in book.FUNDS if f.scenario_account is not None)
EXPECTED_RUNS: dict[str, int] = {
    # return accounts at every boundary; fund roots and scenario accounts at month-ends
    "exposure": _FUNDS * len(book.BOUNDARIES) + _FUNDS * _ME + _SCENARIO_FUNDS * _ME,
    # per fund per month-end: allocation and loadings at the root; allocation at the scenario
    # account
    "factor_exposure": _FUNDS * _ME * 2 + _SCENARIO_FUNDS * _ME,
    "covariance": 2 * _ME,
    "var.parametric": _FUNDS * _ME,
    "var.es": _FUNDS * _ME,
    "var.historical": _FUNDS * _ME,
    "active_risk": _FUNDS * _ME,
    "scenario": _SCENARIO_FUNDS * _ME,
    "concentration": 3 * len(book.MONTH_ENDS),
    "liquidity": 3 * len(book.MONTH_ENDS),
    "portfolio_return": 3,
    "benchmark_relative": 3,
    "rolling_risk": 3,
    "sharpe": 3,
    "sensitivity": 1,
}


def _fresh_session() -> tuple[Session, object]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    assert session.execute(select(func.count()).select_from(Tenant)).scalar_one() == 0
    return session, engine


@pytest.fixture(scope="module")
def seeded() -> Iterator[tuple[Session, SeedSummary]]:
    session, engine = _fresh_session()
    try:
        summary = seed_demo_tenant(session)
        session.commit()
        yield session, summary
    finally:
        session.close()
        engine.dispose()  # type: ignore[attr-defined]


def _june_var(session: Session, fund_id: str) -> Decimal:
    return Decimal(
        session.execute(
            select(VarResult.var_value).where(
                VarResult.metric_type == "VAR_PARAMETRIC",
                VarResult.window_end == book.YEAR_END,
                VarResult.calculation_run_id.in_(
                    select(CalculationRun.run_id).where(
                        CalculationRun.scope_portfolio_id == fund_id,
                        CalculationRun.run_type == "VAR",
                    )
                ),
            )
        ).scalar_one()
    )


def test_the_seed_admits_its_tenant_at_birth(seeded: tuple[Session, SeedSummary]) -> None:
    """A fresh database held no tenant a moment ago; the row it holds now is the seed's."""
    session, _ = seeded
    row = session.get(Tenant, TENANT_ID)
    assert row is not None
    assert row.code == TENANT_CODE and row.status == TENANT_STATUS_ACTIVE


def test_every_family_ran_the_committed_count_and_every_run_completed(
    seeded: tuple[Session, SeedSummary],
) -> None:
    session, summary = seeded
    assert summary.runs == EXPECTED_RUNS
    statuses = dict(
        session.execute(
            select(CalculationRun.status, func.count())
            .where(CalculationRun.tenant_id == TENANT_ID)
            .group_by(CalculationRun.status)
        ).all()
    )
    assert statuses == {"COMPLETED": sum(EXPECTED_RUNS.values())}


def test_every_boundary_carries_a_mark_for_every_instrument(
    seeded: tuple[Session, SeedSummary],
) -> None:
    session, summary = seeded
    assert summary.marks == len(book.BOUNDARIES) * len(book.INSTRUMENTS)
    per_date = dict(
        session.execute(
            select(Valuation.valuation_date, func.count())
            .where(Valuation.tenant_id == TENANT_ID)
            .group_by(Valuation.valuation_date)
        ).all()
    )
    assert set(per_date) == set(book.BOUNDARIES)
    assert set(per_date.values()) == {len(book.INSTRUMENTS)}


def test_the_book_totals_are_a_managers_not_a_fixtures(
    seeded: tuple[Session, SeedSummary],
) -> None:
    """The realism rule's names-counts-totals clause: each fund is tens of millions in base."""
    session, summary = seeded
    for code, pid in summary.fund_ids.items():
        latest = session.execute(
            select(CalculationRun.run_id)
            .where(
                CalculationRun.scope_portfolio_id == pid,
                CalculationRun.run_type == "EXPOSURE_AGGREGATE",
            )
            .order_by(CalculationRun.created_at.desc())
            .limit(1)
        ).scalar_one()
        total = session.execute(
            select(func.sum(ExposureAggregate.exposure_amount)).where(
                ExposureAggregate.calculation_run_id == latest,
                ExposureAggregate.exposure_type == "MARKET_VALUE",
            )
        ).scalar_one()
        assert 20_000_000 < float(total) < 500_000_000, (code, total)


def test_five_principals_can_sign_in(seeded: tuple[Session, SeedSummary]) -> None:
    session, summary = seeded
    n = session.execute(
        select(func.count()).select_from(AppUser).where(AppUser.tenant_id == TENANT_ID)
    ).scalar_one()
    assert n == 5 == len(summary.principal_ids)


def test_a_second_seed_REFUSES_and_writes_nothing(seeded: tuple[Session, SeedSummary]) -> None:
    session, _ = seeded
    before = session.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    with pytest.raises(DemoTenantAlreadySeededError):
        seed_demo_tenant(session)
    session.rollback()
    after = session.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    assert before == after > 0


def test_the_factor_model_SEES_an_equity_move(
    seeded: tuple[Session, SeedSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remit outcome 4's proof. The base campaign's own comment names the defect a currency-only
    model has: "an equity move the CURRENCY factor model cannot see". Here one equity's MARKET
    loading is changed and the whole book re-seeded on a scratch database; the multi-asset fund's
    June VaR must move, and the euro fund's, which holds no equity, must not."""
    session, summary = seeded
    baseline_gma = _june_var(session, summary.fund_ids["NL-GMA"])
    baseline_efi = _june_var(session, summary.fund_ids["NL-EFI"])
    assert baseline_gma > 0

    changed = tuple(
        dataclasses.replace(i, market_beta=i.market_beta * Decimal("2")) if i.code == "CSDA" else i
        for i in book.INSTRUMENTS
    )
    monkeypatch.setattr(book, "INSTRUMENTS", changed)
    scratch, engine = _fresh_session()
    try:
        alt = seed_demo_tenant(scratch)
        scratch.commit()
        assert _june_var(scratch, alt.fund_ids["NL-GMA"]) != baseline_gma
        assert _june_var(scratch, alt.fund_ids["NL-EFI"]) == baseline_efi
    finally:
        scratch.close()
        engine.dispose()  # type: ignore[attr-defined]


def test_the_SYSTEM_schemes_are_created_exactly_once(seeded: tuple[Session, SeedSummary]) -> None:
    """Remit outcome 6: on a fresh database the create arm runs, and it runs once."""
    session, _ = seeded
    n = session.execute(
        select(func.count())
        .select_from(ClassificationScheme)
        .where(
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            ClassificationScheme.scheme_family == SCHEME_FAMILY_ISIC,
            # The version THIS seed resolves-or-creates; other suites seed other version labels.
            ClassificationScheme.version_label == "Rev. 5",
        )
    ).scalar_one()
    assert n == 1


def test_a_missing_mark_STOPS_the_seed_at_that_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact-date pin (remit Part 5): one instrument unmarked on one boundary. The snapshot's
    completeness rule refuses the build (a DataQualityError, severity ERROR) before any exposure
    row is written, and the seed stops there with the boundaries before it done and nothing after:
    a book with a hole in it is never shipped as a book."""
    from irp_shared.demo_tenant import seed as seed_module
    from irp_shared.dq.service import DataQualityError

    real = seed_module.create_valuation
    skipped = {"n": 0}
    hole = book.MONTH_ENDS[3]

    def _skip_one(session, **kwargs):  # noqa: ANN001, ANN202
        if kwargs.get("valuation_date") == hole and skipped["n"] == 0:
            skipped["n"] = 1
            return None
        return real(session, **kwargs)

    monkeypatch.setattr(seed_module, "create_valuation", _skip_one)
    scratch, engine = _fresh_session()
    try:
        with pytest.raises((DemoTenantError, DataQualityError)):
            seed_demo_tenant(scratch)
        assert skipped["n"] == 1
        completed = scratch.execute(
            select(func.count())
            .select_from(CalculationRun)
            .where(CalculationRun.status == "COMPLETED", CalculationRun.tenant_id == TENANT_ID)
        ).scalar_one()
        assert 0 < completed < sum(EXPECTED_RUNS.values())
    finally:
        scratch.rollback()
        scratch.close()
        engine.dispose()  # type: ignore[attr-defined]
