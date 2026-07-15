"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY tests for P3-1 sensitivity_result (PROPRIETARY, IA).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser
``irp_app``
(NOSUPERUSER NOBYPASSRLS). Proves for ``sensitivity_result``: cross-tenant invisibility +
no-context->zero rows; the **append-only P0001 TRIGGER** (irp_app HAS UPDATE/DELETE grants + a
POSITIVE CONTROL first, so the rejection is the trigger, NOT a privilege denial); the RLS ``WITH
CHECK`` backstop denies a forged-tenant INSERT (42501); the POSITIVE symmetric-policy + FORCE-RLS
assertion AND the unchanged closed-hybrid-set; a cross-tenant snapshot consume fails closed; and a
verifiable audit chain after a governed run.
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
from irp_shared.marketdata import CurveActor, CurveNode, capture_curve
from irp_shared.risk import SensitivityActor, register_sensitivity_model, run_sensitivities
from irp_shared.snapshot import CurveSelector, SnapshotNotFound

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P3_1 = ("sensitivity_result",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = (
    "curve",
    "curve_point",
    "currency",
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
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_CD = date(2026, 6, 1)
_SRC = "VENDOR_X"
_ACT = SensitivityActor(actor_id="a")


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
        for table in (*_P3_1, *_RUN, *_SNAP, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _currency(tenant: str, code: str):  # noqa: ANN201
    from irp_shared.reference.models import Currency

    return Currency(tenant_id=tenant, code=code, name=code, valid_from=_VALID_AT)


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """A tenant with a captured curve + a registered model -> a COMPLETED sensitivity run."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(_currency(tenant, "USD"))
        session.flush()
        capture_curve(
            session,
            curve_type="SWAP",
            currency_code="USD",
            curve_date=_CD,
            curve_source=_SRC,
            nodes=[
                CurveNode(
                    tenor_label="1Y",
                    tenor_days=365,
                    value_type="ZERO_RATE",
                    point_value=Decimal("0.05"),
                ),
                CurveNode(
                    tenor_label="2Y",
                    tenor_days=730,
                    value_type="ZERO_RATE",
                    point_value=Decimal("0.06"),
                ),
            ],
            acting_tenant=tenant,
            actor=CurveActor(actor_id="a"),
            valid_from=_T0,
        )
        mv = register_sensitivity_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1"
        )
        session.flush()
        result = run_sensitivities(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv.id,
            curve_selectors=[
                CurveSelector(
                    curve_type="SWAP", currency_code="USD", curve_date=_CD, curve_source=_SRC
                )
            ],
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
        )
        session.commit()
        return result.run.run_id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_and_run(factory, a)
        _seed_and_run(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM sensitivity_result"))
            }
            assert tenants == {a}, "sensitivity_result leaked cross-tenant"
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_and_run(factory, str(uuid.uuid4()))
        session = factory()
        try:
            assert (
                session.execute(text("SELECT count(*) FROM sensitivity_result")).scalar_one() == 0
            )
        finally:
            session.close()
    finally:
        engine.dispose()


def test_append_only_trigger_blocks_update_and_delete(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _seed_and_run(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        row_id = session.execute(
            text("SELECT id FROM sensitivity_result LIMIT 1")
        ).scalar_one()  # POSITIVE control: the row is visible
        with pytest.raises(ProgrammingError) as upd:
            session.execute(
                text(
                    "UPDATE sensitivity_result SET sensitivity_value = 0 "
                    "WHERE id = CAST(:i AS uuid)"
                ),
                {"i": str(row_id)},
            )
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(
                text("DELETE FROM sensitivity_result WHERE id = CAST(:i AS uuid)"),
                {"i": str(row_id)},
            )
        assert _is_append_only_violation(dele.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_rejected(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, forged = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        run_id, snap_id, mv_id, curve_id = session.execute(
            text(
                "SELECT calculation_run_id, input_snapshot_id, model_version_id, curve_id "
                "FROM sensitivity_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "INSERT INTO sensitivity_result "
                    "(id, tenant_id, system_from, calculation_run_id, input_snapshot_id, "
                    "model_version_id, curve_id, curve_type, currency_code, reference_key, "
                    "value_type, tenor_days, tenor_label, sensitivity_type, sensitivity_value, "
                    "bump_bps) VALUES "
                    "(gen_random_uuid(), CAST(:forged AS uuid), now(), CAST(:run AS uuid), "
                    "CAST(:snap AS uuid), CAST(:mv AS uuid), CAST(:curve AS uuid), 'SWAP', 'USD', "
                    "'NONE', 'ZERO_RATE', 365, '1Y', 'DV01', -0.0001, 1.0)"
                ),
                {
                    "forged": forged,
                    "run": str(run_id),
                    "snap": str(snap_id),
                    "mv": str(mv_id),
                    "curve": str(curve_id),
                },
            )
        assert _is_rls_violation(exc.value)  # WITH CHECK forbids writing another tenant's row
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_symmetric_policy_and_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            pol = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE tablename = 'sensitivity_result'"
                )
            ).one()
            assert pol.qual == pol.with_check, "sensitivity_result must be SYMMETRIC (not hybrid)"
            assert "current_setting" in pol.qual
            forced = conn.execute(
                text(
                    "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'sensitivity_result'"
                )
            ).scalar_one()
            assert forced is True
            for table in _P1B1_HYBRID:
                p = conn.execute(
                    text("SELECT qual, with_check FROM pg_policies WHERE tablename = :t"),
                    {"t": table},
                ).one()
                assert p.qual != p.with_check, f"{table} hybrid policy changed"
    finally:
        engine.dispose()


def test_cross_tenant_snapshot_consume_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_and_run(factory, a)
        session = factory()
        try:
            set_tenant_context(session, a)
            snap_a = session.execute(
                text("SELECT input_snapshot_id FROM sensitivity_result LIMIT 1")
            ).scalar_one()
        finally:
            session.close()
        session = factory()
        try:
            set_tenant_context(session, b)
            mv_b = register_sensitivity_model(
                session, tenant_id=b, actor_id="b", code_version="risk-v1"
            )
            session.flush()
            with pytest.raises(SnapshotNotFound):
                run_sensitivities(
                    session,
                    acting_tenant=b,
                    actor=_ACT,
                    code_version="risk-v1",
                    environment_id="ci",
                    model_version_id=mv_b.id,
                    snapshot_id=str(snap_a),
                )
            session.rollback()
            set_tenant_context(session, b)
            assert (
                session.execute(text("SELECT count(*) FROM sensitivity_result")).scalar_one() == 0
            )
        finally:
            session.close()
    finally:
        engine.dispose()


def test_audit_chain_verifies(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _seed_and_run(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        assert verify_chain(session, a).ok
    finally:
        session.close()
        engine.dispose()
