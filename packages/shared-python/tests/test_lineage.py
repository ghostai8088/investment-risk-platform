"""SQLite-local unit/behavior tests for the data-source & lineage skeleton (P1A-1).

RLS is a no-op on SQLite, so isolation/fail-closed proofs live in ``test_lineage_pg.py``; here we
prove model/temporal/utility behavior, audit emission, the BX-LIN enforcement contract, and the
append-only guard.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import (
    SOURCE_REGISTER_EVENT,
    SOURCE_UPDATE_EVENT,
    DataSourceNotVisible,
    LineageMissingError,
    assert_has_lineage,
    record_lineage,
    register_data_source,
    update_data_source,
)
from irp_shared.temporal import TemporalClass


def _tenant() -> str:
    return str(uuid.uuid4())


def _audit_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()


def _source(session: Session, tenant: str, code: str = "SRC") -> DataSource:
    return register_data_source(
        session,
        tenant_id=tenant,
        code=code,
        name="Source",
        source_type="INTERNAL",
        actor_id="admin",
    )


def test_temporal_classes() -> None:
    assert DataSource.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
    assert hasattr(DataSource, "valid_from") and hasattr(DataSource, "valid_to")
    assert LineageEdge.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    assert hasattr(LineageEdge, "system_from")
    assert not hasattr(LineageEdge, "valid_to")  # IA has no second (valid) axis (TR-21)


def test_record_lineage_creates_retrievable_edge(session: Session) -> None:
    tenant = _tenant()
    src = _source(session, tenant)
    target = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    edge = record_lineage(
        session,
        source=src,
        target_entity_type="synthetic.governed_output",
        target_entity_id=target,
        run_id=run_id,
    )

    assert edge.tenant_id == tenant  # stamped server-side from the resolved source
    assert edge.source_type == "data_source"
    assert edge.source_id == src.id
    assert edge.run_id == run_id  # run_id passes through
    fetched = session.get(LineageEdge, edge.id)
    assert fetched is not None
    assert fetched.target_entity_type == "synthetic.governed_output"
    assert fetched.target_entity_id == target


def test_lineage_edge_is_append_only(session: Session) -> None:
    tenant = _tenant()
    src = _source(session, tenant)
    edge = record_lineage(
        session, source=src, target_entity_type="synthetic.t", target_entity_id=str(uuid.uuid4())
    )
    session.commit()
    edge_id = edge.id

    fetched = session.get(LineageEdge, edge_id)
    fetched.edge_kind = "DERIVED_FROM"
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()

    fetched = session.get(LineageEdge, edge_id)
    session.delete(fetched)
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_register_and_update_emit_audit_and_chain_verifies(session: Session) -> None:
    tenant = _tenant()
    src = register_data_source(
        session,
        tenant_id=tenant,
        code="BLOOMBERG_PX",
        name="Bloomberg Prices",
        source_type="VENDOR_FEED",
        actor_id="admin",
    )
    events = (
        session.execute(select(AuditEvent).where(AuditEvent.entity_id == src.id)).scalars().all()
    )
    assert len(events) == 1
    assert events[0].event_type == SOURCE_REGISTER_EVENT
    assert events[0].entity_type == "data_source"

    update_data_source(
        session, src, actor_id="admin", name="Bloomberg Prices (EU)", is_active=False
    )
    assert src.record_version == 2
    upd = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == src.id, AuditEvent.event_type == SOURCE_UPDATE_EVENT
            )
        )
        .scalars()
        .all()
    )
    assert len(upd) == 1
    assert upd[0].before_value["name"] == "Bloomberg Prices"
    assert upd[0].after_value["name"] == "Bloomberg Prices (EU)"

    assert verify_chain(session, tenant).ok is True


def test_update_rejects_unknown_attribute(session: Session) -> None:
    src = _source(session, _tenant())
    with pytest.raises(ValueError, match="non-updatable"):
        update_data_source(session, src, actor_id="admin", tenant_id="other")


def test_unique_code_per_tenant_and_hooks_default_null(session: Session) -> None:
    tenant = _tenant()
    src = _source(session, tenant, code="DUP")
    assert src.approval_status is None and src.approval_ref is None
    assert src.made_by is None and src.checked_by is None
    # Same code in another tenant is allowed.
    register_data_source(
        session, tenant_id=_tenant(), code="DUP", name="n", source_type="INTERNAL", actor_id="a"
    )
    session.flush()
    # Duplicate within the same tenant is rejected (uq_data_source_tenant_code).
    session.add(DataSource(tenant_id=tenant, code="DUP", name="n2", source_type="INTERNAL"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_bx_lin_enforcement_contract(session: Session) -> None:
    tenant = _tenant()
    src = _source(session, tenant)
    target = str(uuid.uuid4())

    # A governed write that does NOT record lineage fails the no-bypass check (CTRL-013).
    with pytest.raises(LineageMissingError):
        assert_has_lineage(session, "synthetic.governed_output", target)

    # Recording lineage makes the same check pass and returns the source->target path (CTRL-006).
    record_lineage(
        session,
        source=src,
        target_entity_type="synthetic.governed_output",
        target_entity_id=target,
    )
    edge = assert_has_lineage(session, "synthetic.governed_output", target)
    assert edge.source_id == src.id


def test_assert_has_lineage_is_tenant_scoped(session: Session) -> None:
    tenant_a = _tenant()
    src = _source(session, tenant_a)
    target = str(uuid.uuid4())
    record_lineage(session, source=src, target_entity_type="synthetic.t", target_entity_id=target)
    # The edge belongs to tenant_a; scoping the check to a different tenant must not satisfy it.
    with pytest.raises(LineageMissingError):
        assert_has_lineage(session, "synthetic.t", target, tenant_id=_tenant())
    assert assert_has_lineage(session, "synthetic.t", target, tenant_id=tenant_a) is not None


def test_record_lineage_emits_no_audit_event(session: Session) -> None:
    tenant = _tenant()
    src = _source(session, tenant)  # this emits one (register) event
    before = _audit_count(session)
    record_lineage(
        session, source=src, target_entity_type="synthetic.t", target_entity_id=str(uuid.uuid4())
    )
    assert _audit_count(session) == before  # the edge is metadata of a governed write, not an event


def test_record_lineage_unknown_source_fails_closed(session: Session) -> None:
    # A source id not visible/resolvable under the session is rejected (cross-tenant RLS hides it
    # on PostgreSQL; here we use an unpersisted id to exercise the same fail-closed path).
    phantom = DataSource(tenant_id=_tenant(), code="X", name="X", source_type="INTERNAL")
    phantom.id = str(uuid.uuid4())
    with pytest.raises(DataSourceNotVisible):
        record_lineage(
            session,
            source=phantom,
            target_entity_type="synthetic.t",
            target_entity_id=str(uuid.uuid4()),
        )


def _raise_audit(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("audit capture failed")


def test_register_data_source_rolls_back_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-7 / CTRL-032 / AUD-04: the data_source row and its audit event are one transaction — if
    # the audit insert fails, the row must NOT persist (fail-closed atomicity).
    import irp_shared.lineage.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    tenant = _tenant()
    with pytest.raises(RuntimeError):
        register_data_source(
            session, tenant_id=tenant, code="X", name="n", source_type="INTERNAL", actor_id="a"
        )
    session.rollback()
    remaining = session.execute(
        select(func.count()).select_from(DataSource).where(DataSource.tenant_id == tenant)
    ).scalar_one()
    assert remaining == 0


def test_update_data_source_rolls_back_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = _tenant()
    src = _source(session, tenant)  # real audit on create
    session.commit()
    src_id = src.id

    import irp_shared.lineage.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        update_data_source(session, src, actor_id="a", name="Changed")
    session.rollback()
    refreshed = session.get(DataSource, src_id)
    assert refreshed.name == "Source"  # update did not persist
    assert refreshed.record_version == 1  # version not advanced
