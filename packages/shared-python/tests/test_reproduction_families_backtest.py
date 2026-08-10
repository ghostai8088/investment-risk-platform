"""REPRO-2 — the three risk-verdict families, each made to say YES and then made to say NO.

Same pair, same reasoning as ``test_reproduction_families``: a real subject run built through the
family's OWN production binder must sweep back ``MATCH`` over a non-zero row count, and then one
governed value column, overwritten in place with raw SQL, must make the same sweep say
``DIVERGED`` and NAME the field. The helper is imported rather than re-implemented — a second copy
would be a second thing to weaken.

``VAR_BACKTEST`` and ``ES_BACKTEST`` share ``var_backtest_result``, and that shared table is
exactly why they are worth planting against separately: the two families are told apart by RUN
TYPE, not by their rows, so a plant scoped to one subject run must not be read as the other
family's divergence. The helper's UPDATE is scoped by ``calculation_run_id`` and each fixture here
mints exactly one run of its own family, so the two never bleed into each other.
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


def test_ACTIVE_RISK_reproduces_and_detects_a_plant(session: Session) -> None:
    """The tracking-error family: the full upstream chain, a captured benchmark, one TE row."""
    from test_active_risk import _build, _model, _seed_benchmark, _seed_upstream_runs

    tenant = str(uuid.uuid4())
    fx_run, cov_run, _factor_ids = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    stored = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="ACTIVE_RISK",
        table="active_risk_result",
        subject_run_id=str(stored.run.run_id),
        # `te_value` is PreciseDecimal(20, 12) — the plant is written at the column's own scale so
        # the read-back compares like with like rather than proving a rounding artefact.
        column="te_value",
        tampered=str(Decimal("0.123456789012")),
    )


def test_VAR_BACKTEST_reproduces_and_detects_a_plant(session: Session) -> None:
    """Kupiec: 70000 -> 68000 over one pair => the exception golden, three metric rows."""
    from test_var_backtest import (
        TENANT,
        _bt_model,
        _return_run,
        _run,
        _seed_var_chain,
        _var_run,
    )

    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    stored = _run(session, return_run, [var_run], mv)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        # The var-backtest fixture's helpers pin their own module-level tenant internally, so the
        # sweep must act as that tenant rather than a fresh one — a mismatch would sweep an empty
        # tenant and MATCH over zero rows, which the helper's row-count assertion refuses anyway.
        TENANT,
        family_key="VAR_BACKTEST",
        table="var_backtest_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        tampered=str(Decimal("7.777777")),
    )


def test_ES_BACKTEST_reproduces_and_detects_a_plant(session: Session) -> None:
    """Acerbi-Szekely: 3 pairs at 0.9750 with one breach — the off-domain golden's substrate."""
    from test_es_backtest import _mint_es_substrate

    from irp_shared.risk.bootstrap import register_es_backtest_model
    from irp_shared.risk.es_backtest_service import run_es_backtest
    from irp_shared.risk.events import EsBacktestActor

    tenant, ret_run, var_runs, es_runs = _mint_es_substrate(session, 3, breach_at=frozenset({1}))
    mv = register_es_backtest_model(
        session, tenant_id=tenant, actor_id="a", code_version="bt3-v1"
    ).id
    stored = run_es_backtest(
        session,
        acting_tenant=tenant,
        actor=EsBacktestActor(actor_id="a"),
        code_version="bt3-v1",
        environment_id="ci",
        model_version_id=mv,
        portfolio_return_run_id=ret_run,
        var_run_ids=var_runs,
        es_run_ids=es_runs,
    )
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="ES_BACKTEST",
        table="var_backtest_result",
        subject_run_id=str(stored.run.run_id),
        # A different column type from VAR_BACKTEST's on the SAME table, deliberately: an adapter
        # that compared only the Numeric value columns would pass that test and fail this one.
        column="n_exceptions",
        tampered="4242",
    )
