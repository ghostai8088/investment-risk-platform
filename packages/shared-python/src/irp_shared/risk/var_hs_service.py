"""Historical-simulation binder (VAR-HS-1 + ES-HS-1, ENT-027): the TWO empirical families.

``run_var_historical`` produces the ONE ``var_result`` summary row ONLY when bound to a
``dataset_snapshot`` (``VAR_HS_INPUT``, pinning EVERY result row of the consumed
FACTOR_EXPOSURE run + the aligned per-factor FACTOR_RETURN windows) + a complete
``calculation_run`` + a **REGISTERED ``model_version`` of ONE of the TWO historical-simulation
families** (AD-014 / FW-RUN / TR-15 / CTRL-003 / OD-VHS-B / OD-ES-HS-1-B — the ``run_var``
exemplar mirrored step-for-step; the family dispatch is the ES-1 registry-map shape):

- ``risk.var.historical`` (declared confidence/horizon/window/quantile-convention) ⇒ the lower
  empirical order statistic, ``metric_type='VAR_HISTORICAL'``: ``VaR = -(k-th smallest pnl)``,
  ``k = ceil(N (1-c))``.
- ``risk.var.historical_es`` (declared confidence/horizon/window/estimator-convention) ⇒ the
  Acerbi-Tasche Prop 4.1 empirical α-tail-mean, ``metric_type='ES_HISTORICAL'``:
  ``ES = -(Σ_{i<=m} pnl_(i) + w·pnl_(m+1)) / (N·a)``.

Both over ``pnl_t = x' r_t`` — NO distributional assumption; the pinned input is IDENTICAL for
the two families (the purpose-only snapshot symmetry is SAFE for exactly that reason — the
adjudicated OD-ES-HS-1-B reuse, unlike the plain/total predicate split).

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned
``COMPONENT_KIND_FACTOR_EXPOSURE``/``COMPONENT_KIND_FACTOR_RETURN`` captured content** — no live
result/factor read; a later vendor supersede or upstream re-run cannot move a historical number.

Failure model (the P3-5 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal**: missing prerequisites; an unregistered/wrong-model version; a
  malformed declaration; a non-COMPLETED / cross-tenant / empty upstream run; a wrong-purpose
  snapshot; pinned content that is not a well-formed v1 input (zero rows of either kind,
  mixed-run exposure rows, non-uniform ``base_currency``, wrong return vocabulary, misaligned /
  short / duplicate-date windows, an exposure factor with NO pinned window, a window shorter
  than the DECLARED ``window_observations``) ⇒ raise BEFORE ``create_run``. **NO imputation.**
- **Post-create FAILED**: the result-magnitude gate (|VaR| beyond Numeric(28,6)'s envelope) ⇒
  committed FAILED run + DQ evidence + ZERO rows + a magnitude-naming ``failure_reason``.
- **Emit-path** raises propagate ⇒ co-transactional rollback (CTRL-032).

One-way imports: ``risk -> {snapshot, calc, model, lineage, dq, audit, db}``; NO live reader in
the compute path; NO numpy; nothing imports ``risk``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.model.models import ModelVersion
from irp_shared.risk.bootstrap import (
    ES_HS_MODEL_CODE,
    VAR_HS_MODEL_CODE,
    EsHsParameters,
    HsVarParameters,
    WrongModelVersionError,
    assert_model_version_of,
    declared_es_hs_parameters,
    declared_hs_var_parameters,
)
from irp_shared.risk.events import (
    METRIC_TYPE_ES_HISTORICAL,
    METRIC_TYPE_VAR_HISTORICAL,
    RUN_TYPE_VAR,
    VarActor,
)
from irp_shared.risk.factor_service import resolve_factor_exposure_run
from irp_shared.risk.models import VarResult
from irp_shared.risk.var_hs_kernel import compute_historical_es, compute_historical_var
from irp_shared.snapshot import (
    COMPONENT_KIND_FACTOR_EXPOSURE,
    COMPONENT_KIND_FACTOR_RETURN,
    PURPOSE_VAR_HS_INPUT,
    SnapshotActor,
    build_var_hs_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the P3-1/3/4/5 pattern).
_COMPLETENESS_RULE_CODE = "risk.var_hs.completeness"
#: The v1 return vocabulary the pinned windows must carry (the P3-2/P3-4 contract).
_REQUIRED_RETURN_TYPE = "SIMPLE"
_REQUIRED_FREQUENCY = "DAILY"
#: Source-column envelopes (the P3-5 review lesson): exposure_amount Numeric(28,6) < 1E22;
#: return_value Numeric(20,12) < 1E8.
_MAX_EXPOSURE_ABS = Decimal("1E22")
_MAX_RETURN_ABS = Decimal("1E8")
#: The var_result var_value column envelope (Numeric(28,6)).
_MAX_RESULT_ABS = Decimal("1E22")


class HsVarInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal
    (no run, no result, no run-audit). Maps to 422."""


@dataclass(frozen=True)
class HsVarRunResult:
    """The outcome of ``run_var_historical``: ``COMPLETED`` (with the ONE summary row) or
    ``FAILED`` (the magnitude gate: a committed FAILED run + ZERO rows + a ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[VarResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _HsFamily:
    """Which of the TWO historical-simulation model codes this run bound (ES-HS-1, OD-B —
    the ES-1 ``_VarFamily`` registry-map shape; a try/except chain is the wrong shape)."""

    code: str
    es: bool


#: The two empirical families, in DISPATCH order (cost only — the codes are mutually exclusive).
_HS_FAMILIES: tuple[_HsFamily, ...] = (
    _HsFamily(code=VAR_HS_MODEL_CODE, es=False),
    _HsFamily(code=ES_HS_MODEL_CODE, es=True),
)


def _resolve_hs_family(
    session: Session, model_version_id: str, *, acting_tenant: str
) -> tuple[ModelVersion, _HsFamily]:
    """Inventory-before-use + model identity (CTRL-003 / BR-3) across the two historical
    families. An UNREGISTERED version raises from the first assert (not a family question); a
    version of NEITHER family raises the FIRST :class:`WrongModelVersionError` — the one naming
    the PLAIN HS code, preserving the pre-ES-HS-1 message for the pre-ES-HS-1 failure (the
    ``_resolve_var_family`` contract, mirrored)."""
    first_error: WrongModelVersionError | None = None
    for family in _HS_FAMILIES:
        try:
            version = assert_model_version_of(
                session,
                str(model_version_id),
                tenant_id=acting_tenant,
                expected_model_code=family.code,
            )
        except WrongModelVersionError as exc:
            if first_error is None:  # the PLAIN-HS-code miss — the pre-ES-HS-1 message
                first_error = exc
            continue
        return version, family
    assert first_error is not None  # the loop is non-empty, so a full miss always set it
    raise first_error


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the kernel arguments + run-uniform captured descriptors."""

    exposures: dict[str, Decimal]  # factor_id lowercase -> per-factor total
    returns_by_date: dict[date, dict[str, Decimal]]
    exposure_run_id: str
    base_currency: str
    n_factors: int
    n_observations: int
    window_start: date
    window_end: date


def _parse_pins(comps: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw exposure-row/return-window dicts (PURE —
    no live read; the AD-014 invariant)."""
    exposure_raw: list[dict[str, Any]] = []
    window_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
            exposure_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_FACTOR_RETURN:
            window_raw.append(data)
    return exposure_raw, window_raw


def _adjudicate_pins(
    exposure_raw: list[dict[str, Any]],
    window_raw: list[dict[str, Any]],
    *,
    declared_window: int,
) -> _ParsedInput:
    """PRE-CREATE adjudication of the pinned input (both entry paths — the OD-VHS-F named
    checks): >= 1 row of EACH kind; single-run exposure provenance; uniform ``base_currency``;
    no duplicate exposure pins; the v1 SIMPLE/DAILY return vocabulary; per-factor windows with
    IDENTICAL date sets of EXACTLY the declared length (no imputation, no ragged windows, no
    duplicate dates); COVERAGE (every exposure factor has a pinned window); source-column
    magnitude envelopes. Raises :class:`HsVarInputError`."""
    if not exposure_raw:
        raise HsVarInputError(
            "the snapshot pins no FACTOR_EXPOSURE rows — not a historical-VaR input (an empty "
            "portfolio vector is refused)"
        )
    if not window_raw:
        raise HsVarInputError("the snapshot pins no FACTOR_RETURN windows — refused")

    exposure_run_ids = {str(r["calculation_run_id"]).lower() for r in exposure_raw}
    if len(exposure_run_ids) != 1:
        raise HsVarInputError("the pinned exposure rows span multiple runs — refused")
    base_currencies = {r["base_currency"] for r in exposure_raw}
    if len(base_currencies) != 1:
        raise HsVarInputError(
            f"the pinned exposure rows carry mixed base currencies {sorted(base_currencies)} — "
            f"refused"
        )
    base_currency = next(iter(base_currencies))
    if not isinstance(base_currency, str) or len(base_currency) != 3:
        # A uniformly-NULL or non-3-letter base_currency ({None} / {"USDX"} pass the set-of-one
        # check) would otherwise reach the NOT-NULL varchar(3) column as a post-create 500 (P3-C3
        # binder-consistency pass — the active-risk twin).
        raise HsVarInputError("the pinned exposure base_currency is not a 3-letter code — refused")

    exposures: dict[str, Decimal] = {}
    exposure_ids_seen: set[str] = set()
    # Per-factor totaling runs at prec 50 (the PARAMETRIC kernel's totaling precision — at the
    # default prec 28 two envelope-legal 28-digit amounts already rounded HALF_EVEN, giving the
    # two methods DIFFERENT portfolio vectors on identical pins; 2026-07 review, numeric finder).
    with localcontext() as ctx:
        ctx.prec = 50
        for r in exposure_raw:
            rid = str(r["id"]).lower()
            if rid in exposure_ids_seen:  # a duplicated pin would double-count the total
                raise HsVarInputError(f"duplicate pinned exposure row {rid} — refused")
            exposure_ids_seen.add(rid)
            amount = Decimal(r["exposure_amount"])
            if abs(amount) >= _MAX_EXPOSURE_ABS:
                raise HsVarInputError(
                    "a pinned exposure_amount exceeds its source-column envelope — refused"
                )
            fid = str(r["factor_id"]).lower()
            exposures[fid] = exposures.get(fid, Decimal(0)) + amount
    for fid, total in exposures.items():
        # The per-factor TOTAL is envelope-gated too: m duplicate-factor rows could otherwise
        # push |x_i| to m×1E22 with every individual pin column-legal (2026-07 review).
        if abs(total) >= _MAX_EXPOSURE_ABS:
            raise HsVarInputError(
                f"the per-factor exposure total for {fid} exceeds the envelope — refused"
            )

    returns_by_factor: dict[str, dict[date, Decimal]] = {}
    for w in window_raw:
        fid = str(w["factor_id"]).lower()
        if fid in returns_by_factor:
            raise HsVarInputError(f"duplicate pinned return window for factor {fid} — refused")
        if w.get("frequency") != _REQUIRED_FREQUENCY:
            raise HsVarInputError(
                f"pinned window frequency {w.get('frequency')!r} is not the v1 "
                f"{_REQUIRED_FREQUENCY} contract"
            )
        rows = w["rows"]
        series: dict[date, Decimal] = {}
        for row in rows:
            if row["return_type"] != _REQUIRED_RETURN_TYPE:
                raise HsVarInputError(
                    f"pinned return_type {row['return_type']!r} is not the v1 "
                    f"{_REQUIRED_RETURN_TYPE} contract"
                )
            d = date.fromisoformat(row["return_date"])
            if d in series:
                raise HsVarInputError(
                    f"duplicate return date {d.isoformat()} in factor {fid}'s window — refused"
                )
            value = parse_strict_decimal(
                row["return_value"], error=HsVarInputError, field="return_value"
            )
            if abs(value) >= _MAX_RETURN_ABS:
                raise HsVarInputError(
                    "a pinned return_value exceeds its source-column envelope — refused"
                )
            series[d] = value
        returns_by_factor[fid] = series

    uncovered = sorted(
        {
            r["factor_code"]
            for r in exposure_raw
            if str(r["factor_id"]).lower() not in returns_by_factor
        }
    )
    if uncovered:
        raise HsVarInputError(
            f"exposure factors {uncovered} have no pinned return window — refused "
            f"(NO imputation)"
        )

    date_sets = {frozenset(series.keys()) for series in returns_by_factor.values()}
    if len(date_sets) != 1:
        raise HsVarInputError("the pinned windows are misaligned across factors — refused")
    window_dates = sorted(next(iter(date_sets)))
    if len(window_dates) != declared_window:
        raise HsVarInputError(
            f"the pinned window has {len(window_dates)} observations but the registered model "
            f"declares {declared_window} — refused (window-as-identity, OD-VHS-B)"
        )

    returns_by_date: dict[date, dict[str, Decimal]] = {
        d: {fid: returns_by_factor[fid][d] for fid in returns_by_factor} for d in window_dates
    }
    return _ParsedInput(
        exposures=exposures,
        returns_by_date=returns_by_date,
        exposure_run_id=next(iter(exposure_run_ids)),
        base_currency=base_currency,
        n_factors=len(exposures),
        n_observations=len(window_dates),
        window_start=window_dates[0],
        window_end=window_dates[-1],
    )


def run_var_historical(
    session: Session,
    *,
    acting_tenant: str,
    actor: VarActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str | None = None,
    snapshot_id: str | None = None,
) -> HsVarRunResult:
    """Run a governed historical-simulation VaR calculation. Build-in-request (default —
    ``exposure_run_id``: builds a ``VAR_HS_INPUT`` snapshot pinning the run's rows + the aligned
    return windows for its factor set at the DECLARED length) or consume-existing
    (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/run-audit) ---
    if not code_version:
        raise HsVarInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise HsVarInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise HsVarInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise HsVarInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if snapshot_id is not None and exposure_run_id is not None:
        raise HsVarInputError(
            "ambiguous input — pass either snapshot_id or the build argument "
            "(exposure_run_id), not both"
        )
    version, family = _resolve_hs_family(
        session, str(model_version_id), acting_tenant=acting_tenant
    )
    declared: HsVarParameters | EsHsParameters = (
        declared_es_hs_parameters(session, version)
        if family.es
        else declared_hs_var_parameters(session, version)
    )

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed ⇒ pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_VAR_HS_INPUT:
            raise HsVarInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_VAR_HS_INPUT}"
            )
    else:
        if not exposure_run_id:
            raise HsVarInputError("exposure_run_id is required to build a historical-VaR snapshot")
        exposure_run = resolve_factor_exposure_run(
            session, str(exposure_run_id), acting_tenant=acting_tenant
        )
        if exposure_run.status != RunStatus.COMPLETED.value:
            raise HsVarInputError(
                f"exposure run {exposure_run_id} status {exposure_run.status!r} != COMPLETED"
            )
        snapshot = build_var_hs_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            window_observations=declared.window_observations,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths; OD-VHS-F) ---
    try:
        exposure_raw, window_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(
            exposure_raw, window_raw, declared_window=declared.window_observations
        )
    except HsVarInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content is the SAME refusal class as a semantically
        # ill-formed input — a governed 422, never a raw parse 500 (the P3-5 review lesson;
        # TypeError added in the P3-C3 binder-consistency pass — Decimal(None)/list-indexing).
        raise HsVarInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # The provenance id comes from the PINNED CONTENT — re-resolve under the acting tenant
    # (run_type + COMPLETED) before it is stamped into the hard-FK column: PG FK checks bypass
    # RLS (the P3-5 review's principal finding). Idempotent tautology on the build path.
    pinned_exposure_run = resolve_factor_exposure_run(
        session, parsed.exposure_run_id, acting_tenant=acting_tenant
    )
    if pinned_exposure_run.status != RunStatus.COMPLETED.value:
        raise HsVarInputError(f"the pinned exposure run {parsed.exposure_run_id} is not COMPLETED")

    # --- The shared governed-run lifecycle (P3-C1 scaffold) ---
    def _compute(run: CalculationRun) -> tuple[list[VarResult], list[str]]:
        if family.es:
            # ES-HS-1 (OD-A): the Prop 4.1 empirical α-tail-mean over the SAME scenarios.
            value = compute_historical_es(
                parsed.exposures, parsed.returns_by_date, confidence=declared.confidence_level
            ).es_value
            metric_type = METRIC_TYPE_ES_HISTORICAL
        else:
            value = compute_historical_var(
                parsed.exposures, parsed.returns_by_date, confidence=declared.confidence_level
            ).var_value
            metric_type = METRIC_TYPE_VAR_HISTORICAL
        gaps: list[str] = []
        if abs(value) >= _MAX_RESULT_ABS:
            # Column-legal-but-extreme inputs: a committed FAILED run with evidence, never a
            # PG NumericValueOutOfRange 500 (the P3-5 review lesson).
            gaps.append(f"magnitude-out-of-range:var_value:{value:E}")
            return [], gaps
        row = VarResult(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            exposure_run_id=parsed.exposure_run_id,
            covariance_run_id=None,  # NO covariance run exists for either method (0028/0041)
            metric_type=metric_type,
            base_currency=parsed.base_currency,
            confidence_level=declared.confidence_level,
            horizon_days=declared.horizon_days,
            z_score=None,  # no normal quantile — the methods' point (0028/0041)
            sigma=None,  # no volatility estimate is produced (0028/0041)
            var_value=value,  # the metric's number, discriminated by metric_type
            n_factors=parsed.n_factors,
            n_observations=parsed.n_observations,
            window_start=parsed.window_start,
            window_end=parsed.window_end,
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
        rule_name="Historical-VaR run output sanity (result within the column envelope)",
        rule_target_entity_type="var_result",
        result_entity_type="var_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",  # the P3-5 family format
        # API-1b (OD-API-1b-B): the ROOT copies forward from the pinned factor-exposure run
        # (re-resolved above in BOTH paths).
        scope_portfolio_id=pinned_exposure_run.scope_portfolio_id,
    )
    return HsVarRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )
