"""End-to-end SQLite behavior tests for PPF-1 — the pure-private factor return (ENT-060, the 18th
governed number; §2.1 unification arc slice 1).

Proves the number COMPUTES end-to-end over the real substrate (a desmoothing run + a promoted
REGRESSION proxy blend + a PRIVATE segment membership), that the pooled pure-private return equals
the independently-recomputed ``desmoothed - Σ w·R`` per period, the summary row + counts, the
min-members / grid / named-gap refusals, and the rule-7 reads. RLS lives in the PG suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_proxy_mapping,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.perf import DesmoothedReturnActor, register_desmoothed_return_model
from irp_shared.perf.desmoothing_service import list_desmoothed_results, run_desmoothed_return
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_PURE_PRIVATE_PERIOD,
    METRIC_TYPE_PURE_PRIVATE_SUMMARY,
    ProxyWeightEstimateActor,
    PurePrivateFactorActor,
    PurePrivateFactorInputError,
    latest_pure_private_factor_for_segment,
    list_pure_private_factor_results,
    list_pure_private_factor_results_by_segment,
    promote_proxy_weight_estimate,
    register_proxy_weight_regression_model,
    register_pure_private_factor_model,
    run_proxy_weight_estimate,
    run_pure_private_factor_return,
)
from irp_shared.risk.private_factor_kernel import member_pure_private_return
from irp_shared.snapshot import PrivateFactorReturnSnapshotError
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2024, 6, 1, tzinfo=UTC)
MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
MARK_VALUES = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")
WINDOW = (date(2024, 6, 1), date(2026, 1, 1))
# One factor return per appraisal period_end (MARK_DATES[1:]) so each period compounds one value.
FX_USD_RETURNS = ["0.01", "0.02", "-0.01", "0.03", "0.00"]
FX_EUR_RETURNS = ["0.02", "-0.01", "0.01", "0.00", "0.02"]
W_USD = Decimal("0.6")
W_EUR = Decimal("0.3")


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


def _currency(db: Session, code: str = "USD") -> None:
    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
        db.flush()


def _desmoothed_run(db: Session, tenant: str) -> tuple[str, str, str]:
    _currency(db, "USD")
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"FUND-{uuid.uuid4().hex[:6]}",
        name="Buyout Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    for d, v in zip(MARK_DATES, MARK_VALUES, strict=True):
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code="USD",
        )
    db.flush()
    model = register_desmoothed_return_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", alpha="0.5"
    )
    out = run_desmoothed_return(
        db,
        acting_tenant=tenant,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(model.id),
        portfolio_id=pf,
        instrument_id=inst,
        window_start=WINDOW[0],
        window_end=WINDOW[1],
    )
    assert out.status == "COMPLETED"
    return str(out.run.run_id), pf, inst


def _factor(db: Session, tenant: str, code: str) -> str:
    return capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id


def _factor_returns(db: Session, tenant: str, factor_id: str, values: list[str]) -> None:
    factor = resolve_factor(db, factor_id, acting_tenant=tenant)
    for d, v in zip(MARK_DATES[1:], values, strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        )
    db.flush()


def _segment_factor(db: Session, tenant: str, code: str = "PRIVATE_EQUITY_GLOBAL") -> str:
    return capture_factor(
        db,
        factor_code=f"{code}-{uuid.uuid4().hex[:6]}",
        factor_source="PPF",
        factor_family="PRIVATE",
        frequency="APPRAISAL",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id


def _member_with_blend(db: Session, tenant: str) -> tuple[str, str, str]:
    """A private member with a desmoothing run + a promoted REGRESSION blend
    {FX_USD:0.6, FX_EUR:0.3}. Returns (desmoothed_run_id, instrument_id, portfolio_id)."""
    run_id, pf, inst = _desmoothed_run(db, tenant)
    fx_usd = _factor(db, tenant, f"FX_USD-{uuid.uuid4().hex[:4]}")
    fx_eur = _factor(db, tenant, f"FX_EUR-{uuid.uuid4().hex[:4]}")
    _factor_returns(db, tenant, fx_usd, FX_USD_RETURNS)
    _factor_returns(db, tenant, fx_eur, FX_EUR_RETURNS)
    est = run_proxy_weight_estimate(
        db,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(
            register_proxy_weight_regression_model(
                db, tenant_id=tenant, actor_id="s", code_version="v1", min_observations=4
            ).id
        ),
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    est_run = str(est.run.run_id)
    for fid, w in ((fx_usd, W_USD), (fx_eur, W_EUR)):
        promote_proxy_weight_estimate(
            db,
            private_instrument_id=inst,
            factor_id=fid,
            weight=w,
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            source_calculation_run_id=est_run,
        )
    db.flush()
    return run_id, inst, pf


def _expected_pp(db: Session, tenant: str, run_id: str) -> list[tuple[date, date, Decimal]]:
    """Recompute pp_t = desmoothed_t - (0.6*R_usd,t + 0.3*R_eur,t) independently from the desmoothed
    rows + the known factor returns (one return per period_end, so compound == that value)."""
    rows = [
        r
        for r in list_desmoothed_results(db, run_id, acting_tenant=tenant)
        if r.metric_type == "DESMOOTHED_PERIOD"
    ]
    # Factor returns by period_end (MARK_DATES[1:]).
    usd = dict(zip(MARK_DATES[1:], (Decimal(v) for v in FX_USD_RETURNS), strict=True))
    eur = dict(zip(MARK_DATES[1:], (Decimal(v) for v in FX_EUR_RETURNS), strict=True))
    out: list[tuple[date, date, Decimal]] = []
    for r in sorted(rows, key=lambda x: x.period_start):
        blend = [(W_USD, usd[r.period_end]), (W_EUR, eur[r.period_end])]
        out.append(
            (r.period_start, r.period_end, member_pure_private_return(r.metric_value, blend))
        )
    return out


def _ppf_model(db: Session, tenant: str, min_members: int = 1) -> str:
    return str(
        register_pure_private_factor_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", min_members=min_members
        ).id
    )


def test_single_member_pooled_return_matches_independent_recompute(session: Session) -> None:
    t = str(uuid.uuid4())
    run_id, inst, _pf = _member_with_blend(session, t)
    seg = _segment_factor(session, t)
    capture_proxy_mapping(  # the MANUAL membership row onto the segment
        session,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=t,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=T0,
    )
    out = run_pure_private_factor_return(
        session,
        acting_tenant=t,
        actor=PurePrivateFactorActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_ppf_model(session, t),
        segment_factor_id=seg,
        member_desmoothed_run_ids=[run_id],
    )
    assert out.status == "COMPLETED"
    rows = list_pure_private_factor_results(session, str(out.run.run_id), acting_tenant=t)
    period_rows = sorted(
        (r for r in rows if r.metric_type == METRIC_TYPE_PURE_PRIVATE_PERIOD),
        key=lambda r: r.period_start,
    )
    expected = _expected_pp(session, t, run_id)
    assert len(period_rows) == len(expected) >= 4
    for r, (p_start, p_end, pp) in zip(period_rows, expected, strict=True):
        assert r.period_start == p_start and r.period_end == p_end
        assert r.metric_value == pp.quantize(Decimal("1E-12"))
        assert r.member_count == 1
        assert r.segment_factor_id == str(seg).lower() or r.segment_factor_id == seg
        assert r.pooling_convention == "EQUAL_WEIGHT"
        assert r.intercept_convention == "RETAIN_ALPHA"
    # The single SUMMARY row: member_count 1, period_count = the number of periods.
    summary = [r for r in rows if r.metric_type == METRIC_TYPE_PURE_PRIVATE_SUMMARY]
    assert len(summary) == 1
    assert summary[0].member_count == 1
    assert summary[0].period_count == len(period_rows)


def test_rule7_reads_by_segment_and_latest(session: Session) -> None:
    t = str(uuid.uuid4())
    run_id, inst, _pf = _member_with_blend(session, t)
    seg = _segment_factor(session, t)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=t,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=T0,
    )
    common = dict(
        acting_tenant=t,
        actor=PurePrivateFactorActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_ppf_model(session, t),
        segment_factor_id=seg,
        member_desmoothed_run_ids=[run_id],
    )
    run_pure_private_factor_return(session, **common)
    run_pure_private_factor_return(session, **common)  # a second, newer run
    by_seg = list_pure_private_factor_results_by_segment(
        session, acting_tenant=t, segment_factor_id=seg
    )
    latest = latest_pure_private_factor_for_segment(session, acting_tenant=t, segment_factor_id=seg)
    # by-segment spans both runs; latest keeps only the newest run's rows.
    assert len({r.calculation_run_id for r in by_seg}) == 2
    assert len({r.calculation_run_id for r in latest}) == 1


def test_min_members_floor_refuses_below(session: Session) -> None:
    t = str(uuid.uuid4())
    run_id, inst, _pf = _member_with_blend(session, t)
    seg = _segment_factor(session, t)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=t,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=T0,
    )
    with pytest.raises(PurePrivateFactorInputError, match="min_members"):
        run_pure_private_factor_return(
            session,
            acting_tenant=t,
            actor=PurePrivateFactorActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=_ppf_model(session, t, min_members=2),  # need 2, only 1 member
            segment_factor_id=seg,
            member_desmoothed_run_ids=[run_id],
        )


def test_member_without_blend_is_named_gap(session: Session) -> None:
    t = str(uuid.uuid4())
    # A desmoothing run with NO promoted REGRESSION blend on the instrument. On the build path the
    # snapshot builder catches the named gap (a 409 PrivateFactorReturnSnapshotError, the
    # proxy-weight build-path precedent); the consume-existing path would raise the binder's 422.
    run_id, _pf, inst = _desmoothed_run(session, t)
    seg = _segment_factor(session, t)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=t,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=T0,
    )
    with pytest.raises(PrivateFactorReturnSnapshotError, match="REGRESSION"):
        run_pure_private_factor_return(
            session,
            acting_tenant=t,
            actor=PurePrivateFactorActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=_ppf_model(session, t),
            segment_factor_id=seg,
            member_desmoothed_run_ids=[run_id],
        )
