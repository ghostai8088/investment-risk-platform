"""REPRO-2 — five of the sixteen adapters, each made to say YES and then made to say NO.

Companion to ``test_reproduction_families.py``, which owns the shared pair
(``assert_reproduces_and_then_diverges``) and the construction guarantees. This module carries the
five PERFORMANCE families: PORTFOLIO_RETURN, BENCHMARK_RELATIVE, DESMOOTHED_RETURN, ROLLING_RISK
and SHARPE.

Every subject run here is built through that family's OWN test module's fixtures rather than
hand-seeded, for the reason SR-1 wrote down and paid for: *a fixture derived FROM the subject
cannot test it*. The adapters re-execute the production binder over the run's own pinned snapshot,
so a subject assembled by anything other than the production write path would prove the adapter
against a shape production never emits.

**On ROLLING_RISK and SHARPE, and their suppressed rows.** Both families emit a row for every
requested window even when the window cannot be filled, and a suppressed row carries
``metric_value IS NULL`` under a total-enumeration CHECK constraint
(``suppressed = false AND metric_value IS NOT NULL``, or ``suppressed = true AND metric_value IS
NULL``). Two consequences, both load-bearing for the plants below:

* a plant into ``metric_value`` on a suppressed row would VIOLATE that CHECK — the tamper would
  fail on the write rather than produce a divergence, and
* a run whose rows are ALL suppressed carries no governed number in that column at all, so a
  "divergence" there would be about the suppression encoding rather than about arithmetic.

So both fixtures are chosen to fill their window completely — fourteen months against a twelve-month
window for ROLLING_RISK, twelve months against a twelve-month window for SHARPE — and each test
ASSERTS that no row is suppressed before planting. That assertion is not decoration: it is what
stops the plant from silently becoming a test of the CHECK constraint instead of a test of the
adapter, and it fails loudly the day a fixture change reintroduces a suppressed row.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_reproduction_families import assert_reproduces_and_then_diverges

from irp_shared.calc.models import RunStatus
from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory

#: A plainly different, in-scale value for a `PreciseDecimal(20, 12)` column. It is not a plausible
#: return, a plausible tracking error or a plausible Sharpe ratio, which is deliberate: a plant that
#: could be mistaken for a real figure makes a failure harder to read, and TD-1's realism rule is
#: explicitly about FIXTURES rather than about labelled boundary values.
_TAMPERED = "0.123456789012"


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


# ------------------------------------------------------------------------------ PORTFOLIO_RETURN --
def test_PORTFOLIO_RETURN_reproduces_and_detects_a_plant(session: Session) -> None:
    """PM-1's Modified-Dietz / TWR pair (ENT-053), through PM-1's own build path."""
    from test_portfolio_return import D0, D1, MID, _book, _boundary_run, _flow, _model, _run

    tenant = str(uuid.uuid4())
    pf, inst = _book(session, tenant)
    r0 = _boundary_run(session, pf, inst, D0, "1000000", tenant)
    r1 = _boundary_run(session, pf, inst, D1, "1050000", tenant)
    _flow(session, pf, inst, MID, "20000", tenant=tenant)
    mv = _model(session, tenant)
    stored = _run(session, [r0, r1], mv, tenant)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="PORTFOLIO_RETURN",
        table="portfolio_return_result",
        subject_run_id=str(stored.run.run_id),
        column="return_value",
        tampered=_TAMPERED,
    )


# ---------------------------------------------------------------------------- BENCHMARK_RELATIVE --
def test_BENCHMARK_RELATIVE_reproduces_and_detects_a_plant(session: Session) -> None:
    """P3-8's active return / TD / TE / IR set (ENT-054) over a real PM-1 run + captured index.

    This is the family whose "not yet adapted" reason was FACTUALLY WRONG — it said the adapter had
    to read ``benchmark_id`` and ``return_basis`` back off the stored rows, when the binder refuses
    both alongside ``snapshot_id`` and adjudicates them out of the pin. The green half below is what
    executes that correction: an adapter written to the old instruction would raise here rather than
    reproduce, on every single run.
    """
    from test_benchmark_relative import (
        D0,
        D1,
        D2,
        _bench_return,
        _benchmark,
        _model,
        _return_run,
        _run,
    )

    tenant = str(uuid.uuid4())
    run_id, _pf = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")], tenant)
    bm = _benchmark(session, tenant)
    _bench_return(session, bm, D1, "0.025", tenant)
    _bench_return(session, bm, D2, "0.005", tenant)
    mv = _model(session, tenant)
    stored = _run(session, run_id, bm.id, mv, tenant)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="BENCHMARK_RELATIVE",
        table="benchmark_relative_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        tampered=_TAMPERED,
    )


# ---------------------------------------------------------------------------- DESMOOTHED_RETURN ---
def test_DESMOOTHED_RETURN_reproduces_and_detects_a_plant(session: Session) -> None:
    """PA-1's Geltner inversion (ENT-056) over the quarterly appraisal book."""
    from test_desmoothed_return import _run, _seed_marks

    tenant = str(uuid.uuid4())
    pf, inst = _seed_marks(session, tenant)
    stored = _run(session, tenant, pf, inst)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="DESMOOTHED_RETURN",
        table="desmoothed_return_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        tampered=_TAMPERED,
    )


# --------------------------------------------------------------------------------- ROLLING_RISK ---
def test_ROLLING_RISK_reproduces_and_detects_a_plant(session: Session) -> None:
    """RM-1's rolling window set (ENT-064) — and the ``window_months`` read-back that feeds it.

    Fourteen monthly sub-periods against a single twelve-month window: three complete windows, four
    metrics each, and NO suppressed row — see the module docstring for why that matters before a
    ``metric_value`` plant. The recovered-window path is exercised implicitly and unavoidably: the
    adapter cannot call ``run_rolling_risk`` at all without recovering ``(12,)`` off these rows.
    """
    from test_rolling_risk import _run_rolling

    tenant = str(uuid.uuid4())
    stored = _run_rolling(session, tenant, returns=["0.01", "0.02"] * 7, windows=(12,))
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason
    # The precondition the plant depends on, asserted rather than assumed: a suppressed row carries
    # a NULL `metric_value` under a total-enumeration CHECK, so tampering one would fail on the
    # WRITE and this test would be about the constraint instead of about the adapter.
    assert stored.rows and not any(r.suppressed for r in stored.rows), (
        "the fixture emitted a suppressed row, so a metric_value plant would violate the "
        "suppressed/metric_value CHECK instead of proving the adapter compares the column"
    )

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="ROLLING_RISK",
        table="rolling_risk_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        tampered=_TAMPERED,
    )


# ---------------------------------------------------------------------------------------- SHARPE --
def test_SHARPE_reproduces_and_detects_a_plant(session: Session) -> None:
    """SR-1's Sharpe pair (ENT-065) over the golden portfolio leg + a real risk-free series.

    The golden fixture is twelve monthly observations against a twelve-month window, so both emitted
    rows carry a governed ``metric_value`` and neither is suppressed — the same precondition
    ROLLING_RISK asserts above, and asserted here for the same reason.
    """
    from test_sharpe import _GOLDEN_PORTFOLIO, _run_sharpe

    tenant = str(uuid.uuid4())
    stored = _run_sharpe(session, tenant, returns=list(_GOLDEN_PORTFOLIO), windows=(12,))
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason
    assert stored.rows and not any(r.suppressed for r in stored.rows), (
        "the fixture emitted a suppressed row, so a metric_value plant would violate the "
        "suppressed/metric_value CHECK instead of proving the adapter compares the column"
    )

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="SHARPE",
        table="sharpe_ratio_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        tampered=_TAMPERED,
    )
