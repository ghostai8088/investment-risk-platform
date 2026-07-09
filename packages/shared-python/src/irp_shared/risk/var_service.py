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
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.risk.bootstrap import (
    VAR_MODEL_CODE,
    VarParameters,
    assert_model_version_of,
    declared_var_parameters,
)
from irp_shared.risk.covariance_service import resolve_covariance_run
from irp_shared.risk.events import (
    METRIC_TYPE_VAR_PARAMETRIC,
    RUN_TYPE_VAR,
    VarActor,
)
from irp_shared.risk.factor_service import resolve_factor_exposure_run
from irp_shared.risk.models import VarResult
from irp_shared.risk.var_kernel import compute_parametric_var
from irp_shared.snapshot import (
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    PURPOSE_VAR_INPUT,
    SnapshotActor,
    build_var_snapshot,
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
        exposure_rows.append((fid, Decimal(r["exposure_amount"])))
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
    """Run a governed parametric-VaR calculation. Build-in-request (default —
    ``exposure_run_id`` + ``covariance_run_id``: builds a ``VAR_INPUT`` snapshot pinning both
    runs' result rows) or consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned
    content pre-create. See the module docstring for the failure model + the AD-014 / CTRL-003 /
    OD-P3-5-D invariants."""

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
    # Inventory-before-use + model identity (CTRL-003 / BR-3) + the DECLARED parameters
    # (OD-P3-5-D: confidence/horizon/z are version identity, parsed from the registered
    # assumptions — never free request parameters).
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=VAR_MODEL_CODE,
    )
    declared: VarParameters = declared_var_parameters(session, version)

    # --- Bind the two-run snapshot (cross-tenant/unknown/ill-formed ⇒ pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_VAR_INPUT:
            raise VarInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_VAR_INPUT}"
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
        snapshot = build_var_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            covariance_run_id=str(covariance_run_id),
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths; OD-P3-5-H): empty /
    # mixed-run / mixed-currency / wrong-vocab / uncovered-factor pins all refuse HERE — before
    # a run (or any run-audit) can exist.
    try:
        exposure_raw, covariance_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(exposure_raw, covariance_raw)
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
        if abs(estimate.sigma) >= _MAX_RESULT_ABS or abs(estimate.var_value) >= _MAX_RESULT_ABS:
            # Column-legal-but-extreme inputs can produce sigma beyond Numeric(28,6): a
            # committed FAILED run with evidence, never a PG overflow 500 (2026-07 review).
            gaps.append(f"magnitude-out-of-range:sigma:{estimate.sigma:E}")
            return [], gaps
        row = VarResult(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            exposure_run_id=parsed.exposure_run_id,
            covariance_run_id=parsed.covariance_run_id,
            metric_type=METRIC_TYPE_VAR_PARAMETRIC,
            base_currency=parsed.base_currency,
            confidence_level=declared.confidence_level,
            horizon_days=declared.horizon_days,
            z_score=declared.z_score,
            sigma=estimate.sigma,
            var_value=estimate.var_value,
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
        rule_name="VaR run output sanity (radicand within the declared PSD quantization floor)",
        rule_target_entity_type="var_result",
        result_entity_type="var_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",  # verbatim P3-5 format
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
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_VAR,
        )
    ).scalar_one_or_none()
    if run is None:
        raise VarRunNotVisible(str(run_id))
    return run


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
