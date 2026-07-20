"""Pure Acerbi-Szekely ES-backtest kernel (BT-3, ENT-055 extension — the Z̄1/Z̄2 statistics).

NO DB, NO I/O — the AS (2014) outcomes-analysis statistics over aligned per-day triples
``(realized P&L X_t, VaR_t, ES_t)`` (forecasts POSITIVE numbers; X negative on loss):

    exception       I_t = 1  iff  X_t + VaR_t < 0            (STRICT — the shipped BT-1 indicator)
    Z-bar-2         (1/(T·a)) · Σ_t X_t·I_t/ES_t  +  1       (unconditional; a = 1 − confidence)
    Z-bar-1         (1/N_T)  · Σ_t X_t·I_t/ES_t  +  1        (conditional; N_T = Σ I_t;
                                                   UNDEFINED at N_T = 0 — returned as None, never 0)
    verdict         REJECT iff Z-bar-2 < Z2_CRITICAL[significance]   (one-sided LEFT tail; fixed
                                                              registered constants — NO simulation)

Formula provenance (BT-3 Part 2, the three-route bar): Z̄2 verbatim in Zeliade zwp-011 §3.2.1 +
Lund (Fredriksson-Johansson) + Moldenhauer-Pitera arXiv:1709.01337 Eq. 6.2; Z̄1 in Lund +
MathWorks (vendor) with the '+1' grouping SETTLED by the null-expectation identity
(``E[X | X < −VaR] = −ES`` ⇒ the '+1' sits OUTSIDE the sum; an inside-denominator '+1' evaluates
to ``−ES/(ES+1)`` ≈ −0.7004 at N(0,1)/a=0.025 — numerically COINCIDING with the −0.70 critical,
which is why the identity regression in the suite is load-bearing, not decorative).

Under H0, ``E[Z̄2] = 0`` and ``E[Z̄1 | N_T > 0] = 0``; negative values indicate risk
UNDERSTATEMENT. ONE-SIDED by construction: over-conservatism is invisible to these statistics
(a registered limitation — the deliberate break with the two-sided Kupiec POF).

The verdict criticals are DOMAIN-BOUND: −0.70 (5%) / −1.8 (0.01%) are AS's simulated left-tail
quantiles at **tail a = 0.025 (confidence 0.9750), T = 250 pairs, near-normal tails** — they are
α-, T-, AND df-dependent (executed at planning: ≈ −1.56 at a=0.005/T=250; ≈ −3.68 at
a=0.025/T=10; −0.82/−4.4 at Student-t3). The BINDER enforces the (0.9750, 250) domain gate
(the Basel-zone precedent); this kernel is the pure arithmetic. Extending the critical set is a
NEW model version, never silent.

Computed in ``Decimal`` at 50-digit context; quantize_HALF_UP to 12dp.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from irp_shared.risk.var_backtest_kernel import exception_indicator

#: Statistic quantum: HALF_UP to 12dp (the BT-1 kernel convention).
_Z_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision (the perf/risk kernel precedent).
_COMPUTE_PREC = 50

#: Fixed Z̄2 left-tail critical values for the DECLARED significance set (OD-BT-3-B) — valid
#: ONLY at (paired confidence 0.9750, n_pairs 250, near-normal tails); the binder gates the
#: domain. Three-route provenance: M-P attribution + Lund Table 1 + the planning pass's executed
#: seeded MC (−0.7001 / −1.78 ± 0.03 at exactly this configuration). Extending the set (or any
#: other (α, T) cell) is a NEW model version under a governed derivation record.
Z2_CRITICALS: dict[Decimal, Decimal] = {
    Decimal("0.05"): Decimal("-0.70"),
    Decimal("0.0001"): Decimal("-1.8"),
}

ES_DECISION_REJECT = "REJECT"
ES_DECISION_FAIL_TO_REJECT = "FAIL_TO_REJECT"


class EsBacktestKernelError(ValueError):
    """Raised for an ill-formed input (no pairs; a tail probability outside (0, 1); a
    non-positive ES forecast; a negative VaR forecast; a significance outside the declared
    critical set). Defense-in-depth: the binder adjudicates the pinned content PRE-create,
    making the structural cases unreachable through the governed path."""


@dataclass(frozen=True)
class AsZStatistics:
    """The AS statistics over one aligned paired series. ``z1`` is ``None`` iff the series has
    ZERO exceptions — the conditional statistic is UNDEFINED there (division by the exception
    count), never coerced to a number."""

    z2: Decimal
    z1: Decimal | None
    n_exceptions: int
    n_pairs: int


def as_z_statistics(
    pairs: Sequence[tuple[Decimal, Decimal, Decimal]], tail_a: Decimal
) -> AsZStatistics:
    """Compute ``(Z̄2, Z̄1, N_T, T)`` over ``pairs`` of ``(realized_pnl, var_value, es_value)``
    at tail probability ``tail_a`` (= 1 − the paired family's declared confidence). Forecasts
    are POSITIVE by the house convention; refuses ``es_value <= 0`` and ``var_value < 0``
    (an ES at-or-below zero cannot scale a tail loss; the binder refuses upstream too).
    ``Z̄2 = (1/(T·a))·Σ X_t·I_t/ES_t + 1``; ``Z̄1 = (1/N_T)·Σ X_t·I_t/ES_t + 1`` when
    ``N_T > 0`` else ``None``. Both quantize_HALF_UP 12dp inside the prec-50 context."""
    if not pairs:
        raise EsBacktestKernelError("the AS statistics need >= 1 aligned pair (got 0)")
    if not (Decimal(0) < tail_a < Decimal(1)):
        raise EsBacktestKernelError(f"tail probability {tail_a} outside (0, 1)")
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        total = Decimal(0)
        n_exceptions = 0
        for realized_pnl, var_value, es_value in pairs:
            if es_value <= 0:
                raise EsBacktestKernelError(
                    f"ES forecast {es_value} is not strictly positive; refused"
                )
            if var_value < 0:
                raise EsBacktestKernelError(f"VaR forecast {var_value} is negative; refused")
            if exception_indicator(realized_pnl, var_value):
                n_exceptions += 1
                total += realized_pnl / es_value
        n_pairs = len(pairs)
        z2 = (total / (Decimal(n_pairs) * tail_a) + Decimal(1)).quantize(
            _Z_QUANTUM, rounding=ROUND_HALF_UP
        )
        z1: Decimal | None = None
        if n_exceptions > 0:
            z1 = (total / Decimal(n_exceptions) + Decimal(1)).quantize(
                _Z_QUANTUM, rounding=ROUND_HALF_UP
            )
        return AsZStatistics(z2=z2, z1=z1, n_exceptions=n_exceptions, n_pairs=n_pairs)


def z2_verdict(z2: Decimal, significance: Decimal) -> str:
    """``REJECT`` iff ``z2`` falls BELOW the fixed left-tail critical for the declared
    ``significance`` (:data:`Z2_CRITICALS`); else ``FAIL_TO_REJECT``. One-sided. The caller
    (binder) enforces the (confidence 0.9750, n_pairs 250) derivation domain BEFORE calling —
    this is the pure comparison. Raises :class:`EsBacktestKernelError` on a significance
    outside the declared set (the registrar constrains it upstream)."""
    critical = Z2_CRITICALS.get(significance)
    if critical is None:
        raise EsBacktestKernelError(
            f"significance {significance} is not in the declared critical set "
            f"{sorted(str(s) for s in Z2_CRITICALS)}"
        )
    return ES_DECISION_REJECT if z2 < critical else ES_DECISION_FAIL_TO_REJECT
