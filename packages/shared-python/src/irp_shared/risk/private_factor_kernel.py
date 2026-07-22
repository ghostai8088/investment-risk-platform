"""Pure-private factor-return kernel (PPF-1, ENT-060 — the pooling math).

The pure-private return of a segment for one appraisal period is the equal-weight mean, across the
segment's members, of each member's DESMOOTHED return MINUS its proxy-implied return (the MSCI PE
Factor Model "pure private" leg; Shepard 2014/2025). All arithmetic is exact Decimal at a 50-digit
context; the binder quantizes the persisted echo to 12dp.

- ``member_pure_private_return`` = ``desmoothed - Σ_f w_f · R_f`` for one member-period (the factor
  returns already compounded over the period window by the shared alignment helper).
- ``pool_equal_weight`` = the arithmetic mean across members (RETAIN-alpha convention: the mean
  out-of-proxy return, a genuine source of risk AND return, stays IN the factor — OQ-PPF-1-3=A).
- ``sample_stdev`` = the summary row's pooled-return dispersion (n-1 sample stdev; a single period
  yields 0 by convention, honestly disclosed alongside the member/period counts).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, localcontext

#: Compute precision (matches the alignment helper + the OLS kernel context).
_CTX_PRECISION = 50


class PurePrivateKernelError(Exception):
    """A structural refusal in the pooling math (empty member set for a period, or a blend/return
    misalignment the binder did not catch). Raised BEFORE any persistence."""


def member_pure_private_return(
    desmoothed_return: Decimal, blend: Sequence[tuple[Decimal, Decimal]]
) -> Decimal:
    """One member-period pure-private return: ``desmoothed - Σ (weight · factor_return)``. ``blend``
    is the member's ``(weight, compounded_factor_return)`` pairs for this period (one per public
    factor in its REGRESSION blend). An empty blend is a caller error (a blend-less member is a
    named-gap refusal at the binder / builder — never reaches here)."""
    if not blend:
        raise PurePrivateKernelError("member has no blend for the period — refused")
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        implied = Decimal(0)
        for weight, factor_return in blend:
            implied += weight * factor_return
        return desmoothed_return - implied


def pool_equal_weight(member_returns: Sequence[Decimal]) -> Decimal:
    """Equal-weight mean of the members' pure-private returns for one period (OQ-PPF-1-2=A). The
    caller guarantees ``member_returns`` is non-empty (the min-members gate)."""
    if not member_returns:
        raise PurePrivateKernelError("no member returns to pool for the period — refused")
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        total = Decimal(0)
        for r in member_returns:
            total += r
        return total / Decimal(len(member_returns))


def sample_stdev(values: Sequence[Decimal]) -> Decimal:
    """The n-1 sample standard deviation of the pooled series (the summary row's dispersion). A
    single observation yields ``0`` by convention (disclosed alongside the period count — thin, not
    hidden). Exact Decimal; the caller quantizes the persisted echo."""
    n = len(values)
    if n <= 1:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        mean = sum(values, Decimal(0)) / Decimal(n)
        ss = sum(((v - mean) * (v - mean) for v in values), Decimal(0))
        return (ss / Decimal(n - 1)).sqrt()
