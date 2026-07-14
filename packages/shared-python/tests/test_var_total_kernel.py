"""Pure-kernel unit tests for the PA-4 total-parametric-VaR residual leg (ENT-027 consumer, the
13th governed number's math substrate — no DB, no I/O; the ``var_kernel`` twin).

HAND REFERENCE (verified independently, in-build): MV=1000, an appraised residual stdev of 4%
per quarter (``appraisal_days=91``), over a factor variance of 100 (``sigma_factor=10``):

    d_trading = 91 * (252/365) = 62.827397260273972602739726027397260273972602739726
    sigma_e_daily = 0.04 / sqrt(d_trading) = 0.0050464439851412522876474927296866606780388697213755
    contribution = 1000 * sigma_e_daily = 5.0464439851412522876474927296866606780388697213755
    residual_variance = contribution^2 = 25.466596895168323739752311180882609454038025466597
    sigma_total = sqrt(100 + residual_variance)
                = 11.201187298459405894292066742886291296247282557390

quantized to the ``var_result`` column scales (``residual_variance`` 20dp, ``sigma`` 6dp):
``residual_variance = 25.46659689516832373975``, ``sigma_total = 11.201187``.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from irp_shared.risk.var_total_kernel import (
    ResidualInstrument,
    VarTotalKernelError,
    daily_residual_stdev,
    total_var_residual,
)

_PREC = 50


def test_hand_reference_single_proxied_instrument() -> None:
    with localcontext() as ctx:
        ctx.prec = _PREC
        r = total_var_residual(
            Decimal("100"),
            [
                ResidualInstrument(
                    instrument_id="inst-1",
                    market_value=Decimal("1000"),
                    residual_stdev_period=Decimal("0.04"),
                    mean_period_calendar_days=Decimal("91"),
                )
            ],
            trading_days_per_year=252,
            calendar_days_per_year=365,
        )
    assert r.residual_variance.quantize(Decimal("1E-20")) == Decimal("25.46659689516832373975")
    assert r.sigma_total.quantize(Decimal("1E-6")) == Decimal("11.201187")


def test_daily_residual_stdev_hand_reference() -> None:
    with localcontext() as ctx:
        ctx.prec = _PREC
        d = daily_residual_stdev(
            Decimal("0.04"),
            Decimal("91"),
            trading_days_per_year=252,
            calendar_days_per_year=365,
        )
    assert d.quantize(Decimal("1E-16")) == Decimal("0.0050464439851413")


def test_zero_proxied_instruments_degrades_to_sqrt_factor_var() -> None:
    """The no-proxied-instrument case: residual_variance = 0, sigma_total = sqrt(factor_var) —
    the plain-family invariance property at the kernel level (the binder-level twin lives in
    ``test_var_total.py``)."""
    with localcontext() as ctx:
        ctx.prec = _PREC
        r = total_var_residual(
            Decimal("100"), [], trading_days_per_year=252, calendar_days_per_year=365
        )
    assert r.residual_variance == Decimal(0)
    assert r.sigma_total == Decimal("100").sqrt()


def test_multiple_instruments_sum_independently() -> None:
    """Diagonal residuals (Sharpe 1963): TWO proxied instruments' contributions sum as squares
    (no cross term) — a 3-4-5 construction: contribution_1=3, contribution_2=4 =>
    residual_variance = 9+16 = 25 exactly, sigma_total = sqrt(factor_var + 25)."""
    # sigma_daily = sigma_period / sqrt(d_trading); pick appraisal_days=252, trading=calendar=1
    # so d_trading = 252 * 1 = 252... instead, force d_trading = 1 (trading=calendar, days=1):
    # sigma_daily = sigma_period exactly (a clean pass-through — isolates the summation math).
    with localcontext() as ctx:
        ctx.prec = _PREC
        r = total_var_residual(
            Decimal("0"),
            [
                ResidualInstrument(
                    instrument_id="a",
                    market_value=Decimal("1"),
                    residual_stdev_period=Decimal("3"),
                    mean_period_calendar_days=Decimal("1"),
                ),
                ResidualInstrument(
                    instrument_id="b",
                    market_value=Decimal("1"),
                    residual_stdev_period=Decimal("4"),
                    mean_period_calendar_days=Decimal("1"),
                ),
            ],
            trading_days_per_year=1,
            calendar_days_per_year=1,
        )
    assert r.residual_variance == Decimal(25)
    assert r.sigma_total == Decimal(5)


def test_non_positive_mean_period_refuses() -> None:
    with localcontext() as ctx:
        ctx.prec = _PREC
        try:
            total_var_residual(
                Decimal("100"),
                [
                    ResidualInstrument(
                        instrument_id="x",
                        market_value=Decimal("1000"),
                        residual_stdev_period=Decimal("0.04"),
                        mean_period_calendar_days=Decimal("0"),
                    )
                ],
                trading_days_per_year=252,
                calendar_days_per_year=365,
            )
            raise AssertionError("expected VarTotalKernelError")
        except VarTotalKernelError as exc:
            assert exc.reason == "non-positive-period"


def test_negative_total_variance_refuses() -> None:
    """A factor_var beyond [-tol, 0) that still lands negative after adding a (non-negative)
    residual leg is unreachable via the governed path (the binder pre-clamps) but the kernel
    itself refuses defensively — the ``var_kernel`` non-PSD-radicand twin."""
    with localcontext() as ctx:
        ctx.prec = _PREC
        try:
            total_var_residual(
                Decimal("-1"), [], trading_days_per_year=252, calendar_days_per_year=365
            )
            raise AssertionError("expected VarTotalKernelError")
        except VarTotalKernelError as exc:
            assert exc.reason == "negative-total-variance"
