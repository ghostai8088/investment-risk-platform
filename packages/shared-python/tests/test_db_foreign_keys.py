"""FK-1 — foreign keys are TRUE on the unit tier, and the enforcement itself is pinned.

For the platform's whole life before this slice, SQLite's ``PRAGMA foreign_keys`` default of OFF
meant the unit tier silently accepted an INSERT naming a parent that does not exist, while
PostgreSQL refused it. The cost was measured twice, not argued: RPT-1 generated reports against a
``portfolio_id`` resolving to NOTHING through eighteen green tests (found only by the deployed
restore proof), and the FK-1 census found **151 tests across 14 suites** writing dangling foreign
keys, all green — every suite sharing the assumption that the parent existed (P15 at engine scale).

Enforcement now lives in ``make_engine`` itself, dialect-guarded, so it is the DEFAULT for every
SQLite engine rather than a per-suite opt-in. These tests are the pin: the negative control proves
the refusal FIRES (P9), the positive control proves the test can tell a refusal from a fixture
error, and the census-style check keeps the property attached to the FACTORY rather than to
whichever suite happens to exercise it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.model.models import Model, ModelVersion
from irp_shared.risk.models import VarResult
from irp_shared.snapshot.models import PURPOSE_VAR_INPUT, DatasetSnapshot


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _genuine_parents(db: Session, tenant: str) -> tuple[str, str, str, str, str]:
    """Seed the FULL parent chain a governed VaR row binds: THREE runs, a snapshot, a model version.

    All three, because ``var_result`` carries three NOT NULL foreign keys, and the two controls
    below must differ by EXACTLY ONE thing — whether the run exists. Seeding less would let the
    negative control pass on a NOT NULL violation (also an ``IntegrityError``), which is a refusal
    test passing for the wrong reason: the shape this suite exists to forbid.
    """

    def _run(run_type: str) -> CalculationRun:
        return CalculationRun(
            run_id=str(uuid.uuid4()),
            tenant_id=tenant,
            run_type=run_type,
            status="COMPLETED",
            initiated_by="fk-1-control",
            code_version="risk-v1",
            environment_id="test",
        )

    run = _run("VAR")
    exposure_run = _run("EXPOSURE_AGGREGATE")
    covariance_run = _run("COVARIANCE")
    snap = DatasetSnapshot(
        tenant_id=tenant,
        label="fk1-risk-src",
        purpose=PURPOSE_VAR_INPUT,
        as_of_valid_at=datetime(2026, 6, 30, tzinfo=UTC),
        as_of_known_at=datetime(2026, 6, 30, tzinfo=UTC),
        as_of_valuation_date=date(2026, 6, 30),
        binding_predicate_version="v1:test",
        component_count=0,
        manifest_hash="0" * 64,
    )
    model = Model(
        tenant_id=tenant,
        code="risk.var_parametric",
        name="Parametric VaR (FK-1 control seed)",
        model_type="VAR_PARAMETRIC",
        is_active=True,
    )
    db.add_all([run, exposure_run, covariance_run, snap, model])
    db.flush()
    mv = ModelVersion(
        tenant_id=tenant,
        model_id=str(model.id),
        version_label="v1",
        status="REGISTERED",
    )
    db.add(mv)
    db.flush()
    return (
        str(run.run_id),
        str(snap.id),
        str(mv.id),
        str(exposure_run.run_id),
        str(covariance_run.run_id),
    )


def _var_row(
    tenant: str, run_id: str, snapshot_id: str, mv_id: str, exposure_run: str, covariance_run: str
) -> VarResult:
    """A plausible governed result row — the child side of the FIVE FKs under test."""
    return VarResult(
        tenant_id=tenant,
        calculation_run_id=run_id,
        input_snapshot_id=snapshot_id,
        model_version_id=mv_id,
        exposure_run_id=exposure_run,
        covariance_run_id=covariance_run,
        metric_type="TOTAL",
        sigma="0.0123",
        var_value="184000.00",
        confidence_level="0.99",
        horizon_days=1,
        base_currency="USD",
        n_factors=6,
        n_observations=36,
        window_start=date(2023, 7, 31),
        window_end=date(2026, 6, 30),
        z_score="2.326",
    )


def test_a_child_naming_a_nonexistent_parent_is_REFUSED(session: Session) -> None:
    """The negative control, made to FIRE (P9) — and made to fire for the RIGHT reason.

    Every parent is genuine EXCEPT the run: snapshot and model version are seeded for real, so the
    only defect in this row is a ``calculation_run_id`` resolving to nothing. That single-difference
    discipline exists because the first draft of this test seeded nothing at all, and it passed on
    the NOT NULL violation of a different column — an ``IntegrityError`` for the wrong reason,
    proving nothing about the foreign key. This INSERT shape is what all 151 census failures reduce
    to; if it is ever accepted again, the unit tier has gone blind exactly where it was blind for
    eighteen slices.
    """
    tenant = str(uuid.uuid4())
    _, snapshot_id, mv_id, exposure_run, covariance_run = _genuine_parents(session, tenant)
    dangling_run = str(uuid.uuid4())
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        session.add(
            _var_row(tenant, dangling_run, snapshot_id, mv_id, exposure_run, covariance_run)
        )
        session.flush()
    session.rollback()


def test_the_same_child_with_a_GENUINE_parent_is_accepted(session: Session) -> None:
    """The positive control — identical row, real run. Without it, the refusal above cannot be told
    apart from a fixture that fails for an unrelated reason."""
    tenant = str(uuid.uuid4())
    run_id, snapshot_id, mv_id, exposure_run, covariance_run = _genuine_parents(session, tenant)
    session.add(_var_row(tenant, run_id, snapshot_id, mv_id, exposure_run, covariance_run))
    session.flush()
    assert (
        session.execute(
            select(VarResult).where(VarResult.calculation_run_id == run_id)
        ).scalar_one()
        is not None
    )


def test_enforcement_is_a_property_of_the_FACTORY_not_of_a_suite(session: Session) -> None:
    """Ask the ENGINE, not a fixture: ``PRAGMA foreign_keys`` must report ON for a connection from
    ``make_engine``. This is what makes the control structural — a per-suite listener (RPT-1's
    interim shape, retired in this slice) protected only the suite that carried it, and the next
    suite was born blind. A factory property covers suites that do not exist yet."""
    from sqlalchemy import text

    assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1, (
        "an engine from make_engine left PRAGMA foreign_keys OFF — the unit tier accepts dangling "
        "foreign keys again, silently, for every suite at once"
    )
