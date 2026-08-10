"""REPRO-2 — the four RISK-side adapters, each made to say YES and then made to say NO.

Companion to ``test_reproduction_families.py``, which owns the shared pair helper and the two
construction guarantees. This module carries the four families whose subject runs are the most
expensive to build — each one is stood up through that family's OWN production binder, using that
family's OWN test-module helpers, so the subject is a real COMPLETED governed run rather than a
hand-assembled row set. The helper then does what it does everywhere: sweep green first (MATCH over
a non-zero row count), then plant one governed value with raw SQL and demand DIVERGED naming the
field.

The subject builders are deliberately borrowed rather than re-written. A fixture derived from the
subject cannot test the subject (SR-1's standing lesson), and a subject hand-built here would be
exactly that — rows shaped by what this test expects the adapter to read, instead of rows shaped by
the binder the adapter re-executes.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_reproduction_families import assert_reproduces_and_then_diverges

from irp_shared.calc.models import RunStatus
from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory

#: A plainly different value of the right type, distinct from anything any of these four families
#: computes for the column it is planted into (the loadings are 1, the DV01s are ~1e-4, the P&Ls are
#: thousands, the private covariances are ~1e-4). Chosen to round-trip exactly through SQLite's
#: NUMERIC affinity so the plant-landed read-back in the shared helper is a real check.
_TAMPERED = str(Decimal("0.123456789012"))


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


def test_COVARIANCE_PRIVATE_reproduces_and_detects_a_plant(session: Session) -> None:
    """Ω_pp — the family the registry wrongly said needed binder resolution.

    It shares ``covariance_result`` with COVARIANCE but not its run type, and the plant is scoped
    by ``calculation_run_id``, so this test touches only the private run's own rows.
    """
    from test_private_covariance_e2e import (
        _SEG_A_EUR,
        _SEG_A_USD,
        _SEG_B_EUR,
        _SEG_B_USD,
        _ppf_model,
        _priv_cov_model,
        _pure_private_segment,
    )

    from irp_shared.risk.events import PurePrivateCovarianceActor
    from irp_shared.risk.private_covariance_service import run_private_covariance

    tenant = str(uuid.uuid4())
    ppf = _ppf_model(session, tenant)
    seg_a = _pure_private_segment(session, tenant, ppf, usd=_SEG_A_USD, eur=_SEG_A_EUR)
    seg_b = _pure_private_segment(session, tenant, ppf, usd=_SEG_B_USD, eur=_SEG_B_EUR)
    stored = run_private_covariance(
        session,
        acting_tenant=tenant,
        actor=PurePrivateCovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=_priv_cov_model(session, tenant, window=4),
        segment_factor_ids=[seg_a, seg_b],
    )
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="COVARIANCE_PRIVATE",
        table="covariance_result",
        subject_run_id=str(stored.run.run_id),
        column="covariance_value",
        tampered=_TAMPERED,
    )


def test_FACTOR_EXPOSURE_reproduces_and_detects_a_plant(session: Session) -> None:
    from test_factor_exposure import _ccy, _exposure_run, _factor, _model, _run

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exposure_run = _exposure_run(
        session, tenant, [("100", "12.50", "USD"), ("-40", "10.00", "USD")]
    )
    factor_id = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    stored = _run(session, tenant, mv, exposure_run, [factor_id])
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="FACTOR_EXPOSURE",
        table="factor_exposure_result",
        subject_run_id=str(stored.run.run_id),
        column="loading",
        tampered=_TAMPERED,
    )


def test_SENSITIVITY_reproduces_and_detects_a_plant(session: Session) -> None:
    from test_sensitivity import _ccy, _curve, _model, _run, _sel, _zero_nodes

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    stored = _run(session, tenant, mv, [_sel()])
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="SENSITIVITY",
        table="sensitivity_result",
        subject_run_id=str(stored.run.run_id),
        column="sensitivity_value",
        tampered=_TAMPERED,
    )


def test_SCENARIO_reproduces_and_detects_a_plant(session: Session) -> None:
    """The shocked-P&L family, whose key includes the NULL ``factor_id`` of the PNL_TOTAL row.

    Two shocked currencies so the run writes the total row AND per-factor rows: a single-row
    subject would leave the key projection's NULL handling unexercised.
    """
    from test_scenario import _run as _run_scenario
    from test_scenario import _scenario, _seed_factor_exposure_run

    tenant = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, tenant)
    definition_id = _scenario(session, tenant, fid_usd, fid_eur)
    stored = _run_scenario(session, tenant, fx_run, definition_id)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="SCENARIO",
        table="scenario_result",
        subject_run_id=str(stored.run.run_id),
        column="pnl",
        tampered=_TAMPERED,
    )
