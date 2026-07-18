"""Empirical-Bayes cross-sectional shrinkage of idiosyncratic residual variances (RS-1, OD-RS-1-B —
pure math, no I/O, no ORM).

Shrinks each instrument's raw specific variance ``s_i^2`` toward the cohort's cross-sectional pool
by the DATA-DRIVEN empirical-Bayes intensity (Efron-Morris / James-Stein method-of-moments; the
Barra USE4 specific-risk shrinkage is a member of this family — NOT Ledoit-Wolf, which shrinks
correlations and leaves variances unshrunk):

    pool         sigma_pool^2 = (1/N) SUM_j s_j^2                 (equal-weighted cross-section)
    sampling var v_i          = 2 s_i^4 / (n_i - k_i)            (Gaussian var-of-a-variance)
    cross disp   S2_cross      = (1/(N-1)) SUM_j (s_j^2 - sigma_pool^2)^2
    prior disp   tau^2         = max(0, S2_cross - v_bar),  v_bar = (1/N) SUM_j v_j
    intensity    w_i           = v_i / (v_i + tau^2)             (per-instrument, data-driven)
    shrunk       s_i^2(shr)    = w_i sigma_pool^2 + (1 - w_i) s_i^2

The intensity is HETEROGENEOUS across instruments (a noisier / shorter-series estimate — larger
``v_i`` — shrinks MORE; a widely-dispersed cohort — larger ``tau^2`` — shrinks LESS; a homogeneous
cohort — ``tau^2 -> 0`` — shrinks fully to the pool). There is NO declared intensity: ``w_i`` is
COMPUTED and, given the pinned per-member ``(s_i^2, n_i, k_i)``, fully reproducible (method-as-
identity; the fit is the declared method, OD-RS-1-B).

Fail-closed (a structural :class:`ResidualShrinkageKernelError`, the binder maps it to a pre-create
refusal) on: a cohort of fewer than :data:`MIN_COHORT_SIZE` comparable members — the DECLARED
prudence/identifiability floor (the method-of-moments ``tau^2`` rests on ``N-1`` df of
cross-sectional dispersion; a single df at N=2 is unusable; Stein's p>=3 dimension is the
motivating ANALOGY, not a transferred guarantee — the doctrine-review softening); a non-positive
residual df ``n_i - k_i`` (no measurable sampling variance); or a negative input variance.
The comparable-risk-group precondition (do not pool across asset classes) is the
declaring caller's responsibility — the kernel pools whatever cohort it is handed.

Computed in ``Decimal`` at 50-digit context; the result carries RAW (un-quantized) values — the
service gates each value's magnitude against the column envelope BEFORE quantizing to 12dp.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

_CTX_PRECISION = 50

#: The minimum comparable-cohort size — the DECLARED prudence/identifiability floor: the
#: method-of-moments tau^2 rests on N-1 df of cross-sectional dispersion (a single df at N=2 is
#: unusable; Stein's p>=3 dimension is the motivating analogy, not a transferred guarantee).
#: Below it the run fails closed rather than substituting an arbitrary intensity (OD-RS-1-B).
MIN_COHORT_SIZE = 3


class ResidualShrinkageKernelError(ValueError):
    """A STRUCTURAL shrinkage failure (cohort too small, non-positive residual df, negative input
    variance). The service maps it to a pre-create refusal (422). ``reason`` is a stable slug."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ShrinkageMemberInput:
    """One cohort member's raw estimate: its residual STDEV + the regression shape (``n_regressors``
    already includes the intercept, so the residual df is ``n_observations - n_regressors``)."""

    residual_stdev: Decimal
    n_observations: int
    n_regressors: int


@dataclass(frozen=True)
class ShrinkageMemberResult:
    """One member's shrinkage outcome (aligned 1:1 with the input order)."""

    shrunk_residual_stdev: Decimal
    shrinkage_weight: Decimal  # w_i in [0, 1]
    raw_residual_variance: Decimal  # s_i^2 (echo)
    sampling_variance: Decimal  # v_i (echo)


@dataclass(frozen=True)
class ResidualShrinkageEstimate:
    """The RAW (un-quantized, prec-50) empirical-Bayes shrinkage fit over a cohort."""

    members: tuple[ShrinkageMemberResult, ...]
    pool_variance: Decimal  # sigma_pool^2
    prior_dispersion: Decimal  # tau^2
    cross_sectional_variance: Decimal  # S2_cross
    mean_sampling_variance: Decimal  # v_bar
    n_members: int


def shrink_residual_variances(
    members: Sequence[ShrinkageMemberInput],
) -> ResidualShrinkageEstimate:
    """Empirical-Bayes cross-sectional shrinkage of a cohort's residual variances (OD-RS-1-B).
    Raises :class:`ResidualShrinkageKernelError` on a too-small cohort, a non-positive residual df,
    or a negative input variance."""
    n_members = len(members)
    if n_members < MIN_COHORT_SIZE:
        raise ResidualShrinkageKernelError(
            "cohort-too-small",
            f"{n_members} comparable member(s) for empirical-Bayes shrinkage — need >= "
            f"{MIN_COHORT_SIZE} (the declared prudence/identifiability floor - tau^2 rests on "
            f"N-1 df of cross-sectional dispersion); "
            f"refused",
        )

    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        n = Decimal(n_members)

        variances: list[Decimal] = []
        sampling: list[Decimal] = []
        for idx, mem in enumerate(members):
            s2 = mem.residual_stdev * mem.residual_stdev
            if s2 < 0:  # a stdev squares non-negative; a malformed negative input is refused
                raise ResidualShrinkageKernelError(
                    "negative-variance",
                    f"member {idx} has a negative residual variance {s2}; refused",
                )
            dof = mem.n_observations - mem.n_regressors
            if dof < 1:
                raise ResidualShrinkageKernelError(
                    "non-positive-residual-df",
                    f"member {idx} has residual df {dof} (n_observations={mem.n_observations} - "
                    f"n_regressors={mem.n_regressors}) < 1 — no measurable sampling variance; "
                    f"refused",
                )
            # v_i = 2 s_i^4 / (n_i - k_i) — the Gaussian sampling variance of a variance estimate.
            v_i = Decimal(2) * (s2 * s2) / Decimal(dof)
            variances.append(s2)
            sampling.append(v_i)

        pool_variance = sum(variances, Decimal(0)) / n
        mean_sampling_variance = sum(sampling, Decimal(0)) / n
        # S2_cross: the unbiased (N-1) cross-sectional sample variance of the s_i^2 estimates.
        ss = sum(((s2 - pool_variance) ** 2 for s2 in variances), Decimal(0))
        cross_sectional_variance = ss / (n - Decimal(1))
        # tau^2: the method-of-moments prior dispersion (observed dispersion net of sampling noise),
        # floored at zero (a cohort tighter than its own sampling noise shrinks fully to the pool).
        prior_dispersion = cross_sectional_variance - mean_sampling_variance
        if prior_dispersion < 0:
            prior_dispersion = Decimal(0)

        results: list[ShrinkageMemberResult] = []
        for s2, v_i in zip(variances, sampling, strict=True):
            denom = v_i + prior_dispersion
            # w_i = v_i/(v_i+tau^2): tau^2=0 & v_i>0 -> w_i=1 (full shrink to pool); v_i=0 -> w_i=0
            # (an infinitely-precise estimate is not shrunk); both zero -> w_i=0 (no shrink).
            weight = Decimal(0) if denom == 0 else v_i / denom
            shrunk_var = weight * pool_variance + (Decimal(1) - weight) * s2
            results.append(
                ShrinkageMemberResult(
                    shrunk_residual_stdev=shrunk_var.sqrt(),
                    shrinkage_weight=weight,
                    raw_residual_variance=s2,
                    sampling_variance=v_i,
                )
            )

        return ResidualShrinkageEstimate(
            members=tuple(results),
            pool_variance=pool_variance,
            prior_dispersion=prior_dispersion,
            cross_sectional_variance=cross_sectional_variance,
            mean_sampling_variance=mean_sampling_variance,
            n_members=n_members,
        )
