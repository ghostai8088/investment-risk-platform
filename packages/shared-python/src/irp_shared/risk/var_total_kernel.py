"""Total-parametric-VaR residual leg (PA-4, ENT-027 consumer — pure math, no I/O, no ORM).

The plain parametric family computes the FACTOR variance ``factor_var = x'Σx`` (the existing
``var_kernel``). This module adds the IDIOSYNCRATIC leg (Sharpe 1963 single-index diagonal) and the
total volatility:

    residual_var = Σ_i (MV_i · σ_e,i,daily)²                (base-currency²; independent residuals)
    σ_total      = √(factor_var + residual_var)
    VaR          = z · σ_total

The per-instrument daily residual stdev de-scales the appraisal-period residual on a DECLARED
TRADING-day grid (OD-PA-4-D): ``σ_e,daily = σ_e,period / √(d̄_cal · trading/calendar)``, ``d̄_cal``
the mean calendar-day period length. Computed in ``Decimal`` at 50-digit context; the binder gates
magnitudes and quantizes (``σ`` → 6dp ``Numeric(28,6)``; ``residual_var`` → 20dp).
Fail-closed (a :class:`VarTotalKernelError`, mapped by the binder to a **post-create committed
FAILED run** — the DQ-gap mechanism, the OD-P3-5-G lifecycle) on a non-positive mean period or a
negative total variance. Both raises are DEFENSE-IN-DEPTH, binder-unreachable through the
governed path: the declared ``appraisal_days`` identity floors the period at 1 pre-create, and
the binder passes a clamped ``factor_var ≥ 0`` plus a sum-of-squares residual (the P3-4
defensive-gate precedent; kernel-unit-tested standalone).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

_CTX_PRECISION = 50


class VarTotalKernelError(ValueError):
    """A structural residual-leg failure (a non-positive mean period, a negative total variance).
    The binder maps it to a post-create committed FAILED run (the DQ-gap mechanism);
    binder-unreachable through the governed path — see the module docstring. ``reason`` is a
    stable short slug."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ResidualInstrument:
    """One proxied instrument's idiosyncratic inputs (adjudicated, pinned): its market value (base
    currency), its cited estimate's APPRAISAL-PERIOD residual stdev, and that estimate's mean
    calendar-day period length."""

    instrument_id: str
    market_value: Decimal
    residual_stdev_period: Decimal
    mean_period_calendar_days: Decimal


@dataclass(frozen=True)
class TotalVarResidual:
    """The RAW (un-quantized, prec-50) residual leg + total volatility. The binder gates magnitudes
    then quantizes to the column scales."""

    residual_variance: Decimal  # Σ_i (MV_i·σ_e,i,daily)² (base-currency²)
    sigma_total: Decimal  # √(factor_var + residual_variance)


def daily_residual_stdev(
    residual_stdev_period: Decimal,
    mean_period_calendar_days: Decimal,
    *,
    trading_days_per_year: int,
    calendar_days_per_year: int,
) -> Decimal:
    """De-scale an appraisal-period residual stdev to daily on the DECLARED trading-day grid:
    ``σ_daily = σ_period / √(d̄_cal · trading/calendar)`` (OD-PA-4-D). Raises on ``d̄_cal ≤ 0``."""
    if mean_period_calendar_days <= 0:
        raise VarTotalKernelError(
            "non-positive-period",
            f"mean period {mean_period_calendar_days} calendar days is non-positive — refused",
        )
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        d_trading = mean_period_calendar_days * (
            Decimal(trading_days_per_year) / Decimal(calendar_days_per_year)
        )
        return residual_stdev_period / d_trading.sqrt()


def total_var_residual(
    factor_var: Decimal,
    instruments: Sequence[ResidualInstrument],
    *,
    trading_days_per_year: int,
    calendar_days_per_year: int,
) -> TotalVarResidual:
    """Combine the FACTOR variance ``factor_var`` (= ``x'Σx``, already PSD-clamped by the caller)
    with the diagonal idiosyncratic variance of the proxied ``instruments`` into the total σ. Raw
    prec-50; the binder gates + quantizes. Raises :class:`VarTotalKernelError` on a non-positive
    period or a negative total variance."""
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        residual_var = Decimal(0)
        for inst in instruments:
            sigma_daily = daily_residual_stdev(
                inst.residual_stdev_period,
                inst.mean_period_calendar_days,
                trading_days_per_year=trading_days_per_year,
                calendar_days_per_year=calendar_days_per_year,
            )
            contribution = inst.market_value * sigma_daily
            residual_var += contribution * contribution
        total_var = factor_var + residual_var
        if total_var < 0:
            raise VarTotalKernelError(
                "negative-total-variance",
                f"total variance {total_var} < 0 (a non-PSD factor leg beyond tolerance) — refused",
            )
        return TotalVarResidual(residual_variance=residual_var, sigma_total=total_var.sqrt())
