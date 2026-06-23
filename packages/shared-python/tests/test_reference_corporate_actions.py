"""SQLite-local unit/behavior tests for P1B-4 corporate_action (REQ-SMR-004, EV; capture-only).

RLS is a no-op on SQLite, so isolation proofs live in the PG file; here we prove the governed-write
contract (own-event audit + MANUAL lineage), the EV amend + status-lifecycle protocol (incl. the
guard matrix and the EVT-143 positive + negative-fence behaviour), the tenant-filtered cross-tenant
fail-closed, the fail-closed audit rollback, and the capture-only scope fences.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.reference.corporate_action import (
    CorporateActionNotVisible,
    IllegalStatusTransition,
    create_corporate_action,
    resolve_corporate_action,
    transition_corporate_action_status,
    update_corporate_action,
)
from irp_shared.reference.instrument import (
    InstrumentNotVisible,
    create_instrument,
    update_instrument,
)
from irp_shared.reference.models import CorporateAction, Instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass


def _t() -> str:
    return str(uuid.uuid4())


def _actor() -> ReferenceActor:
    return ReferenceActor(actor_id="steward")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _instr(session: Session, tenant: str, code: str = "BOND1") -> Instrument:
    return create_instrument(
        session, tenant_id=tenant, code=code, name=code, asset_class="BOND", actor=_actor()
    )


def _ca(
    session: Session, tenant: str, instr: Instrument, code: str = "CA1", **kw
) -> CorporateAction:  # noqa: ANN003
    return create_corporate_action(
        session,
        tenant_id=tenant,
        code=code,
        instrument_id=instr.id,
        action_type=kw.pop("action_type", "DIVIDEND"),
        actor=_actor(),
        **kw,
    )


# --- temporal class + lifecycle flag ---


def test_corporate_action_is_ev_no_status_dual_flag() -> None:
    assert CorporateAction.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
    assert hasattr(CorporateAction, "valid_from")
    assert not hasattr(CorporateAction, "system_from")  # EV, not FR
    cols = {c.name for c in CorporateAction.__table__.columns}
    assert "status" in cols and "is_active" not in cols  # single lifecycle flag (review arch-1)


# --- create ---


def test_create_records_lineage_and_audit(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    ca = _ca(
        session,
        tenant,
        inst,
        ex_date=date(2026, 3, 1),
        effective_date=date(2026, 3, 15),
        amount=Decimal("0.5"),
        currency_code="USD",
    )
    assert ca.status == "ANNOUNCED" and ca.record_version == 1 and ca.ex_date == date(2026, 3, 1)
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == ca.id)
    ).scalar_one()
    assert edge.target_entity_type == "corporate_action" and edge.edge_kind == "ORIGIN"
    src = session.get(DataSource, edge.source_id)
    assert src is not None and src.source_type == "MANUAL"
    assert_has_lineage(session, "corporate_action", ca.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == ca.id)).scalar_one()
    assert ev.event_type == "REFERENCE.CREATE" and ev.entity_type == "corporate_action"
    assert verify_chain(session, tenant).ok is True


def test_create_unique_code(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    _ca(session, tenant, inst, "DUP")
    with pytest.raises(IntegrityError):
        _ca(session, tenant, inst, "DUP")


def test_create_validates_initial_status(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    with pytest.raises(IllegalStatusTransition):  # out-of-vocab initial status rejected (SEC-5)
        _ca(session, tenant, inst, "CAX", status="BOGUS")
    # a valid non-default initial status is allowed (e.g. importing an already-CONFIRMED action)
    ca = _ca(session, tenant, inst, "CAOK", status="CONFIRMED")
    assert ca.status == "CONFIRMED"


# --- amend (EV in-place; REFERENCE.UPDATE) ---


def test_amend_in_place_single_row(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    ca = _ca(session, tenant, inst, pay_date=date(2026, 3, 15))
    update_corporate_action(
        session, ca, actor=_actor(), pay_date=date(2026, 3, 20), amount=Decimal("1.1")
    )
    assert ca.pay_date == date(2026, 3, 20) and ca.amount == Decimal("1.1")
    assert ca.record_version == 2 and ca.status == "ANNOUNCED"  # amend does not touch status
    assert _events(session, "REFERENCE.UPDATE") >= 1
    # EV: one physical row for this logical action.
    assert (
        session.execute(
            select(func.count()).select_from(CorporateAction).where(CorporateAction.code == "CA1")
        ).scalar_one()
        == 1
    )
    # An EV amend AND a status transition add NO new lineage edge — the row keeps its 1 origin edge.
    transition_corporate_action_status(session, ca, new_status="CONFIRMED", actor=_actor())
    assert (
        session.execute(
            select(func.count())
            .select_from(LineageEdge)
            .where(LineageEdge.target_entity_id == ca.id)
        ).scalar_one()
        == 1
    )


def test_amend_rejects_status_attr(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    ca = _ca(session, tenant, inst)
    with pytest.raises(ValueError):  # status is changed only via the transition helper
        update_corporate_action(session, ca, actor=_actor(), status="CONFIRMED")


# --- status lifecycle (guard matrix + EVT-143) ---


def test_status_transition_matrix(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    # legal ANNOUNCED -> CONFIRMED -> CANCELLED
    ca = _ca(session, tenant, inst, "CA_L")
    transition_corporate_action_status(session, ca, new_status="CONFIRMED", actor=_actor())
    assert ca.status == "CONFIRMED" and ca.record_version == 2
    transition_corporate_action_status(session, ca, new_status="CANCELLED", actor=_actor())
    assert ca.status == "CANCELLED" and ca.record_version == 3
    # illegal: out of CANCELLED (terminal) — and the rejected move makes NO DB write (review QA-1).
    for bad in ("CONFIRMED", "ANNOUNCED"):
        with pytest.raises(IllegalStatusTransition):
            transition_corporate_action_status(session, ca, new_status=bad, actor=_actor())
    assert ca.status == "CANCELLED" and ca.record_version == 3  # unchanged after the rejects
    # ANNOUNCED -> CANCELLED is legal (direct cancel-before-confirm)
    ca2 = _ca(session, tenant, inst, "CA_D")
    transition_corporate_action_status(session, ca2, new_status="CANCELLED", actor=_actor())
    assert ca2.status == "CANCELLED"
    # CONFIRMED -> ANNOUNCED illegal — and the row is untouched after rejection.
    ca3 = _ca(session, tenant, inst, "CA_R")
    transition_corporate_action_status(session, ca3, new_status="CONFIRMED", actor=_actor())
    with pytest.raises(IllegalStatusTransition):
        transition_corporate_action_status(session, ca3, new_status="ANNOUNCED", actor=_actor())
    assert ca3.status == "CONFIRMED" and ca3.record_version == 2  # no mutation on reject
    # out-of-vocab target AND a no-op self-transition are both rejected, no DB write (review QA-3).
    ca4 = _ca(session, tenant, inst, "CA_V")
    for bad in ("BOGUS", "ANNOUNCED"):  # out-of-vocab + no-op self-move
        with pytest.raises(IllegalStatusTransition):
            transition_corporate_action_status(session, ca4, new_status=bad, actor=_actor())
    assert ca4.status == "ANNOUNCED" and ca4.record_version == 1


def test_status_change_audit_positive_evt143(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    ca = _ca(session, tenant, inst)
    transition_corporate_action_status(
        session, ca, new_status="CONFIRMED", actor=_actor(), reason="confirmed by issuer"
    )
    assert _events(session, "REFERENCE.STATUS_CHANGE") == 1
    ev = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "REFERENCE.STATUS_CHANGE")
    ).scalar_one()
    assert ev.before_value == {"status": "ANNOUNCED"} and ev.after_value == {"status": "CONFIRMED"}
    assert ev.justification == "confirmed by issuer" and ev.entity_id == ca.id
    assert verify_chain(session, tenant).ok is True


def test_status_change_evt143_fence_only_corporate_action(session: Session) -> None:
    # EVT-143 is emitted ONLY for corporate_action — an instrument is_active flip (REFERENCE.UPDATE)
    # in the SAME session emits ZERO REFERENCE.STATUS_CHANGE.
    tenant = _t()
    inst = _instr(session, tenant)
    update_instrument(session, inst, actor=_actor(), is_active=False)
    assert _events(session, "REFERENCE.STATUS_CHANGE") == 0
    ca = _ca(session, tenant, inst)
    transition_corporate_action_status(session, ca, new_status="CONFIRMED", actor=_actor())
    assert _events(session, "REFERENCE.STATUS_CHANGE") == 1  # only the corporate_action transition


# --- cross-tenant + fail-closed ---


def test_cross_tenant_instrument_fails_closed(session: Session) -> None:
    a, b = _t(), _t()
    inst_b = _instr(session, b, "B_BOND")
    with pytest.raises(InstrumentNotVisible):  # service-layer, NOT IntegrityError
        create_corporate_action(
            session,
            tenant_id=a,
            code="CAx",
            instrument_id=inst_b.id,
            action_type="SPLIT",
            actor=_actor(),
        )
    session.rollback()
    assert session.execute(select(func.count()).select_from(CorporateAction)).scalar_one() == 0


def test_fail_closed_no_audit_no_lineage(session: Session) -> None:
    tenant = _t()
    ghost = str(uuid.uuid4())
    with pytest.raises(InstrumentNotVisible):
        create_corporate_action(
            session,
            tenant_id=tenant,
            code="CA",
            instrument_id=ghost,
            action_type="SPLIT",
            actor=_actor(),
        )
    session.rollback()
    assert session.execute(select(func.count()).select_from(CorporateAction)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(DataSource)).scalar_one() == 0


def test_resolve_corporate_action_cross_tenant(session: Session) -> None:
    a, b = _t(), _t()
    inst_a = _instr(session, a)
    ca = _ca(session, a, inst_a)
    with pytest.raises(CorporateActionNotVisible):  # tenant B cannot resolve tenant A's row
        resolve_corporate_action(session, ca.id, acting_tenant=b)


# --- capture-only scope fences ---


def test_no_application_or_position_columns() -> None:
    forbidden = {
        "applied",
        "is_applied",
        "position_id",
        "quantity",
        "valuation",
        "entitlement",
        "tax",
        "cash_amount",
        "is_active",
    }
    cols = {c.name for c in CorporateAction.__table__.columns}
    assert not (forbidden & cols), forbidden & cols


def test_action_type_and_status_extend_by_value(session: Session) -> None:
    # controlled-vocab plain strings (no enum/CHECK) — a new action_type is data, not a migration.
    tenant = _t()
    inst = _instr(session, tenant)
    ca = _ca(session, tenant, inst, "CA_NEW", action_type="A_BRAND_NEW_TYPE")
    assert ca.action_type == "A_BRAND_NEW_TYPE"
