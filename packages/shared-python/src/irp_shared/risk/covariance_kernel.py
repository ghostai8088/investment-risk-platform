"""Pure covariance-estimation kernel (P3-4, ENT-051 — sample v1).

NO DB, NO I/O, NO decay, NO shrinkage, NO correlation output — the **equal-weighted unbiased
sample covariance** (OD-P3-4-A/F) of aligned factor-return windows:

    mu_i    = ( SUM_t r_i,t ) / N
    cov_ij  = ( SUM_t (r_i,t - mu_i) * (r_j,t - mu_j) ) / (N - 1)        N >= 2

Computed in ``Decimal`` at 50-digit context precision, ``quantize_HALF_UP`` to 20dp (the
``Numeric(38,20)`` column scale). Units: DAILY ``SIMPLE``-return covariance, UNANNUALIZED
(declared). The result is a Gram-form matrix — **PSD by construction** in exact arithmetic
(quantization perturbs at O(1e-20)); the numerical property is verified by the test suite's
eigenvalue checks + an independent ``numpy.cov`` cross-check (the dual-path standing rule).

Alignment is a PRECONDITION (the binder adjudicates the pinned windows pre-create); the kernel
re-verifies it so the pure function is safe standalone (defense-in-depth — unreachable through
the governed binder).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

#: Result quantum: HALF_UP to 20dp = the ``covariance_result.covariance_value`` Numeric(38,20)
#: scale (OD-P3-4-F — second moments of O(1e-2) daily returns need > the platform's 12dp ceiling).
_RESULT_QUANTUM = Decimal(1).scaleb(-20)
#: Compute precision for the sums/products (well above the 20dp result scale; deterministic).
_COMPUTE_PREC = 50


class CovarianceKernelError(ValueError):
    """Raised for an ill-formed input (fewer than two series, a window shorter than two
    observations, or misaligned date sets). Defense-in-depth: the binder adjudicates the pinned
    windows PRE-CREATE, making this unreachable through the governed path."""


@dataclass(frozen=True)
class FactorSeriesPin:
    """One pinned factor-return window (parsed from a ``COMPONENT_KIND_FACTOR_RETURN``
    component): the factor identity + the ordered ``(return_date, return_value)`` rows."""

    id: str
    factor_code: str
    rows: tuple[tuple[date, Decimal], ...]


def _canonical_pair(id_a: str, id_b: str) -> tuple[str, str]:
    """The canonical unordered-pair key: lowercase-GUID string order (OD-P3-4-D)."""
    a, b = str(id_a).lower(), str(id_b).lower()
    return (a, b) if a <= b else (b, a)


def estimate_covariance(
    series: list[FactorSeriesPin],
) -> dict[tuple[str, str], Decimal]:
    """Estimate the sample covariance matrix of the aligned windows. Returns one entry per
    canonical unordered pair INCLUDING the diagonal (the variances) — ``F*(F+1)/2`` entries for
    ``F`` series. Raises :class:`CovarianceKernelError` on an ill-formed input."""
    if len(series) < 2:
        raise CovarianceKernelError(f"covariance needs >= 2 series (got {len(series)})")
    # Ids key the means/demeaned maps and the canonical pairs — a duplicate (incl. a case-variant
    # spelling of the same GUID) would silently collapse the output below F*(F+1)/2 entries.
    ids = [str(pin.id).lower() for pin in series]
    if len(set(ids)) != len(ids):
        raise CovarianceKernelError("duplicate series ids — an ambiguous series set is refused")
    n = len(series[0].rows)
    if n < 2:
        raise CovarianceKernelError(f"covariance needs >= 2 observations (got {n})")
    dates0 = tuple(d for d, _v in series[0].rows)
    for pin in series[1:]:
        if tuple(d for d, _v in pin.rows) != dates0:
            raise CovarianceKernelError(
                f"misaligned windows: {pin.factor_code!r} dates differ from "
                f"{series[0].factor_code!r}"
            )

    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        n_dec = Decimal(n)
        means = {pin.id: sum((v for _d, v in pin.rows), Decimal(0)) / n_dec for pin in series}
        demeaned = {pin.id: [v - means[pin.id] for _d, v in pin.rows] for pin in series}
        out: dict[tuple[str, str], Decimal] = {}
        denominator = Decimal(n - 1)
        for i, pin_i in enumerate(series):
            for pin_j in series[i:]:
                acc = sum(
                    (
                        di * dj
                        for di, dj in zip(demeaned[pin_i.id], demeaned[pin_j.id], strict=True)
                    ),
                    Decimal(0),
                )
                try:
                    value = (acc / denominator).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
                except InvalidOperation as exc:  # |cov| >= 1e30: 20dp needs > prec-50 digits
                    raise CovarianceKernelError(
                        f"covariance magnitude out of range for "
                        f"{pin_i.factor_code!r}/{pin_j.factor_code!r}"
                    ) from exc
                if value == 0:
                    # Normalize -0E-20 -> 0E-20: PG numeric drops the sign, SQLite TEXT keeps it —
                    # without this the two engines would store different values (AD-011).
                    value = abs(value)
                out[_canonical_pair(pin_i.id, pin_j.id)] = value
        return out
