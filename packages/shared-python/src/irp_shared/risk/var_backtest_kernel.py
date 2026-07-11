"""Pure VaR-backtesting kernel (BT-1, ENT-055 — exception counting / Kupiec POF / Basel zone).

NO DB, NO I/O — the outcomes-analysis statistics over aligned (realized P&L, VaR forecast) pairs:

    exception       e_i = 1  iff  -P&L_i > VaR_i                    (STRICT, OD-BT-1-F)
    Kupiec POF      LR = -2 ln[(1-p)^(N-x) p^x]
                         + 2 ln[(1-x/N)^(N-x) (x/N)^x]              (Kupiec 1995; chi-square(1))
    decision        REJECT iff LR > chi2_crit(alpha)                (fixed criticals — NO p-value)
    Basel zone      GREEN 0-4 / YELLOW 5-9 / RED >= 10              (BCBS Jan-1996; (99%, 250) only)

Computed in ``Decimal`` at 50-digit context (``Decimal.ln``); the LR quantize_HALF_UP to 12dp
(the binder stores at the ratified Numeric(28,6) scale — OQ-BT-1-6). The ``x=0`` / ``x=N`` edges
drop the vanishing terms ANALYTICALLY (the ``0^0 = 1`` convention — never ``ln(0)``).

POF is TWO-SIDED: suspiciously FEW exceptions also rejects (an over-conservative model fails
coverage too — e.g. N=250 @ p=0.01 with x=0 gives LR ~ 5.03 > 3.841459). Test-pinned.

The Basel zone table has NO defined meaning off (confidence=0.99, N=250) — the CALLER (binder)
enforces that domain; this kernel is the pure table.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

#: LR quantum: HALF_UP to 12dp (the faithful statistic; storage scale is the binder's concern).
_LR_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision (the perf/risk kernel precedent).
_COMPUTE_PREC = 50

#: Fixed chi-square(1) critical values for the DECLARED alpha set (OD-BT-1-A — Decimal-pure
#: decisions, no p-value/erf in v1). Extending the set is a NEW model version, never silent.
CHI2_1DF_CRITICALS: dict[Decimal, Decimal] = {
    Decimal("0.05"): Decimal("3.841459"),
    Decimal("0.01"): Decimal("6.634897"),
}

DECISION_REJECT = "REJECT"
DECISION_FAIL_TO_REJECT = "FAIL_TO_REJECT"

ZONE_GREEN = "GREEN"
ZONE_YELLOW = "YELLOW"
ZONE_RED = "RED"


class VarBacktestKernelError(ValueError):
    """Raised for an ill-formed input (a non-positive pair count; exceptions exceeding pairs; a
    coverage probability outside (0, 1); an alpha outside the declared critical set). Defense-in-
    depth: the binder adjudicates the pinned content PRE-create, making the structural cases
    unreachable through the governed path."""


def exception_indicator(realized_pnl: Decimal, var_value: Decimal) -> int:
    """``1`` iff the realized LOSS strictly exceeds the VaR forecast: ``-P&L > VaR`` (OD-BT-1-F —
    a loss exactly AT VaR is NOT an exception; the Basel "loss exceeding VaR" convention)."""
    return 1 if -realized_pnl > var_value else 0


def kupiec_lr(n: int, x: int, coverage_p: Decimal) -> Decimal:
    """The Kupiec (1995) proportion-of-failures likelihood-ratio statistic for ``x`` exceptions in
    ``n`` pairs at exception probability ``coverage_p`` (= 1 - confidence). Asymptotically
    chi-square(1); TWO-SIDED (too few exceptions rejects too). ``quantize_HALF_UP`` to 12dp.
    The ``x=0``/``x=n`` edges drop the vanishing terms analytically (``0^0 = 1``). Raises
    :class:`VarBacktestKernelError` on ``n < 1``, ``x < 0``, ``x > n``, or ``coverage_p``
    outside (0, 1)."""
    if n < 1:
        raise VarBacktestKernelError(f"Kupiec POF needs >= 1 pair (got {n})")
    if x < 0 or x > n:
        raise VarBacktestKernelError(f"exception count {x} outside [0, {n}]")
    if not (Decimal(0) < coverage_p < Decimal(1)):
        raise VarBacktestKernelError(f"coverage probability {coverage_p} outside (0, 1)")
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        n_d, x_d = Decimal(n), Decimal(x)
        # ln L(p)  = (n-x) ln(1-p) + x ln(p)        — the null (declared coverage)
        # ln L(x/n) = (n-x) ln(1-x/n) + x ln(x/n)   — the MLE; vanishing terms dropped at edges
        log_null = (n_d - x_d) * (Decimal(1) - coverage_p).ln()
        log_mle = Decimal(0)
        if x > 0:
            log_null += x_d * coverage_p.ln()
            log_mle += x_d * (x_d / n_d).ln()
        if x < n:
            log_mle += (n_d - x_d) * (Decimal(1) - x_d / n_d).ln()
        lr = Decimal(-2) * log_null + Decimal(2) * log_mle
        return lr.quantize(_LR_QUANTUM, rounding=ROUND_HALF_UP)


def kupiec_decision(lr: Decimal, alpha: Decimal) -> str:
    """``REJECT`` iff ``lr`` exceeds the FIXED chi-square(1) critical value for the declared
    ``alpha`` (:data:`CHI2_1DF_CRITICALS`); else ``FAIL_TO_REJECT``. Raises
    :class:`VarBacktestKernelError` on an alpha outside the declared set (the registrar constrains
    it upstream — reaching here with another alpha is a defect, not an input)."""
    critical = CHI2_1DF_CRITICALS.get(alpha)
    if critical is None:
        raise VarBacktestKernelError(
            f"alpha {alpha} is not in the declared critical set "
            f"{sorted(str(a) for a in CHI2_1DF_CRITICALS)}"
        )
    return DECISION_REJECT if lr > critical else DECISION_FAIL_TO_REJECT


def basel_zone(n_exceptions: int) -> str:
    """The BCBS (January 1996) traffic-light zone for ``n_exceptions`` over a 250-observation
    99%-confidence window: GREEN 0-4, YELLOW 5-9, RED >= 10. The (0.99, 250) DOMAIN is the
    caller's gate (OD-BT-1-G) — this is the pure table. Raises on a negative count."""
    if n_exceptions < 0:
        raise VarBacktestKernelError(f"exception count {n_exceptions} is negative")
    if n_exceptions <= 4:
        return ZONE_GREEN
    if n_exceptions <= 9:
        return ZONE_YELLOW
    return ZONE_RED
