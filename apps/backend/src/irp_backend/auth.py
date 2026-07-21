"""OAuth2 resource-server token verification (SSO-1, AD-007).

The API is a **resource server**: it verifies an ``Authorization: Bearer <JWT>`` issued by the
enterprise IdP against the issuer's JWKS — signature, ``iss``, ``aud``, ``exp``/``nbf``, and the
required claims (subject + tenant) — and optionally an MFA assertion (``acr``/``amr``). It issues
no tokens and holds no client secret (BR-10).

**Security posture:**
- The signing algorithm is an explicit allow-list (**RS256 only** by default). ``alg=none`` and
  symmetric algorithms are never accepted — this defeats the ``alg`` confusion / HS-vs-RS
  downgrade attack.
- Key resolution and verification **fail closed**: any JWKS-fetch error, signature failure, wrong
  issuer/audience, expiry, or missing claim raises :class:`TokenError` (→ 401), never a silent
  pass.

The signing-key source is injectable (``key_resolver``) so tests verify locally-signed tokens
with no network; production resolves against the issuer JWKS via :class:`jwt.PyJWKClient`.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt

from irp_backend.config import Settings, settings

_DISCOVERY_TIMEOUT_SECONDS = 5
# Clock-skew tolerance for exp/nbf/iat (seconds) — small, so short-lived tokens (AD-007) are not
# rejected on a few seconds of drift between the IdP and this server.
_CLOCK_SKEW_LEEWAY_SECONDS = 60


class TokenError(Exception):
    """A bearer token failed verification (any cause). Maps to HTTP 401."""


@dataclass(frozen=True)
class VerifiedClaims:
    """The verified identity extracted from a valid token."""

    subject: str
    tenant: str
    raw: dict[str, Any]


class TokenVerifier:
    """Verifies a bearer JWT and extracts the subject + tenant claims.

    ``key_resolver`` maps a raw token to the key to verify it with (a PEM string or a
    :class:`jwt.PyJWK`); it is called inside a fail-closed guard.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str | None,
        algorithms: list[str],
        tenant_claim: str,
        subject_claim: str,
        require_mfa: bool,
        acr_values: list[str] | None,
        key_resolver: Callable[[str], Any],
    ) -> None:
        if require_mfa and not acr_values:
            raise RuntimeError(
                "oidc_require_mfa=True requires oidc_acr_values to be configured (the acr/amr "
                "values that count as MFA)."
            )
        self._issuer = issuer
        self._audience = audience
        self._algorithms = algorithms
        self._tenant_claim = tenant_claim
        self._subject_claim = subject_claim
        self._require_mfa = require_mfa
        self._acr_values = acr_values or []
        self._key_resolver = key_resolver

    def verify(self, token: str) -> VerifiedClaims:
        """Verify ``token`` and return its identity, or raise :class:`TokenError`."""
        try:
            key = self._key_resolver(token)
        except (jwt.PyJWTError, OSError, ValueError) as exc:  # fail closed on any resolution error
            raise TokenError(f"could not resolve signing key: {exc}") from exc

        required = ["exp", "iss", self._subject_claim, self._tenant_claim]
        options: dict[str, Any] = {"require": required, "verify_aud": self._audience is not None}
        decode_kwargs: dict[str, Any] = {
            "algorithms": self._algorithms,  # explicit allow-list — never 'none', never symmetric
            "issuer": self._issuer,
            "options": options,
        }
        if self._audience is not None:
            decode_kwargs["audience"] = self._audience
            required.append("aud")

        decode_kwargs["leeway"] = _CLOCK_SKEW_LEEWAY_SECONDS
        try:
            claims: dict[str, Any] = jwt.decode(token, key, **decode_kwargs)
        except jwt.InvalidTokenError as exc:  # base of expiry/iss/aud/sig/missing-claim/alg errors
            raise TokenError(str(exc)) from exc

        self._check_mfa(claims)

        subject = claims.get(self._subject_claim)
        tenant = claims.get(self._tenant_claim)
        if not subject or not tenant:  # belt-and-suspenders (also enforced via `require`)
            raise TokenError("token missing subject or tenant claim")
        return VerifiedClaims(subject=str(subject), tenant=str(tenant), raw=claims)

    def _check_mfa(self, claims: dict[str, Any]) -> None:
        if not self._require_mfa:
            return
        acr = claims.get("acr")
        amr = claims.get("amr")
        # Keep only hashable str elements — a pathological amr (e.g. a nested list) must not crash
        # the verifier to a 500; it simply asserts no recognized MFA value → deny.
        amr_values = {a for a in amr if isinstance(a, str)} if isinstance(amr, list) else set()
        if acr not in self._acr_values and not (amr_values & set(self._acr_values)):
            raise TokenError("token does not assert a required MFA acr/amr value")


def _discover_jwks_uri(issuer: str) -> str:
    """Resolve the JWKS URI from the issuer's OIDC discovery document (fail closed)."""
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=_DISCOVERY_TIMEOUT_SECONDS) as resp:  # noqa: S310
        doc = json.loads(resp.read())
    jwks_uri = doc.get("jwks_uri")
    if not jwks_uri:
        raise TokenError(f"OIDC discovery document at {url} has no jwks_uri")
    return str(jwks_uri)


def _jwks_key_resolver(issuer: str, jwks_uri: str | None) -> Callable[[str], Any]:
    """Build the production key resolver backed by the issuer JWKS (cached by PyJWKClient)."""
    resolved_uri = jwks_uri or _discover_jwks_uri(issuer)
    client = jwt.PyJWKClient(resolved_uri)

    def resolve(token: str) -> Any:
        return client.get_signing_key_from_jwt(token).key

    return resolve


def build_verifier(s: Settings) -> TokenVerifier:
    """Construct a production :class:`TokenVerifier` from settings (requires ``oidc_issuer``)."""
    if not s.oidc_issuer:
        raise RuntimeError("build_verifier requires oidc_issuer to be set")
    return TokenVerifier(
        issuer=s.oidc_issuer,
        audience=s.oidc_audience,
        algorithms=s.oidc_algorithms,
        tenant_claim=s.oidc_tenant_claim,
        subject_claim=s.oidc_subject_claim,
        require_mfa=s.oidc_require_mfa,
        acr_values=s.oidc_acr_values,
        key_resolver=_jwks_key_resolver(s.oidc_issuer, s.oidc_jwks_uri),
    )


@lru_cache(maxsize=1)
def get_verifier() -> TokenVerifier:
    """The process-wide verifier singleton (JWKS client cached inside). Built on first use so a
    transient IdP outage at boot does not poison the cache (the exception is not cached)."""
    return build_verifier(settings)
