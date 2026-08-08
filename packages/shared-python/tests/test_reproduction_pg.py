"""ENT-073 ``reproduction_check`` on the AUTHORITATIVE engine (REPRO-1).

The properties SQLite structurally cannot test: symmetric FORCE RLS, the P0001 append-only trigger,
and whether the single UNIQUE key is VACUOUS.

**Why the unique key gets its own catalog assertion.** ``uq_reproduction_check_sweep_subject`` is
what stands between "one verdict per (sweep, subject)" and one sweep durably recording two
different conclusions about the same run. On PostgreSQL a UNIQUE index is NULLS DISTINCT by
default, so a nullable column inside the key makes the key unenforceable for exactly the rows that
matter — the defect CON-1 shipped and CAL-1b re-found. Comparing migration text to ORM text cannot
catch it, because both can declare ``nullable=False`` and still lose it to a later ALTER. So the
assertion asks the LIVE database, via ``pg_attribute``, whether every key column is ``attnotnull``.

**The RLS assertions run as ``irp_app``, never as the default superuser.** FORCE RLS does not apply
to a BYPASSRLS role, so a cross-tenant test run as the superuser proves nothing about isolation —
the LQ-1 lesson, and REF-1's before it.

**And the engine-behaviour half, added after a BLOCKING defect survived three scrutiny stages.**
Everything above is about the SCHEMA. The defect was about the ENGINE: PostgreSQL aborts the whole
transaction when a statement fails, SQLite does not, so a guard that catches a DBAPI error and
carries on is correct on the unit tier and inert on the authoritative one. The sweep built a correct
verdict and then died on the next statement, losing the night. Three stages of review read that code
and its unit test was green throughout — because the unit test raised a plain ``RuntimeError``, and
the difference between the two tiers is exactly the difference the test could not express. The last
two tests in this file are that missing coverage, and one of them asserts the mechanism itself so
the reason for the shape survives the next edit.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.reproduction.registry import ComparableRow, ReproducibleFamily
from irp_shared.reproduction.service import (
    ReproductionInfrastructureFailure,
    check_one_family,
    resolve_subject,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

TENANT_A = "aaaaaaaa-7373-4a4a-8b8b-cccccccccccc"
TENANT_B = "bbbbbbbb-7373-4a4a-8b8b-cccccccccccc"

#: The columns of the single UNIQUE key. Named here so the non-vacuity assertion cannot drift into
#: agreeing with whatever the index happens to contain.
_UNIQUE_KEY_COLUMNS = ("calculation_run_id", "subject_run_id")


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
        for table in ("reproduction_check", "calculation_run"):
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


def _seed_runs(conn, tenant: str) -> tuple[str, str]:
    """A real REPRODUCTION sweep run and a real subject run — both genuine rows, because
    ``reproduction_check`` carries a hard FK to each and fake ids would fail the insert for the
    wrong reason and turn a green isolation test into an accident."""
    sweep, subject = str(uuid.uuid4()), str(uuid.uuid4())
    for run_id, run_type in ((sweep, "REPRODUCTION"), (subject, "VAR")):
        conn.execute(
            text(
                "INSERT INTO calculation_run (run_id, id, tenant_id, system_from, run_type,"
                " status, initiated_by, code_version, environment_id, created_at)"
                " VALUES (:id, :id, :t, now(), :rt, 'COMPLETED', 'seed', 'v', 'test', now())"
            ),
            {"id": run_id, "t": tenant, "rt": run_type},
        )
    return sweep, subject


def _insert_check(conn, tenant: str, sweep: str, subject: str, **over: object) -> str:
    row_id = str(uuid.uuid4())
    params: dict[str, object] = {
        "i": row_id,
        "t": tenant,
        "c": sweep,
        "s": subject,
        "f": "VAR",
        "v": "MATCH",
        **over,
    }
    conn.execute(
        text(
            "INSERT INTO reproduction_check (id, tenant_id, system_from, calculation_run_id,"
            " subject_run_id, family_key, verdict, rows_compared, rows_diverged) VALUES"
            " (:i, :t, now(), :c, :s, :f, :v, 1, 0)"
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
                "WHERE c.relname = 'reproduction_check'"
            )
        ).one()
        assert row[0] is True, "RLS not enabled"
        assert row[1] is True, "RLS not FORCED (the owner would bypass it)"
        assert row[2] is True, "USING != WITH CHECK — the policy is not symmetric"
    finally:
        session.close()


def test_a_tenant_cannot_read_another_tenants_verdict(factory) -> None:  # noqa: ANN001
    session = factory()
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        sweep, subject = _seed_runs(session.connection(), TENANT_A)
        row_id = _insert_check(session.connection(), TENANT_A, sweep, subject)
        session.commit()

        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_B})
        seen = session.execute(
            text("SELECT count(*) FROM reproduction_check WHERE id = :i"), {"i": row_id}
        ).scalar_one()
        assert seen == 0, "a verdict leaked across the tenant boundary"

        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        assert (
            session.execute(
                text("SELECT count(*) FROM reproduction_check WHERE id = :i"), {"i": row_id}
            ).scalar_one()
            == 1
        ), "the owning tenant cannot see its own verdict — the fence is not a fence, it is a wall"
    finally:
        session.rollback()
        session.close()


def test_the_append_only_trigger_refuses_UPDATE_and_DELETE(factory) -> None:  # noqa: ANN001
    """The DATABASE refuses, not merely the ORM. Proven with raw SQL so the ORM listeners are out
    of the picture entirely — a verdict edited after the fact would not be evidence."""
    session = factory()
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        sweep, subject = _seed_runs(session.connection(), TENANT_A)
        row_id = _insert_check(session.connection(), TENANT_A, sweep, subject)
        session.commit()

        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        with pytest.raises(DBAPIError):
            session.execute(
                text("UPDATE reproduction_check SET verdict = 'DIVERGED' WHERE id = :i"),
                {"i": row_id},
            )
        session.rollback()

        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        with pytest.raises(DBAPIError):
            session.execute(text("DELETE FROM reproduction_check WHERE id = :i"), {"i": row_id})
        session.rollback()
    finally:
        session.close()


def test_the_unique_key_is_not_vacuous(factory) -> None:  # noqa: ANN001
    """Every column of the UNIQUE key must be NOT NULL in the LIVE catalog.

    A nullable column inside a PostgreSQL UNIQUE index is NULLS DISTINCT, so the key silently stops
    constraining exactly the rows a nullable column would produce. This asks the database rather
    than comparing two pieces of text that can both be right and still lose it to a later ALTER.
    """
    session = factory()
    try:
        for column in _UNIQUE_KEY_COLUMNS:
            notnull = session.execute(
                text(
                    "SELECT a.attnotnull FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
                    " WHERE c.relname = 'reproduction_check' AND a.attname = :col"
                ),
                {"col": column},
            ).scalar_one()
            assert notnull is True, f"{column} is nullable — the unique key is VACUOUS for it"
    finally:
        session.close()


def test_one_sweep_cannot_record_two_verdicts_about_the_same_run(factory) -> None:  # noqa: ANN001
    """The unique key, exercised rather than merely declared."""
    session = factory()
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        sweep, subject = _seed_runs(session.connection(), TENANT_A)
        _insert_check(session.connection(), TENANT_A, sweep, subject)
        with pytest.raises(IntegrityError):
            _insert_check(session.connection(), TENANT_A, sweep, subject, v="DIVERGED")
        session.rollback()
    finally:
        session.close()


def _exploding_family(statement: str) -> ReproducibleFamily:
    """A family whose stored-read runs SQL that really fails on the real engine."""

    def _bad_read(db: Session, _tenant: str, _subject: CalculationRun) -> list[ComparableRow]:
        db.execute(text(statement))
        raise AssertionError("the statement should have raised")

    def _unused(*_a: object, **_k: object) -> list[ComparableRow]:
        raise AssertionError("the recompute must never be reached")

    return ReproducibleFamily(
        family_key="VAR",
        key_fields=("k",),
        compared_fields=("v",),
        read_stored=_bad_read,
        recompute=_unused,
        model=None,
        uncompared={},
    )


def test_a_database_failure_in_a_family_read_leaves_the_SESSION_USABLE(factory) -> None:  # noqa: ANN001
    """The BLOCKING defect, pinned on the only tier that can see it.

    ``check_one_family`` catches a failing per-family read. On SQLite that is the end of the story.
    On PostgreSQL the backend transaction is ABORTED by the failed statement, and a bare
    ``try/except`` — which is what shipped for one commit — leaves it that way: the caught error
    produced a correct verdict and the sweep then died on its next statement with
    ``InFailedSqlTransaction``, discarding every other family's verdict. Measured on this engine
    before the fix: zero verdict rows persisted.

    The discriminating assertion is the LAST one. Catching is not recovering; the savepoint is what
    recovers, because ROLLBACK TO SAVEPOINT clears the aborted state.

    It also pins the redaction, which is PostgreSQL-only for the same reason: psycopg quotes the
    failing statement under a ``LINE n:`` caret that the other markers do not cover, and a real
    statement reached this governed evidence column before ``_redact`` learned about it.
    """
    session = factory()
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        subject = CalculationRun(
            run_id=str(uuid.uuid4()),
            tenant_id=TENANT_A,
            run_type="VAR",
            status="COMPLETED",
            initiated_by="test",
            code_version="v",
            environment_id="test",
        )
        with pytest.raises(ReproductionInfrastructureFailure) as caught:
            check_one_family(
                session,
                acting_tenant=TENANT_A,
                family=_exploding_family("SELECT * FROM a_table_that_does_not_exist"),
                subject=subject,
                code_version="v",
            )
        reason = str(caught.value)
        assert "a_table_that_does_not_exist" in reason, "the reason lost the useful part"
        assert "SELECT *" not in reason, (
            "the failing STATEMENT reached an operator-facing reason that will be persisted into a "
            "governed column — _redact does not cover psycopg's LINE n: caret"
        )
        assert (
            session.execute(text("SELECT 1")).scalar_one() == 1
        ), "the session is still poisoned after the guard — catching is not recovering"
    finally:
        session.rollback()
        session.close()


def test_a_database_failure_in_the_SUBJECT_LOOKUP_leaves_the_session_usable(  # noqa: ANN001
    factory, monkeypatch
) -> None:
    """The sibling guard, on the tier that can see it — and it SURVIVED its first mutation.

    Deleting this savepoint left the whole battery green, because the only test that reached the
    guard raised a hand-constructed ``OperationalError``: a Python object, never a failing
    statement, so no transaction was ever aborted. That is the same defect the guard exists to
    prevent, dressed as its proof.

    Here the lookup fails the way a lookup actually fails — a real statement against a real engine.
    The last assertion is the one that discriminates: without the savepoint, the sweep's fail-closed
    ``UPDATE calculation_run SET status='FAILED'`` cannot run either, so the night ends with no
    ledger row and no reason at all.
    """
    session = factory()
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})

        def _bad_lookup(db: Session, **_k: object) -> None:
            db.execute(text("SELECT * FROM another_table_that_does_not_exist"))
            raise AssertionError("the statement should have raised")

        monkeypatch.setattr("irp_shared.reproduction.service.latest_completed_run", _bad_lookup)
        subject, failure = resolve_subject(session, acting_tenant=TENANT_A, run_type="VAR")
        assert subject is None
        assert failure is not None and "another_table_that_does_not_exist" in failure
        assert "SELECT *" not in failure, "the failing statement reached an operator-facing reason"
        assert (
            session.execute(text("SELECT 1")).scalar_one() == 1
        ), "the session is still poisoned — the sweep's own fail-closed write would die next"
    finally:
        session.rollback()
        session.close()


def test_the_negative_control_a_bare_catch_really_does_leave_it_poisoned(factory) -> None:  # noqa: ANN001
    """Prove the mechanism, so the reason for the savepoint survives the next edit.

    Without this arm the test above passes for a shape that never needed a savepoint, and a later
    maintainer looking at a plain ``try/except`` has no evidence it was ever wrong. Here the same
    failing statement is caught WITHOUT a savepoint and the session is demonstrably unusable —
    which is precisely what shipped, and precisely what SQLite cannot show.
    """
    session = factory()
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        try:
            session.execute(text("SELECT * FROM a_table_that_does_not_exist"))
        except DBAPIError:
            pass
        with pytest.raises(DBAPIError):
            session.execute(text("SELECT 1"))

        session.rollback()
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": TENANT_A})
        try:
            with session.begin_nested():
                session.execute(text("SELECT * FROM a_table_that_does_not_exist"))
        except DBAPIError:
            pass
        assert (
            session.execute(text("SELECT 1")).scalar_one() == 1
        ), "the savepoint form did not recover either — the fix does not work"
    finally:
        session.rollback()
        session.close()
