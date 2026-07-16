"""The MG-1 campaign dossier map (plan Step 5.5, ratified verbatim via OQ-MG-1-6).

The runner (``campaign.py``) only TRANSCRIBES this module: the user's OQ-6 ratification of the
Step-5.5 table IS the human validation judgment (BR-15 honored in substance; the seeded 2L
principal names the user, Claude is the scribe). Per model: the DUAL ratings behind the derived
tier + the assignment rationale (OD-MG-1-A/B), and for the six flagship codes the INITIAL-
validation outcome, conditions and the finding KEYS — substrings resolved at runtime against the
model's OWN REGISTERED ``model_limitation`` rows (findings are drawn from the registry, never
invented; a key that no longer matches a registered row fails the campaign loudly).

Every record's text carries the person-level non-independence disclosure (decision record Part 3
item 1) — the flagship conditions carry the CURRENCY-only condition whose remediation IS FL-1/MF-1
(the ratified flywheel: the MF-1 TRIGGERED re-validation greps for 'FL-1' and closes it).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Decision record Part 3 item 1, transcribed into every campaign record (validations AND
#: exceptions) via ``scope_summary``. Both halves of the SR 26-2 tension are named (the verifier's
#: fold): the rigor-over-structure sentence AND the effective-challenge independence sentence.
NON_INDEPENDENCE_DISCLOSURE = (
    "PERSON-LEVEL INDEPENDENCE DISCLOSURE (MG-1 Part 3 item 1): this record is one human's "
    "judgment wearing the 2L hat. Role-level SOD-03 holds (the validating principal holds "
    "model.validate only; the 1L registrar holds no validation verb), but person-level "
    "independence does not exist in this proof of concept. Anchored honestly on SR 26-2 — 'The "
    "quality of validation process depends on the rigor and effectiveness of the review rather "
    "than on organizational structure of the banking organization's risk management function' — "
    "engaged beside SR 26-2's own effective-challenge requirement of sufficient independence to "
    "maintain objectivity (the disclosed tension, not dodged); SS1/23 P4.1(d) (separate reporting "
    "lines) is not applicable by scope and is never claimed as satisfied. The challenge behind "
    "this record is the adversarial review machinery plus the user's OQ-MG-1-6 ratification of "
    "the dossier map this record transcribes."
)

#: The SR 26-2 §V / SS1/23 P5.3(a)(i) exception shape, shared by all ten EXCEPTION records. The
#: PMA limb is explicitly NOT adopted (OD-MG-1-E — the record's own disclosure standard applied
#: to itself). Deliberately does NOT contain the token 'FL-1': the MF-1 TRIGGERED re-validation
#: greps conditions for that token to find the FIVE flagship AWC conditions, nothing else.
EXCEPTION_CONDITIONS = (
    "USE-BEFORE-VALIDATION EXCEPTION (SR 26-2 SectionV elements; SS1/23 P5.3(a)(i) 'temporary' + "
    "Section2.13 grant semantics — an act of the 2L control function). JUSTIFICATION: POC "
    "sequencing — the Wave-6 governance-first slice validates the six flagship codes first; this "
    "model is registered, tiered, and time-boxed pending its own INITIAL validation. CONTROLS "
    "(the SR 26-2 SectionV limits-on-use / closer-monitoring elements): (i) use is limited to the "
    "demo-campaign tenant; (ii) the version's REGISTERED limitations remain in force — the "
    "limitations-attention finding on this record cites them from the registry; (iii) closer "
    "monitoring: backtest monitoring where the family is backtestable, run-level review "
    "otherwise; (iv) expiry = next_review_due (the tier-bounded ceiling, OD-MG-1-D) — after it, "
    "new binds refuse at the shared seam until a FRESH exception is granted or a real validation "
    "is recorded. NOT ADOPTED (disclosed): the SS1/23 P5.3(a)(i) post-model-adjustment limb — "
    "the platform has no PMA/overlay machinery of any kind; the limb is disclosed as "
    "not-implemented rather than silently dropped."
)


@dataclass(frozen=True)
class TierDossier:
    """One model's ratified dual ratings + the per-model assignment rationale (OD-MG-1-A/B)."""

    materiality_rating: str
    complexity_rating: str
    rationale: str


#: All 16 registered codes -> the ratified ratings (plan Step 5.5; the derived tier follows from
#: ``derive_model_tier``). Materiality = SR 26-2 exposure + purpose ONLY; complexity = the
#: separate inherent-risk axis (SS1/23 P1.3(c)).
TIER_DOSSIERS: dict[str, TierDossier] = {
    "risk.var.parametric": TierDossier(
        "HIGH",
        "MEDIUM",
        "Flagship 1-day portfolio VaR: the platform's primary risk read over the whole governed "
        "book (exposure + purpose = HIGH materiality); closed-form zero-mean delta-normal "
        "arithmetic over a governed covariance (MEDIUM complexity).",
    ),
    "risk.var.historical": TierDossier(
        "HIGH",
        "MEDIUM",
        "Flagship non-parametric VaR on the same book and purpose as the parametric family (HIGH "
        "materiality); empirical order-statistic estimator with a declared window and adequacy "
        "floor (MEDIUM complexity).",
    ),
    "risk.var.parametric_total": TierDossier(
        "HIGH",
        "HIGH",
        "Flagship total VaR: the same exposure and purpose as the plain family (HIGH "
        "materiality) PLUS a multi-stage estimation chain — desmoothed appraisal returns, an OLS "
        "residual estimate, a declared frequency conversion, and a staleness gate (HIGH "
        "complexity).",
    ),
    "risk.var.parametric_es": TierDossier(
        "HIGH",
        "MEDIUM",
        "Flagship tail-severity number on the flagship book and purpose (HIGH materiality); a "
        "registered multiplier over the parametric sigma — the sigma's complexity, one declared "
        "constant more (MEDIUM complexity).",
    ),
    "risk.var.parametric_es_total": TierDossier(
        "HIGH",
        "HIGH",
        "Flagship total-ES: the ES multiplier over the TOTAL sigma, inheriting the total "
        "family's estimation chain (residual estimate, frequency conversion, staleness gate) "
        "verbatim (HIGH materiality, HIGH complexity).",
    ),
    "risk.var_backtest": TierDossier(
        "MEDIUM",
        "MEDIUM",
        "Outcomes-analysis machinery: it gates no capital and prices no book (MEDIUM "
        "materiality — its purpose is evidence about OTHER models), with a two-sided asymptotic "
        "coverage test and a domain-gated zone table (MEDIUM complexity).",
    ),
    "risk.covariance.sample": TierDossier(
        "MEDIUM",
        "MEDIUM",
        "The variance substrate every parametric risk number consumes (MEDIUM materiality "
        "through its consumers); equal-weighted unbiased sample estimator, PSD by construction "
        "(MEDIUM complexity).",
    ),
    "risk.factor_exposure.allocation": TierDossier(
        "MEDIUM",
        "LOW",
        "The x-vector feeding every factor-model number (MEDIUM materiality through its "
        "consumers); indicator (membership) loadings with an exact partition identity (LOW "
        "complexity).",
    ),
    "risk.factor_exposure.proxy": TierDossier(
        "MEDIUM",
        "MEDIUM",
        "The private-asset projection of the exposure vector (MEDIUM materiality — it moves the "
        "book's factor picture where marks are appraisal-based); captured-weight replacement "
        "allocation with a pinned-mapping citation chain (MEDIUM complexity).",
    ),
    "risk.sensitivity.analytic": TierDossier(
        "LOW",
        "LOW",
        "Curve-intrinsic DV01/spread-DV01 at captured nodes only — not instrument-attributed, "
        "not consumed by any downstream governed number (LOW materiality); closed-form "
        "single-bump arithmetic (LOW complexity).",
    ),
    "risk.active_risk.parametric": TierDossier(
        "MEDIUM",
        "MEDIUM",
        "Ex-ante tracking error for benchmark-relative oversight (MEDIUM materiality — a "
        "monitoring number, not the flagship book-risk read); the VaR quadratic form over active "
        "weights with benchmark normalization (MEDIUM complexity).",
    ),
    "risk.scenario.factor_shock": TierDossier(
        "LOW",
        "LOW",
        "Deterministic linear what-if P&L over declared shocks (LOW materiality — illustrative, "
        "no distributional claim); first-order multiply-and-sum (LOW complexity).",
    ),
    "risk.proxy_weight.regression": TierDossier(
        "MEDIUM",
        "HIGH",
        "The estimation model behind promoted proxy weights and the total-VaR residual (MEDIUM "
        "materiality through promotion); OLS on a MODEL-OUTPUT target (the desmoothed series) "
        "with short appraisal samples and wide standard errors (HIGH complexity — an estimated "
        "model feeding a model).",
    ),
    "perf.return.twr": TierDossier(
        "MEDIUM",
        "LOW",
        "The governed portfolio-return series: the realized-P&L leg of every backtest (MEDIUM "
        "materiality — evidence substrate); chain-linked Modified Dietz within caller-supplied "
        "boundaries (LOW complexity).",
    ),
    "perf.benchmark_relative": TierDossier(
        "LOW",
        "LOW",
        "Ex-post active return/TE/IR reporting over a return run and a captured benchmark "
        "series (LOW materiality — descriptive reporting, no downstream consumer); arithmetic "
        "differences and a sample stdev (LOW complexity).",
    ),
    "perf.return.desmoothed_geltner": TierDossier(
        "MEDIUM",
        "HIGH",
        "The appraisal-unsmoothing model whose output is the PA-3 regression target (MEDIUM "
        "materiality — it shapes the private leg's estimated risk); an AR(1) inverse filter with "
        "a DECLARED alpha whose misspecification propagates invisibly into every downstream "
        "estimate (HIGH complexity).",
    ),
}

#: The six flagship codes (OD-MG-1-G), in the dossier-map order.
FLAGSHIP_CODES: tuple[str, ...] = (
    "risk.var.parametric",
    "risk.var.historical",
    "risk.var.parametric_total",
    "risk.var.parametric_es",
    "risk.var.parametric_es_total",
    "risk.var_backtest",
)

#: The shared flagship condition core — the CURRENCY-only condition whose remediation IS FL-1/MF-1
#: (the ratified flywheel hook; the MF-1 TRIGGERED re-validation greps for 'FL-1').
_CURRENCY_CONDITION = (
    "CONDITION (CURRENCY-only factor universe): the factor universe is the CURRENCY family only "
    "and specific/idiosyncratic factor risk = 0 — portfolio risk outside currency factors is "
    "invisible to this number; the campaign book's large equity-move day illustrates exactly the "
    "risk this condition names. REMEDIATION = FL-1/MF-1 (multi-family factor capture): this "
    "condition closes at the MF-1 TRIGGERED re-validation."
)

#: A fixture-honesty disclosure appended to every flagship scope_note that describes a forecast
#: SERIES (MG-1 impl-review, campaign-content finder): the demo's factor-return cycles repeat
#: within the covariance/HS windows, so the 8 daily forecasts are IDENTICAL — the series is
#: constant by fixture construction. It is a real, coherent backtest (a constant forecast against
#: a varying realized-return series), NOT an evolving volatility path; the point of this demo is
#: the governance workflow, and the market-realistic path is FL-1/MF-1 territory.
_CONSTANT_SERIES_NOTE = (
    " NOTE (fixture): the 8 daily forecasts are IDENTICAL — the demo factor-return cycle repeats "
    "within the covariance/HS window, so the series is constant by construction (a real backtest "
    "of a constant forecast against a varying realized-return series, not an evolving vol path; "
    "the multi-family realistic path is FL-1/MF-1)."
)


@dataclass(frozen=True)
class FlagshipDossier:
    """One flagship code's ratified INITIAL-validation content (plan Step 5.5, transcribed)."""

    outcome: str
    scope_note: str
    conditions: str | None
    #: Substring keys resolved against the version's REGISTERED ``model_limitation`` rows —
    #: each key must match exactly one registered row (fail-loud), whose text becomes the finding.
    finding_keys: tuple[str, ...]


FLAGSHIP_DOSSIERS: dict[str, FlagshipDossier] = {
    "risk.var.parametric": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "INITIAL validation of the flagship parametric VaR (0.99, 1-day) over the demo "
            "campaign book: an 8-point consecutive daily forecast series and a REAL BT-1 "
            "backtest over the governed realized-return series (N=8 one-day pairs; Kupiec POF "
            "emitted at N=8, the Basel zone correctly absent off its (0.99, 250) domain — the "
            "series length is stated, nothing pretends to 250 days). Conceptual soundness rests "
            "on the registered assumptions; the registered limitations are re-attached as "
            "findings, not repeated as prose." + _CONSTANT_SERIES_NOTE
        ),
        conditions=(
            _CURRENCY_CONDITION
            + " ACCEPTED POSTURE (recorded as findings, not conditions): joint normality of "
            "factor returns and the 1-day-only horizon."
        ),
        finding_keys=(
            "SPECIFIC/IDIOSYNCRATIC RISK = 0",
            "Joint normality of factor returns",
            "1-day horizon only",
        ),
    ),
    "risk.var.historical": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "INITIAL validation of the flagship historical-simulation VaR (0.95, 1-day, "
            "window=21) over the demo campaign book: an 8-point consecutive daily forecast "
            "series over the same governed exposure substrate as the parametric family "
            "(evidence = this model's OWN runs). The window-adequacy floor (N=21 at 0.95) is "
            "noted as GOVERNED — a declared-identity statistical minimum, not a sufficiency "
            "guarantee." + _CONSTANT_SERIES_NOTE
        ),
        conditions=(
            _CURRENCY_CONDITION
            + " The window-adequacy floor is noted as governed: N=21 at 0.95 is the declared "
            "identity's statistical minimum (k >= 2), not a sufficiency guarantee."
        ),
        finding_keys=(
            "SPECIFIC/IDIOSYNCRATIC RISK = 0",
            "worst scenario IN the window",
            "Equal weighting reacts SLOWLY",
        ),
    ),
    "risk.var.parametric_total": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "INITIAL validation of the flagship TOTAL parametric VaR v2 (0.99, 1-day, "
            "appraisal_days=91, max_estimate_age_days=400) over the demo campaign book: an "
            "8-point consecutive daily forecast series whose residual leg consumes a REAL "
            "promoted PA-3 estimate (real appraisal marks -> desmoothing -> OLS -> promotion), "
            "and a REAL BT-2 backtest over the total series (N=8 one-day pairs; series length "
            "stated). The staleness gate was exercised live: every window_end sat within the "
            "declared 400-day bound of the estimate's span end." + _CONSTANT_SERIES_NOTE
        ),
        conditions=(
            _CURRENCY_CONDITION
            + " BT-2 SMOOTHING-DOCTRINE READ RULE RE-AFFIRMED: on an appraisal-marked book the "
            "unconditional Kupiec/Basel verdict over a 1-day total series is NOT valid adequacy "
            "evidence in either direction (exceptions suppressed between marks, clustered on "
            "mark dates); the dated per-pair EXCEPTION_INDICATOR rows are the honest evidence "
            "surface. The v1 UNGATED GRANDFATHER is NOTED: a pre-BT-2 risk.var.parametric_total "
            "v1 registration binds without the staleness declaration; its sunset lever is a "
            "VW-1 REJECT recorded on the v1 model_version."
        ),
        finding_keys=(
            "DIAGONAL residuals only",
            "hostage to the PA-3 estimate quality",
            "ZERO idiosyncratic risk",
        ),
    ),
    "risk.var.parametric_es": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "INITIAL validation of the flagship parametric Expected Shortfall (0.975, 1-day) "
            "over the demo campaign book: a registered-multiplier tail-severity number over the "
            "SAME governed sigma as the parametric VaR family (evidence = this model's OWN run). "
            "A sigma-multiple is exactly as honest as its sigma, so the parametric family's "
            "condition rides verbatim."
        ),
        conditions=(
            _CURRENCY_CONDITION
            + " This condition RIDES THE PARAMETRIC FAMILY'S VERBATIM — ES_c = k_c * sigma_p is "
            "a fixed multiple of the same sigma (a sigma-multiple is as honest as its sigma). "
            "The non-reconciling-row limitation is cited as a finding: an ES row reproduces "
            "through its bound model_version's declared es_multiplier, never from the row alone."
        ),
        finding_keys=(
            "it inherits",
            "does NOT reconcile against its own columns",
        ),
    ),
    "risk.var.parametric_es_total": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "INITIAL validation of the flagship TOTAL parametric Expected Shortfall (0.975, "
            "1-day, appraisal_days=91, max_estimate_age_days=400) over the demo campaign book: "
            "the registered ES multiplier over the TOTAL sigma, consuming the same REAL promoted "
            "PA-3 residual estimate as the total-VaR family (evidence = this model's OWN run). "
            "The staleness declaration is REQUIRED on this family from birth — no grandfathered "
            "ungated version can exist."
        ),
        conditions=(
            _CURRENCY_CONDITION
            + " THE TOTAL CONDITION VERBATIM: the BT-2 smoothing-doctrine read rule carries over "
            "unchanged — a sigma-multiple is exactly as honest as its sigma, and on an "
            "appraisal-marked book the 1-day total sigma is biased two ways by construction. "
            "PLUS THE ES RIDER: the ES row reproduces through its bound model_version's declared "
            "es_multiplier (the non-reconciling-row limitation), never from the row alone."
        ),
        finding_keys=(
            "The residual leg is PA-4's verbatim",
            "BT-2's smoothing doctrine carries over UNCHANGED",
            "does NOT reconcile against its own columns",
        ),
    ),
    "risk.var_backtest": FlagshipDossier(
        outcome="APPROVED",
        scope_note=(
            "INITIAL validation of the VaR-backtesting model (Kupiec POF at alpha=0.05; Basel "
            "zone domain-gated) — evidence = its OWN executed runs: the REAL BT-1 run over the "
            "plain parametric series and the REAL BT-2 run over the total series (N=8 one-day "
            "pairs each; the Basel zone is correctly ABSENT off its (0.99, 250) domain and its "
            "absence is the correct behavior, not a gap). The doctrine limitations re-attached "
            "as findings (the two-sided appraisal pathology and the BT-2 read rule) are the "
            "model's OWN honesty text about what its outputs may be read to mean — they are not "
            "defects in the model, which is why the outcome is APPROVED, not conditioned."
        ),
        conditions=None,
        finding_keys=(
            "TOTAL-SERIES READ VALIDITY",
            "READ RULE (BT-2)",
            "Small-N honesty",
        ),
    ),
}
