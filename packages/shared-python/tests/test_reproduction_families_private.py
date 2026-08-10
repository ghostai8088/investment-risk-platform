"""REPRO-2 — the private-asset arc's three adapters, each made to say YES and then made to say NO.

A companion to ``test_reproduction_families.py``, carrying the same pair for the three families
whose subject runs cost the most to build: PACING_PROJECTION, PURE_PRIVATE_FACTOR and
PROXY_WEIGHT_ESTIMATE. It imports that module's ``assert_reproduces_and_then_diverges`` rather than
restating it — one helper, so a weakening of the pair is a one-place edit somebody has to justify.

**PROXY_WEIGHT_ESTIMATE gets two tests, not one**, because its adapter is the only one of the
sixteen that BRANCHES: ``_proxy_weight_family`` dispatches between ``run_proxy_weight_estimate``
(OLS/EWMA) and ``run_residual_shrinkage`` (cross-sectional empirical Bayes) on the model version's
declared estimator convention, since both binders assert the same model code. A single test over a
regression run would leave the shrinkage arm — which additionally has to RECOVER the caller-supplied
``target_estimate_run_id`` from ``source_desmoothed_run_id`` against the pinned cohort, a value no
column stores — entirely unexecuted. The recovery is the adapter's own documented weakest link, so
it is the arm that most needs a green sweep and a planted red one.

The subject the sweep picks is always "the most recent COMPLETED run of this run type", and both
proxy-weight arms write run type ``PROXY_WEIGHT_ESTIMATE``. The shrinkage test therefore builds its
cohort FIRST and the shrinkage run LAST, and then asserts that the family's verdict actually named
the shrinkage run — otherwise a passing test could be silently re-proving the OLS arm a third time.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_reproduction_families import (
    _sweep,
    _verdict_for,
    assert_reproduces_and_then_diverges,
)

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.risk.events import ProxyWeightEstimateActor
from irp_shared.risk.residual_shrinkage_service import run_residual_shrinkage


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


# --------------------------------------------------------------------------- PACING_PROJECTION ---
def test_PACING_PROJECTION_reproduces_and_detects_a_plant(session: Session) -> None:
    """The CC-2 stage-8 commitment, projected, swept, then tampered in ``projected_nav``."""
    from test_pacing_binder import _mark, _register, _run, _seed_pair, _stage8_commitment

    from irp_shared.snapshot import build_pacing_snapshot
    from irp_shared.snapshot.events import SnapshotActor

    tenant = str(uuid.uuid4())
    pf, fund = _seed_pair(session, tenant)
    _stage8_commitment(session, tenant, pf, fund)
    _mark(session, tenant, pf, fund, "11200000.000000", date(2025, 6, 30))
    mv = _register(session, tenant)
    session.flush()
    snap = build_pacing_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        portfolio_id=pf,
        instrument_id=fund,
    )
    stored = _run(session, tenant, pf, fund, mv, snap)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="PACING_PROJECTION",
        table="pacing_projection_result",
        subject_run_id=str(stored.run.run_id),
        column="projected_nav",
        # Money scale (28,6): a plainly impossible NAV for a 25M commitment, written at the stored
        # scale so the plant is a value the column could genuinely have held.
        tampered="777777.000000",
    )


# -------------------------------------------------------------------------- PURE_PRIVATE_FACTOR ---
def test_PURE_PRIVATE_FACTOR_reproduces_and_detects_a_plant(session: Session) -> None:
    """One private member with a promoted REGRESSION blend, pooled onto a PRIVATE segment."""
    from test_pure_private_factor import (
        T0,
        _member_with_blend,
        _ppf_model,
        _segment_factor,
    )

    from irp_shared.marketdata import ProxyMappingActor, capture_proxy_mapping
    from irp_shared.risk import PurePrivateFactorActor, run_pure_private_factor_return

    tenant = str(uuid.uuid4())
    desmoothed_run_id, inst, _pf = _member_with_blend(session, tenant)
    seg = _segment_factor(session, tenant)
    capture_proxy_mapping(  # the MANUAL membership row onto the segment
        session,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=T0,
    )
    stored = run_pure_private_factor_return(
        session,
        acting_tenant=tenant,
        actor=PurePrivateFactorActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_ppf_model(session, tenant),
        segment_factor_id=seg,
        member_desmoothed_run_ids=[desmoothed_run_id],
    )
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="PURE_PRIVATE_FACTOR",
        table="private_factor_return_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        # A 12dp fraction: a pooled pure-private return of +42% is not one this fixture produces.
        tampered="0.420000000000",
    )


# ----------------------------------------------------------------- PROXY_WEIGHT_ESTIMATE (OLS) ---
def test_PROXY_WEIGHT_ESTIMATE_regression_reproduces_and_detects_a_plant(session: Session) -> None:
    """The OLS arm: a RAW regression version, so the adapter must pick the regression binder.

    This is the arm the convention dispatch has to get right by NOT taking the shrinkage branch —
    both binders assert ``risk.proxy_weight.regression``, so a dispatcher keyed on model code would
    land here or there at random. Asserting the run reproduces is what proves it landed here.
    """
    from test_proxy_weight import _desmoothed_run, _factor, _factor_returns, _proxy_model

    from irp_shared.risk import ProxyWeightEstimateActor, run_proxy_weight_estimate

    tenant = str(uuid.uuid4())
    desmoothed_run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    stored = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_proxy_model(session, tenant),
        desmoothed_run_id=desmoothed_run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="PROXY_WEIGHT_ESTIMATE",
        table="proxy_weight_estimate_result",
        subject_run_id=str(stored.run.run_id),
        column="metric_value",
        tampered="0.987654321000",
    )


# ----------------------------------------------------- PROXY_WEIGHT_ESTIMATE (EB shrinkage arm) ---
def test_PROXY_WEIGHT_ESTIMATE_shrinkage_reproduces_and_detects_a_plant(session: Session) -> None:
    """The empirical-Bayes arm — the least-proven code in the slice, and the reason for two tests.

    Everything unique to this arm is exercised only here: the convention lookup choosing
    ``run_residual_shrinkage``, and the recovery of ``target_estimate_run_id`` (a caller argument
    with no stored column) by matching the row's ``source_desmoothed_run_id`` against the pinned
    cohort. A wrong recovery does not raise — it re-executes a real computation over the WRONG
    cohort member and reports the difference as a divergence, which is why the green half of the
    pair is the assertion that matters most.

    Both arms write run type ``PROXY_WEIGHT_ESTIMATE`` and the sweep takes the most recent COMPLETED
    run of a type, so the cohort's three raw estimates are built first and the shrinkage run last;
    the subject identity is then asserted rather than assumed.
    """
    from test_proxy_weight import _cohort, _eb_version

    from irp_shared.risk import (
        METRIC_TYPE_ESTIMATION_SUMMARY,
        ProxyWeightEstimateActor,
        list_proxy_weight_results,
        run_residual_shrinkage,
    )

    tenant = str(uuid.uuid4())
    cohort = _cohort(session, tenant, 3)
    # The green half only proves the target RECOVERY if a different member would have produced a
    # different answer. `_cohort` seeds distinct mark paths for exactly that reason; asserting it
    # here is what stops a future homogeneous fixture from turning this test into a tautology.
    raw_stdevs = [
        next(
            r
            for r in list_proxy_weight_results(session, rid, acting_tenant=tenant)
            if r.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY
        ).residual_stdev
        for rid in cohort
    ]
    assert len(set(raw_stdevs)) == len(cohort), (
        f"the cohort's residual stdevs are not distinct ({raw_stdevs}) — a wrong-target recovery "
        "would then reproduce anyway and this test would prove nothing about it"
    )
    stored = run_residual_shrinkage(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_eb_version(session, tenant),
        # The LAST cohort member, deliberately, not the first. The mutation battery proved why:
        # a mutant that recovers "the first cohort member" instead of the MATCHING one survived a
        # version of this test that shrank cohort[0] — the wrong answer and the right answer were
        # the same run. Targeting a non-first member is what makes the recovery's correctness
        # observable at all.
        target_estimate_run_id=cohort[-1],
        cohort_estimate_run_ids=cohort,
    )
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason
    subject_run_id = str(stored.run.run_id)
    assert subject_run_id not in cohort

    # The subject the sweep will actually judge MUST be the shrinkage run: if recency resolved to
    # one of the three raw estimates instead, this test would pass while proving the OLS arm again.
    probe = _verdict_for(_sweep(session, tenant), "PROXY_WEIGHT_ESTIMATE")
    assert str(probe.subject_run_id) == subject_run_id, (
        "the sweep judged a different PROXY_WEIGHT_ESTIMATE run than the shrinkage one "
        f"({probe.subject_run_id} != {subject_run_id}) — the empirical-Bayes arm is NOT what this "
        "test would be proving"
    )
    session.commit()

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="PROXY_WEIGHT_ESTIMATE",
        table="proxy_weight_estimate_result",
        subject_run_id=subject_run_id,
        column="residual_stdev",
        # The shrunk residual stdev IS this arm's output — the one column the transform changes.
        tampered="0.135791357913",
    )


# ------------------------------------- the two proxy-weight refusals the battery found untested --
# NOTE on what is NOT tested here, deliberately. `_shrinkage_target` carries two fail-closed
# guards — "the stored rows do not yield exactly one source run" and "the pinned cohort has more
# than one member matching it". Neither is reachable with data the platform can write:
# `source_desmoothed_run_id` is NOT NULL and an EB run persists exactly one row. They are kept as
# defence in depth and are honestly unreachable; the mutation battery targets the RECOVERY itself
# (picking the wrong cohort member), which is both reachable and the defect that would actually
# hurt — see `scripts/mutants.toml` R-D5 and its two rejected anchors.


def test_an_UNRESOLVABLE_convention_is_REFUSED_as_a_reproduction_verdict(session: Session) -> None:
    """R-D6. Two binders share one model code, so the adapter dispatches on the declared estimator
    convention. When that declaration cannot be resolved — unknown, ambiguous or malformed —
    `declared_proxy_weight_parameters` fails closed with `WrongModelVersionError`, and the adapter
    must turn that into `ReproductionUnsupported`: the binder cannot be identified, so the family
    cannot be CHECKED, which is a verdict rather than an ordinary failure.

    The ambiguity is created the way the platform's own fail-closed rule describes it: TWO
    estimator-convention assumption rows on one version, which the resolver refuses rather than
    collapsing into the grandfather default.
    """
    from test_proxy_weight import _cohort, _eb_version

    from irp_shared.model.assumptions import ModelAssumption
    from irp_shared.reproduction.registry import REPRODUCIBLE_FAMILIES, ReproductionUnsupported
    from irp_shared.risk.bootstrap import ESTIMATOR_ASSUMPTION_PREFIX

    tenant = str(uuid.uuid4())
    cohort = _cohort(session, tenant, 3)
    version = _eb_version(session, tenant)
    stored = run_residual_shrinkage(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a", actor_type="HUMAN"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=version,
        target_estimate_run_id=cohort[0],
        snapshot_id=None,
        cohort_estimate_run_ids=cohort,
    )
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    # A SECOND convention row: ambiguity the resolver must refuse rather than resolve.
    session.add(
        ModelAssumption(
            tenant_id=tenant,
            model_version_id=version,
            assumption_text=f"{ESTIMATOR_ASSUMPTION_PREFIX}SOMETHING_NOBODY_DECLARED",
            category="ESTIMATOR",
            authored_by="test",
        )
    )
    session.commit()
    session.expire_all()

    run = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == stored.run.run_id)
    ).scalar_one()
    with pytest.raises(ReproductionUnsupported) as caught:
        REPRODUCIBLE_FAMILIES["PROXY_WEIGHT_ESTIMATE"].recompute(session, tenant, run, "risk-v1")
    assert "refusing to guess which kernel" in str(
        caught.value
    ), f"the refusal was not the convention-resolution guard: {caught.value}"
