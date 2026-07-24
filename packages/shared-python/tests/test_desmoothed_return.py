"""SQLite unit/behavior tests for PA-1 desmoothing (ENT-056, the ELEVENTH governed number).

Covers: the pure kernel (observed-return + Geltner-inversion goldens; the α=1 identity boundary;
the stdev-inflation property on a positively-autocorrelated series; domain errors); the FULL-STACK
golden over a REAL chain (portfolio -> private instrument -> quarterly appraisal marks -> a
desmoothing run) with every number hand-derived from the fixture; TR-09 BOTH sides (a post-run mark
supersede does not move the historical result; a re-run against the same snapshot reproduces
byte-identically); the pre-create refusal battery (short series, mixed currency, ambiguous input,
unregistered model, out-of-domain alpha) with NO RUNNING orphan; the adjudication unit gates
(duplicate dates, non-positive marks); and the append-only / run_type!=metric / zero-PERF.*-audit /
migration-head guards. PG legs live in test_desmoothed_return_pg.py.

Golden derivation (TD-1-realistic: a private-equity fund's quarterly appraised unit NAVs, alpha=0.4
— a typical appraisal-smoothing speed-of-adjustment):
  marks 100.00 (Q3-25) -> 102.00 (Q4-25) -> 104.55 (Q1-26) -> 103.5045 (Q2-26)
  observed r = [102/100-1, 104.55/102-1, 103.5045/104.55-1] = [0.02, 0.025, -0.01]  (exact)
  desmoothed (alpha=0.4): d2 = (0.025 - 0.6*0.02)/0.4  = 0.013/0.4  =  0.0325
                          d3 = (-0.01 - 0.6*0.025)/0.4 = -0.025/0.4 = -0.0625
  summary (n=2, sample n-1): desmoothed stdev = 0.0475*sqrt(2) = 0.067175144213 (12dp HALF_UP)
                             observed  stdev = 0.0175*sqrt(2) = 0.024748737342 (12dp HALF_UP)
  the honest-uncertainty statement: 0.0672 >> 0.0247 — the smoothed series understated volatility.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from run_assertions import assert_no_running_orphan
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.model.service import UnregisteredModelError
from irp_shared.models import Base
from irp_shared.perf import (
    METRIC_TYPE_DESMOOTHED_PERIOD,
    METRIC_TYPE_DESMOOTHING_SUMMARY,
    RUN_TYPE_DESMOOTHED_RETURN,
    DesmoothedReturnActor,
    DesmoothingInputError,
    DesmoothingKernelError,
    desmooth_geltner,
    observed_returns,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.perf.desmoothing_service import _adjudicate_pins
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import DesmoothingSnapshotError, verify_snapshot
from irp_shared.valuation import create_valuation, supersede_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2025, 9, 1, tzinfo=UTC)
ACT = DesmoothedReturnActor(actor_id="analyst")
#: The quarterly appraisal dates + marks of the golden (see the module docstring derivation).
MARK_DATES = (date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30))
MARK_VALUES = ("100.00", "102.00", "104.55", "103.5045")
WINDOW = (date(2025, 9, 1), date(2026, 7, 1))


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


def _seed_marks(
    db: Session,
    tenant: str,
    values: tuple[str, ...] = MARK_VALUES,
    dates: tuple[date, ...] = MARK_DATES,
    currency: str = "USD",
) -> tuple[str, str]:
    """Seed a private-equity instrument in a portfolio with the quarterly appraisal marks.
    Returns (portfolio_id, instrument_id)."""
    if (
        db.execute(
            select(Currency).where(
                Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == currency
            )
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=currency, name=currency, valid_from=T0))
        db.flush()
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="private book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"PE-FUND-{uuid.uuid4().hex[:6]}",
        name="Buyout Fund IV",
        asset_class="PRIVATE_EQUITY",  # the PA-0 documented convention
        actor=ReferenceActor(actor_id="s"),
    ).id
    for d, v in zip(dates, values, strict=True):
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code=currency,
            valid_from=T0,
        )
    db.flush()
    return pf, inst


def _run(db: Session, tenant: str, pf: str, inst: str, alpha: str = "0.4"):  # noqa: ANN202
    mv = register_desmoothed_return_model(
        db, tenant_id=tenant, actor_id="a", code_version="pa1-v1", alpha=alpha
    )
    db.flush()
    return run_desmoothed_return(
        db,
        acting_tenant=tenant,
        actor=ACT,
        code_version="pa1-v1",
        environment_id="ci",
        model_version_id=mv.id,
        portfolio_id=pf,
        instrument_id=inst,
        window_start=WINDOW[0],
        window_end=WINDOW[1],
    )


# ---------- the pure kernel ----------


def test_kernel_goldens_match_hand_derivation() -> None:
    marks = [Decimal(v) for v in MARK_VALUES]
    observed = observed_returns(marks)
    assert observed == [
        Decimal("0.020000000000"),
        Decimal("0.025000000000"),
        Decimal("-0.010000000000"),
    ]
    desmoothed = desmooth_geltner(observed, Decimal("0.4"))
    assert desmoothed == [Decimal("0.032500000000"), Decimal("-0.062500000000")]


def test_kernel_alpha_one_is_identity() -> None:
    # BOUNDARY: alpha=1 means no smoothing — the inversion must degenerate to the observed series
    # (minus the seed period).
    observed = [Decimal("0.02"), Decimal("0.025"), Decimal("-0.01")]
    assert desmooth_geltner(observed, Decimal("1")) == [
        Decimal("0.025000000000"),
        Decimal("-0.010000000000"),
    ]


def test_kernel_stdev_inflation_on_smoothed_series() -> None:
    # A positively-autocorrelated (smoothed) series desmooths to HIGHER volatility — the mechanism
    # the thesis targets. Uses the golden series (autocorrelated by construction).
    from irp_shared.perf import sample_stdev

    observed = observed_returns([Decimal(v) for v in MARK_VALUES])
    desmoothed = desmooth_geltner(observed, Decimal("0.4"))
    assert sample_stdev(desmoothed) > sample_stdev(observed[1:])


def test_kernel_domain_errors() -> None:
    two = [Decimal("0.02"), Decimal("0.03")]
    with pytest.raises(DesmoothingKernelError):
        desmooth_geltner(two, Decimal("0"))  # alpha out of (0, 1]
    with pytest.raises(DesmoothingKernelError):
        desmooth_geltner(two, Decimal("1.1"))
    with pytest.raises(DesmoothingKernelError):
        desmooth_geltner([Decimal("0.02")], Decimal("0.4"))  # too short
    with pytest.raises(DesmoothingKernelError):
        observed_returns([Decimal("100")])  # one mark is no series
    with pytest.raises(DesmoothingKernelError):
        observed_returns([Decimal("100"), Decimal("0")])  # non-positive mark


# ---------- the full-stack golden ----------


def test_full_stack_golden(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    result = _run(session, t, pf, inst)
    assert result.status == RunStatus.COMPLETED.value
    periods = [r for r in result.rows if r.metric_type == METRIC_TYPE_DESMOOTHED_PERIOD]
    summary = [r for r in result.rows if r.metric_type == METRIC_TYPE_DESMOOTHING_SUMMARY]
    assert len(periods) == 2 and len(summary) == 1

    d2, d3 = sorted(periods, key=lambda r: r.period_start)
    # the hand-derived desmoothed values + the row-by-row consumed-input echoes.
    assert d2.metric_value == Decimal("0.032500000000")
    assert d2.observed_return == Decimal("0.025000000000")
    assert (d2.period_start, d2.period_end) == (MARK_DATES[1], MARK_DATES[2])
    assert (d2.begin_mark, d2.end_mark) == (Decimal("102.000000"), Decimal("104.550000"))
    assert d3.metric_value == Decimal("-0.062500000000")
    assert d3.observed_return == Decimal("-0.010000000000")
    assert (d3.period_start, d3.period_end) == (MARK_DATES[2], MARK_DATES[3])
    for r in (d2, d3):
        assert r.alpha == Decimal("0.4") and r.mark_currency == "USD"

    s = summary[0]
    assert s.metric_value == Decimal("0.067175144213")  # desmoothed stdev (0.0475*sqrt(2))
    assert s.observed_stdev == Decimal("0.024748737342")  # observed stdev (0.0175*sqrt(2))
    assert s.metric_value > s.observed_stdev  # risk WAS understated — the honest pair
    assert s.n_periods == 2
    assert (s.period_start, s.period_end) == (MARK_DATES[1], MARK_DATES[3])
    assert s.portfolio_id == pf and s.instrument_id == inst


# ---------- TR-09 reproducibility (both sides) ----------


def test_tr09_reproducibility_both_sides(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    first = _run(session, t, pf, inst)
    snap_id = first.run.input_snapshot_id
    assert verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t).ok is True

    # Side 1: a POST-RUN mark supersede does not move the historical result (nor its pins).
    supersede_valuation(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=MARK_DATES[2],
        acting_tenant=t,
        actor=ValuationActor(actor_id="s"),
        effective_at=datetime(2026, 7, 10, tzinfo=UTC),
        mark_value=Decimal("120.00"),  # a plausible re-appraisal
    )
    session.flush()
    assert verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t).ok is True

    # Side 2: a re-run against the SAME snapshot reproduces byte-identically.
    mv = register_desmoothed_return_model(
        session, tenant_id=t, actor_id="a", code_version="pa1-v1", alpha="0.4"
    )
    second = run_desmoothed_return(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="pa1-v1",
        environment_id="ci",
        model_version_id=mv.id,
        snapshot_id=snap_id,
    )
    assert second.status == RunStatus.COMPLETED.value
    key = lambda r: (r.metric_type, r.period_start)  # noqa: E731 - local test shorthand
    for a, b in zip(sorted(first.rows, key=key), sorted(second.rows, key=key), strict=True):
        assert (a.metric_value, a.observed_return, a.observed_stdev, a.n_periods) == (
            b.metric_value,
            b.observed_return,
            b.observed_stdev,
            b.n_periods,
        )


# ---------- pre-create refusals (NO RUNNING orphan) ----------


def test_short_series_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t, values=MARK_VALUES[:3], dates=MARK_DATES[:3])
    with pytest.raises(DesmoothingInputError):  # 3 marks < the 4-mark statistical floor
        _run(session, t, pf, inst)
    assert_no_running_orphan(session, run_type=RUN_TYPE_DESMOOTHED_RETURN)


def test_two_mark_window_refused_at_builder(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    mv = register_desmoothed_return_model(
        session, tenant_id=t, actor_id="a", code_version="pa1-v1", alpha="0.4"
    )
    with pytest.raises(DesmoothingSnapshotError):  # window holds < 2 marks — structurally empty
        run_desmoothed_return(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="pa1-v1",
            environment_id="ci",
            model_version_id=mv.id,
            portfolio_id=pf,
            instrument_id=inst,
            window_start=date(2025, 9, 1),
            window_end=date(2025, 10, 15),  # only the first mark falls inside
        )
    assert_no_running_orphan(session, run_type=RUN_TYPE_DESMOOTHED_RETURN)


def test_mixed_currency_series_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t, values=MARK_VALUES[:2], dates=MARK_DATES[:2])
    # Two further marks in EUR on the SAME (portfolio, instrument) — no FX translation in v1.
    if (
        session.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == "EUR")
        ).scalar_one_or_none()
        is None
    ):
        session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="EUR", name="EUR", valid_from=T0))
        session.flush()
    for d, v in zip(MARK_DATES[2:], MARK_VALUES[2:], strict=True):
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=t,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code="EUR",
            valid_from=T0,
        )
    session.flush()
    with pytest.raises(DesmoothingInputError):
        _run(session, t, pf, inst)
    assert_no_running_orphan(session, run_type=RUN_TYPE_DESMOOTHED_RETURN)


def test_ambiguous_input_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    mv = register_desmoothed_return_model(
        session, tenant_id=t, actor_id="a", code_version="pa1-v1", alpha="0.4"
    )
    before = session.execute(select(func.count()).select_from(CalculationRun)).scalar()
    with pytest.raises(DesmoothingInputError):
        run_desmoothed_return(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="pa1-v1",
            environment_id="ci",
            model_version_id=mv.id,
            portfolio_id=pf,
            instrument_id=inst,
            window_start=WINDOW[0],
            window_end=WINDOW[1],
            snapshot_id=str(uuid.uuid4()),  # both build args AND a snapshot -> ambiguous
        )
    assert session.execute(select(func.count()).select_from(CalculationRun)).scalar() == before
    assert_no_running_orphan(session, run_type=RUN_TYPE_DESMOOTHED_RETURN)


def test_unregistered_model_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    with pytest.raises(UnregisteredModelError):
        run_desmoothed_return(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="pa1-v1",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),  # not a registered version
            portfolio_id=pf,
            instrument_id=inst,
            window_start=WINDOW[0],
            window_end=WINDOW[1],
        )
    assert_no_running_orphan(session, run_type=RUN_TYPE_DESMOOTHED_RETURN)


def test_alpha_domain_enforced_at_registration(session: Session) -> None:
    t = str(uuid.uuid4())
    for bad in ("0", "1.5", "-0.4", "0.000000000000", "abc"):
        with pytest.raises(ValueError):
            register_desmoothed_return_model(
                session, tenant_id=t, actor_id="a", code_version="pa1-v1", alpha=bad
            )


# ---------- adjudication unit gates (duplicate dates / non-positive marks) ----------


def _mark_dict(d: str, v: str, pf: str = "p1", inst: str = "i1", ccy: str = "USD") -> dict:
    return {
        "valuation_date": d,
        "mark_value": v,
        "portfolio_id": pf,
        "instrument_id": inst,
        "currency_code": ccy,
    }


def test_adjudication_duplicate_dates_and_nonpositive_marks() -> None:
    base = [_mark_dict(f"2026-0{m}-15", v) for m, v in zip("1234", MARK_VALUES, strict=True)]
    dup = [*base[:3], _mark_dict("2026-03-15", "99.00")]  # duplicate date
    with pytest.raises(DesmoothingInputError):
        _adjudicate_pins(dup)
    zero = [*base[:3], _mark_dict("2026-04-15", "0")]  # non-positive mark (BOUNDARY)
    with pytest.raises(DesmoothingInputError):
        _adjudicate_pins(zero)


def test_magnitude_overflow_is_committed_failed_not_raised(session: Session) -> None:
    # BOUNDARY: marks 100.00 -> 100.00 -> 100000000000.00 jump gives an observed return ~1E9 and a
    # desmoothed value ~2.5E9 — both >= _MAX_RESULT_ABS (1E8) — so the run must COMMIT as FAILED
    # with ZERO rows (never a raised 500; the fold also wraps any deeper Decimal detonation as the
    # same committed-FAILED outcome).
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(
        session,
        t,
        values=("100.00", "100.00", "100000000000.00", "100000000000.00"),
    )
    result = _run(session, t, pf, inst)
    assert result.status == RunStatus.FAILED.value  # committed FAILED, NOT a raised error
    assert result.rows == []  # zero rows on a FAILED run
    assert result.failure_reason and "magnitude" in result.failure_reason
    assert_no_running_orphan(session, run_type=RUN_TYPE_DESMOOTHED_RETURN)


def test_adjudication_mixed_portfolio_and_instrument_refused() -> None:
    # The OD-PA-1-H uniform-subject gates — reachable only via a hand-minted/consume-existing
    # snapshot (the build path filters on one (portfolio, instrument)), so pinned-unit-tested.
    base = [_mark_dict(f"2026-0{m}-15", v) for m, v in zip("1234", MARK_VALUES, strict=True)]
    mixed_pf = [*base[:3], _mark_dict("2026-04-15", "101.00", pf="p2")]
    with pytest.raises(DesmoothingInputError):
        _adjudicate_pins(mixed_pf)
    mixed_inst = [*base[:3], _mark_dict("2026-04-15", "101.00", inst="i2")]
    with pytest.raises(DesmoothingInputError):
        _adjudicate_pins(mixed_inst)


def test_adjudication_duplicate_date_representations_refused() -> None:
    # Review fold: date.fromisoformat also accepts the ISO BASIC form — two representations of ONE
    # date must still collide (the dedupe keys on the PARSED date, not the raw string).
    base = [_mark_dict(f"2026-0{m}-15", v) for m, v in zip("123", MARK_VALUES[:3], strict=True)]
    twin = [*base, _mark_dict("20260315", "99.00")]  # the BASIC form of 2026-03-15
    with pytest.raises(DesmoothingInputError):
        _adjudicate_pins(twin)


# ---------- governed-number guards ----------


def test_result_is_append_only(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    result = _run(session, t, pf, inst)
    row = result.rows[0]
    row.metric_value = Decimal("999")
    with pytest.raises(AppendOnlyViolation):
        session.flush()


def test_run_type_is_not_a_metric_type() -> None:
    # GS2: the run_type FAMILY must never equal a metric_type.
    assert RUN_TYPE_DESMOOTHED_RETURN not in {
        METRIC_TYPE_DESMOOTHED_PERIOD,
        METRIC_TYPE_DESMOOTHING_SUMMARY,
    }


def test_no_perf_star_audit_emitted(session: Session) -> None:
    t = str(uuid.uuid4())
    pf, inst = _seed_marks(session, t)
    _run(session, t, pf, inst)
    n = session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type.like("PERF.%"))
    ).scalar_one()
    assert n == 0  # PERF.DESMOOTHED_RETURN_CREATE is RESERVED, not emitted


def test_migration_head_is_desmoothed_return() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0051_breach_action"  # MG-2
    assert script.get_revision("0036_desmoothed_return").down_revision == "0035_scenario"
    assert (
        script.get_revision("0042_desmoothing_estimated_alpha").down_revision
        == "0041_es_historical"
    )


# --- DS-2 (OD-DS-2-A/B/C): the estimator-convention runs end-to-end -----------------------------

_DS2_DATES = tuple(date(2023, 3, 31) + timedelta(days=91 * i) for i in range(12))


def _smoothed_mark_values(phi: str = "0.6", start: str = "100.00") -> tuple[str, ...]:
    """A deterministic AR(1)-shaped quarterly mark path (fixture-searched at planning: sample
    rho_1 ≈ 0.29 > 0 AND the OW m=2 discriminants positive — admissible for BOTH conventions;
    an AR(1) shape keeps rho_2 ≈ rho_1², which is always OW-admissible, unlike a flat-rho_2
    cycle where (1+rho_2)² < 4·rho_1²)."""
    eps_cycle = ("0.0045", "-0.0043", "0.0082", "-0.0096", "-0.0083", "-0.0072", "0.0067")
    marks = [Decimal(start)]
    prev = Decimal("0.02")
    for i in range(len(_DS2_DATES) - 1):
        obs = Decimal(phi) * prev + Decimal(eps_cycle[i % len(eps_cycle)])
        prev = obs
        marks.append((marks[-1] * (Decimal(1) + obs)).quantize(Decimal("0.000001")))
    return tuple(str(m) for m in marks)


def _register_and_run(  # noqa: ANN202
    db: Session, tenant: str, pf: str, inst: str, version_id: str
):
    from irp_shared.perf import run_desmoothed_return

    return run_desmoothed_return(
        db,
        acting_tenant=tenant,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=version_id,
        portfolio_id=pf,
        instrument_id=inst,
        window_start=_DS2_DATES[0] - timedelta(days=1),
        window_end=_DS2_DATES[-1] + timedelta(days=1),
    )


def test_ar1_estimated_run_echoes_alpha_hat_and_band(session: Session) -> None:
    from irp_shared.perf import register_desmoothed_return_estimated_model
    from irp_shared.perf.desmoothing_kernel import estimate_ar1_alpha, observed_returns

    tenant = str(uuid.uuid4())
    values = _smoothed_mark_values()
    pf, inst = _seed_marks(session, tenant, values=values, dates=_DS2_DATES)
    version = register_desmoothed_return_estimated_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", min_periods=8
    )
    out = _register_and_run(session, tenant, pf, inst, str(version.id))
    assert out.status == "COMPLETED"

    # Independent recomputation: alpha-hat + the band from the same marks.
    est = estimate_ar1_alpha(observed_returns([Decimal(v) for v in values]))
    alpha_hat = est.alpha_hat.quantize(Decimal("1E-12"))
    stderr = est.stderr.quantize(Decimal("1E-12"))
    periods = [r for r in out.rows if r.metric_type == "DESMOOTHED_PERIOD"]
    summary = next(r for r in out.rows if r.metric_type == "DESMOOTHING_SUMMARY")
    assert len(periods) == len(values) - 2
    assert all(r.alpha == alpha_hat for r in periods)
    assert summary.alpha == alpha_hat
    assert summary.alpha_stderr == stderr
    assert all(r.alpha_stderr is None for r in periods)  # the summary-only invariant


def test_ar1_estimated_floor_refusal(session: Session) -> None:
    from irp_shared.perf import register_desmoothed_return_estimated_model
    from irp_shared.perf.desmoothing_service import DesmoothingInputError

    tenant = str(uuid.uuid4())
    values = _smoothed_mark_values()[:6]  # 5 observed < the declared floor 8
    pf, inst = _seed_marks(session, tenant, values=values, dates=_DS2_DATES[:6])
    version = register_desmoothed_return_estimated_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", min_periods=8
    )
    with pytest.raises(DesmoothingInputError, match="min_periods floor"):
        run_desmoothed_return(
            session,
            acting_tenant=tenant,
            actor=DesmoothedReturnActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=str(version.id),
            portfolio_id=pf,
            instrument_id=inst,
            window_start=_DS2_DATES[0] - timedelta(days=1),
            window_end=_DS2_DATES[5] + timedelta(days=1),
        )


def test_ar1_estimated_refuses_negative_autocorrelation(session: Session) -> None:
    from irp_shared.perf import register_desmoothed_return_estimated_model
    from irp_shared.perf.desmoothing_service import DesmoothingInputError

    tenant = str(uuid.uuid4())
    # Alternating up/down marks => strongly negative rho_1.
    vals = []
    m = Decimal("100")
    for i in range(12):
        vals.append(str(m))
        m = (m * (Decimal("1.05") if i % 2 == 0 else Decimal("0.955"))).quantize(
            Decimal("0.000001")
        )
    pf, inst = _seed_marks(session, tenant, values=tuple(vals), dates=_DS2_DATES)
    version = register_desmoothed_return_estimated_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", min_periods=8
    )
    with pytest.raises(DesmoothingInputError, match="alpha estimation refused"):
        _register_and_run(session, tenant, pf, inst, str(version.id))


def test_okunev_white_run_null_alpha_and_alignment(session: Session) -> None:
    from irp_shared.perf import register_desmoothed_return_okunev_white_model
    from irp_shared.perf.benchmark_relative_kernel import sample_stdev
    from irp_shared.perf.desmoothing_kernel import desmooth_okunev_white, observed_returns

    tenant = str(uuid.uuid4())
    values = _smoothed_mark_values()
    pf, inst = _seed_marks(session, tenant, values=values, dates=_DS2_DATES)
    version = register_desmoothed_return_okunev_white_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", ow_max_order=2
    )
    out = _register_and_run(session, tenant, pf, inst, str(version.id))
    assert out.status == "COMPLETED"

    observed = observed_returns([Decimal(v) for v in values])
    ow = desmooth_okunev_white(observed, 2)
    offset = 3  # m(m+1)/2 at m=2
    periods = [r for r in out.rows if r.metric_type == "DESMOOTHED_PERIOD"]
    summary = next(r for r in out.rows if r.metric_type == "DESMOOTHING_SUMMARY")
    assert len(periods) == len(observed) - offset == len(ow.series)
    assert all(r.alpha is None for r in periods) and summary.alpha is None
    assert summary.alpha_stderr is None
    assert summary.n_periods == len(ow.series)
    for k, row in enumerate(sorted(periods, key=lambda r: r.period_start)):
        j = k + offset
        assert row.metric_value == ow.series[k]
        assert (row.period_start, row.period_end) == (_DS2_DATES[j], _DS2_DATES[j + 1])
        assert row.observed_return == observed[j]
    assert summary.metric_value == sample_stdev(list(ow.series))
    assert summary.observed_stdev == sample_stdev(observed[offset:])


def test_okunev_white_floor_refusal(session: Session) -> None:
    from irp_shared.perf import register_desmoothed_return_okunev_white_model
    from irp_shared.perf.desmoothing_service import DesmoothingInputError

    tenant = str(uuid.uuid4())
    values = _smoothed_mark_values()[:5]  # 4 observed < m(m+1)/2+2 = 5 at m=2
    pf, inst = _seed_marks(session, tenant, values=values, dates=_DS2_DATES[:5])
    version = register_desmoothed_return_okunev_white_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", ow_max_order=2
    )
    with pytest.raises(DesmoothingInputError, match="okunev-white transform refused"):
        run_desmoothed_return(
            session,
            acting_tenant=tenant,
            actor=DesmoothedReturnActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=str(version.id),
            portfolio_id=pf,
            instrument_id=inst,
            window_start=_DS2_DATES[0] - timedelta(days=1),
            window_end=_DS2_DATES[4] + timedelta(days=1),
        )
