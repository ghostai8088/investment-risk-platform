"""Unified public+private-VaR kernel (PPF-3, ENT-027 consumer — pure math, no I/O, no ORM).

The §2.1 arc's final assembly. The plain family computes the FACTOR variance ``factor_var = x'Σx``
(``var_kernel``); PA-4's ``var_total_kernel`` computes the diagonal residual leg. This module adds
the PURE-PRIVATE systematic block and the unified volatility:

    Ω_pp,daily = Ω_pp / d_t                        d_t = appraisal_days · (trading/calendar)
    private_var = p'·Ω_pp,daily·p                  = Σ_s p_s²·Ω[s,s] + 2·Σ_{s<t} p_s·p_t·Ω[s,t]
    σ_unified   = √(factor_var + private_var + residual_var)

where ``residual_var`` is PA-4's diagonal leg **REPARTITIONED** — summed by the binder over ONLY
the NON-private-segment members (a private-segment member's non-public variance is in
``private_var``, so counting it in the residual too would DOUBLE-COUNT: PA-4's ``σ_e²`` is the WHOLE
non-public residual, already inside ``Var(pp)``; the verifier's blocking finding, OD-PPF-3-G).

``Ω_pp`` (PPF-2) is stored as canonical unordered pairs ``(a, b)`` with ``a ≤ b`` (lowercase-GUID
order) — the upper triangle; the quadratic form counts each off-diagonal twice. The matrix VARIANCE
de-scales by ``1/d_t`` (the covariance analog of PA-4's ``σ_e/√d_t`` on the stdev). Computed in
``Decimal`` at 50-digit context; the binder gates magnitudes and quantizes.

Fail-closed (a :class:`VarUnifiedKernelError`, mapped by the binder to a post-create committed
FAILED run — the DQ-gap mechanism) on: a non-positive de-scale period; a held segment absent from
the pinned Ω_pp diagonal (an uncovered segment would silently drop from ``private_var``); a
non-finite or negative ``private_var`` (PSD-by-construction, binder-unreachable — defense-in-depth);
a negative total variance. Kernel-unit-tested standalone incl. the two decomposition guardrails (a
lone private fund reduces to ≈ total VaR; a two-fund book differs by exactly the cross-fund term).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, localcontext

_CTX_PRECISION = 50


class VarUnifiedKernelError(ValueError):
    """A structural unified-leg failure (non-positive period, an uncovered held segment, a
    non-finite/negative private or total variance). The binder maps it to a post-create committed
    FAILED run; binder-unreachable through the governed path. ``reason`` is a stable short slug."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def daily_omega(
    omega_appraisal: Mapping[tuple[str, str], Decimal],
    appraisal_days: int,
    *,
    trading_days_per_year: int,
    calendar_days_per_year: int,
) -> dict[tuple[str, str], Decimal]:
    """De-scale an APPRAISAL-period Ω_pp (canonical ``(a, b)`` pairs) to daily on the DECLARED
    trading-day grid: ``Ω_daily = Ω_period / d_t``, ``d_t = appraisal_days·(trading/calendar)`` —
    the variance/covariance analog of PA-4's ``σ_e/√d_t`` (the whole matrix divides by ``d_t``).
    Raises on ``appraisal_days ≤ 0`` (the declared-identity floor makes this binder-unreachable)."""
    if int(appraisal_days) <= 0:
        raise VarUnifiedKernelError(
            "non-positive-period",
            f"appraisal_days {appraisal_days} is non-positive — refused",
        )
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        d_t = Decimal(int(appraisal_days)) * (
            Decimal(trading_days_per_year) / Decimal(calendar_days_per_year)
        )
        return {pair: cov / d_t for pair, cov in omega_appraisal.items()}


def private_block_variance(
    p_by_segment: Mapping[str, Decimal],
    omega_pp_daily: Mapping[tuple[str, str], Decimal],
) -> Decimal:
    """The pure-private block variance ``p'·Ω_pp,daily·p`` over the portfolio's held-segment
    sub-block. ``p_by_segment`` maps a held (lowercase) segment id -> ``p_s = Σ MV_i``;
    ``omega_pp_daily`` is the daily Ω_pp keyed by canonical ``(a, b)`` pairs (``a ≤ b``). Uses ONLY
    pairs whose BOTH segments are held (the principal sub-block); each off-diagonal counts twice.
    Raises if a held segment has no Ω_pp diagonal entry (uncovered — would silently drop), or on a
    non-finite / negative result (PSD by PPF-2 construction — defense-in-depth)."""
    held = set(p_by_segment)
    diagonal_segments = {a for (a, b) in omega_pp_daily if a == b}
    uncovered = held - diagonal_segments
    if uncovered:
        raise VarUnifiedKernelError(
            "uncovered-segment",
            f"held segments {sorted(uncovered)} are absent from the pinned Omega_pp diagonal — "
            f"the private covariance run must span every held segment",
        )
    # FULL held-pair coverage (the 4-finder MED; parity with the public leg's _adjudicate_pins). A
    # held-held OFF-DIAGONAL simply ABSENT from Omega_pp would be silently summed as zero
    # co-movement — understating the cross term that IS the unified number's value over total-VaR.
    # No zero imputation: every canonical (a, b) pair among held segments must be pinned.
    held_sorted = sorted(held)
    missing_pairs = [
        (a, b)
        for i, a in enumerate(held_sorted)
        for b in held_sorted[i + 1 :]
        if (a, b) not in omega_pp_daily
    ]
    if missing_pairs:
        raise VarUnifiedKernelError(
            "uncovered-pair",
            f"held-segment pairs {missing_pairs} are absent from the pinned Omega_pp — the private "
            f"covariance run must span every held-segment PAIR (no zero-cross-covariance impute)",
        )
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        acc = Decimal(0)
        for (a, b), cov in omega_pp_daily.items():
            if a not in held or b not in held:
                continue  # a segment the portfolio does not hold (p_s = 0)
            term = p_by_segment[a] * p_by_segment[b] * cov
            acc += term if a == b else term + term  # 2·p_a·p_b·Ω[a,b] for the off-diagonal
        if not acc.is_finite():
            raise VarUnifiedKernelError(
                "non-finite-private-variance", f"private variance {acc} is not finite — refused"
            )
        if acc < 0:
            raise VarUnifiedKernelError(
                "negative-private-variance",
                f"private variance {acc} < 0 (a non-PSD Omega_pp sub-block beyond tolerance) — "
                f"refused",
            )
        return acc


def sigma_unified(factor_var: Decimal, private_var: Decimal, residual_var: Decimal) -> Decimal:
    """The unified volatility ``√(factor_var + private_var + residual_var)`` — the three
    NON-OVERLAPPING legs (the repartition guarantees a private-segment member is in ``private_var``
    XOR ``residual_var``, never both). Raw prec-50; the binder gates + quantizes. Raises on a
    negative total variance (a non-PSD leg beyond tolerance)."""
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        total = factor_var + private_var + residual_var
        if total < 0:
            raise VarUnifiedKernelError(
                "negative-total-variance",
                f"total variance {total} < 0 (a non-PSD leg beyond tolerance) — refused",
            )
        return total.sqrt()
