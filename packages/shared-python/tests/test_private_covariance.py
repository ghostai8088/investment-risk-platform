"""SQLite-local unit/behavior tests for PPF-2 — the private-factor covariance block Ω_pp
(``risk.covariance.private``, the 19th governed number, §2.1 arc slice 2).

A fail-closed SIBLING of ``risk.covariance.sample``: it reuses the generic ``estimate_covariance``
kernel unchanged + the shared ``covariance_result`` table (``frequency=APPRAISAL``,
``run_type=COVARIANCE_PRIVATE``), consuming PPF-1 pure-private APPRAISAL return series. This module
grows across the PPF-2 steps; step 2 proves the model governance (the private registrar's
window-as-identity + conflicts) and the methodology referent.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.risk import (
    PRIVATE_COVARIANCE_METHODOLOGY_REF,
    ModelVersionConflictError,
    declared_private_window_observations,
    register_private_covariance_model,
)
from irp_shared.risk.bootstrap import WINDOW_ASSUMPTION_PREFIX

_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _model(session: Session, tenant: str, *, code_version: str = "risk-v1", window: int = 5) -> str:
    return register_private_covariance_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        window_observations=window,
    ).id


# ---------- model governance (window-as-identity + methodology referent) ----------
def test_private_model_registered_with_window_assumption_and_methodology(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant, window=5)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == PRIVATE_COVARIANCE_METHODOLOGY_REF
    assert declared_private_window_observations(session, version) == 5
    texts = [
        r.assumption_text
        for r in session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == mv_id)
        ).scalars()
    ]
    assert f"{WINDOW_ASSUMPTION_PREFIX}5" in texts
    assert sum(1 for t in texts if t.startswith(WINDOW_ASSUMPTION_PREFIX)) == 1
    # the block-diagonal-approx honesty is a recorded limitation (the verifier CLAIM-4 fold)
    limits = [
        r.limitation_text
        for r in session.execute(
            select(ModelLimitation).where(ModelLimitation.model_version_id == mv_id)
        ).scalars()
    ]
    assert any("APPROXIMATION" in t and "orthogonal-by-construction" in t for t in limits)


def test_private_register_idempotent_and_conflicts_on_window_or_code_version(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    first = _model(session, tenant, code_version="risk-v1", window=5)
    assert _model(session, tenant, code_version="risk-v1", window=5) == first  # idempotent
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v1", window=6)  # same label, new window
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v2", window=5)  # same label, new code
    with pytest.raises(ValueError):
        _model(session, tenant, window=1)  # the registration floor (N >= 2)


def test_private_covariance_is_a_distinct_model_code(session: Session) -> None:
    """The governance boundary is the model CODE — a private version is NEVER a public
    ``risk.covariance.sample`` identity (and vice-versa)."""
    from irp_shared.risk import PRIVATE_COVARIANCE_MODEL_CODE
    from irp_shared.risk.bootstrap import COVARIANCE_MODEL_CODE

    assert PRIVATE_COVARIANCE_MODEL_CODE == "risk.covariance.private"
    assert PRIVATE_COVARIANCE_MODEL_CODE != COVARIANCE_MODEL_CODE


# ---------- the methodology referent (the covariance-family precedent) ----------
def test_private_methodology_doc_exists_and_has_required_sections() -> None:
    doc = (_ROOT / PRIVATE_COVARIANCE_METHODOLOGY_REF).read_text()
    for section in (
        "## Purpose & applicability",
        "## Inputs & data policy",
        "## Formulas & numerical standards",
        "## Assumptions",
        "## Limitations",
        "## Validation / reproduction tests",
        "## Known limitations",
    ):
        assert section in doc, section
    assert "UNANNUALIZED" in doc
    assert "no pairwise deletion" in doc.lower()
    assert "block-diagonal" in doc.lower()  # the OD-PPF-2-B disclosed approximation


def test_private_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == PRIVATE_COVARIANCE_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).exists()
