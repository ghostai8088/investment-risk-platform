"""SQLite-local unit/behavior tests for P1B-2 legal_entity / issuer / counterparty (REQ-SMR-002).

RLS is a no-op on SQLite, so symmetric-isolation proofs live in the PG test file; here
we prove the governed-write contract (own-event audit + MANUAL lineage), the shared-core / 1:1
role-profile model (OD-P1B-D), the tenant-filtered cross-tenant fail-closed (which MUST hold
on SQLite too), the hierarchy (bounded, cycle-safe, boundary-terminating resolver; self-parent
reject; NO exposure math), the fail-closed audit rollback (CREATE per entity + UPDATE), the import
direction (shared scanner), and the scope fence (proprietary never hybrid; no excluded columns).
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.entitlement.bootstrap import ALL_CODES
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.reference.counterparty import create_counterparty, update_counterparty
from irp_shared.reference.events import (
    REFERENCE_CORRECTION_EVENT,
    REFERENCE_CREATE_EVENT,
    REFERENCE_STATUS_CHANGE_EVENT,
    REFERENCE_UPDATE_EVENT,
)
from irp_shared.reference.issuer import create_issuer, update_issuer
from irp_shared.reference.legal_entity import (
    HierarchyCycleError,
    LegalEntityNotVisible,
    create_legal_entity,
    resolve_legal_entity,
    resolve_ultimate_parent,
    update_legal_entity,
)
from irp_shared.reference.models import (
    HYBRID_TABLES,
    Counterparty,
    Issuer,
    LegalEntity,
)
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass


def _tenant() -> str:
    return str(uuid.uuid4())


def _actor() -> ReferenceActor:
    return ReferenceActor(actor_id="steward")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _le(session: Session, tenant: str, code: str, **kw) -> LegalEntity:  # noqa: ANN003
    return create_legal_entity(
        session, tenant_id=tenant, code=code, name=code, actor=_actor(), **kw
    )


# --- temporal classes: all three EV, no FR/system_from ---


def test_all_three_are_effective_dated_no_fr() -> None:
    for model in (LegalEntity, Issuer, Counterparty):
        assert model.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
        assert hasattr(model, "valid_from") and hasattr(model, "record_version")
        assert not hasattr(model, "system_from")  # not IA/FR


# --- shared core + 1:1 role profiles (OD-P1B-D) ---


def test_legal_entity_create_records_lineage_and_audit(session: Session) -> None:
    tenant = _tenant()
    le = _le(
        session, tenant, "LE1", lei="LEI0000000000000001", jurisdiction="US", entity_type="CORP"
    )
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == le.id)
    ).scalar_one()
    assert edge.target_entity_type == "legal_entity" and edge.edge_kind == "ORIGIN"
    source = session.get(DataSource, edge.source_id)
    assert source is not None and source.source_type == "MANUAL"
    assert_has_lineage(session, "legal_entity", le.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == le.id)).scalar_one()
    assert ev.event_type == "REFERENCE.CREATE" == REFERENCE_CREATE_EVENT
    assert ev.entity_type == "legal_entity" and ev.action == "create"
    assert verify_chain(session, tenant).ok is True


def test_one_legal_entity_carries_both_roles(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "BANK")
    iss = create_issuer(
        session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor(), issuer_type="CORPORATE"
    )
    cpty = create_counterparty(
        session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor(), counterparty_type="BANK"
    )
    assert iss.legal_entity_id == le.id and cpty.legal_entity_id == le.id
    assert iss.tenant_id == tenant and cpty.tenant_id == tenant


def test_dup_issuer_for_same_core_rejected_1to1(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    session.flush()
    with pytest.raises(IntegrityError):  # second issuer for the same core flushes inside the binder
        create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    session.rollback()


def test_dup_counterparty_for_same_core_rejected_1to1(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    session.flush()
    with pytest.raises(IntegrityError):
        create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    session.rollback()


def test_profiles_carry_no_identity_columns(session: Session) -> None:
    # Identity on the core ONLY: profiles must NOT duplicate code/lei/name/jurisdiction/hierarchy.
    forbidden = {"code", "lei", "name", "jurisdiction", "parent_legal_entity_id"}
    for model in (Issuer, Counterparty):
        cols = set(model.__table__.columns.keys())
        assert not (
            forbidden & cols
        ), f"{model.__tablename__} duplicates core identity: {forbidden & cols}"
        # FK only to legal_entity.
        assert {fk.column.table.name for fk in model.__table__.foreign_keys} == {"legal_entity"}


# --- orphan-profile-rejected: explicit tenant filter => fail-closed on SQLite too ---


def test_profile_create_cross_tenant_core_fails_closed(session: Session) -> None:
    owner, other = _tenant(), _tenant()
    le = _le(session, owner, "LE")
    session.flush()
    # Tenant `other` cannot attach a profile to `owner`'s core (explicit tenant_id predicate).
    with pytest.raises(LegalEntityNotVisible):
        create_issuer(session, tenant_id=other, legal_entity_id=le.id, actor=_actor())
    with pytest.raises(LegalEntityNotVisible):
        create_counterparty(session, tenant_id=other, legal_entity_id=le.id, actor=_actor())
    assert session.execute(select(func.count()).select_from(Issuer)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(Counterparty)).scalar_one() == 0


def test_profile_create_unknown_core_fails_closed(session: Session) -> None:
    tenant = _tenant()
    with pytest.raises(LegalEntityNotVisible):
        create_issuer(session, tenant_id=tenant, legal_entity_id=str(uuid.uuid4()), actor=_actor())


def test_resolve_legal_entity_explicit_tenant_filter(session: Session) -> None:
    owner, other = _tenant(), _tenant()
    le = _le(session, owner, "LE")
    session.flush()
    assert resolve_legal_entity(session, le.id, acting_tenant=owner).id == le.id
    with pytest.raises(LegalEntityNotVisible):  # visible to owner, NOT to other (even on SQLite)
        resolve_legal_entity(session, le.id, acting_tenant=other)


# --- hierarchy: structure only, bounded, cycle-safe, boundary-terminating, NO exposure math ---


def test_resolve_ultimate_parent_walks_to_root(session: Session) -> None:
    t = _tenant()
    ult = _le(session, t, "ULT")
    mid = _le(session, t, "MID", parent_legal_entity_id=ult.id)
    leaf = _le(session, t, "LEAF", parent_legal_entity_id=mid.id)
    session.flush()
    assert resolve_ultimate_parent(session, leaf, acting_tenant=t) == ult.id
    assert (
        resolve_ultimate_parent(session, ult, acting_tenant=t) == ult.id
    )  # a root resolves to self


def test_self_parent_rejected_on_update(session: Session) -> None:
    t = _tenant()
    le = _le(session, t, "LE")
    session.flush()
    with pytest.raises(ValueError, match="own parent"):
        update_legal_entity(session, le, actor=_actor(), parent_legal_entity_id=le.id)


def test_cross_tenant_parent_rejected_on_create_and_update(session: Session) -> None:
    t, other = _tenant(), _tenant()
    foreign = _le(session, other, "F")
    session.flush()
    with pytest.raises(LegalEntityNotVisible):
        _le(session, t, "CH", parent_legal_entity_id=foreign.id)  # create with cross-tenant parent
    le = _le(session, t, "CH2")
    session.flush()
    with pytest.raises(LegalEntityNotVisible):
        update_legal_entity(session, le, actor=_actor(), parent_legal_entity_id=foreign.id)


def test_resolver_is_cycle_safe(session: Session) -> None:
    # Deep cycle prevention is deferred (a re-parent that creates a cycle is allowed at write time);
    # the read-time resolver MUST terminate via the visited-set, never loop.
    t = _tenant()
    a = _le(session, t, "A")
    b = _le(session, t, "B", parent_legal_entity_id=a.id)
    session.flush()
    update_legal_entity(session, a, actor=_actor(), parent_legal_entity_id=b.id)  # a<->b cycle
    with pytest.raises(HierarchyCycleError):
        resolve_ultimate_parent(session, a, acting_tenant=t)


def test_resolver_terminates_at_tenant_boundary(session: Session) -> None:
    t, other = _tenant(), _tenant()
    foreign = _le(session, other, "F")
    child = _le(session, t, "CH")
    session.flush()
    child.parent_legal_entity_id = foreign.id  # raw cross-tenant link (bypassing the binder guard)
    session.flush()
    # Walk under tenant t: the foreign parent is not visible -> walk STOPS at child (boundary).
    assert resolve_ultimate_parent(session, child, acting_tenant=t) == child.id


# --- own-event audit: each entity emits its OWN event (NOT folded) ---


def test_each_entity_emits_own_create_event(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    assert _events(session, REFERENCE_CREATE_EVENT) == 3  # one per entity, none folded
    assert _events(session, REFERENCE_UPDATE_EVENT) == 0
    types = {
        r[0]
        for r in session.execute(
            select(AuditEvent.entity_type).where(AuditEvent.event_type == REFERENCE_CREATE_EVENT)
        )
    }
    assert types == {"legal_entity", "issuer", "counterparty"}


def test_issuer_create_emits_exactly_one_issuer_event_not_folded(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    base = _events(session, REFERENCE_CREATE_EVENT)  # == 1 (the legal_entity)
    iss = create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    # Exactly one NEW REFERENCE.CREATE, with entity_type='issuer' on the issuer id (not the core).
    assert _events(session, REFERENCE_CREATE_EVENT) == base + 1
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == iss.id)).scalar_one()
    assert ev.entity_type == "issuer" and ev.event_type == "REFERENCE.CREATE"


# --- lineage: one ORIGIN edge per row; MANUAL-source idempotency; single-origin on UPDATE ---


def test_one_origin_edge_per_row_and_manual_source_idempotent(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    iss = create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    cpty = create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    # One ORIGIN edge per entity row (3 rows -> 3 edges).
    assert session.execute(select(func.count()).select_from(LineageEdge)).scalar_one() == 3
    for ent_type, ent_id in (
        ("legal_entity", le.id),
        ("issuer", iss.id),
        ("counterparty", cpty.id),
    ):
        assert_has_lineage(session, ent_type, ent_id, tenant_id=tenant)
    # Exactly ONE MANUAL data_source + ONE DATA.SOURCE_REGISTER for the tenant across 3 creates.
    assert (
        session.execute(
            select(func.count()).select_from(DataSource).where(DataSource.tenant_id == tenant)
        ).scalar_one()
        == 1
    )
    assert (
        session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "DATA.SOURCE_REGISTER", AuditEvent.tenant_id == tenant)
        ).scalar_one()
        == 1
    )


def test_update_keeps_exactly_one_origin_edge(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE", entity_type="CORP")
    edge_before = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == le.id)
    ).scalar_one()
    update_legal_entity(session, le, actor=_actor(), name="Renamed", is_active=False)
    edges = (
        session.execute(select(LineageEdge).where(LineageEdge.target_entity_id == le.id))
        .scalars()
        .all()
    )
    assert len(edges) == 1 and edges[0].id == edge_before.id  # no second edge on UPDATE


# --- EV mutability + REFERENCE.UPDATE ---


def test_update_emits_update_event_and_bumps_version(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    update_legal_entity(session, le, actor=_actor(), name="New Name", is_active=False)
    assert le.record_version == 2 and le.name == "New Name"
    iss = create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    update_issuer(session, iss, actor=_actor(), sector="Financials")
    cpty = create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    update_counterparty(session, cpty, actor=_actor(), counterparty_type="CCP")
    assert _events(session, REFERENCE_UPDATE_EVENT) == 3
    assert iss.record_version == 2 and cpty.record_version == 2


# --- fail-closed audit rollback (AUD-04 / CTRL-032): CREATE per entity + UPDATE ---


def _raise_audit(*_a: object, **_k: object) -> None:
    raise RuntimeError("audit capture failed")


def _assert_all_empty(session: Session) -> None:
    for model in (LegalEntity, Issuer, Counterparty, DataSource, LineageEdge, AuditEvent):
        assert session.execute(select(func.count()).select_from(model)).scalar_one() == 0


def test_legal_entity_create_rolls_back_no_orphan(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.reference.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        _le(session, _tenant(), "LE")
    session.rollback()
    _assert_all_empty(
        session
    )  # row + edge + lazily-created MANUAL source + DATA.SOURCE_REGISTER all gone


def test_issuer_create_rolls_back_no_orphan(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Valid core FIRST (resolution passes) — all in ONE uncommitted txn — then patched audit raises
    # on the issuer write, so the WHOLE unit-of-work (core + source + edges + issuer) rolls back.
    import irp_shared.reference.service as svc

    tenant = _tenant()
    le = _le(session, tenant, "LE")
    session.flush()
    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    session.rollback()
    _assert_all_empty(session)


def test_counterparty_create_rolls_back_no_orphan(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.reference.service as svc

    tenant = _tenant()
    le = _le(session, tenant, "LE")
    session.flush()
    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    session.rollback()
    _assert_all_empty(session)


def test_update_rolls_back_attributes_and_version(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.reference.service as svc

    tenant = _tenant()
    le = _le(session, tenant, "LE")
    session.commit()  # persist the create; the UPDATE is the unit under test
    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        update_legal_entity(session, le, actor=_actor(), name="Renamed", is_active=False)
    session.rollback()
    refetched = session.get(LegalEntity, le.id)
    assert refetched is not None
    assert refetched.name == "LE" and refetched.is_active is True and refetched.record_version == 1
    assert _events(session, REFERENCE_UPDATE_EVENT) == 0  # no governed change leaked


def test_verify_chain_green_after_fail_closed_rollback(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.reference.service as svc

    tenant = _tenant()
    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        _le(session, tenant, "LE")
    session.rollback()
    monkeypatch.undo()
    _le(session, tenant, "LE2")  # a successful create on the same tenant after the rollback
    result = verify_chain(session, tenant)
    assert result.ok is True  # contiguous sequence_no; the rolled-back event left no gap


# --- DC-2 metadata-only ---


def test_audit_after_value_is_metadata_only(session: Session) -> None:
    tenant = _tenant()
    secret = "MNPI_NAME_42"
    le = _le(session, tenant, "LE")
    le2 = create_legal_entity(
        session, tenant_id=tenant, code="LE2", name=secret, actor=_actor(), lei="LEI2"
    )
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == le2.id)).scalar_one()
    # The legal name IS identifying metadata (DC-2) — present; the assertion is the SHAPE: only the
    # declared keys, no raw extras, no joined profile collection.
    assert set(ev.after_value) == {
        "code",
        "name",
        "lei",
        "jurisdiction",
        "entity_type",
        "is_active",
        "parent_legal_entity_id",
    }
    iss = create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    iev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == iss.id)).scalar_one()
    body = json.dumps(iev.after_value)
    assert set(iev.after_value) == {"legal_entity_id", "issuer_type", "sector", "is_active"}
    assert secret not in body  # the issuer event does not serialize the joined core's name


# --- scope fence (proprietary never hybrid; no excluded columns/entities) ---


def test_scope_fence_proprietary_never_hybrid() -> None:
    # The three P1B-2 tables are NOT in the closed hybrid set (which stays the five P1B-1 tables).
    assert set(HYBRID_TABLES) == {
        "currency",
        "calendar",
        "calendar_holiday",
        "rating_scale",
        "rating_grade",
    }
    for table in ("legal_entity", "issuer", "counterparty"):
        assert table not in HYBRID_TABLES


def test_scope_fence_no_excluded_columns() -> None:
    # counterparty: ZERO netting/CSA/collateral/exposure columns (OD-015 deferred).
    cpty_cols = set(Counterparty.__table__.columns.keys())
    forbidden_cpty = {
        "netting_set",
        "netting_set_id",
        "csa",
        "csa_id",
        "collateral",
        "exposure",
        "current_exposure",
        "potential_exposure",
        "credit_limit",
    }
    assert not (forbidden_cpty & cpty_cols)
    # legal_entity: NO stored rollup/exposure column (only the parent_legal_entity_id self-FK).
    le_cols = set(LegalEntity.__table__.columns.keys())
    forbidden_le = {"ultimate_parent_id", "rollup", "exposure", "concentration", "spread"}
    assert not (forbidden_le & le_cols)
    le_fk_targets = {fk.column.table.name for fk in LegalEntity.__table__.foreign_keys}
    assert le_fk_targets == {"legal_entity"}  # only the intra-tenant self-FK


def test_scope_fence_reserved_events_and_rating_perm() -> None:
    # reference.rating.* RESERVED; reserved REFERENCE.* codes declared but only CREATE/UPDATE used.
    assert not any(code.startswith("reference.rating.") for code in ALL_CODES)
    assert "reference.legal_entity.view" in ALL_CODES and "reference.legal_entity.edit" in ALL_CODES
    assert REFERENCE_CORRECTION_EVENT == "REFERENCE.CORRECTION"
    assert REFERENCE_STATUS_CHANGE_EVENT == "REFERENCE.STATUS_CHANGE"


def test_reserved_events_not_emitted(session: Session) -> None:
    tenant = _tenant()
    le = _le(session, tenant, "LE")
    create_issuer(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    create_counterparty(session, tenant_id=tenant, legal_entity_id=le.id, actor=_actor())
    update_legal_entity(session, le, actor=_actor(), is_active=False)
    assert _events(session, REFERENCE_CORRECTION_EVENT) == 0
    assert _events(session, REFERENCE_STATUS_CHANGE_EVENT) == 0


# --- uniqueness constraints (core code + LEI partial-unique) — DA-1/DA-2 ---


def test_core_code_unique_per_tenant(session: Session) -> None:
    t = _tenant()
    _le(session, t, "DUP")
    session.flush()
    with pytest.raises(IntegrityError):  # UNIQUE(tenant_id, code) on the core
        _le(session, t, "DUP")
    session.rollback()


def test_same_core_code_across_tenants_allowed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    _le(session, a, "SAME")
    _le(session, b, "SAME")  # different tenant -> allowed (per-tenant uniqueness)
    session.flush()


def test_lei_unique_per_tenant_when_present(session: Session) -> None:
    t = _tenant()
    _le(session, t, "A", lei="LEIXXXXXXXXXXXXXXX01")
    session.flush()
    with pytest.raises(IntegrityError):  # same (tenant_id, lei) where lei IS NOT NULL
        _le(session, t, "B", lei="LEIXXXXXXXXXXXXXXX01")
    session.rollback()


def test_null_lei_rows_coexist_in_one_tenant(session: Session) -> None:
    # The partial WHERE lei IS NOT NULL (and NULL-distinctness on SQLite) lets unidentified entities
    # share a tenant — multiple NULL-lei rows must NOT collide.
    t = _tenant()
    _le(session, t, "A")
    _le(session, t, "B")
    session.flush()
    assert (
        session.execute(
            select(func.count()).select_from(LegalEntity).where(LegalEntity.tenant_id == t)
        ).scalar_one()
        == 2
    )


def test_same_lei_across_tenants_allowed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    _le(session, a, "A", lei="LEISHARED0000000001")
    _le(session, b, "B", lei="LEISHARED0000000001")  # LEI unique is per-tenant, not global
    session.flush()


# --- single-physical-row + single-origin-on-UPDATE across all three entities (DA-3 / LIN-01) ---


def test_update_is_single_physical_row(session: Session) -> None:
    t = _tenant()
    le = _le(session, t, "LE")
    le_id = le.id
    update_legal_entity(session, le, actor=_actor(), name="Renamed")
    # In-place EV supersede: same row id, one physical row (history via the audit trail).
    assert le.id == le_id
    assert session.execute(select(func.count()).select_from(LegalEntity)).scalar_one() == 1


def test_update_single_origin_edge_all_entities_incl_reparent(session: Session) -> None:
    t = _tenant()
    p1 = _le(session, t, "P1")
    p2 = _le(session, t, "P2")
    child = _le(session, t, "CH", parent_legal_entity_id=p1.id)
    iss = create_issuer(session, tenant_id=t, legal_entity_id=child.id, actor=_actor())
    cpty = create_counterparty(session, tenant_id=t, legal_entity_id=child.id, actor=_actor())
    session.flush()

    def _edge(eid: str) -> LineageEdge:
        return session.execute(
            select(LineageEdge).where(LineageEdge.target_entity_id == eid)
        ).scalar_one()

    before = {child.id: _edge(child.id).id, iss.id: _edge(iss.id).id, cpty.id: _edge(cpty.id).id}
    update_legal_entity(session, child, actor=_actor(), parent_legal_entity_id=p2.id)  # re-parent
    update_issuer(session, iss, actor=_actor(), sector="Financials")
    update_counterparty(session, cpty, actor=_actor(), counterparty_type="CCP")
    for eid, before_id in before.items():
        edges = (
            session.execute(select(LineageEdge).where(LineageEdge.target_entity_id == eid))
            .scalars()
            .all()
        )
        assert len(edges) == 1 and edges[0].id == before_id  # no second edge on any UPDATE


def test_resolve_ultimate_parent_rejects_foreign_start_node(session: Session) -> None:
    # SEC-01 defense-in-depth: the resolver must reject a start node from another tenant.
    a, b = _tenant(), _tenant()
    le = _le(session, a, "LE")
    session.flush()
    with pytest.raises(LegalEntityNotVisible):
        resolve_ultimate_parent(session, le, acting_tenant=b)


# --- source-of-truth drift guards (PRD-01 / PRD-02) ---


def test_hybrid_tables_parity_models_vs_migration() -> None:
    import importlib.util
    import pathlib

    expected = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
    assert tuple(HYBRID_TABLES) == expected
    mig_path = (
        pathlib.Path(__file__).resolve().parents[3] / "migrations/versions/0008_reference_data.py"
    )
    spec = importlib.util.spec_from_file_location("_mig0008", mig_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(mod.HYBRID_TABLES) == expected  # the migration literal still equals the ORM set


def test_excluded_entity_tables_absent_from_metadata() -> None:
    from irp_shared.models import metadata

    # P1B-3 builds instrument / instrument_terms / identifier_xref; P1B-4 builds corporate_action;
    # P1C-1 builds portfolio (ENT-010); P1C-2 builds transaction (ENT-012); P1C-3 builds position
    # (ENT-011); P1C-4 builds valuation (ENT-013); P2-1 builds dataset_snapshot (ENT-049/050).
    # Later-slice (P2-2+) entities must still NOT exist.
    for table in ("price_point", "exposure", "exposure_aggregate"):
        assert table not in metadata.tables
