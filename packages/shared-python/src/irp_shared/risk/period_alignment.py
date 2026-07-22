"""Appraisal-period ↔ factor-return frequency alignment (shared helper).

The convention (PA-3, `MF-1` frequency disclosure): to regress an appraisal-period series on a
public factor whose returns are captured at a finer (typically daily) cadence, each period's
regressor is the factor's captured SIMPLE returns COMPOUNDED over the HALF-OPEN window
``(period_start, period_end]``. This module holds that convention as ONE shared, tested helper.

Extracted at PPF-1 (OD-PPF-1-C, behavior-preserving) from ``risk/proxy_weight_service.py`` — the
pure-private factor construction (PPF-1) reuses the IDENTICAL alignment to subtract the
proxy-implied return from a member's desmoothed appraisal return, so the two consumers must share
one definition rather than drift two module-private copies. ``proxy_weight_service`` now delegates
its ``_compound`` + per-period window-compounding here; the cadence is deliberately NOT ``daily`` —
any captured cadence compounds through the same window (HG-1 already feeds it quarterly returns).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal, localcontext

#: The compounding precision (prec-50; the caller quantizes nothing — the raw value feeds the
#: kernel/estimator). Kept equal to ``proxy_weight_service._CTX_PRECISION`` by construction.
COMPOUND_PRECISION = 50


def compound_simple_returns(returns: Iterable[Decimal]) -> Decimal:
    """Compound a set of SIMPLE returns: ``prod(1 + r) - 1`` at :data:`COMPOUND_PRECISION`. An
    empty set compounds to ``0`` (the multiplicative identity minus one) — callers that require
    coverage must gate on it BEFORE calling (the P3-7 named-gap rule; NO zero-fill by stealth)."""
    with localcontext() as ctx:
        ctx.prec = COMPOUND_PRECISION
        acc = Decimal(1)
        for r in returns:
            acc *= Decimal(1) + r
        return acc - Decimal(1)


def covering_returns(
    returns: Iterable[tuple[date, Decimal]], *, period_start: date, period_end: date
) -> list[Decimal]:
    """The values of ``returns`` whose date falls in the HALF-OPEN window
    ``(period_start, period_end]`` — the alignment window, verbatim."""
    return [value for (rdate, value) in returns if period_start < rdate <= period_end]


def compound_over_window(
    returns: Iterable[tuple[date, Decimal]], *, period_start: date, period_end: date
) -> Decimal:
    """Compound a factor's ``(date, value)`` returns over ``(period_start, period_end]`` — the
    per-period regressor. Convenience over :func:`covering_returns` +
    :func:`compound_simple_returns`."""
    return compound_simple_returns(
        covering_returns(returns, period_start=period_start, period_end=period_end)
    )
