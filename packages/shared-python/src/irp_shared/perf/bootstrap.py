"""Governed registration of the perf-family models (PM-1 return + P3-8 benchmark-relative).

Each performance-measurement method is a **registered model** (the risk-family precedent, but a
PEER family — ``perf``, never under ``risk``): the per-model registrars inventory the ``model``
head + an immutable ``model_version`` through the governed model service via the ONE shared
``_register_perf_model`` core, emitting ``MODEL.REGISTER``/``MODEL.VERSION``. There are **NO free
numeric request parameters** — each model's fixed v1 conventions ARE the version identity, recorded
as ``model_assumption`` rows and parsed back by its binder; a same-label re-register with a
different ``code_version`` is a governed 409 (mint a new label for a new convention set). Each
binder then asserts the version is REGISTERED and OF ITS MODEL pre-create
(``assert_model_version_of``; CTRL-003).

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


def _register_perf_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str,
    model_code: str,
    model_name: str,
    model_type: str,
    version_label: str,
    methodology_ref: str,
    description: str,
    assumptions: tuple[str, ...],
    limitations: tuple[str, ...],
) -> ModelVersion:
    """The ONE ``code_version``-only perf registrar (idempotent). Every perf governed number carries
    NO free numeric request parameter — the fixed conventions ARE the version identity — so version
    resolution keys on ``code_version`` alone: a same-label re-register with a DIFFERENT
    ``code_version`` raises :class:`ModelVersionConflictError` (mint a new label); a same-label twin
    minted via the GENERIC registration (status != REGISTERED) raises
    :class:`WrongModelVersionError` (the P3-C1 register/run-consistency lesson). The public
    per-model registrars supply only their identity constants."""
    model = session.execute(
        select(Model).where(Model.tenant_id == str(tenant_id), Model.code == model_code)
    ).scalar_one_or_none()
    if model is None:
        model = register_model(
            session,
            tenant_id=str(tenant_id),
            code=model_code,
            name=model_name,
            model_type=model_type,
            actor_id=actor_id,
            description=description,
            actor_type=actor_type,
        )

    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == model.id,
            ModelVersion.version_label == version_label,
        )
    ).scalar_one_or_none()
    if version is not None:
        if version.status != "REGISTERED":
            raise WrongModelVersionError(str(version.id), str(model.code))
        if version.code_version != str(code_version):
            raise ModelVersionConflictError(model_code, version_label, str(code_version))
        return version

    return register_model_version(
        session,
        model=model,
        version_label=version_label,
        actor_id=actor_id,
        methodology_ref=methodology_ref,
        code_version=str(code_version),
        status="REGISTERED",
        assumptions=assumptions,
        limitations=limitations,
        actor_type=actor_type,
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
    ``code_version`` identity (PM-1, OD-PM-1-D). Delegates to :func:`_register_perf_model` — see
    its docstring for the conflict/wrong-version semantics."""
    return _register_perf_model(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=PORTFOLIO_RETURN_MODEL_CODE,
        model_name=PORTFOLIO_RETURN_MODEL_NAME,
        model_type=PORTFOLIO_RETURN_MODEL_TYPE,
        version_label=PORTFOLIO_RETURN_VERSION_LABEL,
        methodology_ref=PORTFOLIO_RETURN_METHODOLOGY_REF,
        description=(
            "Chain-linked time-weighted portfolio return (Modified-Dietz within "
            "caller-supplied exposure-run valuation boundaries), gross-of-fees, unannualized "
            "(PM-1, ENT-053)."
        ),
        assumptions=PORTFOLIO_RETURN_ASSUMPTIONS,
        limitations=PORTFOLIO_RETURN_LIMITATIONS,
    )


# --------------------------------------------------------------------------------------------------
# P3-8 — the ex-post benchmark-relative model (ENT-054). The SAME code_version-only registrar shape
# (no free numeric parameter — the v1 conventions ARE the version identity). Its OWN model family
# under the perf domain (a benchmark-relative run is a distinct governed number from a portfolio
# return; the run family `BENCHMARK_RELATIVE` reuses `perf.run`/`perf.view`, no new permission).
# --------------------------------------------------------------------------------------------------

#: The per-tenant inventory identity of the ex-post benchmark-relative model (PM/P3-8, OD-P3-8-A).
BENCHMARK_RELATIVE_MODEL_CODE = "perf.benchmark_relative"
BENCHMARK_RELATIVE_MODEL_NAME = "Ex-post benchmark-relative performance (active return/TE/IR, v1)"
BENCHMARK_RELATIVE_MODEL_TYPE = "BENCHMARK_RELATIVE"
BENCHMARK_RELATIVE_VERSION_LABEL = "v1"
BENCHMARK_RELATIVE_METHODOLOGY_REF = "05_analytics_methodologies/benchmark_relative_expost_v1.md"

#: Declared methodology choices (mirrored into model_assumption rows; OD-P3-8-C/D/E). NO free
#: numeric request parameter — the identity IS ``code_version`` + these fixed conventions.
BENCHMARK_RELATIVE_ASSUMPTIONS: tuple[str, ...] = (
    "Per sub-period ARITHMETIC active return a_i = r_p,i - r_b,i, where r_p,i are the DIETZ_PERIOD "
    "rows of ONE COMPLETED portfolio-return run (PM-1) and r_b,i is the GEOMETRIC compounding "
    "prod(1 + r_d) - 1 of the pinned SIMPLE benchmark_return rows whose return_date falls in the "
    "SAME half-open sub-period window (start, end]. The sub-periods are the PM-1 run's boundaries.",
    "TRACKING DIFFERENCE TD = R_p - R_b (each side geometrically compounded over the full span, "
    "the ESMA definition). TRACKING ERROR TE = the unbiased SAMPLE standard deviation (n-1 "
    "denominator) of the a_i (the ESMA ex-post definition; requires n >= 2 sub-periods). "
    "INFORMATION RATIO IR = mean(a_i) / TE (Grinold-Kahn); UNDEFINED and OMITTED when TE == 0.",
    "SIMPLE return_type; the CALLER chooses return_basis (PRICE/TOTAL/NET_TOTAL), echoed on every "
    "row. benchmark.benchmark_currency MUST equal the portfolio run's base_currency (no FX "
    "translation of return series in v1). All values Decimal-50 -> quantize_HALF_UP 12dp "
    "fractions/ratios; UNANNUALIZED (the ESMA disclosure TE is typically annualized - the DECLARED "
    "deviation, so these figures are never conflated with the UCITS disclosure numbers).",
)

#: The recorded scope-outs (mirrored into model_limitation rows; OD-P3-8-J + the PM-1 OD-K carry).
BENCHMARK_RELATIVE_LIMITATIONS: tuple[str, ...] = (
    "CAPTURED-HOLDINGS BOOK PROPAGATION: the portfolio side (PM-1) measures the captured-holdings "
    "book with no cash ledger, so uncaptured dividend/interest income understates the portfolio "
    "return - and that understatement flows INTO every P3-8 number (active return, TD, TE, IR) as "
    "a bias against a TOTAL-return benchmark. First-class limitation; mitigation is operational "
    "(capture the cash), NOT mathematical imputation. Named again per the PM-1 OD-K obligation.",
    "MISSING-DAY COMPOUNDING HAZARD: the benchmark side compounds the AVAILABLE pinned rows in "
    "each window; a vendor GAP inside a window silently understates the compounded benchmark "
    "return. Trading-calendar completeness validation is DEFERRED (the reference calendar tables "
    "exist; wiring them is a data-quality slice). A window with ZERO benchmark rows refuses.",
    "GROSS-vs-BASIS comparability: PM-1 returns are gross-of-fees over a captured-holdings book; "
    "the caller owns the return_basis choice (PRICE/TOTAL/NET_TOTAL) and NO silent basis "
    "adjustment is made - a gross portfolio vs a NET_TOTAL benchmark is the caller's comparison.",
    "ARITHMETIC active returns (geometric excess deferred); UNANNUALIZED; single benchmark per "
    "run; no active share; no relative VaR; no attribution; LOG return_type reserved. "
    "validation_status UNVALIDATED - recorded, non-enforcing until the P7 validation workflow.",
)


def register_benchmark_relative_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the ex-post benchmark-relative ``model`` + a ``model_version`` for
    this ``code_version`` identity (P3-8, OD-P3-8-A). Delegates to :func:`_register_perf_model` —
    see its docstring for the conflict/wrong-version semantics."""
    return _register_perf_model(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=BENCHMARK_RELATIVE_MODEL_CODE,
        model_name=BENCHMARK_RELATIVE_MODEL_NAME,
        model_type=BENCHMARK_RELATIVE_MODEL_TYPE,
        version_label=BENCHMARK_RELATIVE_VERSION_LABEL,
        methodology_ref=BENCHMARK_RELATIVE_METHODOLOGY_REF,
        description=(
            "Ex-post benchmark-relative performance (realized active return / tracking "
            "difference / tracking error / information ratio) over a portfolio-return run + a "
            "captured benchmark_return series, unannualized (P3-8, ENT-054)."
        ),
        assumptions=BENCHMARK_RELATIVE_ASSUMPTIONS,
        limitations=BENCHMARK_RELATIVE_LIMITATIONS,
    )
