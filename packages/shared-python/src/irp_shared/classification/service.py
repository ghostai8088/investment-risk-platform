"""Classification binder — the governed vocabulary + the FR assignment capture rail (REF-1).

Three verbs on the vocabulary (``create_scheme`` / ``create_node`` / ``resolve_*``) and the FR
capture protocol on assignments (``capture`` / ``supersede`` / ``correct`` / ``reconstruct``), on
the ``proxy_mapping`` template: server-stamped tenancy, a MANUAL provenance root, one ORIGIN
lineage edge per new version, a fail-closed co-transactional DQ gate, per-op audit grain, ONE
``now`` per op, CLOSE-FIRST ordering on a re-version, and a prior version's CONTENT never mutated.

**Audit reuses ``REFERENCE.*``** with new ``entity_type`` values (no R-07 audit mint) — the
six-entity reference precedent, where all four verbs are already parameterized by a caller-supplied
``entity_type``.

**Two fail-closed resolvers, both required (OQ-REF-1-20).** The assignment carries ``node_code`` as
denormalized text with NO database FK, because PostgreSQL referential-integrity checks bypass RLS —
an FK would let a tenant bind a node its own ``USING`` cannot see. So the binder resolves
``scheme_id`` own-OR-SYSTEM and then ``(scheme_id, node_code)`` against ``classification_node``,
both refusing before any write. Without that check a typo silently becomes its own concentration
bucket in a governed number one slice later.

**The vocabulary guards are not optional.** ``classification_node`` is an adjacency table, and an
adjacency without a cycle guard admits a cycle that would hang :func:`resolve_ancestors`. The
binder enforces cycle-freedom, same-scheme parentage, and level monotonicity, each with a negative
control.

**Sector is an ANCESTOR, not a second dimension (OQ-REF-1-1).** A vendor delivers a leaf code;
CON-1's per-sector bucket is that node's level-1 ancestor. :func:`resolve_ancestors` is the bounded,
cycle-safe walk it consumes — shipped here, in the slice that owns the vocabulary, because the very
next slice needs it and a hierarchy nobody can walk is not a hierarchy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CORRECT, ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.service import record_event
from irp_shared.classification.models import (
    ASSIGNMENT_ENTITY_TYPES,
    BASIS_BY_DIMENSION_KIND,
    BASIS_NOT_APPLICABLE,
    DIMENSION_KINDS,
    ClassificationAssignment,
    ClassificationNode,
    ClassificationScheme,
)
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.lineage.models import DataSource
from irp_shared.lineage.service import EDGE_KIND_ORIGIN, record_lineage, register_data_source
from irp_shared.reference.events import (
    REFERENCE_CORRECTION_EVENT,
    REFERENCE_CREATE_EVENT,
    REFERENCE_UPDATE_EVENT,
)

#: Audit ``entity_type`` values (no new audit CODE — the REFERENCE.* block is reused).
ENTITY_CLASSIFICATION_SCHEME = "classification_scheme"
ENTITY_CLASSIFICATION_NODE = "classification_node"
ENTITY_CLASSIFICATION_ASSIGNMENT = "classification_assignment"

SOURCE_MODULE = "classification"

MANUAL_SOURCE_CODE = "MANUAL_CLASSIFICATION"
MANUAL_SOURCE_NAME = "Manual/vendor classification capture"
MANUAL_SOURCE_TYPE = "MANUAL"

_REQUIRED_RULE_CODE = "CLASSIFICATION_ASSIGNMENT_REQUIRED"

#: Hard ceiling on the ancestor walk. A cycle is refused at write time, but a bounded walk is the
#: second line of defence — a runaway traversal on a governed read path is the failure this makes
#: impossible rather than unlikely (the CC-2 compounding-kernel ceiling precedent).
MAX_HIERARCHY_DEPTH = 16


def canonical_tenant_id(tenant_id: str) -> str:
    """Canonical UUID form. Mirrors ``db.tenant._canonical_tenant`` (private): an uppercased or
    brace-wrapped UUID would filter against no ``tenant_id`` and read silently empty — the SSO-1
    standing rule. A non-UUID raises (fail-loud; there is no legitimate non-UUID tenant)."""
    return str(uuid.UUID(str(tenant_id)))


@dataclass(frozen=True)
class ClassificationActor:
    """Acting principal. ``tenant_id`` is canonicalized HERE, in the actor dataclass — the API-2
    lesson (any path arming a tenant GUC or filtering on tenancy canonicalizes at the boundary,
    never at each use site)."""

    tenant_id: str
    actor_id: str
    actor_type: str = "HUMAN"
    correlation_id: str | None = None
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    _canonical: str = field(init=False, repr=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_canonical", canonical_tenant_id(self.tenant_id))

    @property
    def acting_tenant(self) -> str:
        return self._canonical


class ClassificationValueError(Exception):
    """Binder-side validation refusal (→ 422). Raised BEFORE any write."""


class ClassificationNotVisible(Exception):
    """A referenced scheme/node is not visible to the acting tenant (→ fail-closed refusal)."""


class NoCurrentAssignment(Exception):
    """No OPEN assignment exists for the requested logical key."""


# --------------------------------------------------------------------------------------------
# Validation — vocabularies and the dimension_kind <-> basis invariant
# --------------------------------------------------------------------------------------------


def validate_dimension_kind(dimension_kind: str) -> None:
    if dimension_kind not in DIMENSION_KINDS:
        raise ClassificationValueError(
            f"dimension_kind must be one of {DIMENSION_KINDS} (got {dimension_kind!r})"
        )


def validate_entity_type(entity_type: str) -> None:
    if entity_type not in ASSIGNMENT_ENTITY_TYPES:
        raise ClassificationValueError(
            f"entity_type must be one of {ASSIGNMENT_ENTITY_TYPES} (got {entity_type!r})"
        )


def validate_basis(dimension_kind: str, basis: str) -> None:
    """Enforce the kind↔basis invariant in BOTH directions.

    A country-of-risk row may NOT carry the ``NOT_APPLICABLE`` sentinel, and a sector row may carry
    ONLY the sentinel. Checking one direction would let the discriminator go silently inert, which
    defeats the entire reason it is NOT NULL: stopping two incomparable conventions being mixed
    inside one concentration number. An unlisted kind refuses rather than passing vacuously.
    """
    admissible = BASIS_BY_DIMENSION_KIND.get(dimension_kind)
    if admissible is None:
        raise ClassificationValueError(
            f"no basis policy declared for dimension_kind {dimension_kind!r} — refusing"
        )
    if basis not in admissible:
        raise ClassificationValueError(
            f"basis {basis!r} is not admissible for dimension_kind {dimension_kind!r} "
            f"(admissible: {admissible})"
        )


# --------------------------------------------------------------------------------------------
# Fail-closed resolvers (own-OR-SYSTEM visibility, explicit — correct on SQLite too, where there
# is no RLS at all, so the predicate cannot be delegated to the policy)
# --------------------------------------------------------------------------------------------


def resolve_scheme(session: Session, *, scheme_id: str, acting_tenant: str) -> ClassificationScheme:
    """Resolve a scheme visible to the acting tenant (own row OR the SYSTEM global), fail-closed.

    The explicit ``(own OR SYSTEM)`` predicate mirrors ``resolve_currency``: RLS delivers this on
    PostgreSQL, but the unit tier has no RLS, so a resolver that leaned on the policy would be
    green in tests and wrong nowhere visible.
    """
    tenant = canonical_tenant_id(acting_tenant)
    row = session.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.id == str(scheme_id),
            ClassificationScheme.tenant_id.in_((tenant, SYSTEM_TENANT_ID)),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ClassificationNotVisible(f"classification_scheme {scheme_id!r} is not visible")
    return row


def resolve_node(
    session: Session, *, scheme_id: str, code: str, acting_tenant: str
) -> ClassificationNode:
    """Resolve ``(scheme, code)`` to a node visible to the acting tenant; tenant override WINS.

    Node-grain override (OQ-REF-1-11): a tenant's own row for the same ``(scheme_id, code)`` shadows
    the SYSTEM row. Precedence is decided here in the application layer, never by the RLS policy —
    the AD-013-R1 rule.
    """
    tenant = canonical_tenant_id(acting_tenant)
    rows = (
        session.execute(
            select(ClassificationNode).where(
                ClassificationNode.scheme_id == str(scheme_id),
                ClassificationNode.code == code,
                ClassificationNode.tenant_id.in_((tenant, SYSTEM_TENANT_ID)),
            )
        )
        .scalars()
        .all()
    )
    own = [r for r in rows if r.tenant_id == tenant]
    chosen = own[0] if own else (rows[0] if rows else None)
    if chosen is None:
        raise ClassificationNotVisible(
            f"classification_node {code!r} does not exist in scheme {scheme_id!r} "
            f"(or is not visible to the acting tenant) — refusing the assignment"
        )
    return chosen


def resolve_ancestors(
    session: Session, *, node: ClassificationNode, acting_tenant: str
) -> list[ClassificationNode]:
    """Walk parent links to the scheme root, nearest parent first. Bounded and cycle-safe.

    CON-1's per-sector bucket is an ancestor of the assigned leaf, so this is the read the next
    slice consumes. Two independent protections: a ``seen`` set (a cycle terminates instead of
    hanging even if one somehow reached the table) and :data:`MAX_HIERARCHY_DEPTH`.
    """
    tenant = canonical_tenant_id(acting_tenant)
    out: list[ClassificationNode] = []
    seen: set[str] = {str(node.id)}
    current = node
    while current.parent_node_id is not None:
        if len(out) >= MAX_HIERARCHY_DEPTH:
            raise ClassificationValueError(
                f"hierarchy depth exceeded {MAX_HIERARCHY_DEPTH} walking ancestors of "
                f"node {node.code!r} — refusing (suspected cycle or malformed scheme)"
            )
        parent = session.execute(
            select(ClassificationNode).where(
                ClassificationNode.id == str(current.parent_node_id),
                ClassificationNode.tenant_id.in_((tenant, SYSTEM_TENANT_ID)),
            )
        ).scalar_one_or_none()
        if parent is None:
            # FAIL-CLOSED (CON-1 OQ-CON-1-28; previously a silent ``break``): a short chain would
            # let "the level-1 ancestor" silently be a NEARER node — a concentration bucket on the
            # wrong sector with verify green (the Part 0 fact 11 false-positive-verify harm). An
            # invisible parent is a refusal, never a truncation.
            raise ClassificationNotVisible(
                f"parent node {current.parent_node_id} of {current.code!r} is not visible to "
                f"{tenant} — refusing the truncated ancestor walk (a short chain mis-buckets)"
            )
        if str(parent.id) in seen:
            raise ClassificationValueError(
                f"cycle detected walking ancestors of node {node.code!r} — refusing"
            )
        seen.add(str(parent.id))
        out.append(parent)
        current = parent
    return out


# --------------------------------------------------------------------------------------------
# Provenance, DQ, audit
# --------------------------------------------------------------------------------------------


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Resolve-or-register the acting tenant's classification provenance root (race-safe)."""
    tenant = canonical_tenant_id(tenant_id)
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == tenant, DataSource.code == MANUAL_SOURCE_CODE
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=tenant,
            code=MANUAL_SOURCE_CODE,
            name=MANUAL_SOURCE_NAME,
            source_type=MANUAL_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def _origin_edge(
    session: Session,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    actor: ClassificationActor,
) -> None:
    source = ensure_manual_source(session, tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=entity_type,
        target_entity_id=entity_id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _ensure_required_rule(
    session: Session, *, tenant_id: str, actor: ClassificationActor
) -> DataQualityRule:
    """Resolve-or-register the per-tenant required-fields rule (race-safe: two concurrent first
    callers both SELECT-miss, and the loser re-resolves the peer instead of aborting the unit)."""
    tenant = canonical_tenant_id(tenant_id)
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataQualityRule).where(
                DataQualityRule.tenant_id == tenant,
                DataQualityRule.code == _REQUIRED_RULE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_dq_rule(
            session,
            tenant_id=tenant,
            code=_REQUIRED_RULE_CODE,
            name="classification_assignment required fields present",
            rule_type=RULE_TYPE_NOT_NULL,
            actor_id=actor.actor_id,
            params={"column": "present"},
            target_entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_dq_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: ClassificationActor,
    row: ClassificationAssignment,
) -> None:
    """Fail-closed, co-transactional required-field gate (``DATA.VALIDATE``).

    NO economic RANGE leg — a classification code has no natural numeric bound (the
    ``proxy_mapping`` reasoning). Vocabulary and the kind↔basis invariant are binder guards that
    already ran BEFORE this gate; existence of the node is the fail-closed resolver above.
    """
    missing = any(
        getattr(row, f) is None
        for f in ("entity_type", "entity_id", "scheme_id", "dimension_kind", "node_code", "basis")
    )
    rule = _ensure_required_rule(session, tenant_id=acting_tenant, actor=actor)
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


def _emit(
    session: Session,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: ClassificationActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    record_event(
        session,
        event_type=event_type,
        tenant_id=tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        justification=justification,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
        event_time=now,
    )


def _assignment_summary(row: ClassificationAssignment) -> dict[str, Any]:
    return {
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "scheme_id": str(row.scheme_id),
        "dimension_kind": row.dimension_kind,
        "node_code": row.node_code,
        "basis": row.basis,
        "record_version": row.record_version,
    }


# --------------------------------------------------------------------------------------------
# Vocabulary write verbs (EV)
# --------------------------------------------------------------------------------------------


def create_scheme(
    session: Session,
    *,
    actor: ClassificationActor,
    scheme_family: str,
    version_label: str,
    name: str,
    dimension_kind: str,
    authority: str | None = None,
) -> ClassificationScheme:
    """Create a scheme AT A VERSION. A revision is a NEW row, never an in-place supersede."""
    validate_dimension_kind(dimension_kind)
    now = utcnow()
    row = ClassificationScheme(
        tenant_id=actor.acting_tenant,
        valid_from=now,
        scheme_family=scheme_family,
        version_label=version_label,
        name=name,
        authority=authority,
        dimension_kind=dimension_kind,
        is_active=True,
        record_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_SCHEME,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_SCHEME,
        entity_id=row.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value={
            "scheme_family": scheme_family,
            "version_label": version_label,
            "name": name,
            "dimension_kind": dimension_kind,
            "authority": authority,
        },
        actor=actor,
        now=now,
    )
    return row


def create_node(
    session: Session,
    *,
    actor: ClassificationActor,
    scheme_id: str,
    code: str,
    name: str,
    level: int,
    parent_code: str | None = None,
    description: str | None = None,
) -> ClassificationNode:
    """Create a node under a scheme, with all three adjacency guards enforced before the write.

    The parent is addressed by CODE, resolved through the same override-aware resolver the
    assignment path uses — so a tenant's shadowed parent and the SYSTEM parent live in one key
    space rather than two (the OQ-REF-1-11 consistency the draft left contradictory).
    """
    scheme = resolve_scheme(session, scheme_id=scheme_id, acting_tenant=actor.acting_tenant)
    if level < 1:
        raise ClassificationValueError(f"level must be >= 1 (got {level})")
    # CON-1 (OQ-CON-1-23): node codes share ENT-069's ``bucket_code`` TEXT namespace with the
    # dunder sentinels (__UNCLASSIFIED__/__UNCLASSIFIABLE__/__SUMMARY__) — a vendor node literally
    # coded like a sentinel would collide with a residual bucket. Closed at BOTH ends: the
    # sentinels are dunder-delimited, and capture refuses the dunder shape.
    if code.startswith("__") and code.endswith("__"):
        raise ClassificationValueError(
            f"node code {code!r} uses the reserved dunder sentinel shape __*__ — refused (the "
            "concentration bucket_code namespace guard)"
        )

    parent: ClassificationNode | None = None
    if parent_code is not None:
        parent = resolve_node(
            session, scheme_id=str(scheme.id), code=parent_code, acting_tenant=actor.acting_tenant
        )
        # Same-scheme parentage: the resolver already scopes by scheme_id, so this asserts the
        # invariant rather than discovering it — kept explicit so a future resolver change cannot
        # silently drop it.
        if str(parent.scheme_id) != str(scheme.id):
            raise ClassificationValueError(
                f"parent {parent_code!r} belongs to a different scheme — refusing"
            )
        # Level monotonicity: a child must sit strictly below its parent.
        if level <= parent.level:
            raise ClassificationValueError(
                f"level {level} must be strictly greater than parent level {parent.level} "
                f"(node {code!r} under {parent_code!r}) — refusing"
            )
        # Cycle guard: a node may not be its own ancestor. On create the node has no id yet, so the
        # reachable case is a parent chain that already loops; walking it is bounded and raises.
        resolve_ancestors(session, node=parent, acting_tenant=actor.acting_tenant)
    elif level != 1:
        raise ClassificationValueError(
            f"a root node must be level 1 (got {level} for {code!r} with no parent) — refusing"
        )

    now = utcnow()
    row = ClassificationNode(
        tenant_id=actor.acting_tenant,
        valid_from=now,
        scheme_id=str(scheme.id),
        code=code,
        name=name,
        level=level,
        parent_node_id=str(parent.id) if parent is not None else None,
        description=description,
        record_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_NODE,
        entity_id=row.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value={
            "scheme_id": str(scheme.id),
            "code": code,
            "name": name,
            "level": level,
            "parent_code": parent_code,
        },
        actor=actor,
        now=now,
    )
    return row


# --------------------------------------------------------------------------------------------
# Assignment capture protocol (FR bitemporal)
# --------------------------------------------------------------------------------------------


def _current_open(
    session: Session,
    *,
    acting_tenant: str,
    entity_type: str,
    entity_id: str,
    scheme_id: str,
    dimension_kind: str,
) -> ClassificationAssignment | None:
    return session.execute(
        select(ClassificationAssignment).where(
            ClassificationAssignment.tenant_id == canonical_tenant_id(acting_tenant),
            ClassificationAssignment.entity_type == entity_type,
            ClassificationAssignment.entity_id == str(entity_id),
            ClassificationAssignment.scheme_id == str(scheme_id),
            ClassificationAssignment.dimension_kind == dimension_kind,
            ClassificationAssignment.valid_to.is_(None),
            ClassificationAssignment.system_to.is_(None),
        )
    ).scalar_one_or_none()


def capture_assignment(
    session: Session,
    *,
    actor: ClassificationActor,
    entity_type: str,
    entity_id: str,
    scheme_id: str,
    dimension_kind: str,
    node_code: str,
    basis: str = BASIS_NOT_APPLICABLE,
    asserted_ancestor_code: str | None = None,
) -> ClassificationAssignment:
    """Capture a NEW open assignment. Refuses if one is already open for the logical key.

    ``asserted_ancestor_code`` (OQ-REF-1-1, PAID at CON-1 as OQ-CON-1-27): when the vendor row
    carries BOTH the leaf and its claimed ancestor (a sector column alongside an industry column),
    the caller passes the ancestor code and capture REFUSES fail-closed — naming both codes — if
    the resolved leaf's ancestor chain does not contain it. A contradictory vendor pair must never
    become a stored state CON-1 buckets on."""
    validate_entity_type(entity_type)
    validate_dimension_kind(dimension_kind)
    validate_basis(dimension_kind, basis)

    scheme = resolve_scheme(session, scheme_id=scheme_id, acting_tenant=actor.acting_tenant)
    if scheme.dimension_kind != dimension_kind:
        raise ClassificationValueError(
            f"scheme {scheme.scheme_family} {scheme.version_label} serves dimension "
            f"{scheme.dimension_kind!r}, not {dimension_kind!r} — refusing"
        )
    # Fail-closed vocabulary resolution BEFORE any write: a code that does not exist in the scheme
    # would otherwise become its own concentration bucket in CON-1.
    node = resolve_node(
        session, scheme_id=str(scheme.id), code=node_code, acting_tenant=actor.acting_tenant
    )
    if asserted_ancestor_code is not None:
        chain = resolve_ancestors(session, node=node, acting_tenant=actor.acting_tenant)
        chain_codes = {n.code for n in chain}
        if asserted_ancestor_code not in chain_codes:
            raise ClassificationValueError(
                f"vendor assertion contradiction: node {node_code!r} does not descend from the "
                f"asserted ancestor {asserted_ancestor_code!r} (its chain is "
                f"{sorted(chain_codes) or ['<root>']}) — refused fail-closed (OQ-REF-1-1)"
            )

    existing = _current_open(
        session,
        acting_tenant=actor.acting_tenant,
        entity_type=entity_type,
        entity_id=entity_id,
        scheme_id=str(scheme.id),
        dimension_kind=dimension_kind,
    )
    if existing is not None:
        raise ClassificationValueError(
            f"an open assignment already exists for {entity_type} {entity_id} on "
            f"{dimension_kind} in this scheme — use supersede_assignment"
        )

    now = utcnow()
    row = ClassificationAssignment(
        tenant_id=actor.acting_tenant,
        valid_from=now,
        system_from=now,
        entity_type=entity_type,
        entity_id=str(entity_id),
        scheme_id=str(scheme.id),
        dimension_kind=dimension_kind,
        node_code=node_code,
        basis=basis,
        record_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    _run_dq_gate(session, acting_tenant=actor.acting_tenant, actor=actor, row=row)
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        entity_id=row.id,
        event_type=REFERENCE_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_assignment_summary(row),
        actor=actor,
        now=now,
    )
    return row


def supersede_assignment(
    session: Session,
    *,
    actor: ClassificationActor,
    entity_type: str,
    entity_id: str,
    scheme_id: str,
    dimension_kind: str,
    node_code: str,
    basis: str = BASIS_NOT_APPLICABLE,
) -> ClassificationAssignment:
    """Reclassify: close the open version on the VALID axis and open a new one. CLOSE FIRST.

    This is the operation the FR choice exists for. Closing on ``valid_to`` (not ``system_to``)
    leaves every prior version byte-stable, so a snapshot that pinned the old row still verifies —
    an EV in-place amend would have flipped ``verify_snapshot`` to ``ok=False`` on every historical
    concentration run, visibly, with no remedy.
    """
    validate_entity_type(entity_type)
    validate_dimension_kind(dimension_kind)
    validate_basis(dimension_kind, basis)
    scheme = resolve_scheme(session, scheme_id=scheme_id, acting_tenant=actor.acting_tenant)
    resolve_node(
        session, scheme_id=str(scheme.id), code=node_code, acting_tenant=actor.acting_tenant
    )

    current = _current_open(
        session,
        acting_tenant=actor.acting_tenant,
        entity_type=entity_type,
        entity_id=entity_id,
        scheme_id=str(scheme.id),
        dimension_kind=dimension_kind,
    )
    if current is None:
        raise NoCurrentAssignment(
            f"no open assignment for {entity_type} {entity_id} on {dimension_kind} — "
            f"use capture_assignment"
        )

    now = utcnow()  # ONE now per op
    before = _assignment_summary(current)
    current.valid_to = now  # CLOSE FIRST — content untouched
    current.updated_at = now
    session.flush()

    new = ClassificationAssignment(
        tenant_id=actor.acting_tenant,
        valid_from=now,
        system_from=now,
        entity_type=entity_type,
        entity_id=str(entity_id),
        scheme_id=str(scheme.id),
        dimension_kind=dimension_kind,
        node_code=node_code,
        basis=basis,
        supersedes_id=str(current.id),
        record_version=current.record_version + 1,
        created_at=now,
        updated_at=now,
    )
    session.add(new)
    session.flush()
    _run_dq_gate(session, acting_tenant=actor.acting_tenant, actor=actor, row=new)
    _origin_edge(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        entity_id=new.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        entity_id=new.id,
        event_type=REFERENCE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value=_assignment_summary(new),
        actor=actor,
        now=now,
    )
    return new


def correct_assignment(
    session: Session,
    *,
    actor: ClassificationActor,
    entity_type: str,
    entity_id: str,
    scheme_id: str,
    dimension_kind: str,
    node_code: str,
    restatement_reason: str,
    basis: str = BASIS_NOT_APPLICABLE,
) -> ClassificationAssignment:
    """As-known restatement (TR-08): the previous capture was WRONG, not superseded.

    Closes on the SYSTEM axis — the correction rewrites what we believe we always knew, so the
    valid-time interval is reproduced on the new row.
    """
    validate_entity_type(entity_type)
    validate_dimension_kind(dimension_kind)
    validate_basis(dimension_kind, basis)
    if not restatement_reason or not restatement_reason.strip():
        raise ClassificationValueError("restatement_reason is required on a correction (TR-08)")
    scheme = resolve_scheme(session, scheme_id=scheme_id, acting_tenant=actor.acting_tenant)
    resolve_node(
        session, scheme_id=str(scheme.id), code=node_code, acting_tenant=actor.acting_tenant
    )

    current = _current_open(
        session,
        acting_tenant=actor.acting_tenant,
        entity_type=entity_type,
        entity_id=entity_id,
        scheme_id=str(scheme.id),
        dimension_kind=dimension_kind,
    )
    if current is None:
        raise NoCurrentAssignment(
            f"no open assignment to correct for {entity_type} {entity_id} on {dimension_kind}"
        )

    now = utcnow()
    before = _assignment_summary(current)
    current.system_to = now  # CLOSE FIRST on the SYSTEM axis; content untouched
    current.updated_at = now
    session.flush()

    corrected = ClassificationAssignment(
        tenant_id=actor.acting_tenant,
        valid_from=current.valid_from,  # the valid interval is reproduced, not restarted
        valid_to=current.valid_to,
        system_from=now,
        entity_type=entity_type,
        entity_id=str(entity_id),
        scheme_id=str(scheme.id),
        dimension_kind=dimension_kind,
        node_code=node_code,
        basis=basis,
        restatement_reason=restatement_reason,
        supersedes_id=str(current.id),
        record_version=current.record_version + 1,
        created_at=now,
        updated_at=now,
    )
    session.add(corrected)
    session.flush()
    _run_dq_gate(session, acting_tenant=actor.acting_tenant, actor=actor, row=corrected)
    _origin_edge(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        entity_id=corrected.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_CLASSIFICATION_ASSIGNMENT,
        entity_id=corrected.id,
        event_type=REFERENCE_CORRECTION_EVENT,
        action=ACTION_CORRECT,
        before_value=before,
        after_value=_assignment_summary(corrected),
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return corrected


# --- The read verbs (LQ-1: REF-1's gap PAID, not copied) ---
#
# REF-1 shipped capture/supersede/correct and stopped. Every consumer since has had to hand-roll a
# select over ``valid_to IS NULL AND system_to IS NULL``, which is how a bitemporal table quietly
# grows N slightly-different notions of "current". LQ-1 needs both a list (the read surface, Rule 7)
# and an as-of reconstruction (the governed binder pins heads, and OQ-LQ-1-9 ratified a staleness
# refusal that has to ASK how old a head is). Adding them here rather than in ``liquidity/`` keeps
# one definition of current-head for every dimension kind.


def list_assignments(
    session: Session,
    *,
    acting_tenant: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    scheme_id: str | None = None,
    dimension_kind: str | None = None,
    known_at: datetime | None = None,
) -> list[ClassificationAssignment]:
    """Current-head assignments for the acting tenant, narrowed by any supplied filter.

    ``known_at`` reconstructs the AS-KNOWN state at that instant (the SYSTEM axis) rather than
    today's heads — ``None`` means "as known now". The parameter is named ``known_at`` and not
    ``as_of`` deliberately: it moves ONE axis, and the review found that the earlier name invited
    exactly the wrong reading.

    **The valid-axis filter differs by branch, and that is the point.** With ``known_at=None`` a
    head is ``valid_to IS NULL``. With ``known_at`` supplied, forcing ``valid_to IS NULL`` would
    return SILENT EMPTY for every entity superseded since — the row that was open at
    ``known_at`` has a closed valid axis TODAY, so the natural-looking filter asks a question about
    now while claiming to ask one about then. The as-known branch therefore reconstructs the valid
    interval as it stood at ``known_at``.

    Point-in-time on the valid axis with a full logical key is ``reconstruct_assignment_as_of``.
    """
    tenant = canonical_tenant_id(acting_tenant)
    stmt = select(ClassificationAssignment).where(ClassificationAssignment.tenant_id == tenant)

    if entity_type is not None:
        validate_entity_type(entity_type)
        stmt = stmt.where(ClassificationAssignment.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(ClassificationAssignment.entity_id == str(entity_id))
    if scheme_id is not None:
        stmt = stmt.where(ClassificationAssignment.scheme_id == str(scheme_id))
    if dimension_kind is not None:
        validate_dimension_kind(dimension_kind)
        stmt = stmt.where(ClassificationAssignment.dimension_kind == dimension_kind)

    if known_at is None:
        # Today's heads: open on both axes.
        stmt = stmt.where(
            ClassificationAssignment.system_to.is_(None),
            ClassificationAssignment.valid_to.is_(None),
        )
    else:
        # As KNOWN at that instant, and valid AT that instant — the valid interval is
        # reconstructed rather than forced open, so a since-superseded entity still appears.
        stmt = stmt.where(
            ClassificationAssignment.system_from <= known_at,
            or_(
                ClassificationAssignment.system_to.is_(None),
                ClassificationAssignment.system_to > known_at,
            ),
            ClassificationAssignment.valid_from <= known_at,
            or_(
                ClassificationAssignment.valid_to.is_(None),
                ClassificationAssignment.valid_to > known_at,
            ),
        )

    return list(
        session.execute(
            stmt.order_by(
                ClassificationAssignment.entity_id,
                ClassificationAssignment.dimension_kind,
                ClassificationAssignment.node_code,
            )
        )
        .scalars()
        .all()
    )


def reconstruct_assignment_as_of(
    session: Session,
    *,
    acting_tenant: str,
    entity_type: str,
    entity_id: str,
    scheme_id: str,
    dimension_kind: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> ClassificationAssignment | None:
    """The version in force on the VALID axis at ``valid_at``, as KNOWN at ``known_at``.

    Both axes, which is what makes it a reconstruction rather than a lookup: ``valid_at`` asks what
    the classification WAS, ``known_at`` asks what we BELIEVED it was at that time. A correction
    issued later is invisible to a read pinned before it — which is the property a governed run's
    reproducibility rests on.
    """
    validate_entity_type(entity_type)
    validate_dimension_kind(dimension_kind)
    tenant = canonical_tenant_id(acting_tenant)

    stmt = select(ClassificationAssignment).where(
        ClassificationAssignment.tenant_id == tenant,
        ClassificationAssignment.entity_type == entity_type,
        ClassificationAssignment.entity_id == str(entity_id),
        ClassificationAssignment.scheme_id == str(scheme_id),
        ClassificationAssignment.dimension_kind == dimension_kind,
        ClassificationAssignment.valid_from <= valid_at,
        or_(
            ClassificationAssignment.valid_to.is_(None),
            ClassificationAssignment.valid_to > valid_at,
        ),
    )
    if known_at is None:
        stmt = stmt.where(ClassificationAssignment.system_to.is_(None))
    else:
        stmt = stmt.where(
            ClassificationAssignment.system_from <= known_at,
            or_(
                ClassificationAssignment.system_to.is_(None),
                ClassificationAssignment.system_to > known_at,
            ),
        )
    return session.execute(stmt).scalar_one_or_none()
