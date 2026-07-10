"""Governed registration of the analytic-sensitivity model (P3-1, OD-P3-1-C/M).

The sensitivity method is a **registered model**: ``register_sensitivity_model`` inventories the
``model`` head + an immutable ``model_version`` through the governed model service
(``register_model`` + ``register_model_version`` — emitting ``MODEL.REGISTER``/``MODEL.VERSION``),
**NEVER as a silently hard-coded, unmanaged object** (the user-ratified direction). It is
idempotent
(resolve-or-register on the per-tenant ``code`` + ``version_label`` + ``code_version``), so a fresh
tenant registers once and re-runs reuse the version. ``methodology_ref`` is MANDATORY and points to
the versioned methodology doc; the conventions become ``model_assumption`` rows and the scope-outs
``model_limitation`` rows. ``run_sensitivities`` then **asserts** this version is registered
pre-create (``assert_registered_model_version``; CTRL-003), so no run executes against an
unregistered model.

The ``Model.validation_status`` stays ``UNVALIDATED`` — recorded, **non-enforcing until P7** (the
validation/approval maker-checker workflow is a later phase). This registers the model; it does NOT
validate or approve it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import Model, ModelAssumption, ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model,
    register_model_version,
)

# ``assert_model_version_of`` (+ the two error classes above) were PROMOTED to ``model.service`` at
# PM-1 — generic model-registry governance once ``perf``, the second governed-number family, also
# consumes them (``perf`` must not import ``risk``). Re-exported here UNCHANGED (the explicit ``as``
# re-export) so every existing ``risk.bootstrap`` import + every ``except``/``isinstance`` site
# keeps working identically — zero behavior change.
from irp_shared.model.service import assert_model_version_of as assert_model_version_of

#: The per-tenant inventory identity of the analytic-sensitivity model.
SENSITIVITY_MODEL_CODE = "risk.sensitivity.analytic"
SENSITIVITY_MODEL_NAME = "Analytic curve-node sensitivities (DV01 / spread-DV01)"
SENSITIVITY_MODEL_TYPE = "SENSITIVITY"
SENSITIVITY_VERSION_LABEL = "v1"

#: MANDATORY methodology pointer — the versioned doc under the existing methodology home.
SENSITIVITY_METHODOLOGY_REF = "05_analytics_methodologies/sensitivities_analytic_v1.md"

#: The declared numerical conventions (mirrored into model_assumption rows; OD-P3-1-G).
SENSITIVITY_ASSUMPTIONS: tuple[str, ...] = (
    "Year fraction T = tenor_days / 365 (ACT/365 Fixed).",
    "Continuous compounding: DF = exp(-rate * T).",
    "Bump = 1bp = 0.0001 absolute; analytic closed-form DV01 = -T * DF * 1bp for a unit "
    "(notional = 1) zero-coupon claim at each captured node.",
    "DISCOUNT_FACTOR nodes use the captured DF directly; ZERO_RATE nodes use DF = exp(-z*T); "
    "SPREAD nodes use spread-DV01 = -T * exp(-s*T) * 1bp.",
    "Evaluated AT the captured curve nodes only — NO interpolation between nodes.",
    "Results quantized HALF_UP to 12 decimal places (the Numeric(28,12) column scale).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-P3-1-A/G).
SENSITIVITY_LIMITATIONS: tuple[str, ...] = (
    "Curve-intrinsic only — NOT instrument- or position-attributed key-rate DV01 (a true "
    "instrument DV01 needs captured cash-flow terms + interpolation + discounting; deferred).",
    "PAR_RATE nodes are not supported (par->zero bootstrapping is curve construction; deferred).",
    "No interpolation between nodes; no convexity / cross-gamma / second-order terms.",
    "validation_status UNVALIDATED — recorded, non-enforcing until the P7 validation workflow.",
)

#: The per-tenant inventory identity of the factor-exposure allocation model (P3-3, OD-P3-3-G).
FACTOR_EXPOSURE_MODEL_CODE = "risk.factor_exposure.allocation"
FACTOR_EXPOSURE_MODEL_NAME = "Factor-exposure allocation (indicator loadings, CURRENCY family)"
FACTOR_EXPOSURE_MODEL_TYPE = "FACTOR_EXPOSURE"
FACTOR_EXPOSURE_VERSION_LABEL = "v1"

#: MANDATORY methodology pointer — the versioned doc under the existing methodology home.
FACTOR_EXPOSURE_METHODOLOGY_REF = "05_analytics_methodologies/factor_exposure_allocation_v1.md"

#: The declared methodology choices (mirrored into model_assumption rows; OD-P3-3-C/J).
FACTOR_EXPOSURE_ASSUMPTIONS: tuple[str, ...] = (
    "Indicator (membership) loadings: loading = 1 per matched atom (the fundamental-factor-model "
    "membership-exposure form); fractional/beta loadings are a deferred v2.",
    "The CURRENCY dimension = the pinned atom's captured mark_currency, matched EXACTLY against "
    "the factor definition's currency_code scope (mark_currency is a declared proxy for "
    "denomination currency).",
    "The factor set is a partition: every pinned atom must map to EXACTLY ONE pinned factor; an "
    "unmapped atom fails the run closed (no residual bucket).",
    "factor_exposure = quantize_HALF_UP(loading * exposure_amount, 6) (Numeric(28,6), base "
    "currency; idempotent on the already-6dp atom — exact by construction).",
    "Signs preserved (a short atom allocates negative exposure; no abs/gross/net coercion).",
    "Contributions sum to the pinned input total EXACTLY (epsilon = 0) by the partition "
    "construction (the REQ-MKT-003 acceptance for the allocation leg).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-P3-3-A/C/O).
FACTOR_EXPOSURE_LIMITATIONS: tuple[str, ...] = (
    "Allocation exposures only — NOT vendor-supplied betas (no factor-loading input is captured) "
    "and NOT regression-estimated loadings (need adjusted-price return history + estimation; "
    "both deferred as named prerequisites).",
    "CURRENCY family only in v1; ASSET_CLASS/INDUSTRY/COUNTRY/STYLE/MACRO/MARKET dimensions "
    "deferred (need an instrument pin or captured loadings).",
    "mark_currency approximates denomination currency; an instrument marked in a non-native "
    "currency would misallocate (the instrument-denomination dimension is deferred).",
    "Factor returns are NOT consumed (their first consumer is P3-4 covariance / regression v2).",
    "No residual/UNMAPPED bucket — an unmapped atom fails the whole run closed.",
    "validation_status UNVALIDATED — recorded, non-enforcing until the P7 validation workflow.",
)


def register_sensitivity_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the analytic-sensitivity ``model`` + a ``model_version`` for this
    ``code_version`` through the governed model service, and return the version. Re-invocation with
    the same ``(tenant, code, version_label, code_version)`` returns the existing version (no
    duplicate inventory). The returned ``model_version.id`` is what a sensitivity run binds +
    asserts.
    """
    model = session.execute(
        select(Model).where(Model.tenant_id == str(tenant_id), Model.code == SENSITIVITY_MODEL_CODE)
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=SENSITIVITY_MODEL_CODE,
            name=SENSITIVITY_MODEL_NAME,
            model_type=SENSITIVITY_MODEL_TYPE,
            actor_id=actor_id,
            description="Closed-form curve-node DV01 / spread-DV01 (P3-1, ENT-028).",
            actor_type=actor_type,
        )

    # The inventory identity is (tenant, model, version_label) — the DB unique key. Resolve on
    # THAT key; a same-label registration with a DIFFERENT code_version is a governed conflict
    # (never an IntegrityError 500), because an immutable version cannot be re-pointed.
    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == SENSITIVITY_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            # P3-C1 (OD-B residual, 2026-07 review): a same-label twin minted via the
            # GENERIC registration (status=None) must be a REGISTRATION conflict too —
            # otherwise register reports success while every bind refuses it (a
            # register/run contract split; the label is squatted either way, but honestly).
            raise WrongModelVersionError(str(version.id), str(model.code))
        if version.code_version != str(code_version):
            raise ModelVersionConflictError(
                SENSITIVITY_MODEL_CODE, SENSITIVITY_VERSION_LABEL, str(code_version)
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=SENSITIVITY_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=SENSITIVITY_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=SENSITIVITY_ASSUMPTIONS,
        limitations=SENSITIVITY_LIMITATIONS,
        actor_type=actor_type,
    )


def register_factor_exposure_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the factor-exposure allocation ``model`` + a ``model_version`` for
    this ``code_version`` through the governed model service (P3-3, OD-P3-3-G — the
    ``register_sensitivity_model`` shape; NEVER a silently hard-coded unmanaged object).
    Re-invocation with the same ``(tenant, code, version_label, code_version)`` returns the
    existing version. The returned ``model_version.id`` is what a factor-exposure run binds +
    asserts pre-create (CTRL-003)."""
    model = session.execute(
        select(Model).where(
            Model.tenant_id == str(tenant_id), Model.code == FACTOR_EXPOSURE_MODEL_CODE
        )
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=FACTOR_EXPOSURE_MODEL_CODE,
            name=FACTOR_EXPOSURE_MODEL_NAME,
            model_type=FACTOR_EXPOSURE_MODEL_TYPE,
            actor_id=actor_id,
            description=(
                "Indicator-loading CURRENCY-family factor-exposure allocation over pinned "
                "exposure atoms (P3-3, ENT-028 family)."
            ),
            actor_type=actor_type,
        )

    # (tenant, model, version_label) is the DB unique key — resolve on it; a different
    # code_version under the same label is a governed conflict (see the sensitivity twin above).
    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == FACTOR_EXPOSURE_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            # P3-C1 (OD-B residual, 2026-07 review): a same-label twin minted via the
            # GENERIC registration (status=None) must be a REGISTRATION conflict too —
            # otherwise register reports success while every bind refuses it (a
            # register/run contract split; the label is squatted either way, but honestly).
            raise WrongModelVersionError(str(version.id), str(model.code))
        if version.code_version != str(code_version):
            raise ModelVersionConflictError(
                FACTOR_EXPOSURE_MODEL_CODE, FACTOR_EXPOSURE_VERSION_LABEL, str(code_version)
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=FACTOR_EXPOSURE_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=FACTOR_EXPOSURE_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=FACTOR_EXPOSURE_ASSUMPTIONS,
        limitations=FACTOR_EXPOSURE_LIMITATIONS,
        actor_type=actor_type,
    )


#: The per-tenant inventory identity of the covariance estimation model (P3-4, OD-P3-4-A/G).
COVARIANCE_MODEL_CODE = "risk.covariance.sample"
COVARIANCE_MODEL_NAME = "Sample factor covariance (equal-weighted, unbiased N-1)"
COVARIANCE_MODEL_TYPE = "COVARIANCE"
COVARIANCE_VERSION_LABEL = "v1"

#: MANDATORY methodology pointer — the versioned doc under the existing methodology home.
COVARIANCE_METHODOLOGY_REF = "05_analytics_methodologies/covariance_sample_v1.md"

#: The declared-window assumption prefix (OD-P3-4-G: the estimation window is part of the version
#: identity — parsed back from the assumption row for the identity check + the binder's read).
WINDOW_ASSUMPTION_PREFIX = "window_observations="

#: The declared methodology choices EXCLUDING the window (which is registration-supplied and
#: appended per call; OD-P3-4-F/G).
COVARIANCE_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Equal-weighted UNBIASED sample covariance: cov_ij = SUM_t((r_i,t - mu_i)(r_j,t - mu_j)) "
    "/ (N - 1); mu_i = SUM_t(r_i,t) / N.",
    "Inputs: captured SIMPLE DAILY factor returns (decimal fractions); the window = the N most "
    "recent dates on which EVERY selected factor has a current-head return (set intersection); "
    "fewer than N common dates fails closed — NO imputation, NO pairwise deletion (pairwise "
    "breaks PSD).",
    "Units: DAILY, UNANNUALIZED covariance of SIMPLE returns (annualization is a later, declared "
    "transform).",
    "Computed in Decimal at 50-digit context precision; quantize_HALF_UP to 20 decimal places "
    "(the Numeric(38,20) column scale).",
    "PSD by construction (Gram form) in exact arithmetic; numerically verified by eigenvalue "
    "property tests + an independent numpy.cov cross-check (test-only dependency).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-P3-4-A/P).
COVARIANCE_LIMITATIONS: tuple[str, ...] = (
    "Factor-level covariance only - NOT asset/instrument covariance (instrument return history "
    "requires adjusted/total-return prices; a named captured-data gap).",
    "Equal weights only - no EWMA/decay; no shrinkage (Ledoit-Wolf); each is a later, separately "
    "declared model_version. The sample estimator is rank-deficient for F >= N (use F < N).",
    "No correlation-matrix output (statistic_type CORRELATION reserved); no annualization.",
    "No missing-data imputation: a factor lacking a return on a window date fails the run closed.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def declared_window_observations(session: Session, version: ModelVersion) -> int:
    """Parse the version's declared estimation window from its ``model_assumption`` rows (the
    OD-P3-4-G identity: exactly ONE ``window_observations=N`` assumption must exist)."""
    rows = (
        session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == version.id)
        )
        .scalars()
        .all()
    )
    declared = [
        r.assumption_text[len(WINDOW_ASSUMPTION_PREFIX) :]
        for r in rows
        if r.assumption_text.startswith(WINDOW_ASSUMPTION_PREFIX)
    ]
    # Exactly one, strictly-decimal declaration — a version minted with a malformed/absent window
    # (reachable via the GENERIC model-registration endpoint under the same permission) is NOT a
    # covariance-model identity; refuse fail-closed (422), never a bare int() ValueError (500).
    if len(declared) != 1 or not re.fullmatch(r"[0-9]+", declared[0]):
        raise WrongModelVersionError(str(version.id), COVARIANCE_MODEL_CODE)
    return int(declared[0])


def register_covariance_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    window_observations: int,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the covariance ``model`` + a ``model_version`` for this
    ``(code_version, window_observations)`` pair through the governed model service (P3-4,
    OD-P3-4-G). The window is recorded as a ``model_assumption`` AND is part of the
    version-resolution identity: re-registering the same ``version_label`` with a DIFFERENT
    ``code_version`` OR window raises :class:`ModelVersionConflictError` (an immutable inventory
    identity cannot be re-pointed) — mint a new ``version_label`` instead."""
    if window_observations < 2:
        raise ValueError("window_observations must be >= 2 (the N-1 sample denominator)")
    model = session.execute(
        select(Model).where(Model.tenant_id == str(tenant_id), Model.code == COVARIANCE_MODEL_CODE)
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=COVARIANCE_MODEL_CODE,
            name=COVARIANCE_MODEL_NAME,
            model_type=COVARIANCE_MODEL_TYPE,
            actor_id=actor_id,
            description=(
                "Equal-weighted unbiased sample covariance of captured factor returns "
                "(P3-4, ENT-051)."
            ),
            actor_type=actor_type,
        )

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == COVARIANCE_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            # P3-C1 (OD-B residual, 2026-07 review): a same-label twin minted via the
            # GENERIC registration (status=None) must be a REGISTRATION conflict too —
            # otherwise register reports success while every bind refuses it (a
            # register/run contract split; the label is squatted either way, but honestly).
            raise WrongModelVersionError(str(version.id), str(model.code))
        if version.code_version != str(code_version) or declared_window_observations(
            session, version
        ) != int(window_observations):
            raise ModelVersionConflictError(
                COVARIANCE_MODEL_CODE,
                COVARIANCE_VERSION_LABEL,
                f"{code_version} (window_observations={window_observations})",
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=COVARIANCE_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=COVARIANCE_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=(
            *COVARIANCE_ASSUMPTIONS_BASE,
            f"{WINDOW_ASSUMPTION_PREFIX}{int(window_observations)}",
        ),
        limitations=COVARIANCE_LIMITATIONS,
        actor_type=actor_type,
    )


#: The per-tenant inventory identity of the parametric-VaR model (P3-5, OD-P3-5-A/D).
VAR_MODEL_CODE = "risk.var.parametric"
VAR_MODEL_NAME = "Parametric portfolio VaR (delta-normal, zero-mean, 1-day)"
VAR_MODEL_TYPE = "VAR"
VAR_VERSION_LABEL = "v1"

#: MANDATORY methodology pointer — the versioned doc under the existing methodology home.
VAR_METHODOLOGY_REF = "05_analytics_methodologies/var_parametric_v1.md"

#: The declared-parameter assumption prefixes (OD-P3-5-D: confidence/horizon/z are part of the
#: version identity — parsed back for the identity check + the binder's read; the OD-P3-4-G
#: window precedent extended).
CONFIDENCE_ASSUMPTION_PREFIX = "confidence_level="
HORIZON_ASSUMPTION_PREFIX = "horizon_days="
Z_ASSUMPTION_PREFIX = "z_score="

#: The v1 confidence vocabulary -> the REGISTERED z constants (OD-P3-5-D): recorded to 12dp,
#: dual-sourced from published standard-normal tables and test-verified via the stdlib
#: ``math.erf`` round-trip Phi(z) = (1+erf(z/sqrt(2)))/2 == alpha to 1e-12 AND an independent
#: bisection inversion (2026-07-07). NO runtime inverse-CDF exists (capability-is-not-evidence).
VAR_Z_SCORES: dict[str, str] = {
    "0.9500": "1.644853626951",
    "0.9900": "2.326347874041",
}
#: The v1 horizon (the covariance substrate is DAILY/unannualized; sqrt(h) is a recorded seam).
VAR_HORIZON_DAYS = 1

#: The declared methodology choices EXCLUDING the per-registration declarations (appended per
#: call; OD-P3-5-D/E/F/G).
VAR_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Zero-mean delta-normal parametric VaR under the linear factor model dV = SUM_i(x_i * r_i): "
    "sigma_p = sqrt(x' * Sigma * x); VaR_alpha = z_alpha * sigma_p (1-day; no sqrt(h) scaling).",
    "Inputs: the per-factor CURRENCY-exposure totals of ONE COMPLETED factor-exposure run (base "
    "currency, signed) x the sample covariance matrix of ONE COMPLETED covariance run "
    "(SIMPLE/DAILY, unannualized); every exposure factor MUST be covered by the covariance "
    "factor set - a gap fails closed (NO zero-variance imputation).",
    "z_alpha is a REGISTERED constant from an enumerated confidence vocabulary - no runtime "
    "inverse-normal-CDF is computed.",
    "Radicand quantization floor: x'*Sigma*x in [-tol, 0) with tol = F^2 * max(x_i^2) * 1E-19 "
    "(the 20dp storage-quantum bound, 20x headroom) is treated as 0; below -tol the run FAILS "
    "closed (a non-PSD input).",
    "Computed in Decimal at 50-digit context precision; sigma/VaR quantize_HALF_UP to 6 decimal "
    "places (the Numeric(28,6) base-currency scale).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-P3-5-M).
VAR_LIMITATIONS: tuple[str, ...] = (
    "SPECIFIC/IDIOSYNCRATIC RISK = 0: the linear CURRENCY-family indicator-loading factor model "
    "carries NO residual variance term - portfolio risk outside the factor covariance is "
    "invisible to this number (the allocation-v1 limitation propagates).",
    "Joint normality of factor returns assumed - tail risk is understated for fat-tailed "
    "returns; the empirical-distribution alternative SHIPS as the separately declared family "
    "risk.var.historical v1 (VAR-HS-1).",
    "1-day horizon only (the covariance is daily/unannualized); multi-horizon sqrt(h) scaling "
    "is a later, separately declared transform.",
    "Parametric method only; ONE confidence level per registered version (the declared-parameter "
    "identity); historical simulation ships as the separate family risk.var.historical v1; "
    "ES (closed-form seam) and Monte-Carlo remain later, separately declared versions/families.",
    "Inherits the sample-covariance estimation error (equal weights, no shrinkage; rank-deficient "
    "for F >= N).",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)

#: Strict decimal-fraction pattern for the declared confidence (e.g. '0.9500').
_CONFIDENCE_PATTERN = re.compile(r"0\.[0-9]{1,6}")


@dataclass(frozen=True)
class VarParameters:
    """The version's declared VaR parameters, parsed back from its ``model_assumption`` rows."""

    confidence_level: Decimal
    horizon_days: int
    z_score: Decimal


def declared_var_parameters(session: Session, version: ModelVersion) -> VarParameters:
    """Parse the version's declared confidence/horizon/z from its ``model_assumption`` rows (the
    OD-P3-5-D identity: exactly ONE strictly-well-formed declaration of EACH). A malformed,
    absent, or ambiguous declaration is NOT a parametric-VaR identity — refuse fail-closed
    (:class:`WrongModelVersionError`, 422), never a bare parse crash (the P3-4 review lesson:
    such versions are mintable via the GENERIC registration endpoint)."""
    rows = (
        session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == version.id)
        )
        .scalars()
        .all()
    )

    def _single(prefix: str) -> str | None:
        found = [
            r.assumption_text[len(prefix) :] for r in rows if r.assumption_text.startswith(prefix)
        ]
        return found[0] if len(found) == 1 else None

    confidence_text = _single(CONFIDENCE_ASSUMPTION_PREFIX)
    horizon_text = _single(HORIZON_ASSUMPTION_PREFIX)
    z_text = _single(Z_ASSUMPTION_PREFIX)
    # The v1 identity is EXACT: an enumerated confidence with its table z AND horizon '1'
    # verbatim (isdigit() accepted Unicode digits and any horizon like '250' — a generically
    # minted version could stamp a horizon its 1-day number does not reflect; 2026-07 review).
    if (
        confidence_text is None
        or horizon_text is None
        or z_text is None
        or not _CONFIDENCE_PATTERN.fullmatch(confidence_text)
        or horizon_text != str(VAR_HORIZON_DAYS)
        or VAR_Z_SCORES.get(confidence_text) != z_text
    ):
        raise WrongModelVersionError(str(version.id), VAR_MODEL_CODE)
    return VarParameters(
        confidence_level=Decimal(confidence_text),
        horizon_days=int(horizon_text),
        z_score=Decimal(z_text),
    )


def register_var_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    horizon_days: int = VAR_HORIZON_DAYS,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the parametric-VaR ``model`` + a ``model_version`` for this
    ``(code_version, confidence_level, horizon_days)`` identity through the governed model
    service (P3-5, OD-P3-5-D). The declarations are recorded as ``model_assumption``s AND are
    part of the version-resolution identity: re-registering the same ``version_label`` with ANY
    different declaration raises :class:`ModelVersionConflictError` — mint a new label instead.
    The v1 vocabulary: ``confidence_level`` in {0.95, 0.99} (the registered z table);
    ``horizon_days`` == 1."""
    # STRICT parse — never coerce: a malformed string must not crash (Decimal('abc') raises
    # InvalidOperation, which is NOT a ValueError) and a near-vocabulary value like '0.94995'
    # must be REFUSED, not silently rounded onto 0.9500 (2026-07 review). A <=4dp match
    # quantizes exactly (zero-padding only).
    text = str(confidence_level).strip()
    if not _CONFIDENCE_PATTERN.fullmatch(text) or len(text) > 6:
        raise ValueError(
            f"confidence_level {confidence_level!r} is not in the v1 vocabulary "
            f"{sorted(VAR_Z_SCORES)} (a new level is a new declared registration, "
            f"never a runtime quantile)"
        )
    confidence_key = f"{Decimal(text).quantize(Decimal('0.0001')):f}"
    z_text = VAR_Z_SCORES.get(confidence_key)
    if z_text is None:
        raise ValueError(
            f"confidence_level {confidence_level} is not in the v1 vocabulary "
            f"{sorted(VAR_Z_SCORES)} (a new level is a new declared registration, "
            f"never a runtime quantile)"
        )
    if int(horizon_days) != VAR_HORIZON_DAYS:
        raise ValueError(
            f"horizon_days must be {VAR_HORIZON_DAYS} in v1 (sqrt(h) scaling is a recorded seam)"
        )
    model = session.execute(
        select(Model).where(Model.tenant_id == str(tenant_id), Model.code == VAR_MODEL_CODE)
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=VAR_MODEL_CODE,
            name=VAR_MODEL_NAME,
            model_type=VAR_MODEL_TYPE,
            actor_id=actor_id,
            description=(
                "Zero-mean delta-normal parametric portfolio VaR over governed factor "
                "exposures x a governed sample covariance (P3-5, ENT-027)."
            ),
            actor_type=actor_type,
        )

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == VAR_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            # P3-C1 (OD-B residual, 2026-07 review): a same-label twin minted via the
            # GENERIC registration (status=None) must be a REGISTRATION conflict too —
            # otherwise register reports success while every bind refuses it (a
            # register/run contract split; the label is squatted either way, but honestly).
            raise WrongModelVersionError(str(version.id), str(model.code))
        declared = declared_var_parameters(session, version)  # malformed existing -> 422 class
        if (
            version.code_version != str(code_version)
            or f"{declared.confidence_level:f}" != confidence_key
            or declared.horizon_days != int(horizon_days)
        ):
            raise ModelVersionConflictError(
                VAR_MODEL_CODE,
                VAR_VERSION_LABEL,
                f"{code_version} (confidence_level={confidence_key}, "
                f"horizon_days={horizon_days})",
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=VAR_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=VAR_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=(
            *VAR_ASSUMPTIONS_BASE,
            f"{CONFIDENCE_ASSUMPTION_PREFIX}{confidence_key}",
            f"{HORIZON_ASSUMPTION_PREFIX}{int(horizon_days)}",
            f"{Z_ASSUMPTION_PREFIX}{z_text}",
        ),
        limitations=VAR_LIMITATIONS,
        actor_type=actor_type,
    )


# --- VAR-HS-1: the historical-simulation VaR model family (OD-VHS-B) ---

VAR_HS_MODEL_CODE = "risk.var.historical"
VAR_HS_MODEL_NAME = "Historical-simulation portfolio VaR (plain equal-weight, 1-day)"
VAR_HS_MODEL_TYPE = "VAR"
VAR_HS_VERSION_LABEL = "v1"
VAR_HS_METHODOLOGY_REF = "05_analytics_methodologies/var_historical_v1.md"

#: The v1 quantile convention — REGISTRATION-DECLARED (OD-VHS-D): the lower empirical order
#: statistic k = ceil(N*(1-c)), no interpolation. An interpolated estimator is a NEW declared
#: version, never a silent change.
QUANTILE_ASSUMPTION_PREFIX = "quantile_convention="
VAR_HS_QUANTILE_CONVENTION = "LOWER_ORDER_STATISTIC"

VAR_HS_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Plain EQUAL-WEIGHT historical simulation: every pinned window date is one scenario with "
    "weight 1/N - no volatility filtering, no time decay (FHS/BRW are recorded v2 versions).",
    "Linear factor model dV_t = SUM_i x_i * r_(t,i) over the FACTOR_EXPOSURE run's per-factor "
    "totals - the same substrate as the parametric method; NO revaluation.",
    "The scenario P&L distribution is the EMPIRICAL one - no distributional assumption "
    "(the method's point versus delta-normal).",
    "var_value = -(k-th smallest scenario P&L), quantized HALF_UP to 6 decimal places "
    "(Numeric(28,6)); the value may be negative when the k-th tail scenario is a gain - "
    "reported honestly, never clamped.",
)

VAR_HS_LIMITATIONS: tuple[str, ...] = (
    "SPECIFIC/IDIOSYNCRATIC RISK = 0: x spans registered factors only (the allocation-v1 "
    "limitation propagates - identical to the parametric method).",
    "Equal weighting reacts SLOWLY to volatility shifts; filtered (FHS) and time-weighted "
    "(BRW) variants outperform in the cited literature and are recorded v2 model versions "
    "requiring a declared volatility model (decision record Part 2.1).",
    "The estimate cannot exceed the worst scenario IN the window - regime changes outside the "
    "pinned window are invisible (window-as-declared-identity; the OD-VHS-E adequacy floor is "
    "a statistical minimum, not a sufficiency guarantee).",
    "1-day horizon only; overlapping/multi-day windows and sqrt(h) scaling are recorded seams.",
    "ES (the FRTB-preferred tail measure) is a recorded seam for this family too; backtesting "
    "(Kupiec/traffic-light) is a recorded later slice and Monte-Carlo remains gated on a seeded "
    "simulator (the OD-VHS-G register).",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


@dataclass(frozen=True)
class HsVarParameters:
    """The version's declared HS-VaR parameters, parsed from its ``model_assumption`` rows."""

    confidence_level: Decimal
    horizon_days: int
    window_observations: int
    quantile_convention: str


def declared_hs_var_parameters(session: Session, version: ModelVersion) -> HsVarParameters:
    """Parse the declared confidence/horizon/window/quantile-convention (the OD-VHS-B identity:
    exactly ONE strictly-well-formed declaration of EACH). Malformed/absent/ambiguous -> the
    fail-closed :class:`WrongModelVersionError` (the generic endpoint can mint anything)."""
    rows = (
        session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == version.id)
        )
        .scalars()
        .all()
    )

    def _single(prefix: str) -> str | None:
        found = [
            r.assumption_text[len(prefix) :] for r in rows if r.assumption_text.startswith(prefix)
        ]
        return found[0] if len(found) == 1 else None

    confidence_text = _single(CONFIDENCE_ASSUMPTION_PREFIX)
    horizon_text = _single(HORIZON_ASSUMPTION_PREFIX)
    window_text = _single(WINDOW_ASSUMPTION_PREFIX)
    quantile_text = _single(QUANTILE_ASSUMPTION_PREFIX)
    if (
        confidence_text is None
        or horizon_text is None
        or window_text is None
        or quantile_text is None
        or not _CONFIDENCE_PATTERN.fullmatch(confidence_text)
        or confidence_text not in VAR_Z_SCORES  # the shared v1 confidence vocabulary
        or horizon_text != str(VAR_HORIZON_DAYS)
        or re.fullmatch(r"[0-9]+", window_text) is None
        or quantile_text != VAR_HS_QUANTILE_CONVENTION
        # The adequacy floor is IDENTITY, not registrar courtesy: a generically-minted version
        # (POST /models can stamp any assumptions) with an inadequate window must not bind —
        # window=0 additionally sailed through the 0==0 length check into an IndexError 500
        # (2026-07 review, numeric + line-scan finders independently).
        or int(window_text) < _hs_window_floor(confidence_text)
    ):
        raise WrongModelVersionError(str(version.id), VAR_HS_MODEL_CODE)
    return HsVarParameters(
        confidence_level=Decimal(confidence_text),
        horizon_days=int(horizon_text),
        window_observations=int(window_text),
        quantile_convention=quantile_text,
    )


def _hs_window_floor(confidence_key: str) -> int:
    """The OD-VHS-E adequacy floor, TIGHTENED at the implementation review (2026-07, numeric
    finder): the ratified ``N >= ceil(1/(1-c))`` still yielded ``k = 1`` (the sample MINIMUM —
    the exact condition the floor's rationale refuses) at every integral boundary, incl. BOTH
    v1 vocabulary confidences. Guaranteeing ``k >= 2`` requires ``N·(1-c) > 1`` strictly — the
    floor is the smallest such N (21 at 0.95; 101 at 0.99)."""
    one_minus_c = Decimal(1) - Decimal(confidence_key)
    floor = int((Decimal(1) / one_minus_c).to_integral_value(rounding=ROUND_CEILING))
    while Decimal(floor) * one_minus_c <= Decimal(1):
        floor += 1
    return floor


def _assert_hs_window_adequate(n: int, confidence_key: str) -> None:
    floor = _hs_window_floor(confidence_key)
    if n < floor:
        raise ValueError(
            f"window_observations={n} is below the adequacy floor {floor} for confidence "
            f"{confidence_key} (the order statistic would be the sample minimum - "
            f"statistically meaningless; k >= 2 requires N > 1/(1-c))"
        )


def register_historical_var_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    window_observations: int,
    horizon_days: int = VAR_HORIZON_DAYS,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the historical-simulation VaR model family (VAR-HS-1, OD-VHS-B):
    identity = (code_version, confidence_level, horizon_days, window_observations,
    quantile_convention). Same-label different-declaration -> :class:`ModelVersionConflictError`;
    a non-REGISTERED same-label twin -> :class:`WrongModelVersionError` (the P3-C1 contract).
    The window floor (OD-VHS-E): N >= ceil(1/(1-c)) - below it the order statistic is the
    sample minimum and the estimate is statistically meaningless."""
    text = str(confidence_level).strip()
    if not _CONFIDENCE_PATTERN.fullmatch(text) or len(text) > 6:
        raise ValueError(
            f"confidence_level {confidence_level!r} is not in the v1 vocabulary "
            f"{sorted(VAR_Z_SCORES)} (a new level is a new declared registration)"
        )
    confidence_key = f"{Decimal(text).quantize(Decimal('0.0001')):f}"
    if confidence_key not in VAR_Z_SCORES:
        raise ValueError(
            f"confidence_level {confidence_level} is not in the v1 vocabulary "
            f"{sorted(VAR_Z_SCORES)} (a new level is a new declared registration)"
        )
    if int(horizon_days) != VAR_HORIZON_DAYS:
        raise ValueError(
            f"horizon_days must be {VAR_HORIZON_DAYS} in v1 (sqrt(h) scaling is a recorded seam)"
        )
    n = int(window_observations)
    _assert_hs_window_adequate(n, confidence_key)

    model = session.execute(
        select(Model).where(Model.tenant_id == str(tenant_id), Model.code == VAR_HS_MODEL_CODE)
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=VAR_HS_MODEL_CODE,
            name=VAR_HS_MODEL_NAME,
            model_type=VAR_HS_MODEL_TYPE,
            actor_id=actor_id,
            description=(
                "Plain equal-weight factor-based historical-simulation portfolio VaR over "
                "governed factor exposures x pinned captured factor-return windows "
                "(VAR-HS-1, ENT-027)."
            ),
            actor_type=actor_type,
        )

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == VAR_HS_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            raise WrongModelVersionError(str(version.id), str(model.code))
        declared = declared_hs_var_parameters(session, version)
        if (
            version.code_version != str(code_version)
            or f"{declared.confidence_level:f}" != confidence_key
            or declared.horizon_days != int(horizon_days)
            or declared.window_observations != n
        ):
            raise ModelVersionConflictError(
                VAR_HS_MODEL_CODE,
                VAR_HS_VERSION_LABEL,
                f"{code_version} (confidence_level={confidence_key}, horizon_days="
                f"{horizon_days}, window_observations={n})",
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=VAR_HS_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=VAR_HS_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=(
            *VAR_HS_ASSUMPTIONS_BASE,
            f"{CONFIDENCE_ASSUMPTION_PREFIX}{confidence_key}",
            f"{HORIZON_ASSUMPTION_PREFIX}{int(horizon_days)}",
            f"{WINDOW_ASSUMPTION_PREFIX}{n}",
            f"{QUANTILE_ASSUMPTION_PREFIX}{VAR_HS_QUANTILE_CONVENTION}",
        ),
        limitations=VAR_HS_LIMITATIONS,
        actor_type=actor_type,
    )


# --- P3-7: the ex-ante active-risk / parametric tracking-error model family (OD-P3-7-D) ---

ACTIVE_RISK_MODEL_CODE = "risk.active_risk.parametric"
ACTIVE_RISK_MODEL_NAME = "Ex-ante active risk (parametric tracking error, factor model, 1-day)"
ACTIVE_RISK_MODEL_TYPE = "ACTIVE_RISK"
ACTIVE_RISK_VERSION_LABEL = "v1"
ACTIVE_RISK_METHODOLOGY_REF = "05_analytics_methodologies/active_risk_parametric_v1.md"

#: The declared methodology choices (OD-P3-7-B/D). There are NO free numeric request parameters —
#: the version identity IS ``code_version`` + these fixed conventions (v1). A same-label re-register
#: with a different ``code_version`` is a governed conflict (a new convention set = a new label).
ACTIVE_RISK_ASSUMPTIONS: tuple[str, ...] = (
    "Ex-ANTE (forecast) parametric tracking error under the linear factor model: "
    "TE = sqrt(w_a' * Sigma * w_a), w_a = w_p - w_b (active weights, per factor). This is a "
    "STANDARD DEVIATION (a daily active-return volatility), NOT a quantile - there is NO z factor.",
    "Both sides map through the SAME allocation-v1 CURRENCY-factor model (methodological "
    "symmetry): the PORTFOLIO weight w_p[f] = (sum of the pinned FACTOR_EXPOSURE amounts for "
    "factor f) / portfolio_value, where portfolio_value = the net signed total of all pinned "
    "exposure atoms; the BENCHMARK weight w_b[f] = the sum of the pinned constituent weights whose "
    "constituent_currency maps to factor f (matched on the factor's currency_code scope, the same "
    "index the portfolio allocation uses), NORMALIZED by the total pinned constituent weight.",
    "Inputs: ONE COMPLETED factor-exposure run x ONE COMPLETED covariance run "
    "(SIMPLE/DAILY, unannualized) x ONE captured benchmark membership set x the factor "
    "definitions. Every portfolio factor AND every benchmark-mapped currency factor MUST be in "
    "the covariance factor set - a gap fails closed (NO imputation). A constituent with a NULL "
    "currency, an unmappable currency, a zero total benchmark weight, or a zero portfolio value "
    "fails closed pre-create.",
    "Units: DAILY, UNANNUALIZED active-return volatility (the covariance substrate is daily; "
    "annualization is a later, declared transform - the Pope-Yadav caution).",
    "Radicand quantization floor: w_a'*Sigma*w_a in [-tol, 0) with tol = F^2 * max(w_i^2) * 1E-19 "
    "is treated as 0 (a benchmark-matching portfolio yields TE 0); below -tol the run FAILS closed "
    "(a non-PSD input). Computed in Decimal at 50-digit precision; te quantize_HALF_UP to 12 "
    "decimal places (the Numeric(20,12) return-fraction scale).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-P3-7-B/G/H).
ACTIVE_RISK_LIMITATIONS: tuple[str, ...] = (
    "SPECIFIC/IDIOSYNCRATIC ACTIVE RISK = 0: the CURRENCY-family indicator-loading factor model "
    "carries NO residual term - active risk outside the factor covariance is invisible (the "
    "allocation-v1 limitation propagates to both sides; the Grinold-Kahn specific term is 0 here).",
    "EX-ANTE (forecast) only. The EX-POST / realized tracking error (ESMA: the volatility of the "
    "realized fund-minus-benchmark return difference) and active return / information ratio are "
    "DEFERRED - they require a portfolio RETURN series, which does not exist; deriving it "
    "(flow-adjusted TWR) is a performance-measurement methodology (its own planned slice). The "
    "shipped number is a FORECAST and MUST NOT be read as the UCITS ex-post disclosure figure.",
    "DAILY, UNANNUALIZED; sqrt(T) annualization is a later, separately declared transform "
    "(Pope-Yadav: naive annualization biases TE under serial correlation).",
    "Benchmark weights are NORMALIZED by their captured sum (vendor rounding tolerance); a NULL "
    "constituent currency is a refusal, NEVER imputed to the benchmark header currency (which "
    "would misattribute currency risk).",
    "Relative VaR (the CESR/10-788 sibling), active-share, and benchmark-relative sensitivities "
    "are recorded seams, not built here. Inherits the sample-covariance estimation error.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def register_active_risk_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the active-risk ``model`` + a ``model_version`` for this
    ``code_version`` identity (P3-7, OD-P3-7-D). Unlike VaR/covariance there are NO free numeric
    request parameters — the v1 conventions ARE the identity — so the version resolution keys on
    ``code_version`` alone: re-registering the same ``version_label`` with a DIFFERENT
    ``code_version`` raises :class:`ModelVersionConflictError` (mint a new label instead)."""
    model = session.execute(
        select(Model).where(Model.tenant_id == str(tenant_id), Model.code == ACTIVE_RISK_MODEL_CODE)
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=ACTIVE_RISK_MODEL_CODE,
            name=ACTIVE_RISK_MODEL_NAME,
            model_type=ACTIVE_RISK_MODEL_TYPE,
            actor_id=actor_id,
            description=(
                "Ex-ante parametric tracking error over governed factor exposures, a governed "
                "sample covariance, and a captured benchmark membership set (P3-7, ENT-027)."
            ),
            actor_type=actor_type,
        )

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == ACTIVE_RISK_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            # A same-label twin minted via the GENERIC registration (status=None) is a
            # REGISTRATION conflict too (the P3-C1 register/run-consistency lesson).
            raise WrongModelVersionError(str(version.id), str(model.code))
        if version.code_version != str(code_version):
            raise ModelVersionConflictError(
                ACTIVE_RISK_MODEL_CODE, ACTIVE_RISK_VERSION_LABEL, str(code_version)
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=ACTIVE_RISK_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=ACTIVE_RISK_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=ACTIVE_RISK_ASSUMPTIONS,
        limitations=ACTIVE_RISK_LIMITATIONS,
        actor_type=actor_type,
    )
