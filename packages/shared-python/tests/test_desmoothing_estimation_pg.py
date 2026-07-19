"""PostgreSQL-only proofs for DS-2 (migration ``0042_desmoothing_estimated_alpha``):

- (a) an OKUNEV_WHITE run's NULL-alpha rows SURVIVE under the constrained ``irp_app`` role (the
  relaxed column + RLS posture), and the ``ck_desmoothed_return_result_stderr_summary_only``
  CHECK refuses a hand-minted PERIOD row carrying ``alpha_stderr`` (the summary-only invariant is
  DB-enforced — the 0028 review-forced element carried);
- (b) the NON-SUPERUSER downgrade path (the 0041 owner-via-membership mechanics VERBATIM): a
  NOSUPERUSER/NOBYPASSRLS role granted MEMBERSHIP in the table-owner role drives the REAL
  ``0042`` module's ``downgrade()`` through an alembic ``MigrationContext`` — the FORCE-RLS
  zero-row trap is demonstrated live (an unsandwiched DELETE matches nothing), then the sandwich
  ACTUALLY deletes the NULL-alpha rows, ``alpha`` re-tightens NOT NULL, ``alpha_stderr`` drops;
  assert-then-ROLLBACK restores the widened state for every later suite in the shared-DB job
  (asserted at module end).

The grants/role posture for (a) is REUSED from ``test_desmoothed_return_pg`` (same tables — no
new grant surface). Leg (b) mints its own throwaway role via the superuser URL.
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from test_desmoothed_return import _DS2_DATES, _smoothed_mark_values
from test_desmoothed_return_pg import (  # noqa: F401 - the shared role/grant fixture
    URL,
    app_url,
)

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_okunev_white_model,
    run_desmoothed_return,
)
from irp_shared.perf.models import DesmoothedReturnResult
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_T0 = datetime(2023, 1, 1, tzinfo=UTC)
_ACT = DesmoothedReturnActor(actor_id="analyst")
_MIG_ROLE = "irp_mig_smoke_0042"
_MIG_PW = "mig_smoke_pw"


def _seed_and_run_ow(factory, tenant: str) -> str:  # noqa: ANN001
    """The full chain -> a COMPLETED OKUNEV_WHITE (m=2) desmoothing run (its run_id)."""
    from irp_shared.reference.models import Currency

    values = _smoothed_mark_values()
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(Currency(tenant_id=tenant, code="USD", name="USD", valid_from=_T0))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"PE-{uuid.uuid4().hex[:6]}",
            name="private book",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        ).id
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"PE-FUND-{uuid.uuid4().hex[:6]}",
            name="Buyout Fund IX",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        for d, v in zip(_DS2_DATES, values, strict=True):
            create_valuation(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=d,
                acting_tenant=tenant,
                actor=ValuationActor(actor_id="s"),
                mark_value=Decimal(v),
                currency_code="USD",
                valid_from=_T0,
            )
        session.flush()
        mv = register_desmoothed_return_okunev_white_model(
            session, tenant_id=tenant, actor_id="a", code_version="ds2-v1", ow_max_order=2
        )
        session.flush()
        result = run_desmoothed_return(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="ds2-v1",
            environment_id="ci",
            model_version_id=mv.id,
            portfolio_id=pf,
            instrument_id=inst,
            window_start=_DS2_DATES[0],
            window_end=_DS2_DATES[-1],
        )
        assert result.status == "COMPLETED", result.failure_reason
        assert all(r.alpha is None for r in result.rows)
        run_id = result.run.run_id
        session.commit()
        return run_id
    finally:
        session.close()


def test_ow_null_alpha_rows_survive_and_check_guards_summary_only(app_url: str) -> None:  # noqa: F811
    """(a) The OW chain executes under the constrained role and its NULL-alpha rows persist; a
    hand-minted PERIOD row with a non-null alpha_stderr refuses at the DB (the 0042 CHECK)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    run_id = _seed_and_run_ow(factory, tenant)

    with factory() as s:
        set_tenant_context(s, tenant)
        rows = (
            s.execute(
                select(DesmoothedReturnResult).where(
                    DesmoothedReturnResult.calculation_run_id == run_id
                )
            )
            .scalars()
            .all()
        )
        assert rows and all(r.alpha is None for r in rows)
        template = next(r for r in rows if r.metric_type == "DESMOOTHED_PERIOD")
        # A PERIOD row carrying alpha_stderr violates the summary-only CHECK.
        s.add(
            DesmoothedReturnResult(
                tenant_id=tenant,
                calculation_run_id=template.calculation_run_id,
                input_snapshot_id=template.input_snapshot_id,
                model_version_id=template.model_version_id,
                portfolio_id=template.portfolio_id,
                instrument_id=template.instrument_id,
                metric_type="DESMOOTHED_PERIOD",
                period_start=template.period_end,  # a fresh grain slot
                period_end=template.period_end,
                metric_value=Decimal("0.01"),
                observed_return=Decimal("0.01"),
                begin_mark=Decimal("100"),
                end_mark=Decimal("101"),
                alpha=Decimal("0.5"),
                mark_currency="USD",
                alpha_stderr=Decimal("0.1"),  # the violation
            )
        )
        with pytest.raises(IntegrityError) as excinfo:
            s.flush()
        assert "stderr_summary_only" in str(excinfo.value)
        s.rollback()
    engine.dispose()


def test_downgrade_body_under_nonsuperuser_owner_member_role(app_url: str) -> None:  # noqa: F811
    """(b) The 0041 owner-via-membership mechanics VERBATIM against 0042: the zero-row trap
    demonstrated, then the real ``downgrade()`` deletes the NULL-alpha rows and re-tightens;
    assert-then-ROLLBACK restores the widened state."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run_ow(factory, tenant)

    su = create_engine(URL, poolclass=NullPool)
    with su.connect() as c:
        owner_role = c.execute(
            text("SELECT tableowner FROM pg_tables WHERE tablename='desmoothed_return_result'")
        ).scalar_one()
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

    host_part = URL.split("@", 1)[1] if "@" in URL else URL.split("://", 1)[1]
    scheme = URL.split("://", 1)[0]
    mig_engine = create_engine(f"{scheme}://{_MIG_ROLE}:{_MIG_PW}@{host_part}", poolclass=NullPool)

    mig_path = (
        pathlib.Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0042_desmoothing_estimated_alpha.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0042_desmoothing", mig_path)
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with mig_engine.connect() as conn:
        # The RECORDED trap, live under this role: an UNSANDWICHED delete under FORCE RLS (no
        # tenant GUC) silently matches ZERO rows.
        trans = conn.begin()
        gone = conn.execute(
            text("DELETE FROM desmoothed_return_result WHERE alpha IS NULL")
        ).rowcount
        assert gone == 0  # the OW rows EXIST (seeded above) — RLS hid them
        trans.rollback()

        from irp_shared.models import metadata as target_metadata

        trans = conn.begin()
        ctx = MigrationContext.configure(conn, opts={"target_metadata": target_metadata})
        with Operations.context(ctx):
            mig.downgrade()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        remaining = conn.execute(
            text("SELECT count(*) FROM desmoothed_return_result WHERE alpha IS NULL")
        ).scalar_one()
        assert remaining == 0  # the sandwich ACTUALLY deleted the OW rows
        # alpha is NOT NULL again and alpha_stderr is gone.
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE "
                "table_name='desmoothed_return_result' AND column_name='alpha'"
            )
        ).scalar_one()
        assert nullable == "NO"
        stderr_col = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE "
                "table_name='desmoothed_return_result' AND column_name='alpha_stderr'"
            )
        ).scalar_one()
        assert stderr_col == 0
        trans.rollback()  # PG DDL is transactional — the widened state is restored

    # END-OF-BODY: the widened state is live for every later suite in this shared DB.
    with su.connect() as c:
        nullable = c.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE "
                "table_name='desmoothed_return_result' AND column_name='alpha'"
            )
        ).scalar_one()
        assert nullable == "YES"
    su.dispose()
    mig_engine.dispose()
    engine.dispose()
