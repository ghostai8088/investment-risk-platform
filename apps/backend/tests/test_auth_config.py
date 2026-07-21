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
