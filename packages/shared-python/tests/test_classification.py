"""REF-1 classification unit tests — vocabulary guards, fail-closed resolvers, FR protocol, SoD.

Every guard here carries a NEGATIVE control: a test that the refusal FIRES, not merely that the
happy path passes (P5 — assert by evidence, and any by-absence assertion carries a positive control
that fails when the mechanism breaks).

Note on tiers: these run on the SQLite unit tier, which has NO RLS. That is precisely why the
binder's own-OR-SYSTEM predicates are written EXPLICITLY rather than delegated to the policy — a
resolver leaning on RLS would be green here and wrong on PostgreSQL. The tenancy floors and the
read-filter binds live in the PG tier (`test_classification_pg.py`), because the unit tier is
structurally blind to both.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from irp_shared.classification.models import (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    BASIS_NOT_APPLICABLE,
    BASIS_ULTIMATE_RISK,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    ClassificationAssignment,
    ClassificationNode,
)
from irp_shared.classification.service import (
    MAX_HIERARCHY_DEPTH,
    ClassificationActor,
    ClassificationNotVisible,
    ClassificationValueError,
    NoCurrentAssignment,
    capture_assignment,
    correct_assignment,
    create_node,
    create_scheme,
    resolve_ancestors,
    resolve_node,
    supersede_assignment,
)
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

TENANT = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT = "99999999-8888-7777-6666-555555555555"


def _actor(tenant: str = TENANT) -> ClassificationActor:
    return ClassificationActor(tenant_id=tenant, actor_id="data_steward_1")


def _isic(session: Session, actor: ClassificationActor):  # noqa: ANN202
    return create_scheme(
        session,
        actor=actor,
        scheme_family="ISIC",
        version_label="Rev. 5",
        name="ISIC Revision 5",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        authority="UNSD",
    )


# --------------------------------------------------------------------------------------------
# Actor canonicalization (the SSO-1 / API-2 standing rule)
# --------------------------------------------------------------------------------------------


def test_actor_canonicalizes_tenant_in_the_dataclass() -> None:
    """An uppercased/brace-wrapped UUID must canonicalize AT THE BOUNDARY, not at each use site."""
    messy = ClassificationActor(tenant_id="{" + TENANT.upper() + "}", actor_id="a")
    assert messy.acting_tenant == TENANT


def test_actor_refuses_a_non_uuid_tenant() -> None:
    with pytest.raises(ValueError):
        ClassificationActor(tenant_id="not-a-uuid", actor_id="a")


# --------------------------------------------------------------------------------------------
# dimension_kind <-> basis invariant — BOTH directions (the vacuity failure mode)
# --------------------------------------------------------------------------------------------


def test_country_of_risk_requires_a_real_basis(session: Session) -> None:
    """NEGATIVE CONTROL: the sentinel is refused on a dimension that carries a real convention."""
    actor = _actor()
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family="ISO_3166_1",
        version_label="2026",
        name="ISO 3166-1",
        dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
    )
    create_node(session, actor=actor, scheme_id=scheme.id, code="US", name="United States", level=1)
    with pytest.raises(ClassificationValueError, match="not admissible"):
        capture_assignment(
            session,
            actor=actor,
            entity_type="instrument",
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
            node_code="US",
            basis=BASIS_NOT_APPLICABLE,
        )


def test_sector_refuses_a_country_basis(session: Session) -> None:
    """The OTHER direction. Checking one arm only would let the discriminator go silently inert."""
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationValueError, match="not admissible"):
        capture_assignment(
            session,
            actor=actor,
            entity_type="instrument",
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code="C",
            basis=BASIS_ULTIMATE_RISK,
        )


def test_country_of_risk_accepts_each_declared_basis(session: Session) -> None:
    """POSITIVE control for the two refusals above — the admissible set is genuinely reachable."""
    actor = _actor()
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family="ISO_3166_1",
        version_label="2026",
        name="ISO 3166-1",
        dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
    )
    create_node(session, actor=actor, scheme_id=scheme.id, code="BR", name="Brazil", level=1)
    row = capture_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=str(uuid.uuid4()),
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
        node_code="BR",
        basis=BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    )
    assert row.basis == BASIS_IMMEDIATE_ISSUER_RESIDENCE


# --------------------------------------------------------------------------------------------
# Fail-closed vocabulary resolution — the typo that would become a concentration bucket
# --------------------------------------------------------------------------------------------


def test_capture_refuses_a_node_code_that_does_not_exist(session: Session) -> None:
    """Without this, a typo silently becomes its own concentration bucket in CON-1."""
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationNotVisible, match="does not exist"):
        capture_assignment(
            session,
            actor=actor,
            entity_type="instrument",
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code="CC",  # one keystroke off
        )


def test_capture_refuses_a_scheme_from_another_tenant(session: Session) -> None:
    """Cross-tenant fail-closed: visibility is own-OR-SYSTEM, asserted WITHOUT relying on RLS."""
    other = _actor(OTHER_TENANT)
    scheme = _isic(session, other)
    create_node(session, actor=other, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationNotVisible):
        capture_assignment(
            session,
            actor=_actor(),
            entity_type="instrument",
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code="C",
        )


def test_capture_refuses_a_scheme_serving_a_different_dimension(session: Session) -> None:
    actor = _actor()
    scheme = _isic(session, actor)  # SECTOR_INDUSTRY
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationValueError, match="serves dimension"):
        capture_assignment(
            session,
            actor=actor,
            entity_type="instrument",
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
            node_code="C",
            basis=BASIS_IMMEDIATE_ISSUER_RESIDENCE,
        )


def test_capture_refuses_an_unknown_entity_type(session: Session) -> None:
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationValueError, match="entity_type"):
        capture_assignment(
            session,
            actor=actor,
            entity_type="issuer",  # admissible LATER by value; not written in v1
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code="C",
        )


# --------------------------------------------------------------------------------------------
# Adjacency guards — an unguarded adjacency admits a cycle that would hang the ancestor walk
# --------------------------------------------------------------------------------------------


def test_child_level_must_be_strictly_below_its_parent(session: Session) -> None:
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationValueError, match="strictly greater"):
        create_node(
            session,
            actor=actor,
            scheme_id=scheme.id,
            code="C10",
            name="Food",
            level=1,  # same level as its parent
            parent_code="C",
        )


def test_root_node_must_be_level_one(session: Session) -> None:
    actor = _actor()
    scheme = _isic(session, actor)
    with pytest.raises(ClassificationValueError, match="root node must be level 1"):
        create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Mfg", level=2)


def test_parent_must_exist_in_the_same_scheme(session: Session) -> None:
    actor = _actor()
    isic = _isic(session, actor)
    nace = create_scheme(
        session,
        actor=actor,
        scheme_family="NACE",
        version_label="Rev. 2.1",
        name="NACE Rev 2.1",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
    )
    create_node(session, actor=actor, scheme_id=nace.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(ClassificationNotVisible):
        create_node(
            session,
            actor=actor,
            scheme_id=isic.id,
            code="C10",
            name="Food",
            level=2,
            parent_code="C",  # exists in NACE, not in ISIC
        )


def test_ancestor_walk_returns_the_chain_nearest_first(session: Session) -> None:
    """POSITIVE control: the walk CON-1 consumes for its per-sector bucket actually resolves."""
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    create_node(
        session, actor=actor, scheme_id=scheme.id, code="C10", name="Food", level=2, parent_code="C"
    )
    leaf = create_node(
        session,
        actor=actor,
        scheme_id=scheme.id,
        code="C101",
        name="Meat",
        level=3,
        parent_code="C10",
    )
    chain = resolve_ancestors(session, node=leaf, acting_tenant=TENANT)
    assert [n.code for n in chain] == ["C10", "C"]
    # The level-1 ancestor IS the "sector" a concentration bucket groups by.
    assert chain[-1].level == 1


def test_ancestor_walk_is_bounded_against_a_cycle(session: Session) -> None:
    """NEGATIVE control: a cycle forced directly into the table terminates instead of hanging.

    The binder refuses to CREATE a cycle, so this mutates the rows behind the binder's back — the
    only way to prove the read-path ceiling is real rather than decorative.
    """
    actor = _actor()
    scheme = _isic(session, actor)
    a = create_node(session, actor=actor, scheme_id=scheme.id, code="A", name="A", level=1)
    b = create_node(
        session, actor=actor, scheme_id=scheme.id, code="B", name="B", level=2, parent_code="A"
    )
    a.parent_node_id = b.id  # forced cycle A -> B -> A
    session.flush()
    with pytest.raises(ClassificationValueError, match="cycle|depth exceeded"):
        resolve_ancestors(session, node=b, acting_tenant=TENANT)


def test_hierarchy_depth_ceiling_is_declared_and_finite() -> None:
    assert isinstance(MAX_HIERARCHY_DEPTH, int)
    assert 0 < MAX_HIERARCHY_DEPTH < 100


# --------------------------------------------------------------------------------------------
# The FR protocol — the reason the assignment is not an EV column
# --------------------------------------------------------------------------------------------


def test_supersede_closes_the_prior_version_without_mutating_its_content(session: Session) -> None:
    """THE slice's load-bearing property: a reclassification leaves the prior version byte-stable
    on every content column, so a snapshot that pinned it still verifies."""
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    create_node(session, actor=actor, scheme_id=scheme.id, code="J", name="Information", level=1)
    entity = str(uuid.uuid4())
    first = capture_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=entity,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="C",
    )
    first_id, first_code, first_version = first.id, first.node_code, first.record_version

    second = supersede_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=entity,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="J",
    )
    session.flush()
    prior = session.get(ClassificationAssignment, first_id)
    assert prior is not None
    # Content untouched; ONLY the valid axis moved.
    assert prior.node_code == first_code
    assert prior.record_version == first_version
    assert prior.valid_to is not None
    assert prior.system_to is None  # a supersede is NOT a correction
    # The new open version links back and is the only open row.
    assert second.supersedes_id == first_id
    assert second.record_version == first_version + 1
    assert second.valid_to is None


def test_capture_refuses_a_second_open_assignment(session: Session) -> None:
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    entity = str(uuid.uuid4())
    kwargs = {
        "entity_type": "instrument",
        "entity_id": entity,
        "scheme_id": scheme.id,
        "dimension_kind": DIMENSION_KIND_SECTOR_INDUSTRY,
        "node_code": "C",
    }
    capture_assignment(session, actor=actor, **kwargs)
    with pytest.raises(ClassificationValueError, match="already exists"):
        capture_assignment(session, actor=actor, **kwargs)


def test_supersede_without_an_open_row_refuses(session: Session) -> None:
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    with pytest.raises(NoCurrentAssignment):
        supersede_assignment(
            session,
            actor=actor,
            entity_type="instrument",
            entity_id=str(uuid.uuid4()),
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code="C",
        )


def test_correction_closes_the_system_axis_and_reproduces_the_valid_interval(
    session: Session,
) -> None:
    """A correction says the capture was WRONG — distinct from a supersede on both axes."""
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    create_node(session, actor=actor, scheme_id=scheme.id, code="J", name="Information", level=1)
    entity = str(uuid.uuid4())
    original = capture_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=entity,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="C",
    )
    original_id, original_valid_from = original.id, original.valid_from
    corrected = correct_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=entity,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="J",
        restatement_reason="vendor sent the wrong code",
    )
    session.flush()
    prior = session.get(ClassificationAssignment, original_id)
    assert prior is not None
    assert prior.system_to is not None  # SYSTEM axis closed, not the valid axis
    assert prior.valid_to is None
    assert corrected.valid_from == original_valid_from  # interval reproduced, not restarted
    assert corrected.restatement_reason == "vendor sent the wrong code"


def test_correction_requires_a_restatement_reason(session: Session) -> None:
    """TR-08: a restatement without a stated reason is refused."""
    actor = _actor()
    scheme = _isic(session, actor)
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    entity = str(uuid.uuid4())
    capture_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=entity,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="C",
    )
    with pytest.raises(ClassificationValueError, match="restatement_reason"):
        correct_assignment(
            session,
            actor=actor,
            entity_type="instrument",
            entity_id=entity,
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
            node_code="C",
            restatement_reason="   ",
        )


# --------------------------------------------------------------------------------------------
# Node-grain tenant override (OQ-REF-1-11)
# --------------------------------------------------------------------------------------------


def test_tenant_node_shadows_the_system_node_of_the_same_code(session: Session) -> None:
    """Node-grain override: a tenant row wins over the SYSTEM row for the same (scheme, code),
    and precedence is decided in the APPLICATION layer — never by the RLS policy (AD-013-R1)."""
    system_actor = _actor(SYSTEM_TENANT_ID)
    scheme = _isic(session, system_actor)
    create_node(
        session, actor=system_actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1
    )
    # The tenant shadows ONE node against the SYSTEM parent — no subtree duplication required.
    now = datetime.now(UTC)
    tenant_node = ClassificationNode(
        tenant_id=TENANT,
        valid_from=now,
        scheme_id=scheme.id,
        code="C",
        name="Manufacturing (house definition)",
        level=1,
        record_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(tenant_node)
    session.flush()

    chosen = resolve_node(session, scheme_id=scheme.id, code="C", acting_tenant=TENANT)
    assert chosen.tenant_id == TENANT
    assert chosen.name == "Manufacturing (house definition)"
    # POSITIVE control: a tenant with no override still resolves the SYSTEM row.
    fallback = resolve_node(session, scheme_id=scheme.id, code="C", acting_tenant=OTHER_TENANT)
    assert fallback.tenant_id == SYSTEM_TENANT_ID
