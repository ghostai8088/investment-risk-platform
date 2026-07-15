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

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE
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
        action=ACTION_CREATE,
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
        action=ACTION_CREATE,
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


def resolve_or_register_model(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    model_type: str,
    actor_id: str,
    **kwargs: Any,
) -> Model:
    """Resolve the ``(tenant_id, code)`` model inventory head, registering it if absent — race-safe.

    Two concurrent FIRST bootstraps of the same model both SELECT-miss then INSERT the same
    ``(tenant_id, code)`` → one hits the unique constraint. The INSERT is wrapped in a SAVEPOINT
    (``begin_nested``) so the loser's ``IntegrityError`` rolls back ONLY that INSERT — not the
    caller's governed unit, which an unwrapped error would abort into a 500 on PostgreSQL; the loser
    then re-SELECTs the peer's committed row (READ COMMITTED). Mirrors the ``dq/gates`` resolve-or-
    register savepoint pattern (MD-H1 OD-D). ``kwargs`` are the optional ``register_model`` metadata
    (``description``/``owner``/``developer``/``tier``/``actor_type``/agent fields).
    """
    q = select(Model).where(Model.tenant_id == str(tenant_id), Model.code == code)
    model = session.execute(q).scalar_one_or_none()
    if model is not None:
        return model
    try:
        with session.begin_nested():  # SAVEPOINT around the racy INSERT
            return register_model(
                session,
                tenant_id=str(tenant_id),
                code=code,
                name=name,
                model_type=model_type,
                actor_id=actor_id,
                **kwargs,
            )
    except IntegrityError:
        peer = session.execute(q).scalar_one_or_none()
        if peer is None:  # not the unique-collision we handle — re-raise loudly
            raise
        return peer


def resolve_or_register_version(
    session: Session,
    *,
    model: Model,
    version_label: str,
    register: Callable[[], ModelVersion],
) -> ModelVersion:
    """Resolve the ``(model, version_label)`` immutable version, registering if absent — race-safe.

    The caller supplies ``register`` — a zero-arg closure over ``register_model_version`` carrying
    the family's methodology/assumptions/status. SELECT-miss → register inside a SAVEPOINT; on the
    concurrent-first-registration ``IntegrityError`` (both racers INSERT the same
    ``(model_id, version_label)``), re-SELECT the peer. The caller runs its family-specific
    identity/conflict checks on the returned row — they pass trivially for a row THIS call minted
    and catch a squatted/mismatched peer (the race + idempotent-re-invocation path). Mirrors the
    ``dq/gates`` savepoint pattern (MD-H1 OD-D).
    """
    q = select(ModelVersion).where(
        ModelVersion.model_id == model.id,
        ModelVersion.version_label == version_label,
    )
    version = session.execute(q).scalar_one_or_none()
    if version is not None:
        return version
    try:
        with session.begin_nested():  # SAVEPOINT around the racy INSERT
            return register()
    except IntegrityError:
        peer = session.execute(q).scalar_one_or_none()
        if peer is None:  # not the unique-collision we handle — re-raise loudly
            raise
        return peer


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


class WrongModelVersionError(Exception):
    """The ``model_version`` is registered but belongs to a DIFFERENT model than the run requires
    (a governed-number binder must not bind a methodology from another model family). A CTRL-003
    tightening; fail-closed pre-create. Maps to 422. (Promoted from ``risk.bootstrap`` at PM-1 — a
    generic model-registry-governance concern once a SECOND governed-number family, ``perf``,
    consumes it; re-exported from ``risk.bootstrap`` for API stability.)"""

    def __init__(self, model_version_id: str, expected_model_code: str) -> None:
        super().__init__(
            f"model_version {model_version_id} is not a version of {expected_model_code!r}"
        )
        self.model_version_id = str(model_version_id)
        self.expected_model_code = expected_model_code


class ModelVersionConflictError(Exception):
    """``(tenant, model, version_label)`` is already registered with a DIFFERENT ``code_version``
    — the immutable inventory identity cannot be silently re-pointed (registering a genuinely new
    code requires a NEW version_label). Maps to 409. (Promoted from ``risk.bootstrap`` at PM-1;
    re-exported there for API stability.)"""

    def __init__(self, model_code: str, version_label: str, code_version: str) -> None:
        super().__init__(
            f"{model_code!r} {version_label!r} is already registered with a different "
            f"code_version (requested {code_version!r}); mint a new version_label instead"
        )
        self.model_code = model_code
        self.version_label = version_label
        self.code_version = code_version


class RejectedModelVersionError(Exception):
    """The ``model_version`` is REGISTERED and of the right model, but its LATEST validation record
    (ENT-037, VW-1) has outcome ``REJECTED`` — a validator has stood it down, so no NEW governed run
    may bind it (CTRL-022). Fail-closed pre-create. Maps to 422. Re-validating it with an APPROVED
    record clears the block (the recency semantics); its already-COMPLETED runs stay intact and
    backtestable (the re-validation evidence loop)."""

    def __init__(self, model_version_id: str) -> None:
        super().__init__(
            f"model_version {model_version_id} latest validation outcome is REJECTED — new runs "
            f"refused (CTRL-022)"
        )
        self.model_version_id = str(model_version_id)


def assert_model_version_of(
    session: Session,
    model_version_id: str,
    *,
    tenant_id: str,
    expected_model_code: str,
) -> ModelVersion:
    """CTRL-003 with model-identity: the version must be REGISTERED (fail-closed) AND belong to the
    model ``expected_model_code`` — raising :class:`WrongModelVersionError` otherwise. Used
    pre-create by every governed-number binder (risk + perf) so a run can never bind a methodology
    from a different model family. (Promoted from ``risk.bootstrap`` at PM-1 — the model-family
    identity gate is generic once ``perf`` also consumes it; re-exported from ``risk.bootstrap`` for
    API stability.)"""
    version = assert_registered_model_version(session, str(model_version_id), tenant_id=tenant_id)
    if version.status != "REGISTERED":
        # The binders' documented contract is "a REGISTERED model_version"; a version minted via
        # the GENERIC registration can carry status=None and previously bound anyway (the P3-5
        # review's recorded deferral; P3-C1 OD-B). The generic resolver + P7 validation semantics
        # are untouched — this gate is governed-number-binder-scoped.
        raise UnregisteredModelError(str(model_version_id))
    model = session.execute(
        select(Model).where(Model.id == version.model_id, Model.tenant_id == str(tenant_id))
    ).scalar_one_or_none()
    if model is None or model.code != expected_model_code:
        raise WrongModelVersionError(str(model_version_id), expected_model_code)
    # VW-1 OD-B (CTRL-022): a version whose LATEST validation record is REJECTED is stood down — no
    # new governed run may bind it. Imported inside the function (not a cycle — validation.py does
    # not import service.py — but this keeps the gate's VW-1 dependency local to the one call).
    # UNVALIDATED (no record) and every non-REJECTED outcome bind normally — the documented SR 26-2
    # use-before-validation posture.
    from irp_shared.model.models import VALIDATION_OUTCOME_REJECTED
    from irp_shared.model.validation import latest_validation

    latest = latest_validation(session, str(version.id), acting_tenant=str(tenant_id))
    if latest is not None and latest.outcome == VALIDATION_OUTCOME_REJECTED:
        raise RejectedModelVersionError(str(model_version_id))
    return version


def _resolve_version(session: Session, model_version_id: str) -> ModelVersion:
    version = session.execute(
        select(ModelVersion).where(ModelVersion.id == str(model_version_id))
    ).scalar_one_or_none()
    if version is None:
        raise ModelNotVisible("model_version", str(model_version_id))
    return version
