"""Shared model-version guard — the cross-tenant FK re-resolution for ``model_version_id``.

The P3-5 principal finding (see ``portfolio.guards``): PostgreSQL FK checks BYPASS RLS, so an id
lifted from an external/config string must be re-resolved under the acting tenant BEFORE it is
stamped into a NOT-NULL FK column — otherwise a durable cross-tenant reference (or a flush 500) is
possible. ``model_version`` carries ``TenantMixin``, so a governed writer that stamps a
``model_version_id`` FK re-resolves it here with an explicit tenant predicate. It lives ONCE here,
parameterized by the caller's own pre-create refusal error class (each caller keeps its own error
vocabulary — the API maps them per family).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def assert_model_version_in_tenant(
    session: Session, model_version_id: str, *, acting_tenant: str, error: type[Exception]
) -> None:
    """Re-resolve ``model_version_id`` under the acting tenant with an EXPLICIT tenant predicate
    (models-only import — no service cycle). Raises ``error`` if the id is not visible in the acting
    tenant: a FOREIGN/non-existent ``model_version_id`` must never be stamped into a NOT-NULL FK
    (PG FK checks bypass RLS, so the DB alone would admit a cross-tenant reference)."""
    from irp_shared.model.models import ModelVersion  # models-only (no cycle)

    row = session.execute(
        select(ModelVersion).where(
            ModelVersion.id == str(model_version_id),
            ModelVersion.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise error(
            f"the model version {model_version_id} is not visible in the acting tenant — refused"
        )
