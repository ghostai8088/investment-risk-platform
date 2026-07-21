"""Shared backend test fixtures (SSO-1).

``auth_mode`` now defaults to ``oidc`` (fail-closed). ``app_env`` is ``local`` in tests, so the
startup guard permits the dev-header shim; this autouse fixture pins the suite to ``dev_header`` so
the endpoint tests keep authenticating via ``X-User-Id`` / ``X-Tenant-Id`` unchanged. OIDC-mode
tests opt in explicitly (``test_oidc_auth.py``) by setting ``settings.auth_mode = "oidc"``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from irp_backend.config import settings


@pytest.fixture(autouse=True)
def _dev_header_auth_mode() -> Iterator[None]:
    previous = settings.auth_mode
    settings.auth_mode = "dev_header"
    try:
        yield
    finally:
        settings.auth_mode = previous
