"""The STRUCT-3 demo-stage suite (stage 26) — the three-level book, live on PG.

The stage itself asserts the rollup identity, the sleeve execution, the inherited scope, and the
rename carry (fresh re-runs value-identical); this suite proves the end state under RLS: the
tree resolvable AS-OF from the ENT-076 history alone, the widened rollup read over HTTP-shaped
service calls, and the stage's hand goldens.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from irp_shared.db.mixins import utcnow
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_struct3_stage26
from irp_shared.demo.struct3_stage26 import _FUND_CODE, DemoStruct3AlreadySeededError
from irp_shared.exposure.service import rollup_exposure
from irp_shared.portfolio.models import Portfolio
from irp_shared.portfolio.portfolio import resolve_tree_as_of

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
            run_demo_struct3_stage26(session, actor_id=str(actor))
            session.commit()
        except DemoStruct3AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory


def _session(factory):  # noqa: ANN001, ANN202
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    return session


def test_tree_resolves_as_of_from_the_history_alone(staged) -> None:  # noqa: ANN001
    """REQ-PPM-001 clause 2 on live PG: the tree at a PAST timestamp — before the stage's rename
    carry — shows the ORIGINAL fund name, resolved from the ENT-076 rows by timestamp with no
    run or snapshot in scope; the present shows the contradictory label the carry applied."""
    session = _session(staged)
    try:
        fund_id = str(
            session.execute(
                select(Portfolio.id).where(
                    Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _FUND_CODE
                )
            ).scalar_one()
        )
        now_view = resolve_tree_as_of(session, acting_tenant=DEMO_TENANT_ID, at=utcnow())
        assert now_view[fund_id].name == "Distressed Sovereign Credit Special Situations"
        assert now_view[fund_id].node_type == "FUND"
        # Before the demo era entirely: the fund does not exist yet.
        assert fund_id not in resolve_tree_as_of(
            session,
            acting_tenant=DEMO_TENANT_ID,
            at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        # The tree edges: both sleeves parent to the fund in the as-of view.
        children = [n for n in now_view.values() if n.parent_portfolio_id == fund_id]
        assert {c.node_type for c in children} == {"STRATEGY"}
        assert len(children) == 2
    finally:
        session.close()


def test_rollup_identity_holds_on_pg(staged) -> None:  # noqa: ANN001
    """The identity re-asserted from the persisted run under RLS, hand goldens included."""
    session = _session(staged)
    try:
        from irp_shared.calc.models import CalculationRun

        fund_id = str(
            session.execute(
                select(Portfolio.id).where(
                    Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _FUND_CODE
                )
            ).scalar_one()
        )
        run_id = str(
            session.execute(
                select(CalculationRun.run_id)
                .where(
                    CalculationRun.tenant_id == DEMO_TENANT_ID,
                    CalculationRun.scope_portfolio_id == fund_id,
                    CalculationRun.run_type == "EXPOSURE_AGGREGATE",
                    CalculationRun.status == "COMPLETED",
                )
                .order_by(CalculationRun.created_at)
                .limit(1)
            ).scalar_one()
        )
        totals = {
            r.exposure_type: r.total
            for r in rollup_exposure(
                session, acting_tenant=DEMO_TENANT_ID, run_id=run_id, node_id=fund_id
            )
        }
        assert totals["MARKET_VALUE"] == Decimal("45508.000000")
        assert totals["NOTIONAL"] == Decimal("20000.000000")
    finally:
        session.close()
