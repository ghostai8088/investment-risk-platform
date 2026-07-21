"""Application configuration.

Loaded from the environment only — no secrets in source (BR-10). Defaults are safe,
non-secret development values.

**Auth (SSO-1, AD-007):** ``auth_mode`` selects how a caller's identity is established.
``oidc`` (the default, fail-closed) verifies an ``Authorization: Bearer`` JWT against the
issuer's JWKS; ``dev_header`` reads the unverified ``X-User-Id`` / ``X-Tenant-Id`` shim and is
permitted **only when ``app_env == "local"``** (DR-P1A0-3). The guard is
:func:`validate_auth_config`, invoked at app startup (``main.py`` lifespan) — **never at import**:
``settings`` is a module-level singleton built at import time, so an import-time validator would
raise before pytest can configure the suite. The resource server holds **no client secret** — the
OIDC client secret is the IdP's / front-end's concern.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_version: str = "0.1.0"
    database_url: str | None = None

    # --- Identity / authentication (SSO-1, AD-007) ---
    # Default is fail-closed: verify a real token unless explicitly put in the local dev shim.
    auth_mode: Literal["oidc", "dev_header"] = "oidc"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    # If unset, the JWKS URI is discovered from ``{issuer}/.well-known/openid-configuration``.
    oidc_jwks_uri: str | None = None
    # The signing algorithms accepted — RS256 only. NEVER include ``none`` or a symmetric alg
    # (``alg`` confusion / HS-vs-RS downgrade defence).
    oidc_algorithms: list[str] = ["RS256"]
    # Claims carrying the tenant UUID and the OIDC subject (configurable — IdPs namespace claims).
    oidc_tenant_claim: str = "tenant_id"
    oidc_subject_claim: str = "sub"
    # MFA is enforced at the IdP (AD-007); when True the resource server also requires the token to
    # assert MFA via an ``acr``/``amr`` claim matching one of ``oidc_acr_values``.
    oidc_require_mfa: bool = False
    oidc_acr_values: list[str] | None = None


def validate_auth_config(s: Settings) -> None:
    """Fail-closed startup guard for the identity configuration (AD-007, DR-P1A0-3).

    Called from the FastAPI lifespan (``main.py``) — **not at import, not in a model_validator**:
    ``settings = Settings()`` is constructed at import, and every backend test uses a plain
    ``TestClient`` (no lifespan), so this fires only on a real ``uvicorn`` boot.

    - ``dev_header`` is permitted **only** when ``app_env == "local"`` — the unverified header shim
      must never be reachable in a deployed environment (the cutover's teeth).
    - ``oidc`` requires an issuer AND an audience (audience restriction stops a token minted for a
      different resource server of the same issuer from authenticating here — confused-deputy).
    - ``oidc`` with ``oidc_require_mfa`` requires ``oidc_acr_values`` — so an MFA-tightening
      deployment fails fast at boot, not with a 500 on the first request.
    """
    if s.auth_mode == "dev_header" and s.app_env != "local":
        raise RuntimeError(
            "auth_mode='dev_header' (the unverified identity shim) is permitted only when "
            f"app_env='local'; got app_env={s.app_env!r}. Deployed environments must use OIDC "
            "(AD-007, DR-P1A0-3)."
        )
    if s.auth_mode == "oidc" and not s.oidc_issuer:
        raise RuntimeError(
            "auth_mode='oidc' requires OIDC_ISSUER to be configured (the token issuer to verify "
            "against). Set OIDC_ISSUER, or use auth_mode='dev_header' for local development."
        )
    if s.auth_mode == "oidc" and not s.oidc_audience:
        raise RuntimeError(
            "auth_mode='oidc' requires OIDC_AUDIENCE — the resource-server audience the token must "
            "be scoped to. Without it, any signed token from the issuer (e.g. one minted for a "
            "different client of the same realm) would be accepted (confused-deputy)."
        )
    if s.auth_mode == "oidc" and s.oidc_require_mfa and not s.oidc_acr_values:
        raise RuntimeError(
            "oidc_require_mfa=True requires OIDC_ACR_VALUES (the acr/amr values that count as MFA)."
        )


settings = Settings()
