"""SQLite-local unit/behavior tests for P3-4 covariance matrices (the third governed RISK number,
ENT-051 — sample v1).

RLS is a no-op on SQLite (FORCE-RLS isolation + the P0001 trigger live in
``test_covariance_pg.py``); here we prove: the pure kernel against **hand-computed exact
references** (rational arithmetic independent of BOTH implementations) + an independent
**``numpy.cov(ddof=1)`` cross-check** + an **eigenvalue PSD property test** (the dual-path
verification standing rule's first mandatory application — numpy is TEST-ONLY); the canonical
unordered-pair grain incl. the diagonal (``F·(F+1)/2`` rows; symmetry by construction); the
window-as-version-identity model governance (OD-P3-4-G: declared ``window_observations`` parsed
from assumptions; same-label different window OR code_version conflicts); the FACTOR+FACTOR_RETURN
snapshot pinning + snapshot-only compute (**invariant under a post-pin vendor supersede AND
correction** — TR-09); the fail-closed window/alignment gates on BOTH entry paths (short overlap
= pre-create refusal, zero runs); the defensive post-create FAILED gate; CALC.RUN_* audit (+ NO
RISK.* code); lineage; the append-only ORM guard; entitlement REUSE parity; the methodology doc;
the load-bearing scope fences (incl. **no runtime numpy anywhere in ``irp_shared``**); and the
migration head.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES
from irp_shared.lineage.models import (
    EDGE_KIND_DEPENDENCY,
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    SOURCE_TYPE_DATA_SNAPSHOT,
    LineageEdge,
)
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    correct_factor_return,
    resolve_factor,
    supersede_factor_return,
    update_factor,
)
from irp_shared.model.models import ModelAssumption, ModelVersion
from irp_shared.model.service import UnregisteredModelError
from irp_shared.models import Base
from irp_shared.risk import (
    CovarianceActor,
    CovarianceInputError,
    CovarianceKernelError,
    CovarianceResult,
    FactorSeriesPin,
    ModelVersionConflictError,
    WrongModelVersionError,
    declared_window_observations,
    estimate_covariance,
    list_covariances,
    register_covariance_model,
    register_factor_exposure_model,
    run_covariance,
)
from irp_shared.risk.bootstrap import (
    COVARIANCE_METHODOLOGY_REF,
    WINDOW_ASSUMPTION_PREFIX,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_RETURN,
    PURPOSE_COVARIANCE_INPUT,
    SNAPSHOT_COMPONENT_KINDS,
    CovarianceSnapshotError,
    DatasetSnapshot,
    SnapshotActor,
    SnapshotNotFound,
    build_covariance_snapshot,
    build_snapshot,
    list_components,
    resolve_snapshot,
    verify_snapshot,
)
from irp_shared.snapshot.models import PURPOSE_TEST

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
ACTOR = CovarianceActor(actor_id="analyst")
_Q20 = Decimal(1).scaleb(-20)

#: The aligned 4-observation window used across the full-stack tests.
D1, D2, D3, D4 = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
#: The 3-factor / 4-observation HAND-COMPUTED reference (rational arithmetic, independent of both
#: the kernel and numpy): all three means = 0.025; demeaned A = (-15,-5,5,15)e-3,
#: B = (15,5,-5,-15)e-3, C = (-5,-15,15,5)e-3. Σ(dA²) = Σ(dB²) = Σ(dC²) = 0.0005 ⇒ var = 0.0005/3
#: = 1/6000; Σ(dA·dB) = -0.0005 ⇒ cov = -1/6000; Σ(dA·dC) = +0.0003 ⇒ cov = +1/10000;
#: Σ(dB·dC) = -0.0003 ⇒ cov = -1/10000. 1/6000 HALF_UP at 20dp = 0.00016666666666666667.
SERIES_A = ["0.01", "0.02", "0.03", "0.04"]
SERIES_B = ["0.04", "0.03", "0.02", "0.01"]
SERIES_C = ["0.02", "0.01", "0.04", "0.03"]
REF_VAR = Decimal("0.00016666666666666667")  # 1/6000 quantized HALF_UP @ 20dp
REF_COV_AB = Decimal("-0.00016666666666666667")  # -1/6000
REF_COV_AC = Decimal("0.00010000000000000000")  # +1/10000 exact
REF_COV_BC = Decimal("-0.00010000000000000000")  # -1/10000 exact


@pytest.fixture
def session() -> Session:
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


def _pin(
    fid: str, code: str, values: list[str], dates: list[date] | None = None
) -> FactorSeriesPin:
    ds = dates or [D1, D2, D3, D4][: len(values)]
    return FactorSeriesPin(
        id=fid, factor_code=code, rows=tuple(zip(ds, [Decimal(v) for v in values], strict=True))
    )


def _factor(db: Session, tenant: str, code: str) -> str:
    return capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id


def _returns(
    db: Session, tenant: str, factor_id: str, values: list[str], dates: list[date] | None = None
) -> None:
    ds = dates or [D1, D2, D3, D4][: len(values)]
    factor = resolve_factor(db, factor_id, acting_tenant=tenant)
    for d, v in zip(ds, values, strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        )
    db.flush()


def _abc(db: Session, tenant: str) -> list[str]:
    """Three factors with the aligned hand-reference windows; returns [fA, fB, fC]."""
    ids = []
    for code, values in (("F_A", SERIES_A), ("F_B", SERIES_B), ("F_C", SERIES_C)):
        fid = _factor(db, tenant, code)
        _returns(db, tenant, fid, values)
        ids.append(fid)
    return ids


def _model(db: Session, tenant: str, code_version: str = "risk-v1", window: int = 4) -> str:
    return register_covariance_model(
        db,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        window_observations=window,
    ).id


def _run(db: Session, tenant: str, mv: str, factor_ids: list[str] | None, **kw):  # noqa: ANN202
    # as_of_valid_at is a BUILD-mode argument: never sent alongside snapshot_id (the P3-C1
    # ambiguity gate refuses both-modes input).
    if factor_ids is not None and "as_of_valid_at" not in kw:
        kw["as_of_valid_at"] = VALID_AT
    return run_covariance(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        factor_ids=factor_ids,
        **kw,
    )


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "COVARIANCE")
    ).scalar_one()


def _count_results(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CovarianceResult)
        .where(CovarianceResult.tenant_id == tenant)
    ).scalar_one()


# ---------- (1) pure kernel — the dual-path verification (hand refs + numpy + eigenvalues) -----


def test_kernel_matches_hand_computed_references_exactly() -> None:
    out = estimate_covariance(
        [_pin("a", "A", SERIES_A), _pin("b", "B", SERIES_B), _pin("c", "C", SERIES_C)]
    )
    assert out[("a", "a")] == REF_VAR
    assert out[("b", "b")] == REF_VAR
    assert out[("c", "c")] == REF_VAR
    assert out[("a", "b")] == REF_COV_AB
    assert out[("a", "c")] == REF_COV_AC
    assert out[("b", "c")] == REF_COV_BC
    assert len(out) == 6  # F·(F+1)/2 for F = 3


def test_kernel_unbiased_n_minus_1_denominator() -> None:
    # Two observations, deviations ±0.005 each: Σ(d²) = 0.00005; /(N−1)=1 NOT /N=2.
    out = estimate_covariance([_pin("a", "A", ["0.01", "0.02"]), _pin("b", "B", ["0.02", "0.01"])])
    assert out[("a", "a")] == Decimal("0.00005000000000000000")
    assert out[("a", "b")] == Decimal("-0.00005000000000000000")


def test_kernel_canonical_pair_ordering_including_diagonal() -> None:
    # Ids chosen so lexicographic != insertion order; every key is (min, max) lowercase.
    out = estimate_covariance([_pin("ZZ-9", "Z", SERIES_A), _pin("AA-1", "A", SERIES_B)])
    assert set(out.keys()) == {("aa-1", "aa-1"), ("aa-1", "zz-9"), ("zz-9", "zz-9")}
    for k1, k2 in out:
        assert k1 <= k2


def test_kernel_duplicate_ids_refused() -> None:
    # Duplicate ids (incl. case-variants of one GUID) would silently collapse the output dict
    # below F*(F+1)/2 entries (the 2026-07 review finding) — the kernel refuses instead.
    with pytest.raises(CovarianceKernelError, match="duplicate series ids"):
        estimate_covariance([_pin("x", "A", SERIES_A), _pin("x", "B", SERIES_B)])
    with pytest.raises(CovarianceKernelError, match="duplicate series ids"):
        estimate_covariance([_pin("aa-1", "A", SERIES_A), _pin("AA-1", "B", SERIES_B)])


def test_kernel_magnitude_out_of_range_raises_kernel_error() -> None:
    # |cov| >= 1e30 cannot be quantized to 20dp within the prec-50 context — the kernel maps the
    # raw decimal.InvalidOperation to its own error class (standalone safety; unreachable via
    # governed capture, whose Numeric(20,12) caps |r| < 1e8 => |cov| <= ~8e16).
    rows_a = ((D1, Decimal("2e15")), (D2, Decimal(0)))
    huge = [
        FactorSeriesPin(id="a", factor_code="A", rows=rows_a),
        FactorSeriesPin(id="b", factor_code="B", rows=rows_a),
    ]
    with pytest.raises(CovarianceKernelError, match="out of range"):
        estimate_covariance(huge)


def test_kernel_negative_zero_normalized() -> None:
    # An off-diagonal accumulator in (-5e-21, 0) quantizes to -0E-20; PG numeric drops the sign
    # while SQLite TEXT keeps it — the kernel normalizes to +0 so both engines store one value.
    a = FactorSeriesPin(id="a", factor_code="A", rows=((D1, Decimal("0")), (D2, Decimal("1e-10"))))
    b = FactorSeriesPin(id="b", factor_code="B", rows=((D1, Decimal("0")), (D2, Decimal("-8e-11"))))
    out = estimate_covariance([a, b])
    off = out[("a", "b")]
    assert off == 0
    assert not off.is_signed()  # -0 would round-trip differently across engines


def test_kernel_floors_and_misalignment_raise() -> None:
    with pytest.raises(CovarianceKernelError):
        estimate_covariance([_pin("a", "A", SERIES_A)])  # < 2 series
    with pytest.raises(CovarianceKernelError):
        estimate_covariance([_pin("a", "A", ["0.01"]), _pin("b", "B", ["0.02"])])  # N < 2
    with pytest.raises(CovarianceKernelError):
        estimate_covariance(
            [
                _pin("a", "A", ["0.01", "0.02"], [D1, D2]),
                _pin("b", "B", ["0.01", "0.02"], [D1, D3]),  # misaligned dates
            ]
        )


def test_kernel_quantizes_half_up_to_20dp() -> None:
    out = estimate_covariance([_pin("a", "A", SERIES_A), _pin("b", "B", SERIES_B)])
    for v in out.values():
        assert v == v.quantize(_Q20)
    # 1/6000 is non-terminating: the 21st digit sequence (6̄) rounds the 20th UP to …67.
    assert str(out[("a", "a")]).endswith("67")


def test_kernel_numpy_cross_check_seeded_random() -> None:
    # The independent-implementation leg (numpy is TEST-ONLY). Fixed seed — QS-18 spirit.
    import numpy as np

    rng = np.random.default_rng(20260707)
    data = rng.normal(0.0, 0.01, size=(4, 30)).round(12)  # 4 factors × 30 obs, 12dp like capture
    dates = [D1 + timedelta(days=i) for i in range(30)]
    pins = [_pin(f"f{i}", f"F{i}", [f"{x:.12f}" for x in data[i]], dates) for i in range(4)]
    out = estimate_covariance(pins)
    ref = np.cov(data, ddof=1)
    for i in range(4):
        for j in range(4):
            a, b = sorted((f"f{i}", f"f{j}"))
            got = float(out[(a, b)])
            want = float(ref[i][j])
            assert abs(got - want) <= 1e-9 * max(abs(want), 1e-300), (i, j, got, want)


def test_kernel_psd_eigenvalue_property() -> None:
    # PSD by Gram construction; verify numerically: λ_min ≥ −1e-12·trace (quantization O(1e-20)).
    import numpy as np

    cases = [
        [_pin("a", "A", SERIES_A), _pin("b", "B", SERIES_B), _pin("c", "C", SERIES_C)],
    ]
    rng = np.random.default_rng(42)
    for f_count, n_obs in ((3, 10), (5, 25), (8, 60)):
        data = rng.normal(0.0, 0.02, size=(f_count, n_obs)).round(12)
        dates = [D1 + timedelta(days=i) for i in range(n_obs)]
        cases.append(
            [_pin(f"f{i}", f"F{i}", [f"{x:.12f}" for x in data[i]], dates) for i in range(f_count)]
        )
    for pins in cases:
        out = estimate_covariance(pins)
        ids = sorted({p.id.lower() for p in pins})
        mat = np.array([[float(out[tuple(sorted((r, c)))]) for c in ids] for r in ids])
        eig = np.linalg.eigvalsh(mat)
        assert eig.min() >= -1e-12 * mat.trace(), (len(ids), eig.min())


# ---------- (2) model governance (window-as-version-identity, OD-P3-4-G) ----------


def test_model_registered_with_window_assumption_and_methodology(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant, window=4)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == COVARIANCE_METHODOLOGY_REF
    assert declared_window_observations(session, version) == 4
    texts = [
        r.assumption_text
        for r in session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == mv_id)
        ).scalars()
    ]
    assert f"{WINDOW_ASSUMPTION_PREFIX}4" in texts
    assert sum(1 for t in texts if t.startswith(WINDOW_ASSUMPTION_PREFIX)) == 1


def test_register_idempotent_and_conflicts_on_window_or_code_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    first = _model(session, tenant, code_version="risk-v1", window=4)
    assert _model(session, tenant, code_version="risk-v1", window=4) == first  # idempotent
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v1", window=5)  # same label, new window
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v2", window=4)  # same label, new code
    with pytest.raises(ValueError):
        _model(session, tenant, window=1)  # the registration floor


def test_unregistered_and_wrong_family_model_refused_zero_run(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    with pytest.raises(UnregisteredModelError):
        _run(session, tenant, str(uuid.uuid4()), factors)
    # A registered version of a DIFFERENT model family must be refused (CTRL-003 identity).
    fx_mv = register_factor_exposure_model(
        session, tenant_id=tenant, actor_id="analyst", code_version="risk-v1"
    ).id
    with pytest.raises(WrongModelVersionError):
        _run(session, tenant, fx_mv, factors)
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


# ---------- (3) positive correctness (full stack over pinned windows) ----------


def test_full_stack_matches_hand_references(session: Session) -> None:
    tenant = str(uuid.uuid4())
    f_a, f_b, f_c = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, [f_a, f_b, f_c])
    assert result.status == RunStatus.COMPLETED.value
    assert len(result.rows) == 6  # F·(F+1)/2
    by_codes = {(r.factor_code_1, r.factor_code_2): r.covariance_value for r in result.rows}
    # Diagonal = the variances (identical by the reference construction).
    diag = [r for r in result.rows if r.factor_id_1 == r.factor_id_2]
    assert len(diag) == 3 and all(r.covariance_value == REF_VAR for r in diag)
    off = {frozenset(k): v for k, v in by_codes.items() if k[0] != k[1]}
    assert off[frozenset({"F_A", "F_B"})] == REF_COV_AB
    assert off[frozenset({"F_A", "F_C"})] == REF_COV_AC
    assert off[frozenset({"F_B", "F_C"})] == REF_COV_BC
    for r in result.rows:
        assert r.factor_id_1 <= r.factor_id_2  # canonical stored order
        assert r.statistic_type == "COVARIANCE"
        assert r.return_type == "SIMPLE" and r.frequency == "DAILY"
        assert r.n_observations == 4
        assert r.window_start == D1 and r.window_end == D4
        assert r.covariance_value == r.covariance_value.quantize(_Q20)


def test_window_selects_most_recent_common_dates(session: Session) -> None:
    # Factor A has 6 dates, B has the LAST 4 → the intersection's most recent 3 for window=3.
    tenant = str(uuid.uuid4())
    d0 = date(2026, 5, 24)
    d_all = [d0 + timedelta(days=i) for i in range(6)]
    f_a = _factor(session, tenant, "F_A")
    _returns(session, tenant, f_a, ["0.01", "0.02", "0.03", "0.01", "0.02", "0.03"], d_all)
    f_b = _factor(session, tenant, "F_B")
    _returns(session, tenant, f_b, ["0.03", "0.01", "0.02", "0.01"], d_all[2:])
    mv = _model(session, tenant, window=3)
    result = _run(session, tenant, mv, [f_a, f_b])
    assert result.status == RunStatus.COMPLETED.value
    row = result.rows[0]
    assert row.window_start == d_all[3] and row.window_end == d_all[5]
    assert row.n_observations == 3


# ---------- (4) snapshot pinning + reproducibility (TR-09) ----------


def test_component_kind_minted_and_pin_shapes(session: Session) -> None:
    assert COMPONENT_KIND_FACTOR_RETURN in SNAPSHOT_COMPONENT_KINDS
    tenant = str(uuid.uuid4())
    f_a, f_b, f_c = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, [f_a, f_b, f_c])
    snapshot_id = result.run.input_snapshot_id
    header = resolve_snapshot(session, snapshot_id, acting_tenant=tenant)
    assert header.purpose == PURPOSE_COVARIANCE_INPUT
    assert header.as_of_valuation_date == D4  # the window end
    comps = list_components(session, snapshot_id=snapshot_id, acting_tenant=tenant)
    kinds = [c.component_kind for c in comps]
    assert kinds.count(COMPONENT_KIND_FACTOR) == 3
    assert kinds.count(COMPONENT_KIND_FACTOR_RETURN) == 3
    for c in comps:
        assert c.target_entity_type == "factor"  # the series parent for BOTH kinds
    v = verify_snapshot(session, snapshot_id=snapshot_id, acting_tenant=tenant)
    assert v.ok and v.component_count == 6


def test_invariant_under_post_pin_supersede_and_correction(session: Session) -> None:
    tenant = str(uuid.uuid4())
    f_a, f_b, f_c = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    first = _run(session, tenant, mv, [f_a, f_b, f_c])
    factor_a = resolve_factor(session, f_a, acting_tenant=tenant)
    # A vendor SUPERSEDE of one window return AND a CORRECTION of another, both post-pin.
    supersede_factor_return(
        session,
        factor_a,
        return_date=D2,
        return_value=Decimal("0.99"),
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        effective_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    correct_factor_return(
        session,
        factor_a,
        return_date=D3,
        return_value=Decimal("0.88"),
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
    )
    session.flush()
    second = run_covariance(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=first.run.input_snapshot_id,
    )
    assert second.status == RunStatus.COMPLETED.value
    assert [(r.factor_id_1, r.factor_id_2, r.covariance_value) for r in second.rows] == [
        (r.factor_id_1, r.factor_id_2, r.covariance_value) for r in first.rows
    ]
    # The pinned FR windows stay BYTE-STABLE under both (immutable version content; TR-09).
    v = verify_snapshot(session, snapshot_id=first.run.input_snapshot_id, acting_tenant=tenant)
    assert v.ok


def test_factor_amend_drifts_definition_pin_not_series_pin(session: Session) -> None:
    tenant = str(uuid.uuid4())
    f_a, f_b, f_c = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    first = _run(session, tenant, mv, [f_a, f_b, f_c])
    update_factor(
        session,
        resolve_factor(session, f_a, acting_tenant=tenant),
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        description="amended after the run",
    )
    session.flush()
    v = verify_snapshot(session, snapshot_id=first.run.input_snapshot_id, acting_tenant=tenant)
    assert not v.ok  # the EV amend IS visible (record_version in the FACTOR pin content)
    comps = {
        c.id: c
        for c in list_components(
            session, snapshot_id=first.run.input_snapshot_id, acting_tenant=tenant
        )
    }
    for cid in v.drifted_components:
        assert comps[cid].component_kind == COMPONENT_KIND_FACTOR  # the series pin stays stable


def test_determinism_same_snapshot_and_consume_equals_build(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    first = _run(session, tenant, mv, factors)
    second = run_covariance(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=first.run.input_snapshot_id,
    )
    assert [(r.factor_id_1, r.factor_id_2, r.covariance_value) for r in first.rows] == [
        (r.factor_id_1, r.factor_id_2, r.covariance_value) for r in second.rows
    ]


def test_valid_time_cut_honored_without_known_at(session: Session) -> None:
    # The 2026-07 review fix: with a BACKDATED as_of_valid_at and a LATER valid-time supersede,
    # the builder must pin the version VALID AT the declared instant (v1), not the current head
    # (v2) — with or without as_of_known_at (the frozen header cutoffs reproduce the pin).
    tenant = str(uuid.uuid4())
    f_a, f_b, f_c = _abc(session, tenant)
    supersede_factor_return(
        session,
        resolve_factor(session, f_a, acting_tenant=tenant),
        return_date=D2,
        return_value=Decimal("0.99"),
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        effective_at=datetime(2026, 6, 2, tzinfo=UTC),  # AFTER the backdated valid_at below
    )
    session.flush()
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, [f_a, f_b, f_c], as_of_valid_at=VALID_AT)  # 2026-06-01
    assert result.status == RunStatus.COMPLETED.value
    import json as _json

    comps = list_components(session, snapshot_id=result.run.input_snapshot_id, acting_tenant=tenant)
    pinned_a = next(
        _json.loads(c.captured_content)
        for c in comps
        if c.component_kind == COMPONENT_KIND_FACTOR_RETURN
        and _json.loads(c.captured_content)["factor_code"] == "F_A"
    )
    d2_value = next(
        r["return_value"] for r in pinned_a["rows"] if r["return_date"] == D2.isoformat()
    )
    assert d2_value == "0.020000000000"  # v1 (valid at 2026-06-01), NOT the 0.99 head
    diag = [r for r in result.rows if r.factor_id_1 == r.factor_id_2]
    assert all(r.covariance_value == REF_VAR for r in diag)


def test_lineage_one_edge_per_pinned_factor(session: Session) -> None:
    # A factor is pinned under TWO kinds (FACTOR + FACTOR_RETURN) but is ONE input — exactly one
    # snapshot->factor edge per factor (the 2026-07 review fix: the per-spec loop wrote two).
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, factors)
    edges = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_DATA_SNAPSHOT,
                LineageEdge.source_id == result.run.input_snapshot_id,
                LineageEdge.target_entity_type == "factor",
            )
        )
        .scalars()
        .all()
    )
    assert len(edges) == 3  # one per factor, not one per component


# ---------- (5) window/alignment fail-closed (pre-create refusals; zero run/rows) ----------


def test_short_common_window_refused_before_any_write(session: Session) -> None:
    tenant = str(uuid.uuid4())
    f_a = _factor(session, tenant, "F_A")
    _returns(session, tenant, f_a, SERIES_A)  # 4 dates
    f_b = _factor(session, tenant, "F_B")
    _returns(session, tenant, f_b, ["0.01", "0.02", "0.03"], [D1, D2, D3])  # only 3
    mv = _model(session, tenant, window=4)
    snaps_before = session.execute(select(func.count()).select_from(DatasetSnapshot)).scalar_one()
    with pytest.raises(CovarianceSnapshotError):
        _run(session, tenant, mv, [f_a, f_b])
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0
    snaps_after = session.execute(select(func.count()).select_from(DatasetSnapshot)).scalar_one()
    assert snaps_after == snaps_before  # refused BEFORE any snapshot write


def test_gap_date_in_one_factor_refuses(session: Session) -> None:
    # B has returns on D1, D2, D4 (a hole at D3): only 3 common dates for window=4.
    tenant = str(uuid.uuid4())
    f_a = _factor(session, tenant, "F_A")
    _returns(session, tenant, f_a, SERIES_A)
    f_b = _factor(session, tenant, "F_B")
    _returns(session, tenant, f_b, ["0.01", "0.02", "0.04"], [D1, D2, D4])
    mv = _model(session, tenant, window=4)
    with pytest.raises(CovarianceSnapshotError):
        _run(session, tenant, mv, [f_a, f_b])
    assert _count_runs(session, tenant) == 0


def test_missing_inputs_and_bad_factor_lists_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    for kw in (
        {"code_version": ""},
        {"environment_id": ""},
        {"model_version_id": ""},
    ):
        with pytest.raises(CovarianceInputError):
            run_covariance(
                session,
                acting_tenant=tenant,
                actor=ACTOR,
                **{
                    "code_version": "risk-v1",
                    "environment_id": "ci",
                    "model_version_id": mv,
                    "factor_ids": factors,
                    **kw,
                },
            )
    with pytest.raises(CovarianceInputError):
        _run(session, tenant, mv, None)  # neither factor_ids nor snapshot_id
    with pytest.raises(CovarianceInputError):
        _run(session, tenant, mv, [factors[0]])  # < 2 factors
    with pytest.raises(CovarianceInputError):
        _run(session, tenant, mv, [factors[0], factors[0], factors[1]])  # duplicates
    with pytest.raises(CovarianceInputError):
        # A case-variant spelling of the SAME GUID is the same factor (PG resolves GUIDs
        # case-insensitively) — refused as a duplicate, never an IntegrityError (2026-07 review).
        _run(session, tenant, mv, [factors[0].upper(), factors[0], factors[1]])
    assert _count_runs(session, tenant) == 0


def test_cross_tenant_factor_refused(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    foreign = _factor(session, other, "F_X")
    _returns(session, other, foreign, SERIES_A)
    f_a = _factor(session, tenant, "F_A")
    _returns(session, tenant, f_a, SERIES_A)
    mv = _model(session, tenant, window=4)
    from irp_shared.marketdata.factor import FactorNotVisible

    with pytest.raises(FactorNotVisible):
        _run(session, tenant, mv, [f_a, foreign])
    assert _count_runs(session, tenant) == 0


def test_consume_path_refuses_wrong_window_snapshot(session: Session) -> None:
    # A well-formed COVARIANCE_INPUT snapshot with N=2 (built via the raw builder args) cannot
    # drive a run whose registered version declares N=4 — the adjudication gate (OD-P3-4-H).
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    wrong = build_covariance_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        factor_ids=factors,
        window_observations=2,
        as_of_valid_at=VALID_AT,
    )
    mv = _model(session, tenant, window=4)
    with pytest.raises(CovarianceInputError):
        _run(session, tenant, mv, None, snapshot_id=wrong.id)
    assert _count_runs(session, tenant) == 0


def _portfolio_snapshot(session: Session, tenant: str, purpose: str):  # noqa: ANN202
    """A generic P2-1 portfolio snapshot with an in-vocab ``purpose`` — the wrong-flavor probe
    (the P3-3 review-regression construction)."""
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
    from irp_shared.portfolio import PortfolioActor, create_portfolio
    from irp_shared.position import create_position
    from irp_shared.position.service import PositionActor
    from irp_shared.reference.instrument import create_instrument
    from irp_shared.reference.models import Currency
    from irp_shared.reference.service import ReferenceActor
    from irp_shared.valuation import create_valuation
    from irp_shared.valuation.service import ValuationActor

    session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=T0))
    session.flush()
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code="WF",
        name="wf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        session,
        tenant_id=tenant,
        code="WF-I0",
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("100"),
        valid_from=T0,
    )
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=date(2026, 6, 1),
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal("10.00"),
        currency_code="USD",
        valid_from=T0,
    )
    return build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=purpose,
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
    )


def test_consume_path_refuses_wrong_purpose_snapshot(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    wrong = _portfolio_snapshot(session, tenant, PURPOSE_TEST)
    with pytest.raises(CovarianceInputError, match="purpose"):
        _run(session, tenant, mv, None, snapshot_id=wrong.id)
    assert _count_runs(session, tenant) == 0


def test_consume_path_refuses_wrong_flavor_snapshot(session: Session) -> None:
    # A COVARIANCE_INPUT-purposed snapshot with ZERO FACTOR_RETURN series (mintable via the
    # generic builder) must be a pre-create refusal — NOT a COMPLETED zero-row governed run
    # (the P3-3 review-regression class, applied to this slice's adjudication).
    tenant = str(uuid.uuid4())
    _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    wrong = _portfolio_snapshot(session, tenant, PURPOSE_COVARIANCE_INPUT)
    with pytest.raises(CovarianceInputError, match="FACTOR_RETURN"):
        _run(session, tenant, mv, None, snapshot_id=wrong.id)
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


def _mint_covariance_snapshot(
    session: Session, tenant: str, series: list[dict], factor_pins: list[dict] | None = None
):  # noqa: ANN202
    """Hand-mint a COVARIANCE_INPUT snapshot with ARBITRARY pinned content (bypassing the
    governed builder) — the adjudication-gate probe: a snapshot minted elsewhere must not
    smuggle a malformed input past the consume path (OD-P3-4-H)."""
    from types import SimpleNamespace

    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    specs: list = []
    anchors: dict[str, object] = {}
    for content in series:
        anchor = SimpleNamespace(
            id=content["factor_id"], valid_from=T0, system_from=None, record_version=1
        )
        anchors[content["factor_id"]] = anchor
        _append_spec(specs, COMPONENT_KIND_FACTOR_RETURN, "factor", anchor, content)
    for content in factor_pins or []:
        anchor = anchors.get(
            content["id"],
            SimpleNamespace(id=content["id"], valid_from=T0, system_from=None, record_version=1),
        )
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", anchor, content)
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=PURPOSE_COVARIANCE_INPUT,
        as_of_valid_at=VALID_AT,
        as_of_known_at=VALID_AT,
        as_of_valuation_date=D4,
        binding_predicate_version="test:hand-minted",
    )
    session.flush()
    return header


def _series_content(
    fid: str,
    code: str,
    values: list[str],
    dates: list[date] | None = None,
    return_type: str = "SIMPLE",
) -> dict:
    ds = dates or [D1, D2, D3, D4][: len(values)]
    return {
        "factor_id": fid,
        "factor_code": code,
        "factor_source": "VENDOR_F",
        "return_type": return_type,
        "frequency": "DAILY",
        "rows": [
            {
                "id": str(uuid.uuid4()),
                "return_date": d.isoformat(),
                "return_type": return_type,
                "return_value": v,
                "valid_from": "2026-01-01T00:00:00+00:00",
                "system_from": "2026-01-01T00:00:00+00:00",
                "record_version": 1,
            }
            for d, v in zip(ds, values, strict=True)
        ],
    }


def _factor_pin_content(fid: str, code: str, frequency: str = "DAILY") -> dict:
    return {
        "id": fid,
        "tenant_id": str(uuid.uuid4()),
        "factor_code": code,
        "factor_source": "VENDOR_F",
        "factor_family": "CURRENCY",
        "factor_type": None,
        "region": None,
        "currency_code": None,
        "asset_class": None,
        "frequency": frequency,
        "factor_name": None,
        "description": None,
        "valid_from": "2026-01-01T00:00:00+00:00",
        "record_version": 1,
    }


def test_consume_path_refuses_misaligned_unpaired_and_wrong_vocab(session: Session) -> None:
    # The OD-P3-4-H named checks the governed builder can never produce — proven via hand-minted
    # snapshots (the 2026-07 review coverage fold): each defect refuses pre-create (zero runs).
    tenant = str(uuid.uuid4())
    mv = _model(session, tenant, window=4)
    fa, fb = str(uuid.uuid4()), str(uuid.uuid4())

    mis = _mint_covariance_snapshot(
        session,
        tenant,
        [
            _series_content(fa, "A", SERIES_A, [D1, D2, D3, D4]),
            _series_content(fb, "B", SERIES_B, [D1, D2, D3, date(2026, 5, 30)]),
        ],
        [_factor_pin_content(fa, "A"), _factor_pin_content(fb, "B")],
    )
    with pytest.raises(CovarianceInputError, match="misaligned"):
        _run(session, tenant, mv, None, snapshot_id=mis.id)

    unpaired = _mint_covariance_snapshot(
        session,
        tenant,
        [_series_content(fa, "A", SERIES_A), _series_content(fb, "B", SERIES_B)],
        [_factor_pin_content(fa, "A")],  # B unpaired
    )
    with pytest.raises(CovarianceInputError, match="no paired"):
        _run(session, tenant, mv, None, snapshot_id=unpaired.id)

    log_series = _mint_covariance_snapshot(
        session,
        tenant,
        [
            _series_content(fa, "A", SERIES_A, return_type="LOG"),
            _series_content(fb, "B", SERIES_B),
        ],
        [_factor_pin_content(fa, "A"), _factor_pin_content(fb, "B")],
    )
    with pytest.raises(CovarianceInputError, match="return_type"):
        _run(session, tenant, mv, None, snapshot_id=log_series.id)

    weekly = _mint_covariance_snapshot(
        session,
        tenant,
        [_series_content(fa, "A", SERIES_A), _series_content(fb, "B", SERIES_B)],
        [_factor_pin_content(fa, "A", frequency="WEEKLY"), _factor_pin_content(fb, "B")],
    )
    with pytest.raises(CovarianceInputError, match="frequency"):
        _run(session, tenant, mv, None, snapshot_id=weekly.id)

    # An EXACT duplicate target id is already blocked by the component unique constraint; the
    # smuggleable variant is a CASE-VARIANT spelling of the same factor id (distinct component
    # rows, one factor) — the adjudication lowercases and refuses.
    dup = _mint_covariance_snapshot(
        session,
        tenant,
        [_series_content(fa, "A", SERIES_A), _series_content(fa.upper(), "A2", SERIES_B)],
        [_factor_pin_content(fa, "A")],
    )
    with pytest.raises(CovarianceInputError, match="duplicate FACTOR_RETURN"):
        _run(session, tenant, mv, None, snapshot_id=dup.id)

    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


def test_malformed_declared_window_refused_not_500(session: Session) -> None:
    # A 'risk.covariance.sample' version is mintable via the GENERIC governed registration with a
    # malformed/absent window assumption (same permission) — the binder must refuse it as a
    # model-identity failure (422 class), never a bare int() ValueError (the 2026-07 review fix).
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk.bootstrap import COVARIANCE_MODEL_CODE

    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    model = register_model(
        session,
        tenant_id=tenant,
        code=COVARIANCE_MODEL_CODE,
        name="generic",
        model_type="COVARIANCE",
        actor_id="a",
    )
    for label, assumptions in (
        ("v1", ["window_observations=abc"]),  # malformed
        ("v2", []),  # absent
        ("v3", ["window_observations=4", "window_observations=5"]),  # ambiguous
    ):
        version = register_model_version(
            session,
            model=model,
            version_label=label,
            actor_id="a",
            methodology_ref="05_analytics_methodologies/covariance_sample_v1.md",
            code_version="risk-v1",
            status="REGISTERED",
            assumptions=assumptions,
            limitations=[],
        )
        session.flush()
        with pytest.raises(WrongModelVersionError):
            _run(session, tenant, str(version.id), factors)
    # And the covariance registration path maps the same defect to its governed refusal
    # (label v1 exists with a malformed window -> identity check refuses, never int()-crashes).
    with pytest.raises(WrongModelVersionError):
        register_covariance_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
        )
    assert _count_runs(session, tenant) == 0


def test_consume_path_unknown_snapshot_404_class(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    with pytest.raises(SnapshotNotFound):
        _run(session, tenant, mv, None, snapshot_id=str(uuid.uuid4()))
    assert _count_runs(session, tenant) == 0


def test_builder_refuses_sub_two_factors_duplicates_and_short_window(session: Session) -> None:
    tenant = str(uuid.uuid4())
    f_a, f_b, _f_c = _abc(session, tenant)
    actor = SnapshotActor(actor_id="s")
    with pytest.raises(CovarianceSnapshotError):
        build_covariance_snapshot(
            session,
            acting_tenant=tenant,
            actor=actor,
            factor_ids=[f_a],
            window_observations=2,
            as_of_valid_at=VALID_AT,
        )
    with pytest.raises(CovarianceSnapshotError):
        build_covariance_snapshot(
            session,
            acting_tenant=tenant,
            actor=actor,
            factor_ids=[f_a, f_a, f_b],
            window_observations=2,
            as_of_valid_at=VALID_AT,
        )
    with pytest.raises(CovarianceSnapshotError):
        build_covariance_snapshot(
            session,
            acting_tenant=tenant,
            actor=actor,
            factor_ids=[f_a, f_b],
            window_observations=1,
            as_of_valid_at=VALID_AT,
        )


# ---------- (6) post-create FAILED (the defensive output-sanity gate) ----------


def test_defensive_gate_fails_closed_post_create(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gate is unreachable for the sample estimator over adjudicated pins (PSD by
    # construction) — force a defect through the kernel seam to prove the FAILED wiring:
    # committed FAILED run + ZERO rows + a defect-naming reason + DEPENDS_ON kept.
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    import irp_shared.risk.covariance_service as cs

    real = cs.estimate_covariance

    def poisoned(series):  # noqa: ANN001, ANN202
        out = real(series)
        first = sorted(out)[0]
        out[first] = Decimal("-1")  # a negative DIAGONAL (canonical order ⇒ first key is (a,a))
        return out

    monkeypatch.setattr(cs, "estimate_covariance", poisoned)
    result = _run(session, tenant, mv, factors)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == [] and _count_results(session, tenant) == 0
    assert result.failure_reason and "negative-variance" in result.failure_reason
    assert result.run.status == RunStatus.FAILED.value
    # The FAILED transition is audited with outcome='failure' (the P2-3 OD-P2-3-F/H contract).
    failed_events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == result.run.run_id,
                AuditEvent.event_type == "CALC.RUN_STATUS_CHANGE",
                AuditEvent.outcome == "failure",
            )
        )
        .scalars()
        .all()
    )
    assert len(failed_events) == 1
    # Durable DQ evidence (DATA.VALIDATE): the defect is a persisted data_quality_result row
    # against the FAILED run (the P3-3 exemplar assertion; the 2026-07 review coverage fold).
    from irp_shared.dq.models import DataQualityResult

    dq_rows = (
        session.execute(
            select(DataQualityResult).where(
                DataQualityResult.target_entity_type == "calculation_run",
                DataQualityResult.target_entity_id == result.run.run_id,
            )
        )
        .scalars()
        .all()
    )
    assert dq_rows  # the FAILED run must carry persisted DQ evidence
    dep = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_DATA_SNAPSHOT,
                LineageEdge.target_entity_id == result.run.run_id,
                LineageEdge.edge_kind == EDGE_KIND_DEPENDENCY,
            )
        )
        .scalars()
        .all()
    )
    assert len(dep) == 1  # the FAILED run keeps its input link


# ---------- (7) output contract / audit / lineage / append-only / grain ----------


def test_output_contract_bindings(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, factors)
    run = result.run
    assert run.input_snapshot_id and run.model_version_id == mv
    assert run.code_version == "risk-v1" and run.environment_id == "ci"
    assert run.run_type == "COVARIANCE"
    for row in result.rows:
        assert row.input_snapshot_id == run.input_snapshot_id
        assert row.calculation_run_id == run.run_id
        assert row.model_version_id == mv


def test_audit_calc_run_events_no_risk_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, factors)
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "calculation_run",
                AuditEvent.entity_id == result.run.run_id,
            )
        )
        .scalars()
        .all()
    )
    types = [e.event_type for e in events]
    assert "CALC.RUN_CREATE" in types and "CALC.RUN_STATUS_CHANGE" in types
    risk_events = (
        session.execute(select(AuditEvent).where(AuditEvent.event_type.like("RISK.%")))
        .scalars()
        .all()
    )
    assert risk_events == []  # RISK.COVARIANCE_CREATE stays reserved-not-emitted


def test_lineage_snapshot_to_run_to_result(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, factors)
    origin = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_CALCULATION_RUN,
                LineageEdge.target_entity_type == "covariance_result",
                LineageEdge.edge_kind == EDGE_KIND_ORIGIN,
            )
        )
        .scalars()
        .all()
    )
    assert {e.target_entity_id for e in origin} == {r.id for r in result.rows}
    assert all(e.run_id == result.run.run_id for e in origin)


def test_covariance_result_is_ia_append_only(session: Session) -> None:
    from irp_shared.temporal import TemporalClass

    assert CovarianceResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, factors)
    session.commit()
    row = result.rows[0]
    row.covariance_value = Decimal("999")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):
        session.delete(result.rows[0])
        session.flush()


def test_grain_uniqueness_and_reader_order(session: Session) -> None:
    tenant = str(uuid.uuid4())
    factors = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    result = _run(session, tenant, mv, factors)
    keys = {(r.calculation_run_id, r.factor_id_1, r.factor_id_2) for r in result.rows}
    assert len(keys) == len(result.rows) == 6  # the 3-tuple grain is unique within the run
    listed = list_covariances(session, run_id=result.run.run_id, acting_tenant=tenant)
    assert [(r.factor_id_1, r.factor_id_2) for r in listed] == sorted(
        (r.factor_id_1, r.factor_id_2) for r in result.rows
    )


# ---------- (8) entitlement REUSE parity (no new permission — OD-P3-4-M) ----------


def test_risk_permissions_reused_no_new_codes() -> None:
    all_codes = {code for perms in ROLE_TEMPLATES.values() for code in perms}
    assert "risk.run" in all_codes and "risk.view" in all_codes
    assert not {c for c in all_codes if "covariance" in c or "matrix" in c}


# ---------- (9) methodology doc ----------

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_COV_SERVICE_SRC = (
    _ROOT / "packages/shared-python/src/irp_shared/risk/covariance_service.py"
).read_text()
_COV_KERNEL_SRC = (
    _ROOT / "packages/shared-python/src/irp_shared/risk/covariance_kernel.py"
).read_text()


def test_methodology_doc_exists_and_has_required_sections() -> None:
    doc = (_ROOT / COVARIANCE_METHODOLOGY_REF).read_text()
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
    assert "no pairwise deletion" in doc.lower()  # the OD-P3-0-L fail-closed declaration


def test_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == COVARIANCE_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).exists()


# ---------- (10) load-bearing scope fences ----------


def test_scope_fence_no_live_reads_in_compute_path() -> None:
    # The COMPUTE path (_parse_pins/_adjudicate_pins/_build_rows) reads snapshot-pinned content
    # ONLY; the live factor/return reads belong to the PRE-CREATE gate + the snapshot builder.
    tree = ast.parse(_COV_SERVICE_SRC)
    forbidden = {"resolve_factor", "list_factor_returns", "reconstruct_factor_return_as_of"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "_parse_pins",
            "_adjudicate_pins",
            "_build_rows",
        ):
            found.add(node.name)
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not (names & forbidden), (node.name, names & forbidden)
            assert not (attrs & forbidden), (node.name, attrs & forbidden)
    # The fence must never pass vacuously (the 2026-07 review finding).
    assert found == {"_parse_pins", "_adjudicate_pins", "_build_rows"}, found


def test_scope_fence_no_future_analytics_imports_or_identifiers() -> None:
    for src in (_COV_SERVICE_SRC, _COV_KERNEL_SRC):
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for mod in imported:
            parts = set(mod.split("."))
            assert not (
                parts & {"scenario", "pricing", "stress", "var", "benchmark", "numpy", "scipy"}
            ), f"forbidden import {mod}"
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        forbidden_idents = {
            "value_at_risk",
            "expected_shortfall",
            "shrinkage",
            "ledoit_wolf",
            "ewma",
            "decay",
            "half_life",
            "correlation_matrix",
            "annualize",
            "scenario_result",
            "stress_test",
            "monte_carlo",
            "tracking_error",
            "attribution",
            "cholesky",
        }
        assert not (idents & forbidden_idents), idents & forbidden_idents


def test_scope_fence_no_runtime_numpy_anywhere_in_irp_shared() -> None:
    # numpy is TEST-ONLY (the OD-P3-4-F verification dependency): NO module under the runtime
    # irp_shared package may import it (ast-verified, not grep — comments/strings don't count).
    pkg = _ROOT / "packages/shared-python/src/irp_shared"
    offenders: list[str] = []
    scanned: list[str] = []
    for py in sorted(pkg.rglob("*.py")):
        scanned.append(py.name)
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            mods = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module]
                if isinstance(node, ast.ImportFrom) and node.module
                else []
            )
            if any(m.split(".")[0] in ("numpy", "scipy", "pandas") for m in mods):
                offenders.append(str(py))
    # Never vacuous (the 2026-07 review fold): the scan must actually have seen the runtime tree.
    assert "covariance_kernel.py" in scanned and len(scanned) > 50, scanned[:5]
    assert offenders == [], offenders


# ---------- (10b) PreciseDecimal engine-parity unit tests (the 2026-07 review fixes) ----------


def test_precise_decimal_large_value_and_negative_zero() -> None:
    from sqlalchemy.dialects import postgresql, sqlite

    from irp_shared.db.types import PreciseDecimal

    td = PreciseDecimal(38, 20)
    pg, lite = postgresql.dialect(), sqlite.dialect()
    # > prec-28 total digits (29-digit coefficient) must NOT raise under the default context.
    big = Decimal("123456789.12345678901234567890")
    assert td.process_bind_param(big, pg) == big
    assert td.process_bind_param(big, lite) == "123456789.12345678901234567890"
    assert td.process_result_value("123456789.12345678901234567890", lite) == big
    # 18 integer digits (the full Numeric(38,20) envelope) also binds cleanly.
    full = Decimal("123456789012345678." + "1" * 20)
    assert td.process_bind_param(full, pg) == full
    # -0E-20 normalizes to +0 on BOTH engines (PG numeric drops the sign; TEXT would keep it).
    neg_zero = Decimal("-0E-20")
    assert not td.process_bind_param(neg_zero, pg).is_signed()
    assert not td.process_bind_param(neg_zero, lite).startswith("-")


def test_endpoint_serialization_is_fixed_point() -> None:
    # str(Decimal('1E-8')) flips to scientific notation; the API row-out must stay fixed-point.
    from irp_backend.api.risk import _cov_row_out

    row = CovarianceResult(
        tenant_id=str(uuid.uuid4()),
        calculation_run_id=str(uuid.uuid4()),
        input_snapshot_id=str(uuid.uuid4()),
        model_version_id=str(uuid.uuid4()),
        factor_id_1="a" * 36,
        factor_id_2="b" * 36,
        factor_code_1="A",
        factor_code_2="B",
        statistic_type="COVARIANCE",
        return_type="SIMPLE",
        frequency="DAILY",
        n_observations=4,
        window_start=D1,
        window_end=D4,
        covariance_value=Decimal("1E-8").quantize(_Q20),
    )
    row.id = str(uuid.uuid4())
    out = _cov_row_out(row)
    assert out.covariance_value == "0.00000001000000000000"
    assert "E" not in out.covariance_value and "e" not in out.covariance_value


# ---------- (11) migration head ----------


def test_migration_head_is_covariance() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0028_var_historical"
    assert script.get_revision("0025_covariance").down_revision == "0024_factor_exposure"
