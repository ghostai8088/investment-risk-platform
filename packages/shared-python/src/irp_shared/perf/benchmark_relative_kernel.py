"""Pure ex-post benchmark-relative kernel (P3-8, ENT-054 — realized active return / TE / TD / IR).

NO DB, NO I/O — the realized performance statistics over ALIGNED per-sub-period return pairs:

    active return   a_i = r_p,i - r_b,i                              (arithmetic; the TE input)
    tracking diff   TD  = R_p - R_b   where R = Π_i(1 + r_i) - 1     (compounded difference)
    tracking error  TE  = sample_stdev_{n-1}(a_1..a_n)               (ESMA ex-post; unbiased sample)
    information rat. IR  = mean(a_i) / TE                            (Grinold-Kahn)

All UNANNUALIZED. Computed in ``Decimal`` at 50-digit context; results ``quantize_HALF_UP`` to 12dp
(the ``Numeric(20,12)`` fraction/ratio scale — NOT a currency). The ESMA disclosure TE is typically
ANNUALIZED; the deviation is DECLARED (the methodology doc labels these figures so they cannot be
conflated with the UCITS disclosure numbers).

Conditional statistics (the binder decides emission): ``sample_stdev`` REQUIRES ``n >= 2`` (a
1-observation volatility is not a statistic); ``information_ratio`` is UNDEFINED when ``TE == 0`` (a
perfectly-tracking book is a legitimate input — the binder OMITS the IR row, never fabricates it).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from irp_shared.perf.return_kernel import ReturnKernelError, link_periods

#: Result quantum: HALF_UP to 12dp = the ``benchmark_relative_result.metric_value`` Numeric(20,12)
#: fraction/ratio scale.
_RESULT_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision for compounding + the variance accumulation (the return-kernel precedent).
_COMPUTE_PREC = 50


class BenchmarkRelativeKernelError(ValueError):
    """Raised for an ill-formed input (empty compound set; mismatched active-series lengths; a
    sub-two-observation standard deviation; a zero-TE information ratio; a magnitude beyond the 12dp
    result scale). Defense-in-depth: the binder adjudicates the pinned content PRE-create, making
    the structural cases unreachable through the governed path."""


def _quantize(value: Decimal) -> Decimal:
    try:
        return value.quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:  # magnitude out of range at 12dp
        raise BenchmarkRelativeKernelError("result magnitude out of range") from exc


def compound_returns(returns: Sequence[Decimal]) -> Decimal:
    """Geometrically compound a per-sub-period return series: ``R = Π(1 + r_i) - 1``,
    ``quantize_HALF_UP`` to 12dp. DELEGATES to PM-1's :func:`~irp_shared.perf.return_kernel
    .link_periods` — the binder's exact-linkage cross-check demands the recomputed link EQUAL the
    ``TWR_LINKED`` value PM-1 produced with that function, so sharing ONE implementation makes the
    bit-identical coupling structural, not conventional. Raises
    :class:`BenchmarkRelativeKernelError` on an empty set (a period with no returns has no
    compounded value — the binder refuses a zero-observation window upstream) and on a magnitude
    past the 12dp result scale."""
    if not returns:
        raise BenchmarkRelativeKernelError("no returns to compound")
    try:
        return link_periods(returns)
    except ReturnKernelError as exc:
        raise BenchmarkRelativeKernelError(str(exc)) from exc


def active_series(portfolio: Sequence[Decimal], benchmark: Sequence[Decimal]) -> list[Decimal]:
    """The per-sub-period arithmetic active returns ``a_i = r_p,i - r_b,i``, each
    ``quantize_HALF_UP`` to 12dp (the stored ``ACTIVE_RETURN`` values — the TE/IR estimators read
    exactly these, so the series and its statistics are mutually consistent). Raises
    :class:`BenchmarkRelativeKernelError` on a length mismatch (the sub-periods must align 1:1)."""
    if len(portfolio) != len(benchmark):
        raise BenchmarkRelativeKernelError(
            f"active-series length mismatch (portfolio {len(portfolio)} vs benchmark "
            f"{len(benchmark)})"
        )
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        return [_quantize(p - b) for p, b in zip(portfolio, benchmark, strict=True)]


def mean_return(values: Sequence[Decimal]) -> Decimal:
    """The arithmetic mean of a return series, ``quantize_HALF_UP`` to 12dp. Raises on an empty
    set."""
    if not values:
        raise BenchmarkRelativeKernelError("no values to average")
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        total = sum(values, Decimal(0))
        return _quantize(total / Decimal(len(values)))


def sample_stdev(values: Sequence[Decimal]) -> Decimal:
    """The unbiased SAMPLE standard deviation (``n - 1`` denominator) of the active returns — the
    ESMA ex-post tracking-error estimator (the P3-4 unbiased-sample precedent). Computed at 50-digit
    precision (mean + variance internally UNquantized so the deviation is faithful), then
    ``sqrt`` + ``quantize_HALF_UP`` to 12dp. Raises :class:`BenchmarkRelativeKernelError` when
    ``n < 2`` (a 1-observation volatility is undefined)."""
    n = len(values)
    if n < 2:
        raise BenchmarkRelativeKernelError(
            f"tracking error needs >= 2 sub-period observations (got {n})"
        )
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        mean = sum(values, Decimal(0)) / Decimal(n)
        variance = sum(((v - mean) ** 2 for v in values), Decimal(0)) / Decimal(n - 1)
        return _quantize(variance.sqrt())


def information_ratio(mean_active: Decimal, tracking_error: Decimal) -> Decimal:
    """``IR = mean(active) / TE`` (Grinold-Kahn), ``quantize_HALF_UP`` to 12dp. Raises
    :class:`BenchmarkRelativeKernelError` when ``TE == 0`` (the ratio is undefined — the binder
    OMITS the IR row for a perfectly-tracking book, never fabricates a value)."""
    if tracking_error == 0:
        raise BenchmarkRelativeKernelError("information ratio is undefined for zero tracking error")
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        return _quantize(mean_active / tracking_error)
