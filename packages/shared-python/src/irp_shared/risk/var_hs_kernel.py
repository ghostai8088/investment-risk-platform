"""Pure historical-simulation kernels: VaR (VAR-HS-1, OD-VHS-A/D) + ES (ES-HS-1, OD-ES-HS-1-A).

NO DB, NO I/O, NO distributional assumption — the factor-based historical simulation under the
same linear factor model as the parametric kernel (``dV_t = SUM_i x_i * r_{t,i}``):

    pnl_t  = SUM_i x_i * r_{t,i}          one scenario per pinned window date t   (base ccy)
    k      = ceil(N * (1 - c))            the LOWER empirical order statistic (OD-VHS-D)
    VaR_c  = -(k-th smallest pnl)         loss reported POSITIVE; NO interpolation

    a      = 1 - c;  m = floor(N * a);  w = N*a - m            (ES-HS-1; all EXACT Decimal)
    ES_c   = -( SUM_{i<=m} pnl_(i) + w * pnl_(m+1) ) / (N * a)  the Acerbi-Tasche Prop 4.1
                                                                α-tail-mean — floor count +
                                                                FRACTIONAL boundary weight,
                                                                NEVER the mean of the worst
                                                                ⌈N·a⌉ (that is the TCE,
                                                                forbidden at ES-1)

Computed in ``Decimal`` at 50-digit context precision; the result is ``quantize_HALF_UP`` to
6dp (the ``Numeric(28,6)`` currency scale — parametric parity). ``k``/``m``/``w`` are exact
Decimal arithmetic (``N``, ``c`` are exact Decimals; no float touches the selection). The
conventions are REGISTRATION-DECLARED (``quantile_convention='LOWER_ORDER_STATISTIC'``;
``estimator_convention='TAIL_MEAN_ACERBI_TASCHE_P41'``): a different estimator is a NEW
declared version, never silent drift (VAR-HS-1 record Part 2.4; ES-HS-1 record OD-B).

``ES >= VaR`` holds at raw precision for every window (provable from the sorted order; equality
at TIED tail scenarios — the worst m+1 P&Ls equal). Both values may be NEGATIVE (an all-gains
tail) — reported honestly, never clamped. Coverage/alignment is a PRECONDITION (the binder
adjudicates pinned content pre-create); the kernels re-verify so the pure functions are safe
standalone (defense-in-depth — the parametric kernel's stance).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext

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


@dataclass(frozen=True)
class HsEsEstimate:
    """The ES kernel output: ``n_observations`` scenarios, the tail floor count ``m`` =
    ``floor(N*(1-c))`` (the number of FULLY-weighted worst scenarios; the (m+1)-th carries the
    fractional weight ``N*(1-c) - m``), and the quantized ``es_value`` (positive = loss)."""

    n_observations: int
    tail_floor_count: int
    es_value: Decimal


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

    # k/confidence validation stays AHEAD of the accumulation (refusal precedence is part of
    # the observable contract: a doubly-bad input gets the confidence refusal — test-pinned).
    n = len(returns_by_date)
    k = order_statistic_index(n, confidence)

    # EVERYTHING (accumulation, negation, quantize) runs inside the prec-50 context: at the
    # default prec 28, a >=1E22 result made quantize raise InvalidOperation (a raw 500 instead
    # of the binder's magnitude-gate FAILED run) and the unary minus HALF_EVEN-rounded a
    # >28-significant-digit P&L BEFORE the declared HALF_UP quantize (2026-07 review, numeric
    # finder — both verified empirically).
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        pnls = _sorted_scenario_pnls(exposures, returns_by_date)
        kth_worst = pnls[k - 1]
        var_value = (-kth_worst).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
    return HsVarEstimate(n_observations=n, k=k, var_value=var_value)


def compute_historical_es(
    exposures: dict[str, Decimal],
    returns_by_date: dict[date, dict[str, Decimal]],
    *,
    confidence: Decimal,
) -> HsEsEstimate:
    """The empirical Expected Shortfall over the SAME scenario distribution (ES-HS-1, OD-A):
    the Acerbi-Tasche Prop 4.1 α-tail-mean — with a = 1-c, m = floor(n·a), w = n·a - m (ALL
    exact Decimal; no float touches the selection),

        ES = -( SUM_{i<=m} pnl_(i) + w · pnl_(m+1) ) / (n·a)

    over the ascending-sorted scenario P&Ls (pnl_(1) the worst). NEVER the mean of the worst
    ⌈n·a⌉ — that quantity is the TCE forbidden at ES-1 (it understates ES at every fractional
    n·a). ``pnl_(m+1)`` is always in range (a < 1 ⇒ m ≤ n·a < n); its coefficient is exactly
    zero when n·a is integer. The strict adequacy floor (n·(1-c) > 1) is IDENTITY, enforced at
    registration and bind like the VaR leg's — the kernel mirrors ``compute_historical_var``'s
    defense-in-depth stance (refuses only c outside (0,1) / k < 1 standalone)."""
    if not exposures:
        raise HsVarKernelError("no exposures — nothing to simulate")
    if not returns_by_date:
        raise HsVarKernelError("no scenarios — the pinned window is empty")

    # Validation AHEAD of the accumulation (the same refusal precedence as the VaR leg).
    n = len(returns_by_date)
    order_statistic_index(n, confidence)  # validates c in (0,1) and k >= 1
    a = Decimal(1) - confidence
    n_a = Decimal(n) * a  # exact: c is a <=4dp Decimal, n an int
    m = int(n_a.to_integral_value(rounding=ROUND_FLOOR))
    w = n_a - m  # exact; 0 exactly when n·a is integer

    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        pnls = _sorted_scenario_pnls(exposures, returns_by_date)
        tail = sum(pnls[:m], Decimal(0)) + w * pnls[m]
        es_value = (-(tail / n_a)).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
    return HsEsEstimate(n_observations=n, tail_floor_count=m, es_value=es_value)


def _sorted_scenario_pnls(
    exposures: dict[str, Decimal],
    returns_by_date: dict[date, dict[str, Decimal]],
) -> list[Decimal]:
    """Accumulate one P&L per pinned window date and sort ascending (``pnls[0]`` = the WORST).
    Runs under the CALLER'S active Decimal context — both kernels wrap the call in the prec-50
    localcontext so accumulation, negation, and quantize share one precision regime (the
    2026-07 lesson at :func:`compute_historical_var`)."""
    pnls: list[Decimal] = []
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
    pnls.sort()
    return pnls
