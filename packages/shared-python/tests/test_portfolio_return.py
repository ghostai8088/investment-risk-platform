"""PM-1 portfolio-return binder + kernel (SQLite): the governed time-weighted return (ENT-053).

Covers the pure kernel goldens; the full-stack build-in-request + consume-existing paths; the
AD-014 / TR-09 reproducibility invariant (a later exposure re-run OR a transaction appended after
the snapshot cannot move a historical return); the pre-create refusal battery (NO imputation); the
post-create FAILED magnitude gate; the append-only + run_type!=metric_type + migration-head + fence
sync guards; and the zero-`PERF.*`-audit assertion. The PG-specific RLS / trigger / downgrade legs
live in ``test_portfolio_return_pg.py``.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.models import Base
from irp_shared.perf import (
    METRIC_TYPE_DIETZ_PERIOD,
    METRIC_TYPE_TWR_LINKED,
    PORTFOLIO_RETURN_MODEL_CODE,
    RUN_TYPE_PORTFOLIO_RETURN,
    PortfolioReturnActor,
    PortfolioReturnInputError,
    PortfolioReturnResult,
    compute_dietz_period,
    dietz_denominator,
    link_periods,
    list_portfolio_returns,
    register_portfolio_return_model,
    run_portfolio_return,
)
from irp_shared.perf.return_kernel import ReturnKernelError
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import PURPOSE_RETURN_INPUT, resolve_snapshot
from irp_shared.transaction import TransactionActor, record_transaction
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

TENANT = str(uuid.uuid4())
T0 = datetime(2026, 1, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
D0, D1 = date(2026, 1, 1), date(2026, 1, 31)  # 30-day sub-period
MID = date(2026, 1, 16)  # a mid-period flow: day_offset 15
ACTOR = PortfolioReturnActor(actor_id="analyst")


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


# --------------------------------------------------------------------------- kernel goldens


def test_kernel_goldens() -> None:
    # A +20,000 contribution at the sub-period midpoint (weight 0.5): 30,000/1,010,000.
    est = compute_dietz_period(Decimal("1000000"), Decimal("1050000"), [(15, Decimal("20000"))], 30)
    assert str(est.return_value) == "0.029702970297"
    # A no-flow sub-period reduces EXACTLY to EMV/BMV - 1.
    assert (
        str(compute_dietz_period(Decimal("1000000"), Decimal("1030000"), [], 30).return_value)
        == "0.030000000000"
    )
    # Geometric linking (1.03)(0.98)(1.01) - 1.
    assert str(link_periods([Decimal("0.03"), Decimal("-0.02"), Decimal("0.01")])) == (
        "0.019494000000"
    )
    # The denominator helper: BMV + Σ w·F; MAY be <= 0 without raising (the caller's gate).
    assert dietz_denominator(Decimal("1000000"), [(15, Decimal("20000"))], 30) == Decimal("1010000")
    assert dietz_denominator(Decimal("1000000"), [(1, Decimal("-2000000"))], 30) < 0


def test_kernel_pathologies_refuse() -> None:
    for args in (
        (Decimal("1000000"), Decimal("1"), [], 0),  # non-positive period length
        (Decimal("0"), Decimal("1"), [], 30),  # non-positive begin MV
        (Decimal("1000000"), Decimal("1"), [(31, Decimal("1"))], 30),  # flow outside sub-period
        (Decimal("1000000"), Decimal("900000"), [(1, Decimal("-2000000"))], 30),  # denom <= 0
    ):
        with pytest.raises(ReturnKernelError):
            compute_dietz_period(*args)
    with pytest.raises(ReturnKernelError):
        link_periods([])


# --------------------------------------------------------------------------- full-stack fixtures


def _seed_currency(db: Session, code: str) -> None:
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _book(db: Session, tenant: str = TENANT) -> tuple[str, str]:
    """A single-portfolio, single-instrument book. Returns (portfolio_id, instrument_id)."""
    _seed_currency(db, "USD")
    _seed_currency(db, "EUR")
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"I-{uuid.uuid4().hex[:6]}",
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("1"),
        valid_from=T0,
    )
    return pf, inst


def _boundary_run(
    db: Session, pf: str, inst: str, vdate: date, mark: str, tenant: str = TENANT
) -> str:
    """One COMPLETED exposure run whose valuation date is ``vdate`` and whose single-atom MARKET
    VALUE is ``mark`` (quantity 1 x mark x USD-base fx 1). Returns the exposure run id."""
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=vdate,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code="USD",
        valid_from=T0,
    )
    result = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    assert result.status == RunStatus.COMPLETED.value
    return result.run.run_id


def _flow(
    db: Session,
    pf: str,
    inst: str,
    trade_date: date,
    amount: str,
    txn_type: str = "TRANSFER_IN",
    currency: str | None = "USD",
    tenant: str = TENANT,
) -> None:
    record_transaction(
        db,
        tenant_id=tenant,
        portfolio_id=pf,
        instrument_id=inst,
        txn_type=txn_type,
        trade_date=trade_date,
        quantity=Decimal("0"),
        gross_amount=None if amount is None else Decimal(amount),
        currency_code=currency,
        actor=TransactionActor(actor_id="s"),
    )


def _model(db: Session, tenant: str = TENANT) -> str:
    return register_portfolio_return_model(
        db, tenant_id=tenant, actor_id="a", code_version="perf-v1"
    ).id


def _run(db: Session, runs: list[str], mv_id: str, tenant: str = TENANT):  # noqa: ANN202
    return run_portfolio_return(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=mv_id,
        exposure_run_ids=runs,
    )


# --------------------------------------------------------------------------- golden end-to-end


def test_build_path_dietz_and_twr_golden(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    _flow(session, pf, inst, MID, "20000")  # +20,000 at day 15
    mv = _model(session)

    result = _run(session, [r0, r1], mv)
    assert result.status == RunStatus.COMPLETED.value
    rows = {r.metric_type: r for r in result.rows}
    assert set(rows) == {METRIC_TYPE_DIETZ_PERIOD, METRIC_TYPE_TWR_LINKED}
    dietz = rows[METRIC_TYPE_DIETZ_PERIOD]
    assert str(dietz.return_value) == "0.029702970297"
    assert dietz.begin_mv == Decimal("1000000.000000")
    assert dietz.end_mv == Decimal("1050000.000000")
    assert dietz.net_external_flow == Decimal("20000.000000")
    assert dietz.n_flows == 1 and dietz.n_periods == 1
    assert dietz.period_start == D0 and dietz.period_end == D1
    assert dietz.portfolio_id == pf and dietz.base_currency == "USD"
    # One sub-period => the linked return equals the sub-period return.
    assert str(rows[METRIC_TYPE_TWR_LINKED].return_value) == "0.029702970297"
    assert rows[METRIC_TYPE_TWR_LINKED].n_periods == 1


def test_no_flow_reduces_to_twr(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1030000")
    mv = _model(session)
    result = _run(session, [r0, r1], mv)
    dietz = next(r for r in result.rows if r.metric_type == METRIC_TYPE_DIETZ_PERIOD)
    assert str(dietz.return_value) == "0.030000000000"  # EMV/BMV - 1 exactly
    assert dietz.n_flows == 0


def test_three_boundaries_link(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1030000")  # +3% no-flow
    r2 = _boundary_run(session, pf, inst, date(2026, 3, 2), "1020700")  # -0.902...%? see below
    mv = _model(session)
    result = _run(session, [r0, r1, r2], mv)
    rows = [r for r in result.rows if r.metric_type == METRIC_TYPE_DIETZ_PERIOD]
    assert len(rows) == 2  # N-1 sub-periods
    linked = next(r for r in result.rows if r.metric_type == METRIC_TYPE_TWR_LINKED)
    assert linked.n_periods == 2
    # linked = Π(1+r_i) - 1, recomputed from the two DIETZ rows.
    prod = Decimal(1)
    for r in rows:
        prod *= Decimal(1) + r.return_value
    assert linked.return_value == (prod - Decimal(1)).quantize(Decimal("1.000000000000"))


# --------------------------------------------------------------- reproducibility (AD-014 / TR-09)


def test_consume_existing_reproduces_and_is_snapshot_invariant(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    _flow(session, pf, inst, MID, "20000")
    mv = _model(session)
    first = _run(session, [r0, r1], mv)
    snap_id = first.run.input_snapshot_id
    assert resolve_snapshot(session, snap_id, acting_tenant=TENANT).purpose == PURPOSE_RETURN_INPUT

    # TR-09: append a transaction AFTER the snapshot was pinned — it must NOT move the return.
    _flow(session, pf, inst, MID, "500000")
    rerun = run_portfolio_return(
        session,
        acting_tenant=TENANT,
        actor=ACTOR,
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=snap_id,
    )
    a = next(r for r in first.rows if r.metric_type == METRIC_TYPE_DIETZ_PERIOD)
    b = next(r for r in rerun.rows if r.metric_type == METRIC_TYPE_DIETZ_PERIOD)
    assert a.return_value == b.return_value == Decimal("0.029702970297")


def test_non_base_flow_converted_via_pinned_fx(session: Session) -> None:
    """A EUR flow is converted to the USD base via the FX leg pinned at the flow's trade_date."""
    pf, inst = _book(session)
    capture_fx_rate(
        session,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=MID,
        rate=Decimal("1.100000000000"),  # 1 EUR = 1.10 USD
        acting_tenant=TENANT,
        actor=FxRateActor(actor_id="s"),
        valid_from=T0,
    )
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    _flow(session, pf, inst, MID, "10000", currency="EUR")  # +10,000 EUR = +11,000 USD
    mv = _model(session)
    result = _run(session, [r0, r1], mv)
    dietz = next(r for r in result.rows if r.metric_type == METRIC_TYPE_DIETZ_PERIOD)
    assert dietz.net_external_flow == Decimal("11000.000000")  # converted to base
    expected = compute_dietz_period(
        Decimal("1000000"), Decimal("1050000"), [(15, Decimal("11000"))], 30
    ).return_value
    assert dietz.return_value == expected


# --------------------------------------------------------------------------- pre-create refusals


def test_single_boundary_refused(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    mv = _model(session)
    before = session.execute(select(func.count()).select_from(CalculationRun)).scalar()
    with pytest.raises(PortfolioReturnInputError):
        _run(session, [r0], mv)
    # Zero run: pre-create refusal never created a portfolio-return run.
    after = session.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.run_type == RUN_TYPE_PORTFOLIO_RETURN)
    ).scalar()
    assert after == 0
    assert before == session.execute(select(func.count()).select_from(CalculationRun)).scalar()


def test_multi_portfolio_book_refused(session: Session) -> None:
    pf1, inst1 = _book(session)
    pf2, inst2 = _book(session)
    # Two boundary runs over DIFFERENT portfolios (a subtree-shaped book) — refused.
    r0 = _boundary_run(session, pf1, inst1, D0, "1000000")
    r1 = _boundary_run(session, pf2, inst2, D1, "1050000")
    mv = _model(session)
    with pytest.raises(PortfolioReturnInputError):
        _run(session, [r0, r1], mv)


def test_null_flow_currency_refused(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    _flow(session, pf, inst, MID, "20000", currency=None)  # NULL currency on an in-set flow
    mv = _model(session)
    with pytest.raises(PortfolioReturnInputError):
        _run(session, [r0, r1], mv)


def test_non_positive_denominator_refused(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    # A withdrawal on day 1 far exceeding average capital => denominator <= 0 => pre-create refuse.
    _flow(session, pf, inst, date(2026, 1, 2), "5000000", txn_type="TRANSFER_OUT")
    mv = _model(session)
    with pytest.raises(PortfolioReturnInputError):
        _run(session, [r0, r1], mv)


def test_unregistered_and_ambiguous_refused(session: Session) -> None:
    from irp_shared.model.service import UnregisteredModelError

    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    mv = _model(session)
    # Unregistered model_version id => the CTRL-003 inventory-before-use gate (422 at the API).
    with pytest.raises(UnregisteredModelError):
        run_portfolio_return(
            session,
            acting_tenant=TENANT,
            actor=ACTOR,
            code_version="perf-v1",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            exposure_run_ids=[r0, r1],
        )
    # Ambiguous (both snapshot_id and exposure_run_ids) => refused BEFORE the model gate.
    with pytest.raises(PortfolioReturnInputError):
        run_portfolio_return(
            session,
            acting_tenant=TENANT,
            actor=ACTOR,
            code_version="perf-v1",
            environment_id="ci",
            model_version_id=mv,
            exposure_run_ids=[r0, r1],
            snapshot_id=str(uuid.uuid4()),
        )


def test_internal_txn_types_ignored(session: Session) -> None:
    """A BUY/DIVIDEND is INTERNAL to the book — not an external flow, so it does not enter Dietz."""
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1030000")
    _flow(session, pf, inst, MID, "999999", txn_type="BUY")  # internal — ignored
    mv = _model(session)
    result = _run(session, [r0, r1], mv)
    dietz = next(r for r in result.rows if r.metric_type == METRIC_TYPE_DIETZ_PERIOD)
    assert dietz.n_flows == 0 and str(dietz.return_value) == "0.030000000000"


# ------------------------------------------------------------- post-create FAILED (magnitude gate)


def test_magnitude_overflow_is_failed_run(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    mv = _model(session)
    # Force the kernel to report an out-of-range magnitude inside compute (post-create): a committed
    # FAILED run + zero rows + a naming reason, never a 500 (the P3-7 magnitude-gate precedent).
    import irp_shared.perf.return_service as svc

    def _boom(*_a: object, **_k: object) -> object:
        raise ReturnKernelError("return magnitude out of range")

    monkeypatch.setattr(svc, "compute_dietz_period", _boom)
    result = _run(session, [r0, r1], mv)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.failure_reason and "magnitude" in result.failure_reason
    # The FAILED run is COMMITTED (a durable resource), with zero result rows.
    assert list_portfolio_returns(session, run_id=result.run.run_id, acting_tenant=TENANT) == []


def test_extreme_return_is_failed_not_column_overflow(session: Session) -> None:
    """REAL reachability of the magnitude gate (no monkeypatch): a column-legal-but-extreme pin —
    BMV 1 -> EMV 1E10 => return ~1E10 — exceeds the Numeric(20,12) envelope (|value| < 1E8). The
    kernel's 12dp-quantize guard bounds only the SCALE (trips ~1E38), so WITHOUT the binder's
    _MAX_RESULT_ABS gate this would overflow the column (PG 500) / persist garbage (SQLite). The
    gate makes it a committed FAILED run instead. Labeled magnitude-boundary test (TD-1)."""
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1")  # BMV = 1
    r1 = _boundary_run(session, pf, inst, D1, "10000000000")  # EMV = 1E10 (< 1E22 envelope)
    mv = _model(session)
    result = _run(session, [r0, r1], mv)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.failure_reason and "magnitude" in result.failure_reason


def test_duplicate_boundary_run_ids_refused(session: Session) -> None:
    """A repeated boundary run id would pin its atoms twice -> IntegrityError at the SECOND flush
    (after the header is written). The builder refuses BEFORE any write (ReturnSnapshotError,
    409), surfaced through the binder."""
    from irp_shared.snapshot import ReturnSnapshotError

    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    mv = _model(session)
    with pytest.raises(ReturnSnapshotError):
        _run(session, [r0, r1, r0], mv)  # r0 twice


def test_duplicate_boundary_dates_refused(session: Session) -> None:
    """Two boundary runs at the SAME valuation date = a zero-length sub-period = refused pre-create
    (the binder orders by date + rejects equal dates; caller order is irrelevant). One valuation at
    D0; two exposure runs as-of D0 -> two runs whose boundary date is both D0."""
    pf, inst = _book(session)
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=D0,
        acting_tenant=TENANT,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal("1000000"),
        currency_code="USD",
        valid_from=T0,
    )

    def _run_at_d0() -> str:
        return run_exposure(
            session,
            acting_tenant=TENANT,
            actor=ExposureActor(actor_id="a"),
            code_version="v1",
            environment_id="ci",
            portfolio_id=pf,
            as_of_valid_at=datetime(D0.year, D0.month, D0.day, tzinfo=UTC),
            as_of_known_at=KNOWN_AT,
            base_currency="USD",
        ).run.run_id

    r0, r1 = _run_at_d0(), _run_at_d0()  # two distinct runs, both boundary date D0
    mv = _model(session)
    with pytest.raises(PortfolioReturnInputError):
        _run(session, [r0, r1], mv)


def test_unknown_boundary_run_refused(session: Session) -> None:
    """A boundary run id not visible as a COMPLETED exposure run in the acting tenant is refused
    pre-create (the security gate — a hand-minted set cannot reference a foreign/absent run)."""
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    mv = _model(session)
    with pytest.raises(PortfolioReturnInputError):
        _run(session, [r0, str(uuid.uuid4())], mv)


def test_missing_fx_leg_for_flow_fails_closed(session: Session) -> None:
    """A non-base (EUR) external flow with NO pinned FX rate for its trade_date fails closed at
    build (FxRateNotFound) — the 'a missing leg fails closed, NO imputation' invariant. No FX is
    captured here (contrast test_non_base_flow_converted_via_pinned_fx)."""
    from irp_shared.marketdata import FxRateNotFound

    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    _flow(session, pf, inst, MID, "10000", currency="EUR")  # EUR flow, no EUR/USD rate captured
    mv = _model(session)
    with pytest.raises(FxRateNotFound):
        _run(session, [r0, r1], mv)


def test_foreign_portfolio_id_refused_pre_create(session: Session) -> None:
    """The measured book's portfolio_id (from pinned atom JSON) is re-resolved under the acting
    tenant before it is stamped into the NOT-NULL portfolio FK — a foreign/non-existent id is
    refused pre-create (the P3-5 cross-tenant-FK guard), never a durable cross-tenant reference or a
    flush 500."""
    from irp_shared.perf.return_service import _assert_portfolio_in_tenant

    pf, inst = _book(session)
    # A real portfolio in the tenant resolves cleanly.
    _assert_portfolio_in_tenant(session, pf, acting_tenant=TENANT)
    # A non-existent / foreign portfolio id is refused.
    with pytest.raises(PortfolioReturnInputError):
        _assert_portfolio_in_tenant(session, str(uuid.uuid4()), acting_tenant=TENANT)


# --------------------------------------------------------------------------- governance guards


def test_append_only_result_row(session: Session) -> None:
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    mv = _model(session)
    result = _run(session, [r0, r1], mv)
    row = result.rows[0]
    row.return_value = Decimal("0.999999999999")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_run_type_is_not_a_metric(session: Session) -> None:
    assert RUN_TYPE_PORTFOLIO_RETURN not in {METRIC_TYPE_DIETZ_PERIOD, METRIC_TYPE_TWR_LINKED}


def test_perf_imports_no_risk_or_exposure_symbol() -> None:
    """The peer-family fence: ``perf`` imports NO ``risk`` symbol and NO ``exposure`` symbol (the
    two governed-number families are peers, not a chain; the boundary-run ``run_type`` is a
    fence-kept local constant). Model-registry governance lives in ``model.service`` (PM-1)."""
    import ast

    import irp_shared.perf as perf_pkg

    src = pathlib.Path(perf_pkg.__file__).parent
    for path in src.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                assert "risk" not in parts, f"{path.name} imports risk: {node.module}"
                assert "exposure" not in parts, f"{path.name} imports exposure: {node.module}"
            if isinstance(node, ast.Import):
                for a in node.names:
                    parts = a.name.split(".")
                    assert "risk" not in parts, f"{path.name} imports risk: {a.name}"
                    assert "exposure" not in parts, f"{path.name} imports exposure: {a.name}"


def test_exposure_run_type_constant_in_sync() -> None:
    """The binder keeps a fence-safe LOCAL copy of the exposure run_type (perf must not import
    exposure); this pins the two strings equal so a rename cannot silently break boundaries."""
    from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE
    from irp_shared.perf.return_service import _EXPOSURE_RUN_TYPE

    assert _EXPOSURE_RUN_TYPE == RUN_TYPE_EXPOSURE_AGGREGATE


def test_no_perf_audit_events_emitted(session: Session) -> None:
    """PM-1 mints NO ``PERF.*`` code — the run reuses ``CALC.RUN_*`` (OD-PM-1-A)."""
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    mv = _model(session)
    _run(session, [r0, r1], mv)
    perf_events = session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type.like("PERF.%"))
    ).scalar()
    assert perf_events == 0


def test_migration_head_is_portfolio_return() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_current_head() == "0031_portfolio_return"
    assert script.get_revision("0031_portfolio_return").down_revision == "0030_active_risk"


def test_perf_permissions_grants_as_ratified() -> None:
    from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES

    run_holders = {r for r, codes in ROLE_TEMPLATES.items() if "perf.run" in codes}
    view_holders = {r for r, codes in ROLE_TEMPLATES.items() if "perf.view" in codes}
    assert run_holders == {"platform_admin", "data_steward", "risk_analyst_1l"}
    assert view_holders == {
        "platform_admin",
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "auditor_3l",  # INCLUDED — governed performance-output oversight (OD-PM-1-A)
    }


def test_methodology_doc_exists_and_has_required_sections() -> None:
    from irp_shared.perf.bootstrap import PORTFOLIO_RETURN_METHODOLOGY_REF

    root = pathlib.Path(__file__).resolve().parents[3]
    doc = root / PORTFOLIO_RETURN_METHODOLOGY_REF
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for section in (
        "Purpose & applicability",
        "Inputs & data policy",
        "Formulas & numerical standards",
        "Assumptions",
        "Validation / reproduction tests",
        "Governed-number contract",
        "Known limitations",
    ):
        assert section in text, f"missing methodology section: {section}"


def test_methodology_ref_matches_registered_version(session: Session) -> None:
    from irp_shared.model.models import ModelVersion
    from irp_shared.perf.bootstrap import PORTFOLIO_RETURN_METHODOLOGY_REF

    root = pathlib.Path(__file__).resolve().parents[3]
    mv_id = _model(session)
    version = session.get(ModelVersion, mv_id)
    assert version is not None
    assert version.methodology_ref == PORTFOLIO_RETURN_METHODOLOGY_REF
    assert (root / version.methodology_ref).is_file()


def test_reproduce_result_model_grain(session: Session) -> None:
    """The grain (calculation_run_id, metric_type, period_start) lets a DIETZ_PERIOD row and the
    TWR_LINKED row share period_start (the first boundary) — both persist without a unique clash."""
    pf, inst = _book(session)
    r0 = _boundary_run(session, pf, inst, D0, "1000000")
    r1 = _boundary_run(session, pf, inst, D1, "1050000")
    mv = _model(session)
    result = _run(session, [r0, r1], mv)
    rows = list_portfolio_returns(session, run_id=result.run.run_id, acting_tenant=TENANT)
    starts = {(r.metric_type, r.period_start) for r in rows}
    assert (METRIC_TYPE_DIETZ_PERIOD, D0) in starts
    assert (METRIC_TYPE_TWR_LINKED, D0) in starts  # shares period_start, distinct metric_type
    assert isinstance(rows[0], PortfolioReturnResult)
    assert PORTFOLIO_RETURN_MODEL_CODE == "perf.return.twr"
