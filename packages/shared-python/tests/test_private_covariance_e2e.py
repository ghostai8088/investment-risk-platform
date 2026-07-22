"""End-to-end SQLite tests for PPF-2 — the private-factor covariance block Ω_pp
(``risk.covariance.private``, the 19th governed number, §2.1 arc slice 2).

Proves the number COMPUTES end-to-end over the REAL substrate: two PRIVATE segments each carry a
full PPF-1 pure-private run (a desmoothing run + a promoted REGRESSION blend + a MANUAL membership)
over a SHARED quarterly appraisal grid, then ``run_private_covariance`` estimates Ω_pp over their
common periods. The matrix is cross-checked against an independent ``numpy.cov(ddof=1)`` on the two
pure-private series (numpy is TEST-ONLY). The public/private isolation is proven BOTH directions
(neither family leaks through the other's shared-table reads). RLS lives in the PG suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_proxy_mapping,
    resolve_factor,
)
from irp_shared.perf import DesmoothedReturnActor, register_desmoothed_return_model
from irp_shared.perf.desmoothing_service import run_desmoothed_return
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_PURE_PRIVATE_PERIOD,
    CovarianceActor,
    PrivateCovarianceInputError,
    PrivateCovarianceNotVisible,
    ProxyWeightEstimateActor,
    PurePrivateCovarianceActor,
    PurePrivateFactorActor,
    latest_covariances,
    latest_private_covariances,
    list_private_covariances,
    promote_proxy_weight_estimate,
    register_covariance_model,
    register_private_covariance_model,
    register_proxy_weight_regression_model,
    register_pure_private_factor_model,
    resolve_covariance,
    resolve_private_covariance,
    run_private_covariance,
    run_proxy_weight_estimate,
    run_pure_private_factor_return,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_T0 = datetime(2024, 6, 1, tzinfo=UTC)
_MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
_MARK_VALUES = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")
_WINDOW = (date(2024, 6, 1), date(2026, 1, 1))
_W_USD, _W_EUR = Decimal("0.6"), Decimal("0.3")
# Two distinct blend-return sets → two distinct pure-private series over the SAME 5 periods.
_SEG_A_USD = ["0.010", "0.020", "-0.010", "0.030", "0.000"]
_SEG_A_EUR = ["0.020", "-0.010", "0.010", "0.000", "0.020"]
_SEG_B_USD = ["0.005", "0.015", "0.020", "-0.005", "0.010"]
_SEG_B_EUR = ["-0.010", "0.010", "0.000", "0.015", "-0.005"]


def _currency(db: Session, code: str = "USD") -> None:
    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=_T0))
        db.flush()


def _desmoothed_run(db: Session, tenant: str) -> tuple[str, str]:
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
    for d, v in zip(_MARK_DATES, _MARK_VALUES, strict=True):
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
        window_start=_WINDOW[0],
        window_end=_WINDOW[1],
    )
    assert out.status == "COMPLETED"
    return str(out.run.run_id), inst


def _factor_with_returns(db: Session, tenant: str, code: str, values: list[str]) -> str:
    fid = capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    factor = resolve_factor(db, fid, acting_tenant=tenant)
    for d, v in zip(_MARK_DATES[1:], values, strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        )
    db.flush()
    return fid


def _pure_private_segment(
    db: Session, tenant: str, ppf_model_id: str, *, usd: list[str], eur: list[str]
) -> str:
    """Run the full PPF-1 chain for one PRIVATE segment (a member with a promoted {USD,EUR}
    REGRESSION blend + a MANUAL membership) and return the segment factor id."""
    desmoothed_run, inst = _desmoothed_run(db, tenant)
    fx_usd = _factor_with_returns(db, tenant, f"FX_USD-{uuid.uuid4().hex[:4]}", usd)
    fx_eur = _factor_with_returns(db, tenant, f"FX_EUR-{uuid.uuid4().hex[:4]}", eur)
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
        desmoothed_run_id=desmoothed_run,
        factor_ids=[fx_usd, fx_eur],
    )
    for fid, w in ((fx_usd, _W_USD), (fx_eur, _W_EUR)):
        promote_proxy_weight_estimate(
            db,
            private_instrument_id=inst,
            factor_id=fid,
            weight=w,
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            source_calculation_run_id=str(est.run.run_id),
        )
    seg = capture_factor(
        db,
        factor_code=f"SEG-{uuid.uuid4().hex[:6]}",
        factor_source="PPF",
        factor_family="PRIVATE",
        frequency="APPRAISAL",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    capture_proxy_mapping(
        db,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=_T0,
    )
    out = run_pure_private_factor_return(
        db,
        acting_tenant=tenant,
        actor=PurePrivateFactorActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(ppf_model_id),
        segment_factor_id=seg,
        member_desmoothed_run_ids=[desmoothed_run],
    )
    assert out.status == "COMPLETED"
    return str(seg)


def _series(db: Session, tenant: str, seg_id: str) -> list[Decimal]:
    """The segment's pure-private PERIOD values, chronological (the covariance input series)."""
    from irp_shared.risk import latest_pure_private_factor_for_segment

    rows = latest_pure_private_factor_for_segment(
        db, acting_tenant=tenant, segment_factor_id=seg_id
    )
    period = sorted(
        (r for r in rows if r.metric_type == METRIC_TYPE_PURE_PRIVATE_PERIOD),
        key=lambda r: r.period_end,
    )
    return [r.metric_value for r in period]


def _ppf_model(db: Session, tenant: str) -> str:
    return str(
        register_pure_private_factor_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", min_members=1
        ).id
    )


def _priv_cov_model(db: Session, tenant: str, window: int = 4) -> str:
    return str(
        register_private_covariance_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", window_observations=window
        ).id
    )


def _run_two_segment_omega(db: Session, tenant: str) -> tuple[str, str, str]:
    """Two PRIVATE segments on the shared grid → one Ω_pp run. Returns (seg_a, seg_b, run_id)."""
    ppf = _ppf_model(db, tenant)
    seg_a = _pure_private_segment(db, tenant, ppf, usd=_SEG_A_USD, eur=_SEG_A_EUR)
    seg_b = _pure_private_segment(db, tenant, ppf, usd=_SEG_B_USD, eur=_SEG_B_EUR)
    out = run_private_covariance(
        db,
        acting_tenant=tenant,
        actor=PurePrivateCovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_priv_cov_model(db, tenant, window=4),
        segment_factor_ids=[seg_a, seg_b],
    )
    assert out.status == "COMPLETED", out.failure_reason
    return seg_a, seg_b, str(out.run.run_id)


# ---------- (1) positive correctness (full stack + independent numpy cross-check) ----------
def test_omega_pp_matches_numpy_cov(session: Session) -> None:
    import numpy as np

    tenant = str(uuid.uuid4())
    seg_a, seg_b, run_id = _run_two_segment_omega(session, tenant)

    rows = list_private_covariances(session, run_id=run_id, acting_tenant=tenant)
    assert len(rows) == 3  # K*(K+1)/2 for K=2 — the full matrix, canonical unordered pairs
    assert all(r.frequency == "APPRAISAL" and r.statistic_type == "COVARIANCE" for r in rows)
    assert all(r.return_type == "SIMPLE" and r.n_observations == 4 for r in rows)
    # canonical pair order (factor_id_1 <= factor_id_2, lowercase)
    assert all(r.factor_id_1 <= r.factor_id_2 for r in rows)

    a = np.array([float(v) for v in _series(session, tenant, seg_a)])
    b = np.array([float(v) for v in _series(session, tenant, seg_b)])
    assert len(a) == len(b) == 4  # 6 marks → 5 observed → 4 desmoothed periods (Geltner drops 1st)
    expected = np.cov(np.vstack([a, b]), ddof=1)  # 2x2 sample covariance
    a_id, b_id = str(seg_a).lower(), str(seg_b).lower()
    by_pair = {(r.factor_id_1, r.factor_id_2): float(r.covariance_value) for r in rows}
    lo, hi = (a_id, b_id) if a_id <= b_id else (b_id, a_id)
    var_a = by_pair[(a_id, a_id)]
    var_b = by_pair[(b_id, b_id)]
    cov_ab = by_pair[(lo, hi)]
    assert var_a == pytest.approx(expected[0, 0], rel=1e-9, abs=1e-15)
    assert var_b == pytest.approx(expected[1, 1], rel=1e-9, abs=1e-15)
    assert cov_ab == pytest.approx(expected[0, 1], rel=1e-9, abs=1e-15)


def test_omega_pp_is_reproducible(session: Session) -> None:
    """Byte-identical Ω on re-run (kernel determinism over the pinned series)."""
    tenant = str(uuid.uuid4())
    seg_a, seg_b, run_id = _run_two_segment_omega(session, tenant)
    first = {
        (r.factor_id_1, r.factor_id_2): r.covariance_value
        for r in list_private_covariances(session, run_id=run_id, acting_tenant=tenant)
    }
    out2 = run_private_covariance(
        session,
        acting_tenant=tenant,
        actor=PurePrivateCovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_priv_cov_model(session, tenant, window=4),
        segment_factor_ids=[seg_a, seg_b],
    )
    rows2 = list_private_covariances(session, run_id=str(out2.run.run_id), acting_tenant=tenant)
    second = {(r.factor_id_1, r.factor_id_2): r.covariance_value for r in rows2}
    assert first == second


# ---------- (1b) snapshot pin reproducibility: verify_snapshot + consume==build (AD-014/TR-09) ----
def _latest_pp_run(session: Session, tenant: str, seg_id: str) -> str:
    from irp_shared.risk import latest_pure_private_factor_for_segment

    rows = latest_pure_private_factor_for_segment(
        session, acting_tenant=tenant, segment_factor_id=seg_id
    )
    return str(rows[0].calculation_run_id)


def test_omega_pp_snapshot_verifies_and_consume_equals_build(session: Session) -> None:
    """The AD-014 reproducibility contract: a PRIVATE_COVARIANCE_INPUT snapshot re-resolves
    byte-identically (verify_snapshot ok), and the consume-existing path (snapshot_id) yields the
    IDENTICAL matrix as build-in-request (the covariance leg-4 twin — the previously untested
    consume branch)."""
    from irp_shared.snapshot import (
        SnapshotActor,
        build_private_covariance_snapshot,
        verify_snapshot,
    )

    tenant = str(uuid.uuid4())
    ppf = _ppf_model(session, tenant)
    seg_a = _pure_private_segment(session, tenant, ppf, usd=_SEG_A_USD, eur=_SEG_A_EUR)
    seg_b = _pure_private_segment(session, tenant, ppf, usd=_SEG_B_USD, eur=_SEG_B_EUR)
    run_a, run_b = _latest_pp_run(session, tenant, seg_a), _latest_pp_run(session, tenant, seg_b)

    snap = build_private_covariance_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        pure_private_run_ids=[run_a, run_b],
        window_observations=4,
    )
    session.flush()
    # The pinned PURE_PRIVATE_RETURN + FACTOR components re-resolve byte-identically.
    assert verify_snapshot(session, snapshot_id=str(snap.id), acting_tenant=tenant).ok

    mv = _priv_cov_model(session, tenant, window=4)
    consumed = run_private_covariance(
        session,
        acting_tenant=tenant,
        actor=PurePrivateCovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=mv,
        snapshot_id=str(snap.id),
    )
    assert consumed.status == "COMPLETED", consumed.failure_reason
    built = run_private_covariance(
        session,
        acting_tenant=tenant,
        actor=PurePrivateCovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=mv,
        segment_factor_ids=[seg_a, seg_b],
    )
    cmap = {(r.factor_id_1, r.factor_id_2): r.covariance_value for r in consumed.rows}
    bmap = {(r.factor_id_1, r.factor_id_2): r.covariance_value for r in built.rows}
    assert len(cmap) == 3 and cmap == bmap  # consume-existing == build-in-request, byte-identical


def test_omega_pp_snapshot_verify_reports_drift_not_500(session: Session) -> None:
    """A gone pinned pure-private row reports as DRIFT (ok False), NEVER an uncaught
    PrivateCovarianceSnapshotError (a raw 500) — the review fold adding it to verify_snapshot's
    except tuple. SQLite has no append-only trigger (PG-only), so a Core delete legitimately makes a
    pinned target gone for this drift probe."""
    from sqlalchemy import delete

    from irp_shared.snapshot import (
        SnapshotActor,
        build_private_covariance_snapshot,
        verify_snapshot,
    )

    tenant = str(uuid.uuid4())
    ppf = _ppf_model(session, tenant)
    seg_a = _pure_private_segment(session, tenant, ppf, usd=_SEG_A_USD, eur=_SEG_A_EUR)
    seg_b = _pure_private_segment(session, tenant, ppf, usd=_SEG_B_USD, eur=_SEG_B_EUR)
    run_a, run_b = _latest_pp_run(session, tenant, seg_a), _latest_pp_run(session, tenant, seg_b)
    snap = build_private_covariance_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        pure_private_run_ids=[run_a, run_b],
        window_observations=4,
    )
    session.flush()
    # Make one segment's pinned pure-private rows gone (a Core delete bypasses the ORM guard here).
    from irp_shared.risk.models import PrivateFactorReturnResult

    session.execute(
        delete(PrivateFactorReturnResult).where(
            PrivateFactorReturnResult.calculation_run_id == run_a
        )
    )
    session.flush()
    result = verify_snapshot(session, snapshot_id=str(snap.id), acting_tenant=tenant)
    assert result.ok is False  # reported as drift, not a raw 500


# ---------- (2) public/private isolation over the shared covariance_result table ----------
def test_private_run_never_leaks_into_public_reads(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _seg_a, _seg_b, run_id = _run_two_segment_omega(session, tenant)
    priv_rows = list_private_covariances(session, run_id=run_id, acting_tenant=tenant)

    # The public latest-resolver must NOT surface the private matrix (there is no public run).
    assert latest_covariances(session, acting_tenant=tenant) == []
    # The private latest-resolver DOES surface it (same rows, run_type-filtered).
    latest_priv = latest_private_covariances(session, acting_tenant=tenant)
    assert {r.id for r in latest_priv} == {r.id for r in priv_rows}
    # A private row is NOT resolvable through the PUBLIC by-id surface (the step-1 filter) ...
    for r in priv_rows:
        with pytest.raises(PrivateCovarianceNotVisible):
            resolve_private_covariance(session, str(uuid.uuid4()), acting_tenant=tenant)  # unknown
        from irp_shared.risk import CovarianceNotVisible

        with pytest.raises(CovarianceNotVisible):
            resolve_covariance(session, str(r.id), acting_tenant=tenant)
        # ... but IS resolvable through the private by-id surface.
        assert resolve_private_covariance(session, str(r.id), acting_tenant=tenant).id == r.id


def test_public_run_never_leaks_into_private_reads(session: Session) -> None:
    tenant = str(uuid.uuid4())
    # A PUBLIC covariance run over two DAILY factors.
    fx_usd = _factor_with_returns(session, tenant, f"FX_USD-{uuid.uuid4().hex[:4]}", _SEG_A_USD)
    fx_eur = _factor_with_returns(session, tenant, f"FX_EUR-{uuid.uuid4().hex[:4]}", _SEG_A_EUR)
    from irp_shared.risk import run_covariance

    pub = run_covariance(
        session,
        acting_tenant=tenant,
        actor=CovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(
            register_covariance_model(
                session, tenant_id=tenant, actor_id="s", code_version="v1", window_observations=5
            ).id
        ),
        factor_ids=[fx_usd, fx_eur],
    )
    assert pub.status == "COMPLETED"
    # The PRIVATE latest-resolver must NOT surface the public matrix (there is no private run).
    assert latest_private_covariances(session, acting_tenant=tenant) == []
    # A public row is NOT resolvable through the PRIVATE by-id surface.
    for r in pub.rows:
        with pytest.raises(PrivateCovarianceNotVisible):
            resolve_private_covariance(session, str(r.id), acting_tenant=tenant)


# ---------- (3) fail-closed refusals ----------
def test_single_segment_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    seg = _pure_private_segment(
        session, tenant, _ppf_model(session, tenant), usd=_SEG_A_USD, eur=_SEG_A_EUR
    )
    with pytest.raises(PrivateCovarianceInputError, match=">= 2 segments"):
        run_private_covariance(
            session,
            acting_tenant=tenant,
            actor=PurePrivateCovarianceActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=_priv_cov_model(session, tenant, window=5),
            segment_factor_ids=[seg],
        )


def test_segment_with_no_pure_private_run_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    seg_a = _pure_private_segment(
        session, tenant, _ppf_model(session, tenant), usd=_SEG_A_USD, eur=_SEG_A_EUR
    )
    # A second PRIVATE segment that never had a pure-private run.
    seg_b = capture_factor(
        session,
        factor_code=f"SEG-{uuid.uuid4().hex[:6]}",
        factor_source="PPF",
        factor_family="PRIVATE",
        frequency="APPRAISAL",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    with pytest.raises(PrivateCovarianceInputError, match="no COMPLETED pure-private"):
        run_private_covariance(
            session,
            acting_tenant=tenant,
            actor=PurePrivateCovarianceActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=_priv_cov_model(session, tenant, window=5),
            segment_factor_ids=[seg_a, seg_b],
        )


def test_window_mismatch_refused_when_declared_exceeds_common(session: Session) -> None:
    """A model declaring window=6 over segments with only 5 common periods fails closed (409)."""
    from irp_shared.snapshot import PrivateCovarianceSnapshotError

    tenant = str(uuid.uuid4())
    ppf = _ppf_model(session, tenant)
    seg_a = _pure_private_segment(session, tenant, ppf, usd=_SEG_A_USD, eur=_SEG_A_EUR)
    seg_b = _pure_private_segment(session, tenant, ppf, usd=_SEG_B_USD, eur=_SEG_B_EUR)
    with pytest.raises(PrivateCovarianceSnapshotError, match="common appraisal periods"):
        run_private_covariance(
            session,
            acting_tenant=tenant,
            actor=PurePrivateCovarianceActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=_priv_cov_model(session, tenant, window=6),
            segment_factor_ids=[seg_a, seg_b],
        )
