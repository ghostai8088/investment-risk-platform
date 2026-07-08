"""PostgreSQL-only proofs for VAR-HS-1 ``metric_type='VAR_HISTORICAL'`` rows, run as the
constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role (the CI/pipeline posture):

- the FULL governed chain executes on PG under FORCE RLS (incl. the 0028 NULL columns —
  ``z_score``/``sigma``/``covariance_run_id`` land as SQL NULL);
- symmetric tenant isolation over the hist-sim rows (visibility + no-context zero rows);
- the P0001 append-only trigger blocks UPDATE/DELETE of a hist-sim row;
- cross-tenant snapshot consume fails closed;
- the per-tenant audit hash chain verifies.

The grants/role posture is REUSED from ``test_var_pg`` (same tables — no new grant surface).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool
from test_var_pg import (  # noqa: F401 - the shared role/grant fixture + chain seeder
    URL,
    _is_append_only_violation,
    _is_rls_violation,
    _seed_and_run,
    app_url,
)

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.marketdata.factor import FactorActor, capture_factor_return, resolve_factor
from irp_shared.risk import (
    VarActor,
    VarResult,
    register_historical_var_model,
    run_var_historical,
)
from irp_shared.snapshot import SnapshotActor, SnapshotNotFound, build_var_hs_snapshot

pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_ACTOR = VarActor(actor_id="a")


def _fx_run_id(factory, tenant: str) -> str:  # noqa: ANN001
    """The seeded chain's COMPLETED FACTOR_EXPOSURE run id (``_seed_and_run`` returns the
    PARAMETRIC VaR run id — not what the hist-sim binder consumes)."""
    from irp_shared.calc.models import CalculationRun

    with factory() as s:
        set_tenant_context(s, tenant)
        return s.execute(
            select(CalculationRun.run_id).where(
                CalculationRun.tenant_id == tenant,
                CalculationRun.run_type == "FACTOR_EXPOSURE",
            )
        ).scalar_one()


def _extend_windows_and_run(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    """Extend the ``test_var_pg`` seeded chain (a COMPLETED factor-exposure run over 2 factors
    with 4 return dates) to 21 dates, register the hist-sim model (floor: c=0.95 -> N>=21 —
    the review-tightened k>=2 rule), and execute the governed hist-sim run. Returns
    (run_id, var_result_id)."""
    from irp_shared.marketdata.models import Factor

    _seed_and_run(factory, tenant)  # seeds the full chain (returns the PARAMETRIC run id)
    fx_run_id = _fx_run_id(factory, tenant)
    with factory() as s:
        set_tenant_context(s, tenant)
        factors = s.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().all()
        assert len(factors) >= 2
        base_day = date(2026, 4, 1)
        for factor in factors:
            f = resolve_factor(s, factor.id, acting_tenant=tenant)
            for i in range(1, 22):
                capture_factor_return(
                    s,
                    f,
                    return_date=base_day + timedelta(days=i),
                    return_value=Decimal(i) / Decimal(1000),
                    acting_tenant=tenant,
                    actor=FactorActor(actor_id="s"),
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                )
        mv = register_historical_var_model(
            s,
            tenant_id=tenant,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=21,
        )
        result = run_var_historical(
            s,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version="v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=fx_run_id,
        )
        assert result.status == "COMPLETED", result.failure_reason
        (row,) = result.rows
        assert row.metric_type == "VAR_HISTORICAL"
        assert row.z_score is None and row.sigma is None and row.covariance_run_id is None
        run_id, row_id = result.run.run_id, row.id
        s.commit()
    return run_id, row_id


def test_hs_chain_isolation_nulls_and_append_only(app_url: str) -> None:  # noqa: F811
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    _run_id, row_id = _extend_windows_and_run(factory, tenant_a)

    # NULLs landed as SQL NULL on PG (the 0028 relaxation under FORCE RLS).
    with factory() as s:
        set_tenant_context(s, tenant_a)
        row = s.execute(select(VarResult).where(VarResult.id == row_id)).scalar_one()
        assert row.z_score is None and row.sigma is None and row.covariance_run_id is None

    # Tenant isolation: B sees nothing; no-context sees nothing (RLS fails closed).
    with factory() as s:
        set_tenant_context(s, tenant_b)
        assert (
            s.execute(select(VarResult).where(VarResult.id == row_id)).scalar_one_or_none() is None
        )
    with factory() as s:
        assert s.execute(select(VarResult)).scalars().first() is None

    # The P0001 append-only trigger blocks UPDATE and DELETE at the DB.
    with factory() as s:
        set_tenant_context(s, tenant_a)
        with pytest.raises(ProgrammingError) as upd:
            s.execute(text("UPDATE var_result SET var_value = 0 WHERE id = :id"), {"id": row_id})
        assert _is_append_only_violation(upd.value)
    with factory() as s:
        set_tenant_context(s, tenant_a)
        with pytest.raises(ProgrammingError) as dele:
            s.execute(text("DELETE FROM var_result WHERE id = :id"), {"id": row_id})
        assert _is_append_only_violation(dele.value)

    # The per-tenant audit hash chain still verifies after the governed chain.
    ops_engine = make_engine(URL, poolclass=NullPool)
    with make_session_factory(ops_engine)() as ops:
        assert verify_chain(ops, tenant_id=tenant_a).ok
    ops_engine.dispose()
    engine.dispose()


def test_cross_tenant_snapshot_consume_fails_closed_hs(app_url: str) -> None:  # noqa: F811
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, tenant_a)
    fx_run_id = _fx_run_id(factory, tenant_a)
    with factory() as s:
        set_tenant_context(s, tenant_a)
        from irp_shared.marketdata.models import Factor

        base_day = date(2026, 4, 1)
        factors = s.execute(select(Factor).where(Factor.tenant_id == tenant_a)).scalars().all()
        for factor in factors:
            f = resolve_factor(s, factor.id, acting_tenant=tenant_a)
            for i in range(1, 22):
                capture_factor_return(
                    s,
                    f,
                    return_date=base_day + timedelta(days=i),
                    return_value=Decimal(i) / Decimal(1000),
                    acting_tenant=tenant_a,
                    actor=FactorActor(actor_id="s"),
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                )
        s.commit()
    with factory() as s:
        set_tenant_context(s, tenant_a)
        snapshot = build_var_hs_snapshot(
            s,
            acting_tenant=tenant_a,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run_id,
            window_observations=21,
        )
        snapshot_id = snapshot.id
        s.commit()
    # Tenant B cannot consume tenant A's snapshot (invisible under RLS -> pre-create refusal).
    with factory() as s:
        set_tenant_context(s, tenant_b)
        mv = register_historical_var_model(
            s,
            tenant_id=tenant_b,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=21,
        )
        with pytest.raises(SnapshotNotFound):  # invisible under RLS -> pre-create refusal
            run_var_historical(
                s,
                acting_tenant=tenant_b,
                actor=_ACTOR,
                code_version="v1",
                environment_id="ci",
                model_version_id=mv.id,
                snapshot_id=snapshot_id,
            )
    engine.dispose()


def test_failed_run_persists_reason_on_pg(app_url: str) -> None:  # noqa: F811
    """The magnitude gate's committed FAILED run — incl. the failure_reason UPDATE — executed
    under FORCE RLS on PostgreSQL (the P3-C1 requirement extended to the HS binder; the gate
    became REACHABLE with the kernel prec-50 review fix)."""
    from test_var_hs import _exp, _mint_hs_snapshot, _win

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run(factory, tenant)
    fx_run = _fx_run_id(factory, tenant)
    with factory() as s:
        set_tenant_context(s, tenant)
        mv = register_historical_var_model(
            s,
            tenant_id=tenant,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=21,
        )
        f1 = str(uuid.uuid4()).lower()
        snap = _mint_hs_snapshot(s, tenant, [_exp(fx_run, f1, "1E21")], [_win(f1, ["-10"] * 21)])
        result = run_var_historical(
            s,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version="v1",
            environment_id="ci",
            model_version_id=mv.id,
            snapshot_id=snap.id,
        )
        assert result.status == "FAILED"
        assert result.rows == []
        assert result.failure_reason and "magnitude-out-of-range" in result.failure_reason
        s.commit()
        run_id = result.run.run_id
    with factory() as s:
        set_tenant_context(s, tenant)
        from irp_shared.calc.models import CalculationRun

        row = s.execute(select(CalculationRun).where(CalculationRun.run_id == run_id)).scalar_one()
        assert row.status == "FAILED"
        assert row.failure_reason is not None and "magnitude-out-of-range" in row.failure_reason
    engine.dispose()
