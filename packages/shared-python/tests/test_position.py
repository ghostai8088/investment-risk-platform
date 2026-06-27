"""SQLite-local unit/behavior tests for P1C-3 position (REQ-PPM-002, FR bitemporal).

RLS is a no-op on SQLite, so symmetric-isolation lives in the PG file; here we prove the FR contract
(FullReproducibleMixin; create / effective-dated supersede / as-known correction / reconstruct on
both
axes), the captured-not-derived stance (no transaction FK / no derivation), content-immutability of
prior versions (service-enforced), the NOT-append-only property (a close-out UPDATE succeeds — the
FR
contrast with the IA transaction guard), the governed-write rails (POSITION.* + MANUAL ORIGIN
lineage
per new physical version), the cross-tenant fail-closed, audit event counts/payloads, fail-closed
rollback, import-direction, and the scope fence.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.db.mixins import utcnow
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.portfolio import PortfolioActor, PortfolioNotVisible, create_portfolio
from irp_shared.position import (
    NoCurrentPosition,
    Position,
    PositionActor,
    PositionNotVisible,
    correct_position,
    create_position,
    reconstruct_position_as_of,
    resolve_position,
    supersede_position,
)
from irp_shared.reference.instrument import InstrumentNotVisible, create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass

T0 = datetime(2026, 1, 1, tzinfo=UTC)  # initial as-of (valid) date
T1 = datetime(2026, 6, 1, tzinfo=UTC)  # supersede effective date


def _tenant() -> str:
    return str(uuid.uuid4())


def _actor() -> PositionActor:
    return PositionActor(actor_id="steward")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _seed_pf_inst(session: Session, tenant: str, suffix: str = "") -> tuple[str, str]:
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"PF{suffix}",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    inst = create_instrument(
        session,
        tenant_id=tenant,
        code=f"INST{suffix}",
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="steward"),
    )
    return pf.id, inst.id


def _create(session: Session, tenant: str, pf_id: str, inst_id: str, **kw) -> Position:  # noqa: ANN003
    base: dict = dict(quantity=Decimal("100"), valid_from=T0)
    base.update(kw)
    return create_position(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        acting_tenant=tenant,
        actor=_actor(),
        **base,
    )


# --- temporal class: FR bitemporal; NOT append-only ---


def test_position_is_fr_bitemporal() -> None:
    assert Position.__temporal_class__ == TemporalClass.FULL_REPRODUCIBLE
    for attr in ("valid_from", "valid_to", "system_from", "system_to"):
        assert hasattr(Position, attr), f"FR must have {attr}"
    # FR carries record_version + supersedes_id (NOT an IA event log; NOT in APPEND_ONLY_TABLES).
    assert hasattr(Position, "record_version") and hasattr(Position, "supersedes_id")


def test_position_holds_nothing_scope_fence() -> None:
    cols = set(Position.__table__.columns.keys())
    forbidden = {
        "market_value",
        "price",
        "mark",
        "valuation",
        "nav",
        "exposure",
        "pnl",
        "unrealized",
        "fx_rate",
        "transaction_id",
        "lot_id",
    }
    assert not (forbidden & cols), f"position leaks domain/calc columns: {forbidden & cols}"


def test_record_creates_no_derived_or_excluded_table() -> None:
    names = set(Position.metadata.tables.keys())
    assert "position" in names
    # P2-1 `dataset_snapshot`, P2-2 `fx_rate`, P2-3 `exposure_aggregate` exist; later-slice (P2-4+)
    # tables must still NOT exist.
    for forbidden in (
        "price_point",
        "holding",
    ):
        assert forbidden not in names, f"excluded table {forbidden} must not exist"


# --- governed-write contract: lineage + audit ---


def test_create_lineage_and_audit(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id)
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == row.id)
    ).scalar_one()
    assert edge.target_entity_type == "position" and edge.edge_kind == "ORIGIN"
    src = session.get(DataSource, edge.source_id)
    assert src is not None and src.source_type == "MANUAL"
    assert_has_lineage(session, "position", row.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == row.id)).scalar_one()
    assert ev.event_type == "POSITION.CREATE" and ev.entity_type == "position"
    assert ev.action == "create"
    assert verify_chain(session, tenant).ok is True


def test_create_emits_exactly_one_event(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id)
    assert _events(session, "POSITION.CREATE") == 1
    assert _events(session, "POSITION.UPDATE") == 0
    assert _events(session, "POSITION.CORRECTION") == 0


# --- signed quantity ---


def test_signed_quantity_short_is_negative(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id, quantity=Decimal("-250"))
    session.commit()
    refreshed = session.get(Position, row.id)
    assert refreshed is not None and refreshed.quantity == Decimal("-250")


# --- effective-dated supersede (valid-time) ---


def test_supersede_close_first_two_rows(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    orig_id = original.id
    session.commit()

    new = supersede_position(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        quantity=Decimal("175"),
    )
    session.commit()

    # exactly two rows; the new is the open head; the prior is closed at T1.
    assert session.execute(select(func.count()).select_from(Position)).scalar_one() == 2
    assert new.id != orig_id and new.supersedes_id == orig_id
    assert new.quantity == Decimal("175") and new.record_version == 2
    assert new.valid_to is None and new.system_to is None
    prior = session.get(Position, orig_id)
    assert prior is not None and prior.valid_to is not None  # closed in valid-time
    assert prior.quantity == Decimal("100")  # prior CONTENT unchanged (only valid_to moved)
    # supersede emits exactly: POSITION.UPDATE (close-out) + POSITION.CREATE (new row).
    assert _events(session, "POSITION.UPDATE") == 1
    assert _events(session, "POSITION.CREATE") == 2  # original create + the new open row
    # per-NEW-physical-version lineage: the new open row roots exactly ONE ORIGIN edge; the prior
    # close-out roots NONE (so the pair has exactly two ORIGIN edges total).
    new_edges = session.execute(
        select(func.count()).select_from(LineageEdge).where(LineageEdge.target_entity_id == new.id)
    ).scalar_one()
    prior_edges = session.execute(
        select(func.count()).select_from(LineageEdge).where(LineageEdge.target_entity_id == orig_id)
    ).scalar_one()
    assert new_edges == 1 and prior_edges == 1


def test_supersede_without_current_head_raises(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    session.commit()
    with pytest.raises(NoCurrentPosition):
        supersede_position(
            session,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            acting_tenant=tenant,
            actor=_actor(),
            effective_at=T1,
            quantity=Decimal("10"),
        )


# --- as-known correction (system-time) ---


def test_correct_restatement(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    session.commit()

    corrected = correct_position(
        session,
        original,
        restatement_reason="custodian restatement",
        acting_tenant=tenant,
        actor=_actor(),
        quantity=Decimal("120"),
    )
    session.commit()

    assert corrected.id != original.id and corrected.supersedes_id == original.id
    assert corrected.quantity == Decimal("120")
    assert corrected.restatement_reason == "custodian restatement"
    # corrected covers the SAME valid period; it is the open system-time head.
    assert corrected.valid_from.replace(tzinfo=None) == original.valid_from.replace(tzinfo=None)
    assert corrected.system_to is None
    assert _events(session, "POSITION.CORRECTION") == 1
    assert _events(session, "POSITION.UPDATE") == 1  # the prior system_to close-out


def test_content_immutability_on_correction(session: Session) -> None:
    # The prior row's CONTENT is byte-for-byte unchanged after a correction — only system_to moves.
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    orig_id = original.id
    orig_qty = original.quantity
    session.commit()

    correct_position(
        session,
        original,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=_actor(),
        quantity=Decimal("999"),
    )
    session.commit()

    session.expire_all()
    prior = session.get(Position, orig_id)
    assert prior is not None
    assert prior.quantity == orig_qty  # CONTENT unchanged (not the corrected 999)
    assert prior.restatement_reason is None  # the correction's reason is on the NEW row only
    assert prior.system_to is not None  # only the close-out column moved


def test_correction_audit_payload_two_part(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    orig_id = original.id
    session.commit()

    corrected = correct_position(
        session,
        original,
        restatement_reason="why",
        acting_tenant=tenant,
        actor=_actor(),
        quantity=Decimal("110"),
    )
    session.commit()

    # the prior-row close-out is a POSITION.UPDATE carrying the system_to boundary diff.
    upd = session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == orig_id, AuditEvent.event_type == "POSITION.UPDATE"
        )
    ).scalar_one()
    assert upd.before_value == {"system_to": None}
    assert upd.after_value is not None and "system_to" in upd.after_value
    # the corrected row's CORRECTION carries restatement_reason on justification + after_value.
    cor = session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == corrected.id, AuditEvent.event_type == "POSITION.CORRECTION"
        )
    ).scalar_one()
    assert cor.justification == "why"
    assert cor.after_value["restatement_reason"] == "why"
    assert cor.after_value["supersedes_id"] == orig_id


def test_correction_roots_own_origin_edge(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id)
    session.commit()
    corrected = correct_position(
        session, original, restatement_reason="r", acting_tenant=tenant, actor=_actor()
    )
    session.commit()
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == corrected.id)
    ).scalar_one()
    assert edge.target_entity_type == "position" and edge.edge_kind == "ORIGIN"
    assert_has_lineage(session, "position", corrected.id, tenant_id=tenant)


# --- bitemporal reconstruction (both axes) ---


def test_reconstruct_valid_time_as_of(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    supersede_position(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        quantity=Decimal("175"),
    )
    session.commit()

    # before T1 → the original 100; on/after T1 → the superseding 175.
    early = reconstruct_position_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valid_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    late = reconstruct_position_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valid_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert early is not None and early.quantity == Decimal("100")
    assert late is not None and late.quantity == Decimal("175")


def test_reconstruct_known_at_and_current_view(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    session.commit()

    t_known = utcnow()  # a knowledge instant BEFORE the correction
    correct_position(
        session,
        original,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=_actor(),
        quantity=Decimal("140"),
    )
    session.commit()

    # as-known-at t_known → the pre-correction 100; current view (known_at=None) → corrected 140.
    as_known = reconstruct_position_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valid_at=T0,
        known_at=t_known,
    )
    current = reconstruct_position_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valid_at=T0,
    )
    assert as_known is not None and as_known.quantity == Decimal("100")
    assert current is not None and current.quantity == Decimal("140")


# --- current-head partial-unique ---


def test_current_head_partial_unique(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id, quantity=Decimal("100"))
    session.flush()
    # a SECOND dual-open row for the same (tenant, portfolio, instrument) violates
    # uq_position_current.
    session.add(
        Position(
            tenant_id=tenant,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            valid_from=T0,
            valid_to=None,
            system_from=utcnow(),
            system_to=None,
            quantity=Decimal("5"),
            record_version=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# --- NOT append-only (the FR contrast with the IA transaction) ---


def test_position_is_not_append_only_close_out_update_succeeds(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id)
    session.commit()
    # FR: a close-out UPDATE is PERMITTED (no ORM guard, no P0001 trigger) — unlike the IA
    # transaction.
    row.system_to = utcnow()
    session.flush()  # must NOT raise AppendOnlyViolation
    session.commit()
    assert session.get(Position, row.id).system_to is not None


# --- cross-tenant references fail closed at the service layer ---


def test_cross_tenant_portfolio_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    b_pf, _b_inst = _seed_pf_inst(session, b, "_B")
    _a_pf, a_inst = _seed_pf_inst(session, a, "_A")
    session.commit()
    with pytest.raises(PortfolioNotVisible):
        _create(session, a, b_pf, a_inst)


def test_cross_tenant_instrument_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    _b_pf, b_inst = _seed_pf_inst(session, b, "_B")
    a_pf, _a_inst = _seed_pf_inst(session, a, "_A")
    session.commit()
    with pytest.raises(InstrumentNotVisible):
        _create(session, a, a_pf, b_inst)


def test_resolve_cross_tenant_position_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    b_pf, b_inst = _seed_pf_inst(session, b, "_B")
    b_row = _create(session, b, b_pf, b_inst)
    session.commit()
    with pytest.raises(PositionNotVisible):
        resolve_position(session, b_row.id, acting_tenant=a)


# --- CTRL-012: no silent write (every governed path emits an event) ---


def test_every_governed_write_emits_event(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id)
    supersede_position(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        quantity=Decimal("2"),
    )
    head = resolve_position(
        session, _current_open_id(session, tenant, pf_id, inst_id), acting_tenant=tenant
    )
    correct_position(session, head, restatement_reason="r", acting_tenant=tenant, actor=_actor())
    session.commit()
    total = (
        _events(session, "POSITION.CREATE")
        + _events(session, "POSITION.UPDATE")
        + _events(session, "POSITION.CORRECTION")
    )
    # create(1) + supersede(UPDATE+CREATE=2) + correct(UPDATE+CORRECTION=2) = 5 events.
    assert total == 5
    assert verify_chain(session, tenant).ok is True
    _ = row


def _current_open_id(session: Session, tenant: str, pf_id: str, inst_id: str) -> str:
    return session.execute(
        select(Position.id).where(
            Position.tenant_id == tenant,
            Position.portfolio_id == pf_id,
            Position.instrument_id == inst_id,
            Position.valid_to.is_(None),
            Position.system_to.is_(None),
        )
    ).scalar_one()


# --- fail-closed audit rollback ---


def test_fail_closed_audit_rollback(session: Session, monkeypatch) -> None:  # noqa: ANN001
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    session.commit()
    import irp_shared.position.service as svc

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("audit down")

    monkeypatch.setattr(svc, "record_event", _boom)
    with pytest.raises(RuntimeError):
        _create(session, tenant, pf_id, inst_id)
    session.rollback()
    assert session.execute(select(func.count()).select_from(Position)).scalar_one() == 0


# --- import direction: position -> {portfolio, reference, rails} only ---


def test_import_direction() -> None:
    pkg = pathlib.Path(create_position.__module__.replace(".", "/")).parent
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    allowed = {"lineage", "audit", "db", "temporal", "portfolio", "reference", "position"}
    forbidden_roots = {"irp_backend", "irp_shared.models"}
    for py in (root / pkg).glob("*.py"):
        for line in py.read_text().splitlines():
            line = line.strip()
            if not (line.startswith("from ") or line.startswith("import ")):
                continue
            for bad in forbidden_roots:
                assert bad not in line, f"{py.name} imports forbidden {bad}: {line}"
            if "irp_shared." in line:
                seg = line.split("irp_shared.")[1].split()[0].split(".")[0].rstrip(",")
                assert seg in allowed, f"{py.name} imports irp_shared.{seg}: {line}"
