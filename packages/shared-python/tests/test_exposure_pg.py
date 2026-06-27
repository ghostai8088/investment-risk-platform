"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY tests for P2-3 exposure_aggregate (PROPRIETARY, IA).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
(NOSUPERUSER NOBYPASSRLS). Proves for ``exposure_aggregate``: cross-tenant invisibility +
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
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import SnapshotNotFound
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P2_3 = ("exposure_aggregate",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("portfolio", "instrument", "position", "valuation", "fx_rate", "currency")
_SNAP = ("dataset_snapshot", "dataset_snapshot_component")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_RUN = ("calculation_run",)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)
_ACT = ExposureActor(actor_id="a")


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
        for table in (*_P2_3, *_RUN, *_SNAP, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """A complete multi-currency tenant -> a COMPLETED exposure run. Returns the run_id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        for code in ("USD", "EUR"):
            session.add(_currency(tenant, code))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code="PF",
            name="pf",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="a"),
        )
        for n, (qty, mark, ccy) in enumerate([("100", "12.50", "USD"), ("-200", "7.00", "EUR")]):
            inst = create_instrument(
                session,
                tenant_id=tenant,
                code=f"I{n}",
                name="i",
                asset_class="BOND",
                actor=ReferenceActor(actor_id="a"),
            )
            create_position(
                session,
                portfolio_id=pf.id,
                instrument_id=inst.id,
                acting_tenant=tenant,
                actor=PositionActor(actor_id="a"),
                quantity=Decimal(qty),
                valid_from=_VALID_AT,
            )
            create_valuation(
                session,
                portfolio_id=pf.id,
                instrument_id=inst.id,
                valuation_date=_VD,
                acting_tenant=tenant,
                actor=ValuationActor(actor_id="a"),
                mark_value=Decimal(mark),
                currency_code=ccy,
                valid_from=_VALID_AT,
            )
        capture_fx_rate(
            session,
            base_currency="EUR",
            quote_currency="USD",
            rate_date=_VD,
            rate=Decimal("1.10"),
            acting_tenant=tenant,
            actor=FxRateActor(actor_id="a"),
            valid_from=_VALID_AT,
        )
        session.flush()
        result = run_exposure(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="v1",
            environment_id="ci",
            portfolio_id=pf.id,
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
            base_currency="USD",
        )
        session.commit()
        return result.run.run_id
    finally:
        session.close()


def _currency(tenant: str, code: str):  # noqa: ANN201
    from irp_shared.reference.models import Currency

    return Currency(tenant_id=tenant, code=code, name=code, valid_from=_VALID_AT)


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
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM exposure_aggregate"))
            }
            assert tenants == {a}, "exposure_aggregate leaked cross-tenant"
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
                session.execute(text("SELECT count(*) FROM exposure_aggregate")).scalar_one() == 0
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
            text("SELECT id FROM exposure_aggregate LIMIT 1")
        ).scalar_one()  # POSITIVE control: the row is visible
        with pytest.raises(ProgrammingError) as upd:
            session.execute(
                text(
                    "UPDATE exposure_aggregate SET exposure_amount = 0 WHERE id = CAST(:i AS uuid)"
                ),
                {"i": str(row_id)},
            )
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(
                text("DELETE FROM exposure_aggregate WHERE id = CAST(:i AS uuid)"),
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
    run_id = _seed_and_run(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        snap_id = session.execute(
            text("SELECT input_snapshot_id FROM exposure_aggregate LIMIT 1")
        ).scalar_one()
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "INSERT INTO exposure_aggregate "
                    "(id, tenant_id, system_from, calculation_run_id, input_snapshot_id, "
                    "portfolio_id, instrument_id, base_currency, mark_currency, signed_quantity, "
                    "mark_value, fx_rate, fx_legs, exposure_amount, exposure_type) VALUES "
                    "(gen_random_uuid(), CAST(:forged AS uuid), now(), CAST(:run AS uuid), "
                    "CAST(:snap AS uuid), gen_random_uuid(), gen_random_uuid(), 'USD', 'USD', "
                    "1, 1, 1, '[]', 1, 'MARKET_VALUE')"
                ),
                {"forged": forged, "run": run_id, "snap": str(snap_id)},
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
            # exposure_aggregate is SYMMETRIC (USING == WITH CHECK) + FORCE RLS.
            pol = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE tablename = 'exposure_aggregate'"
                )
            ).one()
            assert pol.qual == pol.with_check, "exposure_aggregate must be SYMMETRIC (not hybrid)"
            assert "current_setting" in pol.qual
            forced = conn.execute(
                text(
                    "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'exposure_aggregate'"
                )
            ).scalar_one()
            assert forced is True
            # The closed 5-table hybrid set is unchanged (USING references SYSTEM, WITH CHECK does
            # not).
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
                text("SELECT input_snapshot_id FROM exposure_aggregate LIMIT 1")
            ).scalar_one()
        finally:
            session.close()
        # Tenant b tries to consume tenant a's snapshot -> fails closed (pre-create refusal).
        session = factory()
        try:
            set_tenant_context(session, b)
            with pytest.raises(SnapshotNotFound):
                run_exposure(
                    session,
                    acting_tenant=b,
                    actor=_ACT,
                    code_version="v1",
                    environment_id="ci",
                    snapshot_id=str(snap_a),
                    base_currency="USD",
                )
            session.rollback()
            set_tenant_context(session, b)
            assert (
                session.execute(text("SELECT count(*) FROM exposure_aggregate")).scalar_one() == 0
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
