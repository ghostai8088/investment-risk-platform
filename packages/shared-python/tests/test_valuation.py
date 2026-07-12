"""SQLite-local unit/behavior tests for P1C-4 valuation (REQ-PPM-003 valuation conjunct, FR).

RLS is a no-op on SQLite, so symmetric-isolation lives in the PG file; here we prove the FR contract
(FullReproducibleMixin; create / effective-dated supersede / as-known correction / reconstruct on
both
axes), the captured-marks-not-modeled stance (no position link / no market value / no model), the
valuation_date LOGICAL-KEY behaviour (separate valuation_dates coexist; carried forward; the 4-part
current-head key), content-immutability of prior versions, the NOT-append-only property, the
governed-write rails (VALUATION.* + MANUAL ORIGIN lineage per physical version), the cross-tenant
fail-closed, audit event counts/payloads, fail-closed rollback, import-direction, and the scope
fence.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, date, datetime
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
from irp_shared.reference.instrument import InstrumentNotVisible, create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass
from irp_shared.valuation import (
    NoCurrentValuation,
    Valuation,
    ValuationActor,
    ValuationNotVisible,
    ValuationValueError,
    correct_valuation,
    create_valuation,
    reconstruct_valuation_as_of,
    resolve_valuation,
    supersede_valuation,
)

VD = date(2026, 3, 31)  # the immutable valuation_date (logical-key component)
VD2 = date(2026, 6, 30)  # a second valuation_date for the same (portfolio, instrument)
T0 = datetime(2026, 4, 1, tzinfo=UTC)  # initial valid_from
T1 = datetime(2026, 4, 15, tzinfo=UTC)  # supersede (re-mark) effective date


def _tenant() -> str:
    return str(uuid.uuid4())


def _actor() -> ValuationActor:
    return ValuationActor(actor_id="steward")


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


def _create(session: Session, tenant: str, pf_id: str, inst_id: str, **kw) -> Valuation:  # noqa: ANN003
    base: dict = dict(valuation_date=VD, mark_value=Decimal("100"), valid_from=T0)
    base.update(kw)
    return create_valuation(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        acting_tenant=tenant,
        actor=_actor(),
        **base,
    )


# --- temporal class: FR bitemporal; NOT append-only ---


def test_valuation_is_fr_bitemporal() -> None:
    assert Valuation.__temporal_class__ == TemporalClass.FULL_REPRODUCIBLE
    for attr in ("valid_from", "valid_to", "system_from", "system_to", "valuation_date"):
        assert hasattr(Valuation, attr), f"FR/valuation must have {attr}"
    assert hasattr(Valuation, "record_version") and hasattr(Valuation, "supersedes_id")


def test_valuation_holds_nothing_scope_fence() -> None:
    cols = set(Valuation.__table__.columns.keys())
    forbidden = {
        "position_id",
        "quantity",
        "market_value",
        "exposure",
        "nav",
        "pnl",
        "unrealized",
        "holding",
    }
    assert not (
        forbidden & cols
    ), f"valuation leaks position/market-value columns: {forbidden & cols}"


def test_no_derived_or_excluded_table() -> None:
    names = set(Valuation.metadata.tables.keys())
    assert "valuation" in names
    # P2-1..4 build dataset_snapshot/fx_rate/exposure_aggregate/price_point; still-future (P2-5+)
    # tables must NOT exist.
    for forbidden in ("holding",):
        assert forbidden not in names, f"excluded table {forbidden} must not exist"


# --- governed-write contract: lineage + audit ---


def test_create_lineage_and_audit(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id)
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == row.id)
    ).scalar_one()
    assert edge.target_entity_type == "valuation" and edge.edge_kind == "ORIGIN"
    src = session.get(DataSource, edge.source_id)
    assert src is not None and src.source_type == "MANUAL"
    assert_has_lineage(session, "valuation", row.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == row.id)).scalar_one()
    assert ev.event_type == "VALUATION.CREATE" and ev.entity_type == "valuation"
    assert ev.action == "create"
    assert verify_chain(session, tenant).ok is True


def test_create_emits_exactly_one_event(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id)
    assert _events(session, "VALUATION.CREATE") == 1
    assert _events(session, "VALUATION.UPDATE") == 0
    assert _events(session, "VALUATION.CORRECTION") == 0


def test_mark_value_captured_roundtrip(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id, mark_value=Decimal("123.456789"))
    session.commit()
    refreshed = session.get(Valuation, row.id)
    assert refreshed is not None and refreshed.mark_value == Decimal("123.456789")
    assert refreshed.valuation_date == VD


# --- effective-dated supersede (re-mark; valid-time) ---


def test_supersede_close_first_two_rows(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, mark_value=Decimal("100"))
    orig_id = original.id
    session.commit()

    new = supersede_valuation(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        mark_value=Decimal("105"),
    )
    session.commit()

    assert session.execute(select(func.count()).select_from(Valuation)).scalar_one() == 2
    assert new.id != orig_id
    assert new.supersedes_id == orig_id and new.record_version == 2  # QA-3 fold
    assert new.mark_value == Decimal("105")
    assert new.valuation_date == VD  # carried verbatim
    assert new.valid_to is None and new.system_to is None
    prior = session.get(Valuation, orig_id)
    assert prior is not None and prior.valid_to is not None
    assert prior.mark_value == Decimal("100")  # prior CONTENT unchanged (only valid_to moved)
    assert _events(session, "VALUATION.UPDATE") == 1
    assert _events(session, "VALUATION.CREATE") == 2  # original + new open row
    # per-NEW-physical-version lineage: new row roots exactly one ORIGIN edge; prior roots one.
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
    with pytest.raises(NoCurrentValuation):
        supersede_valuation(
            session,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            valuation_date=VD,
            acting_tenant=tenant,
            actor=_actor(),
            effective_at=T1,
            mark_value=Decimal("1"),
        )


def test_supersede_backdated_effective_at_refused(session: Session) -> None:
    # MD-H1 window-coherence (Option-A extension): effective_at at/before the head's valid_from
    # (T0) would invert or zero-width the closed window — refused pre-write (→ 422).
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id)  # valid_from=T0
    session.commit()
    with pytest.raises(ValuationValueError):
        supersede_valuation(
            session,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            valuation_date=VD,
            acting_tenant=tenant,
            actor=_actor(),
            effective_at=T0,  # == valid_from → zero-width, refused (strictly-greater)
            mark_value=Decimal("105"),
        )


# --- as-known correction (system-time) ---


def test_correct_restatement(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, mark_value=Decimal("100"))
    session.commit()

    corrected = correct_valuation(
        session,
        original,
        restatement_reason="custodian restatement",
        acting_tenant=tenant,
        actor=_actor(),
        mark_value=Decimal("120"),
    )
    session.commit()

    assert corrected.id != original.id and corrected.supersedes_id == original.id
    assert corrected.mark_value == Decimal("120")
    assert corrected.restatement_reason == "custodian restatement"
    assert corrected.valuation_date == VD  # carried verbatim
    assert corrected.valid_from.replace(tzinfo=None) == original.valid_from.replace(tzinfo=None)
    assert corrected.system_to is None
    assert _events(session, "VALUATION.CORRECTION") == 1
    assert _events(session, "VALUATION.UPDATE") == 1


def test_content_immutability_on_correction(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, mark_value=Decimal("100"))
    orig_id = original.id
    orig_mark = original.mark_value
    session.commit()

    correct_valuation(
        session,
        original,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=_actor(),
        mark_value=Decimal("999"),
    )
    session.commit()

    session.expire_all()
    prior = session.get(Valuation, orig_id)
    assert prior is not None
    assert prior.mark_value == orig_mark  # CONTENT unchanged (not the corrected 999)
    assert prior.restatement_reason is None  # the reason is on the NEW row only
    assert prior.valuation_date == VD
    assert prior.system_to is not None  # only the close-out column moved


def test_correction_audit_payload_two_part(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(session, tenant, pf_id, inst_id, mark_value=Decimal("100"))
    orig_id = original.id
    session.commit()

    corrected = correct_valuation(
        session,
        original,
        restatement_reason="why",
        acting_tenant=tenant,
        actor=_actor(),
        mark_value=Decimal("110"),
    )
    session.commit()

    upd = session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == orig_id, AuditEvent.event_type == "VALUATION.UPDATE"
        )
    ).scalar_one()
    assert upd.before_value == {"system_to": None}
    assert upd.after_value is not None and "system_to" in upd.after_value
    cor = session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == corrected.id, AuditEvent.event_type == "VALUATION.CORRECTION"
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
    corrected = correct_valuation(
        session, original, restatement_reason="r", acting_tenant=tenant, actor=_actor()
    )
    session.commit()
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == corrected.id)
    ).scalar_one()
    assert edge.target_entity_type == "valuation" and edge.edge_kind == "ORIGIN"
    assert_has_lineage(session, "valuation", corrected.id, tenant_id=tenant)


# --- valuation_date as a LOGICAL-KEY dimension ---


def test_two_valuation_dates_coexist(session: Session) -> None:
    # two marks for DIFFERENT valuation_dates on the SAME (portfolio, instrument) are two open
    # heads;
    # the 4-part current-head partial-unique does NOT collide.
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    a = _create(session, tenant, pf_id, inst_id, valuation_date=VD, mark_value=Decimal("100"))
    b = _create(session, tenant, pf_id, inst_id, valuation_date=VD2, mark_value=Decimal("200"))
    session.commit()
    assert a.id != b.id and a.valuation_date == VD and b.valuation_date == VD2
    # both are open current heads (valid_to/system_to NULL).
    open_heads = session.execute(
        select(func.count())
        .select_from(Valuation)
        .where(Valuation.valid_to.is_(None), Valuation.system_to.is_(None))
    ).scalar_one()
    assert open_heads == 2


def test_current_head_partial_unique_four_part_key(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id, valuation_date=VD)
    session.flush()
    # a SECOND dual-open row for the SAME (tenant, portfolio, instrument, valuation_date) collides.
    session.add(
        Valuation(
            tenant_id=tenant,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            valuation_date=VD,
            valid_from=T0,
            valid_to=None,
            system_from=utcnow(),
            system_to=None,
            mark_value=Decimal("5"),
            record_version=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_valuation_date_carried_forward(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id, valuation_date=VD)
    new = supersede_valuation(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        mark_value=Decimal("2"),
    )
    head = resolve_valuation(session, new.id, acting_tenant=tenant)
    corrected = correct_valuation(
        session, head, restatement_reason="r", acting_tenant=tenant, actor=_actor()
    )
    session.commit()
    assert new.valuation_date == VD and corrected.valuation_date == VD  # carried through both ops


# --- bitemporal reconstruction (both axes) ---


def test_reconstruct_valid_time_as_of(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id, valuation_date=VD, mark_value=Decimal("100"))
    supersede_valuation(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        mark_value=Decimal("105"),
    )
    session.commit()

    early = reconstruct_valuation_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        valid_at=datetime(2026, 4, 5, tzinfo=UTC),
    )
    late = reconstruct_valuation_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        valid_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert early is not None and early.mark_value == Decimal("100")
    assert late is not None and late.mark_value == Decimal("105")


def test_reconstruct_known_at_and_current_view(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _create(
        session, tenant, pf_id, inst_id, valuation_date=VD, mark_value=Decimal("100")
    )
    session.commit()

    t_known = utcnow()  # a knowledge instant BEFORE the correction
    correct_valuation(
        session,
        original,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=_actor(),
        mark_value=Decimal("140"),
    )
    session.commit()

    as_known = reconstruct_valuation_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        valid_at=T0,
        known_at=t_known,
    )
    current = reconstruct_valuation_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        valid_at=T0,
    )
    assert as_known is not None and as_known.mark_value == Decimal("100")
    assert current is not None and current.mark_value == Decimal("140")


# --- NOT append-only (the FR contrast with the IA transaction) ---


def test_valuation_is_not_append_only_close_out_update_succeeds(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    row = _create(session, tenant, pf_id, inst_id)
    session.commit()
    row.system_to = utcnow()
    session.flush()  # must NOT raise — FR is not append-only (no ORM guard, no trigger)
    session.commit()
    assert session.get(Valuation, row.id).system_to is not None


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


def test_resolve_cross_tenant_valuation_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    b_pf, b_inst = _seed_pf_inst(session, b, "_B")
    b_row = _create(session, b, b_pf, b_inst)
    session.commit()
    with pytest.raises(ValuationNotVisible):
        resolve_valuation(session, b_row.id, acting_tenant=a)


# --- CTRL-012: no silent write ---


def test_every_governed_write_emits_event(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _create(session, tenant, pf_id, inst_id, valuation_date=VD)
    new = supersede_valuation(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=T1,
        mark_value=Decimal("2"),
    )
    head = resolve_valuation(session, new.id, acting_tenant=tenant)
    correct_valuation(session, head, restatement_reason="r", acting_tenant=tenant, actor=_actor())
    session.commit()
    total = (
        _events(session, "VALUATION.CREATE")
        + _events(session, "VALUATION.UPDATE")
        + _events(session, "VALUATION.CORRECTION")
    )
    assert total == 5  # create(1) + supersede(2) + correct(2)
    assert verify_chain(session, tenant).ok is True


# --- fail-closed audit rollback ---


def test_fail_closed_audit_rollback(session: Session, monkeypatch) -> None:  # noqa: ANN001
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    session.commit()
    import irp_shared.valuation.service as svc

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("audit down")

    monkeypatch.setattr(svc, "record_event", _boom)
    with pytest.raises(RuntimeError):
        _create(session, tenant, pf_id, inst_id)
    session.rollback()
    assert session.execute(select(func.count()).select_from(Valuation)).scalar_one() == 0


# --- import direction: valuation -> {portfolio, reference, rails} only (NO position) ---


def test_import_direction() -> None:
    pkg = pathlib.Path(create_valuation.__module__.replace(".", "/")).parent
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    allowed = {"lineage", "audit", "db", "temporal", "portfolio", "reference", "valuation"}
    forbidden_roots = {"irp_backend", "irp_shared.models", "position"}
    for py in (root / pkg).glob("*.py"):
        for raw in py.read_text().splitlines():
            line = raw.strip()
            if not (line.startswith("from ") or line.startswith("import ")):
                continue
            for bad in forbidden_roots:
                assert bad not in line, f"{py.name} imports forbidden {bad}: {line}"
            if "irp_shared." in line:
                seg = line.split("irp_shared.")[1].split()[0].split(".")[0].rstrip(",")
                assert seg in allowed, f"{py.name} imports irp_shared.{seg}: {line}"
