"""OLS proxy-weight regression kernel (PA-3, ENT-057 — pure math, no I/O, no ORM).

Estimates a private instrument's public-factor loadings by ORDINARY LEAST SQUARES of its DESMOOTHED
appraisal return series ``y`` (n observations) on the candidate factor-return regressors
(``k`` columns), WITH an intercept:

    y = X b + e,    X = [1 | f_1 | ... | f_k]   (n x (k+1))
    b = (X'X)^-1 X'y                             (the normal equations)

Reports, per coefficient (intercept + k slopes): the estimate and its standard error
    Var(b) = s^2 (X'X)^-1,   s^2 = (e'e)/(n - (k+1)),   se_j = sqrt(s^2 * [(X'X)^-1]_jj)
plus R^2 = 1 - SS_res/SS_tot and the residual stdev s.

Computed in ``Decimal`` at 50-digit context; the result carries RAW (un-quantized) values — the
binder gates each value's magnitude against the column envelope BEFORE quantizing to 12dp
(``Numeric(20,12)``), the P3-6/PA-1/PA-2 detonation-guard discipline.

Unconstrained OLS (OD-PA-3-C): NO sum-to-1, NO non-negativity (the Sharpe-1992 constrained and the
Dimson-1979 / Asness-Krail-Liew-2001 summed-lag variants are recorded v2s). Fail-closed (a
STRUCTURAL :class:`ProxyWeightKernelError`, mapped by the binder to a pre-create refusal) on: fewer
than ``(k+1)+1`` observations (no residual degrees of freedom), a SINGULAR/collinear design (a pivot
below tolerance), or a CONSTANT target series (SS_tot == 0, R^2 undefined). Alignment/coverage are
the binder's pre-create job; the kernel re-checks so the pure function is safe standalone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

_CTX_PRECISION = 50
#: A pivot magnitude at/below this (return-scale data; prec-50 arithmetic) is a singular design.
_SINGULAR_TOL = Decimal("1E-30")


class ProxyWeightKernelError(ValueError):
    """A STRUCTURAL regression failure (too few observations, singular/collinear design, constant
    target). The binder maps it to a pre-create refusal (422). ``reason`` is a stable short slug."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class OlsEstimate:
    """The RAW (un-quantized, prec-50) OLS fit. ``coefficients[0]`` is the intercept; ``[1:]`` the
    ``k`` slopes in candidate-factor order. ``std_errors`` aligns 1:1. The binder gates magnitudes
    then quantizes to the ``Numeric(20,12)`` column scale."""

    coefficients: tuple[Decimal, ...]
    std_errors: tuple[Decimal, ...]
    r_squared: Decimal
    residual_stdev: Decimal
    n_observations: int
    n_regressors: int  # k + 1 (intercept included)


def _invert(matrix: list[list[Decimal]]) -> list[list[Decimal]]:
    """Gauss-Jordan inverse with partial pivoting (m x m; m tiny — intercept + a few factors).
    Raises a singular :class:`ProxyWeightKernelError` when a pivot falls at/below tolerance."""
    m = len(matrix)
    aug = [
        [*row, *(Decimal(1) if i == j else Decimal(0) for j in range(m))]
        for i, row in enumerate(matrix)
    ]
    for col in range(m):
        pivot_row = max(range(col, m), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot_row][col]) <= _SINGULAR_TOL:
            raise ProxyWeightKernelError(
                "singular", "design matrix is singular/collinear — refused"
            )
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pivot = aug[col][col]
        aug[col] = [v / pivot for v in aug[col]]
        for r in range(m):
            if r != col and aug[r][col] != 0:
                factor = aug[r][col]
                aug[r] = [v - factor * aug[col][k] for k, v in enumerate(aug[r])]
    return [row[m:] for row in aug]


def estimate_ols(y: Sequence[Decimal], factor_columns: Sequence[Sequence[Decimal]]) -> OlsEstimate:
    """Fit ``y`` on ``[1 | factor_columns]`` by OLS. ``factor_columns`` are the ``k`` candidate
    factor regressors, each a length-``n`` series aligned 1:1 with ``y``. Returns raw prec-50
    values. Raises a structural :class:`ProxyWeightKernelError` on too-few-observations, singular
    design, or a constant target."""
    n = len(y)
    k = len(factor_columns)
    m = k + 1  # regressors incl. the intercept
    for col in factor_columns:
        if len(col) != n:
            raise ProxyWeightKernelError(
                "misaligned", f"a factor column has length {len(col)} != {n} observations"
            )
    if n < m + 1:
        # Need >= 1 residual degree of freedom for a standard error to exist.
        raise ProxyWeightKernelError(
            "insufficient",
            f"{n} observations for {m} regressors — need >= {m + 1} (>= 1 residual df); refused",
        )

    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        # Design matrix rows: [1, f_1[i], ..., f_k[i]].
        design = [[Decimal(1), *(factor_columns[j][i] for j in range(k))] for i in range(n)]
        # X'X (m x m) and X'y (m).
        xtx = [
            [sum((design[i][a] * design[i][b] for i in range(n)), Decimal(0)) for b in range(m)]
            for a in range(m)
        ]
        xty = [sum((design[i][a] * y[i] for i in range(n)), Decimal(0)) for a in range(m)]
        xtx_inv = _invert([row[:] for row in xtx])
        beta = [sum((xtx_inv[a][b] * xty[b] for b in range(m)), Decimal(0)) for a in range(m)]

        # Residuals + sums of squares.
        fitted = [sum((design[i][a] * beta[a] for a in range(m)), Decimal(0)) for i in range(n)]
        residuals = [y[i] - fitted[i] for i in range(n)]
        ss_res = sum((e * e for e in residuals), Decimal(0))
        y_mean = sum(y, Decimal(0)) / Decimal(n)
        ss_tot = sum(((yi - y_mean) ** 2 for yi in y), Decimal(0))
        if ss_tot == 0:
            raise ProxyWeightKernelError(
                "constant-target", "the desmoothed series is constant (SS_tot == 0); R^2 undefined"
            )

        dof = n - m
        s2 = ss_res / Decimal(dof)
        residual_stdev = s2.sqrt()
        r_squared = Decimal(1) - ss_res / ss_tot
        # se_j = sqrt(s^2 * [(X'X)^-1]_jj); a PD inverse has a positive diagonal (a near-singular
        # design is already refused above), so the guard only absorbs O(1e-50) quantization noise.
        std_errors = tuple(
            (s2 * (xtx_inv[j][j] if xtx_inv[j][j] > 0 else Decimal(0))).sqrt() for j in range(m)
        )
        return OlsEstimate(
            coefficients=tuple(beta),
            std_errors=std_errors,
            r_squared=r_squared,
            residual_stdev=residual_stdev,
            n_observations=n,
            n_regressors=m,
        )
