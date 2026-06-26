"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY tests for P2-1 dataset_snapshot (PROPRIETARY, IA).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role (NOSUPERUSER NOBYPASSRLS). Proves, for BOTH ``dataset_snapshot`` and
``dataset_snapshot_component``: cross-tenant invisibility + no-context->zero rows; the **append-only
P0001 TRIGGER** (irp_app HAS UPDATE/DELETE grants + a POSITIVE CONTROL first, so the rejection is
the trigger, NOT a privilege denial); the RLS ``WITH CHECK`` backstop denies a forged-tenant INSERT
(42501, distinct from P0001); the POSITIVE symmetric-policy + FORCE-RLS assertion AND the unchanged
closed-hybrid-set; the cross-tenant binding fail-closed at the service layer; and a verifiable audit
chain after a governed create.
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
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.portfolio import PortfolioActor, PortfolioNotVisible, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import SnapshotActor, build_snapshot, list_components
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P2_1 = ("dataset_snapshot", "dataset_snapshot_component")
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("portfolio", "instrument", "position", "valuation")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
# Fixed FUTURE knowledge cutoff (>= the wall-clock system_from the binders stamp; deterministic).
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 3, 31)
_ACT = SnapshotActor(actor_id="a")


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
        for table in (*_P2_1, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_dataset(factory, tenant: str) -> str:  # noqa: ANN001
    """A complete tenant (portfolio + instrument + position + marked valuation). Returns pf id."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code="PF",
            name="pf",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="a"),
        )
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code="INST",
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
            quantity=Decimal("100"),
            valid_from=_VALID_AT,
        )
        create_valuation(
            session,
            portfolio_id=pf.id,
            instrument_id=inst.id,
            valuation_date=_VD,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="a"),
            mark_value=Decimal("12.50"),
            valid_from=_VALID_AT,
        )
        session.commit()
        return pf.id
    finally:
        session.close()


def _seed_snapshot(factory, tenant: str) -> str:  # noqa: ANN001
    pf_id = _seed_dataset(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        header = build_snapshot(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            purpose="TEST",
            portfolio_id=pf_id,
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
            as_of_valuation_date=_VD,
        )
        session.commit()
        return header.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_snapshot(factory, a)
        _seed_snapshot(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            for table in _P2_1:
                tenants = {
                    str(r[0])
                    for r in session.execute(text(f"SELECT DISTINCT tenant_id FROM {table}"))
                }
                assert tenants == {a}, f"{table} leaked cross-tenant"
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_snapshot(factory, str(uuid.uuid4()))
        session = factory()
        try:
            for table in _P2_1:
                assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_append_only_trigger_blocks_update_and_delete(app_url: str) -> None:
    # The P0001 append-only TRIGGER on BOTH tables: irp_app HAS UPDATE/DELETE grants, so a rejection
    # proves the trigger, not a privilege denial; the POSITIVE CONTROL first shows the row.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    snap_id = _seed_snapshot(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        assert (
            session.execute(
                text("SELECT count(*) FROM dataset_snapshot WHERE id = CAST(:i AS uuid)"),
                {"i": snap_id},
            ).scalar_one()
            == 1
        )
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE dataset_snapshot SET label = 'x' WHERE id = CAST(:i AS uuid)"),
                {"i": snap_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("DELETE FROM dataset_snapshot_component WHERE snapshot_id = CAST(:i AS uuid)"),
                {"i": snap_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_denied(app_url: str) -> None:
    # The RLS WITH CHECK backstop: an INSERT stamping a FOREIGN tenant_id is denied (42501) —
    # distinct from the P0001 trigger (INSERT does not fire the UPDATE/DELETE trigger).
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        session = factory()
        try:
            set_tenant_context(session, a)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(
                        "INSERT INTO dataset_snapshot "
                        "(id, tenant_id, system_from, created_at, updated_at, label, purpose, "
                        "as_of_valid_at, as_of_known_at, as_of_valuation_date, "
                        "binding_predicate_version, component_count, manifest_hash) VALUES "
                        "(CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), 'x', 'TEST', "
                        "now(), now(), CURRENT_DATE, 'v1', 0, 'h')"
                    ),
                    {"id": str(uuid.uuid4()), "b": b},
                )
            assert _is_rls_violation(exc.value)  # 42501 WITH CHECK, not P0001
            session.rollback()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P2_1:
                qual, with_check = conn.execute(
                    text(
                        "SELECT qual, with_check FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).one()
                assert SYSTEM_TENANT_ID not in qual, f"{table} must NOT be hybrid"
                assert SYSTEM_TENANT_ID not in with_check
                assert qual == with_check, f"{table} policy must be symmetric (USING == WITH CHECK)"
                enabled, forced = conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
                    ),
                    {"t": table},
                ).one()
                assert enabled is True and forced is True, f"{table}: FORCE RLS must be on"
    finally:
        engine.dispose()


def test_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            hybrid = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT tablename FROM pg_policies "
                        "WHERE schemaname='public' AND qual LIKE :p"
                    ),
                    {"p": f"%{SYSTEM_TENANT_ID}%"},
                )
            }
            assert hybrid == set(_P1B1_HYBRID), f"hybrid set drifted: {hybrid}"
    finally:
        engine.dispose()


def test_cross_tenant_binding_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_pf = _seed_dataset(factory, b)
    _seed_dataset(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(PortfolioNotVisible):  # service predicate, NOT a 42501
            build_snapshot(
                session,
                acting_tenant=a,
                actor=_ACT,
                purpose="TEST",
                portfolio_id=b_pf,
                as_of_valid_at=_VALID_AT,
                as_of_known_at=_KNOWN_AT,
                as_of_valuation_date=_VD,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_audit_chain_after_create(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _seed_snapshot(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        n = session.execute(
            text("SELECT count(*) FROM audit_event WHERE event_type = 'SNAPSHOT.CREATE'")
        ).scalar_one()
        assert n == 1
        assert verify_chain(session, a).ok is True
    finally:
        session.close()
        engine.dispose()


def test_components_must_be_read_before_commit_under_force_rls(app_url: str) -> None:
    # Regression for the POST /snapshots response contract. The handler builds the response (incl.
    # list_components) BEFORE db.commit(): the transaction-local app.current_tenant GUC clears at
    # COMMIT, after which the same tenant-scoped read runs context-less and, under FORCE RLS, hits
    # ZERO rows. Proves both halves — full BEFORE commit, empty AFTER (no re-set) — which is why the
    # endpoint serializes pre-commit so its 201 body always carries the components.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    pf_id = _seed_dataset(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        header = build_snapshot(
            session,
            acting_tenant=a,
            actor=_ACT,
            purpose="TEST",
            portfolio_id=pf_id,
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
            as_of_valuation_date=_VD,
        )
        before = list_components(session, snapshot_id=header.id, acting_tenant=a)
        assert header.component_count > 0
        assert len(before) == header.component_count  # GUC live -> full set
        session.commit()  # transaction-local GUC clears here
        after = list_components(session, snapshot_id=header.id, acting_tenant=a)
        assert (
            after == []
        )  # context-less read under FORCE RLS -> zero rows (why we read pre-commit)
    finally:
        session.close()
        engine.dispose()
