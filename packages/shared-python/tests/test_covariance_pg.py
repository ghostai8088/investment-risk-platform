"""PostgreSQL-only proofs for P3-4 ``covariance_result`` (ENT-051, IA — sample v1), run as the
constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role (the CI/pipeline posture):

- symmetric FORCE-RLS tenant isolation (visibility + no-context zero rows + forged-tenant 42501);
- the **P0001 append-only trigger** blocks UPDATE/DELETE at the DB (``irp_app`` is GRANTED
  UPDATE/DELETE so the rejection proves the trigger, not a privilege denial);
- the symmetric policy shape + the closed 5-table hybrid set unchanged;
- cross-tenant snapshot consume fails closed;
- the per-tenant audit hash chain verifies.

The full governed setup (factors → captured return windows → registered model with a declared
window → covariance run) executes through the binders under ``set_tenant_context``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.risk import (
    CovarianceActor,
    register_covariance_model,
    run_covariance,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P3_4 = ("covariance_result",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = (
    "factor",
    "factor_return",
    "model",
    "model_version",
    # VW-1: every binder bind now reads the latest model_validation (the OD-B REJECTED gate).
    "model_validation",
    "model_assumption",
    "model_limitation",
)
_SNAP = ("dataset_snapshot", "dataset_snapshot_component")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_RUN = ("calculation_run",)
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
_ACT = CovarianceActor(actor_id="a")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


@pytest.fixture(scope="module")
def app_url() -> str:
    superuser = make_engine(URL, poolclass=NullPool)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'irp_app') "
                "THEN CREATE ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "ELSE ALTER ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO irp_app"))
        for table in (*_P3_4, *_RUN, *_SNAP, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """A tenant with two captured factor-return windows + a registered window-4 model -> a
    COMPLETED covariance run (its run_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        factor_ids: list[str] = []
        for code, values in (
            (f"F_A_{uuid.uuid4().hex[:6]}", ("0.01", "0.02", "0.03", "0.04")),
            (f"F_B_{uuid.uuid4().hex[:6]}", ("0.04", "0.03", "0.02", "0.01")),
        ):
            fid = capture_factor(
                session,
                factor_code=code,
                factor_source="VENDOR_F",
                factor_family="CURRENCY",
                currency_code=None,
                acting_tenant=tenant,
                actor=FactorActor(actor_id="s"),
                valid_from=_T0,
            ).id
            factor = resolve_factor(session, fid, acting_tenant=tenant)
            for d, v in zip(_D, values, strict=True):
                capture_factor_return(
                    session,
                    factor,
                    return_date=d,
                    return_value=Decimal(v),
                    acting_tenant=tenant,
                    actor=FactorActor(actor_id="s"),
                    valid_from=_T0,
                )
            factor_ids.append(fid)
        mv = register_covariance_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
        )
        session.flush()
        result = run_covariance(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv.id,
            factor_ids=factor_ids,
            as_of_valid_at=_VALID_AT,
        )
        assert result.status == "COMPLETED" and len(result.rows) == 3  # F·(F+1)/2 for F = 2
        session.commit()
        return result.run.run_id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    run1 = _seed_and_run(factory, t1)
    _seed_and_run(factory, t2)

    session = factory()
    try:
        set_tenant_context(session, t1)
        rows = session.execute(text("SELECT calculation_run_id FROM covariance_result")).fetchall()
        assert rows and all(str(r[0]) == run1 for r in rows)  # only t1's rows visible
    finally:
        session.close()
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_and_run(factory, str(uuid.uuid4()))
    session = factory()
    try:
        count = session.execute(text("SELECT count(*) FROM covariance_result")).scalar_one()
        assert count == 0  # FORCE RLS: no tenant context -> zero rows
    finally:
        session.close()
        engine.dispose()


def test_append_only_trigger_blocks_update_and_delete(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        # irp_app HAS UPDATE/DELETE grants -> a rejection is the P0001 trigger, not 42501.
        with pytest.raises(ProgrammingError) as upd:
            session.execute(text("UPDATE covariance_result SET covariance_value = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM covariance_result"))
        assert _is_append_only_violation(dele.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_rejected(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant, victim = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = session.execute(
            text(
                "SELECT calculation_run_id, input_snapshot_id, model_version_id "
                "FROM covariance_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO covariance_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, factor_id_1, "
                    "factor_id_2, factor_code_1, factor_code_2, statistic_type, return_type, "
                    "frequency, n_observations, window_start, window_end, covariance_value) "
                    "VALUES (:id, :victim, now(), :run, :snap, :mv, :f1, :f2, 'A', 'B', "
                    "'COVARIANCE', 'SIMPLE', 'DAILY', 4, :ws, :we, 0.0001)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,  # a FOREIGN tenant_id under t1's context
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "f1": str(uuid.uuid4()),
                    "f2": str(uuid.uuid4()),
                    "ws": _D[0],
                    "we": _D[-1],
                },
            )
        assert _is_rls_violation(forged.value)  # WITH CHECK rejects the forged tenant (42501)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_symmetric_policy_and_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(URL, poolclass=NullPool)  # structural read as the owner
    try:
        with engine.connect() as conn:
            qual, check = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE tablename = 'covariance_result'"
                )
            ).one()
            assert "app.current_tenant" in qual and "app.current_tenant" in check
            assert "SYSTEM" not in qual.upper().replace("CURRENT_SETTING", "")  # never hybrid
            # Probe by the REAL system-tenant id from the entitlement bootstrap — the prior
            # hardcoded ...000000 UUID matched ZERO policies, making the assertion vacuous
            # (the 2026-07 P3-4 review finding).
            from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

            hybrid = conn.execute(
                text("SELECT tablename FROM pg_policies WHERE qual LIKE :pat ORDER BY tablename"),
                {"pat": f"%{SYSTEM_TENANT_ID}%"},
            ).fetchall()
            # EQUALITY, not subset (the 2026-07 review fold): a dropped hybrid policy on the
            # closed 5-table reference set is as much a defect as an added one.
            assert {r[0] for r in hybrid} == set(_P1B1_HYBRID)
    finally:
        engine.dispose()


def test_cross_tenant_snapshot_consume_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, t1)

    session = factory()
    try:
        set_tenant_context(session, t1)
        snap = session.execute(
            text(
                "SELECT input_snapshot_id FROM calculation_run "
                "WHERE run_type = 'COVARIANCE' AND tenant_id = :t LIMIT 1"
            ),
            {"t": t1},
        ).scalar_one()
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, t2)
        mv = register_covariance_model(
            session, tenant_id=t2, actor_id="a", code_version="risk-v1", window_observations=4
        )
        session.flush()
        from irp_shared.snapshot import SnapshotNotFound

        with pytest.raises(SnapshotNotFound):
            run_covariance(
                session,
                acting_tenant=t2,
                actor=_ACT,
                code_version="risk-v1",
                environment_id="ci",
                model_version_id=mv.id,
                snapshot_id=str(snap),  # t1's snapshot under t2's context
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_audit_chain_verifies(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        assert verify_chain(session, tenant).ok is True
    finally:
        session.close()
        engine.dispose()
