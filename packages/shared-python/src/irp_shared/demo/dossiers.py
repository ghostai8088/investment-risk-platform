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


# =====================================================================================
# The MF-1 dossier section (mf_1_decision_record.md OD-MF-1-D, ratified via OQ-MF-1-3).
# The extension runner (``multifamily.py``) only TRANSCRIBES this section — the user's OQ-3
# ratification IS the human validation judgment (the MG-1 precedent). NO text below contains
# the token 'FL-1' (the OQ-MF-1-6 grep discipline: post-extension, a tenant-wide conditions
# grep finds that token in exactly the 5 HISTORICAL flagship AWC rows).
# =====================================================================================

#: The MF-1 records' independence disclosure — the MG-1 constant with ONLY the final clause
#: re-pointed at the ratification these records actually rest on (the doctrine finder's HIGH:
#: an MF-1 record citing OQ-MG-1-6 would misstate its own judgment's provenance; the MG-1
#: constant stays byte-untouched for the campaign's filed rows).
MF1_NON_INDEPENDENCE_DISCLOSURE = NON_INDEPENDENCE_DISCLOSURE.replace(
    "the user's OQ-MG-1-6 ratification of the dossier map this record transcribes",
    "the user's OQ-MF-1-3 ratification of the MF-1 dossier section "
    "(mf_1_decision_record.md) this record transcribes",
)
assert MF1_NON_INDEPENDENCE_DISCLOSURE != NON_INDEPENDENCE_DISCLOSURE  # the replace must bite

#: The loadings family's ratified dual ratings (OD-MF-1-B; MEDIUM x MEDIUM => TIER_2 — the
#: covariance precedent: substrate materiality through consumers).
MF1_LOADINGS_TIER = TierDossier(
    "MEDIUM",
    "MEDIUM",
    "The multi-family exposure substrate: it shapes the x-vector its VaR/ES consumers read "
    "(MEDIUM materiality through its consumers, the covariance precedent); a fractional signed "
    "projection over promoted REGRESSION loadings — arithmetic is multiply-and-quantize, the "
    "estimation risk lives in the upstream regression model (MEDIUM complexity).",
)

#: The closure statement prepended (as a finding) to every TRIGGERED record — the frozen-wording
#: disclosure rides with it because the re-cited registered-limitation texts are immutable.
MF1_CLOSURE_FINDING = (
    "CLOSED (this record): the CURRENCY-only factor-universe condition recorded at the INITIAL "
    "validation is closed by the multi-family remediation (MF-1) — the demo tenant's factor "
    "universe now includes governed MARKET/RATES/CREDIT_SPREAD factors with REGRESSION-estimated "
    "loadings, and the cited run is this model's own COMPLETED multi-family evidence over the "
    "multi-asset sleeve. FROZEN-WORDING NOTE: the re-cited registered-limitation texts below "
    "predate the multi-family widening where filed before the HG-1 constants correction "
    "(rows registered after it carry the corrected family-neutral framing) — read any "
    "family-scoped framing as 'the bound factor set'. "
    "Closure is by supersession (latest-outcome-wins); the historical condition text remains "
    "visible, append-only."
)

#: The frequency-conversion honesty note the total/ES-total TRIGGERED records carry: the
#: demo-mg1 declared appraisal_days=91 is calibrated to the legacy quarterly-appraisal leg;
#: the sleeve's estimates are DAILY-period, so the converted daily residual is understated on
#: this evidence run — capability evidence, not residual calibration.
_MF1_FREQ_NOTE = (
    " FREQUENCY-CONVERSION NOTE (this record's evidence): the declared appraisal_days=91 "
    "residual conversion is calibrated to the quarterly-appraisal leg; applied to the "
    "multi-asset sleeve's daily-period estimates it understates the daily residual — the cited "
    "run evidences multi-family capability, not residual calibration."
)

#: The five TRIGGERED re-validations (OD-MF-1-D): conditions FRESHLY DRAFTED per model — the
#: verifier pass killed the mechanical "verbatim minus the CURRENCY clause" derivation (the
#: still-true specific-risk clause is fused into the removed sentence; three riders were
#: cross-referential). Every blob restates the surviving substance standalone.
MF1_TRIGGERED_DOSSIERS: dict[str, FlagshipDossier] = {
    "risk.var.parametric": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "TRIGGERED re-validation of the flagship parametric VaR (0.99, 1-day) — the "
            "multi-family remediation (MF-1): the cited evidence run consumes a loadings-family "
            "factor-exposure run over the multi-asset sleeve (MARKET/RATES/CREDIT_SPREAD "
            "factors, REGRESSION-estimated fractional loadings) through the SAME governed "
            "binder and covariance substrate. The CURRENCY-only condition closes; the surviving "
            "posture is restated in the conditions."
        ),
        conditions=(
            "CONDITION (specific/idiosyncratic risk = 0): the plain parametric family carries "
            "NO residual variance term — idiosyncratic risk remains invisible to this number "
            "regardless of factor universe (the total family pays a diagonal residual for "
            "REGRESSION-cited instruments; this family does not). The joint-normality and "
            "1-day-only-horizon posture recorded at the INITIAL validation continues to apply "
            "unchanged."
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
            "TRIGGERED re-validation of the flagship historical-simulation VaR (0.95, 1-day, "
            "window=21) — the multi-family remediation (MF-1): the cited evidence run samples "
            "the 21-day multi-family factor-return window over the sleeve's loadings-family "
            "exposure. The CURRENCY-only condition closes; the surviving posture is restated "
            "in the conditions."
        ),
        conditions=(
            "CONDITION (specific/idiosyncratic risk = 0): the historical-simulation family "
            "samples FACTOR returns only — idiosyncratic risk remains invisible to this number "
            "regardless of factor universe. The window-adequacy floor remains noted as "
            "governed: N=21 at 0.95 is the declared identity's statistical minimum (k >= 2), "
            "not a sufficiency guarantee."
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
            "TRIGGERED re-validation of the flagship TOTAL parametric VaR v2 (0.99, 1-day, "
            "appraisal_days=91, max_estimate_age_days=400) — the multi-family remediation "
            "(MF-1): the cited evidence run pays a REAL diagonal residual for all three sleeve "
            "instruments (each REGRESSION-promoted from its own single estimate run; estimate "
            "ages fresh, the staleness gate passed live). The CURRENCY-only condition closes; "
            "the surviving posture is restated in the conditions."
        ),
        conditions=(
            "CONDITION (partial idiosyncratic coverage): the residual leg pays a DIAGONAL "
            "idiosyncratic variance for REGRESSION-cited instruments ONLY — non-proxied and "
            "MANUAL-method atoms carry zero idiosyncratic variance, and cross-residual "
            "correlation = 0 by construction. The BT-2 SMOOTHING-DOCTRINE READ RULE stands: on "
            "an appraisal-marked book the unconditional Kupiec/Basel verdict over a 1-day total "
            "series is NOT valid adequacy evidence in either direction (exceptions suppressed "
            "between marks, clustered on mark dates); the dated per-pair EXCEPTION_INDICATOR "
            "rows are the honest evidence surface. The v1 UNGATED GRANDFATHER remains noted: a "
            "pre-BT-2 registration binds without the staleness declaration; its sunset lever is "
            "a VW-1 REJECT on the v1 model_version." + _MF1_FREQ_NOTE
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
            "TRIGGERED re-validation of the flagship parametric Expected Shortfall (0.975, "
            "1-day) — the multi-family remediation (MF-1): the cited evidence run applies the "
            "registered multiplier to the multi-family sigma (a sigma-multiple is exactly as "
            "honest as its sigma). The CURRENCY-only condition closes; the surviving posture is "
            "restated in the conditions."
        ),
        conditions=(
            "CONDITION (specific/idiosyncratic risk = 0): ES_c = k_c * sigma_p is a fixed "
            "multiple of the plain parametric sigma — that sigma carries no residual variance "
            "term, so idiosyncratic risk remains invisible to this number regardless of factor "
            "universe. The non-reconciling-row limitation stands: an ES row reproduces through "
            "its bound model_version's declared es_multiplier, never from the row alone."
        ),
        finding_keys=(
            "it inherits",
            "does NOT reconcile against its own columns",
        ),
    ),
    "risk.var.parametric_es_total": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "TRIGGERED re-validation of the flagship TOTAL parametric Expected Shortfall "
            "(0.975, 1-day, appraisal_days=91, max_estimate_age_days=400) — the multi-family "
            "remediation (MF-1): the cited evidence run applies the registered multiplier to "
            "the TOTAL multi-family sigma, consuming the same three REAL promoted sleeve "
            "estimates as the total-VaR evidence run. The CURRENCY-only condition closes; the "
            "surviving posture is restated in the conditions."
        ),
        conditions=(
            "CONDITION (partial idiosyncratic coverage + the read rule): the ES multiplier over "
            "the TOTAL sigma inherits the total family's posture standalone — diagonal "
            "residuals for REGRESSION-cited instruments only (non-proxied and MANUAL-method "
            "atoms carry zero idiosyncratic variance), and the BT-2 smoothing-doctrine read "
            "rule on appraisal-marked books (a sigma-multiple is exactly as honest as its "
            "sigma). The ES row reproduces through its bound model_version's declared "
            "es_multiplier (the non-reconciling-row limitation), never from the row alone."
            + _MF1_FREQ_NOTE
        ),
        finding_keys=(
            "The residual leg is PA-4's verbatim",
            "BT-2's smoothing doctrine carries over UNCHANGED",
            "does NOT reconcile against its own columns",
        ),
    ),
}

#: The loadings model's own INITIAL (AWC) — real evidence from its first campaign (OD-MF-1-D:
#: the dossier-table ratification is the INITIAL-vs-EXCEPTION criterion, the MG-1 precedent).
MF1_LOADINGS_INITIAL = FlagshipDossier(
    outcome="APPROVED_WITH_CONDITIONS",
    scope_note=(
        "INITIAL validation of the loadings factor-exposure family over the multi-asset sleeve "
        "(MF-1): fractional signed multi-factor loadings, REGRESSION-estimated by the k=3 "
        "Sharpe-1992 regression (each instrument on the full MARKET/RATES/CREDIT_SPREAD "
        "palette via the alpha=1 desmoothing detour, the analyst promoting the structural "
        "coefficients only) — evidence = this model's OWN loadings exposure run plus the "
        "through-VaR consumer run. DISCLOSED: the total-family residual leg consumes "
        "MV*Sum(w_f) as an instrument's market value (the per-factor exposure rows summed), so "
        "an instrument's residual scaling follows its loading sum — first material at "
        "multi-factor scale under unconstrained OLS (Sum(w) != 1)."
    ),
    conditions=(
        "CONDITION (projection residual + estimation quality): the loadings family is a "
        "PROJECTION, not a partition — the loaded-atom residual (1 - Sum_f loading) is honestly "
        "unmodeled and Sum(exposure) != Sum(atoms) in general; the promoted loadings are "
        "price-return betas from short single-name regressions (the standard errors and R^2 "
        "stay first-class on the estimate rows and MUST be read with any consumer of this "
        "number); the total-family residual leg's MV*Sum(w_f) scaling is disclosed in scope."
    ),
    finding_keys=(
        "The loaded-atom residual",
        "Price-return betas",
    ),
)


# --- ES-HS-1 stage 4: the empirical historical-ES code's dossiers (OD-ES-HS-1-F) ---
# SEPARATE constants (the MF1_LOADINGS_TIER shape) — NEVER added to TIER_DOSSIERS or
# FLAGSHIP_DOSSIERS: the campaign PG suite derives its exactly-16 pin from TIER_DOSSIERS itself
# and the flagship map feeds the campaign's own filing loop (the planning verifier's catch).

#: HIGH materiality / MEDIUM complexity — the parametric-ES twin's rating shape; derives
#: TIER_1 under the ratified MG-1 matrix (HIGH materiality alone), so the INITIAL's
#: next_review_due carries the strictest 365-day ceiling (stated at ratification, OQ-ES-HS-1-5).
ES_HS_TIER = TierDossier(
    "HIGH",
    "MEDIUM",
    "Flagship tail-severity number on the flagship book and purpose (HIGH materiality); the "
    "historical-simulation family's mechanics plus an EMPIRICAL tail mean - no estimation "
    "chain, no registered constant, arithmetic fully reproducible from the pinned scenario "
    "set (MEDIUM complexity).",
)

ES_HS_INITIAL = FlagshipDossier(
    outcome="APPROVED_WITH_CONDITIONS",
    scope_note=(
        "INITIAL validation of the flagship historical-simulation ES (0.95, 1-day, window=21) "
        "bound to the SAME pinned snapshot as the flagship historical-VaR run - the coherent "
        "(VaR, ES) pair over ONE scenario set (evidence = this model's OWN run; n*a = 1.05, "
        "the FRACTIONAL Acerbi-Tasche boundary weight applied at the adequacy floor; the "
        "seeded window's worst two scenarios TIE, so ES equals its VaR sibling exactly - the "
        "recorded tied-tail equality case, disclosed rather than smoothed away). "
        "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant under the "
        "ES-HS-1 ratification (OQ-ES-HS-1-5); the ratified dossier table is the human "
        "validation judgment, the filing is its transcription."
    ),
    conditions=(
        "CONDITION (tail resolution at the floor): at window=21/0.95 the effective tail mass "
        "is 1.05 scenario-equivalents - most of the estimate's weight sits on the single "
        "worst scenario; a materially larger window is the remediation lever for tail "
        "resolution and MUST be weighed before this number carries incremental capital or "
        "limit decisions. CONDITION (factor substrate): specific/idiosyncratic risk = 0 "
        "outside the registered factor universe - the tail mean inherits the substrate's "
        "blindness identically to its VaR sibling."
    ),
    finding_keys=(
        "effective tail mass",
        "worst scenario IN the window",
        "DELIBERATELY not backtestable v1",
    ),
)


# --- RS-1 stage 5 (OD-RS-1-E): the residual-estimator remediation — the SECOND lifecycle turn.
# TWO TRIGGERED re-validations close the raw-sample-sigma_e rider on the flagship TOTAL-family
# AWCs (the "hostage to the PA-3 estimate quality" finding is SUPERSEDED by the closure finding;
# the fresh conditions restate the surviving posture in fresh words — the MF-1
# closure-by-supersession discipline at the version grain), plus the INITIAL AWC dossiers for the
# two NEW estimator versions of risk.proxy_weight.regression (no new model CODE — the campaign/
# multifamily/stage-4 code-count pins are untouched; the model keeps its campaign tier).

#: The finding that CLOSES the raw-sample-sigma_e rider (filed on both new TRIGGERED records).
RS1_CLOSURE_FINDING = (
    "CLOSED (RS-1): the raw-sample-only residual-estimator posture is remediated - the "
    "residual estimator now admits DECLARED conventions (EWMA_RISKMETRICS decay-weighting; "
    "SHRINKAGE_CROSS_SECTIONAL_EB empirical-Bayes cross-sectional shrinkage with data-driven "
    "per-instrument intensity), and the cited evidence run's residual leg consumes an "
    "EB-SHRUNK estimate (MF-EQ-A, shrunk toward the 3-equity comparable cohort) and an EWMA "
    "estimate (MF-EQ-B, declared lambda=0.94 on the sleeve's daily-period residuals) "
    "alongside the raw estimates (MF-EQ-C and the corporate bond). Estimation-quality "
    "dependence survives in kind but is "
    "REMEDIABLE by convention choice; the raw-sample-only clause is closed."
)

RS1_TRIGGERED_DOSSIERS: dict[str, FlagshipDossier] = {
    "risk.var.parametric_total": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "TRIGGERED re-validation of the flagship TOTAL parametric VaR v2 (0.99, 1-day, "
            "appraisal_days=91, max_estimate_age_days=400) — the residual-estimator "
            "remediation (RS-1): the cited evidence run pays a REAL diagonal residual whose "
            "estimates span all three declared conventions (EB-shrunk / EWMA / raw). The "
            "raw-sample-only residual clause closes; the surviving posture is restated in the "
            "conditions. "
            "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant "
            "under the RS-1 ratification (OQ-RS-1-5); the ratified dossier table is the "
            "human validation judgment, the filing is its transcription."
        ),
        conditions=(
            "CONDITION (partial idiosyncratic coverage): the residual leg pays a DIAGONAL "
            "idiosyncratic variance for REGRESSION-cited instruments ONLY — non-proxied and "
            "MANUAL-method atoms carry zero idiosyncratic variance, and cross-residual "
            "correlation = 0 by construction. Residual-estimator conventions (RS-1) are "
            "DECLARED model identity: EWMA and EB-shrinkage estimates flow through this "
            "number when promoted; the estimator choice is the declaring analyst's and the "
            "comparable-cohort rule applies to any shrinkage promotion. The BT-2 "
            "SMOOTHING-DOCTRINE READ RULE stands unchanged: on an appraisal-marked book "
            "the unconditional Kupiec/Basel verdict over a 1-day total series is NOT "
            "valid adequacy evidence in either direction (exceptions suppressed between "
            "marks, clustered on mark dates); the dated per-pair EXCEPTION_INDICATOR "
            "rows are the honest evidence surface. The v1 UNGATED GRANDFATHER note "
            "stands (sunset lever: a VW-1 REJECT on the v1 model_version). "
            "FREQUENCY-CONVERSION CAVEAT (carried forward, unremediated): the declared "
            "appraisal_days=91 residual conversion is calibrated to the "
            "quarterly-appraisal leg; applied to the sleeve's daily-period estimates it "
            "understates the daily residual - the cited run evidences the estimator "
            "conventions, not residual calibration (calendar-aware per-period counts "
            "remain the open remediation lever)."
        ),
        finding_keys=(
            "DIAGONAL residuals only",
            "ZERO idiosyncratic risk",
        ),
    ),
    "risk.var.parametric_es_total": FlagshipDossier(
        outcome="APPROVED_WITH_CONDITIONS",
        scope_note=(
            "TRIGGERED re-validation of the flagship TOTAL parametric Expected Shortfall "
            "(0.975, 1-day, appraisal_days=91, max_estimate_age_days=400) — the "
            "residual-estimator remediation (RS-1): the cited evidence run applies the "
            "registered multiplier to a TOTAL sigma whose residual leg consumes EB-shrunk + "
            "EWMA + raw estimates. The raw-sample-only residual clause closes; the surviving "
            "posture is restated in the conditions. "
            "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant "
            "under the RS-1 ratification (OQ-RS-1-5); the ratified dossier table is the "
            "human validation judgment, the filing is its transcription."
        ),
        conditions=(
            "CONDITION (partial idiosyncratic coverage + the read rule): the ES multiplier "
            "over the TOTAL sigma inherits the total family's posture standalone — diagonal "
            "residuals for REGRESSION-cited instruments only, zero idiosyncratic variance "
            "for non-proxied/MANUAL atoms, and the BT-2 smoothing-doctrine read rule on "
            "appraisal-marked books (a sigma-multiple is exactly as honest as its sigma). "
            "Residual-estimator conventions (RS-1) are DECLARED model identity and flow "
            "through the sigma this multiple scales. The ES row reproduces through its bound "
            "model_version's declared es_multiplier (the non-reconciling-row limitation), "
            "never from the row alone. FREQUENCY-CONVERSION CAVEAT (carried forward, "
            "unremediated): the appraisal_days=91 conversion applied to daily-period "
            "sleeve estimates understates the daily residual - the cited run evidences "
            "the estimator conventions, not residual calibration (calendar-aware "
            "per-period counts remain the open remediation lever)."
        ),
        finding_keys=(
            "The residual leg is PA-4's verbatim",
            "BT-2's smoothing doctrine carries over UNCHANGED",
        ),
    ),
}

#: The EWMA version's INITIAL (AWC): a genuinely-new declared VERSION of an existing code — SOME
#: record (the MF-1 loadings-INITIAL criterion applied at the version grain, per the ratified
#: OD-RS-1-E); evidence = its own COMPLETED re-estimate run over MF-EQ-B.
RS1_EWMA_INITIAL = FlagshipDossier(
    outcome="APPROVED_WITH_CONDITIONS",
    scope_note=(
        "INITIAL validation of the EWMA_RISKMETRICS residual-estimator version (declared "
        "decay_lambda=0.94, daily-period sleeve residuals at CALENDAR-daily mark spacing — "
        "the RiskMetrics daily constant, fit on trading-day returns, applied at daily "
        "spacing (the distinction disclosed, not elided): the cited evidence run "
        "re-estimates MF-EQ-B with "
        "loadings/std-errors/R^2 byte-identical to its raw estimate and ONLY the residual "
        "stdev re-weighted (the s2 decoupling, verified in the kernel suite). "
        "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant under the "
        "RS-1 ratification (OQ-RS-1-1/5); the ratified dossier table is the human validation "
        "judgment, the filing is its transcription."
    ),
    conditions=(
        "CONDITION (frequency discipline): the declared lambda is calibrated per observation "
        "frequency — 0.94 is the RiskMetrics DAILY constant and this version is honest only "
        "on daily-period residual series; a quarterly-appraisal series requires its own "
        "declared lambda (a new version), never this one. CONDITION (effective sample size): "
        "the decayed estimate reacts faster on FEWER effective observations — window length "
        "and lambda are the levers, and short-series noise at the tail end is disclosed, not "
        "corrected."
    ),
    finding_keys=(
        "EFFECTIVE SAMPLE SIZE",
        "DECLARED lambda",
    ),
)

#: The EB-shrinkage version's INITIAL (AWC): evidence = its own COMPLETED shrinkage run over the
#: 3-equity comparable cohort (the bond EXCLUDED — the comparable-risk-group rule demonstrated).
RS1_SHRINKAGE_INITIAL = FlagshipDossier(
    outcome="APPROVED_WITH_CONDITIONS",
    scope_note=(
        "INITIAL validation of the SHRINKAGE_CROSS_SECTIONAL_EB residual-estimator version "
        "(method-as-identity — NO declared numeric intensity; every per-instrument w_i is "
        "computed from the pinned cohort and reproduces from the pin alone): the cited "
        "evidence run shrinks MF-EQ-A toward the 3-equity comparable cohort's pool "
        "(MF-EQ-A/B/C; the corporate bond deliberately EXCLUDED), carrying MF-EQ-A's "
        "regression identity unchanged with only the residual stdev transformed. "
        "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant under the "
        "RS-1 ratification (OQ-RS-1-2/5); the ratified dossier table is the human validation "
        "judgment, the filing is its transcription."
    ),
    conditions=(
        "CONDITION (comparable cohort): the cross-sectional pool assumes a comparable-risk "
        "group — the declaring analyst owns cohort membership, and cross-asset-class pooling "
        "(a bond toward an equity pool) is a recorded mis-application. CONDITION "
        "(identifiability floor): fewer than 3 comparable members refuses fail-closed (tau^2 "
        "unidentifiable); the demo cohort sits AT the floor, so the fitted intensities are "
        "genuine but minimally resolved — cohort growth is the resolution lever."
    ),
    finding_keys=(
        "COMPARABLE-COHORT",
        "MIN-COHORT fail-closed",
        "GAUSSIAN sampling variance",
    ),
)


# --- DS-2 stage 6 (OD-DS-2-E): the estimator-convention INITIALs. NO new model CODE (two
# VERSIONS of perf.return.desmoothed_geltner — the count pins hold; the model keeps its campaign
# tier) and NO TRIGGERED re-validation (census-proved: no existing validation condition names the
# declared-alpha rider — the desmoothing versions carry EXCEPTION-form records without closure
# tokens, so there is nothing to close by supersession; forcing one would be the false ceremony
# HG-1's OQ-5 bars — recorded honestly, the deliberate contrast with the MF-1/RS-1 flywheel).

#: The AR1_ESTIMATED version's INITIAL (AWC): the ESTIMATION demonstrated with its honest
#: uncertainty — deliberately NOT a recovery claim (the DS-2 planning verifier's R1 reframe: at
#: n=15 the small-sample upward bias of alpha-hat is ~0.7x the band; a "recovery" claim would
#: ride on seed luck).
DS2_AR1_INITIAL = FlagshipDossier(
    outcome="APPROVED_WITH_CONDITIONS",
    scope_note=(
        "INITIAL validation of the AR1_ESTIMATED desmoothing version (declared min_periods=8, "
        "band_convention=BARTLETT_WHITE_NOISE): the cited evidence run estimates alpha IN-RUN "
        "on the PE-HARBORVIEW-IX series - 16 quarterly marks GENERATED at a KNOWN true alpha "
        "of 0.4, so the record shows estimation WITH its honest uncertainty: the persisted "
        "band (~0.26 at n=15) and the disclosed small-sample UPWARD bias of alpha-hat mean "
        "the estimate is EXPECTED to land above the true alpha at this series length - "
        "deliberately NOT a recovery claim. The platform demonstrates its own estimator's "
        "finite-sample weakness on appraisal-length series - the stated-honestly thesis. "
        "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant under the "
        "DS-2 ratification (OQ-DS-2-1/5); the ratified dossier table is the human validation "
        "judgment, the filing is its transcription."
    ),
    conditions=(
        "CONDITION (short-series estimation): alpha-hat on appraisal-length series carries a "
        "wide band AND a systematic upward bias - both persisted/disclosed, neither corrected; "
        "series length is the remediation lever, and any capital or limit decision consuming a "
        "desmoothed series from this version MUST weigh the band. CONDITION (structure): the "
        "single-lag AR(1) form is still imposed - estimating alpha does not fix structural "
        "mis-specification; the OKUNEV_WHITE_ITERATIVE sibling addresses higher-order "
        "structure."
    ),
    finding_keys=(
        "SAMPLING ERROR",
        "SMALL-SAMPLE UPWARD BIAS",
        "CONSERVATIVE BAND",
    ),
)

#: The OKUNEV_WHITE_ITERATIVE version's INITIAL (AWC).
DS2_OW_INITIAL = FlagshipDossier(
    outcome="APPROVED_WITH_CONDITIONS",
    scope_note=(
        "INITIAL validation of the OKUNEV_WHITE_ITERATIVE desmoothing version (declared "
        "ow_max_order=2): the cited evidence run whitens the same PE-HARBORVIEW-IX series "
        "through two deterministic lag-i passes (the per-pass coefficient the '-' root of the "
        "settled quadratic; rows carry alpha NULL - the convention has no single alpha; the "
        "coefficients reproduce from the pinned marks alone). "
        "NON-INDEPENDENCE DISCLOSURE: drafted and filed by the delivery assistant under the "
        "DS-2 ratification (OQ-DS-2-2/5); the ratified dossier table is the human validation "
        "judgment, the filing is its transcription."
    ),
    conditions=(
        "CONDITION (transcription grade): the per-pass formula is verified by first-principles "
        "derivation plus a vendor reproduction - the SSRN primary is GATED; re-verify against "
        "the primary or a second independent source BEFORE any extension of this convention. "
        "CONDITION (fixed sequence + shortening): one pass per order ascending (a later pass "
        "slightly perturbs earlier orders - the repeat-until-tolerance variant is a recorded "
        "v2), and each order-i pass drops its first i values - short appraisal series bound "
        "the usable order."
    ),
    finding_keys=(
        "FIXED PASS SEQUENCE",
        "VENDOR-NORMALIZED TRANSCRIPTION",
        "SERIES SHORTENING",
    ),
)
