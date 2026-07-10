"""Governed registration of the portfolio-return model (PM-1, OD-PM-1-D).

The performance-measurement method is a **registered model** (the risk-family precedent, but a
PEER family — ``perf``, never under ``risk``): ``register_portfolio_return_model`` inventories the
``model`` head + an immutable ``model_version`` through the governed model service, emitting
``MODEL.REGISTER``/``MODEL.VERSION``. There are **NO free numeric request parameters** — the v1
conventions (the external-flow set, flow timing, day-count, gross-of-fees basis, the MV convention,
geometric linking) ARE the version identity, recorded as ``model_assumption`` rows and parsed back
by the binder; a same-label re-register with a different ``code_version`` is a governed 409 (mint a
new label for a new convention set). ``run_portfolio_return`` then asserts the version is REGISTERED
and OF THIS MODEL pre-create (``assert_model_version_of``; CTRL-003).

``Model.validation_status`` stays ``UNVALIDATED`` — recorded, non-enforcing until P7.

One-way imports: ``perf.bootstrap -> {model}`` only; imports NO ``risk`` symbol (the model-registry
governance primitives it needs — ``assert_model_version_of`` + the conflict/wrong-version errors —
were promoted to ``model.service`` at PM-1 for exactly this).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import Model, ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model,
    register_model_version,
)

#: The per-tenant inventory identity of the portfolio-return model (PM-1, OD-PM-1-D).
PORTFOLIO_RETURN_MODEL_CODE = "perf.return.twr"
PORTFOLIO_RETURN_MODEL_NAME = "Portfolio return (time-weighted, Modified-Dietz, v1)"
PORTFOLIO_RETURN_MODEL_TYPE = "PORTFOLIO_RETURN"
PORTFOLIO_RETURN_VERSION_LABEL = "v1"
PORTFOLIO_RETURN_METHODOLOGY_REF = "05_analytics_methodologies/portfolio_return_twr_v1.md"

#: The declared methodology choices (mirrored into model_assumption rows; OD-PM-1-B/C). NO free
#: numeric request parameters — the version identity IS ``code_version`` + these fixed conventions.
PORTFOLIO_RETURN_ASSUMPTIONS: tuple[str, ...] = (
    "Chain-linked TIME-WEIGHTED return with MODIFIED-DIETZ within caller-supplied valuation "
    "sub-periods (GIPS 2020): per sub-period r = (EMV - BMV - F) / (BMV + sum_j w_j*F_j), "
    "w_j = (CD - D_j)/CD (calendar-day, END-of-day flow timing); cumulative R = prod(1 + r_i) - 1 "
    "(geometric linking). A no-flow sub-period reduces EXACTLY to EMV/BMV - 1 (true TWR).",
    "Market values (BMV/EMV) are the sum of the pinned exposure_aggregate atoms of ONE COMPLETED "
    "exposure run per valuation boundary (the platform MV convention: signed qty * captured mark * "
    "effective FX, base currency); the caller supplies N >= 2 boundaries in date order. Supplying "
    "a boundary AT a flow date makes that flow a true TWR revaluation (the caller's lever).",
    "The EXTERNAL-FLOW set is {TRANSFER_IN -> +contribution, TRANSFER_OUT -> -withdrawal} ONLY. "
    "Every other captured txn_type (BUY/SELL/DIVIDEND/INTEREST/FEE/REVERSAL/...) is INTERNAL to "
    "the measured book. Flow value = the transaction gross_amount converted to base currency via "
    "the pinned FX legs at the flow's trade_date (a NULL amount/currency or a missing leg fails "
    "closed - NO imputation). Extending the flow set is a NEW version label, never silent.",
    "GROSS-of-fees, UNANNUALIZED, in the exposure runs' base currency. BMV > 0 and the average-"
    "capital denominator > 0 are preconditions (a return over zero/negative capital is undefined - "
    "refused pre-create). Computed in Decimal at 50-digit precision; return_value quantize_HALF_UP "
    "to 12 decimal places (the Numeric(20,12) return-fraction scale).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-PM-1-J/K).
PORTFOLIO_RETURN_LIMITATIONS: tuple[str, ...] = (
    "CAPTURED-HOLDINGS BOOK: the platform has no cash ledger, so dividend/interest cash that is "
    "not subsequently captured as a position (or transferred out) is INVISIBLE to market value - "
    "total return is UNDERSTATED by uncaptured income sitting outside the book. This is a "
    "first-class limitation; the mitigation is operational (capture the cash as a position or a "
    "transfer), NOT mathematical imputation. Named again wherever actives consume this series.",
    "MONEY-WEIGHTED return / IRR (the private-asset / committed-capital measure, GIPS 2.A.25+) is "
    "DEFERRED to the private-asset foundations slice (PA-0), where GIPS itself prescribes it.",
    "GROSS-of-fees only - no fee capture exists; net-of-fees is a deferred version.",
    "SINGLE-PORTFOLIO BOOK (v1): all pinned atoms must resolve to ONE portfolio_id; a multi-"
    "portfolio / subtree book is REFUSED pre-create. An intra-subtree transfer between two child "
    "portfolios of the measured book is INTERNAL (not an external flow), and that classification "
    "is a deferred slice - refusing the case is the honest boundary, never a silent mismeasure.",
    "No large-external-flow revaluation THRESHOLD (every valuation boundary is caller-supplied); "
    "no composites (a firm-level GIPS construct, out of platform scope); no annualization "
    "(sqrt/^T scaling is a later declared transform); no sub-portfolio / instrument-level "
    "attribution.",
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def register_portfolio_return_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the portfolio-return ``model`` + a ``model_version`` for this
    ``code_version`` identity (PM-1, OD-PM-1-D). NO free numeric request parameters — the v1
    conventions ARE the identity — so version resolution keys on ``code_version`` alone: a same-
    label re-register with a DIFFERENT ``code_version`` raises :class:`ModelVersionConflictError`
    (mint a new label); a same-label twin minted via the GENERIC registration (status != REGISTERED)
    raises :class:`WrongModelVersionError` (the P3-C1 register/run-consistency lesson)."""
    model = session.execute(
        select(Model).where(
            Model.tenant_id == str(tenant_id), Model.code == PORTFOLIO_RETURN_MODEL_CODE
        )
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=PORTFOLIO_RETURN_MODEL_CODE,
            name=PORTFOLIO_RETURN_MODEL_NAME,
            model_type=PORTFOLIO_RETURN_MODEL_TYPE,
            actor_id=actor_id,
            description=(
                "Chain-linked time-weighted portfolio return (Modified-Dietz within "
                "caller-supplied exposure-run valuation boundaries), gross-of-fees, unannualized "
                "(PM-1, ENT-053)."
            ),
            actor_type=actor_type,
        )

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == PORTFOLIO_RETURN_VERSION_LABEL,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            raise WrongModelVersionError(str(version.id), str(model.code))
        if version.code_version != str(code_version):
            raise ModelVersionConflictError(
                PORTFOLIO_RETURN_MODEL_CODE, PORTFOLIO_RETURN_VERSION_LABEL, str(code_version)
            )
        return version

    return register_model_version(
        session,
        model=model,
        version_label=PORTFOLIO_RETURN_VERSION_LABEL,
        actor_id=actor_id,
        methodology_ref=PORTFOLIO_RETURN_METHODOLOGY_REF,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=PORTFOLIO_RETURN_ASSUMPTIONS,
        limitations=PORTFOLIO_RETURN_LIMITATIONS,
        actor_type=actor_type,
    )
