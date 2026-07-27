"""Domain-neutral descriptive statistics for the ``perf`` family (lifted at RM-1, OD-RM-1-M).

NO DB, NO I/O. Two estimators over a ``Decimal`` return series — the arithmetic mean and the
unbiased-**variance** (``n-1``) standard deviation — computed at 50-digit precision with the mean
and variance held UNquantized internally, then ``quantize_HALF_UP`` to 12dp (the ``Numeric(20,12)``
fraction scale shared by every ``perf`` result column).

**Why this module exists.** Both estimators were born inside ``benchmark_relative_kernel`` (P3-8)
and were already being borrowed across families before RM-1: ``desmoothing_service`` (DS-2) imports
``sample_stdev`` from it directly. RM-1 would have been the third borrower. Reusing them *in place*
imports a foreign error class — ``BenchmarkRelativeKernelError`` — carrying a message about
*"tracking error"* over *"sub-period observations"*, a metric RM-1 does not compute on a grain it
has deliberately abandoned. That breaks the family's own rule that *"a perf number never borrows a
risk error"* and repeats the API-2 error-map lesson.

So the implementation moves here ONCE, with neutral messages and a neutral error class, and each
family keeps its own error type at its own boundary: ``benchmark_relative_kernel`` re-wraps these in
``BenchmarkRelativeKernelError`` (preserving its shipped messages verbatim, so P3-8's contract is
byte-unchanged), and RM-1 pre-checks its preconditions binder-side so the raise below stays
structurally unreachable through the governed path.

**On the error base class.** ``StatsKernelError`` is a ``ValueError``, matching every other kernel
error in this package (``ReturnKernelError``, ``BenchmarkRelativeKernelError``). It is deliberately
NOT an ``ArithmeticError``: DS-2's ``except ArithmeticError`` idiom would then catch a *structural*
input error (an empty series, a one-observation sample) and convert it into a silent suppression,
which is the opposite of fail-closed. Structural errors are the binder's job to prevent, not the
caller's to swallow.

**The estimator's disclosed conventions** (mirrored into RM-1's ``model_assumption`` rows):
``n-1`` gives an unbiased **variance**; its square root is a **downward-biased** estimator of sigma
by ``1 - c4(n)`` — about **2.24% at n=12**. GIPS and CFA Institute both use the square root of the
``n-1`` variance and neither applies a ``c4`` correction, so this follows them. The choice between
``n`` and ``n-1`` is not prescribed by GIPS and is material: ``sqrt(n/(n-1)) - 1`` is **+4.45% at
n=12** and +1.42% at n=36. Centring is the **arithmetic** mean even though returns are linked
geometrically — an internal tension in the standard, documented rather than silently resolved.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

#: Result quantum: HALF_UP to 12dp — the shared ``perf`` Numeric(20,12) fraction/ratio scale.
RESULT_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision for the mean + variance accumulation (the return-kernel precedent).
COMPUTE_PREC = 50


class StatsKernelError(ValueError):
    """An ill-formed statistical input: an empty series, or a sample too small for the estimator.

    Domain-neutral by design — it names the ESTIMATOR's precondition, never a metric. A caller that
    needs a family-specific error re-wraps at its own boundary.
    """


def quantize_result(value: Decimal) -> Decimal:
    """``quantize_HALF_UP`` to the 12dp result scale, converting an out-of-range magnitude into a
    clean :class:`StatsKernelError` rather than letting ``InvalidOperation`` escape from the wrong
    layer."""
    try:
        return value.quantize(RESULT_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise StatsKernelError("result magnitude out of range at the 12dp scale") from exc


def mean_return(values: Sequence[Decimal]) -> Decimal:
    """The arithmetic mean of a series, ``quantize_HALF_UP`` to 12dp.

    Raises :class:`StatsKernelError` on an empty series (a mean over no observations is undefined —
    it is not zero).
    """
    if not values:
        raise StatsKernelError("cannot take the mean of an empty series")
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        total = sum(values, Decimal(0))
        return quantize_result(total / Decimal(len(values)))


def sample_stdev(values: Sequence[Decimal]) -> Decimal:
    """The sample standard deviation on the unbiased-**variance** (``n-1``) denominator, centred on
    the arithmetic mean, ``quantize_HALF_UP`` to 12dp.

    The mean and the variance are accumulated UNquantized at 50-digit precision so the deviation is
    faithful; only the final square root is quantized. Raises :class:`StatsKernelError` when
    ``n < 2`` — a one-observation dispersion is undefined, not zero, and emitting ``0`` would be
    indistinguishable from a genuinely constant series.
    """
    n = len(values)
    if n < 2:
        raise StatsKernelError(f"standard deviation needs >= 2 observations (got {n})")
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        mean = sum(values, Decimal(0)) / Decimal(n)
        variance = sum(((v - mean) ** 2 for v in values), Decimal(0)) / Decimal(n - 1)
        return quantize_result(variance.sqrt())
