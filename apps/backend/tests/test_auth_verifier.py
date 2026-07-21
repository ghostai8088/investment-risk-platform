"""Unit battery for the OAuth2 resource-server JWT verifier (SSO-1, AD-007).

Tokens are minted and signed with a locally-generated RSA keypair — no network, no IdP. The
verifier's key source is injected (``key_resolver``) so signature verification is exercised
end-to-end offline. Every negative path must fail closed with :class:`TokenError`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from irp_backend.auth import TokenError, TokenVerifier

ISS = "https://issuer.example"
AUD = "irp-backend"


def _keypair() -> tuple[bytes, bytes]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


def _verifier(pub_pem: bytes, **overrides: Any) -> TokenVerifier:
    kwargs: dict[str, Any] = {
        "issuer": ISS,
        "audience": AUD,
        "algorithms": ["RS256"],
        "tenant_claim": "tenant_id",
        "subject_claim": "sub",
        "require_mfa": False,
        "acr_values": None,
        "key_resolver": lambda _token: pub_pem,
    }
    kwargs.update(overrides)
    return TokenVerifier(**kwargs)


def _token(
    priv_pem: bytes,
    *,
    iss: str = ISS,
    aud: str = AUD,
    sub: str | None = "subject-1",
    tenant: str | None = "tenant-1",
    exp_delta: int = 3600,
    alg: str = "RS256",
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + timedelta(seconds=exp_delta),
    }
    if sub is not None:
        payload["sub"] = sub
    if tenant is not None:
        payload["tenant_id"] = tenant
    if extra:
        payload.update(extra)
    return jwt.encode(payload, priv_pem, algorithm=alg)


def test_valid_token_round_trips() -> None:
    priv, pub = _keypair()
    claims = _verifier(pub).verify(_token(priv, sub="u-1", tenant="t-1"))
    assert claims.subject == "u-1"
    assert claims.tenant == "t-1"
    assert claims.raw["iss"] == ISS


def test_signature_from_wrong_key_is_rejected() -> None:
    _, pub = _keypair()  # the verifier trusts this key
    other_priv, _ = _keypair()  # the token is signed by a different key
    with pytest.raises(TokenError):
        _verifier(pub).verify(_token(other_priv))


def test_alg_none_is_rejected() -> None:
    priv, pub = _keypair()
    now = datetime.now(tz=UTC)
    unsigned = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "t", "exp": now + timedelta(hours=1)},
        key="",
        algorithm="none",
    )
    with pytest.raises(TokenError):
        _verifier(pub).verify(unsigned)


def test_hs256_confusion_is_rejected() -> None:
    # A token signed HS256 (symmetric) must not verify against an RS256-only verifier.
    priv, pub = _keypair()
    now = datetime.now(tz=UTC)
    hs = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "t", "exp": now + timedelta(hours=1)},
        key="a-shared-secret",
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        _verifier(pub).verify(hs)


def test_wrong_issuer_is_rejected() -> None:
    priv, pub = _keypair()
    with pytest.raises(TokenError):
        _verifier(pub).verify(_token(priv, iss="https://evil.example"))


def test_wrong_audience_is_rejected() -> None:
    priv, pub = _keypair()
    with pytest.raises(TokenError):
        _verifier(pub).verify(_token(priv, aud="some-other-api"))


def test_expired_token_is_rejected() -> None:
    priv, pub = _keypair()
    with pytest.raises(TokenError):
        _verifier(pub).verify(_token(priv, exp_delta=-10))


def test_missing_subject_is_rejected() -> None:
    priv, pub = _keypair()
    with pytest.raises(TokenError):
        _verifier(pub).verify(_token(priv, sub=None))


def test_missing_tenant_claim_is_rejected() -> None:
    priv, pub = _keypair()
    with pytest.raises(TokenError):
        _verifier(pub).verify(_token(priv, tenant=None))


def test_mfa_required_but_absent_is_rejected() -> None:
    priv, pub = _keypair()
    v = _verifier(pub, require_mfa=True, acr_values=["mfa"])
    with pytest.raises(TokenError):
        v.verify(_token(priv))  # no acr/amr claim


def test_mfa_required_and_asserted_passes() -> None:
    priv, pub = _keypair()
    v = _verifier(pub, require_mfa=True, acr_values=["mfa"])
    claims = v.verify(_token(priv, extra={"acr": "mfa"}))
    assert claims.subject == "subject-1"


def test_require_mfa_without_acr_values_is_a_config_error() -> None:
    _, pub = _keypair()
    with pytest.raises(RuntimeError, match="acr_values"):
        _verifier(pub, require_mfa=True, acr_values=None)
