"""SQLite behavior tests for PA-2 — the proxy factor-exposure model (ENT-019's first governed
consumer; the thesis end-to-end demonstration).

Covers: the mixed-book projection golden (hand-derived); the sum-to-total identity in BOTH regimes
(exact for unproxied atoms; Σw × atom for proxied); **the end-to-end invariance golden THROUGH
covariance + VaR** (a proxied private book carries EXACTLY the VaR of its public-factor-equivalent
book — the thesis §2.1 statement as a byte-exact assertion); TR-09 BOTH sides under a proxy-weight
supersede; the fail-closed gates (unpinned proxy factor; proxy model over a non-proxy snapshot)
with NO RUNNING orphan; the no-proxy-rows degradation to the indicator rule; and
replace-not-add (the allocation model on the same book differs by design).

Golden derivation (TD-1-realistic mixed book, base USD):
  public bond I-USD:  qty 100 x mark 300 USD  -> atom  30000 (UNPROXIED -> indicator FX_USD, w=1)
  PE fund   I-PE:     qty 100 x mark 500 USD  -> atom  50000, proxy {FX_USD: 0.6, FX_EUR: 0.3}
  proxy rows: I-PE -> FX_USD 0.6*50000 = 30000; I-PE -> FX_EUR 0.3*50000 = 15000
  per-factor totals: FX_USD 60000, FX_EUR 15000; proxied sum 45000 = 0.9 * 50000 (partial, BY
  DESIGN); the public-equivalent book (I-A 60000 USD + I-B 15000 EUR marks) yields the SAME
  factor vector [60000, 15000] hence the SAME parametric VaR.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest
from run_assertions import assert_no_running_orphan
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    FxRateActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    capture_proxy_mapping,
    resolve_factor,
    supersede_proxy_mapping,
)
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    CovarianceActor,
    FactorExposureActor,
    FactorExposureInputError,
    VarActor,
    register_covariance_model,
    register_factor_exposure_model,
    register_factor_exposure_proxy_model,
    register_var_model,
    run_covariance,
    run_factor_exposure,
    run_var,
)
from irp_shared.snapshot import verify_snapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
ACT = FactorExposureActor(actor_id="analyst")


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


def _currencies(db: Session, *codes: str) -> None:
    from sqlalchemy import select

    for code in codes:
        if (
            db.execute(
                select(Currency).where(
                    Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code
                )
            ).scalar_one_or_none()
            is None
        ):
            db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _factor(db: Session, tenant: str, code: str, ccy: str) -> str:
    fid = capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=ccy,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    factor = resolve_factor(db, fid, acting_tenant=tenant)
    values = ["0.01", "0.02", "0.03", "0.04"] if ccy == "USD" else ["0.04", "0.03", "0.02", "0.01"]
    for d, v in zip(D, values, strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        )
    return fid


def _book(
    db: Session, tenant: str, holdings: list[tuple[str, str, str, str]]
) -> tuple[str, str, dict[str, str]]:
    """Seed a portfolio with (code, qty, mark, mark_ccy) holdings + a COMPLETED exposure run.
    Returns (exposure_run_id, portfolio_id, {code: instrument_id})."""
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="mixed book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    insts: dict[str, str] = {}
    for code, qty, mark, ccy in holdings:
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
            name=code,
            asset_class=("PRIVATE_EQUITY" if code.startswith("I-PE") else "BOND"),
            actor=ReferenceActor(actor_id="s"),
        ).id
        insts[code] = inst
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal(qty),
            valid_from=T0,
        )
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=VD,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(mark),
            currency_code=ccy,
            valid_from=T0,
        )
    from sqlalchemy import select as _select

    from irp_shared.marketdata.models import FxRate

    if (
        db.execute(
            _select(FxRate).where(FxRate.tenant_id == tenant, FxRate.rate_date == VD)
        ).first()
        is None
    ):  # idempotent — the public-equivalent test seeds a SECOND book in the same tenant
        capture_fx_rate(
            db,
            base_currency="EUR",
            quote_currency="USD",
            rate_date=VD,
            rate=Decimal(
                "1.250000000000"
            ),  # plausible EURUSD; NOT the knife-edge 1.0 (review fold)
            acting_tenant=tenant,
            actor=FxRateActor(actor_id="s"),
            valid_from=T0,
        )
    exposure = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    assert exposure.status == "COMPLETED"
    return exposure.run.run_id, pf, insts


def _proxy(db: Session, tenant: str, inst: str, fid: str, weight: str) -> None:
    capture_proxy_mapping(
        db,
        private_instrument_id=inst,
        factor_id=fid,
        weight=Decimal(weight),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=T0,
    )
    db.flush()


def _seed_mixed(db: Session, tenant: str):  # noqa: ANN202
    """The golden mixed book: I-USD 30000 (unproxied) + I-PE 50000 proxied {USD 0.6, EUR 0.3}."""
    _currencies(db, "USD", "EUR")
    fid_usd = _factor(db, tenant, "FX_USD", "USD")
    fid_eur = _factor(db, tenant, "FX_EUR", "EUR")
    exp_run, _pf, insts = _book(
        db, tenant, [("I-USD", "100", "300.00", "USD"), ("I-PE", "100", "500.00", "USD")]
    )
    pe = insts["I-PE"]
    _proxy(db, tenant, pe, fid_usd, "0.6")
    _proxy(db, tenant, pe, fid_eur, "0.3")
    return exp_run, fid_usd, fid_eur, pe, insts


def _run_proxy(db: Session, tenant: str, exp_run: str, fids: list[str]):  # noqa: ANN202
    mv = register_factor_exposure_proxy_model(
        db, tenant_id=tenant, actor_id="a", code_version="pa2-v1"
    )
    db.flush()
    return run_factor_exposure(
        db,
        acting_tenant=tenant,
        actor=ACT,
        code_version="pa2-v1",
        environment_id="ci",
        model_version_id=mv.id,
        exposure_run_id=exp_run,
        factor_ids=fids,
    )


def test_proxy_projection_golden_mixed_book(session: Session) -> None:
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, pe, insts = _seed_mixed(session, t)
    result = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    assert result.status == RunStatus.COMPLETED.value
    rows = {(r.instrument_id, r.factor_code): r for r in result.rows}
    assert len(result.rows) == 3  # 1 indicator (I-USD) + 2 proxied (I-PE)

    usd_inst = insts["I-USD"]
    # UNPROXIED: the allocation-v1 indicator rule unchanged (loading 1, exact).
    ind = rows[(usd_inst, "FX_USD")]
    assert ind.loading == Decimal("1") and ind.exposure_amount == Decimal("30000.000000")
    # PROXIED: exposure x weight per pinned proxy factor; loading = the captured weight.
    p_usd = rows[(pe, "FX_USD")]
    assert p_usd.loading == Decimal("0.6")
    assert p_usd.exposure_amount == Decimal("30000.000000")  # 0.6 * 50000
    p_eur = rows[(pe, "FX_EUR")]
    assert p_eur.loading == Decimal("0.3")
    assert p_eur.exposure_amount == Decimal("15000.000000")  # 0.3 * 50000
    # The sum-to-total identity in BOTH regimes: exact for the unproxied atom; Σw x atom (partial,
    # BY DESIGN — PA-0 OD-D) for the proxied one.
    assert p_usd.exposure_amount + p_eur.exposure_amount == Decimal("45000.000000")  # 0.9 * 50000


def test_end_to_end_var_equals_public_equivalent(session: Session) -> None:
    # THE thesis assertion, byte-exact: the proxied PRIVATE book's parametric VaR equals the VaR
    # of the PUBLIC book holding the same per-factor exposures [60000 USD, 15000 EUR].
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, _pe, _insts = _seed_mixed(session, t)
    fx_run = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    assert fx_run.status == RunStatus.COMPLETED.value

    def _var_over(fx_run_id: str) -> Decimal:
        cov_mv = register_covariance_model(
            session, tenant_id=t, actor_id="a", code_version="risk-v1", window_observations=4
        )
        cov = run_covariance(
            session,
            acting_tenant=t,
            actor=CovarianceActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=cov_mv.id,
            factor_ids=[fid_usd, fid_eur],
            as_of_valid_at=VALID_AT,
        )
        assert cov.status == RunStatus.COMPLETED.value
        var_mv = register_var_model(
            session, tenant_id=t, actor_id="a", code_version="risk-v1", confidence_level="0.99"
        )
        var = run_var(
            session,
            acting_tenant=t,
            actor=VarActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=var_mv.id,
            exposure_run_id=fx_run_id,
            covariance_run_id=cov.run.run_id,
        )
        assert var.status == RunStatus.COMPLETED.value
        return next(r.var_value for r in var.rows if r.metric_type == "VAR_PARAMETRIC")

    private_var = _var_over(fx_run.run.run_id)

    # The public-equivalent book: I-A 60000 in USD marks + I-B 15000 in EUR marks (indicator
    # allocation lands the SAME factor vector), run through the ALLOCATION model.
    # I-A: 200 x 300 USD = 60000. I-B: 40 x 300.00 EUR x 1.25 = 15000 USD — the FX conversion
    # path is EXERCISED (rate 1.25), not masked.
    pub_run, _pf, _pub_insts = _book(
        session, t, [("I-A", "200", "300.00", "USD"), ("I-B", "40", "300.00", "EUR")]
    )
    alloc_mv = register_factor_exposure_model(
        session, tenant_id=t, actor_id="a", code_version="risk-v1"
    )
    pub_fx = run_factor_exposure(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=alloc_mv.id,
        exposure_run_id=pub_run,
        factor_ids=[fid_usd, fid_eur],
    )
    assert pub_fx.status == RunStatus.COMPLETED.value
    public_var = _var_over(pub_fx.run.run_id)
    assert private_var == public_var  # byte-identical — the honest-risk demonstration

    # The ABSOLUTE anchor (review fold — the ratified record promised the end-to-end number
    # hand-derived, not only the invariance): recompute from FIRST PRINCIPLES per the documented
    # conventions (sample covariance (n-1) quantized 20dp; radicand at prec 50; VaR = z * sqrt,
    # quantized 6dp; z(0.99) = 2.326347874041) over the raw fixture returns and x = [60000, 15000].
    a = [Decimal(v) for v in ("0.01", "0.02", "0.03", "0.04")]
    b = [Decimal(v) for v in ("0.04", "0.03", "0.02", "0.01")]
    with localcontext() as ctx:
        ctx.prec = 50
        q20 = Decimal("1E-20")

        def _cov(u: list[Decimal], w: list[Decimal]) -> Decimal:
            mu, mw = sum(u) / 4, sum(w) / 4
            raw = sum((ui - mu) * (wi - mw) for ui, wi in zip(u, w, strict=True)) / 3
            return raw.quantize(q20, rounding=ROUND_HALF_UP)

        x1, x2 = Decimal(60000), Decimal(15000)
        radicand = _cov(a, a) * x1 * x1 + _cov(b, b) * x2 * x2 + 2 * _cov(a, b) * x1 * x2
        anchored = (Decimal("2.326347874041") * radicand.sqrt()).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    assert private_var == anchored  # the hand-derived absolute value


def test_tr09_proxy_supersede_both_sides(session: Session) -> None:
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, pe, insts = _seed_mixed(session, t)
    first = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    snap = first.run.input_snapshot_id
    assert verify_snapshot(session, snapshot_id=snap, acting_tenant=t).ok is True

    # Side 1: a post-run weight supersede is invisible to the pinned snapshot.
    supersede_proxy_mapping(
        session,
        private_instrument_id=pe,
        factor_id=fid_usd,
        weight=Decimal("0.8"),
        acting_tenant=t,
        actor=ProxyMappingActor(actor_id="s"),
        effective_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    session.flush()
    assert verify_snapshot(session, snapshot_id=snap, acting_tenant=t).ok is True

    # Side 2: a re-run against the SAME snapshot reproduces byte-identically (still 0.6).
    mv = register_factor_exposure_proxy_model(
        session, tenant_id=t, actor_id="a", code_version="pa2-v1"
    )
    second = run_factor_exposure(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="pa2-v1",
        environment_id="ci",
        model_version_id=mv.id,
        snapshot_id=snap,
    )
    key = lambda r: (r.instrument_id, r.factor_id)  # noqa: E731
    for a, b in zip(sorted(first.rows, key=key), sorted(second.rows, key=key), strict=True):
        assert (a.loading, a.exposure_amount) == (b.loading, b.exposure_amount)


def test_unpinned_proxy_factor_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, _pe, _insts = _seed_mixed(session, t)
    with pytest.raises(FactorExposureInputError):  # FX_EUR proxied but NOT in factor_ids
        _run_proxy(session, t, exp_run, [fid_usd])
    assert_no_running_orphan(session, run_type="FACTOR_EXPOSURE")


def test_proxy_model_over_plain_snapshot_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, _pe, _insts = _seed_mixed(session, t)
    # An allocation-model run mints a PLAIN (no-proxy-rows) snapshot...
    alloc_mv = register_factor_exposure_model(
        session, tenant_id=t, actor_id="a", code_version="risk-v1"
    )
    plain = run_factor_exposure(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=alloc_mv.id,
        exposure_run_id=exp_run,
        factor_ids=[fid_usd, fid_eur],
    )
    # ...which the PROXY model must refuse (it would silently degrade to the indicator rule).
    mv = register_factor_exposure_proxy_model(
        session, tenant_id=t, actor_id="a", code_version="pa2-v1"
    )
    with pytest.raises(FactorExposureInputError):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="pa2-v1",
            environment_id="ci",
            model_version_id=mv.id,
            snapshot_id=plain.run.input_snapshot_id,
        )
    assert_no_running_orphan(session, run_type="FACTOR_EXPOSURE")


def test_no_proxy_rows_degrades_to_indicator(session: Session) -> None:
    # A proxy-model run over a book with ZERO proxy rows follows the indicator rule for every atom
    # (the MD-H1 design-checklist case: NOT a refusal).
    t = str(uuid.uuid4())
    _currencies(session, "USD", "EUR")
    fid_usd = _factor(session, t, "FX_USD", "USD")
    fid_eur = _factor(session, t, "FX_EUR", "EUR")
    exp_run, _pf, _insts = _book(
        session, t, [("I-USD", "100", "300.00", "USD"), ("I-EUR", "100", "400.00", "EUR")]
    )
    result = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    assert result.status == RunStatus.COMPLETED.value
    rows = {r.factor_code: r for r in result.rows}
    assert rows["FX_USD"].loading == Decimal("1")
    assert rows["FX_USD"].exposure_amount == Decimal("30000.000000")
    assert rows["FX_EUR"].exposure_amount == Decimal("50000.000000")  # 100 x 400 EUR x 1.25


def test_allocation_model_replace_not_add(session: Session) -> None:
    # The ALLOCATION model on the mixed book puts the PE fund's WHOLE atom on its mark-currency
    # factor (50000 on FX_USD); the proxy model REPLACES that with the weighted rows — never both.
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, pe, insts = _seed_mixed(session, t)
    alloc_mv = register_factor_exposure_model(
        session, tenant_id=t, actor_id="a", code_version="risk-v1"
    )
    alloc = run_factor_exposure(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=alloc_mv.id,
        exposure_run_id=exp_run,
        factor_ids=[fid_usd, fid_eur],
    )
    pe_rows = [r for r in alloc.rows if r.instrument_id == pe]
    assert len(pe_rows) == 1 and pe_rows[0].exposure_amount == Decimal("50000.000000")

    proxy = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    pe_proxy_rows = [r for r in proxy.rows if r.instrument_id == pe]
    assert len(pe_proxy_rows) == 2  # replaced, not added-to
    assert {r.factor_code for r in pe_proxy_rows} == {"FX_USD", "FX_EUR"}


def test_zero_weight_leg_is_no_op_not_indicator(session: Session) -> None:
    # An explicit captured ZERO weight = "no loading on this leg" (capture accepts 0 — finiteness
    # only, PA-0 OD-D): the leg emits NO row and the instrument STAYS proxied (never the indicator
    # fallback; review fold — the earlier refusal bricked the whole book on one zero head row).
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, pe, insts = _seed_mixed(session, t)
    from irp_shared.marketdata import supersede_proxy_mapping as _sup

    _sup(
        session,
        private_instrument_id=pe,
        factor_id=fid_eur,
        weight=Decimal("0"),
        acting_tenant=t,
        actor=ProxyMappingActor(actor_id="s"),
        effective_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    session.flush()
    result = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    assert result.status == RunStatus.COMPLETED.value
    pe_rows = [r for r in result.rows if r.instrument_id == pe]
    assert len(pe_rows) == 1  # only the USD leg — the zeroed EUR leg is a no-op, NOT indicator
    assert pe_rows[0].factor_code == "FX_USD"
    assert pe_rows[0].exposure_amount == Decimal("30000.000000")


def test_allocation_model_over_proxy_snapshot_refused(session: Session) -> None:
    # The MIRROR of the predicate gate (review fold): the allocation model over a PROXY-predicate
    # snapshot would silently DISCARD the pinned proxy rows — refuse.
    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, _pe, _insts = _seed_mixed(session, t)
    proxy_run = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    alloc_mv = register_factor_exposure_model(
        session, tenant_id=t, actor_id="a", code_version="risk-v1"
    )
    with pytest.raises(FactorExposureInputError):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=alloc_mv.id,
            snapshot_id=proxy_run.run.input_snapshot_id,
        )
    assert_no_running_orphan(session, run_type="FACTOR_EXPOSURE")


def test_extreme_weight_is_committed_failed_not_raised(session: Session) -> None:
    # BOUNDARY: a capture-legal extreme weight (finiteness-only gate) x a large atom pushes the
    # product past the Numeric(28,6) envelope — a COMMITTED FAILED run (the raw product is gated
    # BEFORE quantize), never an InvalidOperation 500 (the P3-6/BT-1 echo-overflow class).
    t = str(uuid.uuid4())
    _currencies(session, "USD", "EUR")  # _book captures the EUR/USD FX leg unconditionally
    fid_usd = _factor(session, t, "FX_USD", "USD")
    exp_run, _pf, insts = _book(session, t, [("I-PE-XL", "100000000", "100000000.00", "USD")])
    _proxy(session, t, insts["I-PE-XL"], fid_usd, "1000000")  # atom 1E16 x weight 1E6 = 1E22
    result = _run_proxy(session, t, exp_run, [fid_usd])
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.failure_reason and "magnitude" in result.failure_reason
    assert_no_running_orphan(session, run_type="FACTOR_EXPOSURE")


def test_adjudicate_proxies_unit_gates() -> None:
    # Duplicate (instrument, factor) pins, pins matching no atom, and non-finite weights are
    # consume-existing trust-boundary refusals (hand-minted snapshots — the var_service twin).
    from irp_shared.risk.factor_kernel import AtomPin, FactorPin
    from irp_shared.risk.factor_service import ProxyPin, _adjudicate_proxies

    factors = [
        FactorPin(id="f1", factor_code="FX_USD", factor_family="CURRENCY", currency_code="USD")
    ]
    atoms = [
        AtomPin(
            id="a1",
            portfolio_id="p1",
            instrument_id="i1",
            base_currency="USD",
            mark_currency="USD",
            exposure_amount=Decimal("50000"),
        )
    ]
    dup = [
        ProxyPin(instrument_id="i1", factor_id="f1", weight=Decimal("0.6")),
        ProxyPin(instrument_id="i1", factor_id="f1", weight=Decimal("0.4")),
    ]
    with pytest.raises(FactorExposureInputError):
        _adjudicate_proxies(dup, factors, atoms)
    no_atom = [ProxyPin(instrument_id="i9", factor_id="f1", weight=Decimal("0.6"))]
    with pytest.raises(FactorExposureInputError):
        _adjudicate_proxies(no_atom, factors, atoms)
    non_finite = [ProxyPin(instrument_id="i1", factor_id="f1", weight=Decimal("NaN"))]
    with pytest.raises(FactorExposureInputError):
        _adjudicate_proxies(non_finite, factors, atoms)
    # A ZERO weight passes adjudication (a captured judgment — the no-op leg, review fold).
    zero = [ProxyPin(instrument_id="i1", factor_id="f1", weight=Decimal("0"))]
    assert _adjudicate_proxies(zero, factors, atoms) == {"i1": zero}


def test_active_risk_refuses_proxy_run(session: Session) -> None:
    # Downstream partition guard (review fold): active risk normalizes by the SUMMED pinned rows —
    # valid only for a PARTITIONING (allocation) run; a partial-proxy run would silently
    # redistribute the unmodeled residual, so it refuses fail-closed (proxy-aware AR is the v2).
    from irp_shared.risk import ActiveRiskInputError, run_active_risk

    t = str(uuid.uuid4())
    exp_run, fid_usd, fid_eur, _pe, _insts = _seed_mixed(session, t)
    proxy_fx = _run_proxy(session, t, exp_run, [fid_usd, fid_eur])
    cov_mv = register_covariance_model(
        session, tenant_id=t, actor_id="a", code_version="risk-v1", window_observations=4
    )
    cov = run_covariance(
        session,
        acting_tenant=t,
        actor=CovarianceActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=cov_mv.id,
        factor_ids=[fid_usd, fid_eur],
        as_of_valid_at=VALID_AT,
    )
    from irp_shared.risk import ActiveRiskActor, register_active_risk_model

    ar_mv = register_active_risk_model(session, tenant_id=t, actor_id="a", code_version="risk-v1")
    with pytest.raises(ActiveRiskInputError):
        run_active_risk(
            session,
            acting_tenant=t,
            actor=ActiveRiskActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=ar_mv.id,
            exposure_run_id=proxy_fx.run.run_id,
            covariance_run_id=cov.run.run_id,
            benchmark_id=str(uuid.uuid4()),  # never reached — the partition gate fires first
            benchmark_effective_date=VD,
        )
    assert_no_running_orphan(session, run_type="ACTIVE_RISK")
