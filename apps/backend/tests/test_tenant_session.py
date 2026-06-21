"""The app request path sets tenant context via get_tenant_session (AD-016)."""

from __future__ import annotations

import uuid

import pytest

import irp_backend.deps as deps
from irp_shared.entitlement.service import Principal


def test_get_tenant_session_sets_context_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(deps, "set_tenant_context", lambda db, tenant_id: calls.append(tenant_id))

    principal = Principal(user_id="u", tenant_id=str(uuid.uuid4()))
    sentinel_db = object()

    generator = deps.get_tenant_session(principal=principal, db=sentinel_db)  # type: ignore[arg-type]
    yielded = next(generator)

    assert yielded is sentinel_db
    assert calls == [principal.tenant_id]  # context set for the principal's tenant, once
