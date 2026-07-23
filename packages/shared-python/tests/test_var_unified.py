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
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.risk import (
    VAR_UNIFIED_METHODOLOGY_REF,
    ModelVersionConflictError,
    VarUnifiedKernelError,
    daily_omega,
    daily_residual_stdev,
    declared_unified_appraisal_days,
    private_block_variance,
    register_var_parametric_unified_model,
    sigma_unified,
)
from irp_shared.risk.bootstrap import (
    APPRAISAL_DAYS_ASSUMPTION_PREFIX,
    VAR_TOTAL_CALENDAR_DAYS_PER_YEAR,
    VAR_TOTAL_TRADING_DAYS_PER_YEAR,
)

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
def test_reduction_a_lone_private_fund_equals_the_total_residual() -> None:
    """OD-3-G coherence: for a SINGLE private fund (one member, one segment), the pure-private leg
    equals what PA-4's diagonal residual would be — so the unified number reduces to ≈ total VaR.
    Ω_pp[s,s] = Var(pp_s) = σ_e² for a single member, so p²·Ω[s,s]/d_t == (MV·σ_e,daily)²."""
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
    # sqrt-then-square) agree far beyond the 20dp scale. leg 2 REPLACES leg 3, no double-count.
    q = Decimal("1E-20")
    assert private_leg.quantize(q) == residual_leg.quantize(q)


def test_cross_fund_a_two_segment_book_differs_by_the_off_diagonal() -> None:
    """The genuinely-new quantity: for two single-member segments, the unified private block minus
    the total-VaR independent diagonals == exactly the cross-fund covariance term
    2·p_PE·p_PC·Ω[PE,PC]/d_t (the co-movement total VaR misses)."""
    p_pe, p_pc = Decimal("100"), Decimal("50")
    om = _omega({("pe", "pe"): "0.04", ("pc", "pc"): "0.09", ("pe", "pc"): "0.012"})
    unified_private = private_block_variance({"pe": p_pe, "pc": p_pc}, om)
    # total VaR treats the two funds' non-public variance as INDEPENDENT diagonals:
    total_diagonals = p_pe * p_pe * om[("pe", "pe")] + p_pc * p_pc * om[("pc", "pc")]
    cross_term = Decimal(2) * p_pe * p_pc * om[("pe", "pc")]
    assert unified_private - total_diagonals == cross_term
