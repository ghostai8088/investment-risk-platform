"""Audit framework tests: event creation, chain validation, tamper detection, append-only."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from irp_shared.audit.hashing import GENESIS_HASH
from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import create_checkpoint, record_event, verify_chain


def _tenant() -> str:
    return str(uuid.uuid4())


def test_record_event_creates_chained_events(session: Session) -> None:
    tenant = _tenant()
    e1 = record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant,
        actor_type="user",
        actor_id="user-1",
        source_module="test",
        action="create",
        after_value={"k": "v1"},
    )
    e2 = record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant,
        actor_type="user",
        actor_id="user-1",
        source_module="test",
        action="create",
        after_value={"k": "v2"},
    )

    assert e1.sequence_no == 1
    assert e1.previous_event_hash == GENESIS_HASH
    assert e2.sequence_no == 2
    assert e2.previous_event_hash == e1.event_hash
    assert len(e1.event_hash) == 64


def test_verify_chain_ok(session: Session) -> None:
    tenant = _tenant()
    for i in range(5):
        record_event(
            session,
            event_type="TEST.EVENT",
            tenant_id=tenant,
            actor_type="user",
            actor_id="user-1",
            source_module="test",
            action="create",
            after_value={"i": i},
        )
    result = verify_chain(session, tenant)
    assert result.ok is True
    assert result.events_checked == 5


def test_tamper_detection(session: Session) -> None:
    tenant = _tenant()
    for i in range(3):
        record_event(
            session,
            event_type="TEST.EVENT",
            tenant_id=tenant,
            actor_type="user",
            actor_id="user-1",
            source_module="test",
            action="create",
            after_value={"i": i},
        )
    # Tamper out-of-band (simulating direct DB access that bypasses the app guard).
    session.execute(
        text("UPDATE audit_event SET after_value = :v WHERE sequence_no = 2"),
        {"v": '{"i": 999}'},
    )
    session.commit()
    session.expire_all()  # drop cached ORM state so verify reloads the tampered row

    result = verify_chain(session, tenant)
    assert result.ok is False
    assert result.broken_sequence_no == 2
    assert result.reason == "payload_tampered"


def test_append_only_guard_blocks_update(session: Session) -> None:
    tenant = _tenant()
    event = record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant,
        actor_type="user",
        actor_id="user-1",
        source_module="test",
        action="create",
    )
    event.action = "tampered"
    with pytest.raises(AppendOnlyViolation):
        session.flush()


def test_checkpoint_captures_latest(session: Session) -> None:
    tenant = _tenant()
    last = None
    for i in range(4):
        last = record_event(
            session,
            event_type="TEST.EVENT",
            tenant_id=tenant,
            actor_type="user",
            actor_id="user-1",
            source_module="test",
            action="create",
            after_value={"i": i},
        )
    checkpoint = create_checkpoint(session, tenant)
    assert checkpoint is not None
    assert last is not None
    assert checkpoint.sequence_no == 4
    assert checkpoint.last_event_hash == last.event_hash


def test_chains_are_isolated_per_tenant(session: Session) -> None:
    tenant_a, tenant_b = _tenant(), _tenant()
    record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant_a,
        actor_type="user",
        actor_id="u",
        source_module="test",
        action="create",
    )
    b_event = record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant_b,
        actor_type="user",
        actor_id="u",
        source_module="test",
        action="create",
    )
    # Each tenant's chain starts at sequence 1 from genesis.
    assert b_event.sequence_no == 1
    assert b_event.previous_event_hash == GENESIS_HASH
    assert session.query(AuditEvent).count() == 2
