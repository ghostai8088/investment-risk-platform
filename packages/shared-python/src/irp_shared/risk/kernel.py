"""Pure analytic sensitivity kernel (P3-1, ENT-028) — closed-form curve-node DV01 / spread-DV01.

NO DB, NO I/O, NO interpolation, NO pricing/discounting engine, NO instrument cash-flow terms — a
deterministic function of one captured curve node + the ratified numerical conventions (OD-P3-1-G),
fully unit-testable. The sensitivity of a **unit (notional = 1) zero-coupon claim** maturing at the
node tenor ``T``: ``PV = DF(T)``; ``dPV/d(rate) = -T*DF``; so ``DV01 = -T * DF * 1bp`` per a +1bp
single-node bump. Conventions: ``T = tenor_days / 365`` (ACT/365 Fixed); continuous compounding
``DF = exp(-rate * T)``; ``1bp = 0.0001`` absolute; result quantized HALF_UP to 12dp (the
``Numeric(28,12)`` column scale). Evaluated AT the captured nodes only — there is deliberately NO
interpolation between nodes (the curve module is captured-never-computed). ``PAR_RATE`` is rejected
(par->zero needs bootstrapping = curve construction, deferred).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

from irp_shared.marketdata.models import (
    VALUE_TYPE_DISCOUNT_FACTOR,
    VALUE_TYPE_ZERO_RATE,
)

#: ACT/365 Fixed day-count: year fraction = tenor_days / 365 (declared convention, OD-P3-1-G).
_DAYS_PER_YEAR = Decimal(365)
#: One basis point, absolute (the bump size).
_ONE_BP = Decimal("0.0001")
#: Result quantum: HALF_UP to 12dp = the ``sensitivity_result.sensitivity_value`` Numeric(28,12)
#: scale.
_RESULT_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision for the transcendental ``exp`` (well above the 12dp result scale;
#: deterministic
#: Python-only — the kernel never touches the DB, so there is no SQLite/PG split here).
_COMPUTE_PREC = 50


class SensitivityKernelError(ValueError):
    """Raised for an unsupported ``value_type`` (e.g. ``PAR_RATE``) or a non-positive tenor — the
    method does NOT bootstrap or interpolate. A binder-side guard maps it to a fail-closed gap."""


def _year_fraction(tenor_days: int) -> Decimal:
    if not isinstance(tenor_days, int) or tenor_days <= 0:
        raise SensitivityKernelError(f"tenor_days must be a positive int (got {tenor_days!r})")
    return Decimal(tenor_days) / _DAYS_PER_YEAR


def _dv01_from_df(t: Decimal, df: Decimal) -> Decimal:
    """DV01 of a unit zero-coupon claim per +1bp: ``-T * DF * 1bp`` (HALF_UP @ 12dp)."""
    return (Decimal(-1) * t * df * _ONE_BP).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)


def node_dv01(tenor_days: int, value_type: str, point_value: Decimal) -> Decimal:
    """Analytic rate DV01 (per +1bp) of a unit zero-coupon claim at one captured curve node.

    ``ZERO_RATE`` -> ``DF = exp(-z*T)`` (continuous compounding). ``DISCOUNT_FACTOR`` -> the
    captured
    ``DF`` is used **directly** in ``-T*DF*1bp`` (no implied-zero on the compute path —
    ``dPV/d(rate) = -T*DF`` holds however ``DF`` was obtained). Raises
    :class:`SensitivityKernelError`
    for ``PAR_RATE``/``SPREAD``/unknown (use :func:`node_spread_dv01` for spread nodes)."""
    t = _year_fraction(tenor_days)
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        if value_type == VALUE_TYPE_ZERO_RATE:
            df = (Decimal(-1) * Decimal(point_value) * t).exp()
        elif value_type == VALUE_TYPE_DISCOUNT_FACTOR:
            df = Decimal(point_value)  # the captured discount factor, used directly
        else:
            raise SensitivityKernelError(
                f"node_dv01 unsupported value_type {value_type!r} (PAR_RATE deferred)"
            )
        return _dv01_from_df(t, df)


def node_spread_dv01(tenor_days: int, point_value: Decimal) -> Decimal:
    """Analytic spread-DV01 (per +1bp) at one captured ``SPREAD`` node (carried by a
    ``CREDIT_SPREAD``
    curve): ``DF = exp(-s*T)``; ``spread-DV01 = -T * DF * 1bp`` — the same closed form on the
    spread
    node (standalone). Quantized HALF_UP to 12dp."""
    t = _year_fraction(tenor_days)
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        df = (Decimal(-1) * Decimal(point_value) * t).exp()
        return _dv01_from_df(t, df)
