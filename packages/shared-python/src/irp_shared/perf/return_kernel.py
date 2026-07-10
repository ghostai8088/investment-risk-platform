"""Pure portfolio-return kernel (PM-1, ENT-053 — time-weighted return, Modified-Dietz v1).

NO DB, NO I/O — the GIPS-2020 return math over caller-supplied valuation boundaries:

    per sub-period i:  r_i = (EMV_i - BMV_i - F_i) / (BMV_i + Σ_j w_ij·F_ij)   (Modified Dietz)
                       w_ij = (CD_i - D_ij) / CD_i                              (end-of-day weight)
    cumulative:        R    = Π_i (1 + r_i) - 1                                 (geometric linking)

where ``BMV``/``EMV`` are the sub-period begin/end market values, ``F_ij`` the signed external
flows (contribution +, withdrawal -), ``D_ij`` the calendar days from the sub-period START to the
flow (end-of-day convention => a flow present for ``CD - D`` of the period's ``CD`` days), and
``F_i = Σ_j F_ij``. Computed in ``Decimal`` at 50-digit context precision; ``return_value`` is
``quantize_HALF_UP`` to 12dp (the ``Numeric(20,12)`` DECIMAL-fraction return scale — NOT a currency
amount). UNANNUALIZED.

**No-flow reduction:** with ``F_i = 0`` the estimator is EXACTLY ``EMV_i/BMV_i - 1`` — a true
time-weighted sub-period return (test-pinned). **Valuation-at-flow is the caller's lever** (supply
a run boundary at the flow date and Dietz never applies to that flow); Dietz is the declared
within-sub-period fallback (GIPS's own hierarchy).

``BMV > 0`` and the average-capital denominator ``> 0`` are PRECONDITIONS — a return over
zero/negative average capital is meaningless (Bacon): the BINDER refuses these PRE-create; the
kernel re-checks so the pure function is safe standalone (defense-in-depth).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

#: Result quantum: HALF_UP to 12dp = the ``portfolio_return_result.return_value`` Numeric(20,12)
#: fraction scale (a return, NOT currency).
_RESULT_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision for the accumulation + linking (the risk-kernel precedent).
_COMPUTE_PREC = 50


class ReturnKernelError(ValueError):
    """Raised for an ill-formed input (non-positive begin MV or average-capital denominator; a
    non-positive period length; a flow dated outside its sub-period; an empty link set; a return
    magnitude beyond the 12dp result scale). Defense-in-depth: the binder adjudicates the pinned
    content PRE-create, making this unreachable through the governed path."""


@dataclass(frozen=True)
class DietzEstimate:
    """One sub-period's Modified-Dietz outcome. ``denominator`` is the average invested capital
    ``BMV + Σ w·F`` (> 0 by precondition) — carried so the binder can name a pathology without
    recomputing it."""

    return_value: Decimal
    denominator: Decimal


def dietz_denominator(
    begin_mv: Decimal,
    flows: Sequence[tuple[int, Decimal]],
    period_days: int,
) -> Decimal:
    """The Modified-Dietz average-capital denominator ``BMV + Σ_j w_ij·F_ij`` (end-of-day weights),
    computed at ``_COMPUTE_PREC``. ``flows`` is ``(day_offset, signed_amount)`` with
    ``1 <= day_offset <= period_days``. Raises :class:`ReturnKernelError` on the STRUCTURAL
    pathologies (non-positive period length, non-positive begin MV, a flow dated outside the
    sub-period) — but does **NOT** raise when the denominator itself is ``<= 0`` (the average
    capital may be non-positive for a large early withdrawal; the CALLER's pre-create gate decides,
    so it can name that pathology as a refusal rather than a crash). This is the single source of
    the weight formula (``compute_dietz_period`` and the binder's pre-create denominator gate both
    call it)."""
    if period_days <= 0:
        raise ReturnKernelError(f"sub-period length must be positive (got {period_days} days)")
    if begin_mv <= 0:
        raise ReturnKernelError(
            f"begin market value must be positive (got {begin_mv}) — a return over zero/negative "
            f"capital is undefined"
        )
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        cd = Decimal(period_days)
        weighted_flow = Decimal(0)
        for day_offset, amount in flows:
            if not 1 <= day_offset <= period_days:
                raise ReturnKernelError(
                    f"flow day-offset {day_offset} is outside the sub-period (1..{period_days})"
                )
            weight = (cd - Decimal(day_offset)) / cd  # end-of-day: present for CD - D days
            weighted_flow += weight * amount
        return begin_mv + weighted_flow


def compute_dietz_period(
    begin_mv: Decimal,
    end_mv: Decimal,
    flows: Sequence[tuple[int, Decimal]],
    period_days: int,
) -> DietzEstimate:
    """Compute one sub-period Modified-Dietz return. ``flows`` is a sequence of
    ``(day_offset, signed_amount)`` where ``day_offset`` is the calendar days from the sub-period
    START to the flow (``1 <= day_offset <= period_days``; the sub-period window is half-open
    ``(start, end]`` so a flow never lands on ``day_offset == 0``) and ``signed_amount`` is +
    contribution / - withdrawal. Raises :class:`ReturnKernelError` on the declared pathologies
    (structural, non-positive denominator, or a 12dp-magnitude overflow)."""
    denominator = dietz_denominator(begin_mv, flows, period_days)
    if denominator <= 0:
        raise ReturnKernelError(
            f"the Modified-Dietz denominator (average capital) is non-positive ({denominator})"
            f" — the return is undefined; refused"
        )
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        total_flow = Decimal(0)
        for _day_offset, amount in flows:
            total_flow += amount
        try:
            return_value = ((end_mv - begin_mv - total_flow) / denominator).quantize(
                _RESULT_QUANTUM, rounding=ROUND_HALF_UP
            )
        except InvalidOperation as exc:  # magnitude out of range at 12dp
            raise ReturnKernelError("return magnitude out of range") from exc
        return DietzEstimate(return_value=return_value, denominator=denominator)


def link_periods(returns: Sequence[Decimal]) -> Decimal:
    """Geometrically link sub-period returns: ``R = Π(1 + r_i) - 1``, ``quantize_HALF_UP`` to 12dp.
    Raises :class:`ReturnKernelError` on an empty set (there is no return to report)."""
    if not returns:
        raise ReturnKernelError("no sub-period returns to link")
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        product = Decimal(1)
        for r in returns:
            product *= Decimal(1) + r
        try:
            return (product - Decimal(1)).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ReturnKernelError("linked return magnitude out of range") from exc
