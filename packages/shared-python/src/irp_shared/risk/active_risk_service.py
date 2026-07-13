"""Ex-ante active-risk (tracking-error) binder (P3-7, ENT-027 — the SIXTH governed risk number
and the SECOND derived-of-derived one — the VaR binder's sibling).

``run_active_risk`` produces the ONE ``active_risk_result`` summary row ONLY when bound to a
``dataset_snapshot`` (``ACTIVE_RISK_INPUT``, pinning EVERY result row of the two consumed upstream
governed runs + the covariance FACTOR definitions + the captured BENCHMARK membership) + a complete
``calculation_run`` + a **REGISTERED ``model_version`` OF THE ACTIVE-RISK MODEL** (AD-014 / FW-RUN /
TR-15 / CTRL-003 — the ``run_var`` exemplar mirrored step-for-step). Unlike parametric VaR the model
carries NO numeric parameter (no confidence/horizon/z): the methodology identity is the registered
``code_version`` alone (OD-P3-7-D), so there is no ``declared_*_parameters`` call.

The number is the factor-model ex-ante tracking error (``irp_shared.risk.active_risk_kernel``):
``TE = sqrt(w_a' Sigma w_a)`` over the ACTIVE weights ``w_a = w_p - w_b`` (portfolio minus
benchmark, per CURRENCY factor). The active-weight construction is the binder's own arithmetic over
the pinned content (PURE — no live read, the AD-014 invariant):

- ``w_p[f]  = (sum of pinned FACTOR_EXPOSURE exposure_amount for factor f) / portfolio_value``,
  ``portfolio_value = sum of ALL pinned exposure_amount`` (the net book value, base currency);
- ``w_b[f]  = (sum of pinned BENCHMARK constituent weight mapped currency->factor) / sum(weight)``,
  the constituent currency mapped to a factor through the SAME ``build_factor_index`` the portfolio
  side uses (methodological symmetry — a Barra-style currency partition);
- ``w_a = w_p - w_b`` over the UNION factor set; ``Sigma`` from the pinned COVARIANCE rows.

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned content** —
FACTOR_EXPOSURE / COVARIANCE / FACTOR / BENCHMARK captured strings; it makes **NO** live
result/factor/benchmark read, so a later upstream RE-RUN or benchmark restatement cannot move a
historical tracking error (test-proven).

Failure model (the P3-5 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing prerequisites; an unregistered or WRONG-MODEL version; a
  non-COMPLETED / cross-tenant / empty upstream run; a wrong-purpose snapshot; **pinned content that
  is not a well-formed v1 input** — zero rows of a required kind, mixed-run rows, a non-3-letter
  ``base_currency``, wrong covariance vocabulary/window uniformity, a mismatched or DUPLICATE
  FACTOR-definition pin, an exposure factor NOT covered by the covariance set, a missing canonical
  pair, a **NULL/blank ``constituent_currency`` or ``currency_code``**, an UNMAPPABLE constituent
  currency, ``sum(weight) <= 0``, a zero portfolio value, or JSON-null/non-object fields):
  **raise BEFORE ``create_run``** => ZERO run + ZERO rows + ZERO run-audit. A snapshot minted
  elsewhere cannot smuggle an uncovered factor or an unmapped currency past the gate. **NO
  zero-weight / header-currency imputation, ever.**
- **Post-create FAILED** (the OD-P3-5-G radicand gate — a genuinely non-PSD pinned matrix, REACHABLE
  via a hand-minted snapshot; PLUS a result-magnitude gate — a column-legal-but-extreme pin whose te
  overflows the ``Numeric(20,12)`` range, whether caught by the ``_MAX_RESULT_ABS`` envelope or by
  the kernel's 12dp-quantize guard, cannot raise a 500): FAILED run (``outcome='failure'``) +
  ``DATA.VALIDATE`` DQ evidence + ZERO rows + a radicand-/magnitude-naming ``failure_reason``.
- **Emit-path** raises propagate => the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``risk -> {snapshot, marketdata, calc, model, lineage, dq, audit, db}``; imports NO
live result reader into the COMPUTE path; imports NO numpy/simulation/quantile symbol; nothing
imports ``risk``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.benchmark import resolve_benchmark
from irp_shared.risk.active_risk_kernel import ActiveRiskKernelError, compute_tracking_error
from irp_shared.risk.bootstrap import ACTIVE_RISK_MODEL_CODE, assert_model_version_of
from irp_shared.risk.covariance_service import resolve_covariance_run
from irp_shared.risk.events import (
    METRIC_TYPE_TRACKING_ERROR,
    RUN_TYPE_ACTIVE_RISK,
    ActiveRiskActor,
)
from irp_shared.risk.factor_kernel import FactorKernelError, FactorPin, build_factor_index
from irp_shared.risk.factor_service import resolve_factor_exposure_run
from irp_shared.risk.models import ActiveRiskResult
from irp_shared.snapshot import (
    COMPONENT_KIND_BENCHMARK,
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    PURPOSE_ACTIVE_RISK_INPUT,
    SnapshotActor,
    build_active_risk_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the P3-1/3/4/5 pattern).
_COMPLETENESS_RULE_CODE = "risk.active_risk.completeness"
#: The v1 covariance-input vocabulary the pinned matrix must carry (the P3-4 output contract).
_REQUIRED_STATISTIC_TYPE = "COVARIANCE"
_REQUIRED_RETURN_TYPE = "SIMPLE"
_REQUIRED_FREQUENCY = "DAILY"
#: Source-column magnitude bounds: a pinned value EXCEEDING its origin column's envelope cannot be
#: a genuine governed/captured row (exposure_amount Numeric(28,6) < 1E22; covariance Numeric(38,20)
#: < 1E18; weight Numeric(20,12) < 1E8) — refused pre-create (the P3-5 precedent: an absurd
#: hand-minted pin otherwise crashes a downstream quantize/overflow with no durable evidence).
_MAX_EXPOSURE_ABS = Decimal("1E22")
_MAX_COVARIANCE_ABS = Decimal("1E18")
_MAX_WEIGHT_ABS = Decimal("1E8")
#: The active_risk_result.portfolio_value column envelope (Numeric(28,6)): the summed net book value
#: (evidence) is refused pre-create if it exceeds the column so the stored evidence never overflows.
_MAX_PORTFOLIO_VALUE_ABS = Decimal("1E22")
#: The active_risk_result.te_value column envelope (Numeric(20,12)): a column-legal-but-extreme pin
#: can still drive te ~1E8+ — gate it into a committed FAILED run, never a PG overflow 500.
_MAX_RESULT_ABS = Decimal("1E7")
#: Compute precision for the active-weight construction (division/normalization) — the kernel's
#: 50-digit accumulation precedent, so the weight vector is derived at the same fidelity.
_WEIGHT_COMPUTE_PREC = 50


class ActiveRiskInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Maps to 422."""


class ActiveRiskNotVisible(Exception):
    """Raised when an ``active_risk_result`` id is not visible in the acting tenant scope."""

    def __init__(self, active_risk_id: str) -> None:
        super().__init__(
            f"active_risk_result {active_risk_id} is not visible in the current tenant"
        )
        self.active_risk_id = str(active_risk_id)


class ActiveRiskRunNotVisible(Exception):
    """Raised when an active-risk ``calculation_run`` id is not visible in the acting tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"active-risk run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class ActiveRiskRunResult:
    """The outcome of ``run_active_risk``: the ``calculation_run`` + status + the summary row
    produced. ``status`` is ``COMPLETED`` (with ``rows`` holding the ONE summary row) or ``FAILED``
    (the radicand/magnitude gate: a committed FAILED run + ZERO rows + a naming ``failure_reason``).
    """

    run: CalculationRun
    status: str
    rows: list[ActiveRiskResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the kernel arguments (the constructed active-weight vector +
    the covariance map) + the run-uniform captured descriptors + the evidence aggregates."""

    active_weights: dict[str, Decimal]  # factor_id lowercase -> w_a (w_p - w_b)
    covariance: dict[tuple[str, str], Decimal]
    exposure_run_id: str
    covariance_run_id: str
    benchmark_id: str
    benchmark_effective_date: date
    base_currency: str
    portfolio_value: Decimal
    n_factors: int
    n_constituents: int


def _is_present_currency(value: Any) -> bool:
    """A captured currency is PRESENT only if it is a non-blank string. NULL **and** empty/
    whitespace are the same named-gap refusal (``""`` is not ``None``, so the ``is None`` test alone
    would let a blank denomination through ``build_factor_index`` and defeat the OQ-6 no-imputation
    rule — review)."""
    return isinstance(value, str) and bool(value.strip())


def _parse_pins(
    comps: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw exposure/covariance/factor/benchmark row dicts
    (PURE — no live read; the AD-014 invariant)."""
    exposure_raw: list[dict[str, Any]] = []
    covariance_raw: list[dict[str, Any]] = []
    factor_raw: list[dict[str, Any]] = []
    benchmark_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
            exposure_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_COVARIANCE:
            covariance_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_FACTOR:
            factor_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_BENCHMARK:
            benchmark_raw.append(data)
    return exposure_raw, covariance_raw, factor_raw, benchmark_raw


def _adjudicate_covariance(
    covariance_raw: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], Decimal], str]:
    """PRE-CREATE adjudication of the pinned covariance matrix (the VaR contract verbatim): single-
    run provenance; the v1 COVARIANCE/SIMPLE/DAILY vocabulary + a uniform window; canonical pair
    order; no duplicate/reversed pair; the source-column envelope. Returns the canonical-pair map +
    the single covariance run id. Raises :class:`ActiveRiskInputError`."""
    if not covariance_raw:
        raise ActiveRiskInputError(
            "the snapshot pins no COVARIANCE rows — not an active-risk input"
        )
    covariance_run_ids = {str(r["calculation_run_id"]).lower() for r in covariance_raw}
    if len(covariance_run_ids) != 1:
        raise ActiveRiskInputError("the pinned covariance rows span multiple runs — refused")
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
        raise ActiveRiskInputError(
            "the pinned covariance rows carry a non-uniform window/vocabulary"
        )
    statistic_type, return_type, frequency, _n_obs, _w_start, _w_end = next(iter(windows))
    if (
        statistic_type != _REQUIRED_STATISTIC_TYPE
        or return_type != _REQUIRED_RETURN_TYPE
        or frequency != _REQUIRED_FREQUENCY
    ):
        raise ActiveRiskInputError(
            f"the pinned covariance vocabulary ({statistic_type!r}/{return_type!r}/{frequency!r}) "
            f"is not the v1 COVARIANCE/SIMPLE/DAILY contract"
        )
    covariance: dict[tuple[str, str], Decimal] = {}
    for r in covariance_raw:
        pair = (str(r["factor_id_1"]).lower(), str(r["factor_id_2"]).lower())
        if pair[0] > pair[1]:
            # Non-canonical storage order is NOT a well-formed v1 input (OD-P3-4-D) — accepting it
            # verbatim would let a REVERSED duplicate carry a conflicting value past the dup check.
            raise ActiveRiskInputError(f"non-canonical covariance pair order {pair} — refused")
        if pair in covariance:
            raise ActiveRiskInputError(f"duplicate covariance pair {pair} — refused")
        value = Decimal(r["covariance_value"])
        if abs(value) >= _MAX_COVARIANCE_ABS:
            raise ActiveRiskInputError(
                "a pinned covariance_value exceeds its source-column envelope — refused"
            )
        covariance[pair] = value
    return covariance, next(iter(covariance_run_ids))


def _adjudicate_pins(
    exposure_raw: list[dict[str, Any]],
    covariance_raw: list[dict[str, Any]],
    factor_raw: list[dict[str, Any]],
    benchmark_raw: list[dict[str, Any]],
) -> _ParsedInput:
    """PRE-CREATE adjudication of the FULL pinned input (both entry paths). Adjudicates the
    covariance matrix; the single-run/uniform-currency exposure vector; the FACTOR-definition set
    (== the covariance factor set, no NULL/duplicate currency); the single-``(benchmark,
    effective_date)`` membership (no NULL/unmappable ``constituent_currency``, no duplicate
    constituent); then CONSTRUCTS the active weights ``w_a = w_p - w_b`` and re-verifies COVERAGE
    (every active factor in the covariance set + every canonical pair present — NO imputation).
    Raises :class:`ActiveRiskInputError`."""
    covariance, covariance_run_id = _adjudicate_covariance(covariance_raw)
    covariance_factors = {fid for pair in covariance for fid in pair}

    # --- Portfolio side: single-run exposure vector, uniform 3-letter base_currency. ---
    if not exposure_raw:
        raise ActiveRiskInputError(
            "the snapshot pins no FACTOR_EXPOSURE rows — not an active-risk input (an empty "
            "portfolio vector is refused)"
        )
    exposure_run_ids = {str(r["calculation_run_id"]).lower() for r in exposure_raw}
    if len(exposure_run_ids) != 1:
        raise ActiveRiskInputError("the pinned exposure rows span multiple runs — refused")
    base_currencies = {r["base_currency"] for r in exposure_raw}
    if len(base_currencies) != 1:
        raise ActiveRiskInputError(
            f"the pinned exposure rows carry mixed base currencies {sorted(base_currencies)} — "
            f"refused"
        )
    base_currency = next(iter(base_currencies))
    if not isinstance(base_currency, str) or len(base_currency) != 3:
        # A uniformly-NULL or non-3-letter base_currency ({None} / {"USDX"} pass the set-of-one
        # check) would otherwise reach the NOT-NULL varchar(3) column as a post-create 500 (review).
        raise ActiveRiskInputError(
            "the pinned exposure base_currency is not a 3-letter code — refused"
        )

    # --- The FACTOR-definition set: EXACTLY the covariance factor set; NO duplicate id (a repeated
    # id with a DIFFERENT currency_code collapses in a set and would silently merge two currencies
    # onto one factor — review) and NO blank/NULL currency (an ambiguous partition). ---
    factor_pins: list[FactorPin] = []
    factor_ids_seen: set[str] = set()
    for f in factor_raw:
        fid = str(f["id"]).lower()
        if fid in factor_ids_seen:  # a repeated id defeats the set-equality check below
            raise ActiveRiskInputError(f"duplicate pinned FACTOR definition {fid} — refused")
        factor_ids_seen.add(fid)
        currency_code = f["currency_code"]
        if not _is_present_currency(currency_code):
            raise ActiveRiskInputError(
                f"FACTOR {fid} has a blank/NULL currency_code — refused (no imputation)"
            )
        factor_pins.append(
            FactorPin(
                id=fid,
                factor_code=f["factor_code"],
                factor_family=f["factor_family"],
                currency_code=currency_code,
            )
        )
    if factor_ids_seen != covariance_factors:
        raise ActiveRiskInputError(
            "the pinned FACTOR definitions do not match the covariance factor set exactly — "
            "refused (the currency->factor map must be complete and exact)"
        )
    try:
        index = build_factor_index(factor_pins)  # currency_code -> FactorPin (NULL/dup currency)
    except FactorKernelError as exc:
        raise ActiveRiskInputError(
            f"the pinned FACTOR set is not a valid partition ({exc})"
        ) from exc

    # --- Benchmark side: single (benchmark, effective_date); duplicate constituent + NULL/blank/
    # unmappable currency refused. ---
    if not benchmark_raw:
        raise ActiveRiskInputError(
            "the snapshot pins no BENCHMARK constituents — not an active-risk input"
        )
    benchmark_ids = {str(r["benchmark_id"]).lower() for r in benchmark_raw}
    if len(benchmark_ids) != 1:
        raise ActiveRiskInputError("the pinned benchmark constituents span multiple benchmarks")
    effective_dates = {r["effective_date"] for r in benchmark_raw}
    if len(effective_dates) != 1:
        raise ActiveRiskInputError(
            "the pinned benchmark constituents span multiple effective dates — refused"
        )

    # --- Numeric region at COMPUTE precision (all pinned-value accumulation, normalization, and the
    # active-weight construction): a column-legal Numeric(28,6) value carries up to 28 significant
    # digits, so an intermediate sum can need 29 — the default 28-digit context would silently round
    # it (masking a zero-sum book past the ==0 refusal, or corrupting portfolio_value — review). ---
    with localcontext() as ctx:
        ctx.prec = _WEIGHT_COMPUTE_PREC
        exposure_by_factor: dict[str, Decimal] = {}
        exposure_ids_seen: set[str] = set()
        uncovered: set[str] = set()
        for r in exposure_raw:
            rid = str(r["id"]).lower()
            if rid in exposure_ids_seen:  # a duplicated pin would double-count the exposure total
                raise ActiveRiskInputError(f"duplicate pinned exposure row {rid} — refused")
            exposure_ids_seen.add(rid)
            amount = Decimal(r["exposure_amount"])
            if abs(amount) >= _MAX_EXPOSURE_ABS:
                raise ActiveRiskInputError(
                    "a pinned exposure_amount exceeds its source-column envelope — refused"
                )
            fid = str(r["factor_id"]).lower()
            if fid not in covariance_factors:
                uncovered.add(r["factor_code"])
            exposure_by_factor[fid] = exposure_by_factor.get(fid, Decimal(0)) + amount
        if uncovered:
            raise ActiveRiskInputError(
                f"exposure factors {sorted(uncovered)} are not covered by the pinned covariance "
                f"matrix — refused (NO zero-variance imputation)"
            )
        portfolio_value = sum(exposure_by_factor.values(), Decimal(0))
        if portfolio_value == 0:
            raise ActiveRiskInputError(
                "the pinned portfolio value (sum of exposure_amount) is zero — active weights are "
                "undefined; refused"
            )
        if abs(portfolio_value) >= _MAX_PORTFOLIO_VALUE_ABS:
            raise ActiveRiskInputError(
                "the pinned portfolio value exceeds its evidence-column envelope — refused"
            )

        benchmark_by_factor: dict[str, Decimal] = {}
        constituent_ids_seen: set[str] = set()
        for r in benchmark_raw:
            cid = str(r["id"]).lower()
            if cid in constituent_ids_seen:  # a duplicated pin would double-count the weight total
                raise ActiveRiskInputError(
                    f"duplicate pinned benchmark constituent {cid} — refused"
                )
            constituent_ids_seen.add(cid)
            currency = r["constituent_currency"]
            if not _is_present_currency(currency):
                # OQ-6 (ratified): a NULL/blank per-name denomination is a named-gap refusal —
                # NEVER a silent header-currency fallback ("" is not None, so it is checked here).
                raise ActiveRiskInputError(
                    f"benchmark constituent {cid} has a NULL/blank constituent_currency — refused "
                    f"(no header-currency imputation)"
                )
            weight = Decimal(r["weight"])
            if abs(weight) >= _MAX_WEIGHT_ABS:
                raise ActiveRiskInputError(
                    "a pinned benchmark weight exceeds its source-column envelope — refused"
                )
            factor = index.get(currency)
            if factor is None:
                raise ActiveRiskInputError(
                    f"benchmark constituent currency {currency!r} maps to no pinned factor — "
                    f"refused (NO imputation)"
                )
            benchmark_by_factor[factor.id] = benchmark_by_factor.get(factor.id, Decimal(0)) + weight
        total_weight = sum(benchmark_by_factor.values(), Decimal(0))
        if total_weight <= 0:
            raise ActiveRiskInputError(
                f"the pinned benchmark weights sum to {total_weight} (<= 0) — cannot normalize; "
                f"refused"
            )

        # w_a = w_p - w_b over the UNION factor set (all at compute precision).
        w_p = {fid: amt / portfolio_value for fid, amt in exposure_by_factor.items()}
        w_b = {fid: wt / total_weight for fid, wt in benchmark_by_factor.items()}
        active_factor_ids = set(w_p) | set(w_b)
        active_weights = {
            fid: w_p.get(fid, Decimal(0)) - w_b.get(fid, Decimal(0)) for fid in active_factor_ids
        }

    # Pair completeness (every active factor's canonical pair present — NO imputation). The active
    # set is provably covariance-covered (w_p via the `uncovered` gate, w_b via the exact FACTOR-set
    # equality), so a missing DIAGONAL pair is the residual hole this catches. Ids are already
    # lowercased + the loop iterates sorted, so (fid_i, fid_j) is the canonical key directly.
    ordered = sorted(active_factor_ids)
    for i, fid_i in enumerate(ordered):
        for fid_j in ordered[i:]:
            if (fid_i, fid_j) not in covariance:
                raise ActiveRiskInputError(
                    f"the pinned covariance matrix is missing the pair "
                    f"({fid_i}, {fid_j}) — refused"
                )

    return _ParsedInput(
        active_weights=active_weights,
        covariance=covariance,
        exposure_run_id=next(iter(exposure_run_ids)),
        covariance_run_id=covariance_run_id,
        benchmark_id=next(iter(benchmark_ids)),
        benchmark_effective_date=date.fromisoformat(next(iter(effective_dates))),
        base_currency=base_currency,
        portfolio_value=portfolio_value,
        n_factors=len(active_weights),
        n_constituents=len(benchmark_raw),
    )


def _assert_partitioning_exposure_run(session: Session, run: CalculationRun) -> None:
    """PA-2 (review fold): the w_p normalization divides by portfolio_value = the SUM of the
    pinned rows — the NET BOOK VALUE only when the factor-exposure run PARTITIONS the book
    (allocation-v1, epsilon=0). A PARTIAL-proxy run (sum(w) < 1, the residual honestly unmodeled)
    would silently REDISTRIBUTE the residual pro-rata; v1 accepts ONLY allocation-family runs
    (a proxy-aware denominator is the recorded v2). Applied on BOTH entry paths."""
    if run.model_version_id is None:
        return
    from irp_shared.model.models import Model, ModelVersion  # models-only (no cycle)
    from irp_shared.risk.bootstrap import FACTOR_EXPOSURE_MODEL_CODE

    fx_model_code = session.execute(
        select(Model.code)
        .join(ModelVersion, ModelVersion.model_id == Model.id)
        .where(ModelVersion.id == str(run.model_version_id))
    ).scalar_one_or_none()
    if fx_model_code != FACTOR_EXPOSURE_MODEL_CODE:
        raise ActiveRiskInputError(
            f"the exposure run {run.run_id} was produced by {fx_model_code!r} — active risk v1 "
            f"requires the PARTITIONING allocation model ({FACTOR_EXPOSURE_MODEL_CODE!r}; a "
            f"partial-proxy book's residual would be silently redistributed by the weight "
            f"normalization); refused"
        )


def run_active_risk(
    session: Session,
    *,
    acting_tenant: str,
    actor: ActiveRiskActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str | None = None,
    covariance_run_id: str | None = None,
    benchmark_id: str | None = None,
    benchmark_effective_date: date | None = None,
    snapshot_id: str | None = None,
) -> ActiveRiskRunResult:
    """Run a governed ex-ante active-risk (tracking-error) calculation. Build-in-request (default —
    ``exposure_run_id`` + ``covariance_run_id`` + ``benchmark_id`` + ``benchmark_effective_date``:
    builds an ``ACTIVE_RISK_INPUT`` snapshot pinning both runs' rows + the covariance factor defs +
    the benchmark membership) or consume-existing (``snapshot_id``). BOTH paths adjudicate the
    pinned
    content pre-create. See the module docstring for the failure model + the AD-014 / CTRL-003
    invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise ActiveRiskInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ActiveRiskInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ActiveRiskInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise ActiveRiskInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    build_args = (exposure_run_id, covariance_run_id, benchmark_id, benchmark_effective_date)
    if snapshot_id is not None and any(a is not None for a in build_args):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY — an
        # ambiguous request must be refused, never guessed.
        raise ActiveRiskInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(exposure_run_id/covariance_run_id/benchmark_id/benchmark_effective_date), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3). The active-risk model carries NO
    # numeric parameter (OD-P3-7-D) — the registered code_version IS the methodology identity.
    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=ACTIVE_RISK_MODEL_CODE,
    )

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_ACTIVE_RISK_INPUT:
            raise ActiveRiskInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != "
                f"{PURPOSE_ACTIVE_RISK_INPUT}"
            )
    else:
        if not all(a is not None for a in build_args):
            raise ActiveRiskInputError(
                "exposure_run_id + covariance_run_id + benchmark_id + benchmark_effective_date are "
                "required to build an active-risk snapshot"
            )
        exposure_run = resolve_factor_exposure_run(
            session, str(exposure_run_id), acting_tenant=acting_tenant
        )
        if exposure_run.status != RunStatus.COMPLETED.value:
            raise ActiveRiskInputError(
                f"exposure run {exposure_run_id} status {exposure_run.status!r} != COMPLETED"
            )
        _assert_partitioning_exposure_run(session, exposure_run)
        covariance_run = resolve_covariance_run(
            session, str(covariance_run_id), acting_tenant=acting_tenant
        )
        if covariance_run.status != RunStatus.COMPLETED.value:
            raise ActiveRiskInputError(
                f"covariance run {covariance_run_id} status {covariance_run.status!r} != COMPLETED"
            )
        # resolve_benchmark raises BenchmarkNotVisible (fail-closed) on a hidden/unknown id — a
        # pre-create refusal (no run yet).
        resolve_benchmark(session, str(benchmark_id), acting_tenant=acting_tenant)
        assert benchmark_effective_date is not None  # narrowed by the all(build_args) gate above
        snapshot = build_active_risk_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            covariance_run_id=str(covariance_run_id),
            benchmark_id=str(benchmark_id),
            benchmark_effective_date=benchmark_effective_date,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths): empty / mixed-run /
    # mixed-currency / wrong-vocab / uncovered-factor / NULL-or-unmappable-currency / zero-book pins
    # all refuse HERE — before a run (or any run-audit) can exist.
    try:
        exposure_raw, covariance_raw, factor_raw, benchmark_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(exposure_raw, covariance_raw, factor_raw, benchmark_raw)
    except ActiveRiskInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content (missing keys, non-decimal/JSON-null values, bad
        # dates, non-object captured_content) is the SAME refusal class as a semantically ill-formed
        # input — a governed 422, never a raw parse 500. JSONDecodeError/InvalidOperation subclass
        # ValueError/Arithmetic; Decimal(None)/list-indexing raise TypeError (review).
        raise ActiveRiskInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # The provenance ids come from the PINNED CONTENT — re-resolve ALL THREE under the acting tenant
    # (run_type + COMPLETED for the runs; tenant-visibility for the benchmark) before they are
    # stamped into hard-FK columns: PG FK checks bypass RLS, so without this a hand-minted snapshot
    # could durably reference a FOREIGN tenant's runs/benchmark (and probe id existence x-tenant) —
    # the P3-5 review's principal finding, extended to the benchmark FK. On the build path this
    # re-resolution is an idempotent tautology.
    pinned_exposure_run = resolve_factor_exposure_run(
        session, parsed.exposure_run_id, acting_tenant=acting_tenant
    )
    if pinned_exposure_run.status != RunStatus.COMPLETED.value:
        raise ActiveRiskInputError(
            f"the pinned exposure run {parsed.exposure_run_id} is not COMPLETED"
        )
    _assert_partitioning_exposure_run(session, pinned_exposure_run)
    pinned_covariance_run = resolve_covariance_run(
        session, parsed.covariance_run_id, acting_tenant=acting_tenant
    )
    if pinned_covariance_run.status != RunStatus.COMPLETED.value:
        raise ActiveRiskInputError(
            f"the pinned covariance run {parsed.covariance_run_id} is not COMPLETED"
        )
    resolve_benchmark(session, parsed.benchmark_id, acting_tenant=acting_tenant)

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[ActiveRiskResult], list[str]]:
        # The pure kernel over the constructed active weights ONLY (no live read — AD-014).
        gaps: list[str] = []
        try:
            estimate = compute_tracking_error(parsed.active_weights, parsed.covariance)
        except ActiveRiskKernelError as exc:
            # A column-legal-but-extreme pin can drive te past the 12dp quantize range, where the
            # kernel raises BEFORE the _MAX_RESULT_ABS gate below can read te_value: convert it to
            # the SAME committed FAILED run + DQ evidence, never an uncaught overflow 500 (review).
            gaps.append(f"magnitude-out-of-range:{exc}")
            return [], gaps
        if estimate.te_value is None:
            gaps.append(f"non-psd-radicand:{estimate.radicand:E}<-tol:{estimate.tolerance:E}")
            return [], gaps
        if abs(estimate.te_value) >= _MAX_RESULT_ABS:
            # Column-legal-but-extreme inputs can drive te beyond Numeric(20,12): a committed FAILED
            # run with evidence, never a PG overflow 500.
            gaps.append(f"magnitude-out-of-range:te:{estimate.te_value:E}")
            return [], gaps
        row = ActiveRiskResult(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            factor_exposure_run_id=parsed.exposure_run_id,
            covariance_run_id=parsed.covariance_run_id,
            benchmark_id=parsed.benchmark_id,
            benchmark_effective_date=parsed.benchmark_effective_date,
            metric_type=METRIC_TYPE_TRACKING_ERROR,
            base_currency=parsed.base_currency,
            te_value=estimate.te_value,
            portfolio_value=parsed.portfolio_value,
            n_factors=parsed.n_factors,
            n_constituents=parsed.n_constituents,
        )
        return [row], gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_ACTIVE_RISK,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=(
            "active-risk run output sanity (radicand within the declared PSD quantization floor)"
        ),
        rule_target_entity_type="active_risk_result",
        result_entity_type="active_risk_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return ActiveRiskRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_active_risks(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[ActiveRiskResult]:
    """The ``active_risk_result`` rows of a run (tenant-scoped; one row per metric in v1)."""
    return list(
        session.execute(
            select(ActiveRiskResult)
            .where(
                ActiveRiskResult.calculation_run_id == str(run_id),
                ActiveRiskResult.tenant_id == str(acting_tenant),
            )
            .order_by(ActiveRiskResult.metric_type)
        )
        .scalars()
        .all()
    )


def resolve_active_risk_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve an active-risk ``calculation_run`` by ``run_id`` with an EXPLICIT tenant predicate +
    ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable refusal
    evidence). Raises :class:`ActiveRiskRunNotVisible` on a hidden/unknown id or a non-active-risk
    run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_ACTIVE_RISK,
        not_visible=ActiveRiskRunNotVisible,
    )


def resolve_active_risk(
    session: Session, active_risk_id: str, *, acting_tenant: str
) -> ActiveRiskResult:
    """Resolve one ``active_risk_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(ActiveRiskResult).where(
            ActiveRiskResult.id == str(active_risk_id),
            ActiveRiskResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ActiveRiskNotVisible(str(active_risk_id))
    return row
