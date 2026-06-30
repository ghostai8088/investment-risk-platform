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
from irp_shared.model.service import register_model, register_model_version

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

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == SENSITIVITY_VERSION_LABEL,
            ModelVersion.code_version == str(code_version),
        )
    ).scalar_one_or_none()
    if version is not None:
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
