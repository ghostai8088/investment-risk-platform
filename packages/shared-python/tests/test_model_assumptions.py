"""Unit tests for the shared model-assumption parse-back primitives (RD-2 dedup —
`irp_shared.model.assumptions`).

The five `declared_*` parse-backs (Geltner alpha, VaR params, HS-VaR params, covariance window,
Kupiec alpha) are each exercised end-to-end by their family suites; this pins the SHARED contract
directly: the single ModelAssumption load scoped to the version, the sole-value extraction
(found / absent / ambiguous), and the `require_declared` pattern + injectable-error refusal.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.model.assumptions import load_assumption_texts, require_declared, sole_declared
from irp_shared.model.models import Model, ModelAssumption, ModelVersion
from irp_shared.models import Base

_PAT = re.compile(r"0\.[0-9]{1,4}")


class _Invalid(Exception):
    """A stand-in for the family-specific fail-closed class (e.g. WrongModelVersionError)."""


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _version_with(db: Session, tenant: str, texts: list[str]) -> ModelVersion:
    model = Model(tenant_id=tenant, code=f"m-{uuid.uuid4().hex}", name="m", model_type="risk")
    db.add(model)
    db.flush()
    version = ModelVersion(
        tenant_id=tenant, model_id=model.id, version_label="1.0.0", code_version="v1"
    )
    db.add(version)
    db.flush()
    for text in texts:
        db.add(ModelAssumption(tenant_id=tenant, model_version_id=version.id, assumption_text=text))
    db.flush()
    return version


# --- sole_declared / require_declared are PURE (operate on the loaded text list) ---


def test_sole_declared_found_absent_ambiguous() -> None:
    texts = ["alpha=0.4", "window_observations=250", "note: nothing"]
    assert sole_declared(texts, "alpha=") == "0.4"  # prefix stripped
    assert sole_declared(texts, "window_observations=") == "250"
    assert sole_declared(texts, "missing=") is None  # absent -> None
    assert sole_declared(["a=1", "a=2"], "a=") is None  # ambiguous (>1) -> None
    # A text that merely CONTAINS the prefix mid-string is NOT a declaration (startswith-anchored —
    # the parse-back security contract): a `startswith`->`in` regression must not promote it.
    assert sole_declared(["note: alpha=0.4"], "alpha=") is None


def test_require_declared_returns_or_refuses() -> None:
    assert require_declared(["alpha=0.4"], "alpha=", pattern=_PAT, on_invalid=_Invalid) == "0.4"
    # absent, ambiguous, and pattern-mismatch each fail closed via the injected class — never a
    # bare parse crash (the P3-4 lesson).
    with pytest.raises(_Invalid):
        require_declared(["x=1"], "alpha=", pattern=_PAT, on_invalid=_Invalid)
    with pytest.raises(_Invalid):
        require_declared(["alpha=0.4", "alpha=0.5"], "alpha=", pattern=_PAT, on_invalid=_Invalid)
    with pytest.raises(_Invalid):
        require_declared(["alpha=nope"], "alpha=", pattern=_PAT, on_invalid=_Invalid)
    # Trailing garbage after a partial match is refused — `fullmatch`, not `match` (a
    # `fullmatch`->`match` regression would accept "0.4x").
    with pytest.raises(_Invalid):
        require_declared(["alpha=0.4x"], "alpha=", pattern=_PAT, on_invalid=_Invalid)


# --- load_assumption_texts is the shared DB load, scoped to the version ---


def test_load_assumption_texts_scopes_to_version(session: Session) -> None:
    tenant = "t-1"
    v1 = _version_with(session, tenant, ["alpha=0.4", "note: hi"])
    v2 = _version_with(session, tenant, ["window_observations=250"])
    assert sorted(load_assumption_texts(session, v1)) == ["alpha=0.4", "note: hi"]
    assert load_assumption_texts(session, v2) == ["window_observations=250"]


def test_load_then_require_is_the_parse_back_shape(session: Session) -> None:
    # The exact shape every declared_* parse-back now uses: load, then require.
    version = _version_with(session, "t-2", ["alpha=0.4"])
    got = require_declared(
        load_assumption_texts(session, version), "alpha=", pattern=_PAT, on_invalid=_Invalid
    )
    assert got == "0.4"
