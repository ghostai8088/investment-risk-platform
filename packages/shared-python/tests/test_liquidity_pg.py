"""ENT-071 ``liquidity_result`` on the AUTHORITATIVE engine (LQ-1).

The properties SQLite structurally cannot test: symmetric FORCE RLS, the P0001 append-only trigger,
partial-unique predicates, and the CHECK constraints as the DATABASE actually named them.

The CHECK-name assertion reads ``pg_constraint`` rather than comparing migration text to ORM text.
That is the only gate that catches the double-prefix defect: the name is built at DDL time, so no
string literal in the migration is over-length, and ``alembic check`` does not compare CHECKs at
all. CON-1 shipped that defect past three review lanes doing text-vs-text comparison.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.liquidity.models import LiquidityResult

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

TENANT_A = "aaaaaaaa-1111-2222-3333-444444444444"
TENANT_B = "bbbbbbbb-1111-2222-3333-444444444444"


@pytest.fixture(scope="module")
def app_url() -> str:
    """The constrained ``irp_app`` role (NOSUPERUSER NOBYPASSRLS).

    The RLS assertions MUST run as this role. The default ``irp`` connection is a superuser with
    BYPASSRLS, and FORCE RLS does not apply to a BYPASSRLS role — so a cross-tenant test run as
    ``irp`` proves nothing about isolation. My first draft did exactly that and reported "RLS did
    not isolate the tenant", which is the honest outcome of a test asking the wrong role.
    """
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
        for table in (
            "liquidity_result",
            "model",
            "model_version",
            "calculation_run",
            "dataset_snapshot",
        ):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="module")
def factory(app_url):  # noqa: ANN001, ANN201
    engine = make_engine(app_url, poolclass=NullPool)
    yield make_session_factory(engine)
    engine.dispose()


def _seed_parents(conn, tenant: str) -> dict[str, str]:
    """Minimal REAL parents so the result row is written under REAL foreign keys."""
    ids = {k: str(uuid.uuid4()) for k in ("model", "version", "run", "snapshot", "portfolio")}
    now = datetime.now(UTC)
    conn.execute(
        text(
            "INSERT INTO model (id, tenant_id, valid_from, created_at, updated_at, "
            "record_version, code, name, model_type, is_active) VALUES "
            "(:i, :t, :n, :n, :n, 1, :c, 'Liquidity', 'LIQUIDITY', true)"
        ),
        {"i": ids["model"], "t": tenant, "n": now, "c": f"risk.liquidity_tiers.{ids['model'][:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO model_version (id, tenant_id, system_from, model_id, version_label) "
            "VALUES (:i, :t, :n, :m, 'v1')"
        ),
        {"i": ids["version"], "t": tenant, "n": now, "m": ids["model"]},
    )
    conn.execute(
        text(
            "INSERT INTO calculation_run (id, tenant_id, system_from, run_id, run_type, status, "
            "initiated_by, created_at) VALUES (:i, :t, :n, :i, 'LIQUIDITY', 'COMPLETED', 'pg', :n)"
        ),
        {"i": ids["run"], "t": tenant, "n": now},
    )
    conn.execute(
        text(
            "INSERT INTO dataset_snapshot (id, tenant_id, system_from, created_at, updated_at, "
            "label, purpose, as_of_valid_at, as_of_known_at, as_of_valuation_date, "
            "binding_predicate_version, component_count, manifest_hash) VALUES "
            "(:i, :t, :n, :n, :n, 'pg', 'LIQUIDITY_INPUT', :n, :n, :d, 'v1', 1, 'abc')"
        ),
        {"i": ids["snapshot"], "t": tenant, "n": now, "d": now.date()},
    )
    return ids


def _insert_detail(conn, tenant: str, ids: dict[str, str], **over: object) -> None:
    params = {
        "i": str(uuid.uuid4()),
        "t": tenant,
        "n": datetime.now(UTC),
        "r": ids["run"],
        "s": ids["snapshot"],
        "m": ids["version"],
        "p": ids["portfolio"],
        "bucket": "ILLIQUID",
        "basis": "INVESTED_LONG",
        **over,
    }
    conn.execute(
        text(
            "INSERT INTO liquidity_result (id, tenant_id, system_from, calculation_run_id, "
            "input_snapshot_id, model_version_id, portfolio_id, row_kind, bucket_code, "
            "metric_type, denominator_basis, long_amount, tier_share) VALUES "
            "(:i, :t, :n, :r, :s, :m, :p, 'DETAIL', :bucket, 'TIER_SHARE', :basis, 100, 0.5)"
        ),
        params,
    )


def test_check_constraint_names_are_single_prefixed_in_the_live_catalog(factory) -> None:  # noqa: ANN001
    """Trap T1, asked of the DATABASE rather than of the migration text."""
    session = factory()
    try:
        rows = session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'liquidity_result'::regclass AND contype = 'c'"
            )
        ).scalars()
        names = sorted(rows)
        assert names == [
            "ck_liquidity_result_coverage_only_on_summary",
            "ck_liquidity_result_denominator_basis",
            "ck_liquidity_result_detail_shape",
            "ck_liquidity_result_row_kind",
            "ck_liquidity_result_summary_shape",
        ]
        assert all(len(n) <= 63 for n in names)
        assert not any(n.startswith("ck_liquidity_result_ck_") for n in names)
    finally:
        session.close()


def test_rls_is_forced_and_symmetric(factory) -> None:  # noqa: ANN001
    session = factory()
    try:
        row = session.execute(
            text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                "pg_get_expr(p.polqual, p.polrelid) = pg_get_expr(p.polwithcheck, p.polrelid) "
                "FROM pg_class c JOIN pg_policy p ON p.polrelid = c.oid "
                "WHERE c.relname = 'liquidity_result'"
            )
        ).one()
        assert row[0] is True, "RLS not enabled"
        assert row[1] is True, "RLS not FORCED (the owner would bypass it)"
        assert row[2] is True, "USING != WITH CHECK — the policy is not symmetric"
    finally:
        session.close()


def test_a_tenant_cannot_read_another_tenants_rows(factory) -> None:  # noqa: ANN001
    """Cross-tenant negative, asserted BY TABLE NAME on the child (the CAL-1a lesson)."""
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        ids["portfolio"] = str(uuid.uuid4())
        _insert_detail(session.connection(), TENANT_A, ids)
        session.commit()
    finally:
        session.close()

    verify = factory()
    try:
        # A FRESH session: set_tenant_context is TRANSACTION-LOCAL and clears at COMMIT (the
        # MD-H1 annex-4 trap that turned a DATA-1 fold red).
        set_tenant_context(verify, TENANT_A)
        assert verify.query(LiquidityResult).count() >= 1
    finally:
        verify.close()

    other = factory()
    try:
        set_tenant_context(other, TENANT_B)
        assert other.query(LiquidityResult).count() == 0, "RLS did not isolate the tenant"
    finally:
        other.close()


def test_the_append_only_trigger_refuses_update_and_delete(factory) -> None:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        ids["portfolio"] = str(uuid.uuid4())
        _insert_detail(session.connection(), TENANT_A, ids)
        session.commit()

        set_tenant_context(session, TENANT_A)
        with pytest.raises(Exception, match="append-only"):
            session.execute(
                text("UPDATE liquidity_result SET tier_share = 0.99 WHERE portfolio_id = :p"),
                {"p": ids["portfolio"]},
            )
        session.rollback()

        set_tenant_context(session, TENANT_A)
        with pytest.raises(Exception, match="append-only"):
            session.execute(
                text("DELETE FROM liquidity_result WHERE portfolio_id = :p"),
                {"p": ids["portfolio"]},
            )
        session.rollback()
    finally:
        session.close()


def test_the_detail_partial_unique_binds_per_portfolio(factory) -> None:  # noqa: ANN001
    """portfolio_id is IN the key: two portfolios may hold the SAME tier bucket in one run, and a
    single portfolio may not hold it twice."""
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        ids["portfolio"] = str(uuid.uuid4())
        _insert_detail(session.connection(), TENANT_A, ids)
        # A DIFFERENT portfolio, same run, same bucket -> legal.
        second = dict(ids, portfolio=str(uuid.uuid4()))
        _insert_detail(session.connection(), TENANT_A, second, p=second["portfolio"])
        session.commit()

        set_tenant_context(session, TENANT_A)
        with pytest.raises(Exception, match="uq_liquidity_result_detail"):
            _insert_detail(session.connection(), TENANT_A, ids)
            session.flush()
        session.rollback()
    finally:
        session.close()
