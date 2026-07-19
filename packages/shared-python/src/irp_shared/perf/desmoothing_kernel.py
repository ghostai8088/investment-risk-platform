"""Geltner AR(1) desmoothing kernel (PA-1 — pure math, no I/O, no ORM).

The appraisal-smoothing model (Geltner 1991/1993): the OBSERVED appraisal return blends the true
current-period return with the prior observed return, ``r_a,t = α·r_t + (1−α)·r_a,t−1``. Inverting
recovers the desmoothed ("true") series:

    r_t = (r_a,t − (1−α)·r_a,t−1) / α        (OD-PA-1-D)

- ``observed_returns``: simple returns from consecutive appraisal marks
  (``r_a,t = mark_t/mark_{t−1} − 1``), quantize_HALF_UP to 12dp.
- ``desmooth_geltner``: the inversion per period, quantize_HALF_UP to 12dp. The FIRST observed
  return has no prior — it SEEDS the recursion and yields NO desmoothed value (no imputation; the
  standard treatment): ``len(result) == len(observed) − 1``.
- ``α = 1`` is the no-smoothing boundary: the inversion degenerates to identity (desmoothed ==
  observed[1:]) — property-tested.
- The summary stdev pair (OD-PA-1-C) REUSES :func:`irp_shared.perf.benchmark_relative_kernel.
  sample_stdev` (same family, same Decimal-50 sqrt + 12dp convention — the clean-code bar; no
  second stdev implementation).

Computed in ``Decimal`` at 50-digit context; results ``quantize_HALF_UP`` to 12dp (`Numeric(20,12)`
— see ``numerical_quant_standards.md``). The α DOMAIN (``0 < α ≤ 1``) is validated at model
REGISTRATION and parsed back by the binder; this kernel asserts it defensively (a kernel invariant,
not the user-facing gate).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

_RESULT_QUANTUM = Decimal(1).scaleb(-12)
_CTX_PRECISION = 50


class DesmoothingKernelError(ValueError):
    """A kernel-domain violation (non-positive mark; empty/short series; α out of (0, 1]) — the
    binder's gates should make these unreachable; raising loudly is the defensive invariant."""


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)


def observed_returns(marks: Sequence[Decimal]) -> list[Decimal]:
    """The observed appraisal return series from consecutive marks:
    ``r_a,t = mark_t/mark_{t−1} − 1`` (simple returns, 12dp). Requires >= 2 STRICTLY POSITIVE
    marks (a simple return is undefined at/below zero — the binder refuses these pre-create)."""
    if len(marks) < 2:
        raise DesmoothingKernelError(f"need >= 2 marks for a return series; got {len(marks)}")
    if any(m <= 0 for m in marks):
        raise DesmoothingKernelError("marks must be strictly positive — refused")
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        return [
            _quantize(curr / prev - Decimal(1))
            for prev, curr in zip(marks[:-1], marks[1:], strict=True)
        ]


def desmooth_geltner(observed: Sequence[Decimal], alpha: Decimal) -> list[Decimal]:
    """The Geltner AR(1) inversion: ``r_t = (r_a,t − (1−α)·r_a,t−1) / α`` per period (12dp). The
    first observed return seeds the recursion and yields no output row —
    ``len(result) == len(observed) − 1``. The recursion consumes the OBSERVED prior (the published
    single-pass filter), not the previously desmoothed value."""
    if not 0 < alpha <= 1:
        raise DesmoothingKernelError(f"alpha must be in (0, 1]; got {alpha}")
    if len(observed) < 2:
        raise DesmoothingKernelError(f"need >= 2 observed returns to desmooth; got {len(observed)}")
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        one_minus_alpha = Decimal(1) - alpha
        return [
            _quantize((curr - one_minus_alpha * prev) / alpha)
            for prev, curr in zip(observed[:-1], observed[1:], strict=True)
        ]


# --- DS-2 (OD-DS-2-A/B): the estimation pieces — pure, prec-50, raw outputs (the binder
# quantizes once at the column scale; the never-quantize-intermediates discipline). ---


def lag_autocorrelation(series: Sequence[Decimal], lag: int) -> Decimal:
    """The lag-``k`` sample autocorrelation under the T-DENOMINATOR (Box-Jenkins) convention —
    mean-centered, ``ρ̂_k = Σ_{t=1..n−k}(x_t−x̄)(x_{t+k}−x̄) / Σ_{t=1..n}(x_t−x̄)²`` — the shared
    convention BOTH DS-2 conventions cite (|ρ̂_k| ≤ 1 by Cauchy-Schwarz under this form,
    verifier-executed). RAW prec-50 output. Refuses a CONSTANT series (zero denominator) and a
    lag with an EMPTY numerator (``lag ≥ n`` — an empty-sum ρ̂ = 0 would be an artifact, never a
    measurement; the OD-B silent-skip prohibition)."""
    n = len(series)
    if lag < 1:
        raise DesmoothingKernelError(f"lag must be >= 1; got {lag}")
    if lag >= n:
        raise DesmoothingKernelError(
            f"lag {lag} >= series length {n} — the autocorrelation numerator would be an "
            f"empty sum (an artifact, not a measurement); refused"
        )
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        mean = sum(series, Decimal(0)) / Decimal(n)
        centered = [x - mean for x in series]
        denom = sum((c * c for c in centered), Decimal(0))
        if denom == 0:
            raise DesmoothingKernelError(
                "the series is constant (zero autocovariance denominator); refused"
            )
        num = sum(
            (centered[t] * centered[t + lag] for t in range(n - lag)),
            Decimal(0),
        )
        return num / denom


@dataclass(frozen=True)
class Ar1AlphaEstimate:
    """The RAW (un-quantized, prec-50) in-run AR(1) α estimate (OD-DS-2-A): ``alpha_hat`` =
    1 − ρ̂₁; ``stderr`` = the CONSERVATIVE Bartlett white-noise band 1/√n (it OVERSTATES
    SE(ρ̂₁) under AR(1) at lag 1 — verifier-executed; the exact-AR1 band is a named v2). The
    small-n DOWNWARD bias of ρ̂₁ (⇒ α̂ biased UPWARD, ≈ +(1+4φ)/n) is a REGISTERED limitation,
    never corrected here."""

    alpha_hat: Decimal
    rho1: Decimal
    stderr: Decimal
    n_observations: int


def estimate_ar1_alpha(observed: Sequence[Decimal]) -> Ar1AlphaEstimate:
    """α̂ = 1 − ρ̂₁ from the observed return series (OD-DS-2-A) — the PA-1-recorded offline
    convention brought in-run, deterministic closed form (no optimizer). Fail-closed (the binder
    maps to 422): ρ̂₁ ≤ 0 ⇒ no positive first-order autocorrelation — nothing to desmooth (the
    declared-α version remains available; never a silent clamp). The ρ̂₁ = 1 exclusion is a
    DEFENSIVE assert, verifier-proved dead (equality forces the constant series, already refused
    by :func:`lag_autocorrelation`; ρ̂₁ ≤ cos(π/(n+1)) < 1) — labeled per the MG-1 dead-guard
    lesson, kept as belt-and-braces on the kernel domain boundary."""
    rho1 = lag_autocorrelation(observed, 1)
    if rho1 <= 0:
        raise DesmoothingKernelError(
            f"first-order autocorrelation {rho1} <= 0 — no positive smoothing signal, nothing "
            f"to desmooth (the declared-alpha version remains available); refused"
        )
    if rho1 >= 1:  # defensive: unreachable (see docstring); never a live edge
        raise DesmoothingKernelError(f"first-order autocorrelation {rho1} >= 1; refused")
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        n = Decimal(len(observed))
        return Ar1AlphaEstimate(
            alpha_hat=Decimal(1) - rho1,
            rho1=rho1,
            stderr=Decimal(1) / n.sqrt(),
            n_observations=len(observed),
        )


@dataclass(frozen=True)
class OkunevWhiteResult:
    """The RAW OW transform output (OD-DS-2-B): the final filtered series (quantized 12dp — the
    series IS the persisted output) + the per-pass coefficients ``c_i`` (RAW; NOT persisted —
    fully reproducible from the pinned marks + the declared identity; exposed for tests)."""

    series: tuple[Decimal, ...]
    coefficients: tuple[Decimal, ...]


def desmooth_okunev_white(observed: Sequence[Decimal], max_order: int) -> OkunevWhiteResult:
    """The Okunev-White iterative higher-order filter (OD-DS-2-B): ONE deterministic pass per
    order i = 1..max_order, ascending — never repeat-until-tolerance (that variant is a named
    v2; a later pass perturbs earlier orders slightly, disclosed). Pass i measures ρ_i and ρ_2i
    on the CURRENT series (the T-denominator convention) and applies the LAG-i filter

        r*_t = (r_t − c_i·r_{t−i}) / (1 − c_i)

    with ``c_i`` the '−' root of ``ρ_i·c² − (1+ρ_2i)·c + ρ_i = 0`` — the verifier-proved SOLE
    admissible root (Vieta: the roots are reciprocals, so exactly one has |c| ≤ 1 whenever the
    discriminant is STRICTLY positive, BOTH signs of ρ_i — at disc = 0 with ρ_i < 0 the
    reciprocal DOUBLE root c = −1 arrives, admissible and harmless (denominator 2; the numeric
    review's boundary note); ρ_i < 0 is deliberate WHITENING, no sign flip
    since 1 − c_i > 1 there). Each pass drops its first ``i`` values (the recursion seed —
    cumulative loss Σi = m(m+1)/2). Fail-closed: the structural length-vs-order floor
    (``n ≥ m(m+1)/2 + 2`` so TWO values survive for the (n−1) summary stdev; each pass's current
    length must exceed ``2i`` so ρ_2i is measured, not an empty-sum artifact); a negative
    discriminant (PSD-reachable — a live guard); ``c_i ≥ 1`` (NOT equality-only — near a zero
    discriminant the computed root can land an ulp above 1 and flip the filter's sign);
    ρ_i = 0 exactly ⇒ c_i = 0 and the pass is the algebraic identity (applied deterministically,
    the pass count and the length accounting stay fixed). Intermediate passes stay RAW; ONLY the
    final series is quantized (the never-quantize-intermediates discipline)."""
    m = max_order
    if m < 1:
        raise DesmoothingKernelError(f"max_order must be >= 1; got {m}")
    n = len(observed)
    floor = m * (m + 1) // 2 + 2
    if n < floor:
        raise DesmoothingKernelError(
            f"{n} observed returns for max_order={m} — the cumulative pass loss is "
            f"m(m+1)/2 = {m * (m + 1) // 2} and two values must survive for the summary "
            f"stdev; need >= {floor}; refused"
        )
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        current: list[Decimal] = list(observed)
        coefficients: list[Decimal] = []
        for i in range(1, m + 1):
            length = len(current)
            if length <= 2 * i:
                raise DesmoothingKernelError(
                    f"pass {i}: current series length {length} <= 2·{i} — rho_2i would be an "
                    f"empty-sum artifact; refused"
                )
            rho_i = lag_autocorrelation(current, i)
            rho_2i = lag_autocorrelation(current, 2 * i)
            if rho_i == 0:
                c_i = Decimal(0)  # the algebraic limit: the identity pass, deterministically
            else:
                disc = (Decimal(1) + rho_2i) ** 2 - Decimal(4) * rho_i * rho_i
                if disc < 0:
                    raise DesmoothingKernelError(
                        f"pass {i}: negative discriminant {disc} — inadmissible "
                        f"autocorrelation structure (rho_{i}={rho_i}, rho_{2 * i}={rho_2i}); "
                        f"refused"
                    )
                c_i = ((Decimal(1) + rho_2i) - disc.sqrt()) / (Decimal(2) * rho_i)
            if c_i >= 1:  # >=, never equality-only: the ulp-above-one evasion (verifier U5)
                raise DesmoothingKernelError(
                    f"pass {i}: coefficient c={c_i} >= 1 — the filter denominator degenerates "
                    f"or flips sign; refused"
                )
            if abs(c_i) > 1:  # post-selection invariant: the '−' branch is the |c| <= 1 root
                raise DesmoothingKernelError(
                    f"pass {i}: |c|={abs(c_i)} > 1 — the admissible-root invariant failed; "
                    f"refused"
                )
            one_minus_c = Decimal(1) - c_i
            current = [(current[t] - c_i * current[t - i]) / one_minus_c for t in range(i, length)]
            coefficients.append(c_i)
        return OkunevWhiteResult(
            series=tuple(_quantize(v) for v in current),
            coefficients=tuple(coefficients),
        )
