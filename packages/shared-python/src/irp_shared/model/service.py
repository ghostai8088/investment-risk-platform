"""Model-registry write/verify utilities (MG-01/MG-02, BR-3).

- ``register_model`` / ``register_model_version`` — inventory the model + immutable version
  (+ optional assumptions/limitations), each emitting a taxonomy audit event in the **same
  transaction** as the data row (fail-closed: a rejected audit insert rolls the row back).
- ``record_assumption`` / ``record_limitation`` — append IA captures tied to a version; they emit
  **no** event of their own (folded into the version's ``MODEL.VERSION``, per the plan §6 decision).
- ``assert_registered_model_version`` — the inventory-before-use gate (MG-02/BR-3/CTRL-003).

Tenant scoping: ``tenant_id`` is stamped **server-side**; child writes resolve their parent through
the (RLS-scoped) session so a cross-tenant parent id fails closed. No validation/approval/tier
workflow is implemented — governance fields are non-enforcing placeholders.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.model.models import (
    Model,
    ModelAssumption,
    ModelLimitation,
    ModelVersion,
)

#: Existing audit taxonomy codes (audit_event_taxonomy.md, MODEL category, EVT-050…).
MODEL_REGISTER_EVENT = "MODEL.REGISTER"
MODEL_VERSION_EVENT = "MODEL.VERSION"


class UnregisteredModelError(Exception):
    """Raised by the inventory-before-use gate when a model_version is not registered (BR-3)."""

    def __init__(self, model_version_id: str) -> None:
        super().__init__(f"model_version {model_version_id} is not registered (BR-3 / MG-02)")
        self.model_version_id = str(model_version_id)


class ModelNotVisible(Exception):
    """Raised when a parent (model / model_version) is not visible in the current tenant scope
    (cross-tenant id hidden by RLS, or unknown) — the child write fails closed."""

    def __init__(self, kind: str, parent_id: str) -> None:
        super().__init__(f"{kind} {parent_id} is not visible in the current tenant context")
        self.kind = kind
        self.parent_id = str(parent_id)


def register_model(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    model_type: str,
    actor_id: str,
    description: str | None = None,
    owner: str | None = None,
    developer: str | None = None,
    tier: str | None = None,
    actor_type: str = "user",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    on_behalf_of: str | None = None,
    correlation_id: str | None = None,
) -> Model:
    """Create a ``model`` inventory head and audit it (``MODEL.REGISTER``), same transaction.

    ``tier``/``owner``/``developer`` are recorded as metadata but gate nothing. An AI-agent
    registrant passes ``actor_type='agent'`` + ``agent_model*`` so authorship is logged (MG-08).
    """
    model = Model(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        model_type=model_type,
        description=description,
        is_active=True,
        record_version=1,
        owner=owner,
        developer=developer,
        tier=tier,
    )
    session.add(model)
    session.flush()

    record_event(
        session,
        event_type=MODEL_REGISTER_EVENT,
        tenant_id=str(tenant_id),
        actor_type=actor_type,
        actor_id=actor_id,
        source_module="model",
        entity_type="model",
        entity_id=model.id,
        action="create",
        after_value={
            "code": code,
            "name": name,
            "model_type": model_type,
            "owner": owner,
            "tier": tier,
            "validation_status": model.validation_status,
        },
        correlation_id=correlation_id,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        on_behalf_of=on_behalf_of,
        data_classification="DC-1",
    )
    return model


def record_assumption(
    session: Session,
    *,
    model_version: ModelVersion,
    assumption_text: str,
    category: str | None = None,
    authored_by: str | None = None,
) -> ModelAssumption:
    """Append an IA assumption to a version (no own event; folded into MODEL.VERSION)."""
    resolved = _resolve_version(session, model_version.id)
    row = ModelAssumption(
        tenant_id=resolved.tenant_id,
        model_version_id=resolved.id,
        assumption_text=assumption_text,
        category=category,
        authored_by=authored_by,
    )
    session.add(row)
    session.flush()
    return row


def record_limitation(
    session: Session,
    *,
    model_version: ModelVersion,
    limitation_text: str,
    severity: str | None = None,
    authored_by: str | None = None,
) -> ModelLimitation:
    """Append an IA limitation to a version (BX-LIM/CTRL-014; no separate audit event)."""
    resolved = _resolve_version(session, model_version.id)
    row = ModelLimitation(
        tenant_id=resolved.tenant_id,
        model_version_id=resolved.id,
        limitation_text=limitation_text,
        severity=severity,
        authored_by=authored_by,
    )
    session.add(row)
    session.flush()
    return row


def register_model_version(
    session: Session,
    *,
    model: Model,
    version_label: str,
    actor_id: str,
    methodology_ref: str | None = None,
    code_version: str | None = None,
    status: str | None = None,
    assumptions: Sequence[str] | None = None,
    limitations: Sequence[str] | None = None,
    authored_by: str | None = None,
    actor_type: str = "user",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    on_behalf_of: str | None = None,
    correlation_id: str | None = None,
) -> ModelVersion:
    """Create an immutable ``model_version`` (+ optional assumptions/limitations) and audit it
    (``MODEL.VERSION``), same transaction. Assumptions/limitations are folded into this one event
    Counts go in the ``MODEL.VERSION`` ``after_value``; they emit no event of their own.

    The parent ``model`` is resolved through the RLS-scoped session and the version's ``tenant_id``
    is stamped from it (a cross-tenant parent id fails closed with :class:`ModelNotVisible`).
    """
    parent = session.execute(select(Model).where(Model.id == str(model.id))).scalar_one_or_none()
    if parent is None:
        raise ModelNotVisible("model", str(model.id))

    version = ModelVersion(
        tenant_id=parent.tenant_id,  # server-side stamp; RLS WITH CHECK is the backstop
        model_id=parent.id,
        version_label=version_label,
        methodology_ref=methodology_ref,
        code_version=code_version,
        status=status,
    )
    session.add(version)
    session.flush()

    for text in assumptions or ():
        record_assumption(
            session, model_version=version, assumption_text=text, authored_by=authored_by
        )
    for text in limitations or ():
        record_limitation(
            session, model_version=version, limitation_text=text, authored_by=authored_by
        )

    record_event(
        session,
        event_type=MODEL_VERSION_EVENT,
        tenant_id=parent.tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        source_module="model",
        entity_type="model_version",
        entity_id=version.id,
        action="create",
        after_value={
            "model_id": parent.id,
            "version_label": version_label,
            "is_immutable": True,
            "assumption_count": len(assumptions or ()),
            "limitation_count": len(limitations or ()),
        },
        correlation_id=correlation_id,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        on_behalf_of=on_behalf_of,
        data_classification="DC-1",
    )
    return version


def assert_registered_model_version(
    session: Session,
    model_version_id: str,
    *,
    tenant_id: str | None = None,
) -> ModelVersion:
    """Return the registered ``ModelVersion`` or raise :class:`UnregisteredModelError` (MG-02/BR-3).

    Tenant-scoped by RLS on PostgreSQL; pass ``tenant_id`` to also scope explicitly (SQLite tests).
    """
    stmt = select(ModelVersion).where(ModelVersion.id == str(model_version_id))
    if tenant_id is not None:
        stmt = stmt.where(ModelVersion.tenant_id == str(tenant_id))
    version = session.execute(stmt.limit(1)).scalar_one_or_none()
    if version is None:
        raise UnregisteredModelError(str(model_version_id))
    return version


def _resolve_version(session: Session, model_version_id: str) -> ModelVersion:
    version = session.execute(
        select(ModelVersion).where(ModelVersion.id == str(model_version_id))
    ).scalar_one_or_none()
    if version is None:
        raise ModelNotVisible("model_version", str(model_version_id))
    return version
