"""VAR-HS-1 historical-simulation VaR: kernel exactness (hand-computed order statistics),
registrar identity/floor contracts, and the governed chain on BOTH entry paths (build +
consume), incl. pin invariance and the fail-closed adjudication probes.

Hand-reference design (dual-path, the numerical_quant_standards rule): exposures x = (30000
USD-factor, 40000 EUR-factor), returns a_i = i/1000 and b_i = -i/1000 on date_i ⇒ scenario
P&L_i = 30000·a_i - 40000·b_i·(-1) = -10·i EXACTLY (integers) — the order statistics are
knowable by inspection: N=21, c=0.95 ⇒ k=2 ⇒ VaR = 200 (2nd worst); N=40 ⇒ k=2 ⇒ VaR = 390.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_var import session  # noqa: F401 - the shared in-memory session fixture

from irp_shared.calc.models import CalculationRun
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FactorExposureActor,
    HsVarInputError,
    HsVarKernelError,
    ModelVersionConflictError,
    VarActor,
    WrongModelVersionError,
    compute_historical_var,
    order_statistic_index,
    register_factor_exposure_model,
    register_historical_var_model,
    register_var_model,
    run_factor_exposure,
    run_var_historical,
)
from irp_shared.snapshot import (
    PURPOSE_VAR_HS_INPUT,
    PURPOSE_VAR_INPUT,
    SnapshotActor,
    VarSnapshotError,
    build_var_hs_snapshot,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VA = datetime(2026, 6, 1, tzinfo=UTC)
KA = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
ACTOR = VarActor(actor_id="analyst")


# ---------- (1) kernel exactness (pure; no floor constraint) ----------


def _series(values: dict[int, str], fid: str = "f") -> dict[date, dict[str, Decimal]]:
    base = date(2026, 5, 1)
    return {base + timedelta(days=i): {fid: Decimal(v)} for i, v in values.items()}


def test_order_statistic_index_hand_cases() -> None:
    assert order_statistic_index(250, Decimal("0.99")) == 3  # the Basel-era "3rd worst of 250"
    assert order_statistic_index(100, Decimal("0.95")) == 5
    assert order_statistic_index(20, Decimal("0.95")) == 1
    assert order_statistic_index(40, Decimal("0.95")) == 2
    assert order_statistic_index(101, Decimal("0.99")) == 2  # ceil(1.01)
    with pytest.raises(HsVarKernelError):
        order_statistic_index(10, Decimal("1"))
    with pytest.raises(HsVarKernelError):
        order_statistic_index(10, Decimal("0"))


def test_kernel_hand_reference_and_sign_convention() -> None:
    # 5 scenarios, single factor, x=100: P&Ls = -50, -20, 10, 30, 40.
    returns = _series({0: "-0.50", 1: "-0.20", 2: "0.10", 3: "0.30", 4: "0.40"})
    est = compute_historical_var({"f": Decimal(100)}, returns, confidence=Decimal("0.80"))
    # k = ceil(5*0.2) = 1 -> worst P&L -50 -> VaR = +50 (loss positive).
    assert (est.k, est.n_observations) == (1, 5)
    assert est.var_value == Decimal("50.000000")
    # c=0.60 -> k = ceil(2) = 2 -> 2nd worst -20 -> VaR = 20.
    est2 = compute_historical_var({"f": Decimal(100)}, returns, confidence=Decimal("0.60"))
    assert (est2.k, est2.var_value) == (2, Decimal("20.000000"))


def test_kernel_negative_var_reported_honestly() -> None:
    # Every scenario gains: the k-th 'worst' is still a gain -> VaR NEGATIVE, never clamped.
    returns = _series({0: "0.01", 1: "0.02", 2: "0.03", 3: "0.04"})
    est = compute_historical_var({"f": Decimal(1000)}, returns, confidence=Decimal("0.75"))
    assert est.var_value == Decimal("-10.000000")  # k=1, worst P&L +10


def test_kernel_multi_factor_aggregation_and_ties() -> None:
    base = date(2026, 5, 1)
    returns = {
        base: {"a": Decimal("-0.01"), "b": Decimal("0.01")},  # P&L = -100+50 = -50
        base + timedelta(days=1): {"a": Decimal("-0.005"), "b": Decimal("-0.005")},  # -75
        base + timedelta(days=2): {"a": Decimal("-0.0125"), "b": Decimal("0.01")},  # -75 (tie)
        base + timedelta(days=3): {"a": Decimal("0.01"), "b": Decimal("0.01")},  # 150
    }
    x = {"a": Decimal(10000), "b": Decimal(5000)}
    est = compute_historical_var(x, returns, confidence=Decimal("0.60"))
    # k = ceil(4*0.4) = 2; sorted P&Ls: -75, -75, -50, 150 -> 2nd = -75 (tie determinism).
    assert (est.k, est.var_value) == (2, Decimal("75.000000"))


def test_kernel_ill_formed_inputs_raise() -> None:
    with pytest.raises(HsVarKernelError):
        compute_historical_var({}, _series({0: "0.01"}), confidence=Decimal("0.95"))
    with pytest.raises(HsVarKernelError):
        compute_historical_var({"f": Decimal(1)}, {}, confidence=Decimal("0.95"))
    with pytest.raises(HsVarKernelError):  # coverage precondition re-verified in the kernel
        compute_historical_var({"g": Decimal(1)}, _series({0: "0.01"}), confidence=Decimal("0.95"))


# ---------- (2) registrar identity / floor contracts ----------


def test_register_declared_identity_floor_and_conflicts(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    assert mv.status == "REGISTERED"
    # Idempotent same-declaration return.
    again = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    assert again.id == mv.id
    # Same-label different-declaration -> 409 class.
    with pytest.raises(ModelVersionConflictError):
        register_historical_var_model(
            session,
            tenant_id=tenant,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=40,
        )
    # The adequacy floor (OD-VHS-E as TIGHTENED at review: k >= 2 requires N > 1/(1-c) —
    # the ratified ceil() formula still gave k=1 at every integral boundary): c=0.99 needs
    # N >= 101; c=0.95 needs N >= 21.
    t2 = str(uuid.uuid4())
    for conf, bad_n in (("0.99", 100), ("0.99", 99), ("0.95", 20), ("0.95", 19)):
        with pytest.raises(ValueError):
            register_historical_var_model(
                session,
                tenant_id=t2,
                actor_id="a",
                code_version="v1",
                confidence_level=conf,
                window_observations=bad_n,
            )
    ok = register_historical_var_model(
        session,
        tenant_id=t2,
        actor_id="a",
        code_version="v1",
        confidence_level="0.99",
        window_observations=101,
    )
    assert ok.status == "REGISTERED"
    # Out-of-vocabulary confidence / non-v1 horizon refused.
    with pytest.raises(ValueError):
        register_historical_var_model(
            session,
            tenant_id=t2,
            actor_id="a",
            code_version="v1",
            confidence_level="0.90",
            window_observations=21,
        )
    with pytest.raises(ValueError):
        register_historical_var_model(
            session,
            tenant_id=t2,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=21,
            horizon_days=10,
        )


# ---------- (3) the governed chain ----------


def _seed_chain(db: Session, tenant: str, n_dates: int) -> str:
    """Portfolio (30000 USD-factor + 40000 EUR-factor exposure, base USD) -> a COMPLETED
    factor-exposure run; factor returns a_i=i/1000, b_i=-i/1000 on n_dates dates ⇒ scenario
    P&L_i = -10·i exactly. Returns the factor-exposure run id."""
    for code in ("USD", "EUR"):
        exists = db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        if exists is None:
            db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"A-{uuid.uuid4().hex[:6]}",
        name="a",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
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
    capture_fx_rate(
        db,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=VD,
        rate=Decimal("1.000000000000"),
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
        as_of_valid_at=VA,
        as_of_known_at=KA,
        base_currency="USD",
    )
    factor_ids: list[str] = []
    base_day = date(2026, 4, 1)
    for code, ccy, sign in (("FX_USD", "USD", 1), ("FX_EUR", "EUR", -1)):
        fid = capture_factor(
            db,
            factor_code=f"{code}-{uuid.uuid4().hex[:6]}",
            factor_source="V",
            factor_family="CURRENCY",
            currency_code=ccy,
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        ).id
        factor = resolve_factor(db, fid, acting_tenant=tenant)
        for i in range(1, n_dates + 1):
            capture_factor_return(
                db,
                factor,
                return_date=base_day + timedelta(days=i),
                return_value=Decimal(sign * i) / Decimal(1000),
                acting_tenant=tenant,
                actor=FactorActor(actor_id="s"),
                valid_from=T0,
            )
        factor_ids.append(fid)
    fx_mv = register_factor_exposure_model(db, tenant_id=tenant, actor_id="a", code_version="v1")
    fx_run = run_factor_exposure(
        db,
        acting_tenant=tenant,
        actor=FactorExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=fx_mv.id,
        exposure_run_id=exposure.run.run_id,
        factor_ids=factor_ids,
    )
    assert fx_run.status == "COMPLETED"
    return fx_run.run.run_id


def _hs_run(db: Session, tenant: str, mv: str, **kw):  # noqa: ANN202
    return run_var_historical(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        model_version_id=str(mv),
        **kw,
    )


def test_full_stack_build_path_hand_reference_n21(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    result = _hs_run(session, tenant, mv.id, exposure_run_id=fx_run)
    assert result.status == "COMPLETED"
    (row,) = result.rows
    # P&L_i = -10*i for i=1..21; k = ceil(21*0.05) = 2 -> 2nd worst = -200 -> VaR = 200.
    assert row.var_value == Decimal("200.000000")
    assert row.metric_type == "VAR_HISTORICAL"
    assert row.z_score is None and row.sigma is None and row.covariance_run_id is None
    assert row.exposure_run_id == fx_run
    assert (row.n_factors, row.n_observations) == (2, 21)
    assert row.base_currency == "USD"


def test_full_stack_k2_order_statistic_n40(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=40)
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=40,
    )
    result = _hs_run(session, tenant, mv.id, exposure_run_id=fx_run)
    (row,) = result.rows
    # k = ceil(40*0.05) = 2 -> 2nd worst P&L = -390 -> VaR = 390 (NOT the worst, 400).
    assert row.var_value == Decimal("390.000000")


def test_consume_path_equals_build_and_pin_invariance(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    snapshot = build_var_hs_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        exposure_run_id=fx_run,
        window_observations=21,
    )
    assert snapshot.purpose == PURPOSE_VAR_HS_INPUT
    first = _hs_run(session, tenant, mv.id, snapshot_id=snapshot.id)
    assert first.rows[0].var_value == Decimal("200.000000")
    # Pin invariance (NON-VACUOUS): a later return correction moves a FRESH build but the pinned
    # snapshot re-run reproduces the ORIGINAL number exactly.
    factor_id = None
    from irp_shared.marketdata.models import FactorReturn  # local, models-only

    worst_day = date(2026, 4, 1) + timedelta(days=21)
    rows = (
        session.execute(
            select(FactorReturn).where(
                FactorReturn.tenant_id == tenant, FactorReturn.return_date == worst_day
            )
        )
        .scalars()
        .all()
    )
    assert rows
    from irp_shared.marketdata.factor import correct_factor_return

    for r in rows:
        factor = resolve_factor(session, r.factor_id, acting_tenant=tenant)
        correct_factor_return(
            session,
            factor,
            return_date=worst_day,
            return_value=Decimal("0.5"),
            restatement_reason="test restatement",
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
        )
        factor_id = r.factor_id
    assert factor_id is not None
    # NON-VACUITY (review fold): the correction must MOVE a fresh build — day-21's P&L flips
    # from -210 to +35000 (0.5×30000 + 0.5×40000), so the fresh window's k=2 lands on -190.
    fresh = _hs_run(session, tenant, mv.id, exposure_run_id=fx_run)
    assert fresh.rows[0].var_value == Decimal("190.000000")
    again = _hs_run(session, tenant, mv.id, snapshot_id=snapshot.id)
    assert again.rows[0].var_value == Decimal("200.000000")  # the pin is immutable


def test_refusals_zero_run_and_wrong_model_and_both_modes(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )

    def runs() -> int:
        return session.execute(
            select(func.count())
            .select_from(CalculationRun)
            .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
        ).scalar_one()

    before = runs()
    # Both modes -> ambiguity refusal.
    with pytest.raises(HsVarInputError):
        _hs_run(session, tenant, mv.id, exposure_run_id=fx_run, snapshot_id=str(uuid.uuid4()))
    # Missing build arg.
    with pytest.raises(HsVarInputError):
        _hs_run(session, tenant, mv.id)
    # A PARAMETRIC model version cannot drive a historical run (family identity).
    pmv = register_var_model(
        session, tenant_id=tenant, actor_id="a", code_version="v1", confidence_level="0.95"
    )
    with pytest.raises(WrongModelVersionError):
        _hs_run(session, tenant, pmv.id, exposure_run_id=fx_run)
    assert runs() == before  # ZERO runs created by any refusal above


def test_short_window_snapshot_and_declared_mismatch_refused(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=25)
    # Builder floor: fewer common dates than requested -> fail closed (TYPED: the governed 409).
    with pytest.raises(VarSnapshotError) as exc_info:
        build_var_hs_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            window_observations=30,
        )
    assert "common return dates" in str(exc_info.value)
    # Declared-window mismatch: model declares 20, snapshot pins 25 -> pre-create refusal.
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    snapshot = build_var_hs_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        exposure_run_id=fx_run,
        window_observations=25,
    )
    with pytest.raises(HsVarInputError) as ref:
        _hs_run(session, tenant, mv.id, snapshot_id=snapshot.id)
    assert "declares 21" in str(ref.value)


def test_result_row_is_append_only(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    result = _hs_run(session, tenant, mv.id, exposure_run_id=fx_run)
    (row,) = result.rows
    from irp_shared.audit.models import AppendOnlyViolation

    row.var_value = Decimal("1")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


# ---------- (4) hand-minted adjudication probes + provenance + FAILED (review folds) ----------

from types import SimpleNamespace  # noqa: E402

from irp_shared.snapshot import (  # noqa: E402
    COMPONENT_KIND_FACTOR_EXPOSURE,
    COMPONENT_KIND_FACTOR_RETURN,
)


def _mint_hs_snapshot(
    db: Session,
    tenant: str,
    exposure_rows: list[dict],
    windows: list[dict],
    purpose: str = PURPOSE_VAR_HS_INPUT,
):  # noqa: ANN202
    """Hand-mint a VAR_HS_INPUT snapshot with ARBITRARY pinned content (bypassing the governed
    builder) — the adjudication-gate probe vehicle (the test_var precedent)."""
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    specs: list = []
    for content in exposure_rows:
        content = dict(content)
        # "_anchor" decouples the component target id from the captured content id — the
        # duplicate-content smuggle vector (distinct components, identical pinned row).
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        _append_spec(
            specs, COMPONENT_KIND_FACTOR_EXPOSURE, "factor_exposure_result", anchor, content
        )
    for content in windows:
        content = dict(content)
        anchor_id = content.pop("_anchor", None) or content["factor_id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        _append_spec(specs, COMPONENT_KIND_FACTOR_RETURN, "factor", anchor, content)
    header = _persist_snapshot(
        db,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=purpose,
        as_of_valid_at=VA,
        as_of_known_at=VA,
        as_of_valuation_date=VD,
        binding_predicate_version="test:hand-minted",
    )
    db.flush()
    return header


def _exp(run_id: str, fid: str, amount: str, base: str = "USD", code: str = "FX_X") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "calculation_run_id": run_id,
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": str(uuid.uuid4()),
        "factor_id": fid,
        "factor_code": code,
        "factor_family": "CURRENCY",
        "base_currency": base,
        "mark_currency": base,
        "loading": "1.000000000000",
        "exposure_amount": amount,
    }


def _win(
    fid: str, values: list[str], rtype: str = "SIMPLE", freq: str = "DAILY", start_day: int = 1
) -> dict:
    base_day = date(2026, 4, 1)
    return {
        "factor_id": fid,
        "factor_code": "FX_X",
        "factor_source": "V",
        "return_type": rtype,
        "frequency": freq,
        "rows": [
            {
                "id": str(uuid.uuid4()),
                "return_date": (base_day + timedelta(days=start_day + i)).isoformat(),
                "return_type": rtype,
                "return_value": v,
                "valid_from": "2026-01-01T00:00:00+00:00",
                "system_from": "2026-01-01T00:00:00+00:00",
                "record_version": 1,
            }
            for i, v in enumerate(values)
        ],
    }


def _mv21(db: Session, tenant: str):  # noqa: ANN202
    return register_historical_var_model(
        db,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )


V21 = ["0.001"] * 21  # a well-formed 21-obs window


def test_adjudication_gate_probes(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    mv = _mv21(session, tenant)
    run_id = str(uuid.uuid4())
    f1, f2 = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()

    def probe(exposures: list[dict], windows: list[dict], match: str) -> None:
        snap = _mint_hs_snapshot(session, tenant, exposures, windows)
        with pytest.raises(HsVarInputError) as exc:
            _hs_run(session, tenant, mv.id, snapshot_id=snap.id)
        assert match in str(exc.value), str(exc.value)

    ok_exp = [_exp(run_id, f1, "100.000000")]
    ok_win = [_win(f1, V21)]
    probe([], ok_win, "pins no FACTOR_EXPOSURE")
    probe(ok_exp, [], "pins no FACTOR_RETURN")
    probe(
        [_exp(run_id, f1, "1"), _exp(str(uuid.uuid4()), f2, "1")],
        [_win(f1, V21), _win(f2, V21)],
        "span multiple runs",
    )
    probe(
        [_exp(run_id, f1, "1"), _exp(run_id, f2, "1", base="EUR")],
        [_win(f1, V21), _win(f2, V21)],
        "mixed base currencies",
    )
    dup = _exp(run_id, f1, "1")
    dup2 = dict(dup)
    dup2["_anchor"] = str(uuid.uuid4())  # distinct component, identical pinned row id
    probe([dup, dup2], ok_win, "duplicate pinned exposure row")
    dup_win = _win(f1, V21)
    dup_win["_anchor"] = str(uuid.uuid4())
    probe(ok_exp, [_win(f1, V21), dup_win], "duplicate pinned return window")
    probe(ok_exp, [_win(f1, V21, freq="WEEKLY")], "frequency")
    probe(ok_exp, [_win(f1, V21, rtype="LOG")], "return_type")
    probe(
        [_exp(run_id, f1, "1"), _exp(run_id, f2, "1")],
        [_win(f1, V21), _win(f2, V21, start_day=2)],
        "misaligned",
    )
    dup_date = _win(f1, V21)
    dup_date["rows"][1]["return_date"] = dup_date["rows"][0]["return_date"]
    probe(ok_exp, [dup_date], "duplicate return date")
    probe(
        [_exp(run_id, f1, "1"), _exp(run_id, f2, "1")], [_win(f1, V21)], "no pinned return window"
    )
    probe([_exp(run_id, f1, "1E23")], ok_win, "exceeds its source-column envelope")
    big = _win(f1, ["1E9"] + ["0.001"] * 20)
    probe(ok_exp, [big], "exceeds its source-column envelope")
    probe([_exp(run_id, f1, "6E21"), _exp(run_id, f1, "6E21")], ok_win, "per-factor exposure total")
    probe(ok_exp, [_win(f1, V21[:-1])], "declares 21")
    malformed = [_exp(run_id, f1, "1")]
    del malformed[0]["base_currency"]
    snap = _mint_hs_snapshot(session, tenant, malformed, ok_win)
    with pytest.raises(HsVarInputError) as exc:
        _hs_run(session, tenant, mv.id, snapshot_id=snap.id)
    assert "not a well-formed v1 input" in str(exc.value)


def test_pinned_provenance_must_resolve_own_tenant(session: Session) -> None:  # noqa: F811
    # A snapshot whose pinned content names an UNKNOWN/foreign run id passes adjudication but
    # must refuse at the own-tenant re-resolution BEFORE the hard-FK stamp (the P3-5 principal
    # finding class; probe-verified missing at review).
    from irp_shared.risk import FactorExposureRunNotVisible

    tenant = str(uuid.uuid4())
    mv = _mv21(session, tenant)
    f1 = str(uuid.uuid4()).lower()
    snap = _mint_hs_snapshot(
        session, tenant, [_exp(str(uuid.uuid4()), f1, "100.000000")], [_win(f1, V21)]
    )
    before = session.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
    ).scalar_one()
    with pytest.raises(FactorExposureRunNotVisible):
        _hs_run(session, tenant, mv.id, snapshot_id=snap.id)
    after = session.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
    ).scalar_one()
    assert after == before  # zero runs — the refusal is pre-create


def test_magnitude_gate_commits_failed_run(session: Session) -> None:  # noqa: F811
    # Column-legal-but-extreme pins (exposure 1E21 < 1E22; return -10 < 1E8) drive |VaR| past
    # Numeric(28,6): a committed FAILED run + persisted reason + ZERO rows — REACHABLE since
    # the kernel prec-50 fix (the review's dead-gate finding).
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = _mv21(session, tenant)
    f1 = str(uuid.uuid4()).lower()
    snap = _mint_hs_snapshot(session, tenant, [_exp(fx_run, f1, "1E21")], [_win(f1, ["-10"] * 21)])
    result = _hs_run(session, tenant, mv.id, snapshot_id=snap.id)
    assert result.status == "FAILED"
    assert result.rows == []
    assert result.failure_reason is not None
    assert "magnitude-out-of-range" in result.failure_reason
    run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == result.run.run_id)
    ).scalar_one()
    assert run_row.failure_reason == result.failure_reason  # persisted (P3-C1)


def test_reverse_identity_and_purpose_cross_feeds(session: Session) -> None:  # noqa: F811
    from irp_shared.risk import VarInputError, run_var

    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    hs_mv = _mv21(session, tenant)
    # An HS model_version cannot drive the PARAMETRIC binder (reverse identity).
    with pytest.raises(WrongModelVersionError):
        run_var(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            model_version_id=str(hs_mv.id),
            exposure_run_id=fx_run,
            covariance_run_id=fx_run,
        )
    # Purpose cross-feeds: a VAR_HS_INPUT snapshot refused by run_var...
    hs_snap = build_var_hs_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        exposure_run_id=fx_run,
        window_observations=21,
    )
    pmv = register_var_model(
        session, tenant_id=tenant, actor_id="a", code_version="v1", confidence_level="0.95"
    )
    with pytest.raises(VarInputError):
        run_var(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            model_version_id=str(pmv.id),
            snapshot_id=hs_snap.id,
        )
    # ... and a hand-minted VAR_INPUT-purpose snapshot refused by run_var_historical.
    f1 = str(uuid.uuid4()).lower()
    wrong_purpose = _mint_hs_snapshot(
        session, tenant, [_exp(fx_run, f1, "1")], [_win(f1, V21)], purpose=PURPOSE_VAR_INPUT
    )
    with pytest.raises(HsVarInputError) as exc:
        _hs_run(session, tenant, hs_mv.id, snapshot_id=wrong_purpose.id)
    assert "purpose" in str(exc.value)


def test_generic_mint_declared_parse_and_twin_refusals(session: Session) -> None:  # noqa: F811
    # The generic registration path can stamp ANY assumptions: every malformed/inadequate
    # declaration must refuse at BIND (WrongModelVersionError), incl. the review's
    # floor-bypass (window below the adequacy floor) and window=0 (the IndexError-500 probe).
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk.bootstrap import VAR_HS_MODEL_CODE as CODE

    tenant = str(uuid.uuid4())
    model = register_model(
        session, tenant_id=tenant, code=CODE, name="hs", model_type="VAR", actor_id="a"
    )
    cases = {
        "missing-quantile": ["confidence_level=0.9500", "horizon_days=1", "window_observations=21"],
        "floor-bypass-5": [
            "confidence_level=0.9500",
            "horizon_days=1",
            "window_observations=5",
            "quantile_convention=LOWER_ORDER_STATISTIC",
        ],
        "window-zero": [
            "confidence_level=0.9500",
            "horizon_days=1",
            "window_observations=0",
            "quantile_convention=LOWER_ORDER_STATISTIC",
        ],
        "wrong-quantile": [
            "confidence_level=0.9500",
            "horizon_days=1",
            "window_observations=21",
            "quantile_convention=HYNDMAN_FAN_7",
        ],
        "dup-confidence": [
            "confidence_level=0.9500",
            "confidence_level=0.9900",
            "horizon_days=1",
            "window_observations=21",
            "quantile_convention=LOWER_ORDER_STATISTIC",
        ],
        "unicode-window": [
            "confidence_level=0.9500",
            "horizon_days=1",
            "window_observations=²¹",
            "quantile_convention=LOWER_ORDER_STATISTIC",
        ],
    }
    for label, assumptions in cases.items():
        version = register_model_version(
            session,
            model=model,
            version_label=f"gen-{label}",
            actor_id="a",
            methodology_ref="x",
            code_version="v1",
            status="REGISTERED",
            assumptions=tuple(assumptions),
            limitations=(),
        )
        with pytest.raises(WrongModelVersionError):
            _hs_run(session, tenant, version.id, exposure_run_id=str(uuid.uuid4()))
    # The 5th registrar's non-REGISTERED same-label twin refusal (the P3-C1 contract).
    t2 = str(uuid.uuid4())
    model2 = register_model(
        session, tenant_id=t2, code=CODE, name="hs", model_type="VAR", actor_id="a"
    )
    register_model_version(
        session,
        model=model2,
        version_label="v1",
        actor_id="a",
        methodology_ref="x",
        code_version="v1",
        status=None,
        assumptions=(),
        limitations=(),
    )
    with pytest.raises(WrongModelVersionError):
        register_historical_var_model(
            session,
            tenant_id=t2,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=21,
        )
