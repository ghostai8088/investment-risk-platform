"""CC-1 stage-8 PG tier: the seeded end state — the commitment lifecycle LIVE (the negation
reversal Σ self-correction; the recallable flag as data; the provenance version echo), and
the CAPTURE-ONLY honesty: the campaign count pins (19 codes / 34 validation records / 95
COMPLETED runs) DID NOT MOVE, and the perf/backtest evidence chains are row-count-unchanged
(the OD-CC-1-D read rule mechanically visible). Runs AFTER the stage-7 step and BEFORE the
downgrade smoke in CI (the smoke then exercises 0044's destructive downgrade against THIS
stage's captured rows every run)."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DemoCc1AlreadySeededError,
    run_demo_bt3_stage7,
    run_demo_campaign,
    run_demo_cc1_stage8,
    run_demo_ds2_stage6,
    run_demo_eshs_stage4,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
    run_demo_rs1_stage5,
)
from irp_shared.demo.bt3_stage7 import DemoBt3AlreadySeededError
from irp_shared.demo.campaign import DEMO_TENANT_ID, DemoCampaignAlreadySeededError
from irp_shared.demo.ds2_stage6 import DemoDs2AlreadySeededError
from irp_shared.demo.eshs_stage4 import DemoEshsAlreadySeededError
from irp_shared.demo.hg1_private import DemoHg1AlreadySeededError
from irp_shared.demo.multifamily import DemoMultifamilyAlreadySeededError
from irp_shared.demo.rs1_stage5 import DemoRs1AlreadySeededError
from irp_shared.model.models import Model, ModelValidation
from irp_shared.private_capital.models import CapitalCall, Commitment, Distribution

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def factory():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    session_factory = make_session_factory(engine)
    session = session_factory()
    try:
        for runner, refusal in (
            (run_demo_campaign, DemoCampaignAlreadySeededError),
            (run_demo_multifamily_extension, DemoMultifamilyAlreadySeededError),
            (run_demo_hg1_private, DemoHg1AlreadySeededError),
            (run_demo_eshs_stage4, DemoEshsAlreadySeededError),
            (run_demo_rs1_stage5, DemoRs1AlreadySeededError),
            (run_demo_ds2_stage6, DemoDs2AlreadySeededError),
            (run_demo_bt3_stage7, DemoBt3AlreadySeededError),
            (run_demo_cc1_stage8, DemoCc1AlreadySeededError),
        ):
            try:
                runner(session)
                session.commit()
            except refusal:
                session.rollback()
    finally:
        session.close()
    yield session_factory
    engine.dispose()


@pytest.fixture()
def db(factory) -> Session:  # noqa: ANN001
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    yield session
    session.close()


def test_second_stage8_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoCc1AlreadySeededError):
        run_demo_cc1_stage8(db)
    db.rollback()


def test_capture_only_counts_did_not_move(db: Session) -> None:
    """The stage-8 honesty pins: NO model code, NO validation record, NO calculation run
    was added by the capture walk — the BT-3 end-state counts hold verbatim."""
    codes = db.execute(
        select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert codes == 19
    records = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert records == 34
    runs = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()
    assert runs == 95


def test_commitment_lifecycle_end_state(db: Session) -> None:
    commitment = db.execute(
        select(Commitment).where(Commitment.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    assert commitment.committed_amount == Decimal("25000000.000000")
    assert commitment.currency_code == "USD" and commitment.record_version == 1
    calls = (
        db.execute(select(CapitalCall).where(CapitalCall.tenant_id == DEMO_TENANT_ID))
        .scalars()
        .all()
    )
    assert len(calls) == 5  # 4 captures + 1 reversal
    reversals = [c for c in calls if c.reverses_id is not None]
    assert len(reversals) == 1 and reversals[0].amount == Decimal("-9000000.000000")
    assert sum(c.amount for c in calls) == Decimal("10000000.000000")  # Σ self-corrects
    # Every event carries the provenance echo of the commitment version current at capture.
    assert {c.commitment_version_id for c in calls} == {commitment.id}
    dists = (
        db.execute(select(Distribution).where(Distribution.tenant_id == DEMO_TENANT_ID))
        .scalars()
        .all()
    )
    assert len(dists) == 2
    assert sum(d.amount for d in dists) == Decimal("1800000.000000")
    assert sum(1 for d in dists if d.is_recallable) == 1


def test_audit_events_present(db: Session) -> None:
    from sqlalchemy import text

    counts = {
        row[0]: row[1]
        for row in db.execute(
            text(
                "SELECT event_type, count(*) FROM audit_event "
                "WHERE event_type LIKE 'PRIVATE.%' "
                "AND tenant_id::text = :t GROUP BY event_type"
            ),
            {"t": DEMO_TENANT_ID},
        )
    }
    assert counts.get("PRIVATE.COMMITMENT_CREATE") == 1
    assert counts.get("PRIVATE.CAPITAL_CALL_CREATE") == 4
    assert counts.get("PRIVATE.CAPITAL_CALL_REVERSE") == 1
    assert counts.get("PRIVATE.DISTRIBUTION_CREATE") == 2
