"""SQLite-local unit/behavior tests for the model registry skeleton (P1A-2).

RLS is a no-op on SQLite, so isolation/fail-closed proofs live in ``test_model_registry_pg.py``;
here we prove model/temporal/utility behavior, audit emission, the BR-3 inventory-before-use gate,
IA immutability vs the EV head, genericity, and the AC-11 non-enforcement guarantee.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.model.models import (
    Model,
    ModelAssumption,
    ModelLimitation,
    ModelVersion,
)
from irp_shared.model.service import (
    MODEL_REGISTER_EVENT,
    MODEL_TIER_ASSIGN_EVENT,
    MODEL_VERSION_EVENT,
    ModelNotVisible,
    ModelTierValueError,
    UnregisteredModelError,
    assert_registered_model_version,
    assign_model_tier,
    register_model,
    register_model_version,
)
from irp_shared.temporal import TemporalClass

# MODEL.VALIDATE was ACTIVATED at VW-1 (emitted by model.validation.record_validation); the other
# three stay reserved for the approval/restriction/retirement legs (P7, later slices).
STILL_RESERVED_P7_CODES = ("MODEL.APPROVE", "MODEL.RESTRICT", "MODEL.RETIRE")


def _tenant() -> str:
    return str(uuid.uuid4())


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _model(session: Session, tenant: str, code: str = "M1", **kw: object) -> Model:
    return register_model(
        session,
        tenant_id=tenant,
        code=code,
        name="A model",
        model_type=kw.pop("model_type", "STATISTICAL"),
        actor_id="dev",
        **kw,
    )


def test_temporal_classes() -> None:
    assert Model.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
    assert hasattr(Model, "valid_from") and hasattr(Model, "valid_to")
    for ia in (ModelVersion, ModelAssumption, ModelLimitation):
        assert ia.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
        assert hasattr(ia, "system_from")
        assert not hasattr(ia, "valid_to")  # IA: single axis (TR-21)


def test_register_model_and_version(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    assert model.tenant_id == tenant
    version = register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    assert version.tenant_id == tenant  # stamped from resolved parent
    assert version.model_id == model.id
    assert session.get(ModelVersion, version.id) is not None


def test_register_version_with_assumptions_and_limitations(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    version = register_model_version(
        session,
        model=model,
        version_label="1.0.0",
        actor_id="dev",
        assumptions=["normal returns", "no jumps"],
        limitations=["ignores liquidity"],
        authored_by="quant.ai.agent",
    )
    a = (
        session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == version.id)
        )
        .scalars()
        .all()
    )
    limits = (
        session.execute(
            select(ModelLimitation).where(ModelLimitation.model_version_id == version.id)
        )
        .scalars()
        .all()
    )
    assert len(a) == 2 and len(limits) == 1
    assert a[0].authored_by == "quant.ai.agent"  # MG-05 attribution (AI-or-human)


def test_multiple_immutable_versions_per_model(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    v1 = register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    v2 = register_model_version(session, model=model, version_label="2.0.0", actor_id="dev")
    assert v1.id != v2.id
    assert (
        session.execute(
            select(func.count()).select_from(ModelVersion).where(ModelVersion.model_id == model.id)
        ).scalar_one()
        == 2
    )


def test_unique_constraints(session: Session) -> None:
    tenant = _tenant()
    _model(session, tenant, code="DUP")
    session.flush()
    # Same model code in another tenant is allowed.
    _model(session, _tenant(), code="DUP")
    session.flush()
    # Duplicate model code within a tenant is rejected.
    session.add(Model(tenant_id=tenant, code="DUP", name="n", model_type="X"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    # Duplicate version label within a model is rejected.
    model = _model(session, tenant, code="VER")
    register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    session.flush()
    session.add(ModelVersion(tenant_id=tenant, model_id=model.id, version_label="1.0.0"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_governance_placeholders_default_and_writable(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    # Defaults: validation_status seeded UNVALIDATED; the rest null; DR-P1-3 hooks null.
    assert model.validation_status == "UNVALIDATED"
    assert model.tier is None and model.approved_use is None
    assert model.approval_status is None and model.made_by is None
    # Writable but non-enforcing.
    model.tier = "Tier 1"
    model.validation_status = "IN_REVIEW"
    session.flush()
    assert session.get(Model, model.id).tier == "Tier 1"


def test_generic_model_type_needs_no_schema_branch(session: Session) -> None:
    tenant = _tenant()
    for i, mt in enumerate(("MARKET_VAR", "CREDIT_PD", "PRIVATE_ASSET_PROXY", "AI_ML")):
        m = _model(session, tenant, code=f"M_{i}", model_type=mt)
        assert m.model_type == mt  # any model family registers by value, no migration


def test_register_emits_audit_and_chain_verifies(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    reg = (
        session.execute(select(AuditEvent).where(AuditEvent.entity_id == model.id)).scalars().all()
    )
    assert len(reg) == 1 and reg[0].event_type == MODEL_REGISTER_EVENT
    assert reg[0].entity_type == "model"

    version = register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    ver = (
        session.execute(select(AuditEvent).where(AuditEvent.entity_id == version.id))
        .scalars()
        .all()
    )
    assert len(ver) == 1 and ver[0].event_type == MODEL_VERSION_EVENT
    assert ver[0].after_value["is_immutable"] is True
    assert verify_chain(session, tenant).ok is True


def test_assumptions_limitations_emit_no_extra_event(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    before = _events(session, MODEL_VERSION_EVENT)
    version = register_model_version(
        session,
        model=model,
        version_label="1.0.0",
        actor_id="dev",
        assumptions=["a1", "a2"],
        limitations=["l1"],
    )
    # Exactly one MODEL.VERSION (folds the captures); no per-assumption/limitation event.
    assert _events(session, MODEL_VERSION_EVENT) == before + 1
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == version.id)).scalar_one()
    assert ev.after_value["assumption_count"] == 2
    assert ev.after_value["limitation_count"] == 1


def test_reserved_p7_codes_never_emitted(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    register_model_version(
        session, model=model, version_label="1.0.0", actor_id="dev", limitations=["x"]
    )
    # The still-reserved approval/restriction/retirement codes have no emitter anywhere; and a plain
    # register/version path emits no MODEL.VALIDATE either (that requires a validation record).
    for code in (*STILL_RESERVED_P7_CODES, "MODEL.VALIDATE"):
        assert _events(session, code) == 0


def _raise_audit(*_a: object, **_k: object) -> None:
    raise RuntimeError("audit capture failed")


def test_register_rolls_back_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.model.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    tenant = _tenant()
    with pytest.raises(RuntimeError):
        register_model(
            session, tenant_id=tenant, code="X", name="n", model_type="X", actor_id="dev"
        )
    session.rollback()
    assert (
        session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == tenant)
        ).scalar_one()
        == 0
    )


def test_model_version_is_append_only(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant)
    version = register_model_version(
        session,
        model=model,
        version_label="1.0.0",
        actor_id="dev",
        assumptions=["a"],
        limitations=["l"],
    )
    session.commit()
    for cls, row_id in (
        (ModelVersion, version.id),
        (
            ModelAssumption,
            session.execute(select(ModelAssumption.id)).scalars().first(),
        ),
        (ModelLimitation, session.execute(select(ModelLimitation.id)).scalars().first()),
    ):
        row = session.get(cls, row_id)
        # Mutate an arbitrary mapped column to trigger before_update.
        col = (
            "version_label"
            if cls is ModelVersion
            else ("assumption_text" if cls is ModelAssumption else "limitation_text")
        )
        setattr(row, col, "changed")
        with pytest.raises(AppendOnlyViolation):
            session.flush()
        session.rollback()
        row = session.get(cls, row_id)
        session.delete(row)
        with pytest.raises(AppendOnlyViolation):
            session.flush()
        session.rollback()


def test_model_head_is_mutable_ev(session: Session) -> None:
    # Positive contrast: model (EV) is NOT append-only — UPDATE succeeds (no trigger/guard).
    tenant = _tenant()
    model = _model(session, tenant)
    session.commit()
    fetched = session.get(Model, model.id)
    fetched.owner = "new.owner"
    fetched.validation_status = "IN_REVIEW"
    session.flush()  # no AppendOnlyViolation
    assert session.get(Model, model.id).owner == "new.owner"


def test_br3_inventory_before_use_gate(session: Session) -> None:
    tenant = _tenant()
    # A synthetic use of an unregistered model_version fails the BR-3/MG-02 gate.
    with pytest.raises(UnregisteredModelError):
        assert_registered_model_version(session, str(uuid.uuid4()))
    # A registered version passes.
    model = _model(session, tenant)
    version = register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    assert assert_registered_model_version(session, version.id).id == version.id


def test_br3_gate_is_tenant_scoped(session: Session) -> None:
    tenant_a = _tenant()
    model = _model(session, tenant_a)
    version = register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    with pytest.raises(UnregisteredModelError):
        assert_registered_model_version(session, version.id, tenant_id=_tenant())
    assert assert_registered_model_version(session, version.id, tenant_id=tenant_a) is not None


def test_ac11_tier1_unvalidated_model_registers_and_binds(session: Session) -> None:
    # AC-11: a Tier-1, UNVALIDATED model registers and a version binds with NO approval/validation
    # gate — proving tier/validation enforcement is NOT (accidentally) implemented at registration.
    # MG-1 edit (disclosed in the plan): register_model no longer accepts `tier` — the head
    # registers untiered and the tier arrives via the 2L verb; the binding assertion is unchanged.
    tenant = _tenant()
    model = _model(session, tenant, code="TIER1")
    assert model.tier is None  # every head registers UNTIERED (the TIER_1 fail-safe bound applies)
    assert model.validation_status == "UNVALIDATED"
    assign_model_tier(
        session,
        acting_tenant=tenant,
        model_id=model.id,
        materiality_rating="HIGH",
        complexity_rating="MEDIUM",
        rationale="AC-11 fixture: flagship-equivalent exposure",
        actor_id="validator-2l",
    )
    assert model.tier == "TIER_1"
    version = register_model_version(session, model=model, version_label="1.0.0", actor_id="dev")
    assert assert_registered_model_version(session, version.id).id == version.id


# ---------- MG-1 (OD-MG-1-A/B/C): the tier matrix + the 2L assignment verb ----------


def test_derive_model_tier_all_nine_cells() -> None:
    from irp_shared.model.models import derive_model_tier

    # The ratified house matrix (OD-MG-1-A — HOUSE POLICY): TIER_1 = HIGH materiality; TIER_2 =
    # MEDIUM materiality, or LOW materiality escalated by HIGH complexity; TIER_3 = the rest.
    expected = {
        ("HIGH", "HIGH"): "TIER_1",
        ("HIGH", "MEDIUM"): "TIER_1",
        ("HIGH", "LOW"): "TIER_1",
        ("MEDIUM", "HIGH"): "TIER_2",
        ("MEDIUM", "MEDIUM"): "TIER_2",
        ("MEDIUM", "LOW"): "TIER_2",
        ("LOW", "HIGH"): "TIER_2",
        ("LOW", "MEDIUM"): "TIER_3",
        ("LOW", "LOW"): "TIER_3",
    }
    for (m, c), tier in expected.items():
        assert derive_model_tier(m, c) == tier, (m, c)


def test_assign_model_tier_bumps_head_and_carries_the_ratings_in_the_event(
    session: Session,
) -> None:
    # The MODEL.TIER_ASSIGN payload is the RATINGS' ONLY durable home (OQ-MG-1-1 sub-fork (i):
    # no new columns, no migration) — so the payload-shape assertion is load-bearing, not
    # cosmetic (an MG-1 planning-verifier fold).
    tenant = _tenant()
    model = _model(session, tenant, code="TA1")
    rv_before = model.record_version
    assign_model_tier(
        session,
        acting_tenant=tenant,
        model_id=model.id,
        materiality_rating="MEDIUM",
        complexity_rating="LOW",
        rationale="moderate exposure; single consumer",
        actor_id="validator-2l",
    )
    assert model.tier == "TIER_2"
    assert model.record_version == rv_before + 1
    event = session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == MODEL_TIER_ASSIGN_EVENT,
            AuditEvent.entity_id == model.id,
        )
    ).scalar_one()
    assert event.before_value == {"tier": None}
    assert event.after_value == {
        "tier": "TIER_2",
        "materiality_rating": "MEDIUM",
        "complexity_rating": "LOW",
        "rationale": "moderate exposure; single consumer",
    }


def test_assign_model_tier_no_op_vs_rating_change_preserving_tier(session: Session) -> None:
    # The ratified no-op is IDENTICAL RATINGS. A rating flip that PRESERVES the derived tier
    # (MEDIUM×LOW -> LOW×HIGH, both TIER_2) must still emit — the payload is the ratings' only
    # home, so swallowing it would silently lose a governance judgment (caught at self-review).
    tenant = _tenant()
    model = _model(session, tenant, code="TA2")
    kw = dict(acting_tenant=tenant, model_id=model.id, actor_id="validator-2l")
    assign_model_tier(
        session, materiality_rating="MEDIUM", complexity_rating="LOW", rationale="r1", **kw
    )
    rv_after_first = model.record_version
    # identical ratings ⇒ NO-OP: no bump, no second event
    assign_model_tier(
        session, materiality_rating="MEDIUM", complexity_rating="LOW", rationale="r1-again", **kw
    )
    assert model.record_version == rv_after_first
    count = session.execute(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.event_type == MODEL_TIER_ASSIGN_EVENT, AuditEvent.entity_id == model.id)
    ).scalar_one()
    assert count == 1
    # changed ratings, SAME derived tier ⇒ event emitted, record_version NOT bumped (tier moved
    # nowhere), and the new payload carries the new ratings
    assign_model_tier(
        session, materiality_rating="LOW", complexity_rating="HIGH", rationale="re-rated", **kw
    )
    assert model.tier == "TIER_2" and model.record_version == rv_after_first
    count = session.execute(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.event_type == MODEL_TIER_ASSIGN_EVENT, AuditEvent.entity_id == model.id)
    ).scalar_one()
    assert count == 2


def test_assign_model_tier_refusals(session: Session) -> None:
    tenant = _tenant()
    model = _model(session, tenant, code="TA3")
    good = dict(
        acting_tenant=tenant,
        model_id=model.id,
        materiality_rating="HIGH",
        complexity_rating="LOW",
        rationale="x",
        actor_id="v",
    )
    with pytest.raises(ModelTierValueError, match="materiality_rating"):
        assign_model_tier(session, **{**good, "materiality_rating": "SEVERE"})
    with pytest.raises(ModelTierValueError, match="complexity_rating"):
        assign_model_tier(session, **{**good, "complexity_rating": "TIER_1"})
    with pytest.raises(ModelTierValueError, match="rationale"):
        assign_model_tier(session, **{**good, "rationale": "   "})
    with pytest.raises(ModelTierValueError, match="human"):
        assign_model_tier(session, **good, actor_type="agent")
    with pytest.raises(ModelNotVisible):  # cross-tenant / unknown head fails closed
        assign_model_tier(session, **{**good, "model_id": str(uuid.uuid4())})
    assert model.tier is None  # nothing stamped by any refusal
