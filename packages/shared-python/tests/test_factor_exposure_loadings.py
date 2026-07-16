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
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_proxy_mapping,
    resolve_factor,
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
    register_factor_exposure_loadings_model,
    register_factor_exposure_model,
    register_factor_exposure_proxy_model,
    register_var_model,
    run_covariance,
    run_factor_exposure,
    run_var,
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
D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
ACT = FactorExposureActor(actor_id="analyst")


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


def _ccy_factor(db: Session, tenant: str, code: str, ccy: str) -> str:
    """A CURRENCY factor with a 4-day return series (for covariance/VaR downstream)."""
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


def test_loadings_over_plain_allocation_snapshot_refused(session: Session) -> None:
    # The SIXTH 3×3 arm (review fold): the loadings model over a PLAIN allocation-predicate
    # snapshot refuses (it pins no loading rows — the loadings run would have nothing to project).
    t = str(uuid.uuid4())
    _currencies(session, "USD")
    fid_usd = _ccy_factor(session, t, "FX_USD", "USD")
    exp_run, _insts = _book(session, t, [("I-EQ", "100", "500.00")])
    from irp_shared.snapshot import (
        FACTOR_EXPOSURE_BINDING_PREDICATE,
        build_factor_exposure_snapshot,
    )
    from irp_shared.snapshot.service import SnapshotActor as _SA

    snap = build_factor_exposure_snapshot(
        session,
        acting_tenant=t,
        actor=_SA(actor_id="s", actor_type="user"),
        exposure_run_id=exp_run,
        factor_ids=[fid_usd],
    )
    assert snap.binding_predicate_version == FACTOR_EXPOSURE_BINDING_PREDICATE
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


def test_loadings_registrar_conflict_on_same_label_twin(session: Session) -> None:
    # Review fold: a same-label (v1) register with a DIFFERENT code_version is a conflict refusal
    # (the register/run-consistency seam — no silent second identity for the loadings model).
    from irp_shared.risk import ModelVersionConflictError

    t = str(uuid.uuid4())
    register_factor_exposure_loadings_model(
        session, tenant_id=t, actor_id="a", code_version="fl1-v1"
    )
    session.flush()
    with pytest.raises(ModelVersionConflictError):
        register_factor_exposure_loadings_model(
            session, tenant_id=t, actor_id="a", code_version="fl1-v2"
        )


def test_loadings_unpinned_factor_refused(session: Session) -> None:
    # Review fold (V2): the PA-2 unpinned-factor guard pinned for the LOADINGS family — a loading
    # row whose factor is NOT in the run's factor_ids refuses closed (no silent dropping).
    t = str(uuid.uuid4())
    exp_run, fid_mkt, fid_sty, _eq = _seed_equity(session, t)  # loadings on MKT + STY
    mv = register_factor_exposure_loadings_model(
        session, tenant_id=t, actor_id="a", code_version="fl1-v1"
    )
    session.flush()
    # Pin only MKT in factor_ids; the STY loading row is then unpinned → refuse.
    with pytest.raises(FactorExposureInputError, match="not in the pinned factor list"):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="fl1-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=exp_run,
            factor_ids=[fid_mkt],
        )


def test_loadings_binder_refuses_other_family_factor(session: Session) -> None:
    # Review fold: the loadings binder's factor gate refuses OTHER (the catch-all stays refused
    # after the widening — the ES-1 probe-move endpoint).
    t = str(uuid.uuid4())
    fid_mkt = _factor(session, t, "MKT_BROAD", "MARKET")
    fid_other = _factor(session, t, "MYSTERY", "OTHER")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    _loading(session, t, insts["I-EQ"], fid_mkt, "0.8")
    mv = register_factor_exposure_loadings_model(
        session, tenant_id=t, actor_id="a", code_version="fl1-v1"
    )
    session.flush()
    with pytest.raises(FactorExposureInputError, match="is not admitted"):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="fl1-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=exp_run,
            factor_ids=[fid_mkt, fid_other],
        )


def test_loadings_magnitude_breach_is_committed_failed_not_raised(session: Session) -> None:
    # Review fold: an out-of-envelope loading × atom is a committed FAILED run (durable evidence),
    # NOT a raw 500 — the loadings family on the shared _build_rows gate.
    t = str(uuid.uuid4())
    fid_mkt = _factor(session, t, "MKT_BROAD", "MARKET")
    # atom = 100 × 1E19 = 1E21 mark → 1.0 × 1E21 breaches the 1E21 envelope.
    exp_run, insts = _book(session, t, [("I-EQ", "100", "10000000000000000000")])
    _loading(session, t, insts["I-EQ"], fid_mkt, "1.0")
    result = _run_loadings(session, t, exp_run, [fid_mkt])
    assert result.status == RunStatus.FAILED.value
    assert result.rows == [] and result.failure_reason
    assert "magnitude-out-of-range:loading" in result.failure_reason


def test_allocation_refuses_handminted_loading_rows_on_content(session: Session) -> None:
    # Review fold (adversarial F2 — the silent-discard hole): a hand-minted snapshot pinning
    # loading rows under the ALLOCATION predicate is refused on the CONTENT (not just the predicate
    # string), so the allocation binder can never COMPLETE while silently discarding the rows.
    import json
    from types import SimpleNamespace

    from irp_shared.snapshot import (
        COMPONENT_KIND_PROXY_MAPPING,
        FACTOR_EXPOSURE_BINDING_PREDICATE,
        PURPOSE_FACTOR_EXPOSURE_INPUT,
        build_factor_exposure_snapshot,
        list_components,
    )
    from irp_shared.snapshot.service import SnapshotActor as _SA
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    t = str(uuid.uuid4())
    _currencies(session, "USD")
    fid_usd = _ccy_factor(session, t, "FX_USD", "USD")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    _loading(session, t, insts["I-EQ"], fid_usd, "0.5")
    # Build a real rows-bearing (loadings) snapshot, then RE-MINT its components under the
    # ALLOCATION predicate (the snapshot header is append-only immutable, so we forge a fresh one —
    # exactly the hand-mint threat model: attacker-chosen predicate over rows-bearing content).
    good = build_factor_exposure_snapshot(
        session,
        acting_tenant=t,
        actor=_SA(actor_id="s", actor_type="user"),
        exposure_run_id=exp_run,
        factor_ids=[fid_usd],
        loadings_family=True,
    )
    comps = list_components(session, snapshot_id=good.id, acting_tenant=t)
    assert any(c.component_kind == COMPONENT_KIND_PROXY_MAPPING for c in comps)
    specs: list = []
    for c in comps:
        content = json.loads(c.captured_content)
        anchor = SimpleNamespace(
            id=content.get("id", str(uuid.uuid4())),
            valid_from=None,
            system_from=T0,
            record_version=None,
        )
        _append_spec(specs, c.component_kind, c.target_entity_type, anchor, content)
    forged = _persist_snapshot(
        session,
        acting_tenant=t,
        actor=_SA(actor_id="s", actor_type="user"),
        specs=specs,
        label="",
        purpose=PURPOSE_FACTOR_EXPOSURE_INPUT,
        as_of_valid_at=VALID_AT,
        as_of_known_at=VALID_AT,
        as_of_valuation_date=VD,
        binding_predicate_version=FACTOR_EXPOSURE_BINDING_PREDICATE,  # the forgery
    )
    session.flush()
    alloc_mv = register_factor_exposure_model(
        session, tenant_id=t, actor_id="a", code_version="p33-v1"
    )
    session.flush()
    with pytest.raises(FactorExposureInputError, match="would be silently discarded"):
        run_factor_exposure(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="p33-v1",
            environment_id="ci",
            model_version_id=alloc_mv.id,
            snapshot_id=forged.id,
        )


def _var_over(session: Session, t: str, fids: list[str], fx_run_id: str) -> Decimal:
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
        factor_ids=fids,
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


def test_loadings_run_through_var_equals_proxy_equivalent(session: Session) -> None:
    # The verifier-fold M1 (the OD-D per-consumer claim, test-proven): VaR CONSUMES the loadings
    # rows exactly as it consumes proxy rows — a loadings run over CURRENCY factors with weights
    # {0.6, 0.3} yields the SAME VaR as the PROXY run over the same weights (byte-identical), so a
    # fractional loadings row cannot silently drop or double-count into VaR.
    t = str(uuid.uuid4())
    _currencies(session, "USD", "EUR")
    fid_usd = _ccy_factor(session, t, "FX_USD", "USD")
    fid_eur = _ccy_factor(session, t, "FX_EUR", "EUR")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    eq = insts["I-EQ"]
    _loading(session, t, eq, fid_usd, "0.6")
    _loading(session, t, eq, fid_eur, "0.3")

    load_run = _run_loadings(session, t, exp_run, [fid_usd, fid_eur])
    assert load_run.status == RunStatus.COMPLETED.value
    # Same fixture, PROXY model (CURRENCY factors are admitted for proxy too).
    proxy_mv = register_factor_exposure_proxy_model(
        session, tenant_id=t, actor_id="a", code_version="pa2-v1"
    )
    session.flush()
    proxy_run = run_factor_exposure(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="pa2-v1",
        environment_id="ci",
        model_version_id=proxy_mv.id,
        exposure_run_id=exp_run,
        factor_ids=[fid_usd, fid_eur],
    )
    assert proxy_run.status == RunStatus.COMPLETED.value

    load_var = _var_over(session, t, [fid_usd, fid_eur], load_run.run.run_id)
    proxy_var = _var_over(session, t, [fid_usd, fid_eur], proxy_run.run.run_id)
    assert load_var == proxy_var  # byte-identical — VaR consumes loadings rows unchanged
    assert load_var > 0


def test_active_risk_refuses_a_loadings_run(session: Session) -> None:
    # OD-D: active-risk's allocation-only model-code whitelist refuses a loadings run automatically
    # (the loadings-aware denominator stays the recorded v2, open since PA-2).
    from datetime import date as _date

    from irp_shared.risk import ActiveRiskActor, register_active_risk_model, run_active_risk
    from irp_shared.risk.active_risk_service import ActiveRiskInputError

    t = str(uuid.uuid4())
    _currencies(session, "USD", "EUR")
    fid_usd = _ccy_factor(session, t, "FX_USD", "USD")
    fid_eur = _ccy_factor(session, t, "FX_EUR", "EUR")
    exp_run, insts = _book(session, t, [("I-EQ", "100", "500.00")])
    _loading(session, t, insts["I-EQ"], fid_usd, "0.6")
    _loading(session, t, insts["I-EQ"], fid_eur, "0.3")
    load_run = _run_loadings(session, t, exp_run, [fid_usd, fid_eur])
    assert load_run.status == RunStatus.COMPLETED.value

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
    ar_mv = register_active_risk_model(session, tenant_id=t, actor_id="a", code_version="risk-v1")
    session.flush()
    # The loadings exposure run is refused by active-risk's partitioning-only whitelist.
    with pytest.raises(ActiveRiskInputError, match="allocation"):
        run_active_risk(
            session,
            acting_tenant=t,
            actor=ActiveRiskActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=ar_mv.id,
            exposure_run_id=load_run.run.run_id,
            covariance_run_id=cov.run.run_id,
            benchmark_id=str(uuid.uuid4()),
            benchmark_effective_date=_date(2026, 6, 1),
        )


def test_scenario_run_binder_refuses_non_currency_loadings_run(session: Session) -> None:
    # THE FIFTH GATE (the verifier pass's census HIGH — scenario_service.py's run-binder
    # exposure-family gate, distinct from scenario.py's shock-capture gate): a scenario run over a
    # loadings run whose pinned exposure rows carry a non-CURRENCY family REFUSES pre-create.
    # Previously this gate had NO probe of its own; FL-1 pins it with a REAL loadings run.
    from irp_shared.risk import (
        ScenarioActor,
        capture_scenario_shock,
        create_scenario_definition,
        register_scenario_model,
        run_scenario,
    )
    from irp_shared.risk.scenario_service import ScenarioInputError

    t = str(uuid.uuid4())
    _currencies(session, "USD")
    exp_run, fid_mkt, fid_sty, _eq = _seed_equity(session, t)  # MARKET + STYLE loadings
    load_run = _run_loadings(session, t, exp_run, [fid_mkt, fid_sty])
    assert load_run.status == RunStatus.COMPLETED.value

    s_act = ScenarioActor(actor_id="a")
    fid_usd = _ccy_factor(session, t, "FX_USD", "USD")
    d = create_scenario_definition(
        session,
        code="CRASH",
        name="Crash",
        scenario_type="HISTORICAL",
        acting_tenant=t,
        actor=s_act,
    )
    session.flush()
    capture_scenario_shock(
        session,
        scenario_definition_id=d.id,
        factor_id=fid_usd,
        shock_value=Decimal("-0.10"),
        acting_tenant=t,
        actor=s_act,
        valid_from=T0,
    )
    session.flush()
    mv = register_scenario_model(session, tenant_id=t, actor_id="a", code_version="s-v1")
    session.flush()
    with pytest.raises(ScenarioInputError, match="is not CURRENCY"):
        run_scenario(
            session,
            acting_tenant=t,
            actor=s_act,
            code_version="s-v1",
            environment_id="ci",
            model_version_id=mv.id,
            factor_exposure_run_id=load_run.run.run_id,
            scenario_definition_id=d.id,
        )


# --- Step 3: the α=1 estimation chain — public marks → desmooth(identity) → OLS → promote -------

# TD-1-realistic daily equity marks: 9 marks ⇒ 8 observed returns ⇒ 7 desmoothed periods (the α=1
# run consumes its seed observation) — the OLS floor max(min_obs=4, k+2=4) admits k=2.
_EQ_MARK_DATES = tuple(date(2026, 5, d) for d in (18, 19, 20, 21, 22, 25, 26, 27, 28))
_EQ_MARK_VALUES = (
    "500.00",
    "505.00",
    "502.48",
    "507.50",
    "512.58",
    "510.02",
    "515.12",
    "512.54",
    "517.67",
)
_EQ_WINDOW = (date(2026, 5, 17), date(2026, 5, 29))


def test_alpha_one_chain_public_marks_to_promoted_loadings(session: Session) -> None:
    """The OD-FL-1-B end-to-end: a PUBLIC equity's raw marks ride the SHIPPED desmoothing service
    at α=1 (the Geltner identity — metric_value == observed_return per period, asserted), feed
    PA-3's OLS over the WIDENED candidate families (MARKET + RATES — one newly-minted FRTB
    family), and the estimated betas PROMOTE into the widened ENT-019 as REGRESSION-method loading
    rows, byte-equal to the estimate rows."""
    from sqlalchemy import select

    from irp_shared.marketdata.models import ProxyMapping
    from irp_shared.perf import (
        DesmoothedReturnActor,
        register_desmoothed_return_model,
        run_desmoothed_return,
    )
    from irp_shared.perf.models import METRIC_TYPE_DESMOOTHED_PERIOD, DesmoothedReturnResult
    from irp_shared.risk import (
        METRIC_TYPE_WEIGHT,
        ProxyWeightEstimateActor,
        list_proxy_weight_results,
        promote_proxy_weight_estimate,
        register_proxy_weight_regression_model,
        run_proxy_weight_estimate,
    )

    t = str(uuid.uuid4())
    _currencies(session, "USD")

    # 1. The public equity's daily marks (a plain valuation series — no private asset_class).
    pf = create_portfolio(
        session,
        tenant_id=t,
        code=f"EQ-{uuid.uuid4().hex[:6]}",
        name="public equity book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        session,
        tenant_id=t,
        code=f"PUBCO-{uuid.uuid4().hex[:6]}",
        name="PubCo",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    for d, v in zip(_EQ_MARK_DATES, _EQ_MARK_VALUES, strict=True):
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=t,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code="USD",
        )
    session.flush()

    # 2. Desmooth at α=1 — a FREE declared identity parameter with domain (0, 1]; no vocab work.
    dm_model = register_desmoothed_return_model(
        session, tenant_id=t, actor_id="s", code_version="v1", alpha="1"
    )
    dm = run_desmoothed_return(
        session,
        acting_tenant=t,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=str(dm_model.id),
        portfolio_id=pf,
        instrument_id=inst,
        window_start=_EQ_WINDOW[0],
        window_end=_EQ_WINDOW[1],
    )
    assert dm.status == "COMPLETED"
    periods = (
        session.execute(
            select(DesmoothedReturnResult)
            .where(
                DesmoothedReturnResult.calculation_run_id == str(dm.run.run_id),
                DesmoothedReturnResult.metric_type == METRIC_TYPE_DESMOOTHED_PERIOD,
            )
            .order_by(DesmoothedReturnResult.period_end)
        )
        .scalars()
        .all()
    )
    assert len(periods) == 7  # 9 marks ⇒ 8 observed ⇒ 7 desmoothed (the seed is consumed)
    for p in periods:  # the α=1 IDENTITY, asserted per period
        assert p.metric_value == p.observed_return

    # 3. The OLS candidates: MARKET + RATES (a newly-minted FRTB family) — the widened :266 gate.
    f_mkt = _factor(session, t, "MKT_BROAD", "MARKET")
    f_rates = _factor(session, t, "RATES_L1", "RATES")
    period_ends = [p.period_end for p in periods]
    mkt_vals = ["0.010", "-0.005", "0.010", "0.010", "-0.005", "0.010", "-0.005"]
    rates_vals = ["-0.002", "0.004", "0.001", "-0.003", "0.002", "0.000", "0.003"]
    for fid, vals in ((f_mkt, mkt_vals), (f_rates, rates_vals)):
        factor = resolve_factor(session, fid, acting_tenant=t)
        for d, v in zip(period_ends, vals, strict=True):
            capture_factor_return(
                session,
                factor,
                return_date=d,
                return_value=Decimal(v),
                acting_tenant=t,
                actor=FactorActor(actor_id="s"),
                valid_from=T0,
            )
    session.flush()

    pw_model = register_proxy_weight_regression_model(
        session, tenant_id=t, actor_id="s", code_version="v1", min_observations=4
    )
    est = run_proxy_weight_estimate(
        session,
        acting_tenant=t,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=str(pw_model.id),
        desmoothed_run_id=str(dm.run.run_id),
        factor_ids=[f_mkt, f_rates],
    )
    assert est.status == "COMPLETED"
    weights = {
        r.factor_id: r.metric_value
        for r in list_proxy_weight_results(session, str(est.run.run_id), acting_tenant=t)
        if r.metric_type == METRIC_TYPE_WEIGHT
    }
    assert set(weights) == {f_mkt, f_rates}

    # 4. Promote both betas into the widened ENT-019 (the :356 gate now admits MARKET/RATES).
    for fid in (f_mkt, f_rates):
        promoted = promote_proxy_weight_estimate(
            session,
            private_instrument_id=inst,
            factor_id=fid,
            weight=weights[fid],
            acting_tenant=t,
            actor=ProxyMappingActor(actor_id="analyst"),
            source_calculation_run_id=str(est.run.run_id),
        )
        assert promoted.mapping_method == "REGRESSION"
    session.flush()
    rows = (
        session.execute(
            select(ProxyMapping).where(
                ProxyMapping.tenant_id == t,
                ProxyMapping.private_instrument_id == inst,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert {r.factor_id: r.weight for r in rows} == weights  # byte-equal to the estimate rows
