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

from sqlalchemy.orm import Session

from irp_shared.model.assumptions import (
    load_assumption_texts,
    require_declared,
    sole_declared,
)
from irp_shared.model.models import ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
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
    # The inventory identity is (tenant, model, version_label) — the DB unique key. Both the model
    # and the version are resolve-or-register (race-safe savepoint; MD-H1 OD-D): a concurrent first
    # bootstrap re-SELECTs the peer instead of a 500. A same-label registration with a DIFFERENT
    # code_version is a governed conflict (never an IntegrityError), because an immutable version
    # cannot be re-pointed.
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=SENSITIVITY_MODEL_CODE,
        name=SENSITIVITY_MODEL_NAME,
        model_type=SENSITIVITY_MODEL_TYPE,
        actor_id=actor_id,
        description="Closed-form curve-node DV01 / spread-DV01 (P3-1, ENT-028).",
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=SENSITIVITY_VERSION_LABEL,
        register=lambda: register_model_version(
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
        ),
    )
    # Identity/conflict checks run unconditionally on the resolved row: they pass trivially for a
    # row THIS call minted, and catch a squatted (non-REGISTERED GENERIC-path twin — P3-C1 OD-B)
    # or code_version-mismatched peer (the race + idempotent re-invocation path).
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            SENSITIVITY_MODEL_CODE, SENSITIVITY_VERSION_LABEL, str(code_version)
        )
    return version


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
    # (tenant, model, version_label) is the DB unique key — both legs resolve-or-register (race-safe
    # savepoint; MD-H1 OD-D). A different code_version under the same label is a governed conflict
    # (see the sensitivity twin above), never an IntegrityError 500.
    model = resolve_or_register_model(
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
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=FACTOR_EXPOSURE_VERSION_LABEL,
        register=lambda: register_model_version(
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
        ),
    )
    # Identity/conflict checks run unconditionally: trivially pass for a row THIS call minted, catch
    # a squatted (non-REGISTERED GENERIC-path twin — P3-C1 OD-B) or code_version-mismatched peer.
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            FACTOR_EXPOSURE_MODEL_CODE, FACTOR_EXPOSURE_VERSION_LABEL, str(code_version)
        )
    return version


#: The per-tenant inventory identity of the PROXY factor-exposure model (PA-2, OD-PA-2-A —
#: the SECOND registered model family writing ``factor_exposure_result``; the VAR-HS-1
#: one-table/many-models precedent). ``code_version``-only identity: the proxy WEIGHTS are pinned
#: snapshot content (ENT-019 ``proxy_mapping``), never parameters.
FACTOR_EXPOSURE_PROXY_MODEL_CODE = "risk.factor_exposure.proxy"
FACTOR_EXPOSURE_PROXY_MODEL_NAME = (
    "Factor-exposure proxy projection (captured private-asset proxy weights, CURRENCY family)"
)
FACTOR_EXPOSURE_PROXY_VERSION_LABEL = "v1"
FACTOR_EXPOSURE_PROXY_METHODOLOGY_REF = "05_analytics_methodologies/factor_exposure_proxy_v1.md"

#: The declared methodology choices (mirrored into model_assumption rows; OD-PA-2-B).
FACTOR_EXPOSURE_PROXY_ASSUMPTIONS: tuple[str, ...] = (
    "Proxied-else-indicator allocation over ONE mixed public+private book: an atom whose "
    "instrument has >= 1 pinned CURRENT proxy_mapping row allocates exposure_amount * weight per "
    "proxy factor (loading = the captured weight, signed); every other atom follows the "
    "allocation-v1 mark_currency indicator rule unchanged.",
    "A proxied instrument's rows REPLACE its indicator row (never both).",
    "Proxy weights are CAPTURED governance judgments (proxy_mapping.mapping_method records "
    "provenance) pinned into the snapshot - a later supersede cannot move a historical run "
    "(TR-09); regression-estimated weights from the desmoothed return series are the recorded v2.",
    "The unallocated residual (1 - sum(w)) of a partial proxy stays UNMODELED (PA-0 OD-D): "
    "derivable as atom - sum(allocated), never imputed, no synthetic residual factor.",
    "Every pinned proxy row's factor MUST be in the run's pinned factor list - an unpinned proxy "
    "factor refuses the run closed (no silent dropping).",
    "factor_exposure = quantize_HALF_UP(weight * exposure_amount, 6) (Numeric(28,6), base "
    "currency); signs preserved.",
)

#: The recorded scope-outs (mirrored into model_limitation rows; decision record Part 2).
FACTOR_EXPOSURE_PROXY_LIMITATIONS: tuple[str, ...] = (
    "Captured MANUAL-judgment weights only - regression-estimated weights from the PA-1 "
    "desmoothed return series are the recorded v2 (the moment the desmoothed number becomes an "
    "input).",
    "CURRENCY-family proxy factors only (the platform-wide v1 scope; PA-0 OD-H).",
    "The unallocated residual of a partial proxy is unmodeled - a residual/idiosyncratic "
    "variance term is a v2 candidate alongside the regression weights.",
    "Proxied rows break the contributions-sum-to-total identity BY DESIGN (sum = sum(w) * atom); "
    "the REQ-MKT-003 exactness holds per-UNPROXIED-atom only (test-asserted in both regimes).",
    "ACTIVE RISK does not consume proxy runs in v1: its weight normalization divides by the "
    "summed pinned rows, which equals the net book value ONLY under a partitioning run - a "
    "partial proxy would silently redistribute the unmodeled residual (fail-closed gate at "
    "run_active_risk; a proxy-aware denominator is the recorded v2). VaR/HS-VaR/scenario "
    "consume absolute exposures and are unaffected.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def register_factor_exposure_proxy_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the PROXY factor-exposure ``model`` + a ``model_version`` for this
    ``code_version`` (PA-2, OD-PA-2-A — the ``register_factor_exposure_model`` shape). The
    returned ``model_version.id`` is what a proxy factor-exposure run binds; the SHARED
    ``run_factor_exposure`` binder dispatches on the bound model's code."""
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=FACTOR_EXPOSURE_PROXY_MODEL_CODE,
        name=FACTOR_EXPOSURE_PROXY_MODEL_NAME,
        model_type=FACTOR_EXPOSURE_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Private-asset proxy projection: pinned proxy_mapping weights allocate a private "
            "instrument's exposure onto public CURRENCY factors; unproxied atoms follow the "
            "allocation-v1 indicator rule (PA-2, ENT-028 family; ENT-019's first governed "
            "consumer)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=FACTOR_EXPOSURE_PROXY_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=FACTOR_EXPOSURE_PROXY_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=FACTOR_EXPOSURE_PROXY_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=FACTOR_EXPOSURE_PROXY_ASSUMPTIONS,
            limitations=FACTOR_EXPOSURE_PROXY_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            FACTOR_EXPOSURE_PROXY_MODEL_CODE,
            FACTOR_EXPOSURE_PROXY_VERSION_LABEL,
            str(code_version),
        )
    return version


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


#: Strictly-decimal pattern (covariance window_observations + the HS-VaR window sub-field).
_DIGITS_PATTERN = re.compile(r"[0-9]+")


def declared_window_observations(session: Session, version: ModelVersion) -> int:
    """Parse the version's declared estimation window from its ``model_assumption`` rows (the
    OD-P3-4-G identity: exactly ONE ``window_observations=N`` assumption must exist)."""
    # Exactly one, strictly-decimal declaration — a version minted with a malformed/absent window
    # (reachable via the GENERIC model-registration endpoint under the same permission) is NOT a
    # covariance-model identity; refuse fail-closed (422), never a bare int() ValueError (500).
    declared = require_declared(
        load_assumption_texts(session, version),
        WINDOW_ASSUMPTION_PREFIX,
        pattern=_DIGITS_PATTERN,
        on_invalid=lambda: WrongModelVersionError(str(version.id), COVARIANCE_MODEL_CODE),
    )
    return int(declared)


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
    # Both legs resolve-or-register (race-safe savepoint; MD-H1 OD-D). The version identity includes
    # the declared window (OD-P3-4-G) — a same-label re-register with a different code_version OR
    # window is a governed conflict, never an IntegrityError 500.
    model = resolve_or_register_model(
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
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=COVARIANCE_VERSION_LABEL,
        register=lambda: register_model_version(
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
        ),
    )
    # Identity/conflict checks run unconditionally (trivially pass for a row THIS call minted — the
    # window is registered into its assumptions — and catch a squatted or code_version/window peer).
    if version.status != "REGISTERED":
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
    texts = load_assumption_texts(session, version)
    confidence_text = sole_declared(texts, CONFIDENCE_ASSUMPTION_PREFIX)
    horizon_text = sole_declared(texts, HORIZON_ASSUMPTION_PREFIX)
    z_text = sole_declared(texts, Z_ASSUMPTION_PREFIX)
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
    # Both legs resolve-or-register (race-safe savepoint; MD-H1 OD-D). The version identity includes
    # the declared confidence/horizon (OD-P3-5-D) — a same-label re-register differing on
    # code_version/confidence/horizon is a governed conflict, never an IntegrityError 500.
    model = resolve_or_register_model(
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
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=VAR_VERSION_LABEL,
        register=lambda: register_model_version(
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
        ),
    )
    # Identity/conflict checks run unconditionally (trivially pass for a row THIS call minted — the
    # declared params are in its assumptions — and catch a squatted or mismatched peer).
    if version.status != "REGISTERED":
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
            f"{code_version} (confidence_level={confidence_key}, horizon_days={horizon_days})",
        )
    return version


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
    texts = load_assumption_texts(session, version)
    confidence_text = sole_declared(texts, CONFIDENCE_ASSUMPTION_PREFIX)
    horizon_text = sole_declared(texts, HORIZON_ASSUMPTION_PREFIX)
    window_text = sole_declared(texts, WINDOW_ASSUMPTION_PREFIX)
    quantile_text = sole_declared(texts, QUANTILE_ASSUMPTION_PREFIX)
    if (
        confidence_text is None
        or horizon_text is None
        or window_text is None
        or quantile_text is None
        or not _CONFIDENCE_PATTERN.fullmatch(confidence_text)
        or confidence_text not in VAR_Z_SCORES  # the shared v1 confidence vocabulary
        or horizon_text != str(VAR_HORIZON_DAYS)
        or _DIGITS_PATTERN.fullmatch(window_text) is None
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

    # Both legs resolve-or-register (race-safe savepoint; MD-H1 OD-D). The version identity includes
    # the declared confidence/horizon/window (OD-VHS-D) — a same-label re-register differing on any
    # of those is a governed conflict, never an IntegrityError 500.
    model = resolve_or_register_model(
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
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=VAR_HS_VERSION_LABEL,
        register=lambda: register_model_version(
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
        ),
    )
    # Identity/conflict checks run unconditionally (trivially pass for a row THIS call minted, catch
    # a squatted or code_version/confidence/horizon/window-mismatched peer).
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
    # Both legs resolve-or-register (race-safe savepoint; MD-H1 OD-D). No free numeric request
    # parameter — the v1 conventions ARE the identity — so a same-label re-register with a different
    # code_version is a governed conflict, never an IntegrityError 500.
    model = resolve_or_register_model(
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
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=ACTIVE_RISK_VERSION_LABEL,
        register=lambda: register_model_version(
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
        ),
    )
    # Identity/conflict checks run unconditionally: trivially pass for a row THIS call minted, catch
    # a squatted (non-REGISTERED GENERIC-path twin) or code_version-mismatched peer.
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            ACTIVE_RISK_MODEL_CODE, ACTIVE_RISK_VERSION_LABEL, str(code_version)
        )
    return version


# --- BT-1: the VaR-backtesting model family (OD-BT-1-A) ---

VAR_BACKTEST_MODEL_CODE = "risk.var_backtest"
VAR_BACKTEST_MODEL_NAME = "VaR backtesting (exception count, Kupiec POF, Basel zone, v1)"
VAR_BACKTEST_MODEL_TYPE = "VAR_BACKTEST"
VAR_BACKTEST_VERSION_LABEL = "v1"
VAR_BACKTEST_METHODOLOGY_REF = "05_analytics_methodologies/var_backtesting_v1.md"

#: The declared-parameter assumption prefix (OD-BT-1-A: the Kupiec test significance level is part
#: of the version identity — parsed back for the identity check + the binder's read; the P3-5
#: declared-parameter precedent). The v1 vocabulary is EXACTLY the fixed chi-square(1) critical
#: set (``var_backtest_kernel.CHI2_1DF_CRITICALS``) — extending it is a NEW declared registration,
#: never a runtime quantile.
ALPHA_ASSUMPTION_PREFIX = "alpha="

#: Strict decimal-fraction pattern for the declared alpha (e.g. '0.05').
_ALPHA_PATTERN = re.compile(r"0\.[0-9]{1,4}")

#: The declared methodology choices EXCLUDING the per-registration alpha (appended per call;
#: OD-BT-1-D/E/F/G).
VAR_BACKTEST_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Outcomes analysis (SR 11-7) of ONE VaR method per run: per aligned pair the exception "
    "indicator e_i = 1 iff -P&L_i > VaR_i (STRICT - a loss exactly AT VaR is not an exception; "
    "the Basel 'loss exceeding VaR' convention).",
    "Realized P&L_i = end_mv - begin_mv - net_external_flow per DIETZ sub-period of ONE COMPLETED "
    "portfolio-return run (the flow-adjusted ACTUAL-P&L leg; hypothetical/clean P&L is a deferred "
    "leg, never conflated). Each VaR forecast applies as of its window_end and pairs with EXACTLY "
    "the sub-period starting there and spanning horizon_days CALENDAR days; ANY unpaired forecast "
    "refuses the whole run (NO imputation, no silent partial pairing).",
    "Kupiec (1995) POF: LR = -2 ln[(1-p)^(N-x) p^x] + 2 ln[(1-x/N)^(N-x) (x/N)^x], asymptotically "
    "chi-square(1), TWO-SIDED (too few exceptions also rejects); decision = REJECT iff LR exceeds "
    "the FIXED chi-square(1) critical value for the declared alpha - NO p-value/erf at runtime.",
    "Basel (BCBS Jan-1996) traffic-light zone GREEN 0-4 / YELLOW 5-9 / RED >= 10, emitted ONLY on "
    "its defined domain (confidence_level == 0.99 AND n_pairs == 250) - never scaled or "
    "extrapolated off-domain.",
    "Computed in Decimal at 50-digit context; the LR statistic quantize_HALF_UP internally to 12 "
    "decimal places, then quantize_HALF_UP to the Numeric(28,6) result scale - and the "
    "REJECT/FAIL_TO_REJECT decision is taken on that STORED 6dp value against the 6dp critical, "
    "so the persisted row always reproduces its own decision (a knife-edge LR within ~5e-7 of a "
    "critical follows the stored value; the exact inputs are reproducible from the pinned "
    "snapshot).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; decision record Part 3).
VAR_BACKTEST_LIMITATIONS: tuple[str, ...] = (
    "CAPTURED-HOLDINGS P&L BIAS (the PM-1 first-class limitation, third named carry): uncaptured "
    "income understates realized losses' offsets and realized P&L alike - a backtest over a leaky "
    "book is ANTI-CONSERVATIVE. Mitigation stays operational (capture the cash), never imputation.",
    "ACTUAL (flow-adjusted) P&L only - the Basel hypothetical/clean-P&L leg needs static-portfolio "
    "repricing the platform does not yet have; DEFERRED and recorded.",
    "Kupiec POF only: no Christoffersen independence/conditional-coverage (the natural BT-2), no "
    "Basel multiplier arithmetic (the zone is the recorded output), no p-values (critical-value "
    "decisions at the declared alpha).",
    "Small-N honesty: the POF test is asymptotic; KUPIEC_LR is emitted for any N >= 1 with n_pairs "
    "recorded on every row so a reader can weigh it; the Basel zone refuses to exist off-domain.",
    "Calendar-day horizon interpretation (consistent with PM-1's calendar-day Dietz weighting); "
    "trading-day calendar validation is the same deferred data-quality slice P3-8 recorded.",
    "One backtest run = ONE VaR method (uniform metric_type); cross-method comparison is two runs "
    "side by side - no joint test.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def declared_var_backtest_alpha(session: Session, version: ModelVersion) -> Decimal:
    """Parse the version's declared Kupiec ``alpha`` from its ``model_assumption`` rows (the
    OD-BT-1-A identity: exactly ONE strictly-well-formed declaration, inside the fixed critical
    set). A malformed, absent, ambiguous, or off-vocabulary declaration is NOT a var-backtest
    identity — refuse fail-closed (:class:`WrongModelVersionError`, 422), never a bare parse
    crash (generically minted same-label versions exist — the P3-4 review lesson)."""
    from irp_shared.risk.var_backtest_kernel import CHI2_1DF_CRITICALS

    raw = require_declared(
        load_assumption_texts(session, version),
        ALPHA_ASSUMPTION_PREFIX,
        pattern=_ALPHA_PATTERN,
        on_invalid=lambda: WrongModelVersionError(str(version.id), VAR_BACKTEST_MODEL_CODE),
    )
    alpha = Decimal(raw)
    if alpha not in CHI2_1DF_CRITICALS:
        raise WrongModelVersionError(str(version.id), VAR_BACKTEST_MODEL_CODE)
    return alpha


def register_var_backtest_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    alpha: str | Decimal = "0.05",
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the VaR-backtesting ``model`` + a ``model_version`` for this
    ``(code_version, alpha)`` identity (BT-1, OD-BT-1-A — the P3-5 declared-parameter precedent).
    The v1 alpha vocabulary is the fixed chi-square(1) critical set {0.05, 0.01}; re-registering
    the same label with ANY different declaration raises :class:`ModelVersionConflictError` (mint
    a new label); a same-label twin minted via the GENERIC registration (status != REGISTERED)
    raises :class:`WrongModelVersionError` (the P3-C1 register/run-consistency lesson)."""
    from irp_shared.risk.var_backtest_kernel import CHI2_1DF_CRITICALS

    # STRICT parse — never coerce (the P3-5 lesson: Decimal('abc') raises InvalidOperation, not
    # ValueError; a near-vocabulary value must be REFUSED, not rounded onto the set).
    text = str(alpha).strip()
    if not _ALPHA_PATTERN.fullmatch(text) or Decimal(text) not in CHI2_1DF_CRITICALS:
        raise ValueError(
            f"alpha {alpha!r} is not in the v1 critical-value vocabulary "
            f"{sorted(str(a) for a in CHI2_1DF_CRITICALS)} (a new level is a new declared "
            f"registration, never a runtime quantile)"
        )
    alpha_key = f"{Decimal(text).normalize():f}"

    # Both legs resolve-or-register (race-safe savepoint; MD-H1 OD-D). The version identity includes
    # the declared Kupiec alpha (OD-BT-1-A) — a same-label re-register differing on code_version or
    # alpha is a governed conflict, never an IntegrityError 500.
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=VAR_BACKTEST_MODEL_CODE,
        name=VAR_BACKTEST_MODEL_NAME,
        model_type=VAR_BACKTEST_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "VaR backtesting - exception counting, the Kupiec POF coverage test, and the "
            "Basel traffic-light zone over realized flow-adjusted P&L vs the pinned VaR "
            "forecasts of one method (BT-1, ENT-055)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=VAR_BACKTEST_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=VAR_BACKTEST_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=VAR_BACKTEST_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *VAR_BACKTEST_ASSUMPTIONS_BASE,
                f"{ALPHA_ASSUMPTION_PREFIX}{alpha_key}",
            ),
            limitations=VAR_BACKTEST_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    # Identity/conflict checks run unconditionally: trivially pass for a row THIS call minted, catch
    # a squatted or code_version/alpha-mismatched peer.
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_var_backtest_alpha(session, version)  # malformed -> 422 class
    if version.code_version != str(code_version) or f"{declared.normalize():f}" != alpha_key:
        raise ModelVersionConflictError(
            VAR_BACKTEST_MODEL_CODE,
            VAR_BACKTEST_VERSION_LABEL,
            f"{code_version} (alpha={alpha_key})",
        )
    return version


# --- P3-6: the deterministic factor-shock scenario model family (OD-P3-6-D) ---

SCENARIO_MODEL_CODE = "risk.scenario.factor_shock"
SCENARIO_MODEL_NAME = "Deterministic linear factor-shock scenario P&L (v1)"
SCENARIO_MODEL_TYPE = "SCENARIO"
SCENARIO_VERSION_LABEL = "v1"
SCENARIO_METHODOLOGY_REF = "05_analytics_methodologies/scenario_factor_shock_v1.md"

#: NO free numeric request parameter — the shocks live in the PINNED, versioned scenario content
#: (audited THERE), not in the model; the model is the fixed APPLICATION RULE. Version identity is
#: ``code_version`` alone (the active-risk precedent).
SCENARIO_ASSUMPTIONS: tuple[str, ...] = (
    "Deterministic LINEAR first-order P&L over the pinned per-factor exposures of ONE COMPLETED "
    "FACTOR_EXPOSURE run: pnl_i = quantize_HALF_UP(exposure_i * shock_i, 6) per factor; total = "
    "sum of the per-factor rows (the same linear factor substrate dV = sum x_i*r_i every risk "
    "number uses). A shock is a signed RETURN fraction (-0.10 = -10%); the shock vector is the "
    "pinned scenario content, NOT a request parameter.",
    "Partial-coverage semantics (OD-P3-6-G): an exposed factor the scenario does NOT name is "
    "shock 0 (a deterministic scenario is a COMPLETE specification of what moves — 'unnamed = "
    "unchanged', NOT statistical imputation). Every exposed factor gets a result row (its shock "
    "echoed, 0 included); the TOTAL row carries n_factors_exposed / n_factors_shocked / "
    "n_shocks_unmatched. A shock naming a factor with no exposure produces no row (counted in "
    "n_shocks_unmatched).",
    "CURRENCY factor family only (v1 platform scope; enforced at the shock binder). RETURN shock "
    "type only. Computed in Decimal; base currency = the exposure run's base.",
)

SCENARIO_LIMITATIONS: tuple[str, ...] = (
    "LINEAR first-order only — NO instrument revaluation, convexity, gamma, or path dependence; a "
    "large shock on a nonlinear book is mis-stated with no warning beyond this limitation.",
    "DECLARED shocks only (whatever their provenance — hypothetical / offline-historical / "
    "regulatory). In-platform historical-window replay (shocks computed from the captured "
    "factor_return series) is a recorded v2; worst-case / plausibility-constrained scenario search "
    "(Studer 1997; Breuer et al. 2009) is a recorded v3.",
    "scenario_type is a PROVENANCE LABEL, not an attestation — REGULATORY does not imply approval; "
    "maker-checker on definitions is the P7 validation workflow.",
    "Inherits the captured-holdings-book limitation from the consumed exposure run.",
    "validation_status UNVALIDATED — recorded, non-enforcing until the P7 validation workflow.",
)


def register_scenario_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the scenario ``model`` + a ``model_version`` for this
    ``code_version`` identity (P3-6, OD-P3-6-D). NO free numeric request parameter — the shocks are
    the pinned scenario content — so version resolution keys on ``code_version`` alone (the
    active-risk precedent); a same-label re-register with a different code_version is a conflict."""
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=SCENARIO_MODEL_CODE,
        name=SCENARIO_MODEL_NAME,
        model_type=SCENARIO_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Deterministic linear factor-shock scenario P&L over the pinned exposures of one "
            "COMPLETED factor-exposure run x a pinned versioned scenario shock set (P3-6, ENT-030)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=SCENARIO_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=SCENARIO_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=SCENARIO_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=SCENARIO_ASSUMPTIONS,
            limitations=SCENARIO_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    # Identity/conflict checks run unconditionally: trivially pass for a row THIS call minted, catch
    # a squatted (non-REGISTERED) or code_version-mismatched peer.
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            SCENARIO_MODEL_CODE, SCENARIO_VERSION_LABEL, str(code_version)
        )
    return version


#: The per-tenant inventory identity of the proxy-weight regression model (PA-3, OD-PA-3-A/D).
PROXY_WEIGHT_MODEL_CODE = "risk.proxy_weight.regression"
PROXY_WEIGHT_MODEL_NAME = "Regression-estimated proxy factor weights (OLS on desmoothed returns)"
PROXY_WEIGHT_MODEL_TYPE = "PROXY_WEIGHT"
PROXY_WEIGHT_VERSION_LABEL = "v1"
PROXY_WEIGHT_METHODOLOGY_REF = "05_analytics_methodologies/proxy_weight_regression_v1.md"

#: The declared minimum-observations floor is registration-supplied and part of the model identity
#: (OD-PA-3-D), appended per call; the run additionally enforces max(declared, k + 2).
MIN_OBSERVATIONS_ASSUMPTION_PREFIX = "min_observations="

#: The declared methodology choices EXCLUDING min_observations (registration-supplied, appended).
PROXY_WEIGHT_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Unconstrained ORDINARY LEAST SQUARES with an intercept: y = X b + e, X = [1 | f_1..f_k]; "
    "b = (X'X)^-1 X'y. NO sum-to-1, NO non-negativity (the Sharpe-1992 constrained form is a "
    "recorded v2; PA-0 deliberately admits negative/no-sum proxy weights).",
    "Target y = the consumed DESMOOTHED_RETURN run's per-period desmoothed series (PA-1); the "
    "regressors are the candidate factors' captured returns compounded over each appraisal period "
    "(deterministic; a period lacking full factor coverage fails the run closed - NO zero-fill).",
    "Reports per coefficient (intercept + k slopes) the estimate AND its standard error; plus R^2, "
    "n_observations, and the residual stdev - the honest-uncertainty statement.",
    "Computed in Decimal at 50-digit context; quantize_HALF_UP to 12 decimal places (the "
    "Numeric(20,12) column scale).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-PA-3 Part 3).
PROXY_WEIGHT_LIMITATIONS: tuple[str, ...] = (
    "Estimates are MODEL OUTPUT, snapshot/run/model-bound - NEVER auto-written into proxy_mapping; "
    "promotion is a deliberate second capture step citing the estimation run (OD-PA-3-E).",
    "Appraisal series are SHORT (quarterly marks => wide standard errors, reported per coefficient "
    "and never hidden); the estimate regresses a MODEL OUTPUT (the desmoothed series), so "
    "desmoothing model risk (the declared alpha) propagates into the weights.",
    "CURRENCY-family candidate factors only (the PA-2 factor-universe boundary); a non-CURRENCY "
    "candidate fails the run closed. Single-currency series only (no FX translation).",
    "Unconstrained OLS can produce weights an analyst should reject - which is WHY promotion is "
    "human-mediated. Constrained (Sharpe 1992) and summed-lag (Dimson 1979 / Asness-Krail-Liew "
    "2001) variants are recorded v2s.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def declared_min_observations(session: Session, version: ModelVersion) -> int:
    """Parse the version's declared minimum-observations floor from its ``model_assumption`` rows
    (the OD-PA-3-D identity: exactly ONE ``min_observations=N``). Malformed/absent/ambiguous -> the
    fail-closed :class:`WrongModelVersionError` (the generic endpoint can mint anything)."""
    declared = require_declared(
        load_assumption_texts(session, version),
        MIN_OBSERVATIONS_ASSUMPTION_PREFIX,
        pattern=_DIGITS_PATTERN,
        on_invalid=lambda: WrongModelVersionError(str(version.id), PROXY_WEIGHT_MODEL_CODE),
    )
    return int(declared)


def register_proxy_weight_regression_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    min_observations: int,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the proxy-weight regression ``model`` + a ``model_version`` for this
    ``(code_version, min_observations)`` identity (PA-3, OD-PA-3-D — the covariance-window
    precedent). ``min_observations`` (>= 3: intercept + >= 1 slope + >= 1 residual df) is recorded
    as a ``model_assumption`` AND is part of the version-resolution identity: a same-label
    re-register with a DIFFERENT ``code_version`` OR floor raises :class:`ModelVersionConflictError`
    (mint a new label instead)."""
    if min_observations < 3:
        raise ValueError(
            "min_observations must be >= 3 (intercept + >= 1 slope + >= 1 residual df)"
        )
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=PROXY_WEIGHT_MODEL_CODE,
        name=PROXY_WEIGHT_MODEL_NAME,
        model_type=PROXY_WEIGHT_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "OLS regression of a private instrument's desmoothed appraisal return series on "
            "candidate public factor returns (PA-3, ENT-057)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=PROXY_WEIGHT_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=PROXY_WEIGHT_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=PROXY_WEIGHT_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *PROXY_WEIGHT_ASSUMPTIONS_BASE,
                f"{MIN_OBSERVATIONS_ASSUMPTION_PREFIX}{int(min_observations)}",
            ),
            limitations=PROXY_WEIGHT_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version) or declared_min_observations(
        session, version
    ) != int(min_observations):
        raise ModelVersionConflictError(
            PROXY_WEIGHT_MODEL_CODE,
            PROXY_WEIGHT_VERSION_LABEL,
            f"{code_version} (min_observations={min_observations})",
        )
    return version


# --- PA-4: total parametric VaR = factor + idiosyncratic residual variance (OD-PA-4-B) ---

#: The per-tenant inventory identity of the total-parametric-VaR model (PA-4). A DIFFERENT model
#: CODE from the plain parametric family (so the plain family is byte-untouched), but the SAME
#: declared-parameter machinery (confidence/horizon/z) — dispatched through the SAME binder.
VAR_TOTAL_MODEL_CODE = "risk.var.parametric_total"
VAR_TOTAL_MODEL_NAME = "Total parametric VaR (factor + idiosyncratic residual, 1-day)"
VAR_TOTAL_VERSION_LABEL = "v1"
VAR_TOTAL_METHODOLOGY_REF = "05_analytics_methodologies/var_parametric_total_v1.md"

#: The DECLARED trading-day frequency-conversion constants (OD-PA-4-D, amended per the vendor-
#: practice benchmark): the appraisal-period residual stdev de-scales to daily on a TRADING-day
#: grid — d_t = appraisal_days * (TRADING/CALENDAR); the ratio constants are fixed, the appraisal
#: cadence is a per-registration declared parameter (see APPRAISAL_DAYS_ASSUMPTION_PREFIX).
VAR_TOTAL_TRADING_DAYS_PER_YEAR = 252
VAR_TOTAL_CALENDAR_DAYS_PER_YEAR = 365
#: The DECLARED appraisal-period length in CALENDAR days (model identity; e.g. 91 for quarterly).
#: OD-D refinement: the pinned ESTIMATION_SUMMARY row carries no span dates, so the cadence is a
#: declared parameter (auditable, like confidence/horizon) rather than derived from a pin.
APPRAISAL_DAYS_ASSUMPTION_PREFIX = "appraisal_days="

#: Total-family declared choices EXCLUDING the per-registration confidence/horizon/z (appended per
#: call, exactly as the parametric family). Adds the residual leg + the frequency conversion.
VAR_TOTAL_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Total parametric VaR: sigma_total = sqrt(x'*Sigma*x + SUM_i (MV_i * sigma_e,i,daily)^2); "
    "VaR_alpha = z_alpha * sigma_total (1-day). The FACTOR leg x'*Sigma*x is the plain parametric "
    "family unchanged; the IDIOSYNCRATIC leg adds, per PROXIED instrument, its cited proxy-weight "
    "estimate's residual variance (Sharpe 1963 single-index diagonal - residuals independent "
    "across instruments and of the factors).",
    "Idiosyncratic inputs: per proxied instrument, the pinned open REGRESSION proxy_mapping (which "
    "instruments are proxied + the citation) x the cited PROXY_WEIGHT_ESTIMATE run's "
    "ESTIMATION_SUMMARY row (residual_stdev). MV_i = the instrument's total pinned factor exposure "
    "(the projected market exposure the factor model sees - consistent with the factor leg). "
    "Indicator (non-proxied) and MANUAL-method instruments carry ZERO idiosyncratic variance (no "
    "estimation evidence - the P3-3 limitation stands for them, restated).",
    "Frequency conversion (DECLARED): sigma_e,daily = sigma_e,period / sqrt(d_t), "
    "d_t = appraisal_days * (252/365); appraisal_days is a DECLARED model-identity parameter (the "
    "appraisal cadence, e.g. 91 for quarterly) - the ESTIMATION_SUMMARY carries no span, so the "
    "cadence is declared like confidence/horizon, not derived. Calendar-aware per-period "
    "trading-day counts are a recorded v2.",
    "z_alpha is a REGISTERED constant from the enumerated confidence vocabulary - no runtime "
    "inverse-normal-CDF. Computed in Decimal at 50-digit context; sigma/VaR quantize_HALF_UP to "
    "6dp (Numeric(28,6)); residual_variance echoed at 20dp (Numeric(38,20)).",
)

#: Total-family recorded scope-outs.
VAR_TOTAL_LIMITATIONS: tuple[str, ...] = (
    "DIAGONAL residuals only (Sharpe 1963; Barra/Axioma vendor-standard) - no residual "
    "cross-correlation; residual shrinkage (Barra Bayesian) + EWMA weighting (Axioma) are v2s.",
    "The residual is hostage to the PA-3 estimate quality (short appraisal series => noisy "
    "sigma_e; the estimate's per-coefficient std errors stay visible on the pinned estimate).",
    "Non-proxied and MANUAL-method instruments carry ZERO idiosyncratic risk (the allocation-v1 "
    "specific-risk=0 limitation propagates for them).",
    "Flat 252/365 trading-day ratio over the MEAN period (calendar-aware per-period counts a v2); "
    "1-day horizon only; historical-simulation + ES total analogues are recorded v2s.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def declared_appraisal_days(session: Session, version: ModelVersion) -> int:
    """Parse the total-VaR version's declared appraisal-period length (calendar days) from its
    ``model_assumption`` rows (the OD-PA-4-D identity: exactly ONE ``appraisal_days=N``, N >= 1).
    Malformed/absent/ambiguous -> the fail-closed :class:`WrongModelVersionError`."""
    declared = require_declared(
        load_assumption_texts(session, version),
        APPRAISAL_DAYS_ASSUMPTION_PREFIX,
        pattern=_DIGITS_PATTERN,
        on_invalid=lambda: WrongModelVersionError(str(version.id), VAR_TOTAL_MODEL_CODE),
    )
    return int(declared)


def register_var_parametric_total_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    appraisal_days: int,
    horizon_days: int = VAR_HORIZON_DAYS,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the TOTAL-parametric-VaR ``model`` + a ``model_version`` for this
    ``(code_version, confidence_level, horizon_days, appraisal_days)`` identity (PA-4, OD-PA-4-B/D).
    Mirrors :func:`register_var_model`'s declared-parameter machinery (the same confidence
    vocabulary + z table + horizon gate) under a DIFFERENT model CODE, PLUS the declared
    ``appraisal_days`` (the appraisal cadence, calendar days, >= 1) driving the residual frequency
    conversion. The total run is dispatched through the SAME binder."""
    if int(appraisal_days) < 1:
        raise ValueError("appraisal_days must be >= 1 (the calendar-day appraisal cadence)")
    text = str(confidence_level).strip()
    if not _CONFIDENCE_PATTERN.fullmatch(text) or len(text) > 6:
        raise ValueError(
            f"confidence_level {confidence_level!r} is not in the v1 vocabulary "
            f"{sorted(VAR_Z_SCORES)} (a new level is a new declared registration)"
        )
    confidence_key = f"{Decimal(text).quantize(Decimal('0.0001')):f}"
    z_text = VAR_Z_SCORES.get(confidence_key)
    if z_text is None:
        raise ValueError(
            f"confidence_level {confidence_level} not in the v1 vocabulary {sorted(VAR_Z_SCORES)}"
        )
    if int(horizon_days) != VAR_HORIZON_DAYS:
        raise ValueError(
            f"horizon_days must be {VAR_HORIZON_DAYS} in v1 (sqrt(h) scaling is a recorded seam)"
        )
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=VAR_TOTAL_MODEL_CODE,
        name=VAR_TOTAL_MODEL_NAME,
        model_type=VAR_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Total parametric VaR = governed factor variance + the idiosyncratic residual variance "
            "of the proxied instruments' cited proxy-weight estimates (PA-4, ENT-027)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=VAR_TOTAL_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=VAR_TOTAL_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=VAR_TOTAL_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *VAR_TOTAL_ASSUMPTIONS_BASE,
                f"{CONFIDENCE_ASSUMPTION_PREFIX}{confidence_key}",
                f"{HORIZON_ASSUMPTION_PREFIX}{int(horizon_days)}",
                f"{Z_ASSUMPTION_PREFIX}{z_text}",
                f"{APPRAISAL_DAYS_ASSUMPTION_PREFIX}{int(appraisal_days)}",
            ),
            limitations=VAR_TOTAL_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_var_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or f"{declared.confidence_level:f}" != confidence_key
        or declared.horizon_days != int(horizon_days)
        or declared_appraisal_days(session, version) != int(appraisal_days)
    ):
        raise ModelVersionConflictError(
            VAR_TOTAL_MODEL_CODE,
            VAR_TOTAL_VERSION_LABEL,
            f"{code_version} (confidence_level={confidence_key}, horizon_days={horizon_days}, "
            f"appraisal_days={appraisal_days})",
        )
    return version
