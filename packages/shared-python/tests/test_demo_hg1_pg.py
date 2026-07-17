"""PostgreSQL end-state test for the HG-1 stage-3 demo (OD-HG-1-D).

Gated on ``IRP_TEST_DATABASE_URL``. Seeds the campaign + the MF-1 extension when absent, then runs
stage 3 ONCE (module-scoped, owner-engine — the campaign suite's recorded pattern). **CI ORDERING
IS LOAD-BEARING**: this suite runs AFTER `test_demo_multifamily_pg.py` and BEFORE the downgrade
smoke; the campaign suite keeps its recorded fresh-schema-only status and runs first.

KNOWN EDGE (inherited from the campaign/MF-1 suites): a STANDALONE fresh-schema run of this suite
followed by ``alembic downgrade base`` would hit the 0002 role_permission FK violation — the
role_permission teardown lives in the campaign suite, which runs first in every documented
sequence (CI and the local battery).

The end state asserted: the genuinely-private α=0.4 chain ran on multi-family factors — the new
private-credit instrument in the sleeve with ONLY non-CURRENCY REGRESSION heads (the mixed-family
fence holds for the legacy tuple), 10 COMPLETED `demo-hg1` runs, the OLS recovery within the
ratified |β̂−β| ≤ 0.05 of the declared structure, the promote audit carrying `promotion_age_days`,
and refuse-not-skip on a second invocation.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.audit.models import AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoCampaignAlreadySeededError,
    DemoHg1AlreadySeededError,
    DemoMultifamilyAlreadySeededError,
    run_demo_campaign,
    run_demo_hg1_private,
    run_demo_multifamily_extension,
)
from irp_shared.demo.hg1_private import _INSTRUMENT_CODE, _STRUCTURE
from irp_shared.marketdata.models import Factor, ProxyMapping
from irp_shared.reference.models import Instrument

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_LEGACY_INSTRUMENT_CODES = ("EQ-ACME-US", "EQ-EURX-DE", "PE-HARBOR-IV")


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


def _instrument_id(db: Session, code: str) -> str:
    return str(
        db.execute(
            select(Instrument.id).where(
                Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == code
            )
        ).scalar_one()
    )


def test_second_stage3_refuses_not_skips(db: Session) -> None:
    with pytest.raises(DemoHg1AlreadySeededError):
        run_demo_hg1_private(db)
    db.rollback()


def test_the_stage3_chain_completed(db: Session) -> None:
    """10 COMPLETED demo-hg1 runs: desmooth(1) + estimate(1) + exposure(1) + loadings
    factor-exposure(1) + covariance(1) + the five flagship VAR-family runs(5)."""
    runs = (
        db.execute(
            select(CalculationRun).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.code_version == "demo-hg1",
            )
        )
        .scalars()
        .all()
    )
    by_type: dict[str, int] = {}
    for r in runs:
        assert r.status == RunStatus.COMPLETED.value, (r.run_type, r.failure_reason)
        by_type[r.run_type] = by_type.get(r.run_type, 0) + 1
    assert by_type == {
        "DESMOOTHED_RETURN": 1,
        "PROXY_WEIGHT_ESTIMATE": 1,
        "EXPOSURE_AGGREGATE": 1,
        "FACTOR_EXPOSURE": 1,
        "COVARIANCE": 1,
        "VAR": 5,
    }


def test_the_recovery_and_the_fence(db: Session) -> None:
    """The promoted heads recover the declared structure within the ratified tolerance; the new
    instrument carries ONLY non-CURRENCY REGRESSION heads; the legacy fence holds."""
    families = {
        str(f.id).lower(): (f.factor_code, f.factor_family)
        for f in db.execute(select(Factor).where(Factor.tenant_id == DEMO_TENANT_ID))
        .scalars()
        .all()
    }
    inst = _instrument_id(db, _INSTRUMENT_CODE)
    heads = (
        db.execute(
            select(ProxyMapping).where(
                ProxyMapping.tenant_id == DEMO_TENANT_ID,
                ProxyMapping.private_instrument_id == inst,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert len(heads) == len(_STRUCTURE) == 2
    for row in heads:
        code, family = families[str(row.factor_id).lower()]
        assert family != "CURRENCY"
        assert row.mapping_method == "REGRESSION"
        structural = Decimal(_STRUCTURE[code])
        assert abs(Decimal(row.weight) - structural) <= Decimal("0.05"), (code, row.weight)

    for code in _LEGACY_INSTRUMENT_CODES:
        legacy = _instrument_id(db, code)
        legacy_heads = (
            db.execute(
                select(ProxyMapping).where(
                    ProxyMapping.tenant_id == DEMO_TENANT_ID,
                    ProxyMapping.private_instrument_id == legacy,
                    ProxyMapping.valid_to.is_(None),
                    ProxyMapping.system_to.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert all(
            families[str(r.factor_id).lower()][1] == "CURRENCY" for r in legacy_heads
        ), f"legacy instrument {code} gained a non-CURRENCY head — the fence is broken"


def test_the_promote_audit_carries_the_age(db: Session) -> None:
    """The stage-3 promotes are ungated but MEASURED: every promoted head's CREATE audit event
    carries promotion_age_days (span end 2026-03-31 vs the seed-day — a positive, growing int)."""
    inst = _instrument_id(db, _INSTRUMENT_CODE)
    head_ids = [
        str(r.id)
        for r in db.execute(
            select(ProxyMapping).where(
                ProxyMapping.tenant_id == DEMO_TENANT_ID,
                ProxyMapping.private_instrument_id == inst,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    ]
    assert head_ids
    for hid in head_ids:
        event = (
            db.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_id == hid, AuditEvent.action == "create")
                .order_by(AuditEvent.event_time.desc())
            )
            .scalars()
            .first()
        )
        assert event is not None
        age = event.after_value.get("promotion_age_days")
        assert isinstance(age, int) and age > 0  # span end 2026-03-31; seeded later — real age
