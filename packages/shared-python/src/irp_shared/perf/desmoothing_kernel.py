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
            for prev, curr in zip(marks[:-1], marks[1:], strict=False)
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
            for prev, curr in zip(observed[:-1], observed[1:], strict=False)
        ]
