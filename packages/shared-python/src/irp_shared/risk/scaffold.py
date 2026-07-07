"""The shared governed-run lifecycle scaffold (P3-C1, OD-P3-C1-D — the deferral paydown).

Extracted VERBATIM from the four risk binders (P3-1 sensitivities, P3-3 factor exposures, P3-4
covariance, P3-5 VaR), which had accreted four copies of the identical tail:

    create_run → RUNNING → snapshot--DEPENDS_ON-->run → compute(rows, gaps)
    → fail-closed presence gate
    → [FAILED + persisted reason]  |  [rows + per-row ORIGIN + COMPLETED]

**Behavior-preserving (the R0 bar):** the operation ORDER, the audit-event sequence, the lineage
edges, the DQ evidence shape, and each binder's ``failure_reason`` FORMAT (a formatter callback)
are byte-identical to the pre-extraction binders — proven by the P3-C1 golden-capture suite
(``test_p3c1_scaffold_preservation.py``), written and green BEFORE this module existed. The
binders keep their pre-create gates and pinned-content adjudication; ONLY the lifecycle tail
lives here. The compute stays a pure callback over pre-adjudicated inputs (the AD-014
snapshot-only invariant is the caller's; this module performs no reads beyond what its callbacks
do).

The DEPENDS_ON edge is recorded BEFORE the gate (a committed FAILED run keeps its input link —
the P3-1 lineage fold); ORIGIN edges exist only on the success path (a FAILED run has zero
rows).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.dq.gates import ensure_presence_rule, run_presence_gate
from irp_shared.lineage.models import EDGE_KIND_DEPENDENCY, EDGE_KIND_ORIGIN
from irp_shared.lineage.service import record_internal_lineage, record_run_lineage


@dataclass(frozen=True)
class GovernedRunOutcome:
    """The scaffold outcome: the run + terminal status + the rows written (empty on FAILED) +
    the formatted, PERSISTED ``failure_reason`` (None on COMPLETED). Each binder wraps this in
    its own public result dataclass (their shapes are part of the shipped API)."""

    run: CalculationRun
    status: str
    rows: list[Any] = field(default_factory=list)
    failure_reason: str | None = None


def execute_governed_run(
    session: Session,
    *,
    acting_tenant: str,
    actor_id: str,
    actor_type: str,
    run_type: str,
    snapshot_id: str,
    model_version_id: str | None,
    code_version: str,
    environment_id: str,
    rule_code: str,
    rule_name: str,
    rule_target_entity_type: str,
    result_entity_type: str,
    compute: Callable[[CalculationRun], tuple[list[Any], list[str]]],
    format_reason: Callable[[Exception, list[str]], str],
) -> GovernedRunOutcome:
    """Run the governed lifecycle tail. ``compute(run)`` returns ``(rows, gaps)`` over the
    caller's pre-adjudicated pinned content — rows are UNWRITTEN model instances; a non-empty
    ``gaps`` list fails the presence gate closed (⇒ a committed FAILED run + DQ evidence + the
    ``format_reason(gate, gaps)`` string persisted on the run + ZERO rows)."""
    from irp_shared.dq.service import (
        DataQualityError,
    )  # local: keep the import-fence surface minimal (the binders' precedent)

    run = create_run(
        session,
        tenant_id=acting_tenant,
        run_type=run_type,
        initiated_by=actor_id,
        input_snapshot_id=snapshot_id,
        model_version_id=model_version_id,
        code_version=code_version,
        environment_id=environment_id,
    )
    update_run_status(session, run, RunStatus.RUNNING, actor_id=actor_id)

    # The snapshot->run DEPENDS_ON edge is an INPUT-DEPENDENCY fact — recorded BEFORE the DQ
    # gate so a committed FAILED run keeps a traceable link to its input (the P3-1 lineage
    # fold). The run->result ORIGIN edges stay on the success path.
    record_internal_lineage(
        session,
        snapshot_id=snapshot_id,
        target_entity_type="calculation_run",
        target_entity_id=run.run_id,
        edge_kind=EDGE_KIND_DEPENDENCY,
        run_id=run.run_id,
    )

    rows, gaps = compute(run)
    try:
        # Fail-closed BEFORE any result INSERT (emits DATA.VALIDATE; raises on a gap).
        rule = ensure_presence_rule(
            session,
            tenant_id=str(acting_tenant),
            code=rule_code,
            name=rule_name,
            target_entity_type=rule_target_entity_type,
            actor_id=actor_id,
            actor_type=actor_type,
        )
        run_presence_gate(
            session,
            rule=rule,
            gaps=gaps,
            target_entity_type="calculation_run",
            target_entity_id=run.run_id,
            actor_id=actor_id,
            actor_type=actor_type,
        )
    except DataQualityError as gate:
        reason = format_reason(gate, gaps)  # each binder's format, verbatim
        update_run_status(
            session,
            run,
            RunStatus.FAILED,
            actor_id=actor_id,
            outcome="failure",
            failure_reason=reason,
        )
        return GovernedRunOutcome(
            run=run, status=RunStatus.FAILED.value, rows=[], failure_reason=reason
        )

    # --- Governed write: rows + run->result (ORIGIN, run_id) ---
    for row in rows:
        session.add(row)
    session.flush()
    for row in rows:
        record_run_lineage(
            session,
            run_id=run.run_id,
            target_entity_type=result_entity_type,
            target_entity_id=row.id,
            edge_kind=EDGE_KIND_ORIGIN,
        )

    update_run_status(session, run, RunStatus.COMPLETED, actor_id=actor_id)
    return GovernedRunOutcome(run=run, status=RunStatus.COMPLETED.value, rows=rows)
