"""ENT-072 ``report_generation`` on the AUTHORITATIVE engine (RPT-1).

The properties SQLite structurally cannot test: symmetric FORCE RLS, the P0001 append-only trigger,
and — the one that matters most for this table — whether the single UNIQUE key is VACUOUS.

**Why the unique key gets its own catalog assertion.** ``uq_report_generation_run_portfolio`` is the
only thing standing between "one generation per run" and a run that silently produced two different
reports. On PostgreSQL a UNIQUE index is NULLS DISTINCT by default, so a nullable column inside the
key makes the key unenforceable for exactly the rows that matter — the defect CON-1 shipped and
CAL-1b re-found. Comparing migration text to ORM text cannot catch it, because both can declare
``nullable=False`` and still lose it to a later ALTER. So the assertion reads ``pg_attribute`` and
asks the live database whether every key column is ``attnotnull``.

**Where the tenant fence actually is.** The cross-tenant binding test below is deliberately written
as a DISCOVERY, not an assumption: PostgreSQL runs referential-integrity checks in a mode that
bypasses row-level security, so an FK to a parent this tenant cannot SELECT may still resolve. The
test asserts what the engine actually does, and names the consequence either way — because if the
database does not fence it, the service-layer refusal in ``report/service.py`` is the ONLY fence,
and a reviewer needs to know that from the test rather than infer it.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.report.models import ReportGeneration

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

TENANT_A = "aaaaaaaa-7272-4a4a-8b8b-cccccccccccc"
TENANT_B = "bbbbbbbb-7272-4a4a-8b8b-cccccccccccc"

#: The columns of the single UNIQUE key. Named here so the non-vacuity assertion cannot drift into
#: agreeing with whatever the index happens to contain.
_UNIQUE_KEY_COLUMNS = ("calculation_run_id", "portfolio_id")


@pytest.fixture(scope="module")
def app_url() -> str:
    """The constrained ``irp_app`` role (NOSUPERUSER NOBYPASSRLS).

    The RLS assertions MUST run as this role. The default connection is a superuser with BYPASSRLS,
    and FORCE RLS does not apply to a BYPASSRLS role — so a cross-tenant test run as the superuser
    proves nothing about isolation (the LQ-1 lesson, and REF-1's before it).
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
            "report_generation",
            "portfolio",
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
    """Minimal REAL parents so the report row is written under REAL foreign keys.

    Every one of the three is a genuine row rather than a bare UUID: ``report_generation`` carries
    an FK to each, so seeding fake ids would make the insert fail for the wrong reason and turn a
    green cross-tenant test into an accident.
    """
    ids = {k: str(uuid.uuid4()) for k in ("portfolio", "run", "snapshot")}
    conn.execute(
        text(
            "INSERT INTO portfolio (id, tenant_id, valid_from, created_at, updated_at, code, name,"
            " node_type, status, record_version)"
            " VALUES (:id, :t, now(), now(), now(), :code, 'p', 'ACCOUNT', 'ACTIVE', 1)"
        ),
        {"id": ids["portfolio"], "t": tenant, "code": f"pf-{uuid.uuid4().hex[:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO calculation_run (run_id, id, tenant_id, system_from, run_type, status,"
            " initiated_by, code_version, environment_id, created_at)"
            " VALUES (:id, :id, :t, now(), 'REPORT', 'COMPLETED', 'seed', 'v', 'test', now())"
        ),
        {"id": ids["run"], "t": tenant},
    )
    conn.execute(
        text(
            "INSERT INTO dataset_snapshot (id, tenant_id, system_from, created_at, updated_at,"
            " label, purpose, as_of_valid_at, as_of_known_at, as_of_valuation_date,"
            " binding_predicate_version, component_count, manifest_hash) VALUES"
            " (:id, :t, now(), now(), now(), 'pg', 'REPORT_INPUT', now(), now(), :d, 'v1', 1, 'h')"
        ),
        {"id": ids["snapshot"], "t": tenant, "d": datetime.now(UTC).date()},
    )
    return ids


def _insert_report(conn, tenant: str, ids: dict[str, str], **over: object) -> str:
    """One report row via raw SQL — the ORM listeners are bypassed on purpose, so what is proven
    here is the DATABASE's behaviour rather than the application's."""
    row_id = str(uuid.uuid4())
    params: dict[str, object] = {
        "i": row_id,
        "t": tenant,
        "r": ids["run"],
        "s": ids["snapshot"],
        "p": ids["portfolio"],
        "h": hashlib.sha256(row_id.encode()).hexdigest(),
        "d": datetime.now(UTC).date(),
        **over,
    }
    conn.execute(
        text(
            "INSERT INTO report_generation (id, tenant_id, system_from, calculation_run_id,"
            " input_snapshot_id, portfolio_id, report_code, report_version_label, render_format,"
            " as_of_date, content_hash, generated_at, generated_by) VALUES"
            " (:i, :t, now(), :r, :s, :p, 'report.risk_summary', 'v1', 'HTML', :d, :h, now(), 'pg')"
        ),
        params,
    )
    return row_id


def test_rls_is_forced_and_symmetric(factory) -> None:  # noqa: ANN001
    session = factory()
    try:
        row = session.execute(
            text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                "pg_get_expr(p.polqual, p.polrelid) = pg_get_expr(p.polwithcheck, p.polrelid) "
                "FROM pg_class c JOIN pg_policy p ON p.polrelid = c.oid "
                "WHERE c.relname = 'report_generation'"
            )
        ).one()
        assert row[0] is True, "RLS not enabled"
        assert row[1] is True, "RLS not FORCED (the owner would bypass it)"
        assert row[2] is True, "USING != WITH CHECK — the policy is not symmetric"
    finally:
        session.close()


def test_a_tenant_cannot_read_another_tenants_report(factory) -> None:  # noqa: ANN001
    """A report names a specific book's risk position. Cross-tenant visibility is the leak."""
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        _insert_report(session.connection(), TENANT_A, ids)
        session.commit()
    finally:
        session.close()

    verify = factory()
    try:
        # A FRESH session: set_tenant_context is TRANSACTION-LOCAL and clears at COMMIT (the
        # MD-H1 annex-4 trap that turned a DATA-1 fold red).
        set_tenant_context(verify, TENANT_A)
        assert verify.query(ReportGeneration).count() >= 1
    finally:
        verify.close()

    other = factory()
    try:
        set_tenant_context(other, TENANT_B)
        assert other.query(ReportGeneration).count() == 0, "RLS did not isolate the tenant"
    finally:
        other.close()


def test_a_tenant_cannot_write_a_row_stamped_for_another_tenant(factory) -> None:  # noqa: ANN001
    """The WITH CHECK half, asserted BEHAVIOURALLY and not only in the catalog.

    Mutation-proving found this gap: dropping ``WITH CHECK`` to ``true`` was killed only by the
    catalog test, so the suite could tell you the policy LOOKED symmetric while nothing demonstrated
    what asymmetry would actually permit — a tenant writing a report row stamped for someone else,
    which the read test would then obligingly hide from both of them.
    """
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        with pytest.raises(Exception, match="row-level security|violates"):
            _insert_report(session.connection(), TENANT_B, ids)
            session.flush()
        session.rollback()
    finally:
        session.close()


def test_the_append_only_trigger_refuses_update_and_delete(factory) -> None:  # noqa: ANN001
    """The DB fence, not the ORM listener — raw SQL, which the listeners never see.

    ``content_hash`` is the column mutated on purpose: it is the one an attacker would rewrite to
    make a tampered report regenerate 'cleanly'.
    """
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        row_id = _insert_report(session.connection(), TENANT_A, ids)
        session.commit()

        set_tenant_context(session, TENANT_A)
        with pytest.raises(Exception, match="append-only"):
            session.execute(
                text("UPDATE report_generation SET content_hash = :h WHERE id = :i"),
                {"h": "0" * 64, "i": row_id},
            )
        session.rollback()

        set_tenant_context(session, TENANT_A)
        with pytest.raises(Exception, match="append-only"):
            session.execute(text("DELETE FROM report_generation WHERE id = :i"), {"i": row_id})
        session.rollback()

        # The row is STILL THERE. Without this, both refusals could be satisfied by a statement
        # that errored for an unrelated reason after the row had already gone.
        set_tenant_context(session, TENANT_A)
        assert (
            session.execute(
                text("SELECT count(*) FROM report_generation WHERE id = :i"), {"i": row_id}
            ).scalar_one()
            == 1
        )
    finally:
        session.close()


def test_the_unique_key_is_not_vacuous_in_the_live_catalog(factory) -> None:  # noqa: ANN001
    """Trap: a nullable column inside a UNIQUE key is unenforceable on PostgreSQL.

    Asked of ``pg_attribute`` rather than of the migration text — a later ``ALTER COLUMN DROP NOT
    NULL`` would leave both the ORM and the migration reading correct while the key had gone soft.
    """
    session = factory()
    try:
        rows = session.execute(
            text(
                "SELECT a.attname, a.attnotnull, i.indisunique "
                "FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                "WHERE c.relname = 'uq_report_generation_run_portfolio'"
            )
        ).all()
        assert rows, "uq_report_generation_run_portfolio does not exist"
        assert sorted(r[0] for r in rows) == sorted(_UNIQUE_KEY_COLUMNS)
        assert all(
            r[1] for r in rows
        ), "a NULLABLE column in the key — NULLS DISTINCT makes it void"
        assert all(r[2] for r in rows), "the index is not UNIQUE"
    finally:
        session.close()


def test_one_generation_per_run_and_portfolio_but_two_portfolios_share_a_run(factory) -> None:  # noqa: ANN001
    """Both halves of the key, because asserting only the refusal would pass on a key so tight it
    forbade a legitimate multi-portfolio run."""
    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        ids = _seed_parents(session.connection(), TENANT_A)
        _insert_report(session.connection(), TENANT_A, ids)

        # A DIFFERENT portfolio in the SAME run -> legal.
        second = _seed_parents(session.connection(), TENANT_A)
        _insert_report(
            session.connection(),
            TENANT_A,
            dict(ids, portfolio=second["portfolio"]),
            p=second["portfolio"],
        )
        session.commit()

        set_tenant_context(session, TENANT_A)
        with pytest.raises(Exception, match="uq_report_generation_run_portfolio"):
            _insert_report(session.connection(), TENANT_A, ids)
            session.flush()
        session.rollback()
    finally:
        session.close()


def test_the_database_does_not_fence_a_cross_tenant_binding_the_service_does(factory) -> None:  # noqa: ANN001
    """DISCOVERY, not assumption: where does a cross-tenant run binding actually get refused?

    PostgreSQL runs referential-integrity checks in a mode that bypasses row-level security, so an
    FK pointing at a parent this tenant cannot SELECT still resolves. That is asserted here as the
    engine's real behaviour, and the consequence is the point: **the tenant fence on this binding
    lives in the application**, in ``report.service.generate_report``, which resolves the run under
    the caller's tenant context before binding it. ``test_report_generation.py`` proves that
    refusal fires.

    If this test ever fails because the insert was refused, that is GOOD NEWS and a real change:
    the database has gained a fence it did not have. Re-express it then — do not delete it.
    """
    setup = factory()
    try:
        set_tenant_context(setup, TENANT_B)
        foreign = _seed_parents(setup.connection(), TENANT_B)
        setup.commit()
    finally:
        setup.close()

    session = factory()
    try:
        set_tenant_context(session, TENANT_A)
        mine = _seed_parents(session.connection(), TENANT_A)
        # A row OWNED by tenant A (so the RLS WITH CHECK passes) but BOUND to tenant B's run.
        _insert_report(
            session.connection(),
            TENANT_A,
            dict(mine, run=foreign["run"]),
            r=foreign["run"],
        )
        session.commit()

        set_tenant_context(session, TENANT_A)
        bound = session.execute(
            text("SELECT count(*) FROM report_generation WHERE calculation_run_id = :r"),
            {"r": foreign["run"]},
        ).scalar_one()
        assert bound == 1, (
            "the FK refused a cross-tenant parent — the database now fences this; "
            "re-express this test and re-rank the service-layer refusal as defence in depth"
        )
    finally:
        session.close()
