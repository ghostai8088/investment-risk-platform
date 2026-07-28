"""Pure Sharpe-ratio kernel (SR-1, ENT-065 — the 22nd governed number).

NO DB, NO I/O. Turns the RELINKED monthly return series (RM-1's grid, reused verbatim) and a
CAPTURED monthly risk-free series into trailing-window risk-adjusted returns:

    excess          d_j = m_j - r_f,j
    Sharpe ratio    SR  = mean(d) / sigma(d)                 (Sharpe 1994, differential return)
    annualized      SR_ann = SR_stored * sqrt(12)            (Lo 2002 under iid)

**The denominator is sigma of the EXCESS series, not of the portfolio series.** Sharpe (1966)
divided the mean excess return by the standard deviation of the *total* return series; Sharpe
(1994) revised this to the standard deviation of the *differential* series, and that is the
now-canonical form this module implements. The distinction is not cosmetic and it is the reason
SR-1 cannot reuse RM-1's persisted ``ROLLING_VOLATILITY`` rows: the two denominators coincide only
when ``r_f`` is constant across the window, which is a special case rather than a design. A test
pins a fixture where they genuinely differ.

**The divisor DIVERGES from the named paper, and the divergence is disclosed rather than branded
away.** Sharpe (1994)'s own endnote 1 uses the POPULATION standard deviation (divisor ``T``); this
module uses the platform's uniform ``sample_stdev`` (``n-1``), which makes sigma larger by
``sqrt(12/11) ~ +4.4%`` at ``n = 12`` and the ratio correspondingly **~4.3% smaller**. That is
above this platform's own materiality bar, so it is stated here, in the methodology doc, and in the
REGISTERED model assumptions — never described as "Sharpe (1994)" unqualified.

**Single quantization, and the order is load-bearing.** The mean and sigma of the excess series are
accumulated UNQUANTIZED at 50 digits, the division is performed at that precision, and only the
RATIO is quantized to 12dp. Dividing the quantized operands instead was executed and refuted: a
NON-constant excess series such as eleven values of ``1E-12`` and one ``0`` has a true sigma of
about ``2.9E-13``, which quantizes to ``0E-12`` — so the quantized-operand order raises
``DivisionByZero`` on a legal input, i.e. an uncaught 500 rather than a governed number. This
contrasts deliberately with RM-1's ``annualize_volatility``, which MUST read its stored value: RM-1
persists its sigma, so its emitted pair has to reconcile exactly. ENT-065 persists no mean and no
sigma, so no reconciliation constraint binds the internals — but it DOES persist the ratio and its
annualization, so :func:`annualize_sharpe` reads the STORED ratio for exactly RM-1's reason.

**Suppression names the SAME sigma.** The ratio is suppressed iff the UNQUANTIZED sigma is exactly
zero — a genuinely constant excess series (Decimal equality is exact, so this is a real test rather
than a tolerance). Sub-quantum dispersion divides finely and emits a large value, which the
binder's magnitude gate then adjudicates. This keeps the suppression reason TRUE under its own
predicate: the row says the ratio is undefined for a constant series, and it is emitted only for
constant series.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date as dt_date
from decimal import Decimal, localcontext

from irp_shared.perf.rolling_kernel import MONTHS_PER_YEAR, MonthlyReturn
from irp_shared.perf.stats_kernel import (
    COMPUTE_PREC,
    mean_and_stdev_unquantized,
    quantize_result,
)

#: The reason stamped on a zero-dispersion suppression. A module constant because the test suite
#: asserts the emitted row carries exactly this text — a reason a consumer reads is part of the
#: contract, not incidental prose.
ZERO_DISPERSION_REASON = "zero dispersion — the ratio is undefined for a constant excess series"


class SharpeKernelError(ValueError):
    """An ill-formed Sharpe input: a risk-free series that does not cover the measured months, or a
    window the series cannot fill.

    Defense-in-depth — the binder adjudicates the pinned content PRE-create, so these are
    structurally unreachable through the governed path. A ``ValueError`` like every other kernel
    error in this package, and deliberately NOT an ``ArithmeticError`` (the ``stats_kernel``
    rationale: a structural input error must not be swallowed by an ``except ArithmeticError``
    suppression idiom).
    """


def month_key(day: dt_date) -> tuple[int, int]:
    """The ``(year, month)`` join key.

    **The risk-free leg joins the portfolio leg by MONTH, never by date** (the load-bearing
    criterion
    the draft record omitted entirely). The book's month-end convention is "the calendar month end
    or
    the last business day" (GIPS 2.A.23.b), while a vendor publishes a monthly return dated however
    it
    pleases — the calendar end, the last business day, or the first of the following month. Joining
    on
    the date would refuse a perfectly aligned pair for a weekend; joining on the month makes an rf
    row
    dated ANY day of its month match that month's observation, with neither side bending its dates.
    """
    return (day.year, day.month)


@dataclass(frozen=True)
class MonthlyExcess:
    """One month's excess observation, carrying BOTH legs as consumed evidence.

    Keeping the two inputs beside the difference is deliberate: the excess series is where the two
    legs meet, and a reviewer reconstructing a Sharpe row by hand needs the operands, not just the
    result.
    """

    month_end: dt_date
    portfolio_return: Decimal
    risk_free_return: Decimal
    excess: Decimal


def build_excess_series(
    months: Sequence[MonthlyReturn],
    risk_free_by_month: Mapping[tuple[int, int], Decimal],
) -> list[MonthlyExcess]:
    """Pair every relinked month with its risk-free return and difference them.

    The subtraction is EXACT: both legs are 12dp fractions, and Decimal subtraction of two values at
    a common exponent is exact at that exponent regardless of context precision — verified across
    sign and magnitude extremes rather than assumed.

    A month with no risk-free row raises :class:`SharpeKernelError` NAMING the month. There is no
    imputation and no carry-forward: a missing risk-free month is a capture gap an operator must
    fix, and silently computing "the windows we can" would ship a partially-poisoned surface whose
    gaps are invisible on the read side.
    """
    if not months:
        raise SharpeKernelError("no monthly observations to difference")
    out: list[MonthlyExcess] = []
    for month in months:
        key = month_key(month.month_end)
        rf = risk_free_by_month.get(key)
        if rf is None:
            raise SharpeKernelError(
                f"no risk-free return for {key[0]}-{key[1]:02d} (the month ending "
                f"{month.month_end}) — refused; there is no imputation"
            )
        out.append(
            MonthlyExcess(
                month_end=month.month_end,
                portfolio_return=month.value,
                risk_free_return=rf,
                excess=month.value - rf,
            )
        )
    return out


def sharpe_ratio(excess: Sequence[Decimal]) -> Decimal | None:
    """``SR = mean(d)/sigma(d)`` at 12dp, or ``None`` when the excess series is CONSTANT.

    ``None`` is the suppression signal, never a value: the binder turns it into a governed
    suppressed
    row (NULL value + explicit flag + reason), because **zero is a legitimate Sharpe ratio** — a
    book
    that exactly earns the risk-free rate scores 0 — so a stuffed zero would be indistinguishable
    from "not computable" and would read as "earned nothing above cash".

    Single-quantization: mean and sigma unquantized at 50 digits, the division at that precision,
    the
    RATIO quantized once. See the module docstring for the executed refutation of the alternative.
    """
    mean, sigma = mean_and_stdev_unquantized(excess)
    if sigma == 0:
        # EXACT equality on the UNQUANTIZED sigma — the same operand the division would use, so the
        # predicate and the arithmetic cannot disagree. A quantized-sigma predicate would suppress
        # sub-quantum-dispersion series whose ratio is perfectly computable, and (worse) would leave
        # the genuine DivisionByZero reachable through a different rounding path.
        return None
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        return quantize_result(mean / sigma)


def annualize_sharpe(sharpe_stored: Decimal) -> Decimal:
    """``SR_ann = quantize(SR_STORED * sqrt(12))`` — the iid scaling law, DECLARED as a convention.

    Grounded twice: Lo (2002) gives ``SR(q) = sqrt(q) * SR(1)`` under iid returns, and Sharpe
    (1994)'s
    own eqs. 7/8 carry the same operator (mean scales with ``T``, sigma with ``sqrt(T)``, so the
    ratio
    scales with ``sqrt(T)`` under zero serial correlation). Under AUTOCORRELATION this misstates,
    and
    Lo Eq. 20 gives the correction — exact only on log returns, which this platform does not
    compute.
    The correction is a recorded v2; ``sqrt(12)`` here is honest convention, not a claim that the
    books are iid. This platform's own desmoothing slices exist precisely because they are not.

    Reads the STORED 12dp ratio (RM-1's ``annualize_volatility`` order) because ENT-065 persists
    BOTH
    members of this pair: a consumer must be able to multiply the raw row by ``sqrt(12)`` and land
    exactly on the annualized row. Sign is preserved — a negative Sharpe annualizes to a MORE
    negative Sharpe, which is correct and is the direction most likely to be "fixed" by mistake.
    """
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        return quantize_result(sharpe_stored * Decimal(MONTHS_PER_YEAR).sqrt())


@dataclass(frozen=True)
class SharpeWindow:
    """One evaluated trailing window: its span, its sample, and the ratio pair.

    ``sharpe`` and ``annualized_sharpe`` are ``None`` TOGETHER, exactly when the excess series over
    the window is constant. They are never independently absent — an annualized row with no raw row
    (or the reverse) would leave a consumer keying the pair unable to tell which half was
    suppressed.
    """

    window_months: int
    period_start: dt_date  # the OPENING boundary (the prior month's close)
    period_end: dt_date
    n_observations: int
    sharpe: Decimal | None
    annualized_sharpe: Decimal | None


def sharpe_windows(
    excess: Sequence[MonthlyExcess],
    window_months: int,
    *,
    opening_boundary: dt_date,
) -> list[SharpeWindow]:
    """Every COMPLETE trailing window of ``window_months`` over the excess series.

    Incomplete windows are NOT emitted here — the binder emits a governed *suppressed* row for them
    instead, one per ``(metric_type, window_months)`` per run (RM-1's granularity; per-evaluation-
    point would collide on the four-column grain). ``opening_boundary`` is ``d_0``, the boundary
    that
    closes the month BEFORE the first measured month, and therefore the ``period_start`` of the
    first
    window.
    """
    if window_months < 2:
        raise SharpeKernelError(f"window_months must be >= 2 (got {window_months})")
    windows: list[SharpeWindow] = []
    for end in range(window_months - 1, len(excess)):
        start = end - window_months + 1
        sample = excess[start : end + 1]
        ratio = sharpe_ratio([o.excess for o in sample])
        windows.append(
            SharpeWindow(
                window_months=window_months,
                period_start=(opening_boundary if start == 0 else excess[start - 1].month_end),
                period_end=sample[-1].month_end,
                n_observations=len(sample),
                sharpe=ratio,
                annualized_sharpe=(None if ratio is None else annualize_sharpe(ratio)),
            )
        )
    return windows
