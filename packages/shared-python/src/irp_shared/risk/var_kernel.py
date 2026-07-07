"""Pure parametric-VaR kernel (P3-5, ENT-027 — delta-normal v1).

NO DB, NO I/O, NO simulation, NO quantile function — the **zero-mean delta-normal portfolio VaR**
(OD-P3-5-A/E/F) under the linear factor model ``dV = SUM_i x_i * r_i``:

    x_i       = SUM over the run's rows for factor i of exposure_amount     (base currency)
    radicand  = x' * Sigma * x                                              (currency^2)
    sigma_p   = sqrt(radicand)          VaR_alpha = z_alpha * sigma_p       (h = 1)

Computed in ``Decimal`` at 50-digit context precision (``Decimal.sqrt`` is correctly rounded to
context); ``sigma``/``var_value`` are ``quantize_HALF_UP`` to 6dp (the ``Numeric(28,6)`` currency
scale). ``z_alpha`` is a REGISTRATION-DECLARED constant (OD-P3-5-D) — the kernel never computes a
quantile.

**The radicand quantization floor (OD-P3-5-G):** Sigma is PSD in exact arithmetic but stored at
20dp, so for near-null-space ``x`` the quantized radicand can dip a TINY amount below zero. The
DECLARED tolerance ``tol = F^2 * max_i(x_i^2) * 1E-19`` (20x headroom over the per-element
5E-21 quantization bound) separates the storage artifact (clamped to 0) from a genuinely non-PSD
input (``sigma``/``var_value`` = None — the binder's fail-closed DQ defect; REACHABLE via a
hand-minted snapshot pinning a non-PSD matrix, unlike the P3-4 defensive gate).

Alignment/coverage is a PRECONDITION (the binder adjudicates the pinned content pre-create); the
kernel re-verifies coverage so the pure function is safe standalone (defense-in-depth).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

#: Result quantum: HALF_UP to 6dp = the ``var_result.sigma``/``var_value`` Numeric(28,6) currency
#: scale (OD-P3-5-F — no new precision departure; the exposure_amount scale).
_RESULT_QUANTUM = Decimal(1).scaleb(-6)
#: Compute precision for the accumulation + sqrt (the P3-4 kernel precedent).
_COMPUTE_PREC = 50
#: The OD-P3-5-G tolerance coefficient: 20x headroom over the 5E-21 per-element 20dp bound.
_TOLERANCE_COEFFICIENT = Decimal("1E-19")


class VarKernelError(ValueError):
    """Raised for an ill-formed input (no exposures, a non-positive z, or a factor pair missing
    from the covariance map). Defense-in-depth: the binder adjudicates the pinned content
    PRE-CREATE, making this unreachable through the governed path."""


@dataclass(frozen=True)
class VarEstimate:
    """The kernel output. ``sigma``/``var_value`` are ``None`` exactly when the radicand fell
    BELOW the declared tolerance (a non-PSD input — the binder's post-create DQ defect); a
    radicand in ``[-tolerance, 0)`` is clamped to 0 (the declared storage-artifact regime)."""

    radicand: Decimal
    tolerance: Decimal
    sigma: Decimal | None
    var_value: Decimal | None


def _canonical_pair(id_a: str, id_b: str) -> tuple[str, str]:
    """The canonical unordered-pair key: lowercase-GUID string order (the OD-P3-4-D convention —
    identical to the covariance kernel's storage order)."""
    a, b = str(id_a).lower(), str(id_b).lower()
    return (a, b) if a <= b else (b, a)


def compute_parametric_var(
    exposure_rows: list[tuple[str, Decimal]],
    covariance: dict[tuple[str, str], Decimal],
    *,
    z_score: Decimal,
) -> VarEstimate:
    """Compute the zero-mean delta-normal VaR over per-row ``(factor_id, exposure_amount)``
    tuples (the deterministic per-factor totaling happens HERE, inside the pure/testable unit)
    and a canonical-pair covariance map. Raises :class:`VarKernelError` on an ill-formed input."""
    if not exposure_rows:
        raise VarKernelError("no exposure rows — an empty portfolio vector is refused")
    if z_score <= 0:
        raise VarKernelError(f"z_score must be > 0 (got {z_score})")

    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        totals: dict[str, Decimal] = {}
        for factor_id, amount in exposure_rows:
            key = str(factor_id).lower()
            totals[key] = totals.get(key, Decimal(0)) + amount

        factor_ids = sorted(totals)
        n_factors = len(factor_ids)
        radicand = Decimal(0)
        for i, fid_i in enumerate(factor_ids):
            for fid_j in factor_ids[i:]:
                pair = _canonical_pair(fid_i, fid_j)
                sigma_ij = covariance.get(pair)
                if sigma_ij is None:
                    raise VarKernelError(
                        f"covariance pair {pair} is missing — coverage is a precondition"
                    )
                multiplier = Decimal(1) if fid_i == fid_j else Decimal(2)
                radicand += multiplier * totals[fid_i] * totals[fid_j] * sigma_ij

        max_x_squared = max(x * x for x in totals.values())
        tolerance = Decimal(n_factors) ** 2 * max_x_squared * _TOLERANCE_COEFFICIENT

        if radicand < -tolerance:
            # Genuinely non-PSD input (beyond the declared storage-artifact bound) — the
            # binder converts this into the fail-closed post-create DQ defect.
            return VarEstimate(radicand=radicand, tolerance=tolerance, sigma=None, var_value=None)
        clamped = radicand if radicand > 0 else Decimal(0)  # [-tol, 0) -> 0 (declared)
        try:
            sigma = clamped.sqrt().quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
            var_value = (z_score * clamped.sqrt()).quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:  # sigma >= ~1e44: 6dp needs > prec-50 digits
            raise VarKernelError("sigma magnitude out of range") from exc
        return VarEstimate(radicand=radicand, tolerance=tolerance, sigma=sigma, var_value=var_value)
