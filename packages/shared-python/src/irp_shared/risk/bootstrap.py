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

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import Model, ModelVersion
from irp_shared.model.service import (
    assert_registered_model_version,
    register_model,
    register_model_version,
)


class WrongModelVersionError(Exception):
    """The ``model_version`` is registered but belongs to a DIFFERENT model than the run requires
    — reachable once two model families exist (the 2026-07 review finding: a sensitivity
    model_version must not drive a factor-exposure run, and vice versa). A CTRL-003 tightening;
    fail-closed pre-create. Maps to 422."""

    def __init__(self, model_version_id: str, expected_model_code: str) -> None:
        super().__init__(
            f"model_version {model_version_id} is not a version of {expected_model_code!r}"
        )
        self.model_version_id = str(model_version_id)
        self.expected_model_code = expected_model_code


class ModelVersionConflictError(Exception):
    """``(tenant, model, version_label)`` is already registered with a DIFFERENT ``code_version``
    — the immutable inventory identity cannot be silently re-pointed (the 2026-07 review finding:
    the old lookup-by-code_version raised IntegrityError -> 500 on the first re-registration after
    a deploy). Registering a genuinely new code requires a NEW version_label. Maps to 409."""

    def __init__(self, model_code: str, version_label: str, code_version: str) -> None:
        super().__init__(
            f"{model_code!r} {version_label!r} is already registered with a different "
            f"code_version (requested {code_version!r}); mint a new version_label instead"
        )
        self.model_code = model_code
        self.version_label = version_label
        self.code_version = code_version


def assert_model_version_of(
    session: Session,
    model_version_id: str,
    *,
    tenant_id: str,
    expected_model_code: str,
) -> ModelVersion:
    """CTRL-003 with model-identity: the version must be REGISTERED (fail-closed,
    ``assert_registered_model_version``) AND belong to the model ``expected_model_code`` —
    raising :class:`WrongModelVersionError` otherwise. Used pre-create by every risk binder so a
    run can never bind a methodology from a different model family."""
    version = assert_registered_model_version(session, str(model_version_id), tenant_id=tenant_id)
    model = session.execute(
        select(Model).where(Model.id == version.model_id, Model.tenant_id == str(tenant_id))
    ).scalar_one_or_none()
    if model is None or model.code != expected_model_code:
        raise WrongModelVersionError(str(model_version_id), expected_model_code)
    return version


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
