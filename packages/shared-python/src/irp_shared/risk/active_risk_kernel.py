"""Pure ex-ante active-risk kernel (P3-7, ENT-027 — parametric tracking error v1).

NO DB, NO I/O, NO simulation — the **factor-model ex-ante tracking error** (OD-P3-7-B), the
Grinold-Kahn/Roll active-risk form under the linear factor model, over a vector of **active
weights** ``w_a = w_p - w_b`` (portfolio minus benchmark, per factor):

    radicand = w_a' * Sigma * w_a                                    (variance, a fraction^2)
    TE       = sqrt(radicand)                                        (a DAILY active-return
                                                                      volatility; UNANNUALIZED)

Computed in ``Decimal`` at 50-digit context precision (``Decimal.sqrt`` is correctly rounded to
context); ``te_value`` is ``quantize_HALF_UP`` to 12dp (the ``Numeric(20,12)`` factor-return
FRACTION scale — NOT a currency amount; the active risk is a return volatility). There is NO ``z``
multiplier — this is a standard deviation, not a quantile (contrast the parametric-VaR kernel).

**The radicand quantization floor (the OD-P3-5-G pattern, re-derived for the weight scale):** Sigma
is PSD in exact arithmetic but stored at 20dp, so for a near-null-space ``w_a`` the quantized
radicand can dip a TINY amount below zero. The DECLARED tolerance ``tol = F^2 * max_i(w_i^2) *
1E-19`` separates the storage artifact (clamped to 0 -> TE 0) from a genuinely non-PSD input
(``te_value`` = None -> the binder's fail-closed post-create DQ defect, REACHABLE via a hand-minted
snapshot pinning a non-PSD matrix). A benchmark-matching portfolio (``w_a`` all zero) is VALID and
yields TE 0 (zero active risk), NOT an error.

Alignment/coverage is a PRECONDITION (the binder adjudicates the pinned content pre-create); the
kernel re-verifies coverage so the pure function is safe standalone (defense-in-depth).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

#: Result quantum: HALF_UP to 12dp = the ``active_risk_result.te_value`` Numeric(20,12) fraction
#: scale (a daily active-return volatility, the factor-return scale — NOT currency).
_RESULT_QUANTUM = Decimal(1).scaleb(-12)
#: Compute precision for the accumulation + sqrt (the P3-4/P3-5 kernel precedent).
_COMPUTE_PREC = 50
#: The radicand-floor tolerance coefficient: 20x headroom over the 5E-21 per-element 20dp bound
#: (the OD-P3-5-G coefficient, structure scale-invariant).
_TOLERANCE_COEFFICIENT = Decimal("1E-19")


class ActiveRiskKernelError(ValueError):
    """Raised for an ill-formed input (no factors, or a factor pair missing from the covariance
    map). Defense-in-depth: the binder adjudicates the pinned content PRE-CREATE, making this
    unreachable through the governed path."""


@dataclass(frozen=True)
class TeEstimate:
    """The kernel output. ``te_value`` is ``None`` exactly when the radicand fell BELOW the declared
    tolerance (a non-PSD input — the binder's post-create DQ defect); a radicand in
    ``[-tolerance, 0)`` is clamped to 0 (the declared storage-artifact regime -> TE 0)."""

    radicand: Decimal
    tolerance: Decimal
    te_value: Decimal | None


def _canonical_pair(id_a: str, id_b: str) -> tuple[str, str]:
    """The canonical unordered-pair key: lowercase-GUID string order (the OD-P3-4-D convention —
    identical to the covariance kernel's storage order)."""
    a, b = str(id_a).lower(), str(id_b).lower()
    return (a, b) if a <= b else (b, a)


def compute_tracking_error(
    active_weights: dict[str, Decimal],
    covariance: dict[tuple[str, str], Decimal],
) -> TeEstimate:
    """Compute the ex-ante tracking error ``sqrt(w_a' Sigma w_a)`` over a per-factor active-weight
    map and a canonical-pair covariance map. Raises :class:`ActiveRiskKernelError` on an ill-formed
    input. An all-zero ``active_weights`` is valid (TE 0 — a benchmark-matching portfolio)."""
    if not active_weights:
        raise ActiveRiskKernelError("no active weights — an empty factor vector is refused")

    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        # canonicalize keys to lowercase-GUID (the covariance storage order); a duplicate key after
        # lowercasing is an ill-formed input (the caller must pass one weight per factor).
        weights: dict[str, Decimal] = {}
        for factor_id, w in active_weights.items():
            key = str(factor_id).lower()
            if key in weights:
                raise ActiveRiskKernelError(f"duplicate factor {key} in the active-weight vector")
            weights[key] = w

        factor_ids = sorted(weights)
        n_factors = len(factor_ids)
        radicand = Decimal(0)
        for i, fid_i in enumerate(factor_ids):
            for fid_j in factor_ids[i:]:
                pair = _canonical_pair(fid_i, fid_j)
                sigma_ij = covariance.get(pair)
                if sigma_ij is None:
                    raise ActiveRiskKernelError(
                        f"covariance pair {pair} is missing — coverage is a precondition"
                    )
                multiplier = Decimal(1) if fid_i == fid_j else Decimal(2)
                radicand += multiplier * weights[fid_i] * weights[fid_j] * sigma_ij

        max_w_squared = max(w * w for w in weights.values())
        tolerance = Decimal(n_factors) ** 2 * max_w_squared * _TOLERANCE_COEFFICIENT

        if radicand < -tolerance:
            # Genuinely non-PSD input (beyond the declared storage-artifact bound) — the binder
            # converts this into the fail-closed post-create DQ defect.
            return TeEstimate(radicand=radicand, tolerance=tolerance, te_value=None)
        clamped = radicand if radicand > 0 else Decimal(0)  # [-tol, 0) -> 0 (declared)
        try:
            te_value = clamped.sqrt().quantize(_RESULT_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:  # te magnitude out of range at 12dp
            raise ActiveRiskKernelError("tracking-error magnitude out of range") from exc
        return TeEstimate(radicand=radicand, tolerance=tolerance, te_value=te_value)
