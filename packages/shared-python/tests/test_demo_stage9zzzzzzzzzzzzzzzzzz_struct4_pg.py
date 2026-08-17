"""The STRUCT-4 demo-stage suite (stage 27) — the three-currency book, live on PG.

The stage itself asserts the DP-11 resolution (root EUR / node USD / inherited EUR), the P18
translated-leg positive control, the stated pivot, the hand oracles, and the return-chain rename
carry; this suite proves the end state under RLS: the foreign-node oracle re-read from the
STORED rows, the rollup translation evidence, and the DP-12 pivot on the persisted bytes.

Filename z-count = 18: alpha-sort runs this AFTER stage 26 (its own book moves no golden).
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_struct4_stage27
from irp_shared.demo.struct4_stage27 import (
    _FUND_CODE,
    _SLEEVE_UK_USD_ORACLE,
    DemoStruct4AlreadySeededError,
)
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.exposure.service import rollup_exposure
from irp_shared.portfolio.models import Portfolio

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def staged():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        from irp_shared.entitlement.models import AppUser

        actor = session.execute(
            select(AppUser.id).where(AppUser.tenant_id == DEMO_TENANT_ID).limit(1)
        ).scalar_one()
        try:
            run_demo_struct4_stage27(session, actor_id=str(actor))
            session.commit()
        except DemoStruct4AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory


def _session(factory):  # noqa: ANN001, ANN202
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    return session


def _node_ids(session) -> dict[str, str]:  # noqa: ANN001
    rows = session.execute(
        select(Portfolio.code, Portfolio.id).where(
            Portfolio.tenant_id == DEMO_TENANT_ID,
            Portfolio.code.in_((_FUND_CODE, "DEMO-FX-UK", "DEMO-FX-CORE")),
        )
    ).all()
    return {code: str(pid) for code, pid in rows}


def test_the_foreign_node_oracle_holds_on_stored_rows(staged) -> None:  # noqa: ANN001
    """The node-scoped run's PERSISTED rows re-total to the hand-derived literal, in the NODE's
    declared USD — read back from the database, not from the in-request result."""
    session = _session(staged)
    try:
        ids = _node_ids(session)
        rows = list(
            session.execute(
                select(ExposureAggregate).where(
                    ExposureAggregate.tenant_id == DEMO_TENANT_ID,
                    ExposureAggregate.portfolio_id == ids["DEMO-FX-UK"],
                    ExposureAggregate.base_currency == "USD",
                )
            )
            .scalars()
            .all()
        )
        assert rows, "the node-scoped run persisted no USD rows"
        by_run: dict[str, Decimal] = {}
        for r in rows:
            by_run[r.calculation_run_id] = (
                by_run.get(r.calculation_run_id, Decimal(0)) + r.exposure_amount
            )
        assert _SLEEVE_UK_USD_ORACLE in by_run.values()
    finally:
        session.close()


def test_the_stated_pivot_is_on_the_persisted_bytes(staged) -> None:  # noqa: ANN001
    """DP-12 on disk: the triangulated GBP row's stored fx_legs STATE pivot USD (two legs); the
    identity EUR row stores the empty evidence honestly."""
    session = _session(staged)
    try:
        ids = _node_ids(session)
        legs_by_ccy = {}
        for r in (
            session.execute(
                select(ExposureAggregate).where(
                    ExposureAggregate.tenant_id == DEMO_TENANT_ID,
                    ExposureAggregate.portfolio_id == ids["DEMO-FX-UK"],
                    ExposureAggregate.base_currency == "EUR",
                )
            )
            .scalars()
            .all()
        ):
            legs_by_ccy[r.mark_currency] = json.loads(r.fx_legs)
        assert len(legs_by_ccy["GBP"]) == 2
        assert [leg["pivot"] for leg in legs_by_ccy["GBP"]] == ["USD", "USD"]
        assert legs_by_ccy["EUR"] == []
    finally:
        session.close()


def test_the_rollup_translation_is_readable_under_rls(staged) -> None:  # noqa: ANN001
    """The read-time translation at the foreign node, on live PG: EUR total -> the declared USD
    with a single direct leg and no pivot; the fund's own node is an identity pass-through."""
    session = _session(staged)
    try:
        ids = _node_ids(session)
        from irp_shared.calc.models import CalculationRun

        run_id = str(
            session.execute(
                select(CalculationRun.run_id)
                .where(
                    CalculationRun.tenant_id == DEMO_TENANT_ID,
                    CalculationRun.run_type == "EXPOSURE_AGGREGATE",
                    CalculationRun.scope_portfolio_id == ids[_FUND_CODE],
                    CalculationRun.status == "COMPLETED",
                )
                .order_by(CalculationRun.created_at)
                .limit(1)
            ).scalar_one()
        )
        uk = {
            r.exposure_type: r
            for r in rollup_exposure(
                session, acting_tenant=DEMO_TENANT_ID, run_id=run_id, node_id=ids["DEMO-FX-UK"]
            )
        }["MARKET_VALUE"]
        assert (uk.base_currency, uk.reporting_currency) == ("EUR", "USD")
        assert uk.translated_total == _SLEEVE_UK_USD_ORACLE
        assert len(uk.translation_legs) == 1 and uk.translation_pivot is None
        top = {
            r.exposure_type: r
            for r in rollup_exposure(
                session, acting_tenant=DEMO_TENANT_ID, run_id=run_id, node_id=ids[_FUND_CODE]
            )
        }["MARKET_VALUE"]
        assert (top.reporting_currency, top.translated_total) == ("EUR", top.total)
    finally:
        session.close()
