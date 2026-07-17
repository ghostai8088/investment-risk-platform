"""PostgreSQL-only proofs for ES-HS-1 ``metric_type='ES_HISTORICAL'`` rows — the ONLY tier
that can see the 0041 CHECK (migration-only, ORM-invisible; the SQLite battery is blind to it):

- (a) CHECK compliance: the governed ES-HS chain executes under the constrained ``irp_app``
  role and its NULL-trio row SURVIVES the WIDENED ``ck_var_result_parametric_not_null``; a
  non-exempt metric_type with a NULL still refuses at the DB;
- (b) the NON-SUPERUSER downgrade path (closing the recorded 0028 "CI's green smoke had
  proven only the container-superuser path" gap for the new delete): a NOSUPERUSER/NOBYPASSRLS
  role GRANTED MEMBERSHIP in the table-owner role (attributes do not inherit; ownership checks
  pass) drives the REAL ``0041`` module's ``downgrade()`` through an alembic
  ``MigrationContext`` — the ES row is ACTUALLY deleted (the FORCE-RLS zero-row trap is ALSO
  demonstrated: an unsandwiched DELETE under the same role matches nothing) and the narrow
  CHECK is re-added; the whole body runs in ONE transaction with assert-then-ROLLBACK so the
  WIDENED state is live for every later suite in the shared-DB job (asserted at module end);
- (c) RLS/append-only posture over ES-HS rows (tenant isolation; the P0001 trigger).

The grants/role posture for (a)/(c) is REUSED from ``test_var_pg`` (same tables — no new grant
surface). Leg (b) mints its own throwaway role via the superuser URL.
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.pool import NullPool
from test_var_hs_pg import _fx_run_id  # noqa: F401 - the chain helpers
from test_var_pg import (  # noqa: F401 - the shared role/grant fixture + chain seeder
    URL,
    _is_append_only_violation,
    _seed_and_run,
    app_url,
)

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.marketdata.factor import FactorActor, capture_factor_return, resolve_factor
from irp_shared.risk import (
    VarActor,
    VarResult,
    register_historical_var_es_model,
    run_var_historical,
)

pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_ACTOR = VarActor(actor_id="a")
_MIG_ROLE = "irp_mig_smoke_0041"
_MIG_PW = "mig_smoke_pw"


def _extend_and_run_es(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    """The ``test_var_hs_pg`` chain-extension shape with the ES-HS registrar: seed the
    ``test_var_pg`` chain, extend the factor-return series to 21 dates, register
    ``risk.var.historical_es`` (21/0.95 — n·a = 1.05, the FRACTIONAL weight live), run.
    Returns (run_id, var_result_id)."""
    from irp_shared.marketdata.models import Factor

    _seed_and_run(factory, tenant)
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
        mv = register_historical_var_es_model(
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
        assert row.metric_type == "ES_HISTORICAL"
        assert row.z_score is None and row.sigma is None and row.covariance_run_id is None
        run_id, row_id = result.run.run_id, row.id
        s.commit()
    return run_id, row_id


def _constraint_def(conn) -> str:  # noqa: ANN001
    return conn.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_var_result_parametric_not_null'"
        )
    ).scalar_one()


def test_es_row_survives_widened_check_and_nonexempt_still_refuses(app_url: str) -> None:  # noqa: F811
    """(a) The governed ES-HS row (NULL trio) commits under the WIDENED CHECK; a hand-minted
    non-exempt metric_type with a NULL z_score still refuses at the DB — the invariant stayed
    DB-enforced, the exemption widened by exactly one literal."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _run_id, row_id = _extend_and_run_es(factory, tenant)

    with factory() as s:
        set_tenant_context(s, tenant)
        row = s.execute(select(VarResult).where(VarResult.id == row_id)).scalar_one()
        assert row.metric_type == "ES_HISTORICAL"
        assert row.z_score is None and row.sigma is None and row.covariance_run_id is None

        # The non-exempt probe: clone the surviving row's identity onto a parametric metric
        # with the NULL trio — the CHECK must refuse it (IntegrityError naming the constraint).
        clone = VarResult(
            tenant_id=tenant,
            calculation_run_id=row.calculation_run_id,
            input_snapshot_id=row.input_snapshot_id,
            model_version_id=row.model_version_id,
            exposure_run_id=row.exposure_run_id,
            covariance_run_id=None,
            metric_type="VAR_PARAMETRIC",  # non-exempt + NULL trio = the CHECK's refusal
            base_currency=row.base_currency,
            confidence_level=row.confidence_level,
            horizon_days=row.horizon_days,
            z_score=None,
            sigma=None,
            var_value=Decimal("1.000000"),
            n_factors=row.n_factors,
            n_observations=row.n_observations,
            window_start=row.window_start,
            window_end=row.window_end,
        )
        s.add(clone)
        with pytest.raises(IntegrityError) as exc:
            s.flush()
        assert "ck_var_result_parametric_not_null" in str(exc.value)
        s.rollback()


def test_downgrade_body_under_nonsuperuser_owner_member_role(app_url: str) -> None:  # noqa: F811
    """(b) The verifier-settled mechanics. A DML-grant role dies "must be owner" on the first
    ALTER (not the recorded gap) and the alembic CLI reconnects as the superuser (re-masking
    it); the honest shape is owner-via-membership: NOSUPERUSER NOBYPASSRLS + GRANT <owner> —
    role ATTRIBUTES do not inherit through membership, so the role runs the DDL while staying
    RLS-BOUND, the exact 0028:56-59 geometry. The REAL 0041 module's ``downgrade()`` runs via
    ``MigrationContext``; assert-then-ROLLBACK restores the widened state for the shared DB."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _run_id, row_id = _extend_and_run_es(factory, tenant)

    su = create_engine(URL, poolclass=NullPool)  # the container-superuser URL (owner)
    with su.connect() as c:
        owner = c.execute(text("SELECT tableowner FROM pg_tables WHERE tablename='var_result'"))
        owner_role = owner.scalar_one()
        c.execute(
            text(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{_MIG_ROLE}') "
                f"THEN CREATE ROLE {_MIG_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS "
                f"PASSWORD '{_MIG_PW}'; "
                f"ELSE ALTER ROLE {_MIG_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS "
                f"PASSWORD '{_MIG_PW}'; END IF; END $$;"
            )
        )
        c.execute(text(f'GRANT "{owner_role}" TO {_MIG_ROLE}'))
        c.commit()

    mig_url = URL.replace("://", f"://{_MIG_ROLE}:{_MIG_PW}@", 1)
    # URL forms vary (user:pw@host); build robustly from the superuser URL's host part.
    host_part = URL.split("@", 1)[1] if "@" in URL else URL.split("://", 1)[1]
    scheme = URL.split("://", 1)[0]
    mig_url = f"{scheme}://{_MIG_ROLE}:{_MIG_PW}@{host_part}"
    mig_engine = create_engine(mig_url, poolclass=NullPool)

    # Load the REAL migration module (its name starts with a digit — spec-load by path).
    mig_path = (
        pathlib.Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0041_es_historical.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0041_es_historical", mig_path)
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with mig_engine.connect() as conn:
        # The RECORDED trap, demonstrated live under this role: an UNSANDWICHED delete under
        # FORCE RLS (no tenant GUC) silently matches ZERO rows — the exact 0028:56-59 gap.
        trans = conn.begin()
        gone = conn.execute(
            text("DELETE FROM var_result WHERE metric_type = 'ES_HISTORICAL'")
        ).rowcount
        assert gone == 0  # the row EXISTS (seeded above) — RLS hid it from the owner-member
        trans.rollback()

        # The real 0041 downgrade body, in ONE transaction, assert-then-ROLLBACK. The context
        # carries the SAME target_metadata env.py wires (the naming convention that expands the
        # short constraint name to ck_var_result_parametric_not_null).
        from irp_shared.models import metadata as target_metadata

        trans = conn.begin()
        ctx = MigrationContext.configure(conn, opts={"target_metadata": target_metadata})
        with Operations.context(ctx):
            mig.downgrade()
        # The sandwich ACTUALLY deleted the ES row (visible via the tenant GUC).
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        remaining = conn.execute(
            text("SELECT count(*) FROM var_result WHERE metric_type = 'ES_HISTORICAL'")
        ).scalar_one()
        assert remaining == 0
        survivors = conn.execute(text("SELECT count(*) FROM var_result")).scalar_one()
        assert survivors >= 1  # the parametric chain rows survive the downgrade
        # The narrow 0028-form CHECK is live again (no ES_HISTORICAL literal).
        assert "ES_HISTORICAL" not in _constraint_def(conn)
        trans.rollback()  # PG DDL is transactional — the widened state is restored

    # END-OF-BODY assertion: the WIDENED CHECK is live for every later suite in this DB.
    with su.connect() as c:
        assert "ES_HISTORICAL" in _constraint_def(c)
        with factory() as s:
            set_tenant_context(s, tenant)
            back = s.execute(select(VarResult).where(VarResult.id == row_id)).scalar_one()
            assert back.metric_type == "ES_HISTORICAL"  # the rollback restored the row


def test_es_rows_rls_isolation_and_append_only(app_url: str) -> None:  # noqa: F811
    """(c) Symmetric tenant isolation + the P0001 trigger over ES-HS rows."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    _run_id, row_id = _extend_and_run_es(factory, tenant_a)

    with factory() as s:
        set_tenant_context(s, tenant_b)
        assert (
            s.execute(select(VarResult).where(VarResult.id == row_id)).scalar_one_or_none() is None
        )
    with factory() as s:
        assert (
            s.execute(select(VarResult).where(VarResult.id == row_id)).scalar_one_or_none() is None
        )

    with factory() as s:
        set_tenant_context(s, tenant_a)
        with pytest.raises(ProgrammingError) as upd:
            s.execute(text("UPDATE var_result SET var_value = 0 WHERE id = :i"), {"i": row_id})
        assert _is_append_only_violation(upd.value)
        s.rollback()
    with factory() as s:
        set_tenant_context(s, tenant_a)
        with pytest.raises(ProgrammingError) as dele:
            s.execute(text("DELETE FROM var_result WHERE id = :i"), {"i": row_id})
        assert _is_append_only_violation(dele.value)
        s.rollback()
