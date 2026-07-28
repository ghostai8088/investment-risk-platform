"""Unit tests for the fail-closed auth_mode guard (SSO-1, AD-007, DR-P1A0-3).

These branches fire on NO existing in-repo config (app_env is 'local' everywhere), so they are
covered here directly rather than through the app. Explicit init kwargs override .env / the
environment (pydantic-settings init precedence), so each guard input is exactly as given.
"""

from __future__ import annotations

import pytest

from irp_backend.config import Settings, validate_auth_config


def test_dev_header_allowed_in_local() -> None:
    # The unverified shim is permitted locally — no raise.
    validate_auth_config(Settings(auth_mode="dev_header", app_env="local"))


def test_dev_header_rejected_outside_local() -> None:
    # The cutover's teeth: the shim must never run in a deployed environment.
    with pytest.raises(RuntimeError, match="dev_header"):
        validate_auth_config(Settings(auth_mode="dev_header", app_env="production"))


def test_oidc_requires_issuer() -> None:
    with pytest.raises(RuntimeError, match="OIDC_ISSUER"):
        validate_auth_config(
            Settings(auth_mode="oidc", app_env="local", oidc_issuer=None, oidc_audience="a")
        )


def test_oidc_requires_audience() -> None:
    # Audience restriction is mandatory in oidc mode (confused-deputy defence).
    with pytest.raises(RuntimeError, match="OIDC_AUDIENCE"):
        validate_auth_config(
            Settings(
                auth_mode="oidc",
                app_env="local",
                oidc_issuer="https://issuer.example",
                oidc_audience=None,
            )
        )


def test_oidc_require_mfa_needs_acr_values() -> None:
    with pytest.raises(RuntimeError, match="OIDC_ACR_VALUES"):
        validate_auth_config(
            Settings(
                auth_mode="oidc",
                app_env="local",
                oidc_issuer="https://issuer.example",
                oidc_audience="irp-backend",
                oidc_require_mfa=True,
                oidc_acr_values=None,
            )
        )


def test_oidc_fully_configured_ok() -> None:
    # A properly configured OIDC deployment passes even when app_env is non-local.
    validate_auth_config(
        Settings(
            auth_mode="oidc",
            app_env="production",
            oidc_issuer="https://issuer.example",
            oidc_audience="irp-backend",
        )
    )


# --- OPS-H1 (H1-5): the dev-header tenant is canonicalized before it can arm the GUC -------------


def test_dev_header_tenant_is_canonicalized() -> None:
    """The OQ-a class's third boundary: every form a client might send for the SAME tenant must
    yield the ONE canonical form RLS's ``tenant_id::text`` compares against — an uppercased or
    brace-wrapped UUID would otherwise arm a GUC matching nothing and read silently empty."""
    from irp_backend.deps import _principal_from_headers

    canonical = "8c3193a6-1c9c-5353-bbe1-ab8716e986a9"
    for form in (
        canonical,
        canonical.upper(),
        "{" + canonical + "}",
        "urn:uuid:" + canonical,
    ):
        principal = _principal_from_headers("user-1", form)
        assert principal.tenant_id == canonical, form


def test_dev_header_non_uuid_tenant_is_a_401_not_an_armed_guc() -> None:
    """Fail-loud on garbage: a non-UUID tenant header must never reach the GUC."""
    import pytest
    from fastapi import HTTPException

    from irp_backend.deps import _principal_from_headers

    with pytest.raises(HTTPException) as caught:
        _principal_from_headers("user-1", "not-a-uuid")
    assert caught.value.status_code == 401
