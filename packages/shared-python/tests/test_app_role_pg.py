"""DEPLOY-1: the application role's properties, asserted against a real PostgreSQL.

**Why this file exists.** The platform's first hard invariant is "no BYPASSRLS application path",
and until 2026-08-11 it was true of a role that existed only inside the test suite. Sixty-one test
files created ``irp_app`` themselves, proved RLS held for it, and dropped away; the deployed
services connected as ``${POSTGRES_USER}`` — a superuser, by the ``postgres:16`` image's own
behaviour — so every deployed proof ran with tenant isolation switched off.

The distinction this file draws, and the reason both halves are here: **the isolation tests were
never wrong.** They proved a true thing about a role nothing deployed used. So asserting "RLS works
for ``irp_app``" once more would add nothing. What was missing is an assertion that the role a
DEPLOYMENT gets is that role — i.e. that a migration, not a fixture, delivers it.

Both halves run:

* the POSITIVE half asserts the migration-delivered role has the two properties the invariant names;
* the NEGATIVE half asserts the superuser DOES read across tenants — which is not a bug to fix but
  the state being escaped, and pinning it is what stops someone "simplifying" the deploy back to
  the owner role on the grounds that everything still passes.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

APP_ROLE = "irp_app"


def _seed_two_tenants(conn) -> tuple[str, str]:  # noqa: ANN001
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(UTC)
    for tid, code in ((a, f"probe-a-{a[:8]}"), (b, f"probe-b-{b[:8]}")):
        conn.execute(
            text(
                "INSERT INTO tenant (id, code, display_name, status, provenance, created_at, "
                "updated_at) VALUES (:id, :code, 'Probe', 'ACTIVE', 'BACKFILLED', :n, :n)"
            ),
            {"id": tid, "code": code, "n": now},
        )
        conn.execute(
            text(
                "INSERT INTO app_user (id, tenant_id, external_subject, display_name, is_active, "
                "created_at, updated_at) VALUES (:id, :t, :s, 'Probe', true, :n, :n)"
            ),
            {"id": str(uuid.uuid4()), "t": tid, "s": f"{code}@probe", "n": now},
        )
    return a, b


def _cleanup(conn, a: str, b: str) -> None:  # noqa: ANN001
    conn.execute(text("DELETE FROM app_user WHERE tenant_id IN (:a, :b)"), {"a": a, "b": b})
    conn.execute(text("DELETE FROM tenant WHERE id IN (:a, :b)"), {"a": a, "b": b})


def test_the_MIGRATION_ITSELF_declares_the_two_properties_and_the_future_grants() -> None:
    """**Added because the mutation battery killed nothing without it, and that is the finding.**

    The three state-reading tests below were written first and the battery reported **0/2 killed**:
    it mutates the migration FILE, but the database under test was already migrated, so every
    assertion read ambient state and observed the migration not at all. The first of them was named
    ``test_the_MIGRATION_delivers_…`` while testing no such thing — it would have passed with
    ``0070`` deleted, because a test fixture had created ``irp_app`` on that database months ago.
    That is the exact class this project spent Wave 17 finding, reproduced in the fix for it.

    So the DECLARATION is asserted here and the STATE below, and neither is sufficient alone:

    * this test would pass on a database where the migration never ran;
    * those tests would pass on a database whose role came from a test fixture.

    Reading the migration's text is a weak instrument, and it is used deliberately rather than
    silently: it is the same instrument P17's ``DELIVERS`` gate uses, and the alternative — applying
    the revision to a scratch database inside the test — is a real improvement that is scoped as
    its own work rather than smuggled in here. What is NOT acceptable is the state it was in
    thirty seconds ago: a suite that could not tell whether the migration said anything at all.
    """
    path = Path(__file__).resolve().parents[3] / "migrations" / "versions" / "0070_app_role.py"
    source = path.read_text(encoding="utf-8")
    # Say what must NOT be there, not merely what must. The first version of this assertion was
    # `"NOSUPERUSER NOBYPASSRLS" in source`, and mutant X-A1 walked straight through it: it flips
    # the ALTER ROLE line to `BYPASSRLS` while the CREATE ROLE line still contains the negated
    # spelling, so the substring is present and the assertion passes. A presence check cannot see
    # a second occurrence that says the opposite — the same shape as RPT-3's subset assertion, and
    # it took the battery to find it here too.
    # Scoped to the SQL-bearing lines, and the reason is its own small lesson: the first form
    # scanned the WHOLE file for an un-negated `BYPASSRLS` and went red on the unmutated
    # migration — because the docstring says "no BYPASSRLS application path" in prose. A guard
    # that reads documentation as if it were code is a guard that will be silenced rather than
    # fixed, which is how these end up inert.
    role_stmts = [
        line
        for line in source.splitlines()
        if "BYPASSRLS" in line and re.search(r"\b(CREATE|ALTER)\s+ROLE\b", line)
    ]
    assert role_stmts, "migration 0070 no longer constrains the role in any CREATE/ALTER statement"
    offenders = [line.strip() for line in role_stmts if "NOBYPASSRLS" not in line]
    assert not offenders, (
        f"migration 0070 grants BYPASSRLS: {offenders}. The platform's first hard invariant is "
        f"'no BYPASSRLS application path', and this is the migration that exists to guarantee it "
        f"— every one of the 84 FORCE-RLS tables stops constraining the application."
    )
    assert source.count("NOBYPASSRLS") >= 2, (
        "both the CREATE ROLE branch and the re-asserting ALTER ROLE must constrain the role: the "
        "CREATE branch is skipped entirely on a database where a test fixture already made one"
    )
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public " in source and "ON TABLES TO" in source, (
        "migration 0070 no longer grants default privileges on FUTURE tables — the application "
        "breaks on the next slice that adds one, in production rather than in CI"
    )


def test_the_MIGRATED_database_has_an_app_role_that_cannot_bypass_RLS() -> None:
    """The state half. Note what it asserts: the role exists ON A MIGRATED DATABASE.

    Every other RLS test in this suite CREATES ``irp_app`` in its own fixture, which is why the
    deployment's missing role was invisible for the platform's whole life. This one creates
    nothing — on CI's freshly-migrated database, only migration ``0070`` can have delivered it.
    """
    engine = make_engine(URL, poolclass=NullPool)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"),
            {"r": APP_ROLE},
        ).first()
    assert row is not None, (
        f"{APP_ROLE} does not exist on a migrated database. It was created only by test fixtures "
        f"until migration 0070; if this fails, the deployment has no application role again."
    )
    rolsuper, rolbypassrls = row
    assert rolsuper is False, f"{APP_ROLE} is a SUPERUSER — RLS does not apply to it at all"
    assert rolbypassrls is False, f"{APP_ROLE} holds BYPASSRLS — the invariant's exact negation"


def test_the_app_role_sees_NOTHING_across_tenants_and_the_owner_sees_EVERYTHING() -> None:
    """Both halves in one place, because the contrast IS the finding.

    The second assertion looks like it is testing PostgreSQL rather than this platform. It is not:
    it pins the reason the deploy must not connect as the owner. Delete it and "point the services
    back at ``POSTGRES_USER``" becomes a change that breaks nothing visible.
    """
    engine = make_engine(URL, poolclass=NullPool)
    with engine.begin() as conn:
        a, b = _seed_two_tenants(conn)
        try:
            # The OWNER/superuser — what the deployment used to connect as.
            owner_visible = conn.execute(
                text("SELECT count(*) FROM app_user WHERE tenant_id IN (:a, :b)"),
                {"a": a, "b": b},
            ).scalar_one()

            # The APP role, no `app.tenant_id` GUC armed. `SET LOCAL ROLE` is scoped to this
            # transaction, so the session is not left switched.
            conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            app_visible = conn.execute(
                text("SELECT count(*) FROM app_user WHERE tenant_id IN (:a, :b)"),
                {"a": a, "b": b},
            ).scalar_one()
            conn.execute(text("RESET ROLE"))

            assert owner_visible == 2, (
                "the owner role could NOT see both tenants' rows — the fixture did not seed what "
                "this test compares against, so the assertion below would pass vacuously"
            )
            assert app_visible == 0, (
                f"{APP_ROLE} read {app_visible} row(s) across two tenants with no tenant context "
                f"armed. RLS is not constraining the application role — which is the exact state "
                f"the deployment was in until migration 0070."
            )
        finally:
            conn.execute(text("RESET ROLE"))
            _cleanup(conn, a, b)


def test_the_app_role_can_still_DO_its_job_on_a_future_table() -> None:
    """The other way this fix fails: a role so constrained the application breaks.

    Migration 0070 grants on ALL TABLES plus ``ALTER DEFAULT PRIVILEGES`` for tables a LATER
    migration creates. Without the default-privileges half the app would break on the next slice
    that adds a table, in production rather than in CI. Proven by creating a table AFTER the
    migration ran — which is what a future migration is.
    """
    engine = make_engine(URL, poolclass=NullPool)
    name = f"_probe_future_{uuid.uuid4().hex[:8]}"
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {name} (id integer primary key)"))
        try:
            conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            conn.execute(text(f"INSERT INTO {name} (id) VALUES (1)"))
            got = conn.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
            conn.execute(text("RESET ROLE"))
            assert got == 1, (
                "the app role could not write to a table created after 0070 ran — ALTER DEFAULT "
                "PRIVILEGES is not covering future migrations, and the break would surface in "
                "production rather than here"
            )
        finally:
            conn.execute(text("RESET ROLE"))
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
