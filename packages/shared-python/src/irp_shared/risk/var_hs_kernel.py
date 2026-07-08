"""Pure historical-simulation VaR kernel (VAR-HS-1, OD-VHS-A/D — plain equal-weight v1).

NO DB, NO I/O, NO distributional assumption — the factor-based historical simulation under the
same linear factor model as the parametric kernel (``dV_t = SUM_i x_i * r_{t,i}``):

    pnl_t  = SUM_i x_i * r_{t,i}          one scenario per pinned window date t   (base ccy)
    k      = ceil(N * (1 - c))            the LOWER empirical order statistic (OD-VHS-D)
    VaR_c  = -(k-th smallest pnl)         loss reported POSITIVE; NO interpolation

Computed in ``Decimal`` at 50-digit context precision; ``var_value`` is ``quantize_HALF_UP`` to
6dp (the ``Numeric(28,6)`` currency scale — parametric parity). ``k`` is exact integer
arithmetic (``N``, ``c`` are exact Decimals; no float touches the selection). The convention is
REGISTRATION-DECLARED (``quantile_convention='LOWER_ORDER_STATISTIC'``): the conservative,
deterministic reading behind the Basel-era "3rd worst of 250 at 99%" discrete rule; interpolated
estimators are recorded v2 declarations, never silent drift (decision record Part 2.4).

``var_value`` may be NEGATIVE (every k-th-tail scenario was a gain) — reported honestly, never
clamped (the methodology doc states the sign convention). Coverage/alignment is a PRECONDITION
(the binder adjudicates pinned content pre-create); the kernel re-verifies so the pure function
is safe standalone (defense-in-depth — the parametric kernel's stance).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext

#: Result quantum: HALF_UP to 6dp = the ``var_result.var_value`` Numeric(28,6) currency scale.
_RESULT_QUANTUM = Decimal(1).scaleb(-6)
#: Compute precision for the scenario accumulation (the P3-4/P3-5 kernel precedent).
_COMPUTE_PREC = 50


class HsVarKernelError(ValueError):
    """Raised for an ill-formed input (no exposures, no scenarios, a confidence outside (0,1),
    an inadequate window for the confidence, or a date missing an exposure factor's return).
    Defense-in-depth: the binder adjudicates the pinned content PRE-CREATE."""


@dataclass(frozen=True)
class HsVarEstimate:
    """The kernel output: ``n_observations`` scenarios, the selected order statistic ``k``
    (1-based, from the worst), and the quantized ``var_value`` (positive = loss)."""

    n_observations: int
    k: int
    var_value: Decimal


def order_statistic_index(n_observations: int, confidence: Decimal) -> int:
    """``k = ceil(N * (1 - c))`` — exact Decimal arithmetic, 1-based from the worst scenario.
    Refuses ``c`` outside (0,1) and the statistically meaningless ``k == 0`` case."""
    if not Decimal(0) < confidence < Decimal(1):
        raise HsVarKernelError(f"confidence must be in (0,1); got {confidence}")
    k = int(
        (Decimal(n_observations) * (Decimal(1) - confidence)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    if k < 1:
        raise HsVarKernelError(
            f"window of {n_observations} observations cannot support confidence {confidence}"
        )
    return k


def compute_historical_var(
    exposures: dict[str, Decimal],
    returns_by_date: dict[date, dict[str, Decimal]],
    *,
    confidence: Decimal,
) -> HsVarEstimate:
    """Run the plain equal-weight historical simulation over the pinned window.

    ``exposures``: factor_id -> per-factor total exposure (base currency; the FACTOR_EXPOSURE
    run's pinned totals). ``returns_by_date``: date -> {factor_id -> decimal return} — every
    exposure factor must be present on EVERY date (coverage is the binder's pre-create gate;
    re-verified here)."""
    if not exposures:
        raise HsVarKernelError("no exposures — nothing to simulate")
    if not returns_by_date:
        raise HsVarKernelError("no scenarios — the pinned window is empty")

    n = len(returns_by_date)
    k = order_statistic_index(n, confidence)

    pnls: list[Decimal] = []
    # EVERYTHING (accumulation, negation, quantize) runs inside the prec-50 context: at the
    # default prec 28, a >=1E22 result made quantize raise InvalidOperation (a raw 500 instead
    # of the binder's magnitude-gate FAILED run) and the unary minus HALF_EVEN-rounded a
    # >28-significant-digit P&L BEFORE the declared HALF_UP quantize (2026-07 review, numeric
    # finder — both verified empirically).
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        for day in sorted(returns_by_date):
            day_returns = returns_by_date[day]
            pnl = Decimal(0)
            for factor_id, x in exposures.items():
                r = day_returns.get(factor_id)
                if r is None:
                    raise HsVarKernelError(
                        f"factor {factor_id} has no return on {day.isoformat()} — "
                        "coverage precondition violated"
                    )
                pnl += x * r
            pnls.append(pnl)

        pnls.sort()  # ascending: pnls[0] is the WORST scenario
        kth_worst = pnls[k - 1]
        var_value = (-kth_worst).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
    return HsVarEstimate(n_observations=n, k=k, var_value=var_value)
