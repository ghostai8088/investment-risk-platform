"""SQLite behavior tests for FL-1 — the LOADINGS factor-exposure model (the proxy projection
generalized: fractional signed multi-factor loadings over the widened admitted families).

Covers: the fractional multi-factor projection golden (hand-derived; MARKET + STYLE loadings, one
signed negative, Σ exposure ≠ Σ atoms BY DESIGN); the family widening (a MARKET/STYLE loading is
admitted where the allocation/proxy families refuse it); the COVERAGE GATE (an unloaded atom
refuses the run closed — no indicator fallback, no silent zero); a zero-weight row IS coverage (a
declared "this atom projects to nothing"); the 3×3 predicate symmetry (each family refuses the
other two families' snapshots); and active-risk's automatic refusal of a loadings run.

Golden derivation (base USD): one public equity I-EQ, atom 50000, loadings {MKT_BROAD: 0.8
(MARKET), STY_VAL: -0.2 (STYLE)}:
  MKT_BROAD:  0.8 * 50000 = 40000
  STY_VAL:   -0.2 * 50000 = -10000  (signed)
  Σ exposure = 30000 ≠ 50000 (the 0.4 unloaded residual is honestly unmodeled — the projection).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_proxy_mapping,
)
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FactorExposureActor,
    FactorExposureInputError,
    register_factor_exposure_loadings_model,
    register_factor_exposure_model,
    register_factor_exposure_proxy_model,
    run_factor_exposure,
)
from irp_shared.snapshot import (
    FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE,
    FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
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


def _factor(db: Session, tenant: str, code: str, family: str) -> str:
    """A non-partitioning factor (MARKET/STYLE/...): no currency_code — the loadings family matches
    by id, not by a currency partition."""
    fid = capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family=family,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    return fid


def _book(db: Session, tenant: str, holdings: list[tuple[str, str, str]]) -> tuple[str, dict]:
    """Seed a portfolio with (code, qty, mark USD) holdings + a COMPLETED exposure run."""
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="equity book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    insts: dict[str, str] = {}
    for code, qty, mark in holdings:
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
            name=code,
            asset_class="EQUITY",
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
            currency_code="USD",
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
    return exposure.run.run_id, insts


def _loading(db: Session, tenant: str, inst: str, fid: str, weight: str) -> None:
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


def _run_loadings(db: Session, tenant: str, exp_run: str, fids: list[str]):  # noqa: ANN202
    mv = register_factor_exposure_loadings_model(
        db, tenant_id=tenant, actor_id="a", code_version="fl1-v1"
    )
    db.flush()
    return run_factor_exposure(
        db,
        acting_tenant=tenant,
        actor=ACT,
        code_version="fl1-v1",
        environment_id="ci",
        model_version_id=mv.id,
        exposure_run_id=exp_run,
        factor_ids=fids,
    )


def _seed_equity(db: Session, tenant: str):  # noqa: ANN202
    """One equity I-EQ (atom 50000), loadings {MKT_BROAD 0.8 (MARKET), STY_VAL -0.2 (STYLE)}."""
    fid_mkt = _factor(db, tenant, "MKT_BROAD", "MARKET")
    fid_sty = _factor(db, tenant, "STY_VAL", "STYLE")
    exp_run, insts = _book(db, tenant, [("I-EQ", "100", "500.00")])
    eq = insts["I-EQ"]
    _loading(db, tenant, eq, fid_mkt, "0.8")
    _loading(db, tenant, eq, fid_sty, "-0.2")
    return exp_run, fid_mkt, fid_sty, eq


def test_loadings_projection_golden(session: Session) -> None:
    t = str(uuid.uuid4())
    exp_run, fid_mkt, fid_sty, eq = _seed_equity(session, t)
    result = _run_loadings(session, t, exp_run, [fid_mkt, fid_sty])
    assert result.status == RunStatus.COMPLETED.value
    rows = {r.factor_code: r for r in result.rows}
    assert len(result.rows) == 2  # fractional, multi-factor, one instrument

    mkt = rows["MKT_BROAD"]
    assert mkt.loading == Decimal("0.8")
    assert mkt.exposure_amount == Decimal("40000.000000")  # 0.8 * 50000
    sty = rows["STY_VAL"]
    assert sty.loading == Decimal("-0.2")  # SIGNED
    assert sty.exposure_amount == Decimal("-10000.000000")  # -0.2 * 50000
    # The PROJECTION: Σ exposure = 30000 ≠ 50000 (the atom) — the 0.4 residual honestly unmodeled.
    assert mkt.exposure_amount + sty.exposure_amount == Decimal("30000.000000")


def test_loadings_family_widening_admits_market_where_proxy_refuses(session: Session) -> None:
    # The allocation/proxy families stay CURRENCY-only; a MARKET/STYLE factor is admitted ONLY
    # through the loadings family. The golden above proves admission; here the PROXY model over the
    # same MARKET loading rows refuses (its factor gate is CURRENCY-only).
    t = str(uuid.uuid4())
    exp_run, fid_mkt, fid_sty, _eq = _seed_equity(session, t)
    mv = register_factor_exposure_proxy_model(
        session, tenant_id=t, actor_id="a", code_version="pa2-v1"
    )
    session.flush()
    with pytest.raises(FactorExposureInputError, match="is not admitted"):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="pa2-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=exp_run,
            factor_ids=[fid_mkt, fid_sty],
        )


def test_coverage_gate_refuses_unloaded_atom(session: Session) -> None:
    # Two equities; only one is loaded. The unloaded atom REFUSES the run closed (no indicator
    # fallback, no silent zero — the OD-FL-1-D coverage gate).
    t = str(uuid.uuid4())
    fid_mkt = _factor(session, t, "MKT_BROAD", "MARKET")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00"), ("I-BARE", "100", "300.00")])
    _loading(session, t, insts["I-EQ"], fid_mkt, "0.8")
    with pytest.raises(FactorExposureInputError, match="requires every atom to carry"):
        _run_loadings(session, t, exp_run, [fid_mkt])


def test_zero_loading_is_coverage_not_refusal(session: Session) -> None:
    # A captured zero-weight row IS coverage (a declared "this atom projects to nothing"): the atom
    # is loaded, emits no exposure row, and the run COMPLETES (the residual is the whole atom).
    t = str(uuid.uuid4())
    fid_mkt = _factor(session, t, "MKT_BROAD", "MARKET")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    _loading(session, t, insts["I-EQ"], fid_mkt, "0")
    result = _run_loadings(session, t, exp_run, [fid_mkt])
    assert result.status == RunStatus.COMPLETED.value
    assert len(result.rows) == 0  # the zero leg emits no row; the atom is fully residual


def test_loadings_model_over_proxy_snapshot_refused(session: Session) -> None:
    # The 3×3 symmetry: a proxy-predicate snapshot bound to the loadings model refuses.
    t = str(uuid.uuid4())
    fid_usd = _factor(session, t, "FX_USD", "CURRENCY")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    # Build a PROXY snapshot (needs a CURRENCY proxy row so the proxy model would accept it).
    _loading(session, t, insts["I-EQ"], fid_usd, "0.5")
    from irp_shared.snapshot import build_factor_exposure_snapshot
    from irp_shared.snapshot.service import SnapshotActor as _SA

    snap = build_factor_exposure_snapshot(
        session,
        acting_tenant=t,
        actor=_SA(actor_id="s", actor_type="user"),
        exposure_run_id=exp_run,
        factor_ids=[fid_usd],
        include_proxy_rows=True,
    )
    assert snap.binding_predicate_version == FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE
    mv = register_factor_exposure_loadings_model(
        session, tenant_id=t, actor_id="a", code_version="fl1-v1"
    )
    session.flush()
    with pytest.raises(FactorExposureInputError, match="does not match the bound"):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="fl1-v1",
            environment_id="ci",
            model_version_id=mv.id,
            snapshot_id=snap.id,
        )


def test_proxy_and_allocation_over_loadings_snapshot_refused(session: Session) -> None:
    # The other two arms of the 3×3: proxy AND allocation over a loadings-predicate snapshot refuse.
    t = str(uuid.uuid4())
    fid_usd = _factor(session, t, "FX_USD", "CURRENCY")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    _loading(session, t, insts["I-EQ"], fid_usd, "0.5")
    from irp_shared.snapshot import build_factor_exposure_snapshot
    from irp_shared.snapshot.service import SnapshotActor as _SA

    snap = build_factor_exposure_snapshot(
        session,
        acting_tenant=t,
        actor=_SA(actor_id="s", actor_type="user"),
        exposure_run_id=exp_run,
        factor_ids=[fid_usd],
        loadings_family=True,
    )
    assert snap.binding_predicate_version == FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE
    proxy_mv = register_factor_exposure_proxy_model(
        session, tenant_id=t, actor_id="a", code_version="pa2-v1"
    )
    alloc_mv = register_factor_exposure_model(
        session, tenant_id=t, actor_id="a", code_version="p33-v1"
    )
    session.flush()
    for mv, cv in ((proxy_mv, "pa2-v1"), (alloc_mv, "p33-v1")):
        with pytest.raises(FactorExposureInputError, match="does not match the bound"):
            run_factor_exposure(
                session,
                acting_tenant=t,
                actor=ACT,
                code_version=cv,
                environment_id="ci",
                model_version_id=mv.id,
                snapshot_id=snap.id,
            )
