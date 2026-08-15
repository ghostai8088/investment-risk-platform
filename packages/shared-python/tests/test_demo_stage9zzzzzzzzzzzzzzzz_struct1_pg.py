"""The STRUCT-1 demo-stage suite (stage 25) — the demonstrating bond, live on PG.

REQ-PPM-006's demonstrating case executed against the real database: one bond holding in its own
DEMO-FI book (never DEMO-GLOBAL — every downstream golden is hand-derived over that book), whose
ONE governed run yields BOTH measures readable from ONE holding id, off par so they differ, and
whose widened uniqueness key (migration 0071) is proven by the live constraint: the two rows for
one holding coexist, and a true duplicate is refused by PostgreSQL itself.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_struct1_stage25
from irp_shared.demo.struct1_stage25 import _FI_PORTFOLIO_CODE, DemoStruct1AlreadySeededError
from irp_shared.exposure import list_exposure_by_entity
from irp_shared.exposure.models import ExposureAggregate
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
            run_demo_struct1_stage25(session, actor_id=str(actor))
            session.commit()
        except DemoStruct1AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory


def _session(factory):  # noqa: ANN001, ANN202
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    return session


def _fi_rows(session):  # noqa: ANN001, ANN202
    pf = session.execute(
        select(Portfolio.id).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _FI_PORTFOLIO_CODE
        )
    ).scalar_one()
    rows = list(
        session.execute(
            select(ExposureAggregate).where(
                ExposureAggregate.tenant_id == DEMO_TENANT_ID,
                ExposureAggregate.portfolio_id == str(pf),
            )
        )
        .scalars()
        .all()
    )
    return str(pf), rows


def test_both_measures_from_one_holding_id_hand_amounts(staged) -> None:  # noqa: ANN001
    session = _session(staged)
    try:
        pf, rows = _fi_rows(session)
        by_type = {r.exposure_type: r for r in rows}
        assert set(by_type) == {"MARKET_VALUE", "NOTIONAL"}
        holding = {(r.portfolio_id, r.instrument_id) for r in rows}
        assert len(holding) == 1  # ONE holding id carries both measures
        # Hand-derived, off par: 250 x 1,000 vs 250 x 985.40.
        assert str(by_type["NOTIONAL"].exposure_amount) == "250000.000000"
        assert str(by_type["MARKET_VALUE"].exposure_amount) == "246350.000000"
        # Both from the valuation path: run-bound + snapshot-gated.
        assert by_type["NOTIONAL"].calculation_run_id == by_type["MARKET_VALUE"].calculation_run_id
        assert by_type["NOTIONAL"].input_snapshot_id is not None
    finally:
        session.close()


def test_entity_read_returns_both_and_filters_one(staged) -> None:  # noqa: ANN001
    session = _session(staged)
    try:
        pf, rows = _fi_rows(session)
        inst = rows[0].instrument_id
        both = list_exposure_by_entity(
            session, acting_tenant=DEMO_TENANT_ID, portfolio_id=pf, instrument_id=inst
        )
        assert {r.exposure_type for r in both} == {"MARKET_VALUE", "NOTIONAL"}
        only = list_exposure_by_entity(
            session,
            acting_tenant=DEMO_TENANT_ID,
            portfolio_id=pf,
            instrument_id=inst,
            exposure_type="NOTIONAL",
        )
        assert {r.exposure_type for r in only} == {"NOTIONAL"}
    finally:
        session.close()


def test_widened_key_refuses_a_true_duplicate_on_live_pg(staged) -> None:  # noqa: ANN001
    """Migration 0071 proven by the CONSTRAINT, not the ORM: a row duplicating (run, portfolio,
    instrument, base, exposure_type) is refused by PostgreSQL, while the second MEASURE for the
    same holding (already present) was accepted — the exact pair the old key made impossible."""
    session = _session(staged)
    try:
        _, rows = _fi_rows(session)
        template = rows[0]
        dupe = ExposureAggregate(
            id=str(uuid.uuid4()),
            tenant_id=template.tenant_id,
            calculation_run_id=template.calculation_run_id,
            input_snapshot_id=template.input_snapshot_id,
            portfolio_id=template.portfolio_id,
            instrument_id=template.instrument_id,
            base_currency=template.base_currency,
            mark_currency=template.mark_currency,
            signed_quantity=template.signed_quantity,
            mark_value=template.mark_value,
            fx_rate=template.fx_rate,
            fx_legs=template.fx_legs,
            exposure_amount=template.exposure_amount,
            exposure_type=template.exposure_type,  # the TRUE duplicate
        )
        session.add(dupe)
        with pytest.raises(IntegrityError, match="uq_exposure_aggregate_run_grain"):
            session.flush()
        session.rollback()
    finally:
        session.close()
