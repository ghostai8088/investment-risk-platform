"""Pure rolling-risk kernel (RM-1, ENT-064 — the 21st governed number).

NO DB, NO I/O. Turns PM-1's governed ``DIETZ_PERIOD`` sub-period series into trailing-window
statistics on a CALENDAR-MONTH grid:

    monthly return   m_M = Π_{i in M}(1 + r_i) - 1        (relink the sub-periods within month M)
    rolling return   R_k = Π_{j=k-W+1}^{k}(1 + m_j) - 1   (W = window_months)
    annualized ret.  R_ann = (1 + R)^(12/W) - 1           (GIPS's geometric convention)
    rolling vol      sigma = sample_stdev_{n-1}(m_j)      (unannualized, monthly)
    annualized vol   sigma_ann = sigma_stored * sqrt(12)  (GIPS 4.A.1.j's operator)
    max drawdown     MDD = max_k[(peak_k - V_k)/peak_k]   (window-local, V_0 = 1 an observation)

All fractions at the 12dp ``Numeric(20,12)`` scale.

**Why a monthly grid at all (the crux, OD-RM-1-F).** GIPS defines the ex-post risk statistic ONLY
on the monthly series (4.A.1.j) and requires the input valued *"at least monthly"*, *"as of the
calendar month end or the last business day of the month"* (2.A.23.a/b), with sub-period returns
geometrically linked up to that grid (2.A.24.f). Sub-period returns are inputs, never the sample.
The estimator-theory corroboration (Lo Eq. 19: variance scales with interval length, so unequal sub-
periods are
heteroskedastic by construction) points the same way but is explicitly DEMOTED — calendar months are
28-31 days, so the monthly grid is itself heteroskedastic by ~5.2%. The grid is conventionalized by
the standard, not made homogeneous by mathematics. RM-1 refuses the sub-period alternative on the
STANDARDS ground, not on a false claim about its own grid.

**The alignment criterion is a THREE-condition conjunction, and each condition is load-bearing.**
The first draft stated only (3) and was *vacuous* for any series contained inside a single month —
which is how it "passed" the demo campaign's 2026-05-18 -> 05-26 span while the record's own prose
said it should refuse. (1) and (2) are what make a span PARTITIONABLE; (3) alone is not, and (3)
alone also admits a partial leading or trailing month, pooling e.g. a 16-day observation with a
28-day one whose standard deviations differ by 1.32x — the exact heteroskedastic pooling the grid
exists to prevent. A partial edge month is therefore a REFUSAL, never a silent truncation:
truncating would change the caller's requested span behind their back, and imputing a valuation is
prohibited outright.
"""

from __future__ import annotations

import calendar as _calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as dt_date
from datetime import timedelta
from decimal import Decimal, localcontext

from irp_shared.perf.return_kernel import ReturnKernelError, link_periods
from irp_shared.perf.stats_kernel import COMPUTE_PREC, quantize_result, sample_stdev

#: Months per year — the annualization basis. k = 12 is the ONLY basis RM-1 cites: GIPS's measure is
#: monthly, so sqrt(12) is grounded [V]. k = 252/52/365 are deliberately NOT carried (uncited).
MONTHS_PER_YEAR = 12


class RollingKernelError(ValueError):
    """An ill-formed rolling-risk input: a misaligned boundary grid, a return at or below -100%, or
    a window the series cannot fill. Defense-in-depth — the binder adjudicates the pinned content
    PRE-create, so these are structurally unreachable through the governed path."""


# ------------------------------------------------------------------- the month-end convention ---
def last_weekday_of_month(year: int, month: int) -> dt_date:
    """The last Mon-Fri date of a calendar month — the QS-11 ``preceding`` roll over a WEEKEND-ONLY
    non-business-day predicate.

    **Deliberately mirrored from ``scheduling.service._last_weekday_of_month`` rather than
    imported.** That module imports the entire risk + exposure compute stack to build its dispatch
    registry, so ``perf`` importing it would invert the layering for three lines of calendar
    arithmetic. Per the SCH-2 standing rule, a hand-mirrored contract carries a CONFORMANCE PIN:
    ``test_rolling_kernel`` asserts the two implementations agree across a multi-year sweep, so the
    duplication cannot silently diverge.

    No holiday substrate exists (ENT-006 ``calendar``/``calendar_holiday`` are vocabulary tables
    with no business-day logic), so a month-end landing on a market HOLIDAY is a recorded residual,
    not a handled case. A full holiday-aware convention is the recorded v2.
    """
    day = _calendar.monthrange(year, month)[1]
    candidate = dt_date(year, month, day)
    while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
        candidate -= timedelta(days=1)
    return candidate


def is_month_end(day: dt_date) -> bool:
    """Is ``day`` a month-end under GIPS 2.A.23.b — *"the calendar month end **or the last business
    day of the month**"*?

    **The second clause is load-bearing and the draft truncated it.** 2026-01-31 is a Saturday and
    2026-05-31 a Sunday, so a firm valuing on the preceding Friday is fully GIPS-conforming; a
    strict calendar-month-end gate would REFUSE a compliant book while citing GIPS as its authority.
    """
    return day.day == _calendar.monthrange(day.year, day.month)[1] or day == last_weekday_of_month(
        day.year, day.month
    )


def _month_key(day: dt_date) -> tuple[int, int]:
    return (day.year, day.month)


def _next_month(key: tuple[int, int]) -> tuple[int, int]:
    year, month = key
    return (year + 1, 1) if month == 12 else (year, month + 1)


def assert_month_aligned(boundaries: Sequence[dt_date]) -> None:
    """The THREE-condition alignment criterion (OD-RM-1-F). Raises naming the offending boundary.

    Over the ordered boundary dates ``d_0 .. d_n``, ALL of:

    1. ``d_0`` is a month-end — the span opens on a grid point, so the first measured month is
       whole;
    2. ``d_n`` is a month-end — the span closes on one, so the last measured month is whole;
    3. every calendar month strictly between them contributes a month-end boundary — no interior
       month is missing;
    4. ``d_0`` is the LAST boundary in its own month — otherwise the first measured month is a
       partial stub (see the inline note: a Friday/Saturday month-end pair admits a ONE-DAY
       "month");
    5. every measured month CLOSES on a month-end — intra-month boundaries relink, but a month may
       not end on a non-grid date.

    Extra INTRA-month boundaries are explicitly fine: they are relinked into their month by
    :func:`relink_to_months`. The criterion constrains which months are *represented*, never how
    many boundaries a month may contain.
    """
    if len(boundaries) < 2:
        raise RollingKernelError(
            f"a rolling series needs at least 2 boundaries (got {len(boundaries)})"
        )
    ordered = list(boundaries)
    if any(later <= earlier for earlier, later in zip(ordered, ordered[1:], strict=False)):
        raise RollingKernelError("boundaries must be strictly increasing")

    first, last = ordered[0], ordered[-1]
    # (1) and (2): a partial leading/trailing month is a REFUSAL, not a truncation.
    if not is_month_end(first):
        raise RollingKernelError(
            f"the series opens on {first}, which is not a month end — a partial first month would "
            "pool a short observation with whole ones (refused, never truncated)"
        )
    if not is_month_end(last):
        raise RollingKernelError(
            f"the series closes on {last}, which is not a month end — a partial last month would "
            "pool a short observation with whole ones (refused, never truncated)"
        )

    # A span must cover at least ONE whole month. Without this the loop below still refuses (its
    # first probe misses), but it blames "a missing interior month" — a misleading reason for a
    # span that measures nothing at all. It is also the only shape that could make the month walk
    # below unbounded, so the guard is explicit rather than incidentally-correct.
    if _month_key(last) <= _month_key(first):
        raise RollingKernelError(
            f"the span {first} -> {last} does not cover a whole calendar month: both boundaries "
            "fall in the same month, so there is nothing to measure"
        )

    # (4) d_0 must be the LAST boundary in its own month — the ratified rule said so ("d_0 is the
    # last boundary of the month preceding the first measured month") and the first implementation
    # only checked that d_0 IS a month-end. That is not the same thing, because `is_month_end`
    # accepts BOTH the last weekday AND the weekend calendar end, so ONE month can hold two of
    # them. Executed counterexample, admitted by the first version: 2026-01-30 (Friday, the last
    # business day) followed by 2026-01-31 (Saturday, the calendar end) — condition (1) passes on
    # d_0 and the relink then emits a ONE-DAY "January" observation, which is pooled into sigma,
    # x sqrt(12), the drawdown and the 12-month return. The dispersion ratio against a 31-day month
    # is sqrt(31) ~ 5.6x — five times worse than the 1.32x partial-edge case that conditions (1)
    # and (2) exist to prevent.
    if any(d in ordered[1:] and _month_key(d) == _month_key(first) for d in ordered[1:]):
        offender = next(d for d in ordered[1:] if _month_key(d) == _month_key(first))
        raise RollingKernelError(
            f"the opening boundary {first} is not the LAST boundary in its month ({offender} also "
            "falls there) — the first measured month would be a partial stub, not a whole month"
        )

    # (5) the last boundary in every measured month must itself be a month-end. Intra-month
    # boundaries are still welcome (they relink); what is refused is a month that CLOSES on one.
    # Same root cause as (4) at the other end: 2026-05-29 (last weekday) followed by 2026-05-30
    # (a Saturday, NOT a month end) would otherwise make May's observation close on a non-grid
    # date, and that date is then stamped into governed rows as `period_end`.
    last_in_month: dict[tuple[int, int], dt_date] = {}
    for day in ordered[1:]:
        last_in_month[_month_key(day)] = day
    for key, day in last_in_month.items():
        if not is_month_end(day):
            raise RollingKernelError(
                f"{key[0]}-{key[1]:02d} closes on {day}, which is not a month end — a measured "
                "month must close on a grid point"
            )

    # (3): every interior calendar month must contribute a month-end boundary.
    month_ends = {_month_key(d) for d in ordered if is_month_end(d)}
    key, stop = _next_month(_month_key(first)), _month_key(last)
    while key != stop:
        if key not in month_ends:
            raise RollingKernelError(
                f"no month-end boundary for {key[0]}-{key[1]:02d} — an interior month is missing, "
                "so the span cannot be partitioned into whole months"
            )
        key = _next_month(key)


# ------------------------------------------------------------------------------ the relink -----
@dataclass(frozen=True)
class SubPeriod:
    """One pinned PM-1 ``DIETZ_PERIOD`` row, reduced to what the grid needs."""

    period_start: dt_date
    period_end: dt_date
    return_value: Decimal


@dataclass(frozen=True)
class MonthlyReturn:
    """One relinked calendar-month observation — the sample every statistic below is computed on."""

    month_end: dt_date
    value: Decimal
    n_sub_periods: int


def relink_to_months(sub_periods: Sequence[SubPeriod]) -> list[MonthlyReturn]:
    """Geometrically link the sub-periods falling in each calendar month (GIPS 2.A.24.f).

    Grouped by the month of ``period_end`` — the month a sub-period's return is *realized into*.
    Contiguity is structural rather than assumed: RM-1 consumes exactly ONE PM-1 run, and PM-1
    builds sub-periods from consecutively-ordered distinct boundaries, so
    ``period_end_i == period_start_{i+1}`` holds by construction.

    A month holding exactly one sub-period is safe: ``link_periods`` on a single element is
    bit-identically the identity, because ``quantize((1+r)-1)`` is idempotent on 12dp input.
    """
    if not sub_periods:
        raise RollingKernelError("no sub-periods to relink")
    ordered = sorted(sub_periods, key=lambda p: p.period_end)
    grouped: dict[tuple[int, int], list[SubPeriod]] = {}
    for period in ordered:
        grouped.setdefault(_month_key(period.period_end), []).append(period)

    months: list[MonthlyReturn] = []
    for key in sorted(grouped):
        bucket = grouped[key]
        try:
            linked = link_periods([p.return_value for p in bucket])
        except ReturnKernelError as exc:
            # The linked product left the 12dp envelope. Surfaced as OUR error so the binder does
            # not have to catch a foreign class to convert it into a committed FAILED run.
            raise RollingKernelError(
                f"relinking {key[0]}-{key[1]:02d} left the result envelope: {exc}"
            ) from exc
        months.append(
            MonthlyReturn(month_end=bucket[-1].period_end, value=linked, n_sub_periods=len(bucket))
        )
    return months


def assert_above_total_loss(months: Sequence[MonthlyReturn]) -> None:
    """The ``1 + m_j > 0`` precondition (OD-RM-1-H). Raises naming the offending month.

    **The measure is otherwise UNDEFINED on a reachable input.** PM-1's only value gates are
    ``BMV > 0`` and ``denominator > 0``, so ``EMV = 0`` is legal and yields exactly
    ``-1.000000000000``; ``link_periods`` has no ``1+r > 0`` guard, so a ``-1`` is ABSORBING. And a
    month below -100% is reachable via a large late ``TRANSFER_IN`` under PM-1's own recorded
    no-cash-ledger limitation. Consequences if unguarded, all three real:

    - the wealth index hits zero and stays there;
    - the ratio-to-peak EXCEEDS 1 (a "150% drawdown"), and a further loss can make the reported
      drawdown SMALLER — the response inverts sign;
    - ``(1+R) ** (12/W)`` raises ``InvalidOperation`` on a negative base — an uncaught 500.

    This is NOT the magnitude gate: ``-1`` sits well inside ``_MAX_RESULT_ABS = 1E7``. A total-loss
    book therefore cannot carry a governed drawdown — recorded as a first-class limitation rather
    than allowed to become a 500.
    """
    for month in months:
        if month.value <= Decimal(-1):
            raise RollingKernelError(
                f"month ending {month.month_end} returned {month.value} (at or below -100%): the "
                "wealth index is absorbing and the drawdown ratio is undefined — refused"
            )


# ------------------------------------------------------------------------ drawdown + windows ---
def max_drawdown(returns: Sequence[Decimal]) -> Decimal:
    """Maximum drawdown over a WINDOW-LOCAL compounded wealth index, as a non-negative fraction.

    Two choices the draft left unspecified, both now declared (OD-RM-1-H):

    - **Window-local rebasing.** ``V`` is rebased to 1 at the window's opening boundary and the peak
      is taken over observations WITHIN the window only. A run-global peak would import a high-water
      mark from outside and report a "12-month maximum drawdown" for a drawdown that did not happen
      in those 12 months. **``MDD_36 >= MDD_12`` does NOT prove this choice** (an earlier comment
      claimed it did): under a run-global peak the drawdown at each point is window-independent, so
      that inequality holds under BOTH conventions. What discriminates is a window opening while
      the book is already BELOW an earlier run peak — see
      ``test_the_drawdown_is_WINDOW_LOCAL_not_run_global``.
    - **The base point IS an observation.** ``V_0 = 1`` with ``DD_0 = 0`` (Chekhlov's ``w_0`` /
      ``xi_0`` treatment). Omitting it makes a window that OPENS on a loss report zero: for -10%
      then eleven +1% months, including ``V_0`` gives 0.10 and omitting it gives 0.00 — a 10pp error
      that turns
      a real drawdown into a value indistinguishable from "no drawdown".

    Running peak, no look-ahead (Magdon-Ismail Eq. 1 / Chekhlov Def. 3.1-3.2 on a level path).

    **Post-condition ``0 <= MDD <= 1`` is asserted, not inherited.** Chekhlov Prop. 3.1 proves
    non-negativity for the ABSOLUTE drawdown on an UNCOMPOUNDED cumulative return, and the paper
    explicitly disclaims the relative form — which is what RM-1 emits, on a compounded base. So this
    is RM-1's own invariant, provable only under :func:`assert_above_total_loss`.
    """
    if not returns:
        raise RollingKernelError("no returns for a drawdown")
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        level = Decimal(1)  # V_0 — an OBSERVATION, not merely a starting scale
        peak = Decimal(1)
        worst = Decimal(0)
        for value in returns:
            level *= Decimal(1) + value
            if level > peak:
                peak = level
            drawdown = (peak - level) / peak
            if drawdown > worst:
                worst = drawdown
        result = quantize_result(worst)
    if not (Decimal(0) <= result <= Decimal(1)):
        raise RollingKernelError(
            f"drawdown post-condition violated: {result} is outside [0, 1] — the 1+m>0 "
            "precondition must have been skipped"
        )
    return result


def annualize_volatility(monthly_sigma: Decimal) -> Decimal:
    """``sigma_ann = quantize(sigma_STORED * sqrt(12))`` — GIPS 4.A.1.j's operator [V].

    **The order is declared and load-bearing (V1-M13).** The multiplication reads the already-
    quantized 12dp STORED value, not an unquantized intermediate, so the emitted pair reconciles
    EXACTLY by construction — a consumer can multiply the unannualized row by sqrt(12) and land on
    the annualized row. That costs <=2 ulp at 12dp against a single-quantization path, accepted
    because it is what makes emitting both rows honest rather than merely redundant.
    """
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        return quantize_result(monthly_sigma * Decimal(MONTHS_PER_YEAR).sqrt())


def annualize_return(cumulative: Decimal, window_months: int) -> Decimal:
    """``R_ann = (1 + R)^(12/W) - 1`` — GIPS's geometric convention [V].

    GIPS 2.A.12 is a hard MUST NOT: *"Returns for periods of less than one year must not be
    annualized."* **Where that is actually enforced is the REGISTERED PARAMETER DOMAIN** ({12, 36}),
    not this guard — under that domain no governed caller can reach ``W < 12``, so calling the check
    below "the invariant" would be a vacuous control. It is honest defense-in-depth and labelled as
    such. (Twelve consecutive month-ends span exactly 365/366 days, so expressing the one-year
    threshold in months is coherent — though note the supporting arithmetic often quoted for it,
    "twelve consecutive month-ends span exactly 365/366 days", is FALSE under this module's own
    last-weekday convention: 2026-01-30 to 2027-01-29 is 364 days. The conclusion rests on GIPS's
    monthly convention, not on the day count.)

    At ``W == 12`` the exponent is exactly 1 and the annualized return is DEFINITIONALLY the
    cumulative return — which is why the binder suppresses that row rather than shipping two
    always-identical governed numbers.
    """
    if window_months < MONTHS_PER_YEAR:
        raise RollingKernelError(
            f"refusing to annualize a {window_months}-month return: GIPS 2.A.12 forbids "
            "annualizing periods of less than one year"
        )
    base = Decimal(1) + cumulative
    if base <= 0:
        raise RollingKernelError(
            "cannot annualize a return at or below -100% (the 1+m>0 precondition was skipped)"
        )
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        exponent = Decimal(MONTHS_PER_YEAR) / Decimal(window_months)
        return quantize_result(base**exponent - Decimal(1))


@dataclass(frozen=True)
class RollingWindow:
    """One evaluated trailing window: its span, its sample, and the three statistics."""

    window_months: int
    period_start: dt_date  # the OPENING boundary (the V_0 observation's date)
    period_end: dt_date
    n_observations: int
    cumulative_return: Decimal
    annualized_return: Decimal | None  # None at W == 12 (definitionally the cumulative return)
    volatility: Decimal
    annualized_volatility: Decimal
    max_drawdown: Decimal


def rolling_windows(
    months: Sequence[MonthlyReturn],
    window_months: int,
    *,
    opening_boundary: dt_date,
) -> list[RollingWindow]:
    """Every COMPLETE trailing window of ``window_months`` over the relinked monthly series.

    Incomplete windows are NOT emitted here — the binder emits a governed *suppressed* row for them
    instead (a nullable value plus an explicit flag, never a stuffed zero, since 0 is a legitimate
    value for all three statistics). ``opening_boundary`` is ``d_0``: the boundary that closes the
    month BEFORE the first measured month, and therefore the ``period_start`` of the first window.
    """
    if window_months < 2:
        raise RollingKernelError(f"window_months must be >= 2 (got {window_months})")
    windows: list[RollingWindow] = []
    for end in range(window_months - 1, len(months)):
        start = end - window_months + 1
        sample = months[start : end + 1]
        values = [m.value for m in sample]
        cumulative = link_periods(values)
        sigma = sample_stdev(values)
        windows.append(
            RollingWindow(
                window_months=window_months,
                # The opening boundary is the PRIOR month's close — d_0 for the first window.
                period_start=(opening_boundary if start == 0 else months[start - 1].month_end),
                period_end=sample[-1].month_end,
                n_observations=len(values),
                cumulative_return=cumulative,
                annualized_return=(
                    None
                    if window_months == MONTHS_PER_YEAR
                    else annualize_return(cumulative, window_months)
                ),
                volatility=sigma,
                annualized_volatility=annualize_volatility(sigma),
                max_drawdown=max_drawdown(values),
            )
        )
    return windows
