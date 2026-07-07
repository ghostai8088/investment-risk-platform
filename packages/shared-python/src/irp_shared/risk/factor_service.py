"""Factor-exposure binder (P3-3, ENT-028 family — allocation v1, the second governed risk number).

``run_factor_exposure`` produces ``factor_exposure_result`` rows ONLY when bound to a
``dataset_snapshot`` (``FACTOR_EXPOSURE_INPUT``, pinning the consumed ``exposure_aggregate`` atoms
+ the ``factor`` EV definitions) + a complete ``calculation_run`` + a **REGISTERED
``model_version`` OF THE FACTOR-EXPOSURE MODEL** (AD-014 / FW-RUN / TR-15 / CTRL-003 — the
``run_sensitivities`` exemplar mirrored step-for-step, plus the model-identity tightening: a
version of a DIFFERENT model family is refused pre-create). The number is the deterministic
indicator-loading allocation (``irp_shared.risk.factor_kernel``): CURRENCY family, matched on the
atom's captured ``mark_currency``; contributions sum to the pinned input total EXACTLY (ε = 0,
REQ-MKT-003).

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned
``COMPONENT_KIND_EXPOSURE``/``COMPONENT_KIND_FACTOR`` captured content** — it makes **NO** live
exposure/factor read, so a later factor-definition amend or exposure re-run cannot change a
historical factor exposure.

Failure model (the P2-3/P3-1 precedent, split by timing — and, post the 2026-07 adversarial
review, UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing ``code_version``/``environment_id``/initiator/
  ``model_version_id``; an unregistered or WRONG-MODEL model_version; a non-COMPLETED /
  cross-tenant / empty exposure run; a wrong-purpose snapshot; **pinned content that is not a
  well-formed v1 input** — zero pinned atoms, zero pinned factors, a non-CURRENCY family, a
  NULL ``currency_code`` scope, or a duplicate ``currency_code`` (an ambiguous partition)):
  **raise BEFORE ``create_run``** ⇒ ZERO run + ZERO rows + ZERO run-audit. Both the
  build-in-request AND consume-existing (``snapshot_id``) paths adjudicate the PINNED content
  pre-create through the same kernel rules, so a snapshot minted by any other builder cannot
  smuggle an ill-formed input past the gate.
- **Post-create FAILED** (the DQ gate failing AFTER RUNNING — an unmapped atom, OD-P3-3-N): mark
  the run FAILED (``outcome='failure'``) and **return** ⇒ a committed FAILED run +
  ``CALC.RUN_STATUS_CHANGE`` + a ``DATA.VALIDATE`` DQ record + ZERO result rows (durable refusal
  evidence; the returned ``failure_reason`` names the unmapped atoms/currencies).
- **Emit-path** raises propagate ⇒ the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``risk -> {snapshot, marketdata(constants), exposure(read-only run resolution),
calc, model, lineage, dq, audit, db}``; imports NO live exposure/factor resolver into the COMPUTE
path; imports no covariance/VaR/ES/scenario/stress/regression symbol; nothing imports ``risk``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.exposure.service import resolve_run as resolve_exposure_run
from irp_shared.marketdata.models import FACTOR_FAMILY_CURRENCY
from irp_shared.risk.bootstrap import FACTOR_EXPOSURE_MODEL_CODE, assert_model_version_of
from irp_shared.risk.events import RUN_TYPE_FACTOR_EXPOSURE, FactorExposureActor
from irp_shared.risk.factor_kernel import (
    AtomPin,
    FactorKernelError,
    FactorPin,
    allocate_atom,
    build_factor_index,
)
from irp_shared.risk.models import FactorExposureResult
from irp_shared.risk.scaffold import execute_governed_run
from irp_shared.snapshot import (
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FACTOR,
    PURPOSE_FACTOR_EXPOSURE_INPUT,
    SnapshotActor,
    build_factor_exposure_snapshot,
    list_components,
    resolve_snapshot,
)

#: The v1 supported mapping families (OD-P3-3-C; anything else is a pre-create refusal — enforced
#: on the PINNED factor content for both entry paths).
SUPPORTED_FACTOR_FAMILIES = (FACTOR_FAMILY_CURRENCY,)
#: Per-tenant governed completeness DQ rule (resolve-or-register; the sensitivity pattern).
_COMPLETENESS_RULE_CODE = "risk.factor_exposure.completeness"
#: How many unmapped-atom identifiers the FAILED ``failure_reason`` names (evidence, bounded).
_MAX_GAPS_IN_REASON = 10


class FactorExposureInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Maps to 422."""


class FactorExposureNotVisible(Exception):
    """Raised when a ``factor_exposure_result`` id is not visible in the acting tenant scope."""

    def __init__(self, factor_exposure_id: str) -> None:
        super().__init__(
            f"factor_exposure_result {factor_exposure_id} is not visible in the current tenant"
        )
        self.factor_exposure_id = str(factor_exposure_id)


class FactorExposureRunNotVisible(Exception):
    """Raised when a factor-exposure ``calculation_run`` id is not visible in the acting
    tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"factor-exposure run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class FactorExposureRunResult:
    """The outcome of ``run_factor_exposure``: the ``calculation_run`` + status + the rows
    produced. ``status`` is ``COMPLETED`` (with ``rows``) or ``FAILED`` (a post-create gate
    failure: a committed FAILED run + ZERO rows + ``failure_reason`` naming the unmapped
    atoms)."""

    run: CalculationRun
    status: str
    rows: list[FactorExposureResult] = field(default_factory=list)
    failure_reason: str | None = None


def _parse_pins(comps: list[Any]) -> tuple[list[AtomPin], list[FactorPin]]:
    """Parse the pinned ``captured_content`` into kernel pins (PURE — no live read; the AD-014
    invariant)."""
    atoms: list[AtomPin] = []
    factors: list[FactorPin] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_EXPOSURE:
            atoms.append(
                AtomPin(
                    id=data["id"],
                    portfolio_id=data["portfolio_id"],
                    instrument_id=data["instrument_id"],
                    base_currency=data["base_currency"],
                    mark_currency=data["mark_currency"],
                    exposure_amount=Decimal(data["exposure_amount"]),
                )
            )
        elif comp.component_kind == COMPONENT_KIND_FACTOR:
            factors.append(
                FactorPin(
                    id=data["id"],
                    factor_code=data["factor_code"],
                    factor_family=data["factor_family"],
                    currency_code=data["currency_code"],
                )
            )
    return atoms, factors


def _adjudicate_pins(atoms: list[AtomPin], factors: list[FactorPin]) -> dict[str, FactorPin]:
    """PRE-CREATE adjudication of the pinned input (both entry paths; the 2026-07 review
    hardening): ≥1 atom, ≥1 factor, every factor family v1-supported, and a well-formed partition
    (the kernel is the single rule source — NULL scope / duplicate ``currency_code`` refuse).
    Raises :class:`FactorExposureInputError`; returns the allocation index."""
    if not atoms:
        raise FactorExposureInputError(
            "the snapshot pins no exposure atoms (COMPONENT_KIND_EXPOSURE) — not a "
            "factor-exposure input"
        )
    if not factors:
        raise FactorExposureInputError(
            "the snapshot pins no factor definitions (COMPONENT_KIND_FACTOR) — not a "
            "factor-exposure input"
        )
    base_currencies = {a.base_currency for a in atoms}
    if len(base_currencies) != 1:
        # P3-C1 (OD-H): base is run-uniform by construction on the governed path, but a
        # hand-minted snapshot could pin mixed-base atoms — the recorded latent hole, closed
        # at the adjudication (the P3-5 twin check); the 4-tuple grain is unchanged.
        raise FactorExposureInputError(
            f"the pinned atoms carry mixed base currencies {sorted(base_currencies)} — refused"
        )
    for pin in factors:
        if pin.factor_family not in SUPPORTED_FACTOR_FAMILIES:
            raise FactorExposureInputError(
                f"factor {pin.factor_code!r} family {pin.factor_family!r} is not supported "
                f"in v1 (supported: {SUPPORTED_FACTOR_FAMILIES})"
            )
    try:
        return build_factor_index(factors)
    except FactorKernelError as exc:
        raise FactorExposureInputError(str(exc)) from exc


def _build_rows(
    atoms: list[AtomPin],
    index: dict[str, FactorPin],
    *,
    run: CalculationRun,
    snapshot_id: str,
    model_version_id: str,
    acting_tenant: str,
) -> tuple[list[FactorExposureResult], list[str]]:
    """Allocate each pinned atom to its factor (the pure kernel over pre-adjudicated pins only).
    Returns ``(rows, gaps)`` — one gap per unmapped atom (the fail-closed DQ signal; rows are NOT
    written when gaps exist)."""
    rows: list[FactorExposureResult] = []
    gaps: list[str] = []
    for atom in atoms:
        allocated = allocate_atom(atom, index)
        if allocated is None:
            gaps.append(f"unmapped-atom:{atom.id}:{atom.mark_currency}")
            continue
        rows.append(
            FactorExposureResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=str(snapshot_id),
                model_version_id=str(model_version_id),
                portfolio_id=atom.portfolio_id,
                instrument_id=atom.instrument_id,
                factor_id=allocated.factor.id,
                factor_code=allocated.factor.factor_code,
                factor_family=allocated.factor.factor_family,
                base_currency=atom.base_currency,
                mark_currency=atom.mark_currency,
                loading=allocated.loading,
                exposure_amount=allocated.exposure_amount,
            )
        )
    return rows, gaps


def run_factor_exposure(
    session: Session,
    *,
    acting_tenant: str,
    actor: FactorExposureActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str | None = None,
    factor_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> FactorExposureRunResult:
    """Run a governed factor-exposure allocation. Build-in-request (default — ``exposure_run_id``
    + ``factor_ids``: builds a ``FACTOR_EXPOSURE_INPUT`` snapshot pinning the atoms + factors) or
    consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create. See
    the module docstring for the failure model + the AD-014 / CTRL-003 invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/run-audit) ---
    if not code_version:
        raise FactorExposureInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise FactorExposureInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise FactorExposureInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise FactorExposureInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    if snapshot_id is not None and (exposure_run_id is not None or factor_ids is not None):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY —
        # an ambiguous request must be refused, never guessed.
        raise FactorExposureInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(exposure_run_id/factor_ids), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3): the version must be REGISTERED and
    # belong to the FACTOR-EXPOSURE model (a sensitivity/other-family version is refused — the
    # 2026-07 review hardening).
    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=FACTOR_EXPOSURE_MODEL_CODE,
    )

    # --- Bind the atoms+factors snapshot (cross-tenant/unknown/ill-formed ⇒ pre-create refusal) --
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_FACTOR_EXPOSURE_INPUT:
            raise FactorExposureInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} "
                f"!= {PURPOSE_FACTOR_EXPOSURE_INPUT}"
            )
    else:
        if not exposure_run_id or not factor_ids:
            raise FactorExposureInputError(
                "exposure_run_id + factor_ids are required to build a factor-exposure snapshot"
            )
        # The consumed exposure run must be a COMPLETED own-tenant EXPOSURE_AGGREGATE run (a
        # FAILED run has zero rows; RUNNING output is not a governed input). The builder itself
        # fail-closes on an empty atom set / empty factor list BEFORE any write.
        exposure_run = resolve_exposure_run(
            session, str(exposure_run_id), acting_tenant=acting_tenant
        )
        if exposure_run.status != RunStatus.COMPLETED.value:
            raise FactorExposureInputError(
                f"exposure run {exposure_run_id} status {exposure_run.status!r} != COMPLETED"
            )
        snapshot = build_factor_exposure_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            factor_ids=[str(fid) for fid in factor_ids],
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths; kernel-rule-sourced):
    # zero atoms / zero factors / unsupported family / NULL scope / duplicate currency all refuse
    # HERE — before a run (or any run-audit) can exist.
    atoms, factors = _parse_pins(
        list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    )
    index = _adjudicate_pins(atoms, factors)

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[FactorExposureResult], list[str]]:
        return _build_rows(
            atoms,
            index,
            run=run,
            snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            acting_tenant=acting_tenant,
        )

    def _format_reason(gate: Exception, gaps: list[str]) -> str:  # verbatim P3-3 format
        # Name the unmapped atoms/currencies in the reason (bounded) — the review finding: the
        # computed gap identifiers must not be discarded.
        detail = "; ".join(gaps[:_MAX_GAPS_IN_REASON])
        more = (
            f" (+{len(gaps) - _MAX_GAPS_IN_REASON} more)" if len(gaps) > _MAX_GAPS_IN_REASON else ""
        )
        return f"{gate} — {detail}{more}"

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_FACTOR_EXPOSURE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=(
            "Factor-exposure run mapping completeness (every atom maps to exactly one factor)"
        ),
        rule_target_entity_type="factor_exposure_result",
        result_entity_type="factor_exposure_result",
        compute=_compute,
        format_reason=_format_reason,
    )
    return FactorExposureRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_factor_exposures(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[FactorExposureResult]:
    """The factor-exposure rows of a run (tenant-scoped, stable order)."""
    return list(
        session.execute(
            select(FactorExposureResult)
            .where(
                FactorExposureResult.calculation_run_id == str(run_id),
                FactorExposureResult.tenant_id == str(acting_tenant),
            )
            .order_by(
                FactorExposureResult.factor_id,
                FactorExposureResult.portfolio_id,
                FactorExposureResult.instrument_id,
            )
        )
        .scalars()
        .all()
    )


def resolve_factor_exposure_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a FACTOR_EXPOSURE ``calculation_run`` by ``run_id`` with an EXPLICIT tenant
    predicate + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable
    refusal evidence). Raises :class:`FactorExposureRunNotVisible` on a hidden/unknown id or a
    non-factor-exposure run."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_FACTOR_EXPOSURE,
        )
    ).scalar_one_or_none()
    if run is None:
        raise FactorExposureRunNotVisible(str(run_id))
    return run


def resolve_factor_exposure(
    session: Session, factor_exposure_id: str, *, acting_tenant: str
) -> FactorExposureResult:
    """Resolve one ``factor_exposure_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(FactorExposureResult).where(
            FactorExposureResult.id == str(factor_exposure_id),
            FactorExposureResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise FactorExposureNotVisible(str(factor_exposure_id))
    return row
