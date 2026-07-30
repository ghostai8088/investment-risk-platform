"""CON-1 binder — the 23rd governed number family (ENT-069), computed ONLY from pinned content.

**RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (AD-014). The upstream exposure run is EXPLICITLY
SELECTED — never "latest COMPLETED" (Part 6b item 5: the demo's latest is a 99.98%-one-issuer
book; latest survives only as an API convenience default, upstream of this binder).

**Refusal timings (OQ-CON-1-1, stated once and used consistently):**

- **PRE-CREATE raises (zero run, zero snapshot):** missing prerequisites; a wrong/unregistered
  model version; a non-COMPLETED / wrong-type / cross-tenant upstream run; a **NULL-scope
  upstream run** (the OD-API-1b-D honest NULL — the ENT-069 ``portfolio_id = scope_portfolio_id``
  identity would be uncomputable, so it is refused from the run head, never guessed at); and the
  snapshot builder's own pre-build refusals (mixed basis, mixed same-family scheme versions,
  scheme/dimension mismatch, empty atoms).
- **POST-BUILD ``gaps`` (a committed FAILED run, zero rows):** a zero invested-long total; the
  all-UNCLASSIFIABLE 0/0 book; classifiable coverage below the declared floor.

**Bucketing (OQ-CON-1-4, per-dimension predicates):** ISSUER — the pinned edge's ``issuer_id``,
else UNCLASSIFIABLE. Classification dimensions — a pinned assignment ALWAYS classifies (bucket =
the closure's level-1 code); no assignment + no issuer edge → UNCLASSIFIABLE; no assignment but
an issuer edge exists → UNCLASSIFIED.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.runs import resolve_completed_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.classification.models import BASIS_NOT_APPLICABLE
from irp_shared.concentration.bootstrap import (
    CONCENTRATION_MODEL_CODE,
    declared_concentration_parameters,
)
from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION, ConcentrationActor
from irp_shared.concentration.kernel import Atom, DimensionResult, compute_dimension
from irp_shared.concentration.models import (
    BUCKET_SUMMARY,
    BUCKET_UNCLASSIFIABLE,
    BUCKET_UNCLASSIFIED,
    DENOMINATOR_BASIS_INVESTED_LONG,
    DIMENSION_KIND_ISSUER,
    METRIC_TYPE_SHARE,
    ROW_KIND_DETAIL,
    ROW_KIND_SUMMARY,
    ConcentrationResult,
)
from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE
from irp_shared.model.service import assert_model_version_of
from irp_shared.snapshot.models import (
    COMPONENT_KIND_CLASSIFICATION,
    COMPONENT_KIND_CLASSIFICATION_SCHEME,
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_ISSUER_EDGE,
)
from irp_shared.snapshot.service import (
    SnapshotActor,
    build_concentration_snapshot,
    list_components,
)


class ConcentrationInputError(Exception):
    """A pre-create refusal — raised BEFORE any run/snapshot write; the whole unit rolls back."""


_COMPLETENESS_RULE_CODE = "CONCENTRATION_COMPLETENESS"
_COMPLETENESS_RULE_NAME = "Concentration input completeness (zero-long / 0-0 / coverage floor)"


def _format_reason(gate: Exception, gaps: list[str]) -> str:
    return f"concentration refused: {'; '.join(gaps)}"


def run_concentration(
    session: Session,
    *,
    acting_tenant: str,
    actor: ConcentrationActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str,
    scheme_by_dimension: dict[str, str],
) -> Any:
    """Run a governed concentration calculation: build the ``CONCENTRATION_INPUT`` snapshot over
    the EXPLICITLY SELECTED exposure run, then compute every dimension from the pinned content."""
    # --- Pre-create prerequisite gate (raise BEFORE any write => zero run/snapshot) ---
    if not code_version:
        raise ConcentrationInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ConcentrationInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ConcentrationInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise ConcentrationInputError("model_version_id is required (CTRL-003)")
    if not scheme_by_dimension:
        raise ConcentrationInputError(
            "at least one classification dimension with its scheme is required"
        )
    if DIMENSION_KIND_ISSUER in scheme_by_dimension:
        raise ConcentrationInputError(
            "ISSUER is CON-1-owned and carries no scheme — it is always computed and must not "
            "appear in scheme_by_dimension"
        )

    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=CONCENTRATION_MODEL_CODE,
    )
    coverage_floor = declared_concentration_parameters(session, version)

    upstream = resolve_completed_run_of_type(
        session,
        str(exposure_run_id),
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_EXPOSURE_AGGREGATE,
        label="exposure",
        error=ConcentrationInputError,
    )
    if upstream.scope_portfolio_id is None:
        raise ConcentrationInputError(
            f"exposure run {exposure_run_id} carries a NULL scope_portfolio_id (the OD-API-1b-D "
            "snapshot-consume honest NULL) — the concentration scope identity is uncomputable; "
            "select a run built with an explicit portfolio scope"
        )
    portfolio_id = str(upstream.scope_portfolio_id)

    snapshot = build_concentration_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
        exposure_run_id=str(exposure_run_id),
        scheme_by_dimension=scheme_by_dimension,
    )

    pinned = _parse_pins(
        list(list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant))
    )

    def _compute(run: CalculationRun) -> tuple[list[ConcentrationResult], list[str]]:
        rows: list[ConcentrationResult] = []
        gaps: list[str] = []
        dimensions: dict[str, tuple[str | None, str]] = {
            DIMENSION_KIND_ISSUER: (None, BASIS_NOT_APPLICABLE)
        }
        for dim, scheme_id in sorted(scheme_by_dimension.items()):
            dimensions[dim] = (scheme_id, pinned.basis_by_dimension.get(dim, BASIS_NOT_APPLICABLE))

        for dim, (scheme_id, basis) in sorted(dimensions.items()):
            atoms = _bucket_atoms(pinned, dim)
            result = compute_dimension(atoms, coverage_floor)
            if result.gaps:
                gaps.extend(f"{dim}: {g}" for g in result.gaps)
                continue
            rows.extend(
                _dimension_rows(
                    run=run,
                    snapshot_id=str(snapshot.id),
                    model_version_id=str(model_version_id),
                    portfolio_id=portfolio_id,
                    tenant_id=acting_tenant,
                    dimension_kind=dim,
                    scheme_id=scheme_id,
                    basis=basis,
                    result=result,
                    issuer_ids=pinned.issuer_by_instrument,
                )
            )
        return rows, gaps

    return execute_governed_run(
        session,
        acting_tenant=acting_tenant,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_CONCENTRATION,
        snapshot_id=str(snapshot.id),
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=_COMPLETENESS_RULE_NAME,
        rule_target_entity_type="concentration_result",
        result_entity_type="concentration_result",
        compute=_compute,
        format_reason=_format_reason,
        scope_portfolio_id=portfolio_id,
    )


class _PinnedContent:
    """The parsed pinned content, indexed for bucketing."""

    def __init__(self) -> None:
        self.atoms: list[dict[str, Any]] = []
        self.issuer_by_instrument: dict[str, str | None] = {}
        self.assignment_by_dim_instrument: dict[tuple[str, str], dict[str, Any]] = {}
        self.basis_by_dimension: dict[str, str] = {}


def _parse_pins(components: list[Any]) -> _PinnedContent:
    pinned = _PinnedContent()
    for comp in components:
        content = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_EXPOSURE:
            pinned.atoms.append(content)
        elif comp.component_kind == COMPONENT_KIND_ISSUER_EDGE:
            pinned.issuer_by_instrument[content["id"]] = content["issuer_id"]
        elif comp.component_kind == COMPONENT_KIND_CLASSIFICATION:
            key = (content["dimension_kind"], content["entity_id"])
            pinned.assignment_by_dim_instrument[key] = content
            pinned.basis_by_dimension[content["dimension_kind"]] = content["basis"]
        elif comp.component_kind == COMPONENT_KIND_CLASSIFICATION_SCHEME:
            pass  # the discriminator inputs; consumed by the builder's refusals
    return pinned


def _level1_code(assignment: dict[str, Any]) -> str:
    for node in assignment["closure"]:
        if node["level"] == 1:
            return str(node["code"])
    raise ConcentrationInputError(
        f"pinned closure for assignment {assignment['id']} carries no level-1 ancestor — the "
        "fail-closed ancestor walk (OQ-CON-1-28) should have refused this at build"
    )


def _bucket_atoms(pinned: _PinnedContent, dimension_kind: str) -> list[Atom]:
    atoms: list[Atom] = []
    for content in pinned.atoms:
        instrument_id = content["instrument_id"]
        amount = Decimal(content["exposure_amount"])
        issuer_id = pinned.issuer_by_instrument.get(instrument_id)
        if dimension_kind == DIMENSION_KIND_ISSUER:
            if issuer_id is None:
                atoms.append(Atom(amount, None, BUCKET_UNCLASSIFIABLE))
            else:
                atoms.append(Atom(amount, str(issuer_id)))
            continue
        assignment = pinned.assignment_by_dim_instrument.get((dimension_kind, instrument_id))
        if assignment is not None:
            atoms.append(Atom(amount, _level1_code(assignment)))
        elif issuer_id is None:
            atoms.append(Atom(amount, None, BUCKET_UNCLASSIFIABLE))
        else:
            atoms.append(Atom(amount, None, BUCKET_UNCLASSIFIED))
    return atoms


def _dimension_rows(
    *,
    run: CalculationRun,
    snapshot_id: str,
    model_version_id: str,
    portfolio_id: str,
    tenant_id: str,
    dimension_kind: str,
    scheme_id: str | None,
    basis: str,
    result: DimensionResult,
    issuer_ids: dict[str, str | None],
) -> list[ConcentrationResult]:
    """The DETAIL + SUMMARY rows of one dimension, shaped exactly to the 0057 CHECKs."""
    is_issuer_dim = dimension_kind == DIMENSION_KIND_ISSUER
    known_issuers = {str(v) for v in issuer_ids.values() if v is not None}
    rows: list[ConcentrationResult] = []
    for bucket in result.buckets:
        issuer_fk = (
            bucket.bucket_code
            if is_issuer_dim and not bucket.is_residual and bucket.bucket_code in known_issuers
            else None
        )
        rows.append(
            ConcentrationResult(
                tenant_id=tenant_id,
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot_id,
                model_version_id=model_version_id,
                portfolio_id=portfolio_id,
                row_kind=ROW_KIND_DETAIL,
                dimension_kind=dimension_kind,
                metric_type=METRIC_TYPE_SHARE,
                bucket_code=bucket.bucket_code,
                issuer_id=issuer_fk,
                scheme_id=None if is_issuer_dim else scheme_id,
                basis=basis,
                denominator_basis=DENOMINATOR_BASIS_INVESTED_LONG,
                gross_amount=bucket.gross_amount,
                long_amount=bucket.long_amount,
                short_amount=bucket.short_amount,
                net_amount=bucket.net_amount,
                share_invested_long=bucket.share_invested_long,
                metric_value=None,
                coverage_ratio=None,
                coverage_classifiable=None,
            )
        )
    run_gross = sum((b.gross_amount for b in result.buckets), Decimal("0"))
    run_long = sum((b.long_amount for b in result.buckets), Decimal("0"))
    run_short = sum((b.short_amount for b in result.buckets), Decimal("0"))
    run_net = sum((b.net_amount for b in result.buckets), Decimal("0"))
    for suffix, value in (
        ("MAX_SHARE", result.max_share),
        ("HHI", result.hhi),
        ("CR_5", result.cr_n),
    ):
        rows.append(
            ConcentrationResult(
                tenant_id=tenant_id,
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot_id,
                model_version_id=model_version_id,
                portfolio_id=portfolio_id,
                row_kind=ROW_KIND_SUMMARY,
                dimension_kind=dimension_kind,
                metric_type=f"{suffix}_{dimension_kind}",
                bucket_code=BUCKET_SUMMARY,
                issuer_id=None,
                scheme_id=None if is_issuer_dim else scheme_id,
                basis=basis,
                denominator_basis=DENOMINATOR_BASIS_INVESTED_LONG,
                gross_amount=run_gross,
                long_amount=run_long,
                short_amount=run_short,
                net_amount=run_net,
                share_invested_long=None,
                metric_value=value,
                coverage_ratio=result.coverage_ratio,
                coverage_classifiable=result.coverage_classifiable,
            )
        )
    return rows
