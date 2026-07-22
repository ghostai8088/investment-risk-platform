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
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.marketdata.factor import FactorActor, capture_factor
from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.risk import (
    PRIVATE_COVARIANCE_METHODOLOGY_REF,
    ModelVersionConflictError,
    declared_private_window_observations,
    register_private_covariance_model,
)
from irp_shared.risk.bootstrap import WINDOW_ASSUMPTION_PREFIX
from irp_shared.risk.models import METRIC_TYPE_PURE_PRIVATE_PERIOD, PrivateFactorReturnResult
from irp_shared.snapshot import (
    PrivateCovarianceSnapshotError,
    build_private_covariance_snapshot,
)
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.snapshot.serialize import pure_private_return_content

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _private_segment(session: Session, tenant: str, code: str = "PE_GLOBAL") -> str:
    return capture_factor(
        session,
        factor_code=f"{code}-{uuid.uuid4().hex[:6]}",
        factor_source="PPF",
        factor_family="PRIVATE",
        frequency="APPRAISAL",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id


def _currency_factor(session: Session, tenant: str) -> str:
    return capture_factor(
        session,
        factor_code=f"FX-{uuid.uuid4().hex[:6]}",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id


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


# ---------- the PURE_PRIVATE_RETURN serializer (governed-row no-valid-axis pin flavor) ----------
def test_pure_private_return_content_pins_the_governed_row_shape() -> None:
    tenant, seg = str(uuid.uuid4()), str(uuid.uuid4())
    row = PrivateFactorReturnResult(
        id=str(uuid.uuid4()),
        tenant_id=tenant,
        calculation_run_id=str(uuid.uuid4()),
        input_snapshot_id=str(uuid.uuid4()),
        model_version_id=str(uuid.uuid4()),
        segment_factor_id=seg,
        metric_type=METRIC_TYPE_PURE_PRIVATE_PERIOD,
        period_start=date(2024, 12, 31),
        period_end=date(2025, 3, 31),
        metric_value=Decimal("0.012345678901"),
        member_count=2,
        period_count=None,  # None on PERIOD rows
        pooling_convention="EQUAL_WEIGHT",
        intercept_convention="RETAIN_ALPHA",
        min_members=1,
        system_from=datetime(2026, 4, 1, tzinfo=UTC),
    )
    content = pure_private_return_content(row)
    # the reconstruction keys the binder needs, at the 12dp column scale
    assert content["segment_factor_id"] == seg.lower()
    assert content["metric_type"] == METRIC_TYPE_PURE_PRIVATE_PERIOD
    assert content["period_start"] == "2024-12-31" and content["period_end"] == "2025-03-31"
    assert content["metric_value"] == "0.012345678901"
    assert content["period_count"] is None  # None-tolerant
    assert content["pooling_convention"] == "EQUAL_WEIGHT"
    # the mutable close-out/valid axis is NOT pinned (no record_version / valid_to)
    assert "record_version" not in content and "valid_to" not in content


# ---------- the builder fail-closed gates (BEFORE any write) ----------
# NB: the builder consumes explicit pure-private RUN ids (the proxy_weight/PPF-1 run-bound-input
# precedent — the RISK binder resolves each segment's latest run). The positive path + the
# non-PRIVATE/multi-segment/short-overlap gates need real PPF-1 runs and are proven end-to-end in
# the binder tests (test_private_covariance_binder / the PG chain).
def test_builder_refuses_sub_two_window() -> None:
    with pytest.raises(PrivateCovarianceSnapshotError, match="window_observations must be >= 2"):
        build_private_covariance_snapshot(
            None,  # never reached — the window check is first
            acting_tenant=str(uuid.uuid4()),
            actor=SnapshotActor(actor_id="a"),
            pure_private_run_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            window_observations=1,
        )


def test_builder_refuses_duplicate_and_sub_two_runs() -> None:
    dup = str(uuid.uuid4())
    with pytest.raises(PrivateCovarianceSnapshotError, match="duplicate pure-private run"):
        build_private_covariance_snapshot(
            None,
            acting_tenant=str(uuid.uuid4()),
            actor=SnapshotActor(actor_id="a"),
            pure_private_run_ids=[dup, dup],
            window_observations=2,
        )
    with pytest.raises(PrivateCovarianceSnapshotError, match=">= 2 distinct pure-private runs"):
        build_private_covariance_snapshot(
            None,
            acting_tenant=str(uuid.uuid4()),
            actor=SnapshotActor(actor_id="a"),
            pure_private_run_ids=[str(uuid.uuid4())],
            window_observations=2,
        )


def test_builder_refuses_run_with_no_pure_private_series(session: Session) -> None:
    # Two unknown run ids — each resolves to zero PURE_PRIVATE_PERIOD rows → fail-closed pre-write.
    with pytest.raises(PrivateCovarianceSnapshotError, match="no per-period result rows"):
        build_private_covariance_snapshot(
            session,
            acting_tenant=str(uuid.uuid4()),
            actor=SnapshotActor(actor_id="a"),
            pure_private_run_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            window_observations=2,
        )
