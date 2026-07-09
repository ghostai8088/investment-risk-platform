"""P3-C2 OD-B: exposure adopts the shared ``execute_governed_run`` scaffold (relocated to
``calc`` — the neutral home below both risk and exposure).

The adoption is behavior-preserving on the COMPLETED path (audit sequence, ORIGIN edges, rows)
and brings TWO INTENDED improvements on the FAILED path that exposure was silently missing —
proven here as the delta:

  1. ``failure_reason`` is PERSISTED on the FAILED ``calculation_run`` row (was returned-only ⇒
     the GET showed None);
  2. the snapshot->run DEPENDS_ON lineage edge is recorded BEFORE the DQ gate, so a committed
     FAILED exposure run KEEPS its input-lineage link (the P3-1 lineage fold, extended here).

Reuses the ``test_exposure`` fixtures (function-scoped session; the P3-C1 golden precedent of
importing sibling test helpers)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_exposure import (  # noqa: F401 - shared fixtures/helpers (package-less tests dir)
    _ccy,
    _fx,
    _holding,
    _pf,
    _run,
    run_exposure,
    session,
)

from irp_shared.audit.models import AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.lineage.models import EDGE_KIND_DEPENDENCY, EDGE_KIND_ORIGIN, LineageEdge

ACTOR_ID = "s"  # matches test_exposure.ACTOR

# The exposure family now rides the shared scaffold, so it must meet the SAME golden bar the four
# risk binders meet in test_p3c1_scaffold_preservation.py — the ORDERED CALC.* audit sequence and
# the DQ-rule identity, not merely edge counts (review fold E1). These constants mirror that
# golden's _COMPLETED_SEQUENCE/_FAILED_SEQUENCE.
_COMPLETED_SEQUENCE = [
    ("CALC.RUN_CREATE", "create", None, "CREATED", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "CREATED", "RUNNING", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "RUNNING", "COMPLETED", "success"),
]
_FAILED_SEQUENCE = [
    ("CALC.RUN_CREATE", "create", None, "CREATED", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "CREATED", "RUNNING", "success"),
    ("CALC.RUN_STATUS_CHANGE", "status_change", "RUNNING", "FAILED", "failure"),
]
# The exposure scaffold call-site's governed-rule identity (exposure/service.py) — a typo in any
# of these would mint a DIFFERENT per-tenant rule with edge/row counts unchanged.
_EXPOSURE_RULE_CODE = "exposure.completeness"
_EXPOSURE_RULE_NAME = "Exposure run input completeness (mark + FX)"
_EXPOSURE_RULE_TARGET = "exposure_aggregate"


def _lifecycle(db: Session, run_id: str) -> list[tuple]:
    rows = (
        db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "calculation_run",
                AuditEvent.entity_id == run_id,
            )
            .order_by(AuditEvent.sequence_no)
        )
        .scalars()
        .all()
    )
    return [
        (
            e.event_type,
            e.action,
            (e.before_value or {}).get("status"),
            (e.after_value or {}).get("status"),
            e.outcome,
        )
        for e in rows
    ]


def _assert_dq_identity(db: Session, run_id: str) -> None:
    """Pin the FAILED run's DQ evidence to the exposure family's governed rule (code/name/target
    verbatim) — the scaffold call-site parameters, not just that SOME rule fired."""
    results = (
        db.execute(
            select(DataQualityResult).where(
                DataQualityResult.target_entity_type == "calculation_run",
                DataQualityResult.target_entity_id == run_id,
            )
        )
        .scalars()
        .all()
    )
    assert results
    rule_ids = {r.rule_id for r in results}
    assert len(rule_ids) == 1
    rule = db.execute(
        select(DataQualityRule).where(DataQualityRule.id == next(iter(rule_ids)))
    ).scalar_one()
    assert rule.code == _EXPOSURE_RULE_CODE
    assert rule.name == _EXPOSURE_RULE_NAME
    assert rule.target_entity_type == _EXPOSURE_RULE_TARGET


def _failed_run(db: Session, tenant: str):  # noqa: ANN202
    """A committed FAILED exposure run: build a USD-base snapshot (pins EUR/USD), then CONSUME it
    requesting base JPY (no JPY legs pinned) — the post-create FX-completeness gate fails."""
    _ccy(db, "USD", "EUR")
    pf = _pf(db, tenant)
    _holding(db, tenant, pf, "I0", "100", "7.00", "EUR")
    _fx(db, tenant, "EUR", "USD", "1.10")
    db.flush()
    built = _run(db, tenant, pf, "USD")
    from irp_shared.exposure import ExposureActor

    return run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id=ACTOR_ID),
        code_version="v1",
        environment_id="ci",
        snapshot_id=built.run.input_snapshot_id,
        base_currency="JPY",
    )


def test_failed_exposure_run_persists_reason(session: Session) -> None:  # noqa: F811
    """IMPROVEMENT 1: the FAILED run row carries failure_reason (was None pre-P3-C2)."""
    tenant = str(uuid.uuid4())
    result = _failed_run(session, tenant)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.failure_reason is not None
    # Persisted on the ROW, not just returned (the GET reads the row).
    row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == result.run.run_id)
    ).scalar_one()
    assert row.failure_reason == result.failure_reason
    # The bare P3-1 reason format is preserved verbatim (a DataQualityError str).
    assert "severity=ERROR" in row.failure_reason
    # GOLDEN BAR (E1): the FAILED lifecycle is the exact ordered CALC.* sequence, and the DQ
    # evidence references the exposure family's governed rule verbatim.
    assert _lifecycle(session, result.run.run_id) == _FAILED_SEQUENCE
    _assert_dq_identity(session, result.run.run_id)


def test_failed_exposure_run_keeps_depends_on_edge(session: Session) -> None:  # noqa: F811
    """IMPROVEMENT 2: a FAILED exposure run STILL has the snapshot->run DEPENDS_ON edge
    (recorded before the gate) — previously the edge was written only on the success path."""
    tenant = str(uuid.uuid4())
    result = _failed_run(session, tenant)
    run_id = result.run.run_id
    deps = [
        e
        for e in session.execute(select(LineageEdge)).scalars()
        if e.edge_kind == EDGE_KIND_DEPENDENCY and e.target_entity_id == run_id
    ]
    assert len(deps) == 1
    assert deps[0].run_id == run_id
    # And ZERO ORIGIN edges (a FAILED run wrote no rows).
    origin = [
        e
        for e in session.execute(select(LineageEdge)).scalars()
        if e.edge_kind == EDGE_KIND_ORIGIN and e.run_id == run_id
    ]
    assert origin == []


def test_completed_exposure_run_lineage_and_rows_preserved(session: Session) -> None:  # noqa: F811
    """PRESERVED: the COMPLETED path still records DEPENDS_ON (run-stamped) + one ORIGIN edge
    per row, and produces the rows — byte-behavior unchanged by the scaffold adoption."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    run_id = result.run.run_id
    assert result.status == RunStatus.COMPLETED.value
    assert result.failure_reason is None
    assert len(result.rows) == 1
    edges = list(session.execute(select(LineageEdge)).scalars())
    deps = [
        e for e in edges if e.edge_kind == EDGE_KIND_DEPENDENCY and e.target_entity_id == run_id
    ]
    assert len(deps) == 1 and deps[0].run_id == run_id
    origin = [e for e in edges if e.edge_kind == EDGE_KIND_ORIGIN and e.run_id == run_id]
    assert len(origin) == len(result.rows)
    for e in origin:
        assert e.target_entity_type == "exposure_aggregate"
    # GOLDEN BAR (E1): the COMPLETED lifecycle is the exact ordered CALC.* sequence — a scaffold
    # regression that skipped RUNNING or mislabeled an outcome would keep edges/rows intact but
    # fail HERE (matching the P3-C1 golden the risk binders are held to).
    assert _lifecycle(session, run_id) == _COMPLETED_SEQUENCE
