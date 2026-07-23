"""Parametric-VaR binder (P3-5, ENT-027 — delta-normal v1, the fourth governed risk number and
the FIRST derived-of-derived one).

``run_var`` produces the ONE ``var_result`` summary row ONLY when bound to a ``dataset_snapshot``
(``VAR_INPUT``, pinning EVERY result row of the two consumed upstream governed runs) + a complete
``calculation_run`` + a **REGISTERED ``model_version`` OF THE PARAMETRIC-VAR MODEL whose DECLARED
confidence/horizon/z fixed the parameters** (AD-014 / FW-RUN / TR-15 / CTRL-003 / OD-P3-5-D — the
``run_covariance`` exemplar mirrored step-for-step; the declared-parameter identity extends the
OD-P3-4-G window precedent). The number is the zero-mean delta-normal VaR
(``irp_shared.risk.var_kernel``): ``sigma_p = sqrt(x' Sigma x)``, ``VaR = z * sigma_p`` — the
exposure vector ``x`` from a COMPLETED FACTOR_EXPOSURE run, ``Sigma`` from a COMPLETED COVARIANCE
run.

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned
``COMPONENT_KIND_FACTOR_EXPOSURE``/``COMPONENT_KIND_COVARIANCE`` captured content** — it makes
**NO** live result/factor read, so a later upstream RE-RUN (new rows under a NEW run) cannot
move a historical VaR (test-proven).

Failure model (the P3-4 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing prerequisites; an unregistered or WRONG-MODEL version; a
  malformed/absent/ambiguous declared parameter; a non-COMPLETED / cross-tenant / empty upstream
  run; a wrong-purpose snapshot; **pinned content that is not a well-formed v1 input** — zero
  rows of either kind, mixed-run rows, non-uniform ``base_currency``, wrong covariance
  vocabulary/window uniformity, an exposure factor NOT covered by the covariance set, or a
  missing canonical pair): **raise BEFORE ``create_run``** ⇒ ZERO run + ZERO rows + ZERO
  run-audit. A snapshot minted elsewhere cannot smuggle an uncovered factor or a mixed input
  past the gate. **NO zero-variance imputation, ever.**
- **Post-create FAILED** (the OD-P3-5-G radicand gate — a genuinely non-PSD pinned matrix,
  REACHABLE via a hand-minted snapshot, unlike the P3-4 defensive gate): FAILED run
  (``outcome='failure'``) + ``DATA.VALIDATE`` DQ evidence + ZERO rows + a radicand-naming
  ``failure_reason``.
- **Emit-path** raises propagate ⇒ the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``risk -> {snapshot, calc, model, lineage, dq, audit, db}``; imports NO live
result reader into the COMPUTE path; imports NO numpy (test-only), NO quantile/simulation/
revaluation symbol; nothing imports ``risk``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.reads import latest_run_rows, list_governed_results
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.models import (
    FREQUENCY_APPRAISAL,
    FREQUENCY_DAILY,
    MAPPING_METHOD_MANUAL,
    MAPPING_METHOD_REGRESSION,
)
from irp_shared.model.models import ModelVersion
from irp_shared.risk.bootstrap import (
    ES_MODEL_CODE,
    ES_TOTAL_MODEL_CODE,
    VAR_MODEL_CODE,
    VAR_TOTAL_CALENDAR_DAYS_PER_YEAR,
    VAR_TOTAL_MODEL_CODE,
    VAR_TOTAL_TRADING_DAYS_PER_YEAR,
    VAR_UNIFIED_MODEL_CODE,
    VarParameters,
    WrongModelVersionError,
    assert_model_version_of,
    declared_appraisal_days,
    declared_es_multiplier,
    declared_es_total_max_estimate_age_days,
    declared_max_estimate_age_days,
    declared_unified_appraisal_days,
    declared_var_parameters,
)
from irp_shared.risk.covariance_service import resolve_covariance_run
from irp_shared.risk.es_kernel import EsKernelError, compute_parametric_es
from irp_shared.risk.events import (
    METRIC_TYPE_ES_PARAMETRIC,
    METRIC_TYPE_VAR_PARAMETRIC,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    RUN_TYPE_VAR,
    VarActor,
)
from irp_shared.risk.factor_service import resolve_factor_exposure_run
from irp_shared.risk.models import METRIC_TYPE_ESTIMATION_SUMMARY, VarResult
from irp_shared.risk.private_covariance_service import resolve_private_covariance_run
from irp_shared.risk.var_kernel import compute_parametric_var
from irp_shared.risk.var_total_kernel import (
    ResidualInstrument,
    VarTotalKernelError,
    total_var_residual,
)
from irp_shared.risk.var_unified_kernel import (
    VarUnifiedKernelError,
    daily_omega,
    private_block_variance,
    sigma_unified,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    COMPONENT_KIND_PROXY_MAPPING,
    COMPONENT_KIND_PROXY_WEIGHT,
    PURPOSE_PROXY_WEIGHT_INPUT,
    PURPOSE_RESIDUAL_SHRINKAGE_INPUT,
    PURPOSE_VAR_INPUT,
    VAR_TOTAL_BINDING_PREDICATE,
    VAR_UNIFIED_BINDING_PREDICATE,
    SnapshotActor,
    SnapshotNotFound,
    build_var_snapshot,
    build_var_total_snapshot,
    build_var_unified_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the P3-1/3/4 pattern).
_COMPLETENESS_RULE_CODE = "risk.var.completeness"
#: The v1 covariance-input vocabulary the pinned matrix must carry (the P3-4 output contract).
_REQUIRED_STATISTIC_TYPE = "COVARIANCE"
_REQUIRED_RETURN_TYPE = "SIMPLE"
_REQUIRED_FREQUENCY = "DAILY"
#: Source-column magnitude bounds: a pinned value EXCEEDING its origin column's envelope cannot
#: be a genuine governed row (exposure_amount Numeric(28,6) < 1E22; covariance Numeric(38,20)
#: < 1E18) — refused pre-create (2026-07 review: an absurd hand-minted pin otherwise crashed
#: the kernel quantize POST-create with no durable evidence).
_MAX_EXPOSURE_ABS = Decimal("1E22")
_MAX_COVARIANCE_ABS = Decimal("1E18")
#: The var_result sigma/var_value column envelope (Numeric(28,6)): column-legal-but-extreme
#: inputs can still produce sigma ~1E31 — gate it into a committed FAILED run, never a PG
#: NumericValueOutOfRange 500 (2026-07 review).
_MAX_RESULT_ABS = Decimal("1E22")
#: PA-4 total-family envelopes (the SAME source-column-envelope discipline, extended): a pinned
#: PROXY_WEIGHT ``residual_stdev`` (PreciseDecimal(20,12), 8 integer digits) and the RAW
#: ``residual_variance`` leg (Numeric(38,20), 18 integer digits) before quantize.
_MAX_RESIDUAL_STDEV_ABS = Decimal("1E8")
_MAX_RESIDUAL_VARIANCE_ABS = Decimal("1E18")
#: sigma_total/var_value_total quantum (6dp, the var_kernel ``_RESULT_QUANTUM`` twin) and
#: residual_variance quantum (20dp, the ``var_result.residual_variance`` Numeric(38,20) scale).
_SIGMA_QUANTUM = Decimal(1).scaleb(-6)
_RESIDUAL_VARIANCE_QUANTUM = Decimal(1).scaleb(-20)
#: Compute precision for the total-family post-kernel arithmetic (the ``var_kernel``/
#: ``var_total_kernel`` ``_COMPUTE_PREC``/``_CTX_PRECISION`` twin) — z*sigma_total + the quantize
#: calls run at the SAME 50-digit precision the kernels used, so the zero-proxied-instrument
#: invariance (total ≡ plain) is byte-exact, not merely numerically close.
_COMPUTE_PREC = 50


class VarInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Maps to 422."""


class VarNotVisible(Exception):
    """Raised when a ``var_result`` id is not visible in the acting tenant scope."""

    def __init__(self, var_id: str) -> None:
        super().__init__(f"var_result {var_id} is not visible in the current tenant")
        self.var_id = str(var_id)


class VarRunNotVisible(Exception):
    """Raised when a VaR ``calculation_run`` id is not visible in the acting tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"VaR run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class VarRunResult:
    """The outcome of ``run_var``: the ``calculation_run`` + status + the summary row produced.
    ``status`` is ``COMPLETED`` (with ``rows`` holding the ONE summary row) or ``FAILED`` (the
    radicand gate: a committed FAILED run + ZERO rows + a radicand-naming ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[VarResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the kernel arguments + the run-uniform captured
    descriptors."""

    exposure_rows: list[tuple[str, Decimal]]  # (factor_id lowercase, exposure_amount)
    covariance: dict[tuple[str, str], Decimal]
    exposure_run_id: str
    covariance_run_id: str
    base_currency: str
    n_factors: int
    n_observations: int
    window_start: date
    window_end: date


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw exposure/covariance row dicts (PURE — no
    live read; the AD-014 invariant)."""
    exposure_raw: list[dict[str, Any]] = []
    covariance_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
            exposure_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_COVARIANCE:
            covariance_raw.append(data)
    return exposure_raw, covariance_raw


def _adjudicate_pins(
    exposure_raw: list[dict[str, Any]], covariance_raw: list[dict[str, Any]]
) -> _ParsedInput:
    """PRE-CREATE adjudication of the pinned input (both entry paths — the OD-P3-5-H named
    checks): >= 1 row of EACH kind; single-run provenance per kind (no mixed-run smuggle);
    uniform ``base_currency``; the v1 covariance vocabulary + uniform window; COVERAGE (every
    exposure factor in the covariance factor set, every needed canonical pair present — NO
    zero-variance imputation); no duplicate covariance pair. Raises :class:`VarInputError`."""
    if not exposure_raw:
        raise VarInputError(
            "the snapshot pins no FACTOR_EXPOSURE rows — not a VaR input (an empty portfolio "
            "vector is refused)"
        )
    if not covariance_raw:
        raise VarInputError("the snapshot pins no COVARIANCE rows — not a VaR input")

    exposure_run_ids = {str(r["calculation_run_id"]).lower() for r in exposure_raw}
    if len(exposure_run_ids) != 1:
        raise VarInputError("the pinned exposure rows span multiple runs — refused")
    covariance_run_ids = {str(r["calculation_run_id"]).lower() for r in covariance_raw}
    if len(covariance_run_ids) != 1:
        raise VarInputError("the pinned covariance rows span multiple runs — refused")

    base_currencies = {r["base_currency"] for r in exposure_raw}
    if len(base_currencies) != 1:
        raise VarInputError(
            f"the pinned exposure rows carry mixed base currencies {sorted(base_currencies)} — "
            f"refused"
        )
    base_currency = next(iter(base_currencies))
    if not isinstance(base_currency, str) or len(base_currency) != 3:
        # A uniformly-NULL or non-3-letter base_currency ({None} / {"USDX"} pass the set-of-one
        # check) would otherwise reach the NOT-NULL varchar(3) column as a post-create 500 (P3-C3
        # binder-consistency pass — the active-risk twin).
        raise VarInputError("the pinned exposure base_currency is not a 3-letter code — refused")

    exposure_ids_seen: set[str] = set()
    for r in exposure_raw:
        rid = str(r["id"]).lower()
        if rid in exposure_ids_seen:  # a duplicated pin would double-count the exposure total
            raise VarInputError(f"duplicate pinned exposure row {rid} — refused")
        exposure_ids_seen.add(rid)
        if abs(Decimal(r["exposure_amount"])) >= _MAX_EXPOSURE_ABS:
            raise VarInputError(
                "a pinned exposure_amount exceeds its source-column envelope — refused"
            )

    windows = {
        (
            r["statistic_type"],
            r["return_type"],
            r["frequency"],
            r["n_observations"],
            r["window_start"],
            r["window_end"],
        )
        for r in covariance_raw
    }
    if len(windows) != 1:
        raise VarInputError("the pinned covariance rows carry a non-uniform window/vocabulary")
    statistic_type, return_type, frequency, n_observations, window_start, window_end = next(
        iter(windows)
    )
    if (
        statistic_type != _REQUIRED_STATISTIC_TYPE
        or return_type != _REQUIRED_RETURN_TYPE
        or frequency != _REQUIRED_FREQUENCY
    ):
        raise VarInputError(
            f"the pinned covariance vocabulary ({statistic_type!r}/{return_type!r}/"
            f"{frequency!r}) is not the v1 COVARIANCE/SIMPLE/DAILY contract"
        )

    covariance: dict[tuple[str, str], Decimal] = {}
    for r in covariance_raw:
        pair = (str(r["factor_id_1"]).lower(), str(r["factor_id_2"]).lower())
        if pair[0] > pair[1]:
            # Non-canonical storage order is NOT a well-formed v1 input (the OD-P3-4-D
            # contract) — and accepting it verbatim would let a REVERSED duplicate carry a
            # conflicting value past the duplicate check (2026-07 review).
            raise VarInputError(f"non-canonical covariance pair order {pair} — refused")
        if pair in covariance:
            raise VarInputError(f"duplicate covariance pair {pair} — refused")
        value = Decimal(r["covariance_value"])
        if abs(value) >= _MAX_COVARIANCE_ABS:
            raise VarInputError(
                "a pinned covariance_value exceeds its source-column envelope — refused"
            )
        covariance[pair] = value
    covariance_factors = {fid for pair in covariance for fid in pair}

    exposure_rows: list[tuple[str, Decimal]] = []
    uncovered: set[str] = set()
    for r in exposure_raw:
        fid = str(r["factor_id"]).lower()
        exposure_rows.append(
            (
                fid,
                parse_strict_decimal(
                    r["exposure_amount"], error=VarInputError, field="exposure_amount"
                ),
            )
        )
        if fid not in covariance_factors:
            uncovered.add(r["factor_code"])
    if uncovered:
        raise VarInputError(
            f"exposure factors {sorted(uncovered)} are not covered by the pinned covariance "
            f"matrix — refused (NO zero-variance imputation)"
        )
    exposure_factors = sorted({fid for fid, _amt in exposure_rows})
    for i, fid_i in enumerate(exposure_factors):
        for fid_j in exposure_factors[i:]:
            if (fid_i, fid_j) not in covariance:
                raise VarInputError(
                    f"the pinned covariance matrix is missing the pair ({fid_i}, {fid_j}) — "
                    f"refused"
                )

    return _ParsedInput(
        exposure_rows=exposure_rows,
        covariance=covariance,
        exposure_run_id=next(iter(exposure_run_ids)),
        covariance_run_id=next(iter(covariance_run_ids)),
        base_currency=base_currency,
        n_factors=len(exposure_factors),
        n_observations=int(n_observations),
        window_start=date.fromisoformat(window_start),
        window_end=date.fromisoformat(window_end),
    )


@dataclass(frozen=True)
class _ParsedProxyWeight:
    """One adjudicated proxied instrument's idiosyncratic input (PA-4): its cited estimate's
    APPRAISAL-PERIOD residual stdev, keyed by lowercase instrument id. ``estimate_snapshot_id``
    (BT-2) is the estimate's OWN pinned PROXY_WEIGHT_INPUT snapshot id — the handle to the
    regression span end that the staleness gate measures age against (OD-BT-2-C)."""

    instrument_id: str
    residual_stdev: Decimal
    estimate_snapshot_id: str | None


def _parse_total_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``PROXY_MAPPING``/``PROXY_WEIGHT`` captured_content (PA-4, total-family
    only; PURE — no live read; the ``_parse_pins`` twin)."""
    mapping_raw: list[dict[str, Any]] = []
    weight_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_PROXY_MAPPING:
            mapping_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_PROXY_WEIGHT:
            weight_raw.append(data)
    return mapping_raw, weight_raw


def _adjudicate_total_proxies(
    mapping_raw: list[dict[str, Any]],
    weight_raw: list[dict[str, Any]],
    *,
    base_currency: str,
    exposure_instrument_ids: set[str],
) -> list[_ParsedProxyWeight]:
    """PRE-CREATE adjudication of the pinned PROXY_MAPPING/PROXY_WEIGHT pins (PA-4 — the same
    trust boundary ``_adjudicate_pins`` defends: consume-existing accepts ANY snapshot, so a
    hand-minted pin set must not smuggle an ill-formed idiosyncratic input past the gate). Fail-
    closed gates: every ``PROXY_WEIGHT`` pin MUST be an ``ESTIMATION_SUMMARY`` row (the wrong-type
    refusal); NO duplicate instrument across ``PROXY_WEIGHT`` pins; every ``PROXY_WEIGHT``
    instrument MUST have >= 1 pinned ``PROXY_MAPPING`` AND >= 1 pinned ``FACTOR_EXPOSURE`` row for
    the SAME instrument (the instrument-mismatch refusal, all three directions); the pinned
    ``series_currency`` MUST equal the run-uniform ``base_currency`` (the currency-match gate — no
    FX conversion, a v1 limitation); a missing/negative/envelope-exceeding ``residual_stdev``
    refuses; every pinned ``PROXY_MAPPING`` MUST carry ``mapping_method='REGRESSION'`` (the
    predicate's open-REGRESSION contract — a MANUAL-method pin carries no estimation evidence and
    must not smuggle a residual in; the 2026-07 review fold, the ``metric_type`` vocabulary-gate
    twin). Returns the adjudicated per-instrument residual inputs (empty ⇒ the book has no
    proxied instrument, the total ≡ plain-parametric invariance case). Raises
    :class:`VarInputError`."""
    for r in mapping_raw:
        if r["mapping_method"] != MAPPING_METHOD_REGRESSION:
            raise VarInputError(
                f"a pinned PROXY_MAPPING for instrument "
                f"{str(r['private_instrument_id']).lower()} carries mapping_method "
                f"{r['mapping_method']!r} — the total-VaR predicate pins REGRESSION rows only; "
                f"refused"
            )
    mapping_instruments = {str(r["private_instrument_id"]).lower() for r in mapping_raw}
    seen_instruments: set[str] = set()
    parsed: list[_ParsedProxyWeight] = []
    for r in weight_raw:
        if r["metric_type"] != METRIC_TYPE_ESTIMATION_SUMMARY:
            raise VarInputError(
                f"a pinned PROXY_WEIGHT component is not an ESTIMATION_SUMMARY row "
                f"(metric_type={r['metric_type']!r}) — refused"
            )
        instrument_id = str(r["instrument_id"]).lower()
        if instrument_id in seen_instruments:
            raise VarInputError(
                f"duplicate pinned PROXY_WEIGHT for instrument {instrument_id} — refused"
            )
        seen_instruments.add(instrument_id)
        if instrument_id not in mapping_instruments:
            raise VarInputError(
                f"PROXY_WEIGHT pin for instrument {instrument_id} has no corresponding pinned "
                f"PROXY_MAPPING — refused (instrument mismatch)"
            )
        if instrument_id not in exposure_instrument_ids:
            raise VarInputError(
                f"PROXY_WEIGHT pin for instrument {instrument_id} has no corresponding pinned "
                f"FACTOR_EXPOSURE row — refused (instrument mismatch)"
            )
        residual_stdev_raw = r.get("residual_stdev")
        if residual_stdev_raw is None:
            raise VarInputError(
                f"PROXY_WEIGHT pin for instrument {instrument_id} carries no residual_stdev — "
                f"refused"
            )
        residual_stdev = parse_strict_decimal(
            residual_stdev_raw, error=VarInputError, field="residual_stdev"
        )
        if residual_stdev < 0 or abs(residual_stdev) >= _MAX_RESIDUAL_STDEV_ABS:
            raise VarInputError(
                f"PROXY_WEIGHT pin for instrument {instrument_id} residual_stdev is negative or "
                f"exceeds its source-column envelope — refused"
            )
        series_currency = r["series_currency"]
        if series_currency != base_currency:
            raise VarInputError(
                f"PROXY_WEIGHT pin for instrument {instrument_id} series_currency "
                f"{series_currency!r} != the book's base_currency {base_currency!r} — refused "
                f"(no FX conversion, a v1 limitation)"
            )
        estimate_snapshot_raw = r.get("input_snapshot_id")
        parsed.append(
            _ParsedProxyWeight(
                instrument_id=instrument_id,
                residual_stdev=residual_stdev,
                # BT-2: the estimate's own input-snapshot handle (present on every genuine pin —
                # the serializer has always emitted it). Kept OPTIONAL here so this function stays
                # PURE and total; the age gate one layer up decides what an absent one means
                # (gated v2 ⇒ refuse; ungated v1 ⇒ echo NULL).
                estimate_snapshot_id=(
                    str(estimate_snapshot_raw).lower() if estimate_snapshot_raw else None
                ),
            )
        )
    for instrument_id in mapping_instruments:
        if instrument_id not in seen_instruments:
            raise VarInputError(
                f"PROXY_MAPPING pin for instrument {instrument_id} has no corresponding pinned "
                f"PROXY_WEIGHT — refused (instrument mismatch)"
            )
    return parsed


def _adjudicate_private_covariance(
    appraisal_cov_raw: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], Decimal], str]:
    """PRE-CREATE adjudication of the pinned APPRAISAL Ω_pp rows (PPF-3): >= 1 row; single-run
    provenance; the APPRAISAL/COVARIANCE/SIMPLE vocabulary (NOT the DAILY public contract);
    canonical pair order; no duplicate pair; the covariance envelope. Returns the Ω_pp matrix
    (canonical ``(a, b)`` pairs -> Decimal) + the run id. Coverage against ``p`` is the kernel's
    job (a held segment absent from the diagonal fails closed there)."""
    if not appraisal_cov_raw:
        raise VarInputError(
            "the unified snapshot pins no APPRAISAL covariance rows — not an Omega_pp input"
        )
    run_ids = {str(r["calculation_run_id"]).lower() for r in appraisal_cov_raw}
    if len(run_ids) != 1:
        raise VarInputError("the pinned private (Omega_pp) covariance rows span multiple runs")
    for r in appraisal_cov_raw:
        if (
            r["statistic_type"] != _REQUIRED_STATISTIC_TYPE
            or r["return_type"] != _REQUIRED_RETURN_TYPE
            or r["frequency"] != FREQUENCY_APPRAISAL
        ):
            raise VarInputError(
                f"the pinned Omega_pp vocabulary ({r['statistic_type']!r}/{r['return_type']!r}/"
                f"{r['frequency']!r}) is not the COVARIANCE/SIMPLE/APPRAISAL contract"
            )
    omega: dict[tuple[str, str], Decimal] = {}
    for r in appraisal_cov_raw:
        pair = (str(r["factor_id_1"]).lower(), str(r["factor_id_2"]).lower())
        if pair[0] > pair[1]:
            raise VarInputError(f"non-canonical Omega_pp pair order {pair} — refused")
        if pair in omega:
            raise VarInputError(f"duplicate Omega_pp pair {pair} — refused")
        value = parse_strict_decimal(
            r["covariance_value"], error=VarInputError, field="covariance_value"
        )
        if abs(value) >= _MAX_COVARIANCE_ABS:
            raise VarInputError("a pinned Omega_pp value exceeds its source-column envelope")
        omega[pair] = value
    return omega, next(iter(run_ids))


def _build_p_vector(
    manual_mapping_raw: list[dict[str, Any]], mv_by_instrument: dict[str, Decimal]
) -> dict[str, Decimal]:
    """Form the private-exposure vector ``p_s = Σ_{i ∈ MANUAL-members(s)} MV_i`` from the pinned
    MANUAL memberships + the exposure-derived ``MV_i`` (OD-PPF-3-B). Each membership's ``factor_id``
    is the pure-private segment. Fail-closed: an instrument with no pinned exposure MV (a membership
    that is not an exposure instrument), or an instrument that is a MANUAL member of MORE THAN ONE
    segment (ambiguous private attribution). At least one membership is required (the builder
    guarantees it; re-checked here for the consume-existing trust boundary)."""
    if not manual_mapping_raw:
        raise VarInputError(
            "the unified snapshot pins no MANUAL pure-private membership — not a unified input"
        )
    seen_instruments: set[str] = set()
    p_by_segment: dict[str, Decimal] = {}
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        for r in manual_mapping_raw:
            if r["mapping_method"] != MAPPING_METHOD_MANUAL:
                raise VarInputError(
                    f"a pinned membership carries mapping_method {r['mapping_method']!r} != MANUAL"
                )
            instrument_id = str(r["private_instrument_id"]).lower()
            if instrument_id in seen_instruments:
                raise VarInputError(
                    f"instrument {instrument_id} is a MANUAL member of more than one pure-private "
                    f"segment — ambiguous private attribution, refused"
                )
            seen_instruments.add(instrument_id)
            if instrument_id not in mv_by_instrument:
                raise VarInputError(
                    f"MANUAL membership for instrument {instrument_id} has no pinned "
                    f"FACTOR_EXPOSURE MV — refused (instrument mismatch)"
                )
            segment_id = str(r["factor_id"]).lower()
            p_by_segment[segment_id] = (
                p_by_segment.get(segment_id, Decimal(0)) + mv_by_instrument[instrument_id]
            )
    return p_by_segment


#: The snapshot purposes whose ``as_of_valuation_date`` IS a regression span end (age-measurable
#: for the staleness gate): the estimate's own input pin, and — RS-1 — a shrinkage cohort pin,
#: whose builder stamps the STALEST member's span end (the conservative age by construction).
_MEASURABLE_ESTIMATE_PURPOSES = frozenset(
    {PURPOSE_PROXY_WEIGHT_INPUT, PURPOSE_RESIDUAL_SHRINKAGE_INPUT}
)


def _estimate_age_days(
    session: Session,
    proxy_weights: list[_ParsedProxyWeight],
    *,
    acting_tenant: str,
    window_end: date,
    max_estimate_age_days: int | None,
) -> int | None:
    """The BT-2 staleness gate + evidence echo (OD-BT-2-C/D). Returns the MAX estimate age in
    calendar days across the cited estimates (the binding constraint), or ``None`` when there is
    nothing to measure.

    **Age** = ``window_end`` (this run's OWN economic as-of — the pinned covariance window end)
    MINUS the cited estimate's regression SPAN END (its PROXY_WEIGHT_INPUT snapshot header's
    ``as_of_valuation_date`` = max desmoothed ``period_end``). That anchor answers the question a
    staleness policy actually asks — *how old is the DATA under this σ_e* — rather than when the
    estimate happened to be computed (the pin's ``system_from``, which a re-run would preserve but
    which says nothing about data recency).

    **Reproducibility (AD-014):** both sides are fixed by the snapshot — ``window_end`` is pinned
    content, and the header is reached through the PINNED ``input_snapshot_id``. The header read
    is live, but ``dataset_snapshot`` is true-append-only (created once, never mutated), so the
    same snapshot re-run later yields the same age — the PM-1 "drift-free by construction"
    precedent for live-reading a pinned id.

    **The gate** (only when the version DECLARES a policy — a v2 identity): ``age >
    max_estimate_age_days`` (strict) ⇒ pre-create :class:`VarInputError` (422, zero run). On a
    gated bind ANY unmeasurable estimate REFUSES (the gate cannot evaluate — fail-closed): a pin
    with no ``input_snapshot_id``, a snapshot not visible in the acting tenant, or a cited header
    whose ``purpose`` is not ``PROXY_WEIGHT_INPUT`` (the anchor's MEANING is the contract — an
    ``as_of_valuation_date`` read off some other snapshot kind is not a regression span end, and
    without this check a hand-minted pin could cite a fresh VAR_INPUT header and defeat a tight
    policy; review fold, converged on by two finders).

    **The grandfather** (``max_estimate_age_days is None`` — an immutable pre-BT-2 v1 row): NO
    refusal is ever added. The age is computed and echoed as evidence, but ONLY when EVERY cited
    estimate is measurable: if any is unmeasurable the echo is ``None``, because a max over the
    resolvable SUBSET is not "the max across cited estimates" — it would understate staleness and
    read as a confident number (a validator triaging v1 staleness via VW-1's sunset lever must not
    see "30 days" when an unmeasured sibling could be years stale). UNKNOWN outranks any known max
    (review fold).
    """
    gated = max_estimate_age_days is not None
    ages: list[int] = []
    for weight in proxy_weights:
        if weight.estimate_snapshot_id is None:
            if gated:
                raise VarInputError(
                    f"PROXY_WEIGHT pin for instrument {weight.instrument_id} carries no "
                    f"input_snapshot_id — the declared max_estimate_age_days policy cannot be "
                    f"evaluated; refused"
                )
            return None  # ungated: unmeasurable ⇒ the whole echo is unknown, never a subset max
        try:
            estimate_snapshot = resolve_snapshot(
                session, weight.estimate_snapshot_id, acting_tenant=acting_tenant
            )
        except SnapshotNotFound:
            if gated:
                raise VarInputError(
                    f"PROXY_WEIGHT pin for instrument {weight.instrument_id} cites estimation "
                    f"snapshot {weight.estimate_snapshot_id}, which is not visible in the acting "
                    f"tenant — the declared max_estimate_age_days policy cannot be evaluated; "
                    f"refused"
                ) from None
            return None
        # RS-1 (OD-RS-1-B, a recorded Part-5.5 deviation from the byte-untouched fence): a
        # RESIDUAL_SHRINKAGE_INPUT citation is ADMITTED to the measurement — its
        # as_of_valuation_date is the STALEST cohort member's regression span end by builder
        # construction, so the measured age is the CONSERVATIVE (oldest-input) age. Without this
        # admission a shrunk estimate could never feed a GATED total run — the remediation would
        # be unusable on the exact family whose raw-sample rider it closes.
        if estimate_snapshot.purpose not in _MEASURABLE_ESTIMATE_PURPOSES:
            if gated:
                raise VarInputError(
                    f"PROXY_WEIGHT pin for instrument {weight.instrument_id} cites snapshot "
                    f"{weight.estimate_snapshot_id} of purpose "
                    f"{estimate_snapshot.purpose!r} not in "
                    f"{sorted(_MEASURABLE_ESTIMATE_PURPOSES)} — its as_of_valuation_date is "
                    f"not a regression span end, so the declared max_estimate_age_days policy "
                    f"cannot be evaluated; refused"
                )
            return None
        age = (window_end - estimate_snapshot.as_of_valuation_date).days
        if max_estimate_age_days is not None and age > max_estimate_age_days:
            raise VarInputError(
                f"the residual estimate cited for instrument {weight.instrument_id} is "
                f"{age} calendar days old at this run's as-of ({window_end.isoformat()}; the "
                f"estimate's regression data ends "
                f"{estimate_snapshot.as_of_valuation_date.isoformat()}), exceeding the declared "
                f"max_estimate_age_days={max_estimate_age_days} — refused (re-estimate, or "
                f"register a model version declaring a policy that admits it)"
            )
        ages.append(age)
    # A NEGATIVE age (the estimate's data ends AFTER this run's as-of — a look-ahead) passes: the
    # ratified policy is a MAXIMUM age, and a look-ahead gate is a different, unratified concern
    # (a recorded limitation). It is echoed honestly so the evidence shows it.
    return max(ages) if ages else None


@dataclass(frozen=True)
class _VarFamily:
    """Which of the FOUR model codes this run bound, decomposed onto the two axes the compute path
    actually branches on (ES-1, OD-ES-1-C/D; the helper is ratified in OD-ES-1-G).

    ``total`` = add PA-4's diagonal idiosyncratic residual leg to the factor variance.
    ``es``    = multiply the sigma by the REGISTERED ES multiplier k_c instead of the quantile z_c.

    The axes are independent, which is exactly why a 4-deep try/except chain over model codes was
    the wrong shape: the four codes are a 2x2, not a list.
    """

    code: str
    total: bool
    es: bool


#: The 2x2, in DISPATCH order. Order matters only for cost (each miss is a failed assert), not for
#: correctness — the codes are mutually exclusive, so at most one can match a given version.
_VAR_FAMILIES: tuple[_VarFamily, ...] = (
    _VarFamily(code=VAR_MODEL_CODE, total=False, es=False),
    _VarFamily(code=VAR_TOTAL_MODEL_CODE, total=True, es=False),
    _VarFamily(code=ES_MODEL_CODE, total=False, es=True),
    _VarFamily(code=ES_TOTAL_MODEL_CODE, total=True, es=True),
)


def _resolve_var_family(
    session: Session, model_version_id: str, *, acting_tenant: str
) -> tuple[ModelVersion, _VarFamily]:
    """Inventory-before-use + model identity (CTRL-003 / BR-3), dispatching on the bound model's
    code across the four VaR/ES families (PA-4's OD-PA-4-B dispatch, extended by ES-1).

    An UNREGISTERED version raises :class:`UnregisteredModelError` from the first assert (it is not
    a family question); a version of NONE of the four families raises the FIRST
    :class:`WrongModelVersionError` — i.e. the one naming the PLAIN code, which keeps the pre-ES-1
    message for the pre-ES-1 failure and is the family a caller passing an unrelated version most
    likely meant.
    """
    first_error: WrongModelVersionError | None = None
    for family in _VAR_FAMILIES:
        try:
            version = assert_model_version_of(
                session,
                str(model_version_id),
                tenant_id=acting_tenant,
                expected_model_code=family.code,
            )
        except WrongModelVersionError as exc:
            if first_error is None:  # the PLAIN-code miss — the pre-ES-1 message, preserved
                first_error = exc
            continue
        return version, family
    assert first_error is not None  # the loop is non-empty, so a full miss always set it
    raise first_error


def run_var(
    session: Session,
    *,
    acting_tenant: str,
    actor: VarActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str | None = None,
    covariance_run_id: str | None = None,
    snapshot_id: str | None = None,
) -> VarRunResult:
    """Run a governed parametric-VaR calculation — plain (``risk.var.parametric``) OR total
    (``risk.var.parametric_total``, PA-4), dispatched on the BOUND model (the PA-2
    one-binder-dispatches-on-bound-model precedent). Build-in-request (default —
    ``exposure_run_id`` + ``covariance_run_id``: builds a ``VAR_INPUT`` snapshot pinning both
    runs' result rows, PLUS the proxied instruments' idiosyncratic evidence on the total path) or
    consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create. See
    the module docstring for the failure model + the AD-014 / CTRL-003 / OD-P3-5-D invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/run-audit) ---
    if not code_version:
        raise VarInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise VarInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise VarInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise VarInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if snapshot_id is not None and (exposure_run_id is not None or covariance_run_id is not None):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY —
        # an ambiguous request must be refused, never guessed.
        raise VarInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(exposure_run_id/covariance_run_id), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3): the version must be REGISTERED and
    # belong to ONE of the four VaR/ES families (PA-4's OD-PA-4-B dispatch on the bound model's
    # code, extended by ES-1 to the 2x2 of {plain, total} x {VaR, ES}). The DECLARED
    # confidence/horizon/z (OD-P3-5-D) are version identity for ALL four (the SAME assumption-prefix
    # machinery); the total families ALSO declare ``appraisal_days``, and the ES families ALSO
    # declare their ``es_multiplier``.
    version, family = _resolve_var_family(
        session, str(model_version_id), acting_tenant=acting_tenant
    )
    is_total = family.total
    declared: VarParameters = declared_var_parameters(session, version)
    appraisal_days = declared_appraisal_days(session, version) if is_total else None
    # ES-1 (OD-ES-1-B): the DECLARED k_c, identity-checked against the registered table for the
    # version's OWN declared confidence. None on the VaR families (they multiply by z).
    es_multiplier = (
        declared_es_multiplier(session, version, code=family.code) if family.es else None
    )
    # BT-2 (OD-BT-2-C): the DECLARED staleness policy — None on the plain/HS families AND on a
    # grandfathered pre-BT-2 total v1 row (immutable, cannot absorb the declaration ⇒ ungated).
    # The ES-TOTAL code has no such grandfather (it is born with the declaration), so absent
    # REFUSES there rather than degrading to ungated (ES-1, plan Step 3).
    if is_total:
        max_estimate_age_days = (
            declared_es_total_max_estimate_age_days(session, version)
            if family.es
            else declared_max_estimate_age_days(session, version)
        )
    else:
        max_estimate_age_days = None

    # --- Bind the two-run snapshot (cross-tenant/unknown/ill-formed ⇒ pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_VAR_INPUT:
            raise VarInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_VAR_INPUT}"
            )
        # The plain path must REFUSE any snapshot that pins a leg it would silently drop — the total
        # predicate (idiosyncratic leg) AND, PPF-3 OD-3-F, the UNIFIED predicate (idiosyncratic +
        # pure-private legs). The verifier's fold: the binary is_total toggle had a HOLE — a
        # UNIFIED-predicate snapshot passed the plain path, running as a plain VaR while dropping
        # BOTH extra legs. (The total path below already refuses a unified snapshot: != VAR_TOTAL.)
        if not is_total and snapshot.binding_predicate_version in (
            VAR_TOTAL_BINDING_PREDICATE,
            VAR_UNIFIED_BINDING_PREDICATE,
        ):
            raise VarInputError(
                f"snapshot {snapshot_id} predicate {snapshot.binding_predicate_version!r} pins an "
                f"idiosyncratic/pure-private leg the plain parametric family drops — bind the "
                f"model_version whose family built it (total, or the unified model), not the plain "
                f"one (the OD-PA-2-C symmetric-refusal precedent, extended to unified)"
            )
        if is_total and snapshot.binding_predicate_version != VAR_TOTAL_BINDING_PREDICATE:
            # A plain/unified VAR_INPUT snapshot pins the wrong leg set — running the total model
            # over it would silently degrade or mis-decompose; refuse (OD-PA-4-C; unified != total).
            raise VarInputError(
                f"snapshot {snapshot_id} predicate {snapshot.binding_predicate_version!r} does "
                f"not pin the total-family idiosyncratic leg — build the snapshot under the total "
                f"model ({VAR_TOTAL_BINDING_PREDICATE!r})"
            )
    else:
        if not exposure_run_id or not covariance_run_id:
            raise VarInputError(
                "exposure_run_id + covariance_run_id are required to build a VaR snapshot"
            )
        exposure_run = resolve_factor_exposure_run(
            session, str(exposure_run_id), acting_tenant=acting_tenant
        )
        if exposure_run.status != RunStatus.COMPLETED.value:
            raise VarInputError(
                f"exposure run {exposure_run_id} status {exposure_run.status!r} != COMPLETED"
            )
        covariance_run = resolve_covariance_run(
            session, str(covariance_run_id), acting_tenant=acting_tenant
        )
        if covariance_run.status != RunStatus.COMPLETED.value:
            raise VarInputError(
                f"covariance run {covariance_run_id} status {covariance_run.status!r} "
                f"!= COMPLETED"
            )
        build_snapshot_fn = build_var_total_snapshot if is_total else build_var_snapshot
        snapshot = build_snapshot_fn(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            covariance_run_id=str(covariance_run_id),
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths; OD-P3-5-H): empty /
    # mixed-run / mixed-currency / wrong-vocab / uncovered-factor pins all refuse HERE — before
    # a run (or any run-audit) can exist. The total path ADDITIONALLY adjudicates the pinned
    # idiosyncratic evidence (OD-PA-4-C).
    try:
        comps = list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        exposure_raw, covariance_raw = _parse_pins(comps)
        parsed = _adjudicate_pins(exposure_raw, covariance_raw)
        proxy_weights: list[_ParsedProxyWeight] = []
        mv_by_instrument: dict[str, Decimal] = {}
        if is_total:
            mapping_raw, weight_raw = _parse_total_pins(comps)
            with localcontext() as ctx:
                # prec-50 like every other total-path arithmetic step: a default-context (prec-28)
                # sum of >= 2 near-envelope exposure rows silently rounds the MV — a breach of the
                # registered "Decimal at 50-digit context" assumption (2026-07 review).
                ctx.prec = _COMPUTE_PREC
                for r in exposure_raw:
                    iid = str(r["instrument_id"]).lower()
                    mv_by_instrument[iid] = mv_by_instrument.get(iid, Decimal(0)) + Decimal(
                        r["exposure_amount"]
                    )
            proxy_weights = _adjudicate_total_proxies(
                mapping_raw,
                weight_raw,
                base_currency=parsed.base_currency,
                exposure_instrument_ids=set(mv_by_instrument),
            )
    except VarInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content (missing keys, non-decimal/JSON-null values, bad
        # dates, non-object captured_content) is the SAME refusal class as a semantically ill-formed
        # input — a governed 422, never a raw parse 500 (2026-07 review). JSONDecodeError/
        # InvalidOperation subclass ValueError/Arithmetic; Decimal(None)/list-indexing raise
        # TypeError (P3-C3 binder-consistency pass — the active-risk twin).
        raise VarInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # BT-2 (OD-BT-2-C/D): the staleness gate + the age echo — OUTSIDE the pure-adjudication try
    # (it makes a tenant-scoped live read of the PINNED estimate snapshot id, so it must not sit
    # under the structural-parse net that would relabel a genuine refusal). No-op on the plain/HS
    # paths (proxy_weights is empty ⇒ None).
    estimate_age_days = _estimate_age_days(
        session,
        proxy_weights,
        acting_tenant=str(acting_tenant),
        window_end=parsed.window_end,
        max_estimate_age_days=max_estimate_age_days,
    )

    # The provenance ids come from the PINNED CONTENT — re-resolve BOTH under the acting tenant
    # (run_type + COMPLETED) before they are stamped into hard-FK columns: PG FK checks bypass
    # RLS, so without this a hand-minted snapshot could durably reference a FOREIGN tenant's
    # runs (and probe run-id existence cross-tenant) — the 2026-07 review's principal finding.
    # On the build path this re-resolution is an idempotent tautology.
    pinned_exposure_run = resolve_factor_exposure_run(
        session, parsed.exposure_run_id, acting_tenant=acting_tenant
    )
    if pinned_exposure_run.status != RunStatus.COMPLETED.value:
        raise VarInputError(f"the pinned exposure run {parsed.exposure_run_id} is not COMPLETED")
    pinned_covariance_run = resolve_covariance_run(
        session, parsed.covariance_run_id, acting_tenant=acting_tenant
    )
    if pinned_covariance_run.status != RunStatus.COMPLETED.value:
        raise VarInputError(
            f"the pinned covariance run {parsed.covariance_run_id} is not COMPLETED"
        )

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[VarResult], list[str]]:
        # The pure kernel over the adjudicated pins ONLY (no live read — the AD-014 invariant).
        estimate = compute_parametric_var(
            parsed.exposure_rows, parsed.covariance, z_score=declared.z_score
        )
        gaps: list[str] = []
        if estimate.sigma is None or estimate.var_value is None:
            gaps.append(f"non-psd-radicand:{estimate.radicand:E}<-tol:{estimate.tolerance:E}")
            return [], gaps

        if not is_total:
            if es_multiplier is None:
                plain_value = estimate.var_value
                plain_metric = METRIC_TYPE_VAR_PARAMETRIC
            else:
                # ES-1: ES = k_c * sigma_p over the SAME adjudicated pins. Multiply the RAW sqrt
                # and quantize ONCE, exactly as the kernel derives var_value = (z*raw).quantize()
                # — NOT k * estimate.sigma, which would double-round (the 6dp-quantized sigma
                # times k is not the 6dp quantization of k*sigma).
                with localcontext() as ctx:
                    ctx.prec = _COMPUTE_PREC
                    clamped = estimate.radicand if estimate.radicand > 0 else Decimal(0)
                    try:
                        raw_es = compute_parametric_es(clamped.sqrt(), es_multiplier=es_multiplier)
                        # The quantize is INSIDE the try — the var_kernel:111 precedent, which
                        # guards the identical operation. Because k_c > z_c there is a band where
                        # the kernel's z*sigma quantize succeeds but k*sigma raises
                        # InvalidOperation (6dp would need more than prec-50 digits), and the
                        # magnitude gate cannot cover it: the gate runs AFTER this line. It is
                        # UNREACHABLE today (column-legal pins cap sigma ~1e31; this needs ~4e43,
                        # i.e. ~1e12 factors in one run) — defense-in-depth, symmetric with the
                        # kernel it mirrors, per the PA-4 defensive-gate precedent.
                        plain_value = raw_es.quantize(_SIGMA_QUANTUM, rounding=ROUND_HALF_UP)
                    except EsKernelError as exc:  # defense-in-depth; binder-unreachable
                        gaps.append(f"es-kernel:{exc.reason}:{exc}")
                        return [], gaps
                    except InvalidOperation:  # defense-in-depth; binder-unreachable (see above)
                        gaps.append("es-kernel:magnitude-out-of-range")
                        return [], gaps
                plain_metric = METRIC_TYPE_ES_PARAMETRIC
            # The magnitude gate runs on the value ACTUALLY STORED. k_c > z_c at every confidence,
            # so an ES can breach the envelope where its VaR did not — the band is wide, not a
            # knife-edge (sigma in [3.75e21, 4.30e21) at c=0.99, ~13% of the envelope). Gating
            # z*sigma while storing k*sigma would be a real PG overflow 500. DELIBERATELY under
            # the DEFAULT context (prec 28) — see the total path's note below.
            if abs(estimate.sigma) >= _MAX_RESULT_ABS or abs(plain_value) >= _MAX_RESULT_ABS:
                # Column-legal-but-extreme inputs can produce sigma beyond Numeric(28,6): a
                # committed FAILED run with evidence, never a PG overflow 500 (2026-07 review).
                # Name the value that ACTUALLY breached (ES-1 review): an ES trips this gate at a
                # sigma the VaR passes (k_c > z_c), so reporting sigma alone showed a validator an
                # in-envelope number next to an unexplained refusal — on a governed-number platform
                # the FAILED run IS the deliverable, and its recorded reason has to be true.
                breach = "sigma" if abs(estimate.sigma) >= _MAX_RESULT_ABS else plain_metric
                breached_value = (
                    estimate.sigma if abs(estimate.sigma) >= _MAX_RESULT_ABS else plain_value
                )
                gaps.append(f"magnitude-out-of-range:{breach}:{breached_value:E}")
                return [], gaps
            row = VarResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                exposure_run_id=parsed.exposure_run_id,
                covariance_run_id=parsed.covariance_run_id,
                metric_type=plain_metric,
                base_currency=parsed.base_currency,
                confidence_level=declared.confidence_level,
                horizon_days=declared.horizon_days,
                # z_score is echoed on an ES row too — it is NOT the ES arithmetic (k is), but the
                # live ck_var_result_parametric_not_null CHECK forces it non-NULL for every
                # non-VAR_HISTORICAL row, and that CHECK is ORM-invisible (PG-only). See the
                # registered limitation: an ES row reproduces THROUGH its model_version's declared
                # es_multiplier, never from the row's own columns.
                z_score=declared.z_score,
                sigma=estimate.sigma,
                var_value=plain_value,
                n_factors=parsed.n_factors,
                n_observations=parsed.n_observations,
                window_start=parsed.window_start,
                window_end=parsed.window_end,
            )
            return [row], gaps

        # --- PA-4 total path: factor variance (the SAME clamped radicand the plain family
        # would sqrt) + the diagonal idiosyncratic residual leg. ---
        assert appraisal_days is not None  # guaranteed by the is_total branch above
        factor_var = estimate.radicand if estimate.radicand > 0 else Decimal(0)
        try:
            residual = total_var_residual(
                factor_var,
                [
                    ResidualInstrument(
                        instrument_id=pw.instrument_id,
                        market_value=mv_by_instrument[pw.instrument_id],
                        residual_stdev_period=pw.residual_stdev,
                        mean_period_calendar_days=Decimal(appraisal_days),
                    )
                    for pw in proxy_weights
                ],
                trading_days_per_year=VAR_TOTAL_TRADING_DAYS_PER_YEAR,
                calendar_days_per_year=VAR_TOTAL_CALENDAR_DAYS_PER_YEAR,
            )
        except VarTotalKernelError as exc:
            gaps.append(f"total-var-kernel:{exc.reason}:{exc}")
            return [], gaps

        with localcontext() as ctx:
            ctx.prec = _COMPUTE_PREC
            if es_multiplier is None:
                raw_var_value = declared.z_score * residual.sigma_total
            else:
                # ES-1 (OD-ES-1-D): the SAME multiplier over PA-4's sigma_total. A sigma-multiple
                # is exactly as honest as its sigma — the ES-total leg therefore inherits BT-2's
                # smoothing doctrine and PA-4's residual limitations verbatim (registered).
                try:
                    raw_var_value = compute_parametric_es(
                        residual.sigma_total, es_multiplier=es_multiplier
                    )
                except EsKernelError as exc:  # defense-in-depth; binder-unreachable
                    gaps.append(f"es-kernel:{exc.reason}:{exc}")
                    return [], gaps
        if (
            abs(residual.sigma_total) >= _MAX_RESULT_ABS
            or abs(raw_var_value) >= _MAX_RESULT_ABS
            or abs(residual.residual_variance) >= _MAX_RESIDUAL_VARIANCE_ABS
        ):
            # The plain-family magnitude gate, extended to the total σ/VaR/residual_variance.
            # DELIBERATELY under the DEFAULT context (prec 28): abs() ROUNDS the prec-50 value
            # before comparing, which CLOSES the column-overflow windows — every raw value in
            # [1E22−5E-7, 1E22) / [1E18−5E-21, 1E18) rounds UP to the bound and trips the gate,
            # so nothing that passes can overflow Numeric(28,6)/(38,20) at INSERT (probe-verified
            # at all three boundaries, 2026-07 review). Do NOT move this inside the prec-50
            # localcontext: a prec-50 abs() reopens the window (quantize then mints exactly the
            # bound → a PG NumericValueOutOfRange 500 instead of this governed FAILED run).
            # Name the value that ACTUALLY breached (ES-1 review) — with k_c > z_c an ES-total can
            # trip where its VaR-total would not, and "sigma-total: <in-range value>" would send a
            # validator hunting a gate bug instead of reading the real cause.
            if abs(residual.sigma_total) >= _MAX_RESULT_ABS:
                breach, breached_value = "sigma-total", residual.sigma_total
            elif abs(residual.residual_variance) >= _MAX_RESIDUAL_VARIANCE_ABS:
                breach, breached_value = "residual-variance", residual.residual_variance
            else:
                breach = METRIC_TYPE_ES_PARAMETRIC if es_multiplier else "var-total"
                breached_value = raw_var_value
            gaps.append(f"magnitude-out-of-range:{breach}:{breached_value:E}")
            return [], gaps

        with localcontext() as ctx:
            ctx.prec = _COMPUTE_PREC
            sigma_q = residual.sigma_total.quantize(_SIGMA_QUANTUM, rounding=ROUND_HALF_UP)
            var_value_q = raw_var_value.quantize(_SIGMA_QUANTUM, rounding=ROUND_HALF_UP)
            residual_variance_q = residual.residual_variance.quantize(
                _RESIDUAL_VARIANCE_QUANTUM, rounding=ROUND_HALF_UP
            )
        row = VarResult(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            exposure_run_id=parsed.exposure_run_id,
            covariance_run_id=parsed.covariance_run_id,
            metric_type=(
                METRIC_TYPE_VAR_PARAMETRIC_TOTAL
                if es_multiplier is None
                else METRIC_TYPE_ES_PARAMETRIC
            ),
            base_currency=parsed.base_currency,
            confidence_level=declared.confidence_level,
            horizon_days=declared.horizon_days,
            z_score=declared.z_score,
            sigma=sigma_q,
            var_value=var_value_q,
            n_factors=parsed.n_factors,
            n_observations=parsed.n_observations,
            window_start=parsed.window_start,
            window_end=parsed.window_end,
            residual_variance=residual_variance_q,
            # BT-2: the MAX cited-estimate age at this run's as-of (evidence; NULL when nothing
            # was measurable — no proxied instruments, or an ungated v1 whose estimate snapshot
            # is unresolvable). The GATE already ran pre-create; this is the echo.
            estimate_age_days=estimate_age_days,
        )
        return [row], gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_VAR,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="VaR run output sanity (radicand within the declared PSD quantization floor)",
        rule_target_entity_type="var_result",
        result_entity_type="var_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",  # verbatim P3-5 format
        # API-1b (OD-API-1b-B): the ROOT copies forward from the pinned factor-exposure run
        # (re-resolved above in BOTH paths); NULL propagates faithfully if that run was
        # snapshot-consume-rooted (OD-API-1b-D).
        scope_portfolio_id=pinned_exposure_run.scope_portfolio_id,
    )
    return VarRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def run_var_unified(
    session: Session,
    *,
    acting_tenant: str,
    actor: VarActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str | None = None,
    covariance_run_id: str | None = None,
    private_covariance_run_id: str | None = None,
    snapshot_id: str | None = None,
) -> VarRunResult:
    """Run the UNIFIED public+private parametric VaR (PPF-3, ``risk.var.parametric_unified``, the
    20th governed number) — the §2.1 arc's final assembly. Its OWN binder path (the plain/total
    ``run_var`` stays byte-untouched — OD-3-A). Build-in-request (``exposure_run_id`` +
    ``covariance_run_id`` + ``private_covariance_run_id``: builds a unified ``VAR_INPUT`` snapshot)
    or consume-existing (``snapshot_id``, which MUST carry the unified predicate). Both paths
    adjudicate the pinned content pre-create. The three NON-OVERLAPPING legs (OD-3-G REPARTITION):
    ``x'Σx`` (public factor) + ``p'(Ω_pp/d_t)·p`` (pure-private block) + the residual over the
    NON-private-segment members (the builder pinned only those). See the module docstring for the
    failure model + the AD-014 / CTRL-003 invariants."""
    if not code_version:
        raise VarInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise VarInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise VarInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise VarInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if snapshot_id is not None and (
        exposure_run_id is not None
        or covariance_run_id is not None
        or private_covariance_run_id is not None
    ):
        raise VarInputError(
            "ambiguous input — pass either snapshot_id or the build arguments (exposure_run_id/"
            "covariance_run_id/private_covariance_run_id), not both"
        )
    # Inventory-before-use + model identity: MUST be the unified code (NOT the 2x2 VaR/ES family —
    # this binder never dispatches on total/es; the unified number is VaR-only, v1).
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=VAR_UNIFIED_MODEL_CODE,
    )
    declared: VarParameters = declared_var_parameters(session, version)
    appraisal_days = declared_unified_appraisal_days(session, version)
    max_estimate_age_days = declared_max_estimate_age_days(session, version)

    # --- Bind the unified snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_VAR_INPUT:
            raise VarInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_VAR_INPUT}"
            )
        if snapshot.binding_predicate_version != VAR_UNIFIED_BINDING_PREDICATE:
            raise VarInputError(
                f"snapshot {snapshot_id} predicate {snapshot.binding_predicate_version!r} != the "
                f"unified {VAR_UNIFIED_BINDING_PREDICATE!r} — a plain/total snapshot pins no "
                f"pure-private block; build it under the unified model"
            )
    else:
        if not (exposure_run_id and covariance_run_id and private_covariance_run_id):
            raise VarInputError(
                "exposure_run_id + covariance_run_id + private_covariance_run_id are required to "
                "build a unified VaR snapshot"
            )
        exposure_run = resolve_factor_exposure_run(
            session, str(exposure_run_id), acting_tenant=acting_tenant
        )
        if exposure_run.status != RunStatus.COMPLETED.value:
            raise VarInputError(f"exposure run {exposure_run_id} status != COMPLETED")
        covariance_run = resolve_covariance_run(
            session, str(covariance_run_id), acting_tenant=acting_tenant
        )
        if covariance_run.status != RunStatus.COMPLETED.value:
            raise VarInputError(f"covariance run {covariance_run_id} status != COMPLETED")
        private_run = resolve_private_covariance_run(
            session, str(private_covariance_run_id), acting_tenant=acting_tenant
        )
        if private_run.status != RunStatus.COMPLETED.value:
            raise VarInputError(
                f"private covariance run {private_covariance_run_id} status != COMPLETED"
            )
        snapshot = build_var_unified_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            covariance_run_id=str(covariance_run_id),
            private_covariance_run_id=str(private_covariance_run_id),
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths) ---
    try:
        comps = list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        exposure_raw, covariance_raw = _parse_pins(comps)
        # Split the COVARIANCE pins by frequency: DAILY = the public Sigma; APPRAISAL = Omega_pp.
        daily_cov_raw = [r for r in covariance_raw if r.get("frequency") == FREQUENCY_DAILY]
        appraisal_cov_raw = [r for r in covariance_raw if r.get("frequency") == FREQUENCY_APPRAISAL]
        parsed = _adjudicate_pins(exposure_raw, daily_cov_raw)  # the public factor leg (DAILY)
        omega_pp, omega_run_id = _adjudicate_private_covariance(appraisal_cov_raw)
        with localcontext() as ctx:
            ctx.prec = _COMPUTE_PREC  # prec-50 MV sum (the total-path precedent)
            mv_by_instrument: dict[str, Decimal] = {}
            for r in exposure_raw:
                iid = str(r["instrument_id"]).lower()
                mv_by_instrument[iid] = mv_by_instrument.get(iid, Decimal(0)) + Decimal(
                    r["exposure_amount"]
                )
        # Split PROXY_MAPPING pins by method: REGRESSION = the residual leg; MANUAL = the p vector.
        mapping_raw, weight_raw = _parse_total_pins(comps)
        regression_mapping_raw = [
            m for m in mapping_raw if m.get("mapping_method") == MAPPING_METHOD_REGRESSION
        ]
        manual_mapping_raw = [
            m for m in mapping_raw if m.get("mapping_method") == MAPPING_METHOD_MANUAL
        ]
        proxy_weights = _adjudicate_total_proxies(
            regression_mapping_raw,
            weight_raw,
            base_currency=parsed.base_currency,
            exposure_instrument_ids=set(mv_by_instrument),
        )
        p_by_segment = _build_p_vector(manual_mapping_raw, mv_by_instrument)
    except VarInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise VarInputError(
            f"pinned content is not a well-formed v1 unified input ({type(exc).__name__})"
        ) from exc

    estimate_age_days = _estimate_age_days(
        session,
        proxy_weights,
        acting_tenant=str(acting_tenant),
        window_end=parsed.window_end,
        max_estimate_age_days=max_estimate_age_days,
    )

    # Re-resolve ALL THREE provenance ids under the acting tenant (run_type + COMPLETED) before
    # they hit hard-FK columns — PG FK checks bypass RLS (the SSO-1/API-1 cross-tenant lesson).
    pinned_exposure_run = resolve_factor_exposure_run(
        session, parsed.exposure_run_id, acting_tenant=acting_tenant
    )
    if pinned_exposure_run.status != RunStatus.COMPLETED.value:
        raise VarInputError(f"the pinned exposure run {parsed.exposure_run_id} is not COMPLETED")
    pinned_covariance_run = resolve_covariance_run(
        session, parsed.covariance_run_id, acting_tenant=acting_tenant
    )
    if pinned_covariance_run.status != RunStatus.COMPLETED.value:
        raise VarInputError(
            f"the pinned covariance run {parsed.covariance_run_id} is not COMPLETED"
        )
    pinned_private_run = resolve_private_covariance_run(
        session, omega_run_id, acting_tenant=acting_tenant
    )
    if pinned_private_run.status != RunStatus.COMPLETED.value:
        raise VarInputError(f"the pinned Omega_pp run {omega_run_id} is not COMPLETED")

    def _compute(run: CalculationRun) -> tuple[list[VarResult], list[str]]:
        estimate = compute_parametric_var(
            parsed.exposure_rows, parsed.covariance, z_score=declared.z_score
        )
        gaps: list[str] = []
        if estimate.sigma is None or estimate.var_value is None:
            gaps.append(f"non-psd-radicand:{estimate.radicand:E}<-tol:{estimate.tolerance:E}")
            return [], gaps
        factor_var = estimate.radicand if estimate.radicand > 0 else Decimal(0)
        try:
            # Leg 3 (REPARTITIONED): the residual over the pinned proxy_weights, which the builder
            # already restricted to NON-private-segment members. factor_var=0 -> just the residual.
            residual = total_var_residual(
                Decimal(0),
                [
                    ResidualInstrument(
                        instrument_id=pw.instrument_id,
                        market_value=mv_by_instrument[pw.instrument_id],
                        residual_stdev_period=pw.residual_stdev,
                        mean_period_calendar_days=Decimal(appraisal_days),
                    )
                    for pw in proxy_weights
                ],
                trading_days_per_year=VAR_TOTAL_TRADING_DAYS_PER_YEAR,
                calendar_days_per_year=VAR_TOTAL_CALENDAR_DAYS_PER_YEAR,
            )
        except VarTotalKernelError as exc:
            gaps.append(f"total-var-kernel:{exc.reason}:{exc}")
            return [], gaps
        try:
            omega_d = daily_omega(
                omega_pp,
                appraisal_days,
                trading_days_per_year=VAR_TOTAL_TRADING_DAYS_PER_YEAR,
                calendar_days_per_year=VAR_TOTAL_CALENDAR_DAYS_PER_YEAR,
            )
            private_var = private_block_variance(p_by_segment, omega_d)
            sigma_u = sigma_unified(factor_var, private_var, residual.residual_variance)
        except VarUnifiedKernelError as exc:
            gaps.append(f"var-unified-kernel:{exc.reason}:{exc}")
            return [], gaps
        with localcontext() as ctx:
            ctx.prec = _COMPUTE_PREC
            raw_var_value = declared.z_score * sigma_u
        # The magnitude gate (DEFAULT prec-28 abs, closing the column-overflow windows — the PA-4
        # note), extended to sigma / VaR / private_variance / residual_variance.
        if (
            abs(sigma_u) >= _MAX_RESULT_ABS
            or abs(raw_var_value) >= _MAX_RESULT_ABS
            or abs(private_var) >= _MAX_RESIDUAL_VARIANCE_ABS
            or abs(residual.residual_variance) >= _MAX_RESIDUAL_VARIANCE_ABS
        ):
            if abs(sigma_u) >= _MAX_RESULT_ABS:
                breach, breached_value = "sigma-unified", sigma_u
            elif abs(private_var) >= _MAX_RESIDUAL_VARIANCE_ABS:
                breach, breached_value = "private-variance", private_var
            elif abs(residual.residual_variance) >= _MAX_RESIDUAL_VARIANCE_ABS:
                breach, breached_value = "residual-variance", residual.residual_variance
            else:
                breach, breached_value = "var-unified", raw_var_value
            gaps.append(f"magnitude-out-of-range:{breach}:{breached_value:E}")
            return [], gaps
        with localcontext() as ctx:
            ctx.prec = _COMPUTE_PREC
            sigma_q = sigma_u.quantize(_SIGMA_QUANTUM, rounding=ROUND_HALF_UP)
            var_value_q = raw_var_value.quantize(_SIGMA_QUANTUM, rounding=ROUND_HALF_UP)
            private_variance_q = private_var.quantize(
                _RESIDUAL_VARIANCE_QUANTUM, rounding=ROUND_HALF_UP
            )
            residual_variance_q = residual.residual_variance.quantize(
                _RESIDUAL_VARIANCE_QUANTUM, rounding=ROUND_HALF_UP
            )
        row = VarResult(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            exposure_run_id=parsed.exposure_run_id,
            covariance_run_id=parsed.covariance_run_id,  # the PUBLIC Sigma run
            metric_type=METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
            base_currency=parsed.base_currency,
            confidence_level=declared.confidence_level,
            horizon_days=declared.horizon_days,
            z_score=declared.z_score,
            sigma=sigma_q,
            var_value=var_value_q,
            n_factors=parsed.n_factors,
            n_observations=parsed.n_observations,
            window_start=parsed.window_start,
            window_end=parsed.window_end,
            residual_variance=residual_variance_q,  # leg-3 sum over NON-private-segment members
            estimate_age_days=estimate_age_days,
            private_variance=private_variance_q,  # PPF-3: the pure-private block p'(Omega/d_t)p
            private_covariance_run_id=omega_run_id,  # PPF-3: the Omega_pp provenance
        )
        return [row], gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_VAR,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="Unified VaR run output sanity (radicand within the declared PSD floor)",
        rule_target_entity_type="var_result",
        result_entity_type="var_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
        scope_portfolio_id=pinned_exposure_run.scope_portfolio_id,
    )
    return VarRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_vars(session: Session, *, run_id: str, acting_tenant: str) -> list[VarResult]:
    """The ``var_result`` rows of a run (tenant-scoped; one row per metric in v1)."""
    return list(
        session.execute(
            select(VarResult)
            .where(
                VarResult.calculation_run_id == str(run_id),
                VarResult.tenant_id == str(acting_tenant),
            )
            .order_by(VarResult.metric_type)
        )
        .scalars()
        .all()
    )


def resolve_var_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve a VAR ``calculation_run`` by ``run_id`` with an EXPLICIT tenant predicate +
    ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable refusal
    evidence). Raises :class:`VarRunNotVisible` on a hidden/unknown id or a non-VaR run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_VAR,
        not_visible=VarRunNotVisible,
    )


def resolve_var(session: Session, var_id: str, *, acting_tenant: str) -> VarResult:
    """Resolve one ``var_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(VarResult).where(
            VarResult.id == str(var_id),
            VarResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarNotVisible(str(var_id))
    return row


def list_var_results(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    metric_type: str | None = None,
    as_of=None,  # noqa: ANN001  (datetime | None — the API-1 run cutoff)
) -> list[VarResult]:
    """API-1b (Class C, OD-API-1b-C): governed VaR rows for a portfolio, resolved via the run's
    ROOT ``scope_portfolio_id`` — ``var_result`` carries no ``portfolio_id`` (the scope lives on the
    run, stamped at creation, since a VaR run is subtree-scoped). All VaR flavors share
    ``run_type=VAR`` (``metric_type`` distinguishes parametric/total/HS/ES); an optional
    ``metric_type`` narrows to one flavor. Silent-empty on an unknown/foreign/NULL-scope portfolio
    (a snapshot-consume-rooted or pre-0046 run is honestly unresolvable, OD-API-1b-D).
    ``as_of=None`` = now."""
    return list_governed_results(
        session,
        VarResult,
        acting_tenant=acting_tenant,
        filters=(
            (CalculationRun.scope_portfolio_id, portfolio_id),
            (VarResult.metric_type, metric_type),
        ),
        run_type=RUN_TYPE_VAR,
        as_of=as_of,
        order_by=VarResult.metric_type,
    )


def latest_var_for_portfolio(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    metric_type: str | None = None,
    as_of=None,  # noqa: ANN001
) -> list[VarResult]:
    """API-1b latest-resolver: the newest COMPLETED VaR run scoped to the portfolio (its metric
    row(s), or the one ``metric_type``). Empty when the portfolio has no scoped COMPLETED run — the
    flagship 'latest VaR for portfolio P' read the UI/agent most wants."""
    return latest_run_rows(
        list_var_results(
            session,
            acting_tenant=acting_tenant,
            portfolio_id=portfolio_id,
            metric_type=metric_type,
            as_of=as_of,
        )
    )
