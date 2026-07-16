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

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from irp_shared.model.assumptions import load_assumption_texts, require_declared
from irp_shared.model.models import ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
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
    # Both the model and the version are resolve-or-register (race-safe savepoint; MD-H1 OD-D): a
    # concurrent first bootstrap re-SELECTs the peer instead of a 500.
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=model_code,
        name=model_name,
        model_type=model_type,
        actor_id=actor_id,
        description=description,
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
            methodology_ref=methodology_ref,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=assumptions,
            limitations=limitations,
            actor_type=actor_type,
        ),
    )
    # Identity/conflict checks run unconditionally: trivially pass for a row THIS call minted, catch
    # a squatted (non-REGISTERED) or code_version-mismatched peer (race + idempotent re-invocation).
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(model_code, version_label, str(code_version))
    return version


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
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome refuses every new bind at the shared seam.",
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
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome refuses every new bind at the shared seam.",
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


#: The per-tenant inventory identity of the desmoothed-return model (PA-1, OD-PA-1-E). UNLIKE the
#: other perf models, this one carries a DECLARED numeric parameter: the Geltner speed-of-adjustment
#: ``alpha`` is part of the version identity (the BT-1 declared-alpha precedent) — the smoothing
#: profile is declared at registration, never a free request parameter.
DESMOOTHED_RETURN_MODEL_CODE = "perf.return.desmoothed_geltner"
DESMOOTHED_RETURN_MODEL_NAME = "Desmoothed return (Geltner AR(1) unsmoothing, v1)"
DESMOOTHED_RETURN_MODEL_TYPE = "DESMOOTHED_RETURN"
DESMOOTHED_RETURN_VERSION_LABEL = "v1"
DESMOOTHED_RETURN_METHODOLOGY_REF = "05_analytics_methodologies/desmoothing_geltner_v1.md"

#: The declared-parameter assumption prefix (OD-PA-1-E: alpha is part of the version identity —
#: parsed back for the identity check + the binder's read; the BT-1 precedent).
DESMOOTHING_ALPHA_ASSUMPTION_PREFIX = "alpha="

#: Strict decimal-fraction pattern for the declared alpha: a fraction in (0, 1] at up to 12dp
#: (e.g. '0.4', '0.25', '1'). The ZERO-valued match ('0.000...') is excluded by the domain check.
_DESMOOTHING_ALPHA_PATTERN = re.compile(r"(?:0\.[0-9]{1,12}|1(?:\.0{1,12})?)")

#: The declared methodology choices EXCLUDING the per-registration alpha (appended per call).
DESMOOTHED_RETURN_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "Geltner (1991/1993) AR(1) appraisal-unsmoothing: observed r_a,t = alpha*r_t + "
    "(1-alpha)*r_a,t-1; inverted per period as r_t = (r_a,t - (1-alpha)*r_a,t-1)/alpha. The "
    "single-lag AR(1) smoothing structure is ASSUMED (Getmansky-Lo-Makarov MA(q) and the "
    "Okunev-White iterative higher-order filter are recorded v2 variants).",
    "alpha ('speed of adjustment', 0 < alpha <= 1) is a DECLARED registration parameter estimated "
    "OFFLINE (conventionally alpha ~= 1 - rho_1, the observed series' first-order "
    "autocorrelation) - NOT a runtime regression; a different alpha is a different registered "
    "version (the declared-not-computed precedent).",
    "Observed returns are simple returns of consecutive appraisal marks (r_a,t = "
    "mark_t/mark_{t-1} - 1) of ONE (portfolio, instrument) pair; the AR(1) step is "
    "per-OBSERVATION (appraisal cadence is a convention, not schema-enforced).",
    "The first observed return SEEDS the recursion and yields NO desmoothed row (no imputation).",
    "Computed in Decimal at 50-digit context; per-period returns and stdevs quantize_HALF_UP to "
    "12 decimal places (Numeric(20,12)); the DESMOOTHING_SUMMARY row carries the desmoothed "
    "sample stdev (n-1) with the observed stdev as evidence - the honest-uncertainty statement.",
)

#: The recorded scope-outs (mirrored into model_limitation rows; decision record Part 3).
DESMOOTHED_RETURN_LIMITATIONS: tuple[str, ...] = (
    "SINGLE-LAG AR(1) ONLY: residual higher-order autocorrelation survives one Geltner pass; the "
    "Getmansky-Lo-Makarov MA(q) profile and the Okunev-White iterative filter are the recorded "
    "v2s.",
    "alpha is DECLARED, not estimated in-run - an offline mis-estimated alpha propagates directly "
    "into every desmoothed value; the desmoothed series is a MODEL OUTPUT, not an observation.",
    "IRREGULAR APPRAISAL SPACING is accepted and recorded: the AR(1) coefficient applies per "
    "observation step; a calendar-regularity gate is a recorded v2.",
    "Single-currency mark series only (no FX translation); simple returns (no log-return leg).",
    "Money-weighted return / IRR / capital-call handling deferred (the OD-PA-1-I re-recorded "
    "PA-3 item).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome refuses every new bind at the shared seam.",
)


def declared_desmoothing_alpha(session: Session, version: ModelVersion) -> Decimal:
    """Parse the version's declared Geltner ``alpha`` from its ``model_assumption`` rows (the
    OD-PA-1-E identity: exactly ONE strictly-well-formed declaration inside the (0, 1] domain).
    A malformed, absent, ambiguous, zero, or out-of-domain declaration is NOT a desmoothing
    identity — refuse fail-closed (:class:`WrongModelVersionError`, 422), never a bare parse
    crash (the P3-4 review lesson)."""
    raw = require_declared(
        load_assumption_texts(session, version),
        DESMOOTHING_ALPHA_ASSUMPTION_PREFIX,
        pattern=_DESMOOTHING_ALPHA_PATTERN,
        on_invalid=lambda: WrongModelVersionError(str(version.id), DESMOOTHED_RETURN_MODEL_CODE),
    )
    alpha = Decimal(raw)
    if not 0 < alpha <= 1:
        raise WrongModelVersionError(str(version.id), DESMOOTHED_RETURN_MODEL_CODE)
    return alpha


def register_desmoothed_return_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    alpha: str | Decimal = "0.4",
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the desmoothed-return ``model`` + a ``model_version`` for this
    ``(code_version, alpha)`` identity (PA-1, OD-PA-1-E — the BT-1 declared-parameter precedent).
    ``alpha`` must be a strict decimal fraction in ``(0, 1]`` (up to 12dp; alpha=1 is the
    no-smoothing boundary); re-registering the same label with ANY different declaration raises
    :class:`ModelVersionConflictError` (mint a new label); a same-label twin minted via the
    GENERIC registration (status != REGISTERED) raises :class:`WrongModelVersionError`."""
    # STRICT parse — never coerce (the P3-5 lesson: refuse, don't round).
    text = str(alpha).strip()
    if not _DESMOOTHING_ALPHA_PATTERN.fullmatch(text) or not 0 < Decimal(text) <= 1:
        raise ValueError(
            f"alpha {alpha!r} must be a strict decimal fraction in (0, 1] (up to 12dp) — "
            f"estimated OFFLINE and DECLARED, never a runtime regression (OD-PA-1-E)"
        )
    alpha_key = f"{Decimal(text).normalize():f}"

    # Both legs resolve-or-register (race-safe savepoint; MD-H1 OD-D). The version identity
    # includes the declared alpha — a same-label re-register differing on code_version or alpha is
    # a governed conflict, never an IntegrityError 500.
    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=DESMOOTHED_RETURN_MODEL_CODE,
        name=DESMOOTHED_RETURN_MODEL_NAME,
        model_type=DESMOOTHED_RETURN_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Geltner AR(1) unsmoothing of a captured private-asset appraisal mark series into a "
            "governed desmoothed return series with the honest-uncertainty stdev pair (PA-1, "
            "ENT-056)."
        ),
        actor_type=actor_type,
    )
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=DESMOOTHED_RETURN_VERSION_LABEL,
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=DESMOOTHED_RETURN_VERSION_LABEL,
            actor_id=actor_id,
            methodology_ref=DESMOOTHED_RETURN_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *DESMOOTHED_RETURN_ASSUMPTIONS_BASE,
                f"{DESMOOTHING_ALPHA_ASSUMPTION_PREFIX}{alpha_key}",
            ),
            limitations=DESMOOTHED_RETURN_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    # Identity/conflict checks run unconditionally: trivially pass for a row THIS call minted,
    # catch a squatted or code_version/alpha-mismatched peer.
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_desmoothing_alpha(session, version)  # malformed -> 422 class
    if version.code_version != str(code_version) or f"{declared.normalize():f}" != alpha_key:
        raise ModelVersionConflictError(
            DESMOOTHED_RETURN_MODEL_CODE,
            DESMOOTHED_RETURN_VERSION_LABEL,
            f"{code_version} (alpha={alpha_key})",
        )
    return version
