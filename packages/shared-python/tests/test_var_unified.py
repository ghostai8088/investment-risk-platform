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
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.risk import (
    VAR_UNIFIED_METHODOLOGY_REF,
    ModelVersionConflictError,
    VarActor,
    VarInputError,
    VarUnifiedKernelError,
    daily_omega,
    daily_residual_stdev,
    declared_unified_appraisal_days,
    private_block_variance,
    register_var_parametric_unified_model,
    run_var_unified,
    sigma_unified,
)
from irp_shared.risk.bootstrap import (
    APPRAISAL_DAYS_ASSUMPTION_PREFIX,
    VAR_TOTAL_CALENDAR_DAYS_PER_YEAR,
    VAR_TOTAL_TRADING_DAYS_PER_YEAR,
)
from irp_shared.snapshot import VAR_UNIFIED_BINDING_PREDICATE, SnapshotActor

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_APPRAISAL_DAYS = 91
_MAX_AGE = 400
_TRADING = VAR_TOTAL_TRADING_DAYS_PER_YEAR
_CALENDAR = VAR_TOTAL_CALENDAR_DAYS_PER_YEAR


def _omega(appraisal: dict[tuple[str, str], str], days: int = _APPRAISAL_DAYS):
    return daily_omega(
        {k: Decimal(v) for k, v in appraisal.items()},
        days,
        trading_days_per_year=_TRADING,
        calendar_days_per_year=_CALENDAR,
    )


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


# ---------- the unified kernel: the 1/d_t de-scale + the p'Ω·p quadratic form ----------
def test_daily_omega_descales_the_matrix_by_dt() -> None:
    d_t = float(_APPRAISAL_DAYS) * (float(_TRADING) / float(_CALENDAR))
    got = _omega({("a", "a"): "0.04", ("a", "b"): "0.01", ("b", "b"): "0.09"})
    assert float(got[("a", "a")]) == pytest.approx(0.04 / d_t, rel=1e-15)
    assert float(got[("a", "b")]) == pytest.approx(0.01 / d_t, rel=1e-15)
    assert float(got[("b", "b")]) == pytest.approx(0.09 / d_t, rel=1e-15)


def test_private_block_variance_is_the_quadratic_form() -> None:
    """p'Ω·p = Σ_s p_s²·Ω[s,s] + 2·Σ_{s<t} p_s·p_t·Ω[s,t], cross-checked against numpy."""
    import numpy as np

    om = _omega({("a", "a"): "0.04", ("a", "b"): "0.01", ("b", "b"): "0.09"})
    p = {"a": Decimal("100"), "b": Decimal("50")}
    got = private_block_variance(p, om)
    # numpy: p' M p with M the symmetric daily matrix
    d_t = float(_APPRAISAL_DAYS) * (float(_TRADING) / float(_CALENDAR))
    m = np.array([[0.04, 0.01], [0.01, 0.09]]) / d_t
    pv = np.array([100.0, 50.0])
    assert float(got) == pytest.approx(float(pv @ m @ pv), rel=1e-12)


def test_private_block_variance_uses_only_the_held_subblock() -> None:
    """A segment the portfolio does NOT hold (absent from p) contributes nothing (its rows/cols are
    dropped) — the principal sub-block."""
    om = _omega(
        {
            ("a", "a"): "0.04",
            ("a", "b"): "0.01",
            ("b", "b"): "0.09",
            ("a", "c"): "0.02",  # segment c is NOT held -> ignored
            ("c", "c"): "0.16",
        }
    )
    held = private_block_variance({"a": Decimal("100"), "b": Decimal("50")}, om)
    only_ab = private_block_variance(
        {"a": Decimal("100"), "b": Decimal("50")},
        _omega({("a", "a"): "0.04", ("a", "b"): "0.01", ("b", "b"): "0.09"}),
    )
    assert held == only_ab  # c's pairs did not leak in


def test_private_block_variance_refuses_uncovered_held_segment() -> None:
    """A held segment with no Ω diagonal entry fails closed (else it drops from the sum)."""
    with pytest.raises(VarUnifiedKernelError, match="absent from the pinned Omega_pp diagonal"):
        private_block_variance({"a": Decimal("100")}, _omega({("b", "b"): "0.09"}))


def test_sigma_unified_sums_the_three_legs() -> None:
    got = sigma_unified(Decimal("4"), Decimal("5"), Decimal("16"))
    assert float(got) == pytest.approx(5.0, rel=1e-40)  # sqrt(4+5+16)=sqrt(25)=5
    with pytest.raises(VarUnifiedKernelError) as exc:
        sigma_unified(Decimal("1"), Decimal("-3"), Decimal("0"))
    assert exc.value.reason == "negative-total-variance"


# ---------- the TWO decomposition guardrails (both FAIL under a naive additive formula) ----------
def test_kernel_reduction_single_segment_diagonal_equals_the_residual_form() -> None:
    """KERNEL IDENTITY (the repartition's numerical BASIS, not its enforcement): GIVEN
    ``Ω_pp[s,s] = σ_e²``, leg 2's single-member diagonal ``p²·Ω[s,s]/d_t`` equals the PA-4 residual
    form ``(MV·σ_e,daily)²`` — the arithmetic that lets leg 2 REPLACE leg 3. This is a conditional
    identity, NOT a claim about the real pipeline: there ``Ω[s,s]`` (pure-private sample variance,
    ÷(N−1)) and ``σ_e²`` (the OLS residual variance, ÷(N−k)) are DIFFERENT estimators, so a lone
    fund only APPROXIMATELY reduces to total VaR. The anti-double-count ENFORCEMENT (a member in leg
    2 XOR leg 3) lives in the binder — see the consume-path double-count refusal test below."""
    mv, sigma_e_period = Decimal("100"), Decimal("0.20")  # 0.04 = sigma_e^2
    private_leg = private_block_variance({"s": mv}, _omega({("s", "s"): "0.04"}))
    sigma_e_daily = daily_residual_stdev(
        sigma_e_period,
        Decimal(_APPRAISAL_DAYS),
        trading_days_per_year=_TRADING,
        calendar_days_per_year=_CALENDAR,
    )
    residual_leg = (mv * sigma_e_daily) * (mv * sigma_e_daily)
    # The identity is exact in real arithmetic; the two computation paths (direct /d_t vs
    # sqrt-then-square) agree far beyond the 20dp scale.
    q = Decimal("1E-20")
    assert private_leg.quantize(q) == residual_leg.quantize(q)


def test_kernel_cross_fund_block_carries_the_off_diagonal_co_movement() -> None:
    """KERNEL IDENTITY: for two single-member segments, the unified private block minus the
    total-VaR independent diagonals == the cross-fund covariance term 2·p_PE·p_PC·Ω[PE,PC]/d_t (the
    co-movement leg 2 carries). Canonical pair keys (a ≤ b): "pc" < "pe"."""
    p_pe, p_pc = Decimal("100"), Decimal("50")
    om = _omega({("pc", "pc"): "0.09", ("pe", "pe"): "0.04", ("pc", "pe"): "0.012"})
    unified_private = private_block_variance({"pe": p_pe, "pc": p_pc}, om)
    # total VaR treats the two funds' non-public variance as INDEPENDENT diagonals:
    total_diagonals = p_pe * p_pe * om[("pe", "pe")] + p_pc * p_pc * om[("pc", "pc")]
    cross_term = Decimal(2) * p_pe * p_pc * om[("pc", "pe")]
    assert unified_private - total_diagonals == cross_term


def test_private_block_variance_refuses_a_missing_held_pair() -> None:
    """The 4-finder MED: a held-held OFF-DIAGONAL absent from Ω_pp is refused, NOT silently summed
    as zero co-movement (parity with the public leg's full-pairwise coverage). Understating the
    cross term — the unified number's whole value — must fail closed."""
    from irp_shared.risk.var_unified_kernel import VarUnifiedKernelError

    with pytest.raises(VarUnifiedKernelError) as exc:  # both diagonals present, (pc,pe) absent
        private_block_variance(
            {"pe": Decimal("100"), "pc": Decimal("50")},
            _omega({("pc", "pc"): "0.09", ("pe", "pe"): "0.04"}),
        )
    assert exc.value.reason == "uncovered-pair"


# ---------- consume-path double-count refusal (the 4-finder HIGH: OD-3-G trust boundary) ----
_T0 = datetime(2024, 1, 1, tzinfo=UTC)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)


def _content_hash(content: dict) -> tuple[str, str]:
    from irp_shared.audit.hashing import sha256_hex
    from irp_shared.snapshot.serialize import serialize_content

    cc = serialize_content(content)
    return cc, sha256_hex(cc)


def _mint_unified_snapshot_with_instrument_in_both_legs(session: Session, tenant: str) -> str:
    """Hand-mint a unified-predicate VAR_INPUT snapshot pinning ONE instrument X in BOTH a
    REGRESSION proxy (leg 3) AND a MANUAL pure-private membership (leg 2) — the exact repartition
    violation the builder silently excludes but a consumed snapshot could smuggle. Fabricated ids:
    the disjointness gate fires DURING pin adjudication, before provenance re-resolution."""
    from types import SimpleNamespace

    from irp_shared.snapshot import COMPONENT_KIND_PROXY_MAPPING, COMPONENT_KIND_PROXY_WEIGHT
    from irp_shared.snapshot.service import _persist_snapshot

    fid, iid, seg = "f", "x", "s"
    run = str(uuid.uuid4())
    exposure = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "calculation_run_id": run,
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": _T0.isoformat(),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": iid,
        "factor_id": fid,
        "factor_code": "F",
        "factor_family": "CURRENCY",
        "base_currency": "USD",
        "mark_currency": "USD",
        "loading": "1.000000000000",
        "exposure_amount": "30000.000000",
    }
    daily_cov = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "calculation_run_id": run,
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": _T0.isoformat(),
        "factor_id_1": fid,
        "factor_id_2": fid,
        "statistic_type": "COVARIANCE",
        "return_type": "SIMPLE",
        "frequency": "DAILY",
        "n_observations": 4,
        "window_start": "2026-05-01",
        "window_end": "2026-05-25",
        "covariance_value": "0.00010000000000000000",
    }
    omega = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "calculation_run_id": str(uuid.uuid4()),
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": _T0.isoformat(),
        "factor_id_1": seg,
        "factor_id_2": seg,
        "statistic_type": "COVARIANCE",
        "return_type": "SIMPLE",
        "frequency": "APPRAISAL",
        "n_observations": 5,
        "window_start": "2024-12-31",
        "window_end": "2025-12-31",
        "covariance_value": "0.04000000000000000000",
    }

    def _mapping(factor_id: str, method: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant,
            "private_instrument_id": iid,
            "factor_id": factor_id,
            "weight": "0.500000000000",
            "mapping_method": method,
            "valid_from": _T0.isoformat(),
            "system_from": _T0.isoformat(),
            "record_version": 1,
        }

    weight = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "calculation_run_id": str(uuid.uuid4()),
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": iid,
        "source_desmoothed_run_id": str(uuid.uuid4()),
        "metric_type": "ESTIMATION_SUMMARY",
        "factor_id": None,
        "metric_value": "0.800000000000",
        "std_error": None,
        "n_observations": 6,
        "n_regressors": 1,
        "residual_stdev": "0.20",
        "min_observations": 4,
        "series_currency": "USD",
        "system_from": _T0.isoformat(),
    }
    plan = [
        ("FACTOR_EXPOSURE", "factor_exposure_result", exposure),
        ("COVARIANCE", "covariance_result", daily_cov),
        ("COVARIANCE", "covariance_result", omega),
        (COMPONENT_KIND_PROXY_MAPPING, "proxy_mapping", _mapping(fid, "REGRESSION")),  # leg 3
        (
            COMPONENT_KIND_PROXY_MAPPING,
            "proxy_mapping",
            _mapping(seg, "MANUAL"),
        ),  # leg 2 — SAME iid
        (COMPONENT_KIND_PROXY_WEIGHT, "proxy_weight_estimate_result", weight),
    ]
    specs = []
    for kind, ttype, content in plan:
        anchor = SimpleNamespace(
            id=content["id"], valid_from=None, system_from=_T0, record_version=None
        )
        cc, h = _content_hash(content)
        specs.append((kind, ttype, anchor, cc, h))
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        specs=specs,
        label="",
        purpose="VAR_INPUT",
        as_of_valid_at=_VALID_AT,
        as_of_known_at=_KNOWN_AT,
        as_of_valuation_date=_VALID_AT.date(),
        binding_predicate_version=VAR_UNIFIED_BINDING_PREDICATE,
    )
    return str(header.id)


def test_consume_path_refuses_a_double_counted_instrument(session: Session) -> None:
    """OD-3-G at the consume boundary (the 4-finder HIGH): a consumed unified snapshot pinning an
    instrument in BOTH a REGRESSION residual (leg 3) and a MANUAL pure-private membership (leg 2)
    would count its variance twice — the ratify-blocking double-count. The binder REFUSES it (the
    builder's repartition skip is re-enforced where the adjudicator (not builder) is trusted)."""
    tenant = str(uuid.uuid4())
    snapshot_id = _mint_unified_snapshot_with_instrument_in_both_legs(session, tenant)
    with pytest.raises(VarInputError, match="BOTH a REGRESSION residual"):
        run_var_unified(
            session,
            acting_tenant=tenant,
            actor=VarActor(actor_id="analyst"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=_model(session, tenant),
            snapshot_id=snapshot_id,
        )
