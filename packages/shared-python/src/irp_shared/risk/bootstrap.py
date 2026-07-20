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
    "validation_status UNVALIDATED — recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    "CURRENCY family only in v1 (the allocation model's own deliberate scope); multi-family "
    "dimensions ship via the loadings family (captured/promoted loadings), not this "
    "model.",
    "mark_currency approximates denomination currency; an instrument marked in a non-native "
    "currency would misallocate (the instrument-denomination dimension is deferred).",
    "Factor returns are NOT consumed (their first consumer is P3-4 covariance / regression v2).",
    "No residual/UNMAPPED bucket — an unmapped atom fails the whole run closed.",
    "validation_status UNVALIDATED — recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    "CURRENCY-family proxy factors only (this model's own deliberate gate; PA-0 OD-H - the "
    "platform-wide claim ended at the multi-family widening: the loadings family admits "
    "the widened set).",
    "The unallocated residual of a partial proxy is unmodeled - a residual/idiosyncratic "
    "variance term is a v2 candidate alongside the regression weights.",
    "Proxied rows break the contributions-sum-to-total identity BY DESIGN (sum = sum(w) * atom); "
    "the REQ-MKT-003 exactness holds per-UNPROXIED-atom only (test-asserted in both regimes).",
    "ACTIVE RISK does not consume proxy runs in v1: its weight normalization divides by the "
    "summed pinned rows, which equals the net book value ONLY under a partitioning run - a "
    "partial proxy would silently redistribute the unmodeled residual (fail-closed gate at "
    "run_active_risk; a proxy-aware denominator is the recorded v2). VaR/HS-VaR/scenario "
    "consume absolute exposures and are unaffected.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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


# --- FL-1: the third factor-exposure family — fractional multi-factor loadings (OD-FL-1-D) -------
FACTOR_EXPOSURE_LOADINGS_MODEL_CODE = "risk.factor_exposure.loadings"
FACTOR_EXPOSURE_LOADINGS_MODEL_NAME = (
    "Factor-exposure loadings projection (fractional, non-partitioning; the multi-family substrate)"
)
FACTOR_EXPOSURE_LOADINGS_VERSION_LABEL = "v1"
FACTOR_EXPOSURE_LOADINGS_METHODOLOGY_REF = (
    "05_analytics_methodologies/factor_exposure_loadings_v1.md"
)

#: The declared methodology choices (mirrored into model_assumption rows; OD-FL-1-D).
FACTOR_EXPOSURE_LOADINGS_ASSUMPTIONS: tuple[str, ...] = (
    "Fractional multi-factor projection: each pinned atom carries >= 1 (instrument, factor, "
    "loading) row from the widened proxy_mapping (ENT-019); exposure_amount = quantize_HALF_UP("
    "loading * atom.exposure_amount, 6) per (instrument, factor), signed. Multiple factors per "
    "instrument; the loading is fractional and signed (a regression beta, not a partition weight).",
    "The loadings are a PROJECTION, not a partition: Sum(exposure) = Sum_atoms(atom * Sum_f "
    "loading) != Sum(atoms) in general. The generalization of the proxy projection to the full "
    "admitted-family set (LOADING_FACTOR_FAMILIES; OTHER/unknown refused).",
    "The coverage gate (OD-FL-1-D): a pinned atom with ZERO loading rows REFUSES the run closed - "
    "no indicator fallback (unlike the proxy family), no silent zero (a dropped atom would "
    "under-count downstream VaR). Every pinned loading factor MUST be in the run's pinned factor "
    "list (the PA-2 unpinned-factor guard, carried).",
    "Loadings source: the widened ENT-019 proxy_mapping (originally private-asset-only; "
    "private_instrument_id is a recorded misnomer for public rows - it is a pin-serializer key, "
    "renaming it would false-drift every historical pin). REGRESSION-estimated betas from the "
    "PA-3 desmoothed (alpha=1 identity for public marks) return series flow through the SAME "
    "promote step; vendor-supplied betas are the recorded v2.",
)

#: The recorded scope-outs (mirrored into model_limitation rows; decision record Part 3).
FACTOR_EXPOSURE_LOADINGS_LIMITATIONS: tuple[str, ...] = (
    "The loaded-atom residual (1 - Sum_f loading) is honestly UNMODELED - Sum(exposure) != "
    "Sum(atoms) in general; REQ-MKT-003's epsilon=0 acceptance holds for the allocation family "
    "only (unchanged since PA-2). An UNLOADED atom is refused, not imputed.",
    "Price-return betas (no dividend capture) + short-window single-name regression noise - the "
    "standard errors and R^2 stay first-class on the estimate rows; any loadings-family "
    "validation must cite them.",
    "ACTIVE RISK does not consume the loadings family (its allocation-only model-code whitelist "
    "refuses it automatically) - a loadings-aware active-risk denominator is the recorded v2, "
    "open since PA-2. SCENARIO refuses a non-CURRENCY loadings run at its run-binder gate "
    "(scenario_service.py; shock semantics per FRTB class are methodology work, not a gate flip).",
    "The FRTB family names (RATES/CREDIT_SPREAD/COMMODITY + the CURRENCY=FX, MARKET=equity "
    "aliases) are VOCABULARY - they classify factors and confer NO FRTB capital-calculation "
    "semantics (liquidity horizons, partial-ES aggregation).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation exception, "
    "MG-1) refuses every new bind at the shared seam.",
)


def register_factor_exposure_loadings_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the LOADINGS factor-exposure ``model`` + a ``model_version`` for this
    ``code_version`` (FL-1, OD-FL-1-D — the ``register_factor_exposure_proxy_model`` shape). The
    returned ``model_version.id`` is what a loadings factor-exposure run binds; the SHARED
    ``run_factor_exposure`` binder dispatches on the bound model's code via the registry map."""
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
        name=FACTOR_EXPOSURE_LOADINGS_MODEL_NAME,
        model_type=FACTOR_EXPOSURE_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Fractional multi-factor loadings projection: pinned (instrument, factor, loading) "
            "rows from the widened proxy_mapping (ENT-019) project each atom onto the admitted "
            "factor families; the multi-family substrate (FL-1, ENT-028 family). The proxy "
            "projection generalized - fractional, signed, non-partitioning."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=FACTOR_EXPOSURE_LOADINGS_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=FACTOR_EXPOSURE_LOADINGS_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=FACTOR_EXPOSURE_LOADINGS_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=FACTOR_EXPOSURE_LOADINGS_ASSUMPTIONS,
            limitations=FACTOR_EXPOSURE_LOADINGS_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
            FACTOR_EXPOSURE_LOADINGS_VERSION_LABEL,
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
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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

#: The confidence vocabulary -> the REGISTERED z constants (OD-P3-5-D): recorded to 12dp,
#: dual-sourced from published standard-normal tables and test-verified via the stdlib
#: ``math.erf`` round-trip Phi(z) = (1+erf(z/sqrt(2)))/2 == alpha to 1e-12 AND an independent
#: bisection inversion (2026-07-07). NO runtime inverse-CDF exists (capability-is-not-evidence).
#:
#: ONE table, shared by FOUR families (risk.var.parametric, .parametric_total v1+v2,
#: .historical, and ES-1's .parametric_es/.parametric_es_total). ES-1 (OQ-ES-1-4, sub-fork (i))
#: ADDED 0.9750 - the only externally-anchored ES confidence (BCBS d457 MAR33.3). Ratified with
#: its disclosed cost: 97.5% became registrable on the historical/total families too, which ES-1
#: did not analyze (the HS adequacy floor computes N >= 41 there - verified, not exercised).
VAR_Z_SCORES: dict[str, str] = {
    "0.9500": "1.644853626951",
    "0.9750": "1.959963984540",
    "0.9900": "2.326347874041",
}

#: The confidence vocabulary -> the REGISTERED ES multipliers k_c (OD-ES-1-A/B). The exact
#: structural twin of VAR_Z_SCORES: a per-confidence declared constant, so NO runtime normal
#: function of ANY kind exists - not the inverse CDF (already barred above) and not the forward
#: PDF phi. The tail arithmetic lives HERE, in a registered constant, never in code.
#:
#: CONVENTION (pinned explicitly - the recorded P3-5 seam ``ES = sigma*phi(z)/(1-alpha)`` never
#: defined ``alpha`` and the literature is genuinely split on that symbol: Acerbi-Tasche use the
#: TAIL probability, Gneiting uses the CONFIDENCE level):
#:
#:     k_c := phi(Phi^-1(c)) / (1 - c),  c = the CONFIDENCE level (0.9750 -> tail mass 0.0250)
#:     ES_c = k_c * sigma_p,  losses loss-POSITIVE, zero-mean (mu_L = 0)
#:
#: consistent with the shipped VaR_c = z_c * sigma_p. ES is the alpha-TAIL-MEAN INTEGRAL, never
#: E[L | L > VaR] (that is TCE, which is NOT coherent for discontinuous distributions; they
#: coincide only in the continuous/normal case - Acerbi-Tasche Cor. 5.3(i)). A later
#: ES-over-historical-simulation leg MUST inherit the tail-mean estimator (Acerbi-Tasche Prop.
#: 4.1: a FLOOR count plus a FRACTIONAL boundary weight, NOT the mean of the worst ceil(n*a)
#: losses - that quantity IS the TCE forbidden above).
#:
#: Verified at 12dp by THREE independent routes (2026-07-15): Decimal bisection on Phi at prec
#: 50-80 with pi via Machin; stdlib NormalDist.inv_cdf (Wichura AS241, a different algorithm);
#: and composite-Simpson integration of the tail mean using NO closed form. All agree to the last
#: digit. Test-pinned BYTE-EXACT with z re-derived in-test (test_es.py) - a tolerance-based check
#: against a pre-rounded z CANNOT pin the 12th dp (its noise floor exceeds the quantum).
#: Correctly ROUNDED, not truncated: k_0.9900 = 2.665214220345804... -> ...346.
VAR_ES_MULTIPLIERS: dict[str, str] = {
    "0.9500": "2.062712807507",
    "0.9750": "2.337802792201",
    "0.9900": "2.665214220346",
}
#: The v1 horizon (the covariance substrate is DAILY/unannualized; sqrt(h) is a recorded seam).
VAR_HORIZON_DAYS = 1

#: The declared methodology choices EXCLUDING the per-registration declarations (appended per
#: call; OD-P3-5-D/E/F/G).
VAR_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Zero-mean delta-normal parametric VaR under the linear factor model dV = SUM_i(x_i * r_i): "
    "sigma_p = sqrt(x' * Sigma * x); VaR_alpha = z_alpha * sigma_p (1-day; no sqrt(h) scaling).",
    "Inputs: the per-factor exposure totals of ONE COMPLETED factor-exposure run of ANY "
    "registered family (base currency, signed) x the sample covariance matrix of ONE "
    "COMPLETED covariance run "
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
    "SPECIFIC/IDIOSYNCRATIC RISK = 0: the linear factor model carries NO residual variance "
    "term regardless of the bound exposure family (allocation, proxy, or multi-family loadings "
    "- HG-1 corrected the pre-widening CURRENCY-only framing) - portfolio risk outside the factor "
    "covariance is invisible to this number.",
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
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    The vocabulary: ``confidence_level`` in {0.95, 0.975, 0.99} (the registered z table; 0.975
    admitted by ES-1/OQ-ES-1-4 — the table is SHARED across the VaR/ES families);
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
    "SPECIFIC/IDIOSYNCRATIC RISK = 0: x spans registered factors only, whichever exposure "
    "family produced it (HG-1 corrected the pre-widening attribution) - identical to the "
    "parametric method.",
    "Equal weighting reacts SLOWLY to volatility shifts; filtered (FHS) and time-weighted "
    "(BRW) variants outperform in the cited literature and are recorded v2 model versions "
    "requiring a declared volatility model (decision record Part 2.1).",
    "The estimate cannot exceed the worst scenario IN the window - regime changes outside the "
    "pinned window are invisible (window-as-declared-identity; the OD-VHS-E adequacy floor is "
    "a statistical minimum, not a sufficiency guarantee).",
    "1-day horizon only; overlapping/multi-day windows and sqrt(h) scaling are recorded seams.",
    "ES (the FRTB-preferred tail measure) is REALIZED as the sibling risk.var.historical_es "
    "family (ES-HS-1) - the empirical tail mean over this family's own scenario distribution; "
    "Kupiec/traffic-light backtesting of THIS family is LIVE (BT-1 admits VAR_HISTORICAL); "
    "Monte-Carlo remains gated on a seeded simulator (the OD-VHS-G register).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    the exact condition the floor's rationale refuses) at every integral boundary, incl. EVERY
    vocabulary confidence (three since ES-1 widened the shared table; the floor is computed, not
    tabulated, so 0.975 -> 41 needs no change here). Guaranteeing ``k >= 2`` requires
    ``N·(1-c) > 1`` strictly — the floor is the smallest such N (21 at 0.95; 101 at 0.99)."""
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
    version_label: str = VAR_HS_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the historical-simulation VaR model family (VAR-HS-1, OD-VHS-B):
    identity = (code_version, confidence_level, horizon_days, window_observations,
    quantile_convention). Same-label different-declaration -> :class:`ModelVersionConflictError`;
    a non-REGISTERED same-label twin -> :class:`WrongModelVersionError` (the P3-C1 contract).
    The window floor (OD-VHS-E): N >= ceil(1/(1-c)) - below it the order statistic is the
    sample minimum and the estimate is statistically meaningless. ``version_label`` is
    caller-suppliable (BT-3 — the MF-1 ``v1-alpha1``/HG-1 house precedent; default unchanged,
    every pre-BT-3 call site byte-equivalent) so a second declared confidence registers as a
    SIBLING version instead of a same-label 409."""
    if not version_label or not str(version_label).strip():
        raise ValueError("version_label must be a non-empty string")
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
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
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
            str(version_label),
            f"{code_version} (confidence_level={confidence_key}, horizon_days="
            f"{horizon_days}, window_observations={n})",
        )
    return version


# --- ES-HS-1: the empirical historical-simulation ES model family (OD-ES-HS-1-B) ---

ES_HS_MODEL_CODE = "risk.var.historical_es"
ES_HS_MODEL_NAME = "Historical-simulation Expected Shortfall (empirical tail mean, 1-day)"
ES_HS_MODEL_TYPE = "VAR"
ES_HS_VERSION_LABEL = "v1"
ES_HS_METHODOLOGY_REF = "05_analytics_methodologies/var_historical_es_v1.md"

#: The v1 estimator convention - REGISTRATION-DECLARED (OD-ES-HS-1-B, the quantile_convention
#: precedent): the Acerbi-Tasche Prop 4.1 discrete alpha-tail-mean (floor count + FRACTIONAL
#: boundary weight, / n*a). A different estimator (interpolated, simple-average/TCE,
#: kernel-smoothed) is a NEW declared version, never silent drift. There is NO registered
#: constant in this family (no es_multiplier, no z) - the tail mean is empirical.
ESTIMATOR_ASSUMPTION_PREFIX = "estimator_convention="
ES_HS_ESTIMATOR_CONVENTION = "TAIL_MEAN_ACERBI_TASCHE_P41"

ES_HS_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "The Acerbi-Tasche Prop 4.1 discrete alpha-tail-mean: with a = 1-c, m = floor(n*a), "
    "w = n*a - m over the ascending-sorted scenario P&Ls, ES = -(SUM_(i<=m) pnl_(i) + "
    "w*pnl_(m+1)) / (n*a) - the exact empirical integral, NEVER the mean of the worst "
    "ceil(n*a) losses (that quantity is the TCE the ES-1 convention forbids; it never "
    "exceeds the true ES and STRICTLY understates it at every fractional n*a with an "
    "untied (m+1)-boundary - equality exactly at fully-tied tails).",
    "The SAME scenario substrate as the historical-simulation VaR: plain EQUAL-WEIGHT "
    "scenarios from the linear factor model dV_t = SUM_i x_i * r_(t,i) over the "
    "FACTOR_EXPOSURE run's per-factor totals; the pinned input is byte-identical to the "
    "sibling VaR family's (one snapshot can feed both).",
    "The scenario P&L distribution is the EMPIRICAL one - no distributional assumption; "
    "ES >= VaR holds at raw precision on the same window by construction (equality at tied "
    "tail scenarios); the value may be negative when the whole tail is gains - reported "
    "honestly, never clamped.",
    "es_value (carried in var_value, discriminated by metric_type) is quantized HALF_UP to 6 "
    "decimal places ONCE; the number is FULLY reproducible from the pinned snapshot content "
    "plus the declared parameters alone - no registered constant participates (contrast: the "
    "parametric ES reproduces only THROUGH its registered multiplier).",
)

ES_HS_LIMITATIONS: tuple[str, ...] = (
    "SPECIFIC/IDIOSYNCRATIC RISK = 0: x spans registered factors only, whichever exposure "
    "family produced it - the tail mean inherits the factor substrate's blindness identically "
    "to every sibling number.",
    "At the adequacy floor most of the estimate's WEIGHT sits on the single worst scenario "
    "(21/0.95: n*a = 1.05 - about 95% of the weight on pnl_(1)); the effective tail mass is "
    "n*(1-c) scenario-equivalents, the floor is a statistical MINIMUM, and window size is the "
    "lever that buys tail resolution.",
    "The estimate cannot exceed the worst scenario IN the window - the tail mean lives "
    "ENTIRELY in the window's extreme tail, so regime changes outside the pinned window are "
    "invisible with sharper teeth than the VaR leg (window-as-declared-identity).",
    "Equal weighting reacts SLOWLY to volatility shifts - inherited from the scenario "
    "substrate; filtered/time-weighted variants are recorded v2 versions of the SIBLING VaR "
    "family and would flow through here via the shared substrate, each a new declared "
    "version.",
    # BT-3 reword (NEW registrations only; the fresh-seed key-match re-runs against this
    # constant, so the "DELIBERATELY not backtestable v1" key substring is PRESERVED — the
    # planning verifier's BT3-V-2 invariant; a conformance test pins it).
    "DELIBERATELY not backtestable v1 by Kupiec/Basel: the exception count is a quantile test, "
    "statistically meaningless over a tail-mean series - the Kupiec binder refuses this metric "
    "with the recorded scope-out, never an unknown-vocabulary miss. The genuine Acerbi-Szekely "
    "ES backtest SHIPS at risk.es_backtest (BT-3): pair the ES-HS run with its sibling VaR-HS "
    "run by shared input_snapshot_id.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
)


@dataclass(frozen=True)
class EsHsParameters:
    """The version's declared ES-HS parameters, parsed from its ``model_assumption`` rows."""

    confidence_level: Decimal
    horizon_days: int
    window_observations: int
    estimator_convention: str


def declared_es_hs_parameters(session: Session, version: ModelVersion) -> EsHsParameters:
    """Parse the declared confidence/horizon/window/estimator-convention (the OD-ES-HS-1-B
    identity: exactly ONE strictly-well-formed declaration of EACH). Malformed/absent/
    ambiguous -> the fail-closed :class:`WrongModelVersionError` (the generic endpoint can
    mint anything). The strict window floor is IDENTITY here exactly as on the VaR leg (the
    same n*(1-c) > 1 bound - m >= 1 keeps the fractional-weight estimator out of its
    degenerate single-scenario shape)."""
    texts = load_assumption_texts(session, version)
    confidence_text = sole_declared(texts, CONFIDENCE_ASSUMPTION_PREFIX)
    horizon_text = sole_declared(texts, HORIZON_ASSUMPTION_PREFIX)
    window_text = sole_declared(texts, WINDOW_ASSUMPTION_PREFIX)
    estimator_text = sole_declared(texts, ESTIMATOR_ASSUMPTION_PREFIX)
    if (
        confidence_text is None
        or horizon_text is None
        or window_text is None
        or estimator_text is None
        or not _CONFIDENCE_PATTERN.fullmatch(confidence_text)
        or confidence_text not in VAR_Z_SCORES  # the shared v1 confidence vocabulary
        or horizon_text != str(VAR_HORIZON_DAYS)
        or _DIGITS_PATTERN.fullmatch(window_text) is None
        or estimator_text != ES_HS_ESTIMATOR_CONVENTION
        or int(window_text) < _hs_window_floor(confidence_text)
    ):
        raise WrongModelVersionError(str(version.id), ES_HS_MODEL_CODE)
    return EsHsParameters(
        confidence_level=Decimal(confidence_text),
        horizon_days=int(horizon_text),
        window_observations=int(window_text),
        estimator_convention=estimator_text,
    )


def register_historical_var_es_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    window_observations: int,
    horizon_days: int = VAR_HORIZON_DAYS,
    version_label: str = ES_HS_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the historical-simulation ES model family (ES-HS-1, OD-B):
    identity = (code_version, confidence_level, horizon_days, window_observations,
    estimator_convention). Same-label different-declaration ->
    :class:`ModelVersionConflictError`; a non-REGISTERED same-label twin ->
    :class:`WrongModelVersionError` (the P3-C1 contract). The window floor is the VaR leg's
    strict bound (n*(1-c) > 1), shared arithmetic, registrar-and-bind enforced."""
    if not version_label or not str(version_label).strip():
        raise ValueError("version_label must be a non-empty string")
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

    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=ES_HS_MODEL_CODE,
        name=ES_HS_MODEL_NAME,
        model_type=ES_HS_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Empirical historical-simulation Expected Shortfall (the Acerbi-Tasche Prop 4.1 "
            "alpha-tail-mean) over governed factor exposures x pinned captured factor-return "
            "windows - the same scenario substrate as risk.var.historical (ES-HS-1, ENT-027)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=ES_HS_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *ES_HS_ASSUMPTIONS_BASE,
                f"{CONFIDENCE_ASSUMPTION_PREFIX}{confidence_key}",
                f"{HORIZON_ASSUMPTION_PREFIX}{int(horizon_days)}",
                f"{WINDOW_ASSUMPTION_PREFIX}{n}",
                f"{ESTIMATOR_ASSUMPTION_PREFIX}{ES_HS_ESTIMATOR_CONVENTION}",
            ),
            limitations=ES_HS_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_es_hs_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or f"{declared.confidence_level:f}" != confidence_key
        or declared.horizon_days != int(horizon_days)
        or declared.window_observations != n
    ):
        raise ModelVersionConflictError(
            ES_HS_MODEL_CODE,
            str(version_label),
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
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    "Kupiec POF only: no Christoffersen independence/conditional-coverage (a named BT-3 candidate "
    "- NOT the ratified BT-2, which is the total-series admit), no Basel multiplier arithmetic "
    "(the zone is the recorded output), no p-values (critical-value decisions at the declared "
    "alpha).",
    "TOTAL-SERIES READ VALIDITY (BT-2, the honest-pairing doctrine): VAR_PARAMETRIC_TOTAL is "
    "backtestable here, but every VaR is a 1-DAY forecast while an appraisal-marked book's "
    "private leg only moves on mark dates. The daily pairing is therefore biased TWO WAYS BY "
    "CONSTRUCTION: exceptions are mechanically SUPPRESSED between marks (the private leg's "
    "realized P&L is flat, so it can never breach) and CLUSTERED on mark dates (a whole appraisal "
    "period's move lands against a 1-day allowance). BCBS 22 states the traffic light's PRIMARY "
    "assumption is that each day's test is independent of the others - an assumption this series "
    "violates by construction. (Basel's own answer to stale/unobservable inputs is FRTB's "
    "RFET/NMRF: exclude them from the daily VaR+backtest perimeter and capitalise separately - "
    "not backtest them daily.)",
    "READ RULE (BT-2): on a book with appraisal-marked positions the unconditional KUPIEC_LR / "
    "BASEL_ZONE verdict is NOT valid evidence of adequacy in EITHER direction (a clean record "
    "proves nothing; an excess count is confounded by mark-date clustering). Validity degrades "
    "with the private-leg share - a liquid-dominated book with a small proxied sleeve keeps a "
    "near-valid read. The DATED per-pair EXCEPTION_INDICATOR rows are the honest evidence "
    "surface: mark-date clustering is visible in them. The statistically-honest configurations - "
    "appraisal-frequency pairing (needs multi-day-horizon VaR) and a Christoffersen independence "
    "leg - are named BT-3 candidates, not silently absent.",
    "Small-N honesty: the POF test is asymptotic; KUPIEC_LR is emitted for any N >= 1 with n_pairs "
    "recorded on every row so a reader can weigh it; the Basel zone refuses to exist off-domain.",
    "Calendar-day horizon interpretation (consistent with PM-1's calendar-day Dietz weighting); "
    "trading-day calendar validation is the same deferred data-quality slice P3-8 recorded.",
    "One backtest run = ONE VaR method (uniform metric_type); cross-method comparison is two runs "
    "side by side - no joint test.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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


# --- BT-3: the Christoffersen v2 convention on risk.var_backtest (OD-BT-3-E) ---

#: The declared independence-leg convention (BT-3): ABSENT => the v1 Kupiec-only identity (the
#: grandfather — every shipped v1 parses byte-identically); present => the Markov leg. The parse
#: is the COUNTING tri-state (0 / 1 / >1), NEVER bare ``sole_declared`` — its absent/ambiguous
#: conflation would silently fail an ambiguous v2 OPEN to v1 behavior (the RS-1 A1 / DS-2 trap,
#: named at the shipped documentation site).
INDEPENDENCE_ASSUMPTION_PREFIX = "independence="
VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION = "CHRISTOFFERSEN_MARKOV"
VAR_BACKTEST_V2_VERSION_LABEL = "v2-christoffersen"

#: The v2 assumption rows APPENDED to the base + alpha (the Markov leg's declared methodology).
VAR_BACKTEST_V2_ASSUMPTIONS_EXTRA: tuple[str, ...] = (
    "Christoffersen (1998) Markov independence leg: the exception series' adjacent-day 2x2 "
    "transition counts n_ij (FROM i TO j); LR_IND = 2[ln L(first-order Markov MLE) - ln L(one "
    "common violation probability)], asymptotically chi-square(1), decided against the SAME "
    "fixed df=1 criticals as the POF; LR_CC = LR_UC + LR_IND (the standard decomposition; "
    "LR_UC over the full N pairs, LR_IND over the N-1 transitions - the applied convention, "
    "stated), chi-square(2), decided against fixed df=2 criticals (-2 ln(alpha), closed form).",
    "DEGENERATE-TABLE HONESTY: a series with no transition leaving state 1 (zero exceptions, or "
    "a single trailing exception) or none leaving state 0 has NO defined LR_IND - no row is "
    "emitted and no LR_CC composes (the exception-count row makes the absence legible); never "
    "coerced to 0.",
)

#: The v2 limitation rows — the v1 set with the two Christoffersen-candidate clauses DISCHARGED
#: (rows 3 and 5 of the v1 constant go FALSE on a version that emits LR_IND/LR_CC — the planning
#: verifier's enumeration) + the Markov-scope rows. NEW registrations only; the shipped v1
#: constant stays byte-identical.
VAR_BACKTEST_V2_LIMITATIONS: tuple[str, ...] = (
    VAR_BACKTEST_LIMITATIONS[0],  # captured-holdings P&L bias — carries verbatim
    VAR_BACKTEST_LIMITATIONS[1],  # ACTUAL P&L only — carries verbatim
    "Kupiec POF + the Christoffersen (1998) Markov independence/conditional-coverage leg "
    "(SHIPPED at this version, BT-3); no Basel multiplier arithmetic (the zone is the recorded "
    "output), no p-values (critical-value decisions at the declared alpha).",
    VAR_BACKTEST_LIMITATIONS[3],  # the BT-2 total-series read validity doctrine — carries
    "READ RULE (BT-2): on a book with appraisal-marked positions the unconditional KUPIEC_LR / "
    "BASEL_ZONE verdict is NOT valid evidence of adequacy in EITHER direction (a clean record "
    "proves nothing; an excess count is confounded by mark-date clustering). Validity degrades "
    "with the private-leg share - a liquid-dominated book with a small proxied sleeve keeps a "
    "near-valid read. The DATED per-pair EXCEPTION_INDICATOR rows are the honest evidence "
    "surface: mark-date clustering is visible in them - and the Christoffersen leg SHIPPED at "
    "this version scores exactly that clustering (LR_IND). Appraisal-frequency pairing (needs "
    "multi-day-horizon VaR) remains the named open candidate, not silently absent.",
    "MARKOV SCOPE: the independence leg tests FIRST-ORDER dependence only (yesterday's "
    "exception) - longer-lag dependence is invisible to it (Campbell 2005 notes the class); "
    "the Christoffersen-Pelletier (2004) duration test is the named variant, out of scope.",
    VAR_BACKTEST_LIMITATIONS[5],  # small-N honesty — carries verbatim
    VAR_BACKTEST_LIMITATIONS[6],  # calendar-day horizon — carries verbatim
    VAR_BACKTEST_LIMITATIONS[7],  # one method per run — carries verbatim
    VAR_BACKTEST_LIMITATIONS[8],  # validation_status — carries verbatim
)


def declared_var_backtest_independence(session: Session, version: ModelVersion) -> str | None:
    """Parse the version's declared independence-leg convention (BT-3, OD-BT-3-E). ZERO
    ``independence=`` rows => ``None`` (the v1 Kupiec-only grandfather, byte-preserved); MORE
    THAN ONE => fail-closed :class:`WrongModelVersionError` (ambiguity never collapses into the
    grandfather); exactly one must be the recognized Markov literal."""
    texts = load_assumption_texts(session, version)
    rows = [t for t in texts if t.startswith(INDEPENDENCE_ASSUMPTION_PREFIX)]
    if not rows:
        return None
    if len(rows) > 1:
        raise WrongModelVersionError(str(version.id), VAR_BACKTEST_MODEL_CODE)
    convention = rows[0][len(INDEPENDENCE_ASSUMPTION_PREFIX) :]
    if convention != VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION:
        raise WrongModelVersionError(str(version.id), VAR_BACKTEST_MODEL_CODE)
    return convention


def register_var_backtest_christoffersen_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    alpha: str | Decimal = "0.05",
    version_label: str = VAR_BACKTEST_V2_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the Christoffersen v2 of ``risk.var_backtest`` (BT-3, OD-BT-3-E):
    the SAME model code, a NEW version whose registrar-stamped identity adds
    ``independence=CHRISTOFFERSEN_MARKOV`` to the declared Kupiec alpha. The v1 registrar and
    every shipped v1 stay byte-preserved (the absent-convention grandfather). Same-label
    different-declaration => :class:`ModelVersionConflictError`; a squatted non-REGISTERED twin
    => :class:`WrongModelVersionError`."""
    from irp_shared.risk.var_backtest_kernel import CHI2_1DF_CRITICALS

    if not version_label or not str(version_label).strip():
        raise ValueError("version_label must be a non-empty string")
    text = str(alpha).strip()
    if not _ALPHA_PATTERN.fullmatch(text) or Decimal(text) not in CHI2_1DF_CRITICALS:
        raise ValueError(
            f"alpha {alpha!r} is not in the v1 critical-value vocabulary "
            f"{sorted(str(a) for a in CHI2_1DF_CRITICALS)} (a new level is a new declared "
            f"registration, never a runtime quantile)"
        )
    alpha_key = f"{Decimal(text).normalize():f}"
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
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=VAR_BACKTEST_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *VAR_BACKTEST_ASSUMPTIONS_BASE,
                *VAR_BACKTEST_V2_ASSUMPTIONS_EXTRA,
                f"{ALPHA_ASSUMPTION_PREFIX}{alpha_key}",
                f"{INDEPENDENCE_ASSUMPTION_PREFIX}{VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION}",
            ),
            limitations=VAR_BACKTEST_V2_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_var_backtest_alpha(session, version)
    convention = declared_var_backtest_independence(session, version)
    if (
        version.code_version != str(code_version)
        or f"{declared.normalize():f}" != alpha_key
        or convention != VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION
    ):
        raise ModelVersionConflictError(
            VAR_BACKTEST_MODEL_CODE,
            str(version_label),
            f"{code_version} (alpha={alpha_key}, independence="
            f"{VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION})",
        )
    return version


# --- BT-3: the Acerbi-Szekely ES-backtest model family (OD-BT-3-A/B/D) ---

ES_BACKTEST_MODEL_CODE = "risk.es_backtest"
ES_BACKTEST_MODEL_NAME = "ES backtesting (Acerbi-Szekely Z statistics, v1)"
ES_BACKTEST_MODEL_TYPE = "ES_BACKTEST"
ES_BACKTEST_VERSION_LABEL = "v1"
ES_BACKTEST_METHODOLOGY_REF = "05_analytics_methodologies/es_backtest_v1.md"

#: The declared verdict significance (OD-BT-3-B: part of the version identity; the vocabulary is
#: EXACTLY the fixed Z2 critical set — extending it, or any other (alpha, T) cell, is a NEW
#: declared registration under a governed derivation record, never a runtime simulation).
SIGNIFICANCE_ASSUMPTION_PREFIX = "significance="
_SIGNIFICANCE_PATTERN = re.compile(r"0\.[0-9]{1,4}")

#: The registrar-stamped verdict DOMAIN (OD-BT-3-B, the adversarial verifier's HIGH): the AS
#: criticals are alpha-, T-, AND df-dependent — valid only at (paired confidence 0.9750,
#: n_pairs 250, near-normal tails). Stamped as identity so drift = a new version.
VERDICT_CONFIDENCE_ASSUMPTION_PREFIX = "verdict_confidence="
VERDICT_PAIRS_ASSUMPTION_PREFIX = "verdict_pairs="
ES_BACKTEST_VERDICT_CONFIDENCE = Decimal("0.9750")
ES_BACKTEST_VERDICT_PAIRS = 250

ES_BACKTEST_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Acerbi-Szekely (2014) ES outcomes analysis over an aligned paired series (X_t, VaR_t, "
    "ES_t): I_t = 1 iff X_t + VaR_t < 0 (STRICT - the shipped BT-1 exception convention); "
    "Z2 = (1/(T*a)) * SUM X_t*I_t/ES_t + 1 (unconditional, a = 1 - the paired family's declared "
    "confidence); Z1 = (1/N_T) * SUM X_t*I_t/ES_t + 1 (conditional; UNDEFINED at N_T = 0 - no "
    "row, never 0). The '+1' sits OUTSIDE the sum (settled by the null-expectation identity "
    "E[X | X < -VaR] = -ES; three-route verified at planning).",
    "Pairing: sibling (VaR-HS, ES-HS) runs resolved per as-of by IDENTICAL input_snapshot_id "
    "and the SAME declared confidence; the VaR leg supplies VaR_t and the as-of (window_end), "
    "the ES leg ES_t; realized P&L_t = end_mv - begin_mv - net_external_flow per DIETZ "
    "sub-period of ONE COMPLETED portfolio-return run, aligned by the BT-1 all-or-nothing "
    "calendar-day convention (ANY unpaired forecast refuses the whole run).",
    "Verdict (one-sided LEFT tail): REJECT iff Z2 < the FIXED registered critical for the "
    "declared significance - EMITTED ONLY inside the criticals' derivation domain (paired "
    "confidence 0.9750 AND n_pairs = 250; the Basel-zone domain-gate precedent); off-domain "
    "runs persist the Z evidence rows + ES_PAIR_COUNT and NO verdict (the absence is "
    "mechanically derivable from the persisted rows). NO simulation at runtime, ever.",
    "Computed in Decimal at 50-digit context; the Z statistics quantize_HALF_UP internally to "
    "12 decimal places, then quantize_HALF_UP to the Numeric(28,6) result scale - the "
    "REJECT/FAIL_TO_REJECT decision is taken on that STORED 6dp value against the registered "
    "critical, so the persisted row always reproduces its own decision.",
)

ES_BACKTEST_LIMITATIONS: tuple[str, ...] = (
    "DOMAIN-BOUND VERDICT: the registered Z2 criticals (-0.70 at 5%, -1.8 at 0.01%) are "
    "Acerbi-Szekely's simulated left-tail quantiles at tail a = 0.025 (confidence 0.9750), "
    "T = 250 pairs, near-normal tails - they are alpha-, T-, AND df-DEPENDENT (executed at "
    "planning: ~-1.56 at a=0.005/T=250; ~-3.68 at a=0.025/T=10; -0.82/-4.4 at Student-t3). "
    "Off-domain pairings get Z evidence rows and NO verdict; a per-(alpha, T) critical table "
    "is a named v2 under a governed offline derivation record (the TR-09 determinism bar).",
    "ONE-SIDED: the AS statistics flag UNDERSTATEMENT only - over-conservatism is invisible "
    "to them (the deliberate break with the two-sided Kupiec POF, which remains the coverage "
    "test). A zero-breach full-domain series is itself evidence of over-conservatism this "
    "test cannot score; Z1 is additionally UNDEFINED there (no row, never 0).",
    "Z1 IS EVIDENCE, NEVER A VERDICT: the Test-1 critical values are distribution-UNSTABLE "
    "(the recorded AS weakness) - Z1 rows persist for the reader; only Z2 carries the "
    "domain-gated decision.",
    "CAPTURED-HOLDINGS P&L BIAS (the PM-1 first-class limitation, carried verbatim from BT-1): "
    "uncaptured income understates realized losses' offsets and realized P&L alike - a "
    "backtest over a leaky book is ANTI-CONSERVATIVE. Mitigation stays operational (capture "
    "the cash), never imputation.",
    "ACTUAL (flow-adjusted) P&L only - the Basel hypothetical/clean-P&L leg needs "
    "static-portfolio repricing the platform does not yet have; DEFERRED and recorded.",
    "One backtest run = ONE paired (VaR-HS, ES-HS) family at ONE declared confidence, "
    "model-version-UNIFORM across pairs on BOTH legs (a series mixing code_versions of one "
    "declared identity refuses); cross-method comparison is two runs side by side.",
    "Small-T honesty: the Z statistics are emitted for any T >= 1 with ES_PAIR_COUNT recorded "
    "on the summary surface so a reader can weigh them; the verdict refuses to exist "
    "off-domain (see DOMAIN-BOUND VERDICT).",
    "FRTB posture (the honest framing): desk backtesting under FRTB remains VaR-based while "
    "97.5% ES is the capital measure - this test trails the ACADEMIC frontier (AS 2014; "
    "Kratz-Lok-McNeil), not a Basel floor; 0.9750 is the externally-anchored verdict "
    "confidence (MAR33.3).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
)


@dataclass(frozen=True)
class EsBacktestParameters:
    """The parsed ES-backtest declared identity (OD-BT-3-B/D)."""

    significance: Decimal
    verdict_confidence: Decimal
    verdict_pairs: int


def declared_es_backtest_parameters(
    session: Session, version: ModelVersion
) -> EsBacktestParameters:
    """Parse the version's declared ES-backtest identity: EXACTLY ONE well-formed
    ``significance=`` inside the fixed Z2 critical set, plus the registrar-stamped verdict
    domain (``verdict_confidence=0.9750``, ``verdict_pairs=250``) verbatim. Anything malformed,
    absent, ambiguous, off-vocabulary, or off-domain is NOT this identity — fail-closed
    :class:`WrongModelVersionError` (the generic endpoint can mint anything)."""
    from irp_shared.risk.es_backtest_kernel import Z2_CRITICALS

    texts = load_assumption_texts(session, version)

    def _fail() -> WrongModelVersionError:
        return WrongModelVersionError(str(version.id), ES_BACKTEST_MODEL_CODE)

    raw = require_declared(
        texts, SIGNIFICANCE_ASSUMPTION_PREFIX, pattern=_SIGNIFICANCE_PATTERN, on_invalid=_fail
    )
    significance = Decimal(raw)
    if significance not in Z2_CRITICALS:
        raise _fail()
    conf_raw = require_declared(
        texts, VERDICT_CONFIDENCE_ASSUMPTION_PREFIX, pattern=_SIGNIFICANCE_PATTERN, on_invalid=_fail
    )
    if Decimal(conf_raw) != ES_BACKTEST_VERDICT_CONFIDENCE:
        raise _fail()
    pairs_raw = require_declared(
        texts,
        VERDICT_PAIRS_ASSUMPTION_PREFIX,
        pattern=re.compile(r"[1-9][0-9]{0,3}"),
        on_invalid=_fail,
    )
    if int(pairs_raw) != ES_BACKTEST_VERDICT_PAIRS:
        raise _fail()
    return EsBacktestParameters(
        significance=significance,
        verdict_confidence=ES_BACKTEST_VERDICT_CONFIDENCE,
        verdict_pairs=ES_BACKTEST_VERDICT_PAIRS,
    )


def register_es_backtest_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    significance: str | Decimal = "0.05",
    version_label: str = ES_BACKTEST_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the AS ES-backtest ``model`` + a ``model_version`` for this
    ``(code_version, significance)`` identity (BT-3, OD-BT-3-B/D — the SIXTEENTH governed
    number's model). The verdict domain (0.9750, 250) is REGISTRAR-STAMPED, never
    caller-suppliable; the significance vocabulary is the fixed Z2 critical set {0.05, 0.0001}.
    Same-label different-declaration => :class:`ModelVersionConflictError`; a squatted
    non-REGISTERED twin => :class:`WrongModelVersionError`."""
    from irp_shared.risk.es_backtest_kernel import Z2_CRITICALS

    if not version_label or not str(version_label).strip():
        raise ValueError("version_label must be a non-empty string")
    text = str(significance).strip()
    if not _SIGNIFICANCE_PATTERN.fullmatch(text) or Decimal(text) not in Z2_CRITICALS:
        raise ValueError(
            f"significance {significance!r} is not in the v1 critical-value vocabulary "
            f"{sorted(str(s) for s in Z2_CRITICALS)} (a new cell is a new declared "
            f"registration under a governed derivation record, never a runtime simulation)"
        )
    significance_key = f"{Decimal(text).normalize():f}"
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=ES_BACKTEST_MODEL_CODE,
        name=ES_BACKTEST_MODEL_NAME,
        model_type=ES_BACKTEST_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "ES backtesting - the Acerbi-Szekely Z1/Z2 statistics over sibling "
            "(VaR-HS, ES-HS) forecast pairs sharing input_snapshot_id, against realized "
            "flow-adjusted P&L; domain-gated Z2 verdict (BT-3, ENT-055)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=ES_BACKTEST_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *ES_BACKTEST_ASSUMPTIONS_BASE,
                f"{SIGNIFICANCE_ASSUMPTION_PREFIX}{significance_key}",
                f"{VERDICT_CONFIDENCE_ASSUMPTION_PREFIX}0.9750",
                f"{VERDICT_PAIRS_ASSUMPTION_PREFIX}250",
            ),
            limitations=ES_BACKTEST_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_es_backtest_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or f"{declared.significance.normalize():f}" != significance_key
    ):
        raise ModelVersionConflictError(
            ES_BACKTEST_MODEL_CODE,
            str(version_label),
            f"{code_version} (significance={significance_key})",
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
    "CURRENCY factor family only (this model's own v1 scope, enforced at the shock binder; "
    "per-class shock semantics for the wider families are recorded methodology work). RETURN "
    "shock type only. Computed in Decimal; base currency = the exposure run's base.",
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
    "validation_status UNVALIDATED — recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    "Candidate factors span the admitted loading families (the multi-family widening relaxed "
    "PA-2's CURRENCY-only boundary; OTHER/unknown families still fail the run closed). "
    "Single-currency series only "
    "(no FX translation).",
    "Unconstrained OLS can produce weights an analyst should reject - which is WHY promotion is "
    "human-mediated. Constrained (Sharpe 1992) and summed-lag (Dimson 1979 / Asness-Krail-Liew "
    "2001) variants are recorded v2s.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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


# --- RS-1: residual-estimator conventions on the proxy-weight family (OD-RS-1-A/B/C) ---
#
# Both are new declared VERSIONS of the SAME risk.proxy_weight.regression code (the estimate is an
# INPUT to total VaR, not a governed output — the version label carries the estimator). The raw v1
# is
# GRANDFATHERED: an ABSENT estimator_convention means the implicit RAW (the DELIBERATE inverse of
# the
# es_hs required-literal template — declared_proxy_weight_parameters below).
# ESTIMATOR_ASSUMPTION_PREFIX
# is the shared "estimator_convention=" prefix declared in the ES-HS-1 block above.

#: The implicit v1 convention (never stamped on a raw version — absent => this).
PROXY_WEIGHT_RAW_CONVENTION = "RAW"
#: RS-1 OD-RS-1-A: the Axioma/RiskMetrics EWMA residual-variance convention (a regression version —
#: it still runs OLS; only the residual variance is decayed). Carries a declared decay_lambda.
PROXY_WEIGHT_EWMA_CONVENTION = "EWMA_RISKMETRICS"
# : RS-1 OD-RS-1-B: the empirical-Bayes cross-sectional shrinkage convention (a TRANSFORM version —
# it
#: runs no OLS; run_residual_shrinkage blends a cohort of raw estimates). Method-as-identity: NO
#: declared numeric intensity (the per-instrument w_i are computed + pin-reproduced).
PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION = "SHRINKAGE_CROSS_SECTIONAL_EB"

#: The conventions the OLS ESTIMATE run accepts (run_proxy_weight_estimate); the shrinkage TRANSFORM
# : run (run_residual_shrinkage) accepts the EB convention. A version bound to the wrong operation
# is a
#: fail-closed WrongModelVersionError (the registry-map dispatch, OD-RS-1-C).
PROXY_WEIGHT_REGRESSION_CONVENTIONS = frozenset(
    {PROXY_WEIGHT_RAW_CONVENTION, PROXY_WEIGHT_EWMA_CONVENTION}
)

DECAY_LAMBDA_ASSUMPTION_PREFIX = "decay_lambda="
#: 0.<1..6 digits> — the EWMA decay in (0, 1); the confidence/alpha decimal-literal shape. The gate
#: additionally parses to Decimal and enforces 0 < lambda < 1 (excludes 0.000000).
_DECAY_LAMBDA_PATTERN = re.compile(r"0\.[0-9]{1,6}")

PROXY_WEIGHT_EWMA_VERSION_LABEL = "v2-ewma"
PROXY_WEIGHT_SHRINKAGE_EB_VERSION_LABEL = "v2-shrinkage-eb"
#: The RS-1 residual-estimator methodology referent (both new conventions share it).
PROXY_WEIGHT_RESIDUAL_METHODOLOGY_REF = "05_analytics_methodologies/residual_estimation_v1.md"

#: OD-RS-1-A dossier — the EWMA convention's declared methodology (min_observations appended at
#: registration, exactly as the raw family).
PROXY_WEIGHT_EWMA_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "The idiosyncratic residual variance is an EXPONENTIALLY-WEIGHTED mean of squared OLS "
    "residuals: "
    "sigma_e^2 = SUM_i w_i e_i^2, w_i = (1-lambda) lambda^(n-1-i)/(1-lambda^n) over the residual "
    "series oldest-first, so the MOST RECENT appraisal period carries the largest weight (the "
    "Axioma EWMA of specific returns; RiskMetrics Technical Document 4th ed).",
    "The OLS factor loadings, their standard errors, and R^2 are UNCHANGED from the raw v1 - the "
    "EWMA "
    "convention re-weights ONLY the specific-risk variance (the classical residual variance is "
    "retained for the coefficient inference; the s2 decoupling).",
    "NO n-k degrees-of-freedom correction: the EWMA normalizes by SUM w_i = 1 (the RiskMetrics "
    "biased "
    "form); the effective sample size is 1/SUM w_i^2 (< n) and the residual mean is taken as zero.",
    "decay_lambda is a DECLARED model-identity parameter (0 < lambda < 1) stamped at registration "
    "and "
    "enforced at bind - RiskMetrics' 0.94-daily/0.97-monthly are NOT transferable to "
    "appraisal-period "
    "marks, so a different lambda is a new declared version; the RMSE-fitted lambda is a recorded "
    "v2.",
)

#: OD-RS-1-A dossier limitations (EWMA-specific + the raw family's standing rows).
PROXY_WEIGHT_EWMA_LIMITATIONS: tuple[str, ...] = (
    "EFFECTIVE SAMPLE SIZE 1/SUM w_i^2 < n: EWMA reacts faster to a specific-risk shift but on "
    "FEWER "
    "effective observations - on the SHORT appraisal series the decayed estimate is noisier at the "
    "tail end; window length and lambda are the levers.",
    "The DECLARED lambda is a fixed model-identity constant, NOT fit from data (the RMSE-fitted "
    "lambda "
    "is a recorded v2 - on a ~12-mark per-period residual series a fitted lambda is unstable).",
    "Estimates are MODEL OUTPUT, snapshot/run/model-bound - NEVER auto-written into proxy_mapping; "
    "promotion is a deliberate second capture step citing the estimation run (OD-PA-3-E).",
    "Candidate factors span the admitted loading families; single-currency series only (no FX "
    "translation); unconstrained OLS can produce weights an analyst should reject (WHY promotion "
    "is "
    "human-mediated).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome "
    "(VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation exception, MG-1) "
    "refuses "
    "every new bind at the shared seam.",
)

#: OD-RS-1-B dossier — the empirical-Bayes shrinkage convention's declared methodology.
PROXY_WEIGHT_SHRINKAGE_EB_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Empirical-Bayes cross-sectional shrinkage of each member's raw specific variance s_i^2 toward "
    "the cohort pool sigma_pool^2 = mean(s_j^2): s_i^2(shrunk) = w_i sigma_pool^2 + (1-w_i) s_i^2 "
    "(the Efron-Morris method-of-moments; the Barra USE4 specific-risk shrinkage family - NOT "
    "Ledoit-Wolf, which shrinks correlations and leaves variances unshrunk).",
    "The per-instrument intensity is DATA-DRIVEN, not declared: w_i = v_i/(v_i+tau^2), v_i = "
    "2 s_i^4/(n_i-k_i) the Gaussian sampling variance of a variance estimate, tau^2 = max(0, "
    "S2_cross - v_bar) the method-of-moments prior dispersion - a noisier/shorter-series estimate "
    "shrinks MORE, a widely-dispersed cohort shrinks LESS (heterogeneous by construction).",
    "Method-as-identity: the declared identity is the METHOD, carrying NO numeric intensity; every "
    "w_i is COMPUTED and fully reproducible from the pinned per-member (s_i^2, residual df) alone "
    "- "
    "the fit is not minted as a separate governed number.",
    "A TRANSFORM over promoted raw estimates (it runs no OLS); the shrunk residual stdev feeds the "
    "same total-VaR residual leg as the raw estimate, byte-unchanged downstream.",
)

#: OD-RS-1-B dossier limitations.
PROXY_WEIGHT_SHRINKAGE_EB_LIMITATIONS: tuple[str, ...] = (
    "COMPARABLE-COHORT rule: the cross-sectional pool assumes a comparable-risk group - pooling "
    "across asset classes (a bond shrunk toward an equity pool) is a mis-application the declaring "
    "analyst owns; the kernel pools whatever cohort it is handed.",
    "MIN-COHORT fail-closed: fewer than 3 DISTINCT comparable instruments refuses - the declared "
    "prudence/identifiability floor (the method-of-moments tau^2 rests on N-1 df of "
    "cross-sectional dispersion, a single df at N=2 being unusable; Stein's p>=3 dimension is "
    "the motivating ANALOGY, not a transferred guarantee) - never an arbitrary intensity.",
    "SHRINKAGE MAY REORDER same-side variances: the intensity grows with s^4, so two members on "
    "the SAME side of the pool can cross after shrinkage (inherent to heterogeneous-intensity "
    "empirical Bayes; every shrunk value stays within its own raw-to-pool interval) - the "
    "cross-member RANKING of shrunk specific risks is not order-preserving.",
    "The GAUSSIAN sampling variance v_i = 2 s_i^4/(n_i-k_i) assumes approximately-normal residuals "
    "- "
    "heavy tails understate v_i and under-shrink; the plug-in s_i^4 adds noise on short series.",
    "The EQUAL-WEIGHTED pool is a simplification of USE4's cap-weighted target (a recorded v2); "
    "the "
    "shrinkage target is the cross-sectional MEAN specific variance, not a structural model.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome "
    "(VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation exception, MG-1) "
    "refuses "
    "every new bind at the shared seam.",
)


@dataclass(frozen=True)
class ProxyWeightParameters:
    """The version's declared proxy-weight estimator identity (RS-1, OD-RS-1-C).
    ``estimator_convention`` is OPTIONAL with a RAW default (the grandfather — absent => RAW, the
    deliberate inverse of the es_hs required-literal template). ``min_observations`` is present for
    the RAW/EWMA regression conventions and ``None`` for the EB shrinkage transform;
    ``decay_lambda`` is present only for EWMA."""

    estimator_convention: str
    min_observations: int | None
    decay_lambda: Decimal | None


def declared_proxy_weight_parameters(
    session: Session, version: ModelVersion
) -> ProxyWeightParameters:
    """Parse the version's declared proxy-weight estimator identity (RS-1, OD-RS-1-C). ABSENT
    ``estimator_convention`` (zero rows) => the implicit ``RAW`` v1 (the grandfather); a present
    convention must be SOLE and one of the three recognized literals with its required companions
    well-formed and NO inapplicable stray literal. AMBIGUOUS (>1 convention row — the adversarial
    review's catch: ambiguity must never collapse into the grandfather), malformed, or unknown ->
    the fail-closed :class:`WrongModelVersionError` (the generic endpoint can mint anything)."""
    texts = load_assumption_texts(session, version)
    convention_rows = [t for t in texts if t.startswith(ESTIMATOR_ASSUMPTION_PREFIX)]

    def _fail() -> WrongModelVersionError:
        return WrongModelVersionError(str(version.id), PROXY_WEIGHT_MODEL_CODE)

    if len(convention_rows) > 1:
        # AMBIGUOUS is refused, never grandfathered — only a genuinely ABSENT declaration is RAW.
        raise _fail()
    has_lambda = any(t.startswith(DECAY_LAMBDA_ASSUMPTION_PREFIX) for t in texts)
    if not convention_rows:
        if has_lambda:  # a stray decay_lambda on an implicit-RAW version is a lying identity
            raise _fail()
        min_obs = require_declared(
            texts, MIN_OBSERVATIONS_ASSUMPTION_PREFIX, pattern=_DIGITS_PATTERN, on_invalid=_fail
        )
        return ProxyWeightParameters(PROXY_WEIGHT_RAW_CONVENTION, int(min_obs), None)
    convention = convention_rows[0][len(ESTIMATOR_ASSUMPTION_PREFIX) :]
    if convention == PROXY_WEIGHT_RAW_CONVENTION:
        if has_lambda:
            raise _fail()
        min_obs = require_declared(
            texts, MIN_OBSERVATIONS_ASSUMPTION_PREFIX, pattern=_DIGITS_PATTERN, on_invalid=_fail
        )
        return ProxyWeightParameters(PROXY_WEIGHT_RAW_CONVENTION, int(min_obs), None)
    if convention == PROXY_WEIGHT_EWMA_CONVENTION:
        min_obs = require_declared(
            texts, MIN_OBSERVATIONS_ASSUMPTION_PREFIX, pattern=_DIGITS_PATTERN, on_invalid=_fail
        )
        lam_text = require_declared(
            texts, DECAY_LAMBDA_ASSUMPTION_PREFIX, pattern=_DECAY_LAMBDA_PATTERN, on_invalid=_fail
        )
        lam = Decimal(lam_text)
        if not (Decimal(0) < lam < Decimal(1)):
            raise _fail()
        return ProxyWeightParameters(PROXY_WEIGHT_EWMA_CONVENTION, int(min_obs), lam)
    if convention == PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION:
        # Method-as-identity: a stray numeric literal on an EB version is a lying identity.
        if has_lambda or any(t.startswith(MIN_OBSERVATIONS_ASSUMPTION_PREFIX) for t in texts):
            raise _fail()
        return ProxyWeightParameters(PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION, None, None)
    raise _fail()


def register_proxy_weight_ewma_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    decay_lambda: str | Decimal,
    min_observations: int,
    version_label: str = PROXY_WEIGHT_EWMA_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) an EWMA residual-variance version of the proxy-weight family (RS-1,
    OD-RS-1-A). Identity = (code_version, min_observations, estimator_convention=EWMA_RISKMETRICS,
    decay_lambda). The convention + lambda are REGISTRAR-STAMPED (not caller-suppliable from the
    generic endpoint); a same-label re-register with a different declaration raises
    :class:`ModelVersionConflictError`."""
    lam_text = str(decay_lambda).strip()
    if not _DECAY_LAMBDA_PATTERN.fullmatch(lam_text) or not (
        Decimal(0) < Decimal(lam_text) < Decimal(1)
    ):
        raise ValueError(
            f"decay_lambda {decay_lambda!r} must be 0.<1..6 digits> with 0 < lambda < 1"
        )
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
        version_label=version_label,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=version_label,
            actor_id=actor_id,
            methodology_ref=PROXY_WEIGHT_RESIDUAL_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *PROXY_WEIGHT_EWMA_ASSUMPTIONS_BASE,
                f"{MIN_OBSERVATIONS_ASSUMPTION_PREFIX}{int(min_observations)}",
                f"{ESTIMATOR_ASSUMPTION_PREFIX}{PROXY_WEIGHT_EWMA_CONVENTION}",
                f"{DECAY_LAMBDA_ASSUMPTION_PREFIX}{lam_text}",
            ),
            limitations=PROXY_WEIGHT_EWMA_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_proxy_weight_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or declared.estimator_convention != PROXY_WEIGHT_EWMA_CONVENTION
        or declared.min_observations != int(min_observations)
        or declared.decay_lambda != Decimal(lam_text)
    ):
        raise ModelVersionConflictError(
            PROXY_WEIGHT_MODEL_CODE,
            version_label,
            f"{code_version} (min_observations={min_observations}, decay_lambda={lam_text})",
        )
    return version


def register_proxy_weight_shrinkage_eb_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    version_label: str = PROXY_WEIGHT_SHRINKAGE_EB_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) an empirical-Bayes shrinkage version of the proxy-weight family
    (RS-1, OD-RS-1-B). Identity = (code_version, estimator_convention=SHRINKAGE_CROSS_SECTIONAL_EB)
    — method-as-identity, NO numeric intensity. A same-label re-register with a different
    declaration raises :class:`ModelVersionConflictError`."""
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
        version_label=version_label,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=version_label,
            actor_id=actor_id,
            methodology_ref=PROXY_WEIGHT_RESIDUAL_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *PROXY_WEIGHT_SHRINKAGE_EB_ASSUMPTIONS_BASE,
                f"{ESTIMATOR_ASSUMPTION_PREFIX}{PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION}",
            ),
            limitations=PROXY_WEIGHT_SHRINKAGE_EB_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_proxy_weight_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or declared.estimator_convention != PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION
    ):
        raise ModelVersionConflictError(
            PROXY_WEIGHT_MODEL_CODE,
            version_label,
            f"{code_version} (estimator_convention={PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION})",
        )
    return version


# --- PA-4: total parametric VaR = factor + idiosyncratic residual variance (OD-PA-4-B) ---

#: The per-tenant inventory identity of the total-parametric-VaR model (PA-4). A DIFFERENT model
#: CODE from the plain parametric family (so the plain family is byte-untouched), but the SAME
#: declared-parameter machinery (confidence/horizon/z) — dispatched through the SAME binder.
VAR_TOTAL_MODEL_CODE = "risk.var.parametric_total"
VAR_TOTAL_MODEL_NAME = "Total parametric VaR (factor + idiosyncratic residual, 1-day)"
#: BT-2 (OD-BT-2-C): v1 -> **v2**, the label bump forced by the immutable-version convention — v2
#: adds the DECLARED ``max_estimate_age_days`` staleness policy (the 5th identity parameter). An
#: existing v1 registration is IMMUTABLE and cannot absorb the declaration, so v1 rows keep binding
#: UNGATED (the recorded grandfather); the registrar mints only v2 from here. The governance sunset
#: lever for a lingering v1 is VW-1: a 2L validator REJECTs the v1 model_version and every new v1
#: bind refuses at the shared ``assert_model_version_of`` seam.
VAR_TOTAL_VERSION_LABEL = "v2"
VAR_TOTAL_METHODOLOGY_REF = "05_analytics_methodologies/var_parametric_total_v2.md"

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
#: BT-2 (OD-BT-2-C): the DECLARED staleness policy — the maximum age, in CALENDAR days, of a cited
#: PA-3 residual estimate at the run's own economic as-of. Age = the pinned covariance
#: ``window_end`` MINUS the cited estimation run's PROXY_WEIGHT_INPUT snapshot
#: ``as_of_valuation_date`` (the regression span end — what data the sigma_e actually saw). The
#: v2 identity's 5th declared parameter; ABSENT (a v1 row) = ungated, the recorded grandfather.
MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX = "max_estimate_age_days="
#: The ratified declared-value pattern: 1..99999 calendar days, no leading zeros (the identity is
#: an exact string — an unbounded/zero-padded value is not a policy).
_MAX_ESTIMATE_AGE_PATTERN = re.compile(r"[1-9][0-9]{0,4}")

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
    "Unproxied and MANUAL-method instruments carry ZERO idiosyncratic variance whichever "
    "exposure family binds (no estimation evidence - the P3-3 limitation stands for them, "
    "restated).",
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
    "cross-correlation; residual shrinkage (Barra USE4 empirical-Bayes) + EWMA weighting (Axioma/"
    "RiskMetrics) are REALIZED as declared risk.proxy_weight.regression estimator conventions "
    "(RS-1) - a total-VaR run consumes such an estimate through its promoted citation (the "
    "estimator version is bound by the cited ESTIMATE run, never by the total run itself).",
    "The residual is hostage to the PA-3 estimate quality (short appraisal series => noisy "
    "sigma_e; the estimate's per-coefficient std errors stay visible on the pinned estimate).",
    "Non-proxied and MANUAL-method instruments carry ZERO idiosyncratic risk under ANY bound "
    "exposure family (the specific-risk=0 posture propagates for them; HG-1 corrected the "
    "allocation-v1 attribution).",
    "Flat 252/365 trading-day ratio over the MEAN period (calendar-aware per-period counts a v2); "
    "1-day horizon only; historical-simulation + ES total analogues are recorded v2s.",
    "No FX conversion - a proxied instrument's estimate series_currency must equal the book's "
    "base_currency; a mismatch refuses rather than converting.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
)


def declared_appraisal_days(session: Session, version: ModelVersion) -> int:
    """Parse the total-VaR version's declared appraisal-period length (calendar days) from its
    ``model_assumption`` rows (the OD-PA-4-D identity: exactly ONE ``appraisal_days=N``, N >= 1).
    Malformed/absent/ambiguous/sub-floor -> the fail-closed :class:`WrongModelVersionError`.
    The floor is IDENTITY, not registrar courtesy (the ``_hs_window_floor`` precedent): a
    generically-minted version (POST /models can stamp any assumptions) declaring
    ``appraisal_days=0`` must refuse at BIND time, not surface later as a committed FAILED run
    from the kernel's non-positive-period gate (2026-07 review, numeric + adversarial finders
    independently)."""
    declared = require_declared(
        load_assumption_texts(session, version),
        APPRAISAL_DAYS_ASSUMPTION_PREFIX,
        pattern=_DIGITS_PATTERN,
        on_invalid=lambda: WrongModelVersionError(str(version.id), VAR_TOTAL_MODEL_CODE),
    )
    if int(declared) < 1:
        raise WrongModelVersionError(str(version.id), VAR_TOTAL_MODEL_CODE)
    return int(declared)


def declared_max_estimate_age_days(session: Session, version: ModelVersion) -> int | None:
    """Parse the total-VaR version's DECLARED staleness policy (BT-2, OD-BT-2-C), or ``None`` when
    the version declares none — the ONE deliberately-optional declared parameter in the family.

    Tri-state, and the asymmetry is the whole point:
    - **ABSENT** (zero matches) -> ``None`` = UNGATED. This is the recorded v1 grandfather: a
      pre-BT-2 ``risk.var.parametric_total`` v1 row is IMMUTABLE and cannot absorb the declaration,
      so it must keep binding exactly as it did (a grandfathered path must not gain a NEW refusal).
    - **MALFORMED or DUPLICATED** -> fail-closed :class:`WrongModelVersionError` (422). NOT
      ``sole_declared``, whose None-on-ambiguous would fail OPEN here — a version declaring the
      policy TWICE (mintable via the generic POST /models path under the same permission, the P3-4
      lesson) must never silently degrade to ungated. Absent and ambiguous are DIFFERENT answers.
    - **Well-formed** -> the int, ``>= 1`` (a zero/negative max-age is not a policy).
    """
    texts = load_assumption_texts(session, version)
    found = [
        t[len(MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX) :]
        for t in texts
        if t.startswith(MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX)
    ]
    if not found:
        return None  # ungated — the v1 grandfather
    if len(found) > 1:  # ambiguous is a REFUSAL here, never a silent ungate
        raise WrongModelVersionError(str(version.id), VAR_TOTAL_MODEL_CODE)
    # The RATIFIED pattern (plan Step 3): 1-99999, no leading zeros, bounded — NOT the shared
    # unbounded _DIGITS_PATTERN (which admits "007" and 20-digit values that are ungated in
    # practice). A declared policy is an exact identity string (review fold).
    if not _MAX_ESTIMATE_AGE_PATTERN.fullmatch(found[0]):
        raise WrongModelVersionError(str(version.id), VAR_TOTAL_MODEL_CODE)
    return int(found[0])


def register_var_parametric_total_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    appraisal_days: int,
    max_estimate_age_days: int,
    horizon_days: int = VAR_HORIZON_DAYS,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the TOTAL-parametric-VaR ``model`` + a ``model_version`` for this
    ``(code_version, confidence_level, horizon_days, appraisal_days)`` identity (PA-4, OD-PA-4-B/D).
    Mirrors :func:`register_var_model`'s declared-parameter machinery (the same confidence
    vocabulary + z table + horizon gate) under a DIFFERENT model CODE, PLUS the declared
    ``appraisal_days`` (the appraisal cadence, calendar days, >= 1) driving the residual frequency
    conversion, PLUS the BT-2 ``max_estimate_age_days`` staleness policy. The total run is
    dispatched through the SAME binder.

    **BT-2 (OD-BT-2-C):** the label is now ``v2`` — ``max_estimate_age_days`` is a REQUIRED
    declared identity parameter (no default: a staleness policy is consciously chosen, the
    OD-P3-5-D philosophy), and an immutable v1 row cannot absorb it. v1 registrations survive and
    keep binding ungated (recorded grandfather); this registrar mints only v2."""
    if int(appraisal_days) < 1:
        raise ValueError("appraisal_days must be >= 1 (the calendar-day appraisal cadence)")
    if int(max_estimate_age_days) < 1:
        raise ValueError(
            "max_estimate_age_days must be >= 1 (the calendar-day staleness policy for a cited "
            "residual estimate)"
        )
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
                f"{MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX}{int(max_estimate_age_days)}",
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
        # A resolved v2 row MUST carry the policy (absent -> None -> conflict, never a silent
        # ungate for a version this registrar claims to have minted).
        or declared_max_estimate_age_days(session, version) != int(max_estimate_age_days)
    ):
        raise ModelVersionConflictError(
            VAR_TOTAL_MODEL_CODE,
            VAR_TOTAL_VERSION_LABEL,
            f"{code_version} (confidence_level={confidence_key}, horizon_days={horizon_days}, "
            f"appraisal_days={appraisal_days}, max_estimate_age_days={max_estimate_age_days})",
        )
    return version


# --------------------------------------------------------------------------------------------
# ES-1 — the parametric Expected Shortfall families (OD-ES-1-C/D)
# --------------------------------------------------------------------------------------------
#: The PLAIN ES family: ES_c = k_c * sigma_p over the SAME factor sigma the plain parametric VaR
#: computes. A NEW model CODE dispatched through the SAME binder (the PA-4 shape), NOT an extra row
#: on the existing VaR run: the snapshot builder pins EVERY var_result row of a run with no
#: metric_type filter and the backtest binder then refuses a snapshot whose pinned rows mix
#: methods, so an extra ES row would break every BT-1/BT-2 backtest over a parametric run AND
#: silently change a shipped v1 model's output (OD-ES-1-C — the alternative is DISQUALIFIED, not
#: dispreferred). Also honours P3-5's own ratified words: each method is its own registered family.
ES_MODEL_CODE = "risk.var.parametric_es"
ES_MODEL_NAME = "Parametric Expected Shortfall (zero-mean delta-normal, 1-day)"
ES_VERSION_LABEL = "v1"
ES_METHODOLOGY_REF = "05_analytics_methodologies/var_parametric_es_v1.md"

#: The TOTAL ES family: ES_c = k_c * sigma_total (PA-4's factor+idiosyncratic sigma, incl. BT-2's
#: staleness gate). Ships with the plain leg because the mandate is "BOTH sigma and sigma_total"
#: and the arithmetic is one multiplier over a sigma the platform already computes.
ES_TOTAL_MODEL_CODE = "risk.var.parametric_es_total"
ES_TOTAL_MODEL_NAME = "Total parametric Expected Shortfall (factor + idiosyncratic residual, 1-day)"
ES_TOTAL_VERSION_LABEL = "v1"

#: The DECLARED ES multiplier k_c (model identity). Declared like confidence/horizon/z so the row
#: is auditable, and IDENTITY-CHECKED against VAR_ES_MULTIPLIERS[c] at bind: a generically-minted
#: version (POST /models can stamp any assumptions — the P3-4 lesson) CANNOT declare a k that does
#: not match its own declared c. The k is never recomputed at runtime; it is looked up and verified.
ES_MULTIPLIER_ASSUMPTION_PREFIX = "es_multiplier="

#: ES-family declared choices EXCLUDING the per-registration confidence/horizon/z/k.
ES_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Zero-mean parametric Expected Shortfall under the SAME linear factor model as the plain "
    "parametric VaR family: ES_c = k_c * sigma_p, k_c := phi(Phi^-1(c)) / (1 - c), with c the "
    "CONFIDENCE level (0.9750 -> tail mass 0.0250), losses loss-POSITIVE and zero-mean (mu_L = 0) "
    "- consistent with the shipped VaR_c = z_c * sigma_p. The Landsman-Valdez (2003) elliptical "
    "closed form at mu = 0. ES is the alpha-TAIL-MEAN INTEGRAL, never E[L | L > VaR] (that is "
    "TCE, NOT coherent for discontinuous distributions; they coincide only under continuity - "
    "Acerbi-Tasche Cor. 5.3(i)).",
    "k_c is a REGISTERED constant from the SAME enumerated confidence vocabulary as z_alpha - no "
    "runtime normal function of ANY kind is computed: not the inverse CDF (barred since P3-5) and "
    "not the forward PDF phi. The tail arithmetic lives in the registered constant, under model "
    "governance, not in code. The declared es_multiplier is identity-checked against the "
    "registered table at bind.",
    "Inputs: IDENTICAL to the plain parametric VaR family (the per-factor exposure totals of "
    "ONE COMPLETED factor-exposure run of ANY registered family x the sample covariance of "
    "ONE COMPLETED covariance run) "
    "- ES multiplies the SAME sigma_p through the SAME adjudication, snapshot bind and provenance "
    "re-resolution. Every input limitation of that family applies verbatim.",
    "Computed in Decimal at 50-digit context precision; ES quantizes HALF_UP to 6 decimal places "
    "(the Numeric(28,6) base-currency scale), exactly as sigma/VaR.",
)

#: ES-family recorded scope-outs. NOTE the coherence + backtest rows: both are written to the
#: research corrections (OD-ES-1-F, Part 2), NOT to the tempting-but-false versions.
ES_LIMITATIONS: tuple[str, ...] = (
    "ES here is a fixed multiple of the SAME sigma_p as the parametric VaR family, so it inherits "
    "EVERY limitation of that number verbatim: SPECIFIC/IDIOSYNCRATIC RISK = 0 (the plain leg; the "
    "total ES family adds it), joint normality of factor returns, 1-day horizon only (no sqrt(h) "
    "scaling), the registered-factor universe of the bound exposure family, and the "
    "sample-covariance estimation error.",
    "ES's practical content here is TAIL SEVERITY (VaR is a cut-off and says nothing about "
    "magnitude beyond it) plus ROBUSTNESS: ES's coherence is UNCONDITIONAL (Acerbi-Tasche 2002 "
    "Prop. 3.1, any distribution), whereas this platform's parametric VaR is coherent only "
    "CONTINGENT on normality holding - under the model's OWN elliptical assumption VaR is ALREADY "
    "subadditive (Embrechts-McNeil-Straumann 2002), so ES does NOT fix a defect in today's "
    "arithmetic; it keeps the aggregation guarantee exactly when the model is WRONG. Do not read "
    "this number as 'VaR was incoherent'. (BCBS's own stated rationale for ES is tail capture "
    "only - d219; the coherence argument is academic, not regulatory.)",
    "NO ES backtest leg: ES rows are deliberately EXCLUDED from the backtestable metric vocabulary "
    "and a backtest over an ES run REFUSES. The reason is FRTB precedent + parametric redundancy, "
    "NOT non-elicitability: 'ES cannot be backtested' is FALSE (Acerbi-Szekely 2014 give practical "
    "ES backtests; Fissler-Ziegel 2016 show ES is jointly elicitable with VaR). FRTB backtests VaR "
    "and never ES (MAR32.4/32.5/32.18), and under this leg's own normality an ES backtest would be "
    "the VaR backtest with a rescaled threshold - no new information. A genuine ES backtest "
    "becomes meaningful for a non-elliptical ES-over-historical-simulation leg (a BT-3 candidate).",
    "ONE confidence level per registered version (the declared-parameter identity). ES over "
    "historical simulation and Monte Carlo remain later, separately declared families - each MUST "
    "inherit the alpha-tail-mean estimator: with a = 1-c the TAIL probability and L_(1) >= L_(2) "
    ">= ... the losses sorted worst-first, ES_a = ( SUM_{i<=floor(n*a)} L_(i) + (n*a - "
    "floor(n*a)) * L_(floor(n*a)+1) ) / (n*a) - a FLOOR count plus a FRACTIONAL weight on the "
    "boundary observation (Acerbi-Tasche 2002 Prop. 4.1). It is NOT the mean of the worst "
    "ceil(n*a) losses: that quantity IS the TCE this guard forbids (identical for untied "
    "samples) and it UNDERSTATES ES whenever n*a is not an integer - by ~14% at n=41, which is "
    "this platform's own historical-simulation adequacy floor at c=0.975. The two coincide only "
    "when n*a is an integer.",
    "An ES row does NOT reconcile against its own columns: var_value = k_c * sigma, but k_c is on "
    "no column - the row carries the arithmetically-UNUSED quantile z_score instead (the live "
    "ck_var_result_parametric_not_null CHECK forces it non-NULL). The multiplier lives only in "
    "this "
    "model_version's declared es_multiplier, so an ES row is reproducible THROUGH its bound "
    "model_version, never from the row alone. Key off metric_type: var_value holds the METRIC's "
    "number (the VAR_HISTORICAL precedent), and for an ES row that number is an ES, not a VaR.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
)

#: Total-ES-family scope-outs = the ES rows PLUS the total family's residual/smoothing doctrine.
ES_TOTAL_LIMITATIONS: tuple[str, ...] = (
    *ES_LIMITATIONS,
    "The residual leg is PA-4's verbatim: DIAGONAL residuals only (Sharpe 1963), hostage to the "
    "PA-3 estimate quality, ZERO idiosyncratic risk for non-proxied/MANUAL instruments, a flat "
    "252/365 trading-day ratio over the mean period, and no FX conversion. Residual shrinkage "
    "(Barra USE4) + EWMA weighting (Axioma) are now REALIZED as declared "
    "risk.proxy_weight.regression estimator conventions (RS-1); calendar-aware per-period "
    "trading-day counts remain a recorded v2.",
    "BT-2's smoothing doctrine carries over UNCHANGED - a sigma-multiple is exactly as honest as "
    "its sigma. On an appraisal-marked book the 1-day total sigma is biased two ways by "
    "construction (P&L suppressed between marks, clustered on mark dates), so the total ES "
    "inherits that bias directly. The DECLARED max_estimate_age_days staleness policy is REQUIRED "
    "on this family from birth (no grandfathered ungated version exists, unlike the total-VaR v1).",
)


def declared_es_multiplier(session: Session, version: ModelVersion, *, code: str) -> Decimal:
    """Parse + IDENTITY-CHECK the version's declared ES multiplier (OD-ES-1-B).

    Exactly ONE well-formed ``es_multiplier=K`` whose value equals ``VAR_ES_MULTIPLIERS[c]`` for
    the version's OWN declared confidence. The equality is the point: a generically-minted version
    (POST /models stamps arbitrary assumptions under the same permission — the P3-4 lesson) must
    not be able to pair a 0.99 confidence with a 0.95 multiplier and emit a governed number that
    is neither. Malformed/absent/ambiguous/mismatched -> fail-closed
    :class:`WrongModelVersionError` (422), never a bare parse crash.
    """
    declared = declared_var_parameters(session, version)  # also gates confidence/horizon/z
    texts = load_assumption_texts(session, version)
    found = [
        t[len(ES_MULTIPLIER_ASSUMPTION_PREFIX) :]
        for t in texts
        if t.startswith(ES_MULTIPLIER_ASSUMPTION_PREFIX)
    ]
    # Absent AND ambiguous both refuse: unlike BT-2's max_estimate_age_days (whose absent-branch is
    # the recorded v1 grandfather), an ES version has NO legitimate ungated form — the multiplier IS
    # the arithmetic. Never `sole_declared`, whose None-on-ambiguous would collapse the two.
    if len(found) != 1:
        raise WrongModelVersionError(str(version.id), code)
    confidence_key = f"{declared.confidence_level:f}"
    expected = VAR_ES_MULTIPLIERS.get(confidence_key)
    if expected is None or found[0] != expected:
        raise WrongModelVersionError(str(version.id), code)
    return Decimal(expected)


def register_var_parametric_es_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    horizon_days: int = VAR_HORIZON_DAYS,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the parametric-ES ``model`` + a ``model_version`` for this
    ``(code_version, confidence_level, horizon_days, z, es_multiplier)`` identity (ES-1, OD-ES-1-C).

    Mirrors :func:`register_var_model`'s declared-parameter machinery verbatim (the same shared
    confidence vocabulary + z table + horizon gate) under a DIFFERENT model CODE, PLUS the declared
    ``es_multiplier`` looked up from :data:`VAR_ES_MULTIPLIERS` and identity-checked at bind. The ES
    run is dispatched through the SAME binder as the plain/total VaR families.
    """
    text = str(confidence_level).strip()
    if not _CONFIDENCE_PATTERN.fullmatch(text) or len(text) > 6:
        raise ValueError(
            f"confidence_level {confidence_level!r} is not in the vocabulary "
            f"{sorted(VAR_ES_MULTIPLIERS)} (a new level is a new declared registration, "
            f"never a runtime quantile)"
        )
    confidence_key = f"{Decimal(text).quantize(Decimal('0.0001')):f}"
    z_text = VAR_Z_SCORES.get(confidence_key)
    k_text = VAR_ES_MULTIPLIERS.get(confidence_key)
    if z_text is None or k_text is None:
        raise ValueError(
            f"confidence_level {confidence_level} is not in the vocabulary "
            f"{sorted(VAR_ES_MULTIPLIERS)} (a new level is a new declared registration, "
            f"never a runtime quantile)"
        )
    if int(horizon_days) != VAR_HORIZON_DAYS:
        raise ValueError(
            f"horizon_days must be {VAR_HORIZON_DAYS} in v1 (sqrt(h) scaling is a recorded seam)"
        )
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=ES_MODEL_CODE,
        name=ES_MODEL_NAME,
        model_type=VAR_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Zero-mean parametric Expected Shortfall (the alpha-tail mean) over the SAME governed "
            "factor sigma as the parametric VaR family (ES-1, ENT-027)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=ES_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=ES_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=ES_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *ES_ASSUMPTIONS_BASE,
                f"{CONFIDENCE_ASSUMPTION_PREFIX}{confidence_key}",
                f"{HORIZON_ASSUMPTION_PREFIX}{int(horizon_days)}",
                f"{Z_ASSUMPTION_PREFIX}{z_text}",
                f"{ES_MULTIPLIER_ASSUMPTION_PREFIX}{k_text}",
            ),
            limitations=ES_LIMITATIONS,
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
        or declared_es_multiplier(session, version, code=ES_MODEL_CODE) != Decimal(k_text)
    ):
        raise ModelVersionConflictError(
            ES_MODEL_CODE,
            ES_VERSION_LABEL,
            f"{code_version} (confidence_level={confidence_key}, horizon_days={horizon_days}, "
            f"es_multiplier={k_text})",
        )
    return version


def register_var_parametric_es_total_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    confidence_level: str | Decimal,
    appraisal_days: int,
    max_estimate_age_days: int,
    horizon_days: int = VAR_HORIZON_DAYS,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the TOTAL-parametric-ES ``model`` + ``model_version`` for this
    ``(code_version, confidence_level, horizon_days, z, es_multiplier, appraisal_days,
    max_estimate_age_days)`` identity (ES-1, OD-ES-1-D).

    The ES multiplier over PA-4's ``sigma_total``, reusing the total family's residual machinery and
    BT-2's staleness gate verbatim. ``max_estimate_age_days`` is REQUIRED from birth: unlike
    ``risk.var.parametric_total``, this code has no pre-BT-2 v1, so no grandfathered ungated
    registration can legitimately exist — the ES-total bind path refuses an absent declaration
    outright rather than degrading to ungated (see :func:`declared_es_total_max_estimate_age_days`).
    """
    if int(appraisal_days) < 1:
        raise ValueError("appraisal_days must be >= 1 (the calendar-day appraisal cadence)")
    if int(max_estimate_age_days) < 1:
        raise ValueError(
            "max_estimate_age_days must be >= 1 (the calendar-day staleness policy for a cited "
            "residual estimate)"
        )
    text = str(confidence_level).strip()
    if not _CONFIDENCE_PATTERN.fullmatch(text) or len(text) > 6:
        raise ValueError(
            f"confidence_level {confidence_level!r} is not in the vocabulary "
            f"{sorted(VAR_ES_MULTIPLIERS)} (a new level is a new declared registration)"
        )
    confidence_key = f"{Decimal(text).quantize(Decimal('0.0001')):f}"
    z_text = VAR_Z_SCORES.get(confidence_key)
    k_text = VAR_ES_MULTIPLIERS.get(confidence_key)
    if z_text is None or k_text is None:
        raise ValueError(
            f"confidence_level {confidence_level} not in the vocabulary "
            f"{sorted(VAR_ES_MULTIPLIERS)}"
        )
    if int(horizon_days) != VAR_HORIZON_DAYS:
        raise ValueError(
            f"horizon_days must be {VAR_HORIZON_DAYS} in v1 (sqrt(h) scaling is a recorded seam)"
        )
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=ES_TOTAL_MODEL_CODE,
        name=ES_TOTAL_MODEL_NAME,
        model_type=VAR_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Total parametric Expected Shortfall = the registered ES multiplier over the governed "
            "total sigma (factor + idiosyncratic residual) (ES-1, ENT-027)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=ES_TOTAL_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=ES_TOTAL_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=ES_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *ES_ASSUMPTIONS_BASE,
                *VAR_TOTAL_ASSUMPTIONS_BASE[:3],  # the residual leg + frequency conversion
                f"{CONFIDENCE_ASSUMPTION_PREFIX}{confidence_key}",
                f"{HORIZON_ASSUMPTION_PREFIX}{int(horizon_days)}",
                f"{Z_ASSUMPTION_PREFIX}{z_text}",
                f"{ES_MULTIPLIER_ASSUMPTION_PREFIX}{k_text}",
                f"{APPRAISAL_DAYS_ASSUMPTION_PREFIX}{int(appraisal_days)}",
                f"{MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX}{int(max_estimate_age_days)}",
            ),
            limitations=ES_TOTAL_LIMITATIONS,
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
        or declared_es_multiplier(session, version, code=ES_TOTAL_MODEL_CODE) != Decimal(k_text)
        or declared_appraisal_days(session, version) != int(appraisal_days)
        or declared_es_total_max_estimate_age_days(session, version) != int(max_estimate_age_days)
    ):
        raise ModelVersionConflictError(
            ES_TOTAL_MODEL_CODE,
            ES_TOTAL_VERSION_LABEL,
            f"{code_version} (confidence_level={confidence_key}, horizon_days={horizon_days}, "
            f"es_multiplier={k_text}, appraisal_days={appraisal_days}, "
            f"max_estimate_age_days={max_estimate_age_days})",
        )
    return version


def declared_es_total_max_estimate_age_days(session: Session, version: ModelVersion) -> int:
    """The ES-total family's staleness policy — REQUIRED, never optional (ES-1, plan Step 3).

    :func:`declared_max_estimate_age_days` returns ``None`` on ABSENT because BT-2's total-VaR v1
    predates the policy and is immutable (the recorded grandfather). The ES-total CODE is born with
    the declaration, so no legitimate ungated version can ever exist here — absent must REFUSE, not
    degrade to ungated. Today an absent declaration is already unreachable through the governed path
    (a generic POST /models version carries status != REGISTERED and is caught by the backstop at
    every bind), so this costs nothing; it makes the record's claim true BY CONSTRUCTION rather than
    by an inherited backstop, which is the difference between a guarantee and a coincidence.
    """
    declared = declared_max_estimate_age_days(session, version)
    if declared is None:
        raise WrongModelVersionError(str(version.id), ES_TOTAL_MODEL_CODE)
    return declared
