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

from collections.abc import Sequence
from dataclasses import dataclass
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


# --- Christoffersen (1998) Markov independence leg (BT-3, OD-BT-3-E — the v2 convention) ---

#: Fixed chi-square(2) critical values for LR_cc (the joint conditional-coverage statistic,
#: df = 2). Textbook constants at the three-route bar: the closed form for chi-square(2) is
#: quantile(1-α) = −2·ln(α) exactly (CDF = 1 − e^(−x/2)) — −2·ln(0.05) = 5.991465…,
#: −2·ln(0.01) = 9.210340… (verified closed-form at planning). Extending the set is a NEW
#: model version, never silent.
CHI2_2DF_CRITICALS: dict[Decimal, Decimal] = {
    Decimal("0.05"): Decimal("5.991465"),
    Decimal("0.01"): Decimal("9.210340"),
}


@dataclass(frozen=True)
class MarkovCounts:
    """The 2x2 adjacent-day transition counts of an exception series: ``n_ij`` = the number of
    t >= 2 with ``I_{t-1} = i`` and ``I_t = j`` (transitions FROM i TO j — pinned explicitly:
    the written reproduction's prose swaps the index order against its own transition-matrix
    convention, a disclosed source wobble; the likelihood structure below is the arbiter and
    the review re-derives it from the 2x2 MLEs)."""

    n00: int
    n01: int
    n10: int
    n11: int

    @property
    def from_zero(self) -> int:
        return self.n00 + self.n01

    @property
    def from_one(self) -> int:
        return self.n10 + self.n11

    @property
    def total(self) -> int:
        return self.n00 + self.n01 + self.n10 + self.n11


def markov_counts(indicators: Sequence[int]) -> MarkovCounts:
    """Count the 2x2 adjacent-pair transitions of a 0/1 exception series (chronological order).
    Raises :class:`VarBacktestKernelError` on fewer than 2 observations or a non-0/1 value."""
    if len(indicators) < 2:
        raise VarBacktestKernelError(
            f"the Markov test needs >= 2 chronological observations (got {len(indicators)})"
        )
    counts = {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}
    for prev, curr in zip(indicators, indicators[1:], strict=False):
        if prev not in (0, 1) or curr not in (0, 1):
            raise VarBacktestKernelError("exception indicators must be 0 or 1")
        counts[(prev, curr)] += 1
    return MarkovCounts(
        n00=counts[(0, 0)], n01=counts[(0, 1)], n10=counts[(1, 0)], n11=counts[(1, 1)]
    )


def christoffersen_lr_ind(counts: MarkovCounts) -> Decimal | None:
    """The Christoffersen (1998) Markov INDEPENDENCE likelihood-ratio statistic over the 2x2
    transition counts; asymptotically chi-square(1). Alternative: first-order Markov with
    ``pi01 = n01/(n00+n01)``, ``pi11 = n11/(n10+n11)``; null: one common violation probability
    ``pi2 = (n01+n11)/total``. ``LR_ind = 2·[ln L(alt) − ln L(null)]`` — the NONNEGATIVE
    orientation (the written reproduction renders the ratio inverted against its own
    likelihoods, a second disclosed source wobble; the MLE dominance ``L(alt) >= L(null)``
    fixes the sign). Vanishing terms drop analytically (the ``0^0 = 1`` convention).

    Returns ``None`` — the statistic is UNDEFINED, never 0 — on a DEGENERATE table: no
    transition leaves state 1 (``n10 + n11 = 0``: pi11 has no observations, e.g. a zero- or
    single-trailing-exception series) or none leaves state 0 (``n00 + n01 = 0``)."""
    if counts.from_one == 0 or counts.from_zero == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        total = Decimal(counts.total)
        hits = Decimal(counts.n01 + counts.n11)
        pi2 = hits / total
        log_alt = Decimal(0)
        for x, row_total in (
            (counts.n01, counts.from_zero),
            (counts.n11, counts.from_one),
        ):
            x_d, row_d = Decimal(x), Decimal(row_total)
            if x > 0:
                log_alt += x_d * (x_d / row_d).ln()
            if x < row_total:
                log_alt += (row_d - x_d) * (Decimal(1) - x_d / row_d).ln()
        log_null = Decimal(0)
        if hits > 0:
            log_null += hits * pi2.ln()
        if hits < total:
            log_null += (total - hits) * (Decimal(1) - pi2).ln()
        lr = Decimal(2) * (log_alt - log_null)
        return lr.quantize(_LR_QUANTUM, rounding=ROUND_HALF_UP)


def christoffersen_lr_cc(lr_uc: Decimal, lr_ind: Decimal) -> Decimal:
    """The joint conditional-coverage statistic ``LR_cc = LR_uc + LR_ind`` (the standard
    decomposition; asymptotically chi-square(2)). The applied convention — LR_uc over the full
    N pairs, LR_ind over the N−1 transitions — is stated in the referent, not hidden."""
    return (lr_uc + lr_ind).quantize(_LR_QUANTUM, rounding=ROUND_HALF_UP)


def lr_cc_decision(lr_cc: Decimal, alpha: Decimal) -> str:
    """``REJECT`` iff ``lr_cc`` exceeds the FIXED chi-square(2) critical for the declared
    ``alpha`` (:data:`CHI2_2DF_CRITICALS`); else ``FAIL_TO_REJECT``. (The LR_ind decision
    reuses :func:`kupiec_decision` — same df=1 critical table.) Raises on an alpha outside
    the declared set."""
    critical = CHI2_2DF_CRITICALS.get(alpha)
    if critical is None:
        raise VarBacktestKernelError(
            f"alpha {alpha} is not in the declared chi-square(2) critical set "
            f"{sorted(str(a) for a in CHI2_2DF_CRITICALS)}"
        )
    return DECISION_REJECT if lr_cc > critical else DECISION_FAIL_TO_REJECT
