"""BOOK-1a — the Northlight seed on a FRESH in-memory database (the causality half).

The PostgreSQL suite proves the end state under RLS and through the real admission gate; it
tolerates an already-seeded tenant, so a row it finds could have been written by anything (the
M-DEMO-1 lesson). This file seeds a database that did not exist a moment ago, so every row it
finds was written by the code under test. It is also the mutation battery's unit-tier host for the
seed: RLS is a no-op here, the whole seed takes about half a minute, and no shared database can
mask a mutant behind a leftover row.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.demo_tenant import (
    TENANT_CODE,
    TENANT_ID,
    DemoTenantAlreadySeededError,
    SeedSummary,
    book,
    seed_demo_tenant,
)
from irp_shared.entitlement.models import AppUser
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.models import Base
from irp_shared.tenancy.models import TENANT_STATUS_ACTIVE, Tenant
from irp_shared.valuation.models import Valuation

EXPECTED_RUNS: dict[str, int] = {
    "exposure": 3 * len(book.BOUNDARIES) + 3 * len(book.MONTH_ENDS),
    "factor_exposure": 3 * len(book.MONTH_ENDS) * 3,
    "covariance": 2 * len(book.MONTH_ENDS),
    "var.parametric": 3 * len(book.MONTH_ENDS),
    "var.es": 3 * len(book.MONTH_ENDS),
    "var.historical": 3 * len(book.MONTH_ENDS),
    "active_risk": 3 * len(book.MONTH_ENDS),
    "scenario": 3 * len(book.MONTH_ENDS),
    "concentration": 3 * len(book.MONTH_ENDS),
    "liquidity": 3 * len(book.MONTH_ENDS),
    "portfolio_return": 3,
    "benchmark_relative": 3,
    "rolling_risk": 3,
    "sharpe": 3,
    "sensitivity": 1,
}


@pytest.fixture(scope="module")
def seeded() -> Iterator[tuple[Session, SeedSummary]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    try:
        assert session.execute(select(func.count()).select_from(Tenant)).scalar_one() == 0
        summary = seed_demo_tenant(session)
        session.commit()
        yield session, summary
    finally:
        session.close()
        engine.dispose()


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
