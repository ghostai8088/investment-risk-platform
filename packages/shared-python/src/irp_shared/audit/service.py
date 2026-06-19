"""Audit write and verification utilities.

``record_event`` is the only sanctioned way to write an audit event: it append-only
inserts, assigns the next per-chain sequence number, and computes the hash chain.
``verify_chain`` independently recomputes hashes to detect tampering (CTRL-026).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from irp_shared.audit.hashing import GENESIS_HASH, chain_hash, payload_hash
from irp_shared.audit.models import AuditCheckpoint, AuditEvent


def _iso(dt: datetime) -> str:
    """Canonical UTC ISO-8601 string used for both storage and hashing."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _advisory_lock_key(chain_id: str) -> int:
    """Deterministic signed 64-bit key for a per-tenant audit chain (advisory lock)."""
    digest = hashlib.blake2b(chain_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_chain(session: Session, chain_id: str) -> None:
    """Serialize concurrent writers of one tenant's audit chain (BR-18, OD-051).

    On PostgreSQL, take a transaction-scoped advisory lock keyed by the chain so concurrent
    ``record_event`` calls for the same tenant produce gapless, unique ``sequence_no`` values
    (released automatically on commit/rollback). On other engines (SQLite in unit tests),
    writes are already serialized, so this is a no-op.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _advisory_lock_key(chain_id)}
        )


def _build_payload(
    *,
    event_type: str,
    event_time: str,
    tenant_id: str,
    actor_type: str,
    actor_id: str,
    on_behalf_of: str | None,
    source_module: str,
    entity_type: str | None,
    entity_id: str | None,
    action: str,
    before_value: dict[str, Any] | None,
    after_value: dict[str, Any] | None,
    justification: str | None,
    approval_ref: str | None,
    correlation_id: str | None,
    outcome: str,
    severity: str,
    data_classification: str,
    agent_model: str | None,
    agent_model_version: str | None,
    chain_id: str,
    sequence_no: int,
) -> dict[str, Any]:
    """The exact, ordered set of fields covered by ``event_payload_hash``."""
    return {
        "event_type": event_type,
        "event_time": event_time,
        "tenant_id": tenant_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "on_behalf_of": on_behalf_of,
        "source_module": source_module,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "before_value": before_value,
        "after_value": after_value,
        "justification": justification,
        "approval_ref": approval_ref,
        "correlation_id": correlation_id,
        "outcome": outcome,
        "severity": severity,
        "data_classification": data_classification,
        "agent_model": agent_model,
        "agent_model_version": agent_model_version,
        "chain_id": chain_id,
        "sequence_no": sequence_no,
    }


def record_event(
    session: Session,
    *,
    event_type: str,
    tenant_id: str,
    actor_type: str,
    actor_id: str,
    source_module: str,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any] | None = None,
    justification: str | None = None,
    approval_ref: str | None = None,
    correlation_id: str | None = None,
    on_behalf_of: str | None = None,
    outcome: str = "success",
    severity: str = "info",
    data_classification: str = "DC-2",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    event_time: datetime | None = None,
) -> AuditEvent:
    """Append a hash-chained audit event for ``tenant_id`` (one chain per tenant)."""
    chain_id = str(tenant_id)
    _lock_chain(session, chain_id)
    last = session.execute(
        select(AuditEvent)
        .where(AuditEvent.chain_id == chain_id)
        .order_by(AuditEvent.sequence_no.desc())
        .limit(1)
    ).scalar_one_or_none()

    sequence_no = 1 if last is None else last.sequence_no + 1
    previous_event_hash = GENESIS_HASH if last is None else last.event_hash
    event_time_iso = _iso(event_time or datetime.now(tz=UTC))

    payload = _build_payload(
        event_type=event_type,
        event_time=event_time_iso,
        tenant_id=str(tenant_id),
        actor_type=actor_type,
        actor_id=str(actor_id),
        on_behalf_of=on_behalf_of,
        source_module=source_module,
        entity_type=entity_type,
        entity_id=(str(entity_id) if entity_id is not None else None),
        action=action,
        before_value=before_value,
        after_value=after_value,
        justification=justification,
        approval_ref=approval_ref,
        correlation_id=correlation_id,
        outcome=outcome,
        severity=severity,
        data_classification=data_classification,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        chain_id=chain_id,
        sequence_no=sequence_no,
    )
    event_payload_hash = payload_hash(payload)
    event_hash = chain_hash(previous_event_hash, event_payload_hash)

    audit_event = AuditEvent(
        chain_id=chain_id,
        sequence_no=sequence_no,
        tenant_id=str(tenant_id),
        event_time=event_time_iso,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=str(actor_id),
        on_behalf_of=on_behalf_of,
        source_module=source_module,
        entity_type=entity_type,
        entity_id=(str(entity_id) if entity_id is not None else None),
        action=action,
        before_value=before_value,
        after_value=after_value,
        justification=justification,
        approval_ref=approval_ref,
        correlation_id=correlation_id,
        outcome=outcome,
        severity=severity,
        data_classification=data_classification,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        previous_event_hash=previous_event_hash,
        event_payload_hash=event_payload_hash,
        event_hash=event_hash,
    )
    session.add(audit_event)
    session.flush()
    return audit_event


@dataclass(frozen=True)
class ChainVerificationResult:
    ok: bool
    events_checked: int
    broken_sequence_no: int | None = None
    reason: str | None = None


def verify_chain(session: Session, tenant_id: str) -> ChainVerificationResult:
    """Recompute the chain for a tenant and report the first integrity failure (CTRL-026)."""
    chain_id = str(tenant_id)
    events = list(
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.chain_id == chain_id)
            .order_by(AuditEvent.sequence_no.asc())
        ).scalars()
    )

    previous_event_hash = GENESIS_HASH
    expected_seq = 1
    for ev in events:
        if ev.sequence_no != expected_seq:
            return ChainVerificationResult(False, expected_seq - 1, ev.sequence_no, "sequence_gap")

        payload = _build_payload(
            event_type=ev.event_type,
            event_time=ev.event_time,
            tenant_id=ev.tenant_id,
            actor_type=ev.actor_type,
            actor_id=ev.actor_id,
            on_behalf_of=ev.on_behalf_of,
            source_module=ev.source_module,
            entity_type=ev.entity_type,
            entity_id=ev.entity_id,
            action=ev.action,
            before_value=ev.before_value,
            after_value=ev.after_value,
            justification=ev.justification,
            approval_ref=ev.approval_ref,
            correlation_id=ev.correlation_id,
            outcome=ev.outcome,
            severity=ev.severity,
            data_classification=ev.data_classification,
            agent_model=ev.agent_model,
            agent_model_version=ev.agent_model_version,
            chain_id=ev.chain_id,
            sequence_no=ev.sequence_no,
        )
        if payload_hash(payload) != ev.event_payload_hash:
            return ChainVerificationResult(
                False, ev.sequence_no, ev.sequence_no, "payload_tampered"
            )
        if ev.previous_event_hash != previous_event_hash:
            return ChainVerificationResult(
                False, ev.sequence_no, ev.sequence_no, "chain_link_broken"
            )
        if chain_hash(previous_event_hash, ev.event_payload_hash) != ev.event_hash:
            return ChainVerificationResult(
                False, ev.sequence_no, ev.sequence_no, "event_hash_mismatch"
            )

        previous_event_hash = ev.event_hash
        expected_seq += 1

    return ChainVerificationResult(True, len(events))


def create_checkpoint(session: Session, tenant_id: str) -> AuditCheckpoint | None:
    """Capture the latest sequence and hash for a tenant's chain (CP-01)."""
    chain_id = str(tenant_id)
    last = session.execute(
        select(AuditEvent)
        .where(AuditEvent.chain_id == chain_id)
        .order_by(AuditEvent.sequence_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return None
    checkpoint = AuditCheckpoint(
        tenant_id=str(tenant_id),
        chain_id=chain_id,
        sequence_no=last.sequence_no,
        last_event_hash=last.event_hash,
    )
    session.add(checkpoint)
    session.flush()
    return checkpoint


@dataclass(frozen=True)
class ChainReport:
    chain_id: str
    result: ChainVerificationResult
    checkpoint_sequence_no: int | None = None


def verify_all_chains(session: Session, *, create_checkpoints: bool = False) -> list[ChainReport]:
    """Verify every tenant's audit chain; optionally checkpoint each (ops job, CTRL-026).

    Returns one report per chain (ordered by chain_id). Backs the audit-verification CLI.
    """
    chain_ids = list(
        session.execute(
            select(AuditEvent.chain_id).distinct().order_by(AuditEvent.chain_id)
        ).scalars()
    )
    reports: list[ChainReport] = []
    for chain_id in chain_ids:
        result = verify_chain(session, chain_id)
        checkpoint_seq: int | None = None
        if create_checkpoints and result.ok:
            checkpoint = create_checkpoint(session, chain_id)
            checkpoint_seq = checkpoint.sequence_no if checkpoint is not None else None
        reports.append(
            ChainReport(chain_id=chain_id, result=result, checkpoint_sequence_no=checkpoint_seq)
        )
    return reports
