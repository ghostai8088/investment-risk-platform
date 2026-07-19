"""DS-2 pure-kernel tests (OD-DS-2-A/B) — lag autocorrelation, the in-run AR(1) α estimate, and
the Okunev-White iterative filter, verified against INDEPENDENT re-derivations: exact Fraction
where the arithmetic is rational (ρ̂, α̂ — no sqrt), a prec-120 independent Decimal mirror where a
root is involved (the OW coefficients/series), and the R2-respecified ALGEBRAIC quadratic-residual
identity (never a filtered-series autocorrelation-is-zero assertion at finite n)."""

from __future__ import annotations

import random
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from irp_shared.perf.desmoothing_kernel import (
    DesmoothingKernelError,
    desmooth_okunev_white,
    estimate_ar1_alpha,
    lag_autocorrelation,
)


def _frac_autocorr(xs: list[Fraction], lag: int) -> Fraction:
    n = len(xs)
    mean = sum(xs, Fraction(0)) / n
    c = [x - mean for x in xs]
    denom = sum(v * v for v in c)
    return sum(c[t] * c[t + lag] for t in range(n - lag)) / denom


def _smoothed_series(rng: random.Random, n: int, alpha: Fraction) -> list[Fraction]:
    """A deterministic Geltner-smoothed series: observed_t = α·true_t + (1−α)·observed_{t−1},
    with rational 'true' draws — positive ρ₁ by construction for α < 1."""
    true = [Fraction(rng.randint(-400, 500), 10_000) for _ in range(n)]
    out = [true[0]]
    for t in range(1, n):
        out.append(alpha * true[t] + (1 - alpha) * out[-1])
    return out


def _d(fr: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(fr.numerator) / Decimal(fr.denominator)


# --- lag_autocorrelation ------------------------------------------------------------------------


def test_lag_autocorrelation_matches_exact_fraction_and_is_bounded() -> None:
    rng = random.Random(421)
    for _ in range(60):
        n = rng.randint(5, 24)
        xs = [Fraction(rng.randint(-500, 500), 1000) for _ in range(n)]
        if len(set(xs)) == 1:
            continue
        for lag in (1, 2, min(3, n - 1)):
            if lag >= n:
                continue
            got = lag_autocorrelation([_d(x) for x in xs], lag)
            want = _frac_autocorr(xs, lag)
            assert abs(got - _d(want)) < Decimal("1E-40")
            assert abs(got) <= 1  # Cauchy-Schwarz under the T-denominator form


def test_lag_autocorrelation_refusals() -> None:
    xs = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")]
    with pytest.raises(DesmoothingKernelError):
        lag_autocorrelation(xs, 0)
    with pytest.raises(DesmoothingKernelError):
        lag_autocorrelation(xs, 3)  # lag >= n: the empty-sum artifact refusal
    with pytest.raises(DesmoothingKernelError):
        lag_autocorrelation([Decimal("0.01")] * 5, 1)  # constant series


# --- estimate_ar1_alpha -------------------------------------------------------------------------


def test_ar1_alpha_matches_exact_fraction() -> None:
    rng = random.Random(422)
    checked = 0
    for _ in range(40):
        xs = _smoothed_series(rng, rng.randint(8, 30), Fraction(2, 5))
        rho1 = _frac_autocorr(xs, 1)
        if rho1 <= 0:
            continue
        est = estimate_ar1_alpha([_d(x) for x in xs])
        assert abs(est.rho1 - _d(rho1)) < Decimal("1E-40")
        assert abs(est.alpha_hat - _d(1 - rho1)) < Decimal("1E-40")
        # stderr = 1/sqrt(n) at prec 50
        with localcontext() as ctx:
            ctx.prec = 50
            want_se = Decimal(1) / Decimal(len(xs)).sqrt()
        assert abs(est.stderr - want_se) < Decimal("1E-45")
        assert Decimal(0) < est.alpha_hat < Decimal(1)
        checked += 1
    assert checked >= 30  # the smoothed generator yields positive rho1 essentially always


def test_ar1_alpha_refuses_non_positive_rho1() -> None:
    # An alternating series has strongly negative rho1.
    xs = [Decimal("0.05") if t % 2 == 0 else Decimal("-0.05") for t in range(12)]
    with pytest.raises(DesmoothingKernelError, match="no positive smoothing signal"):
        estimate_ar1_alpha(xs)


# --- desmooth_okunev_white ----------------------------------------------------------------------


def _mirror_ow(observed: list[Decimal], m: int) -> tuple[list[Decimal], list[Decimal]]:
    """An INDEPENDENT prec-120 mirror of the OW transform (different code path, higher precision
    — the numeric-finder discipline)."""
    with localcontext() as ctx:
        ctx.prec = 120
        cur = list(observed)
        cs: list[Decimal] = []
        for i in range(1, m + 1):
            n = len(cur)
            mean = sum(cur, Decimal(0)) / Decimal(n)
            cen = [x - mean for x in cur]
            den = sum((v * v for v in cen), Decimal(0))
            r_i = sum((cen[t] * cen[t + i] for t in range(n - i)), Decimal(0)) / den
            r_2i = sum((cen[t] * cen[t + 2 * i] for t in range(n - 2 * i)), Decimal(0)) / den
            if r_i == 0:
                c = Decimal(0)
            else:
                disc = (Decimal(1) + r_2i) ** 2 - Decimal(4) * r_i * r_i
                c = ((Decimal(1) + r_2i) - disc.sqrt()) / (Decimal(2) * r_i)
            cur = [(cur[t] - c * cur[t - i]) / (Decimal(1) - c) for t in range(i, n)]
            cs.append(c)
        return cur, cs


def test_ow_matches_independent_mirror_and_quadratic_residual() -> None:
    """The kernel's OW output matches a prec-120 independent mirror, and each pass coefficient
    satisfies the ALGEBRAIC identity ρ_i·c² − (1+ρ_2i)·c + ρ_i ≈ 0 on ITS OWN pass's series (the
    R2 respecification — never a filtered-autocorrelation-is-zero assertion)."""
    rng = random.Random(423)
    for m in (1, 2, 3):
        for _ in range(12):
            xs = [_d(x) for x in _smoothed_series(rng, rng.randint(14, 40), Fraction(1, 2))]
            try:
                got = desmooth_okunev_white(xs, m)
            except DesmoothingKernelError:
                continue  # a refused draw (negative disc etc.) is fine here
            mirror_series, mirror_cs = _mirror_ow(xs, m)
            assert len(got.series) == len(xs) - m * (m + 1) // 2
            for a, b in zip(got.coefficients, mirror_cs, strict=True):
                assert abs(a - b) < Decimal("1E-40")
            for a, b in zip(got.series, mirror_series, strict=True):
                # the kernel quantizes the FINAL series to 12dp; the mirror is raw
                assert abs(a - b) <= Decimal("5E-13")
            # the algebraic residual, pass by pass (recompute each pass's rho on the mirror);
            # the residual arithmetic itself MUST run at prec 50 — the default prec-28 context
            # would inject ~1e-28 arithmetic noise and swamp the identity.
            cur = list(xs)
            for i, c in enumerate(got.coefficients, start=1):
                rho_i = lag_autocorrelation(cur, i)
                rho_2i = lag_autocorrelation(cur, 2 * i)
                with localcontext() as ctx:
                    ctx.prec = 50
                    residual = rho_i * c * c - (Decimal(1) + rho_2i) * c + rho_i
                    assert abs(residual) < Decimal("1E-45")
                    cur = [(cur[t] - c * cur[t - i]) / (Decimal(1) - c) for t in range(i, len(cur))]


def test_ow_whitens_negative_autocorrelation_deliberately() -> None:
    """ρ_i < 0 is admissible (whitening — the recorded OD-A/OD-B asymmetry): the pass runs, c is
    negative, and the filter is well-defined with (1−c) > 1."""
    # An MA(1)-flavored alternating-ish series with negative rho1 but non-constant structure.
    rng = random.Random(424)
    base = [Decimal(rng.randint(-300, 300)) / Decimal(10_000) for _ in range(30)]
    xs = [base[t] - (base[t - 1] if t else Decimal(0)) * Decimal("0.6") for t in range(30)]
    rho1 = lag_autocorrelation(xs, 1)
    assert rho1 < 0
    got = desmooth_okunev_white(xs, 1)
    assert got.coefficients[0] < 0
    assert len(got.series) == len(xs) - 1


def test_ow_structural_floors_fail_closed() -> None:
    xs = [Decimal("0.01"), Decimal("0.03"), Decimal("0.02")]
    # n=3 < m(m+1)/2+2 = 5 at m=2
    with pytest.raises(DesmoothingKernelError, match="cumulative pass loss"):
        desmooth_okunev_white(xs, 2)
    # m=1 floor is 3 -> passes the floor, but pass 1 needs length > 2 (ok: 3 > 2) — runs or
    # refuses on structure, never crashes:
    try:
        desmooth_okunev_white(xs, 1)
    except DesmoothingKernelError:
        pass


def test_ow_identity_pass_when_rho_is_zero() -> None:
    """A series engineered with EXACTLY zero lag-1 sample autocorrelation takes the c=0 identity
    pass deterministically (count preserved: the first value still drops)."""
    # x with mean 0 and sum(x_t*x_{t+1}) == 0: e.g. [a, b, -a, -b] pattern scaled — verify in
    # Fraction then feed Decimal.
    xs_f = [Fraction(1, 100), Fraction(1, 100), Fraction(-1, 100), Fraction(-1, 100)] * 2
    assert _frac_autocorr(xs_f, 1) != 0  # this pattern is NOT zero; construct directly instead
    # direct construction: [a, 0, -a, 0] repeated has sum x_t x_{t+1} = 0 and nonzero variance
    xs_f = [Fraction(1, 100), Fraction(0), Fraction(-1, 100), Fraction(0)] * 3
    assert _frac_autocorr(xs_f, 1) == 0
    got = desmooth_okunev_white([_d(x) for x in xs_f], 1)
    assert got.coefficients == (Decimal(0),)
    assert len(got.series) == len(xs_f) - 1


# --- The convention gate (OD-DS-2-C): ambiguity + stray-literal refusals (the RS-1 battery) ----


@pytest.fixture
def db():  # noqa: ANN201
    from sqlalchemy.pool import StaticPool

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.models import Base

    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _mint_desmoothing_version(db, tenant: str, assumptions: list[str]):  # noqa: ANN001, ANN202
    """Mint a desmoothing version through the GENERIC path (arbitrary assumption rows — the
    P3-4 threat the parse-gate exists for)."""
    import uuid as _uuid

    from irp_shared.model.service import register_model_version, resolve_or_register_model

    model = resolve_or_register_model(
        db,
        tenant_id=tenant,
        code="perf.return.desmoothed_geltner",
        name="dm",
        model_type="DESMOOTHED_RETURN",
        actor_id="s",
        description="generic mint (test)",
    )
    return register_model_version(
        db,
        model=model,
        version_label=f"vX-{_uuid.uuid4().hex[:6]}",
        actor_id="s",
        methodology_ref="05_analytics_methodologies/desmoothing_estimated_v1.md",
        code_version="v1",
        status="REGISTERED",
        assumptions=tuple(assumptions),
        limitations=(),
    )


@pytest.mark.parametrize(
    "assumptions",
    [
        # AMBIGUOUS: duplicated convention rows never collapse into the DECLARED grandfather.
        ["alpha=0.4", "estimator_convention=AR1_ESTIMATED", "estimator_convention=AR1_ESTIMATED"],
        ["estimator_convention=AR1_ESTIMATED", "estimator_convention=OKUNEV_WHITE_ITERATIVE"],
        # STRAY literals on the implicit-DECLARED grandfather (a lying displayed identity).
        ["alpha=0.4", "min_periods=8"],
        ["alpha=0.4", "ow_max_order=2"],
        ["alpha=0.4", "band_convention=BARTLETT_WHITE_NOISE"],
        # AR1_ESTIMATED with a stray alpha / missing companions / sub-floor min_periods.
        [
            "estimator_convention=AR1_ESTIMATED",
            "alpha=0.4",
            "min_periods=8",
            "band_convention=BARTLETT_WHITE_NOISE",
        ],
        ["estimator_convention=AR1_ESTIMATED", "min_periods=8"],  # no band
        ["estimator_convention=AR1_ESTIMATED", "band_convention=BARTLETT_WHITE_NOISE"],  # no floor
        [
            "estimator_convention=AR1_ESTIMATED",
            "min_periods=5",
            "band_convention=BARTLETT_WHITE_NOISE",
        ],  # below the structural floor 6
        # OW with a stray alpha / min_periods / band, or an out-of-domain order.
        ["estimator_convention=OKUNEV_WHITE_ITERATIVE", "ow_max_order=2", "alpha=0.4"],
        ["estimator_convention=OKUNEV_WHITE_ITERATIVE", "ow_max_order=2", "min_periods=8"],
        ["estimator_convention=OKUNEV_WHITE_ITERATIVE", "ow_max_order=5"],
        ["estimator_convention=OKUNEV_WHITE_ITERATIVE"],  # no order
        # Unknown convention literal.
        ["alpha=0.4", "estimator_convention=GLM_MA_K"],
    ],
)
def test_gate_refuses_ambiguous_stray_and_malformed(db, assumptions) -> None:  # noqa: ANN001
    import uuid as _uuid

    from irp_shared.model.service import WrongModelVersionError
    from irp_shared.perf import declared_desmoothing_parameters

    version = _mint_desmoothing_version(db, str(_uuid.uuid4()), assumptions)
    with pytest.raises(WrongModelVersionError):
        declared_desmoothing_parameters(db, version)


def test_gate_grandfathers_the_shipped_declared_identity(db) -> None:  # noqa: ANN001
    """Zero convention rows + a clean alpha => the implicit DECLARED grandfather, byte-preserving
    the shipped parse; the REAL registrar's output parses identically."""
    import uuid as _uuid

    from irp_shared.perf import (
        declared_desmoothing_parameters,
        register_desmoothed_return_model,
    )

    tenant = str(_uuid.uuid4())
    minted = _mint_desmoothing_version(db, tenant, ["alpha=0.4"])
    params = declared_desmoothing_parameters(db, minted)
    assert params.estimator_convention == "DECLARED"
    assert params.alpha == Decimal("0.4")
    assert (params.min_periods, params.band_convention, params.ow_max_order) == (None, None, None)

    real = register_desmoothed_return_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", alpha="0.4"
    )
    real_params = declared_desmoothing_parameters(db, real)
    assert real_params.estimator_convention == "DECLARED"
    assert real_params.alpha == Decimal("0.4")


def test_registrars_stamp_and_reparse(db) -> None:  # noqa: ANN001
    import uuid as _uuid

    from irp_shared.perf import (
        declared_desmoothing_parameters,
        register_desmoothed_return_estimated_model,
        register_desmoothed_return_okunev_white_model,
    )

    tenant = str(_uuid.uuid4())
    est = register_desmoothed_return_estimated_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", min_periods=8
    )
    p = declared_desmoothing_parameters(db, est)
    assert p.estimator_convention == "AR1_ESTIMATED"
    assert p.min_periods == 8 and p.band_convention == "BARTLETT_WHITE_NOISE"
    assert p.alpha is None and p.ow_max_order is None

    ow = register_desmoothed_return_okunev_white_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", ow_max_order=2
    )
    q = declared_desmoothing_parameters(db, ow)
    assert q.estimator_convention == "OKUNEV_WHITE_ITERATIVE"
    assert q.ow_max_order == 2
    assert q.alpha is None and q.min_periods is None and q.band_convention is None

    # same-label different-declaration => the governed 409
    from irp_shared.model.service import ModelVersionConflictError

    with pytest.raises(ModelVersionConflictError):
        register_desmoothed_return_estimated_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", min_periods=10
        )
    with pytest.raises(ModelVersionConflictError):
        register_desmoothed_return_okunev_white_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", ow_max_order=3
        )
