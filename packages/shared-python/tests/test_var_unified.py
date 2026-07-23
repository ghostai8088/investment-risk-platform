"""SQLite-local unit/behavior tests for PPF-3 — the UNIFIED public+private parametric VaR
(``risk.var.parametric_unified``, the 20th governed number, §2.1 arc slice 3).

A NEW model CODE (the plain + total families stay byte-untouched) whose binder REPARTITIONS PA-4's
non-public variance: a pure-private-segment member's variance moves from the diagonal residual into
PPF-2's correlated Ω_pp block (no double-count). This module grows across the PPF-3 steps; step 2
proves the model governance (declared-parameter identity + conflicts) and the methodology referent.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.risk import (
    VAR_UNIFIED_METHODOLOGY_REF,
    ModelVersionConflictError,
    declared_unified_appraisal_days,
    register_var_parametric_unified_model,
)
from irp_shared.risk.bootstrap import APPRAISAL_DAYS_ASSUMPTION_PREFIX

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_APPRAISAL_DAYS = 91
_MAX_AGE = 400


def _model(
    session: Session,
    tenant: str,
    *,
    code_version: str = "risk-v1",
    confidence: str = "0.95",
    appraisal_days: int = _APPRAISAL_DAYS,
    max_estimate_age_days: int = _MAX_AGE,
) -> str:
    return register_var_parametric_unified_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        confidence_level=confidence,
        appraisal_days=appraisal_days,
        max_estimate_age_days=max_estimate_age_days,
    ).id


# ---------- model governance (declared-parameter identity + methodology referent) ----------
def test_unified_model_registered_with_declared_params_and_methodology(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant, appraisal_days=91)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == VAR_UNIFIED_METHODOLOGY_REF
    assert declared_unified_appraisal_days(session, version) == 91
    texts = [
        r.assumption_text
        for r in session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == mv_id)
        ).scalars()
    ]
    assert f"{APPRAISAL_DAYS_ASSUMPTION_PREFIX}91" in texts
    assert any("confidence_level=0.9500" == t for t in texts)
    # the REPARTITION honesty (the verifier's blocking fold) is a recorded assumption
    assert any("REPARTITION" in t and "double-count" in t for t in texts)
    # the block-diagonal + unlevered disclosures are recorded limitations
    limits = [
        r.limitation_text
        for r in session.execute(
            select(ModelLimitation).where(ModelLimitation.model_version_id == mv_id)
        ).scalars()
    ]
    assert any("Block-diagonal" in t for t in limits)
    assert any("UNLEVERED" in t for t in limits)


def test_unified_register_idempotent_and_conflicts(session: Session) -> None:
    tenant = str(uuid.uuid4())
    first = _model(session, tenant, appraisal_days=91)
    assert _model(session, tenant, appraisal_days=91) == first  # idempotent
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, appraisal_days=30)  # same label, different declaration
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, confidence="0.99")  # same label, different confidence
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v2")  # same label, different code


def test_unified_confidence_vocab_and_floors(session: Session) -> None:
    tenant = str(uuid.uuid4())
    with pytest.raises(ValueError):
        _model(session, tenant, confidence="0.777")  # not in the z vocabulary
    with pytest.raises(ValueError):
        _model(session, tenant, appraisal_days=0)  # the cadence floor
    with pytest.raises(ValueError):
        _model(session, tenant, max_estimate_age_days=0)  # the staleness-policy floor


def test_unified_is_a_distinct_model_code(session: Session) -> None:
    from irp_shared.risk import VAR_TOTAL_MODEL_CODE, VAR_UNIFIED_MODEL_CODE

    assert VAR_UNIFIED_MODEL_CODE == "risk.var.parametric_unified"
    assert VAR_UNIFIED_MODEL_CODE != VAR_TOTAL_MODEL_CODE


# ---------- the methodology referent ----------
def test_unified_methodology_doc_exists_and_has_required_sections() -> None:
    doc = (_ROOT / VAR_UNIFIED_METHODOLOGY_REF).read_text()
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
    assert "UNLEVERED" in doc
    assert "repartition" in doc.lower()  # the verifier's blocking fold
    assert "block-diagonal" in doc.lower()
    assert "Getmansky" in doc  # the √-time-on-desmoothed citation
    assert "Shepard" in doc  # the MSCI decomposition


def test_unified_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == VAR_UNIFIED_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).exists()
