"""Perf-family model registration (PM-1 return, P3-8 benchmark-relative, PA-1/DS-2 desmoothing,
RM-1 rolling risk, SR-1 Sharpe).

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
from dataclasses import dataclass
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
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    "SINGLE-LAG AR(1) ONLY on this version: residual higher-order autocorrelation survives one "
    "Geltner pass; the Okunev-White iterative filter is REALIZED as a declared estimator "
    "convention (DS-2); the Getmansky-Lo-Makarov MA(q) profile remains the recorded v2 - its "
    "MLE requires constrained numerical optimization, a determinism obstacle this runtime has "
    "not admitted.",
    "alpha is DECLARED on this version - the AR1_ESTIMATED convention (DS-2) estimates it "
    "in-run with a persisted Bartlett band; an offline mis-estimated alpha still propagates "
    "directly into every desmoothed value here, and the desmoothed series is a MODEL OUTPUT, "
    "not an observation.",
    "IRREGULAR APPRAISAL SPACING is accepted and recorded: the AR(1) coefficient applies per "
    "observation step; a calendar-regularity gate is a recorded v2.",
    "Single-currency mark series only (no FX translation); simple returns (no log-return leg).",
    "Money-weighted return / IRR / capital-call handling deferred (the OD-PA-1-I re-recorded "
    "PA-3 item).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
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
    version_label: str = DESMOOTHED_RETURN_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the desmoothed-return ``model`` + a ``model_version`` for this
    ``(code_version, alpha)`` identity (PA-1, OD-PA-1-E — the BT-1 declared-parameter precedent).
    ``alpha`` must be a strict decimal fraction in ``(0, 1]`` (up to 12dp; alpha=1 is the
    no-smoothing boundary); re-registering the same label with ANY different declaration raises
    :class:`ModelVersionConflictError` — minting the new label is done HERE via ``version_label``
    (MF-1: a tenant holding the alpha=0.4 ``v1`` registers its alpha=1 sibling under a distinct
    label; the identity discipline stays inside the family registrar, never the generic path); a
    same-label twin minted via the GENERIC registration (status != REGISTERED) raises
    :class:`WrongModelVersionError`."""
    # STRICT parse — never coerce (the P3-5 lesson: refuse, don't round).
    text = str(alpha).strip()
    if not _DESMOOTHING_ALPHA_PATTERN.fullmatch(text) or not 0 < Decimal(text) <= 1:
        raise ValueError(
            f"alpha {alpha!r} must be a strict decimal fraction in (0, 1] (up to 12dp) — "
            f"estimated OFFLINE and DECLARED, never a runtime regression (OD-PA-1-E)"
        )
    if not str(version_label).strip():
        raise ValueError("version_label must be non-empty (MF-1: the label IS the identity key)")
    alpha_key = f"{Decimal(text).normalize():f}"
    # NOTE: distinct labels MAY declare the same (code_version, alpha) — each version is an
    # independent, fully-declared registration; the conflict discipline is per-label (MF-1).

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
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
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
            str(version_label),
            f"{code_version} (alpha={alpha_key})",
        )
    return version


# --- DS-2 (OD-DS-2-C): the desmoothing estimator conventions — the RS-1 gate pattern adapted.
#
# Both new estimators are declared VERSIONS of the SAME perf.return.desmoothed_geltner code (no new
# model code). The shipped declared-alpha identity is GRANDFATHERED: an ABSENT estimator_convention
# means the implicit DECLARED convention (every existing version parses exactly as before).
# AMBIGUITY (>1 convention row) and STRAY inapplicable literals are refused fail-closed — the RS-1
# adversarial-HIGH lesson folded from birth.

#: The implicit v1 convention (never stamped on a declared-alpha version — absent => this).
DESMOOTHING_DECLARED_CONVENTION = "DECLARED"
#: OD-DS-2-A: alpha-hat = 1 - rho-hat_1 computed IN-RUN from the pinned marks (+ the band).
DESMOOTHING_AR1_ESTIMATED_CONVENTION = "AR1_ESTIMATED"
#: OD-DS-2-B: the Okunev-White iterative higher-order filter (declared max order; alpha = NULL).
DESMOOTHING_OKUNEV_WHITE_CONVENTION = "OKUNEV_WHITE_ITERATIVE"

#: The same literal prefix the risk families use ("estimator_convention=") — defined locally (perf
#: imports NO risk symbol; the peer-package split).
DESMOOTHING_ESTIMATOR_ASSUMPTION_PREFIX = "estimator_convention="
DESMOOTHING_MIN_PERIODS_ASSUMPTION_PREFIX = "min_periods="
DESMOOTHING_BAND_ASSUMPTION_PREFIX = "band_convention="
DESMOOTHING_OW_ORDER_ASSUMPTION_PREFIX = "ow_max_order="

#: The declared band convention literal (OD-DS-2-A): the band is registrar-stamped IDENTITY so a
#: future exact-AR1 band is a NEW version, never silent drift.
DESMOOTHING_BARTLETT_BAND = "BARTLETT_WHITE_NOISE"
#: The structural floor under any declared min_periods (rho-hat_1 on fewer points is noise).
DESMOOTHING_MIN_PERIODS_FLOOR = 6
#: The declared OW max order domain (small-int gate; each order adds a pass + drops i values).
_DESMOOTHING_OW_ORDER_PATTERN = re.compile(r"[1-4]")
# No leading zeros: "007" and "7" must not alias one identity (the strict-alpha no-coercion
# discipline; the adversarial-review A2 fold).
_DESMOOTHING_MIN_PERIODS_PATTERN = re.compile(r"[1-9][0-9]{0,2}")

DESMOOTHING_AR1_ESTIMATED_VERSION_LABEL = "v2-ar1-estimated"
#: The DS-2 residual-estimation referent (both new conventions cite it).
DESMOOTHING_ESTIMATED_METHODOLOGY_REF = "05_analytics_methodologies/desmoothing_estimated_v1.md"
DESMOOTHING_OKUNEV_WHITE_VERSION_LABEL = "v2-okunev-white"

#: OD-DS-2-A dossier — the estimated convention's declared methodology.
DESMOOTHING_AR1_ESTIMATED_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "The Geltner AR(1) inversion with alpha ESTIMATED IN-RUN from the pinned observed series: "
    "alpha-hat = 1 - rho-hat_1, where rho-hat_1 is the lag-1 sample autocorrelation under the "
    "T-denominator (Box-Jenkins) convention - the PA-1-recorded offline procedure brought "
    "in-run, deterministic closed form (no optimizer), fully reproducible from the pinned marks "
    "alone.",
    "FAIL-CLOSED, never a silent clamp: rho-hat_1 <= 0 (no positive smoothing signal) refuses "
    "pre-create - the declared-alpha version remains available; alpha-hat lands in (0,1) by "
    "construction otherwise.",
    "The persisted alpha column carries the COMPUTED alpha-hat (the echo = what the run used); "
    "the DESMOOTHING_SUMMARY row additionally persists alpha_stderr under the declared "
    "band_convention=BARTLETT_WHITE_NOISE (SE(rho-hat_1) ~ 1/sqrt(n); SE(alpha-hat) equals it "
    "by the delta method).",
    "A declared min_periods floor gates the estimation (structural floor 6 observed returns) - "
    "an estimate on fewer points is refused, not disclaimed.",
)

#: OD-DS-2-A/OD-F dossier limitations (the verifier-corrected honesty set).
DESMOOTHING_AR1_ESTIMATED_LIMITATIONS: tuple[str, ...] = (
    "SAMPLING ERROR on appraisal-length series: SE(rho-hat_1) ~ 1/sqrt(n) is large at typical "
    "private-asset lengths (~0.26 at n=15) - the band is persisted and wide; series length is "
    "the lever.",
    "SMALL-SAMPLE UPWARD BIAS: rho-hat_1 is biased DOWNWARD ~ -(1+4*phi)/n (Kendall 1954; "
    "Marriott-Pope 1954), so alpha-hat is biased UPWARD on short series (executed MC: E[alpha-"
    "hat] ~ 0.58 at n=15 when the true alpha is 0.40) - disclosed, never corrected in-run; a "
    "bias-corrected estimator is a recorded v2.",
    "CONSERVATIVE BAND: the declared BARTLETT_WHITE_NOISE band 1/sqrt(n) OVERSTATES SE(rho-"
    "hat_1) under AR(1) at lag 1 (the exact-AR1 band sqrt((1-phi^2)/n) is narrower - a recorded "
    "v2); the band is an identification convention, never an exact confidence interval.",
    "STRUCTURE STILL ASSUMED: estimating alpha does not fix structural mis-specification - the "
    "single-lag AR(1) form is still imposed; the Okunev-White higher-order filter (this slice) "
    "and the Getmansky-Lo-Makarov MA(q) profile (a recorded v2 - its MLE requires constrained "
    "numerical optimization, a determinism obstacle this runtime has not admitted) address "
    "structure.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
)

#: OD-DS-2-B dossier — the Okunev-White convention's declared methodology.
DESMOOTHING_OKUNEV_WHITE_ASSUMPTIONS_BASE: tuple[str, ...] = (
    "The Okunev-White iterative higher-order filter (SSRN 460641; Loudon-Okunev-White JFI 2006): "
    "ONE deterministic pass per order i = 1..ow_max_order, ascending; pass i measures rho_i and "
    "rho_2i on the CURRENT series (the T-denominator convention) and applies the lag-i filter "
    "r*_t = (r_t - c_i*r_{t-i})/(1 - c_i) with c_i the '-' root of rho_i*c^2 - (1+rho_2i)*c + "
    "rho_i = 0 (the sole admissible |c| <= 1 root - Vieta reciprocal roots; settled by "
    "derivation and executed proof at planning).",
    "Deterministic closed form (no optimizer); the c_i coefficients are NOT persisted - fully "
    "reproducible from the pinned marks + the declared identity.",
    "The filtered rows carry alpha NULL (the convention has no single alpha); the summary "
    "row persists the stdev pair as v1 with alpha_stderr NULL.",
    "rho_i < 0 is admissible and DELIBERATE (whitening is the objective, both signs); the "
    "Geltner single pass is the m=1 special case under EXACT AR(1) structure only (on sample "
    "data OW m=1 differs from AR1_ESTIMATED - never asserted equivalent).",
)

#: OD-DS-2-B/OD-F dossier limitations.
DESMOOTHING_OKUNEV_WHITE_LIMITATIONS: tuple[str, ...] = (
    "FIXED PASS SEQUENCE: one pass per order, ascending - a later pass slightly perturbs "
    "earlier orders' autocorrelations; the repeat-until-tolerance variant is a recorded v2 "
    "(deliberately not shipped: a tolerance loop is not deterministic-by-declaration).",
    "VENDOR-NORMALIZED TRANSCRIPTION: the per-pass formula is verified by first-principles "
    "derivation plus a technical vendor reproduction; the SSRN primary is GATED - re-verify "
    "against the primary or a second independent source before any extension.",
    "SERIES SHORTENING: each order-i pass drops its first i filtered values (cumulative loss "
    "m(m+1)/2); the structural floor requires n >= m(m+1)/2 + 2 and each pass's length > 2i "
    "(else rho_2i would be an empty-sum artifact; at the per-pass minimum length 2i+1 it "
    "rests on a SINGLE product - measured, admissible, maximally noisy) - short appraisal "
    "series bound the usable order.",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation "
    "exception, MG-1) refuses every new bind at the shared seam.",
)


@dataclass(frozen=True)
class DesmoothingParameters:
    """The version's declared desmoothing estimator identity (DS-2, OD-DS-2-C).
    ``estimator_convention`` is OPTIONAL with a DECLARED default (the grandfather — absent =>
    DECLARED, exactly the shipped parse). ``alpha`` is present for DECLARED only; ``min_periods``
    + ``band_convention`` for AR1_ESTIMATED only; ``ow_max_order`` for OKUNEV_WHITE only."""

    estimator_convention: str
    alpha: Decimal | None
    min_periods: int | None
    band_convention: str | None
    ow_max_order: int | None


def declared_desmoothing_parameters(
    session: Session, version: ModelVersion
) -> DesmoothingParameters:
    """Parse the version's declared desmoothing estimator identity (DS-2, OD-DS-2-C). ABSENT
    ``estimator_convention`` (zero rows) => the implicit DECLARED grandfather (requires the
    ``alpha=`` literal, exactly the shipped behavior; an EXPLICIT ``DECLARED`` row is
    accepted and behaviorally identical — no registrar stamps one, adversarial A5). AMBIGUOUS
    (>1 convention row) is refused — never collapsed into the grandfather (the RS-1
    adversarial-HIGH lesson); a present
    convention must be a recognized literal with its companions well-formed and NO inapplicable
    stray literal (a stray ``alpha=`` on an estimated/OW version is a lying identity). Malformed
    -> the fail-closed :class:`WrongModelVersionError`."""
    texts = load_assumption_texts(session, version)
    convention_rows = [t for t in texts if t.startswith(DESMOOTHING_ESTIMATOR_ASSUMPTION_PREFIX)]

    def _fail() -> WrongModelVersionError:
        return WrongModelVersionError(str(version.id), DESMOOTHED_RETURN_MODEL_CODE)

    if len(convention_rows) > 1:
        raise _fail()  # ambiguity is refused, never grandfathered

    has_alpha = any(t.startswith(DESMOOTHING_ALPHA_ASSUMPTION_PREFIX) for t in texts)
    has_min_periods = any(t.startswith(DESMOOTHING_MIN_PERIODS_ASSUMPTION_PREFIX) for t in texts)
    has_band = any(t.startswith(DESMOOTHING_BAND_ASSUMPTION_PREFIX) for t in texts)
    has_ow = any(t.startswith(DESMOOTHING_OW_ORDER_ASSUMPTION_PREFIX) for t in texts)

    convention = (
        convention_rows[0][len(DESMOOTHING_ESTIMATOR_ASSUMPTION_PREFIX) :]
        if convention_rows
        else DESMOOTHING_DECLARED_CONVENTION
    )

    if convention == DESMOOTHING_DECLARED_CONVENTION:
        if has_min_periods or has_band or has_ow:  # stray literals = a lying identity
            raise _fail()
        alpha = declared_desmoothing_alpha(session, version)
        return DesmoothingParameters(DESMOOTHING_DECLARED_CONVENTION, alpha, None, None, None)
    if convention == DESMOOTHING_AR1_ESTIMATED_CONVENTION:
        if has_alpha or has_ow:
            raise _fail()
        min_periods_text = require_declared(
            texts,
            DESMOOTHING_MIN_PERIODS_ASSUMPTION_PREFIX,
            pattern=_DESMOOTHING_MIN_PERIODS_PATTERN,
            on_invalid=_fail,
        )
        min_periods = int(min_periods_text)
        if min_periods < DESMOOTHING_MIN_PERIODS_FLOOR:
            raise _fail()
        band = require_declared(
            texts,
            DESMOOTHING_BAND_ASSUMPTION_PREFIX,
            pattern=re.compile(re.escape(DESMOOTHING_BARTLETT_BAND)),
            on_invalid=_fail,
        )
        return DesmoothingParameters(
            DESMOOTHING_AR1_ESTIMATED_CONVENTION, None, min_periods, band, None
        )
    if convention == DESMOOTHING_OKUNEV_WHITE_CONVENTION:
        if has_alpha or has_min_periods or has_band:
            raise _fail()
        ow_text = require_declared(
            texts,
            DESMOOTHING_OW_ORDER_ASSUMPTION_PREFIX,
            pattern=_DESMOOTHING_OW_ORDER_PATTERN,
            on_invalid=_fail,
        )
        return DesmoothingParameters(
            DESMOOTHING_OKUNEV_WHITE_CONVENTION, None, None, None, int(ow_text)
        )
    raise _fail()


def register_desmoothed_return_estimated_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    min_periods: int = 8,
    version_label: str = DESMOOTHING_AR1_ESTIMATED_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) an AR1_ESTIMATED desmoothing version (DS-2, OD-DS-2-A). Identity =
    (code_version, estimator_convention=AR1_ESTIMATED, min_periods, band_convention) — the
    convention + companions are REGISTRAR-STAMPED, never caller-suppliable from the generic path;
    a same-label re-register with a different declaration raises
    :class:`ModelVersionConflictError`."""
    if int(min_periods) < DESMOOTHING_MIN_PERIODS_FLOOR:
        raise ValueError(
            f"min_periods must be >= {DESMOOTHING_MIN_PERIODS_FLOOR} (rho-hat_1 on fewer "
            f"observed returns is noise); got {min_periods}"
        )
    if not str(version_label).strip():
        raise ValueError("version_label must be non-empty")
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
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=DESMOOTHING_ESTIMATED_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *DESMOOTHING_AR1_ESTIMATED_ASSUMPTIONS_BASE,
                f"{DESMOOTHING_ESTIMATOR_ASSUMPTION_PREFIX}"
                f"{DESMOOTHING_AR1_ESTIMATED_CONVENTION}",
                f"{DESMOOTHING_MIN_PERIODS_ASSUMPTION_PREFIX}{int(min_periods)}",
                f"{DESMOOTHING_BAND_ASSUMPTION_PREFIX}{DESMOOTHING_BARTLETT_BAND}",
            ),
            limitations=DESMOOTHING_AR1_ESTIMATED_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_desmoothing_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or declared.estimator_convention != DESMOOTHING_AR1_ESTIMATED_CONVENTION
        or declared.min_periods != int(min_periods)
    ):
        raise ModelVersionConflictError(
            DESMOOTHED_RETURN_MODEL_CODE,
            str(version_label),
            f"{code_version} (estimator_convention={DESMOOTHING_AR1_ESTIMATED_CONVENTION}, "
            f"min_periods={min_periods})",
        )
    return version


def register_desmoothed_return_okunev_white_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    ow_max_order: int = 2,
    version_label: str = DESMOOTHING_OKUNEV_WHITE_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) an OKUNEV_WHITE_ITERATIVE desmoothing version (DS-2, OD-DS-2-B).
    Identity = (code_version, estimator_convention=OKUNEV_WHITE_ITERATIVE, ow_max_order); the
    convention + order are REGISTRAR-STAMPED; a same-label re-register with a different
    declaration raises :class:`ModelVersionConflictError`."""
    if not 1 <= int(ow_max_order) <= 4:
        raise ValueError(f"ow_max_order must be in 1..4; got {ow_max_order}")
    if not str(version_label).strip():
        raise ValueError("version_label must be non-empty")
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
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=DESMOOTHING_ESTIMATED_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=(
                *DESMOOTHING_OKUNEV_WHITE_ASSUMPTIONS_BASE,
                f"{DESMOOTHING_ESTIMATOR_ASSUMPTION_PREFIX}"
                f"{DESMOOTHING_OKUNEV_WHITE_CONVENTION}",
                f"{DESMOOTHING_OW_ORDER_ASSUMPTION_PREFIX}{int(ow_max_order)}",
            ),
            limitations=DESMOOTHING_OKUNEV_WHITE_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), str(model.code))
    declared = declared_desmoothing_parameters(session, version)
    if (
        version.code_version != str(code_version)
        or declared.estimator_convention != DESMOOTHING_OKUNEV_WHITE_CONVENTION
        or declared.ow_max_order != int(ow_max_order)
    ):
        raise ModelVersionConflictError(
            DESMOOTHED_RETURN_MODEL_CODE,
            str(version_label),
            f"{code_version} (estimator_convention={DESMOOTHING_OKUNEV_WHITE_CONVENTION}, "
            f"ow_max_order={ow_max_order})",
        )
    return version


# --------------------------------------------------------------------------------------------------

#: The per-tenant inventory identity of the rolling-risk model (RM-1, OD-RM-1-G/M). The declared
#: WINDOW SET is part of the version identity: {12, 36} months. That is not a convenience — **it is
#: where GIPS 2.A.12 is actually enforced**. No governed caller can present a window under 12
#: months, so the kernel's own annualization guard is honest defense-in-depth rather than "the
#: invariant" (calling it the invariant would be a vacuous control).
ROLLING_RISK_MODEL_CODE = "perf.rolling_risk"
ROLLING_RISK_MODEL_NAME = "Rolling risk over the governed return series (return/volatility/MDD, v1)"
ROLLING_RISK_MODEL_TYPE = "ROLLING_RISK"
ROLLING_RISK_VERSION_LABEL = "v1"
ROLLING_RISK_METHODOLOGY_REF = "05_analytics_methodologies/rolling_risk_v1.md"

#: The registered window set — the parameter domain that enforces GIPS 2.A.12.
ROLLING_RISK_WINDOWS: tuple[int, ...] = (12, 36)

ROLLING_RISK_ASSUMPTIONS: tuple[str, ...] = (
    "GRID: the pinned DIETZ_PERIOD sub-periods of ONE COMPLETED portfolio-return run (PM-1) are "
    "GEOMETRICALLY RELINKED within each calendar month (GIPS 2.A.24.f), and every statistic is "
    "computed on the resulting MONTHLY series. GIPS defines the ex-post risk statistic only on the "
    "monthly series (4.A.1.j) over inputs valued at least monthly, as of the calendar month end OR "
    "THE LAST BUSINESS DAY of the month (2.A.23.a/b) - so sub-period returns are inputs, never the "
    "sample. A span that does not partition into whole months is REFUSED, never truncated: the "
    "boundary grid must open on a month end, close on a month end, contain a month-end boundary "
    "for every interior calendar month, open on the LAST boundary of its month (a later boundary "
    "in the opening month would make the first observation a partial stub), and close every "
    "measured month on a month-end (an intra-month closing date would be stamped into governed "
    "rows as period_end). (Enumeration completed at the Wave-13 close: this registered text "
    "previously stated the first three conditions while the kernel enforces five - the two added "
    "here are the pair the 4-finder review's one-day-month HIGH was folded with, so the per-tenant "
    "governance artifact a 2L validator reads now matches the enforced gate.)",
    "VOLATILITY: the sample standard deviation on the unbiased-VARIANCE (n-1) denominator, centred "
    "on the ARITHMETIC mean, ANNUALIZED by x sqrt(12) (GIPS 4.A.1.j's operator) computed from the "
    "STORED 12dp monthly value so the emitted pair reconciles EXACTLY. GIPS does not prescribe n "
    "vs n-1; the choice is material (+4.45% at n=12, +1.42% at n=36). The square root of an "
    "unbiased variance is itself a DOWNWARD-BIASED estimator of sigma by about 2.24% at n=12 "
    "(Bessel/c4) - GIPS and CFA Institute both use it and neither applies a c4 correction, and "
    "RM-1 follows them. Centring is arithmetic although returns link geometrically: an internal "
    "tension in the standard, documented rather than silently resolved.",
    "RETURN: R = prod(1 + m_j) - 1 over the window; annualized as R_ann = (1 + R)^(12/W) - 1 "
    "(GIPS's geometric convention). Never below a 12-month window (GIPS 2.A.12: returns for "
    "periods of less than one year MUST NOT be annualized), enforced by this registered window "
    "domain. At W = 12 the exponent is exactly 1, so the annualized return is DEFINITIONALLY the "
    "cumulative return and the redundant row is SUPPRESSED rather than emitted twice.",
    "MAXIMUM DRAWDOWN: max over the window of (running_peak - V)/running_peak on the compounded "
    "TWR wealth index (a NAV path would register a redemption as a drawdown; the linked TWR index "
    "is flow-neutral). The index is REBASED TO 1 AT EACH WINDOW'S OPENING BOUNDARY and the peak is "
    "taken within that window only, so MDD_36 >= MDD_12 at a common end date. The base point V_0 = "
    "1 IS an observation with drawdown zero (Chekhlov's w_0/xi_0). NEVER annualized: a bounded, "
    "saturating, horizon-monotone statistic has no horizon-scaling law. Every row carries its "
    "window and its sampling frequency (MONTHLY), the measure being frequency-dependent and "
    "downward-biased by discretisation (monthly MDD <= daily MDD <= continuous MDD, always).",
    "PRECONDITION: every monthly return must satisfy 1 + m > 0. PM-1 admits EMV = 0 (yielding "
    "exactly -1), and link_periods has no such guard, so the wealth index would be ABSORBING, the "
    "ratio-to-peak could exceed 1 or invert sign, and the geometric annualization would raise on a "
    "negative base. A total-loss book cannot carry a governed drawdown - a first-class recorded "
    "limitation, not a 500.",
)

ROLLING_RISK_LIMITATIONS: tuple[str, ...] = (
    "TWO-STAGE LINKING IS NOT BIT-IDENTICAL TO PM-1's. The same link_periods implementation is "
    "used, so the linkage CONVENTION is shared, but it quantizes to 12dp on return - so "
    "sub-periods -> month -> window aggregation is NOT associative with PM-1's one-stage link "
    "(worst case a few ulp at 12dp). A supervisor comparing RM-1's 12-month rolling return with "
    "PM-1's TWR_LINKED over the same span will find a 12th-decimal difference. This is expected; "
    "a test pins the NON-equality direction so nobody later 'fixes' it with an equality assert.",
    "ROLLING VALUES ARE NOT INDEPENDENT. Adjacent 12-month windows share 11 of 12 observations "
    "(~92% overlap), so a change between consecutive windows reflects the single entering and "
    "exiting month, NOT a re-estimate. This is the most likely misreading of the surface.",
    "MONTH-END CONVENTION IS HOLIDAY-FREE in v1: the last calendar day, or the last WEEKDAY when "
    "that falls on a weekend. A month end landing on a market HOLIDAY is a recorded residual - no "
    "holiday substrate exists (the ENT-006 calendar tables carry no business-day logic). A full "
    "holiday-aware convention is a recorded v2.",
    "CAPTURED-HOLDINGS BOOK PROPAGATION: PM-1 measures a book with no cash ledger, so uncaptured "
    "income understates the return series - and that understatement flows into every RM-1 "
    "statistic. Mitigation is operational (capture the cash), never mathematical imputation.",
    "NO BENCHMARK LEG in v1, so GIPS 2.A.18.a (same-grid, same-methodology comparison) does not "
    "bind here - it binds the v2 benchmark leg. Rows are GROSS-of-fees (inherited from PM-1) and "
    "carry that flag rather than inferring it (GIPS 4.C.44). No Sharpe (SR-1), no AvDD/CDD, no "
    "drawdown duration or time-to-recovery, no daily grid (k=252 is uncited). "
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation exception, "
    "MG-1) refuses every new bind at the shared seam.",
)


def register_rolling_risk_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the rolling-risk ``model`` + a ``model_version`` for this
    ``code_version`` identity (RM-1, OD-RM-1-G/M).

    **PM-1's ``PORTFOLIO_RETURN_ASSUMPTIONS`` tuple is deliberately NOT edited here**, even though
    it is where the annualization deferral was originally recorded: ``resolve_or_register_version``
    returns an existing version UNTOUCHED on a SELECT hit, so amending that tuple would leave
    tenants registered before the change carrying DIFFERENT assumption text under the same ``v1``
    label — silent, un-audited divergence. The discharge lives in RM-1's own assumption rows above
    and in the doc amendments.
    """
    return _register_perf_model(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=ROLLING_RISK_MODEL_CODE,
        model_name=ROLLING_RISK_MODEL_NAME,
        model_type=ROLLING_RISK_MODEL_TYPE,
        version_label=ROLLING_RISK_VERSION_LABEL,
        methodology_ref=ROLLING_RISK_METHODOLOGY_REF,
        description=(
            "Trailing-window rolling return, rolling volatility and maximum drawdown over the "
            "governed portfolio-return series, on a relinked calendar-month grid (RM-1, ENT-064)."
        ),
        assumptions=ROLLING_RISK_ASSUMPTIONS,
        limitations=ROLLING_RISK_LIMITATIONS,
    )


#: The per-tenant inventory identity of the Sharpe model (SR-1, OD-SR-1-E). The declared WINDOW SET
#: {12, 36} is part of the version identity, exactly as in RM-1 — and here too it is the parameter
#: domain, not a kernel guard, that keeps a governed caller off sub-annual windows.
SHARPE_MODEL_CODE = "perf.sharpe"
SHARPE_MODEL_NAME = "Sharpe ratio over the governed return series (excess/sigma-excess, v1)"
SHARPE_MODEL_TYPE = "SHARPE"
SHARPE_VERSION_LABEL = "v1"
SHARPE_METHODOLOGY_REF = "05_analytics_methodologies/sharpe_v1.md"

#: The registered window set — the same domain RM-1 declares, reused rather than re-argued.
SHARPE_WINDOWS: tuple[int, ...] = (12, 36)

SHARPE_ASSUMPTIONS: tuple[str, ...] = (
    "CONSTRUCTION: SHARPE (1994)'s DIFFERENTIAL-RETURN form - SR = mean(d)/sigma(d) over the "
    "trailing window, where d_j = m_j - r_f,j on the relinked CALENDAR-MONTH grid. The denominator "
    "is the standard deviation of the EXCESS series, NOT of the portfolio series. Sharpe (1966) "
    "divided by sigma of the TOTAL return series; that earlier form is NOT what this model "
    "computes, and reusing RM-1's persisted ROLLING_VOLATILITY rows as the denominator would "
    "silently implement it (the two coincide only when r_f is constant across the window). If the "
    "1966 form is ever wanted it is a SECOND declared metric, never a substitution.",
    "DIVISOR - A DISCLOSED DIVERGENCE FROM THE NAMED PAPER. Sharpe (1994)'s own endnote 1 uses the "
    "POPULATION standard deviation (divisor T). This model uses the platform's uniform n-1 sample "
    "standard deviation, which makes sigma larger by sqrt(12/11) = about +4.4% at n = 12 and the "
    "ratio correspondingly about 4.3% SMALLER. That is above this platform's own materiality bar, "
    "so it is stated here rather than absorbed into the paper's name: the construction is "
    "'Sharpe (1994)'s differential-return form with OUR n-1 divisor', following the shared "
    "stats_kernel estimator and GIPS practice (GIPS does not prescribe n vs n-1).",
    "QUANTIZATION: the mean and sigma of the excess series are accumulated UNQUANTIZED at 50 "
    "digits, the division performed at that precision, and only the RATIO quantized once to 12dp. "
    "Dividing the quantized operands instead was executed and refuted: a NON-constant excess "
    "series can quantize to sigma = 0E-12 and raise DivisionByZero on a legal input. The "
    "SUPPRESSION predicate names the SAME unquantized sigma, so the predicate and the arithmetic "
    "cannot disagree - a row is suppressed iff the excess series is genuinely CONSTANT.",
    "ANNUALIZATION: SR_ann = SR_STORED x sqrt(12), the iid scaling law, computed from the STORED "
    "12dp ratio so the emitted pair reconciles EXACTLY. Grounded by Lo (2002) SR(q) = sqrt(q)SR(1) "
    "AND by Sharpe (1994) eqs. 7/8 (mean scales with T, sigma with sqrt(T) under zero serial "
    "correlation). Under AUTOCORRELATION this MISSTATES; Lo Eq. 20 gives the correction, exact "
    "only on log returns, and is a recorded v2. sqrt(12) is carried as a DECLARED CONVENTION, not "
    "as a claim that these books are iid - this platform's own desmoothing slices exist because "
    "they are not. BOTH metrics are emitted at EVERY computable window INCLUDING W = 12: unlike "
    "RM-1's geometric return annualization, whose exponent is exactly 1 at W = 12, sqrt(12) x SR "
    "differs from SR at every window.",
    "WINDOW DOMAIN: the registered windows are {12, 36} MONTHS, and that set is part of this "
    "version's IDENTITY, not a caller convenience. A governed run may present ONLY a declared "
    "window - enforced PRE-CREATE, so a run outside the domain never reaches a result row. "
    "Twelve months is the floor for the reason RM-1 carries it: GIPS 2.A.12 forbids "
    "annualizing a period of less than one year, and the x sqrt(12) operator is an "
    "annualization. Adding a window is a NEW version label, never a silent widening.",
    "RISK-FREE LEG: a CAPTURED vendor-published monthly return series carried as an ordinary "
    "benchmark head (ENT-052), joined to the portfolio months by MONTH KEY (year, month) - never "
    "by date, so a last-business-day book and a calendar-month-end vendor align without either "
    "side bending its dates. EXACTLY ONE current-head rf return per MEASURED month is required: a "
    "missing month is a pre-create REFUSAL naming the month and more than one is a refusal too. "
    "There is NO imputation and no carry-forward. This is deliberately ASYMMETRIC with the "
    "per-window suppression convention: window-insufficiency is structural and time fills it, "
    "while a missing rf month is a CAPTURE GAP an operator must fix, and computing 'the windows we "
    "can' would ship a partially-poisoned surface whose gaps are invisible on the read side.",
    "PRECONDITION: every monthly return must satisfy 1 + m > 0. This is POLICY, not domain "
    "necessity - the Sharpe arithmetic computes cleanly at -100% and even -150% (there is no "
    "wealth index and no geometric exponent here). The grounds are that the monthly series is "
    "SHARED SUBSTRATE with RM-1: a book RM-1 refuses to carry a drawdown for must not quietly "
    "carry a Sharpe ratio, and a month at or below -100% means the PM-1 series itself is "
    "degenerate (the no-cash-ledger pathology).",
)

SHARPE_LIMITATIONS: tuple[str, ...] = (
    "THE RATIO IS UNBOUNDED on admitted inputs. Twelve column-legal monthly returns can yield a "
    "Sharpe ratio of 1E10 - past both the Numeric(20,12) column and the house 1E7 envelope - so a "
    "magnitude gate applies to the EMITTED value of every row INCLUDING the annualized member of "
    "the pair: an SR of 9E6 passes the gate while 9E6 x sqrt(12) = 3.12E7 does not. That pair "
    "breaches the HOUSE 1E7 envelope, NOT the Numeric(20,12) column, which admits values below "
    "1E8 - the gate is a declared policy ceiling, not an overflow guard, and earlier drafts of "
    "this text said overflows, which was arithmetically wrong. A breach is a COMMITTED "
    "FAILED run with DQ evidence and zero rows, never a partial emit.",
    "ROLLING VALUES ARE NOT INDEPENDENT. Adjacent 12-month windows share 11 of 12 observations, so "
    "a change between consecutive windows reflects the single entering and exiting month, not a "
    "re-estimate. Inherited from RM-1's grid and equally the most likely misreading here.",
    "GIPS 2020 does NOT require or define a Sharpe ratio. Presented, it is an 'additional risk "
    "measure': 4.C.43.a (describe it) and 4.C.44 (gross/net) apply. Rows are GROSS-of-fees, "
    "inherited from PM-1, and say so rather than inferring it. NO benchmark-relative variant "
    "(the information ratio is P3-8's, on a different grain), no Sortino, no Treynor, no "
    "downside-deviation denominator, no daily grid (k = 252 is uncited here).",
    "THE RISK-FREE SERIES IS A CAPTURE, and its quality bounds the number. v1 takes vendor-"
    "published RETURNS only; a source publishing index LEVELS cannot be used, because level -> "
    "return conversion is a registered-model exercise this slice deliberately refuses to smuggle "
    "in (ENT-052's twice-ratified never-derive-from-levels constraint). A yield curve (ENT-021) "
    "would additionally need a registered yield -> period-return model; recorded, costed, and not "
    "taken in v1. validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator "
    "records an outcome (VW-1).",
)


def register_sharpe_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the Sharpe ``model`` + a ``model_version`` for this ``code_version``
    identity (SR-1, OD-SR-1-E). RM-1's ``ROLLING_RISK_ASSUMPTIONS`` is deliberately NOT edited to
    mention SR-1 — ``resolve_or_register_version`` returns an existing version UNTOUCHED on a SELECT
    hit, so amending a shipped tuple would leave tenants registered before the change carrying
    DIFFERENT assumption text under the same ``v1`` label (silent, un-audited divergence)."""
    return _register_perf_model(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=SHARPE_MODEL_CODE,
        model_name=SHARPE_MODEL_NAME,
        model_type=SHARPE_MODEL_TYPE,
        version_label=SHARPE_VERSION_LABEL,
        methodology_ref=SHARPE_METHODOLOGY_REF,
        description=(
            "Trailing-window Sharpe ratio over the governed portfolio-return series against a "
            "captured risk-free return series, on a relinked calendar-month grid (SR-1, ENT-065)."
        ),
        assumptions=SHARPE_ASSUMPTIONS,
        limitations=SHARPE_LIMITATIONS,
    )


# --------------------------------------------------------------- CAL-1b: the v2 month-end move ---
#: The machine literals carrying the v2 convention (OQ-CAL-1-2 — the assumption-literal pattern,
#: NEVER label-parsed; perf-local constants, the peer-package split).
MONTH_END_CONVENTION_ASSUMPTION_PREFIX = "month_end_convention="
HOLIDAY_CALENDAR_ASSUMPTION_PREFIX = "holiday_calendar="
#: The implicit v1 grandfather (absent literal) and the sole recognized v2 convention.
MONTH_END_WEEKEND_CONVENTION = "WEEKEND"
MONTH_END_BUSINESS_CONVENTION = "BUSINESS"
ROLLING_RISK_V2_VERSION_LABEL = "v2"
SHARPE_V2_VERSION_LABEL = "v2"
#: The default holiday calendar the v2 registrars declare (the SYSTEM XNYS seed).
DEFAULT_HOLIDAY_CALENDAR_CODE = "XNYS"
_HOLIDAY_CALENDAR_CODE_PATTERN = re.compile(r"[A-Z0-9_\-]{1,50}")


@dataclass(frozen=True)
class MonthEndParameters:
    """The version's declared month-end convention identity (CAL-1b, OQ-CAL-1-2).
    ``convention`` is WEEKEND (the implicit v1 grandfather — absent literal) or BUSINESS;
    ``holiday_calendar`` is the declared calendar CODE, present for BUSINESS only."""

    convention: str
    holiday_calendar: str | None


def declared_month_end_parameters(
    session: Session, version: ModelVersion, *, model_code: str
) -> MonthEndParameters:
    """Parse the version's declared month-end convention (CAL-1b) with the precedent's full
    discipline (DS-2/RS-1): ABSENT ``month_end_convention`` (zero rows) => the implicit WEEKEND
    v1 grandfather, on which a stray ``holiday_calendar=`` literal is a lying identity and
    refuses; AMBIGUOUS (>1 convention row) refuses — never collapsed into the grandfather; a
    present convention must be the recognized BUSINESS literal WITH a well-formed
    ``holiday_calendar=`` companion. Malformed -> the fail-closed
    :class:`WrongModelVersionError`."""
    texts = load_assumption_texts(session, version)
    convention_rows = [t for t in texts if t.startswith(MONTH_END_CONVENTION_ASSUMPTION_PREFIX)]

    def _fail() -> WrongModelVersionError:
        return WrongModelVersionError(str(version.id), model_code)

    if len(convention_rows) > 1:
        raise _fail()
    has_calendar = any(t.startswith(HOLIDAY_CALENDAR_ASSUMPTION_PREFIX) for t in texts)
    if not convention_rows:
        if has_calendar:  # a stray calendar literal on a weekend-convention version lies
            raise _fail()
        return MonthEndParameters(MONTH_END_WEEKEND_CONVENTION, None)
    convention = convention_rows[0][len(MONTH_END_CONVENTION_ASSUMPTION_PREFIX) :]
    if convention != MONTH_END_BUSINESS_CONVENTION:
        raise _fail()
    calendar_code = require_declared(
        texts,
        HOLIDAY_CALENDAR_ASSUMPTION_PREFIX,
        pattern=_HOLIDAY_CALENDAR_CODE_PATTERN,
        on_invalid=_fail,
    )
    return MonthEndParameters(MONTH_END_BUSINESS_CONVENTION, calendar_code)


#: The v2 additions to the v1 tuples. The v1 tuples are NEVER edited (the G21 no-edit rule) —
#: v2 is a NEW label with NEW assumption rows; the shipped v1 rows stay byte-identical.
_MONTH_END_V2_ASSUMPTION = (
    "MONTH-END CONVENTION (v2): HOLIDAY-AWARE. The acceptance grid WIDENS the v1 predicate - the "
    "calendar month end, the last WEEKDAY, or the last BUSINESS day under the declared holiday "
    "calendar (the QS-11 'preceding' rolling convention: a month-end landing on a weekend OR a "
    "market holiday rolls BACK to the preceding business day). Widening, never substitution: "
    "every v1-compliant book stays compliant under v2 (GIPS 2.A.23.b's 'last business day' arm, "
    "now honored holiday-aware). The holiday set the run used is PINNED into the run's input "
    "snapshot as a HOLIDAY_CALENDAR component (AD-014: the compute reads only pinned content), "
    "so every v2 reading reproduces bit-exactly from its own bindings."
)
_MONTH_END_V2_LIMITATION = (
    "THE HOLIDAY SET IS REFERENCE DATA, AND ITS COVERAGE BOUNDS THE GRID. A span beyond the "
    "calendar's DECLARED holidays_complete_through refuses pre-create (fail-closed - an "
    "uncovered month must never silently degrade to the weekend-only answer). The calendar is "
    "EV-mutable: an ADD-ONLY refresh that inserts a past-dated holiday inside an already-pinned "
    "span does not change any shipped reading (the pin is the input), but verify_snapshot "
    "honestly reports the drift and the refresh itself is audited with its full date diff."
)

ROLLING_RISK_V2_ASSUMPTIONS: tuple[str, ...] = (
    _MONTH_END_V2_ASSUMPTION,
    *ROLLING_RISK_ASSUMPTIONS,
)
ROLLING_RISK_V2_LIMITATIONS: tuple[str, ...] = (
    _MONTH_END_V2_LIMITATION,
    *(
        item
        for item in ROLLING_RISK_LIMITATIONS
        if not item.startswith("MONTH-END CONVENTION IS HOLIDAY-FREE")
    ),
)
SHARPE_V2_ASSUMPTIONS: tuple[str, ...] = (
    _MONTH_END_V2_ASSUMPTION,
    *SHARPE_ASSUMPTIONS,
)
SHARPE_V2_LIMITATIONS: tuple[str, ...] = (
    _MONTH_END_V2_LIMITATION,
    *SHARPE_LIMITATIONS,
)


def _register_perf_model_v2(
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
    holiday_calendar: str,
) -> ModelVersion:
    """The shared v2 mint: delegate to ``_register_perf_model`` with the convention literals
    REGISTRAR-STAMPED into the tuple, then RE-PARSE the declared parameters as the idempotent
    conflict check (the DS-2 discipline — ``_register_perf_model``'s own post-check verifies
    code_version only, so a squatted same-label peer with DIFFERENT literals would pass it)."""
    if not _HOLIDAY_CALENDAR_CODE_PATTERN.fullmatch(str(holiday_calendar)):
        raise ValueError(f"holiday_calendar code {holiday_calendar!r} is not a valid calendar code")
    version = _register_perf_model(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=model_code,
        model_name=model_name,
        model_type=model_type,
        version_label=version_label,
        methodology_ref=methodology_ref,
        description=description,
        assumptions=(
            *assumptions,
            f"{MONTH_END_CONVENTION_ASSUMPTION_PREFIX}{MONTH_END_BUSINESS_CONVENTION}",
            f"{HOLIDAY_CALENDAR_ASSUMPTION_PREFIX}{holiday_calendar}",
        ),
        limitations=limitations,
    )
    declared = declared_month_end_parameters(session, version, model_code=model_code)
    if declared.convention != MONTH_END_BUSINESS_CONVENTION or declared.holiday_calendar != str(
        holiday_calendar
    ):
        raise ModelVersionConflictError(
            model_code,
            version_label,
            f"{code_version} (month_end_convention={MONTH_END_BUSINESS_CONVENTION}, "
            f"holiday_calendar={holiday_calendar})",
        )
    return version


def register_rolling_risk_model_v2(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    holiday_calendar: str = DEFAULT_HOLIDAY_CALENDAR_CODE,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the HOLIDAY-AWARE rolling-risk version — a NEW ``v2`` label on the
    SAME ``perf.rolling_risk`` code (OQ-CAL-1-2; the RS-1/DS-2 grandfather pattern). The v1
    registrar and its tuples are untouched; v1 keeps binding new runs until its callers repoint
    (nothing retires it automatically — G24)."""
    return _register_perf_model_v2(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=ROLLING_RISK_MODEL_CODE,
        model_name=ROLLING_RISK_MODEL_NAME,
        model_type=ROLLING_RISK_MODEL_TYPE,
        version_label=ROLLING_RISK_V2_VERSION_LABEL,
        methodology_ref=ROLLING_RISK_METHODOLOGY_REF,
        description=(
            "Trailing-window rolling return, rolling volatility and maximum drawdown over the "
            "governed portfolio-return series, on a relinked HOLIDAY-AWARE calendar-month grid "
            "(CAL-1b v2 of RM-1/ENT-064)."
        ),
        assumptions=ROLLING_RISK_V2_ASSUMPTIONS,
        limitations=ROLLING_RISK_V2_LIMITATIONS,
        holiday_calendar=holiday_calendar,
    )


def register_sharpe_model_v2(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    holiday_calendar: str = DEFAULT_HOLIDAY_CALENDAR_CODE,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the HOLIDAY-AWARE Sharpe version — a NEW ``v2`` label on the SAME
    ``perf.sharpe`` code. SR-1 moves in LOCKSTEP with RM-1 (OQ-CAL-1-2): its rf month-key join is
    numerically insulated from month-end DATE moves, but its grid text inherits RM-1's, so the
    registered identity moves too."""
    return _register_perf_model_v2(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        code_version=code_version,
        actor_type=actor_type,
        model_code=SHARPE_MODEL_CODE,
        model_name=SHARPE_MODEL_NAME,
        model_type=SHARPE_MODEL_TYPE,
        version_label=SHARPE_V2_VERSION_LABEL,
        methodology_ref=SHARPE_METHODOLOGY_REF,
        description=(
            "Trailing-window Sharpe ratio over the governed portfolio-return series against a "
            "captured risk-free return series, on a relinked HOLIDAY-AWARE calendar-month grid "
            "(CAL-1b v2 of SR-1/ENT-065)."
        ),
        assumptions=SHARPE_V2_ASSUMPTIONS,
        limitations=SHARPE_V2_LIMITATIONS,
        holiday_calendar=holiday_calendar,
    )
