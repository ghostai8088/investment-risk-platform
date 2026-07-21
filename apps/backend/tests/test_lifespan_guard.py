"""The main-app lifespan enforces the fail-closed auth guard at startup (SSO-1, AD-007).

`validate_auth_config` is unit-tested in isolation; this proves the lifespan actually calls it, so
a regression that drops the guard from `main.py` is caught. Uses `with TestClient(app)` to trigger
the lifespan (the rest of the suite uses a plain client that does not).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from irp_backend.config import settings
from irp_backend.main import app


def test_lifespan_boots_in_local_dev_header() -> None:
    # dev_header + local (the autouse conftest default) boots cleanly through the lifespan.
    with TestClient(app):
        pass


def test_lifespan_rejects_dev_header_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    # auth_mode is dev_header (autouse); a non-local env must make the lifespan refuse to start.
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="dev_header"), TestClient(app):
        pass
