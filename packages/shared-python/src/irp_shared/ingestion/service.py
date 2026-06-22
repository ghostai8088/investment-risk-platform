"""Generic ingestion-staging orchestration (P1A-4, REQ-INT-001) — the first composing slice.

``stage_upload`` runs the whole governed flow in the **caller's single tenant-scoped transaction**
(no mid-call commit — the endpoint owns the commit): resolve the provenance ``data_source`` (RLS),
create the ``ingestion_batch`` (audited ``DATA.INGEST`` create) + the mandatory lineage ORIGIN edge
(P1A-1 ``record_lineage``, recorded for EVERY batch), run the anti-corruption layer, stage immutable
rows, run generic data-quality checks (P1A-3 ``run_quality_check``) and the gate
(``assert_passed_quality_checks``), then finalize.

No-silent-failure / durable evidence (CTRL-029 / CTRL-032): on an anti-corruption rejection or a DQ
ERROR the batch is driven to ``REJECTED`` and the failure is **committed** (batch + staged rows +
flagged ``data_quality_result`` + ``DATA.VALIDATE`` + ``DATA.INGEST`` transition + lineage all
survive). We never roll back the evidence trail; ``run_quality_check`` flushes its result/audit
**before** it raises, so the rejection path simply continues (set REJECTED, audit, return) — it must
NOT roll back or use a rolling-back savepoint (that would discard the very evidence). Audit
``after_value`` carries metadata/reason codes ONLY — never raw payload or the full client path.

Composes ``irp_shared.lineage`` + ``irp_shared.dq`` + ``irp_shared.audit`` — and nothing
imports it back (no backend / model coupling); it maps NOTHING into canonical tables.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NoReturn, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import OUTCOME_WARN, DataQualityRule
from irp_shared.dq.service import (
    DataQualityError,
    QualityCheckFailedError,
    assert_passed_quality_checks,
    run_quality_check,
)
from irp_shared.ingestion.anticorruption import (
    AntiCorruptionError,
    decode_text,
    parse_csv,
    sanitize_filename,
    scan_for_malware,
    validate_file_type,
)
from irp_shared.ingestion.models import (
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_RECEIVED,
    STATUS_REJECTED,
    IngestionBatch,
    IngestionStagedRecord,
)
from irp_shared.lineage.models import DataSource
from irp_shared.lineage.service import (
    DataSourceNotVisible,
    assert_has_lineage,
    record_lineage,
)

#: Audit taxonomy code for the batch lifecycle (DATA category). Reused, not minted — P1A-4 ACTIVATES
#: the reserved DATA.INGEST; DQ runs reuse DATA.VALIDATE (emitted by run_quality_check).
INGEST_EVENT = "DATA.INGEST"

#: The polymorphic DQ rule target this slice runs (generic staged rows). Rules opt in by value.
STAGING_ROW_TARGET = "staging.row"

#: The entity type DQ results / lineage record against (so the gate + placeholder resolve).
BATCH_ENTITY_TYPE = "ingestion_batch"

#: A fallback batch filename when the client name is unsafe (so a rejection is still auditable).
_REJECTED_NAME = "(rejected-upload)"


class _AuditCtx(TypedDict):
    """The shared actor/correlation kwargs threaded into every audit emission for one upload."""

    actor_id: str
    actor_type: str
    agent_model: str | None
    agent_model_version: str | None
    on_behalf_of: str | None
    correlation_id: str | None


class IngestionRejected(Exception):
    """Raised to the API layer when a persisted batch ended in a terminal failure state; carries the
    committed batch + a stable reason code so the endpoint returns a 4xx (never a 200)."""

    def __init__(self, batch: IngestionBatch, reason: str) -> None:
        super().__init__(f"ingestion batch {batch.id} rejected: {reason}")
        self.batch = batch
        self.reason = reason


def _ingest_event(
    session: Session,
    batch: IngestionBatch,
    *,
    action: str,
    actor_id: str,
    actor_type: str,
    before_status: str | None,
    outcome: str,
    reason: str | None,
    agent_model: str | None,
    agent_model_version: str | None,
    on_behalf_of: str | None,
    correlation_id: str | None,
) -> None:
    """Emit a ``DATA.INGEST`` lifecycle event (metadata/reason ONLY — never raw payload/path)."""
    after: dict[str, Any] = {
        "status": batch.status,
        "filename": batch.filename,  # sanitized basename only
        "content_type": batch.content_type,
        "byte_size": batch.byte_size,
        "data_source_id": batch.data_source_id,
        "scan_status": batch.scan_status,
        "row_count": batch.row_count,
        "staged_count": batch.staged_count,
        "failed_count": batch.failed_count,
    }
    if reason is not None:
        after["reason"] = reason
    record_event(
        session,
        event_type=INGEST_EVENT,
        tenant_id=batch.tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        source_module="ingestion",
        entity_type=BATCH_ENTITY_TYPE,
        entity_id=batch.id,
        action=action,
        outcome=outcome,
        before_value=({"status": before_status} if before_status is not None else None),
        after_value=after,
        correlation_id=correlation_id,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        on_behalf_of=on_behalf_of,
        data_classification="DC-2",  # metadata may echo the (sanitized) client filename
    )


def stage_upload(
    session: Session,
    *,
    tenant_id: str,
    data_source_id: str,
    filename: str | None,
    content_type: str | None,
    raw_bytes: bytes,
    actor_id: str,
    actor_type: str = "user",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    on_behalf_of: str | None = None,
    correlation_id: str | None = None,
) -> IngestionBatch:
    """Ingest one upload generically (no canonical mapping). Returns the persisted batch on success;
    raises :class:`IngestionRejected` (persisted REJECTED) on an anti-corruption/DQ failure, or
    :class:`DataSourceNotVisible` if the provenance source is not visible in the caller's tenant.

    The caller MUST commit the batch's transaction (single-transaction invariant)."""
    # --- Provenance: resolve data_source under RLS (cross-tenant/unknown fails closed). ---
    source = session.execute(
        select(DataSource).where(DataSource.id == str(data_source_id))
    ).scalar_one_or_none()
    if source is None:
        raise DataSourceNotVisible(str(data_source_id))

    # --- Best-effort sanitized name so even an unsafe-filename rejection is auditable. ---
    early_error: AntiCorruptionError | None = None
    try:
        safe_name = sanitize_filename(filename)
    except AntiCorruptionError as exc:
        safe_name, early_error = _REJECTED_NAME, exc

    common: _AuditCtx = {
        "actor_id": actor_id,
        "actor_type": actor_type,
        "agent_model": agent_model,
        "agent_model_version": agent_model_version,
        "on_behalf_of": on_behalf_of,
        "correlation_id": correlation_id,
    }

    # --- Create the batch (RECEIVED) + audit + the mandatory lineage ORIGIN edge (every batch). ---
    batch = IngestionBatch(
        tenant_id=str(tenant_id),
        data_source_id=source.id,  # server-resolved; RLS WITH CHECK is the backstop
        filename=safe_name,
        # Bound the client-supplied content_type to the column width (varchar(100)) so an
        # over-length value can never raise a truncation error before the durable-evidence path.
        content_type=(content_type[:100] if content_type else None),
        byte_size=len(raw_bytes),
        status=STATUS_RECEIVED,
        scan_status=scan_for_malware(raw_bytes),  # no-op AV seam (OD-042)
    )
    session.add(batch)
    session.flush()
    _ingest_event(
        session,
        batch,
        action="create",
        before_status=None,
        outcome="success",
        reason=None,
        **common,
    )
    record_lineage(
        session,
        source=source,
        target_entity_type=BATCH_ENTITY_TYPE,
        target_entity_id=batch.id,
    )

    # --- Anti-corruption (THR-05/06): a failure -> REJECTED, audited, evidence committed. ---
    if early_error is not None:
        _reject(session, batch, early_error.reason, **common)
    try:
        validate_file_type(safe_name, content_type)
        rows: Sequence[dict[str, Any]] = parse_csv(decode_text(raw_bytes))
    except AntiCorruptionError as exc:
        _reject(session, batch, exc.reason, **common)

    # --- Stage immutable rows (generic JSON payload; no canonical mapping). ---
    for index, row in enumerate(rows):
        session.add(
            IngestionStagedRecord(
                tenant_id=str(tenant_id), batch_id=batch.id, row_number=index, payload=dict(row)
            )
        )
    session.flush()
    batch.row_count = len(rows)
    batch.staged_count = len(rows)

    # --- Generic data quality (P1A-3): run active staging rules; ERROR rejects, WARNING flags. ---
    active_rules = (
        session.execute(
            select(DataQualityRule).where(
                DataQualityRule.target_entity_type == STAGING_ROW_TARGET,
                DataQualityRule.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    warned = 0
    for rule in active_rules:
        try:
            result = run_quality_check(
                session,
                rule=rule,
                dataset=rows,
                actor_id=actor_id,
                target_entity_type=BATCH_ENTITY_TYPE,
                target_entity_id=batch.id,
                data_source_id=batch.data_source_id,
                ingestion_batch_id=batch.id,
                actor_type=actor_type,
                agent_model=agent_model,
                agent_model_version=agent_model_version,
                on_behalf_of=on_behalf_of,
                correlation_id=correlation_id,
            )
        except DataQualityError:
            # ERROR-severity FAIL or evaluator error: result + DATA.VALIDATE already flushed by
            # run_quality_check. Do NOT roll back — persist the rejection as committed evidence.
            _reject(session, batch, "dq_failed", failed=True, **common)
        if result.outcome == OUTCOME_WARN:
            warned += 1

    # --- The gate (fail-closed): no recorded checks (e.g. empty active rule set) -> REJECTED. ---
    try:
        assert_passed_quality_checks(session, BATCH_ENTITY_TYPE, batch.id, tenant_id=str(tenant_id))
    except QualityCheckFailedError:
        _reject(session, batch, "dq_gate_failed", failed=True, **common)

    # --- BX-LIN no-bypass (CTRL-013): a finalized batch must have a provenance path. ---
    assert_has_lineage(session, BATCH_ENTITY_TYPE, batch.id)

    # --- Finalize (COMPLETED, or COMPLETED_WITH_WARNINGS if any WARNING flagged). ---
    before = batch.status
    batch.failed_count = warned
    batch.status = STATUS_COMPLETED_WITH_WARNINGS if warned else STATUS_COMPLETED
    batch.completed_at = utcnow()
    session.flush()
    _ingest_event(
        session,
        batch,
        action="status_change",
        before_status=before,
        outcome="success",
        reason=None,
        **common,
    )
    return batch


def _reject(
    session: Session,
    batch: IngestionBatch,
    reason: str,
    *,
    failed: bool = False,
    actor_id: str,
    actor_type: str,
    agent_model: str | None,
    agent_model_version: str | None,
    on_behalf_of: str | None,
    correlation_id: str | None,
) -> NoReturn:
    """Drive the batch to REJECTED, audit the transition (outcome='failure'), and raise
    :class:`IngestionRejected`. The transaction is NOT rolled back — the rejection (and any flushed
    DQ result) is durable evidence (CTRL-029); the caller commits before surfacing the 4xx."""
    before = batch.status
    batch.status = STATUS_REJECTED
    batch.completed_at = utcnow()
    if failed:
        batch.failed_count = (batch.failed_count or 0) + 1
    session.flush()
    _ingest_event(
        session,
        batch,
        action="status_change",
        before_status=before,
        outcome="failure",
        reason=reason,
        actor_id=actor_id,
        actor_type=actor_type,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        on_behalf_of=on_behalf_of,
        correlation_id=correlation_id,
    )
    raise IngestionRejected(batch, reason)
