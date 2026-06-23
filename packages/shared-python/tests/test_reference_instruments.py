"""SQLite-local unit/behavior tests for P1B-3 instrument / instrument_terms / identifier_xref.

RLS is a no-op on SQLite, so symmetric-isolation proofs live in the PG file; here we prove the
governed-write contract (own-event audit + MANUAL lineage), the FR bitemporal protocol (create /
effective-dated supersede / as-known correction + reconstruct-as-of on BOTH axes + content-
immutability + one-now), the deterministic-or-ambiguity resolver, the tenant-filtered cross-tenant
fail-closed (service-layer, pre-commit), the fail-closed audit rollback, and the scope fences.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.reference.identifier import (
    AmbiguousIdentifier,
    create_identifier_xref,
    resolve_identifier,
)
from irp_shared.reference.instrument import (
    InstrumentNotVisible,
    create_instrument,
)
from irp_shared.reference.instrument_terms import (
    NoCurrentTerms,
    correct_instrument_terms,
    create_instrument_terms,
    reconstruct_terms_as_of,
    supersede_instrument_terms,
)
from irp_shared.reference.issuer import IssuerNotVisible, create_issuer
from irp_shared.reference.legal_entity import create_legal_entity
from irp_shared.reference.models import (
    HYBRID_TABLES,
    IdentifierXref,
    Instrument,
    InstrumentTerms,
)
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass


def _t() -> str:
    import uuid

    return str(uuid.uuid4())


def _actor() -> ReferenceActor:
    return ReferenceActor(actor_id="steward")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _instr(session: Session, tenant: str, code: str = "BOND1", **kw) -> Instrument:  # noqa: ANN003
    return create_instrument(
        session,
        tenant_id=tenant,
        code=code,
        name=code,
        asset_class=kw.pop("asset_class", "BOND"),
        actor=_actor(),
        **kw,
    )


_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2027, 1, 1, tzinfo=UTC)
_T2 = datetime(2028, 1, 1, tzinfo=UTC)


# --- temporal classes ---


def test_temporal_classes() -> None:
    assert Instrument.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
    assert not hasattr(Instrument, "system_from")  # EV, not FR
    assert InstrumentTerms.__temporal_class__ == TemporalClass.FULL_REPRODUCIBLE
    assert hasattr(InstrumentTerms, "system_from") and hasattr(InstrumentTerms, "system_to")
    assert IdentifierXref.__temporal_class__ == TemporalClass.EFFECTIVE_DATED


def test_instrument_has_single_lifecycle_flag_no_status() -> None:
    for model in (Instrument, IdentifierXref):
        assert hasattr(model, "is_active")
        assert not hasattr(
            model, "status"
        )  # review arch-1: single is_active flag, no status string


# --- instrument identity ---


def test_instrument_create_lineage_and_audit(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant, currency_code="USD")
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == inst.id)
    ).scalar_one()
    assert edge.target_entity_type == "instrument" and edge.edge_kind == "ORIGIN"
    src = session.get(DataSource, edge.source_id)
    assert src is not None and src.source_type == "MANUAL"
    assert_has_lineage(session, "instrument", inst.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == inst.id)).scalar_one()
    assert ev.event_type == "REFERENCE.CREATE" and ev.entity_type == "instrument"
    assert verify_chain(session, tenant).ok is True


def test_instrument_unique_code(session: Session) -> None:
    tenant = _t()
    _instr(session, tenant, "DUP")
    with pytest.raises(IntegrityError):
        _instr(session, tenant, "DUP")


def test_instrument_issuer_optional_and_with_issuer(session: Session) -> None:
    tenant = _t()
    cash = _instr(session, tenant, "CASH", asset_class="CASH")  # no issuer
    assert cash.issuer_id is None
    le = create_legal_entity(session, tenant_id=tenant, code="LE", name="LE", actor=_actor())
    iss = create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    bond = _instr(session, tenant, "BOND", issuer_id=iss.id)
    assert bond.issuer_id == iss.id


def test_instrument_cross_tenant_issuer_fails_closed_no_side_effect(session: Session) -> None:
    a, b = _t(), _t()
    le = create_legal_entity(session, tenant_id=b, code="LE", name="LE", actor=_actor())
    iss = create_issuer(session, tenant_id=b, legal_entity_id=le.id, actor=_actor())
    # Tenant A cannot attach tenant B's issuer — service-layer IssuerNotVisible (NOT
    # IntegrityError).
    with pytest.raises(IssuerNotVisible):
        create_instrument(
            session,
            tenant_id=a,
            code="X",
            name="X",
            asset_class="BOND",
            actor=_actor(),
            issuer_id=iss.id,
        )
    session.rollback()
    # No instrument row + no instrument audit event were created for the rejected write.
    assert session.execute(select(func.count()).select_from(Instrument)).scalar_one() == 0
    assert (
        session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "instrument")
        ).scalar_one()
        == 0
    )


# --- FR instrument_terms ---


def _seed_terms(session: Session, tenant: str) -> tuple[Instrument, InstrumentTerms]:
    inst = _instr(session, tenant)
    v1 = create_instrument_terms(
        session,
        instrument_id=inst.id,
        acting_tenant=tenant,
        actor=_actor(),
        valid_from=_T0,
        coupon_rate=Decimal("5.5"),
        day_count="30/360",
    )
    return inst, v1


def test_terms_create_open_version(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    assert v1.valid_to is None and v1.system_to is None and v1.record_version == 1
    assert_has_lineage(session, "instrument_terms", v1.id, tenant_id=tenant)
    assert _events(session, "REFERENCE.CREATE") >= 1


def test_terms_effective_supersede(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    create_ct = _events(session, "REFERENCE.CREATE")
    v2 = supersede_instrument_terms(
        session,
        instrument_id=inst.id,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=_T1,
        coupon_rate=Decimal("6.0"),
    )
    assert v1.valid_to == _T1  # prior valid-time closed at the new effective date
    assert v2.valid_from == _T1 and v2.valid_to is None and v2.system_to is None
    assert v2.supersedes_id == v1.id and v2.record_version == 2 and v2.coupon_rate == Decimal("6.0")
    assert _events(session, "REFERENCE.CREATE") == create_ct + 1  # new version row
    assert _events(session, "REFERENCE.UPDATE") >= 1  # prior valid_to close-out
    assert_has_lineage(session, "instrument_terms", v2.id, tenant_id=tenant)  # own origin edge


def test_terms_correction_as_known_axis(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    before_correction = datetime.now(UTC)
    v_corr = correct_instrument_terms(
        session,
        v1,
        restatement_reason="bad coupon",
        acting_tenant=tenant,
        actor=_actor(),
        coupon_rate=Decimal("5.25"),
    )
    assert v1.system_to is not None  # prior knowledge interval closed
    assert v1.system_to == v_corr.system_from  # ONE now (no inter-row gap)
    assert (
        v_corr.valid_from == v1.valid_from and v_corr.valid_to == v1.valid_to
    )  # same valid period
    assert v_corr.restatement_reason == "bad coupon" and v_corr.supersedes_id == v1.id
    assert _events(session, "REFERENCE.CORRECTION") == 1
    # The corrected row is a NEW governed version -> its OWN MANUAL-source ORIGIN edge (CTRL-013).
    edge = assert_has_lineage(session, "instrument_terms", v_corr.id, tenant_id=tenant)
    assert edge.edge_kind == "ORIGIN"
    # known-time reconstruction: as-known-before the correction returns the prior values.
    old = reconstruct_terms_as_of(
        session, inst.id, acting_tenant=tenant, valid_at=_T1, known_at=before_correction
    )
    assert old is not None and old.id == v1.id and old.coupon_rate == Decimal("5.5")
    cur = reconstruct_terms_as_of(session, inst.id, acting_tenant=tenant, valid_at=_T1)
    assert cur is not None and cur.id == v_corr.id and cur.coupon_rate == Decimal("5.25")


def test_terms_content_immutability_on_correction(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    correct_instrument_terms(
        session,
        v1,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=_actor(),
        coupon_rate=Decimal("9.9"),
    )
    refetched = session.get(InstrumentTerms, v1.id)
    assert refetched is not None
    assert refetched.coupon_rate == Decimal("5.5")  # prior economic column NEVER mutated
    assert refetched.restatement_reason is None  # restatement_reason set only on the corrected row


def test_terms_as_of_both_axes_valid_time(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    v2 = supersede_instrument_terms(
        session,
        instrument_id=inst.id,
        acting_tenant=tenant,
        actor=_actor(),
        effective_at=_T1,
        coupon_rate=Decimal("6.0"),
    )
    # valid-time reconstruction picks the version effective at the queried business date.
    early = reconstruct_terms_as_of(
        session, inst.id, acting_tenant=tenant, valid_at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    late = reconstruct_terms_as_of(session, inst.id, acting_tenant=tenant, valid_at=_T2)
    assert early is not None and early.id == v1.id
    assert late is not None and late.id == v2.id


def test_terms_current_version_partial_unique(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    # A second OPEN-on-both-axes version for the same instrument violates
    # uq_instrument_terms_current.
    with pytest.raises(IntegrityError):
        create_instrument_terms(
            session, instrument_id=inst.id, acting_tenant=tenant, actor=_actor(), valid_from=_T0
        )


def test_correction_audit_payload_tr08(session: Session) -> None:
    tenant = _t()
    inst, v1 = _seed_terms(session, tenant)
    v_corr = correct_instrument_terms(
        session, v1, restatement_reason="restate", acting_tenant=tenant, actor=_actor()
    )
    ev = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "REFERENCE.CORRECTION")
    ).scalar_one()
    assert ev.justification == "restate"  # TR-08 reason on the canonical audit field
    assert "restatement_reason" in ev.after_value and "supersedes_id" in ev.after_value
    assert ev.after_value["supersedes_id"] == v1.id == v_corr.supersedes_id
    # The other half of the two-event correction write: the prior row's REFERENCE.UPDATE captures
    # the system_to close-out transition (null -> the close instant) — provable in the audit trail.
    upd = session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == "REFERENCE.UPDATE", AuditEvent.entity_id == v1.id
        )
    ).scalar_one()
    assert upd.before_value == {"system_to": None}
    assert upd.after_value["system_to"] is not None
    assert upd.after_value["system_to"] == v1.system_to.isoformat()


def test_supersede_without_current_terms_raises(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    with pytest.raises(NoCurrentTerms):
        supersede_instrument_terms(
            session, instrument_id=inst.id, acting_tenant=tenant, actor=_actor(), effective_at=_T1
        )


def test_terms_cross_tenant_instrument_fails_closed(session: Session) -> None:
    a, b = _t(), _t()
    inst_b = _instr(session, b, "B_BOND")
    with pytest.raises(InstrumentNotVisible):
        create_instrument_terms(
            session, instrument_id=inst_b.id, acting_tenant=a, actor=_actor(), valid_from=_T0
        )
    session.rollback()
    assert (
        session.execute(
            select(func.count())
            .select_from(InstrumentTerms)
            .where(InstrumentTerms.instrument_id == inst_b.id)
        ).scalar_one()
        == 0
    )


# --- identifier_xref ---


def test_identifier_create_and_resolve_single(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    x = create_identifier_xref(
        session,
        tenant_id=tenant,
        instrument_id=inst.id,
        scheme="ISIN",
        value="  US0000001  ",
        actor=_actor(),
    )
    assert x.entity_type == "instrument" and x.entity_id == inst.id and x.value == "US0000001"
    resolved = resolve_identifier(session, scheme="ISIN", value="US0000001", acting_tenant=tenant)
    assert resolved is not None and resolved.id == inst.id  # trim hygiene + single result


def test_identifier_active_partial_unique(session: Session) -> None:
    tenant = _t()
    inst = _instr(session, tenant)
    create_identifier_xref(
        session, tenant_id=tenant, instrument_id=inst.id, scheme="CUSIP", value="X", actor=_actor()
    )
    inst2 = _instr(session, tenant, "BOND2")
    with pytest.raises(IntegrityError):  # two ACTIVE (tenant, scheme, value) rows
        create_identifier_xref(
            session,
            tenant_id=tenant,
            instrument_id=inst2.id,
            scheme="CUSIP",
            value="X",
            actor=_actor(),
        )


def test_identifier_resolve_none(session: Session) -> None:
    tenant = _t()
    assert resolve_identifier(session, scheme="ISIN", value="MISSING", acting_tenant=tenant) is None


def test_identifier_resolve_ambiguous_historical_overlap(session: Session) -> None:
    tenant = _t()
    inst1 = _instr(session, tenant, "I1")
    inst2 = _instr(session, tenant, "I2")
    # Two CLOSED rows (valid_to NOT NULL — not blocked by the active partial-unique) whose windows
    # overlap, pointing at DIFFERENT instruments. A past as_of inside the overlap matches BOTH.
    session.add_all(
        [
            IdentifierXref(
                tenant_id=tenant,
                entity_type="instrument",
                entity_id=inst1.id,
                scheme="SEDOL",
                value="AMB",
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 1, tzinfo=UTC),
                is_active=True,
                record_version=1,
            ),
            IdentifierXref(
                tenant_id=tenant,
                entity_type="instrument",
                entity_id=inst2.id,
                scheme="SEDOL",
                value="AMB",
                valid_from=datetime(2026, 3, 1, tzinfo=UTC),
                valid_to=datetime(2026, 9, 1, tzinfo=UTC),
                is_active=True,
                record_version=1,
            ),
        ]
    )
    session.flush()
    with pytest.raises(AmbiguousIdentifier) as exc:
        resolve_identifier(
            session,
            scheme="SEDOL",
            value="AMB",
            acting_tenant=tenant,
            as_of=datetime(2026, 4, 1, tzinfo=UTC),
        )
    assert len(exc.value.matched_entity_ids) == 2  # no silent arbitrary pick


def test_identifier_cross_tenant_entity_id_fails_closed(session: Session) -> None:
    a, b = _t(), _t()
    inst_b = _instr(session, b, "B_BOND")
    with pytest.raises(InstrumentNotVisible):  # service-layer, not an RLS 42501
        create_identifier_xref(
            session, tenant_id=a, instrument_id=inst_b.id, scheme="ISIN", value="V", actor=_actor()
        )
    session.rollback()
    assert (
        session.execute(
            select(func.count())
            .select_from(IdentifierXref)
            .where(IdentifierXref.entity_id == inst_b.id)
        ).scalar_one()
        == 0
    )


# --- fail-closed audit rollback (no row => no audit => no lineage) ---


def test_fail_closed_no_audit_no_lineage(session: Session) -> None:
    tenant = _t()
    import uuid

    ghost_issuer = str(uuid.uuid4())
    with pytest.raises(IssuerNotVisible):
        create_instrument(
            session,
            tenant_id=tenant,
            code="X",
            name="X",
            asset_class="BOND",
            actor=_actor(),
            issuer_id=ghost_issuer,
        )
    session.rollback()
    assert session.execute(select(func.count()).select_from(Instrument)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(DataSource)).scalar_one() == 0


# --- scope fences ---


def test_hybrid_set_unchanged() -> None:
    # P1B-3 adds NO hybrid table; the closed set stays exactly the five P1B-1 tables.
    assert HYBRID_TABLES == (
        "currency",
        "calendar",
        "calendar_holiday",
        "rating_scale",
        "rating_grade",
    )


def test_instrument_has_no_terms_or_risk_columns() -> None:
    forbidden = {
        "coupon_rate",
        "maturity_date",
        "price",
        "valuation",
        "quantity",
        "exposure",
        "var",
        "status",
    }
    cols = {c.name for c in Instrument.__table__.columns}
    assert not (forbidden & cols), forbidden & cols


def test_identifier_xref_has_no_precedence_column() -> None:
    # OD-012 precedence/vendor-authority engine is deferred to P1C — no ranking/authority column.
    forbidden = {"precedence", "rank", "priority", "authority", "vendor_rank", "status"}
    cols = {c.name for c in IdentifierXref.__table__.columns}
    assert not (forbidden & cols), forbidden & cols


def test_create_identifier_xref_forces_instrument_entity_type(session: Session) -> None:
    # entity_type is hard-forced to 'instrument' in P1B-3 (scope fence; entity-identifier deferred).
    tenant = _t()
    inst = _instr(session, tenant)
    x = create_identifier_xref(
        session, tenant_id=tenant, instrument_id=inst.id, scheme="ISIN", value="V", actor=_actor()
    )
    assert x.entity_type == "instrument"
