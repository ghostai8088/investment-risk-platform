"""SCH-2 PG-tier: the per-family/per-cadence CHECKs + the non-superuser downgrade-body test.

Gated on ``IRP_TEST_DATABASE_URL``. Both legs are PG-ONLY by construction: this repo creates every
CHECK imperatively in migrations, so the constraints are ORM-invisible and the whole SQLite battery
is blind to them (which is exactly why ``_validate_config`` carries the same rule in both
directions — see the service).

**Why the CHECK pin is BEHAVIORAL, not textual (SCH-2 verifier M2).** ``pg_get_constraintdef()``
returns a NORMALIZED expression — casts inserted, parentheses re-associated, IN-lists rewritten to
``= ANY (ARRAY[...])`` — so comparing it to a Python-built string is either brittle across PG
versions or, written defensively (``assert "VAR" in defn``), vacuous: that substring appears in any
expression naming the family. So the pin drives the registry's own declarations through a matrix of
raw INSERTs and asserts accept/reject. The inserts are RAW on purpose: going through
``create_schedule`` would short-circuit on the service gate and prove nothing about the DB.

The matrix ships with its **executed negative control** — dropping the constraint inside a savepoint
and proving the SAME helper then fails — because a guard that has never been shown to fire is not a
guard (the standing rule).
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.scheduling.events import CADENCE_CALENDAR_RESERVED
from irp_shared.scheduling.queries import list_scheduled_runs, list_schedules
from irp_shared.scheduling.service import FAMILY_REGISTRY, MAX_INTERVAL_DAYS

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_MIG_ROLE = "irp_mig_sch2"
_MIG_PW = "irp_mig_sch2_pw"
_CHECK_FAMILY = "ck_schedule_model_version_by_family"


@pytest.fixture(scope="module")
def app_url() -> str:
    """The NON-superuser, NON-BYPASSRLS app role — the CHECK legs must hold for the role the
    application actually connects as, not for a superuser that bypasses everything."""
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
        # The referent tables are here because `_seed_referents` INSERTs into all three as
        # `irp_app` (4-finder review, schema lens): without them this file is green in CI only by
        # GRANT LEAKAGE from ~30 earlier suites in the same job, and fails when run alone against a
        # freshly migrated database. The SCH-1 sibling suite declares the same `_DEPS` set.
        # `calendar` joined at CAL-1b: `_seed_calendar_row` INSERTs the BUSINESS_MONTH_END
        # referent as `irp_app` (same declared-deps rule as the three originals).
        for table in ("schedule", "scheduled_run", "portfolio", "model", "model_version", "calendar"):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_referents(conn, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    """A real portfolio + model_version in ``tenant``.

    Both are HARD FKs on ``schedule``, and an FK violation is also an ``IntegrityError`` — so a
    matrix using random UUIDs would "reject" every row for the wrong reason and pass while proving
    nothing about the CHECK. Real referents make the CHECK the only thing that can refuse.
    """
    pf, model, mv = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO portfolio (id, tenant_id, valid_from, created_at, updated_at, code,"
            " name, node_type, status, record_version)"
            " VALUES (:id, :t, now(), now(), now(), :code, 'p', 'ACCOUNT', 'ACTIVE', 1)"
        ),
        {"id": pf, "t": tenant, "code": f"pf-{uuid.uuid4().hex[:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO model (id, tenant_id, valid_from, created_at, updated_at, record_version,"
            " code, name, model_type, is_active)"
            " VALUES (:id, :t, now(), now(), now(), 1, :code, 'm', 'RISK', true)"
        ),
        {"id": model, "t": tenant, "code": f"m-{uuid.uuid4().hex[:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO model_version (id, tenant_id, system_from, model_id, version_label)"
            " VALUES (:id, :t, now(), :model, 'v1')"
        ),
        {"id": mv, "t": tenant, "model": model},
    )
    return pf, mv


def _raw_insert_schedule(
    conn,  # noqa: ANN001
    *,
    tenant: str,
    target_run_type: str,
    model_version_id: str | None,
    portfolio_id: str,
    cadence_kind: str = "INTERVAL",
    interval_days: int | None = 7,
    calendar_id: str | None = None,
) -> None:
    """Insert a ``schedule`` row DIRECTLY — the DB is the only judge here."""
    conn.execute(
        text(
            "INSERT INTO schedule (id, tenant_id, valid_from, created_at, updated_at, code, name,"
            " target_run_type, scope_portfolio_id, model_version_id, environment_id, cadence_kind,"
            " interval_days, calendar_id, anchor_date, status, record_version)"
            " VALUES (:id, :tenant, now(), now(), now(), :code, 'n', :trt, :pf, :mv, 'ci', :ck,"
            " :iv, :cal, :anchor, 'ACTIVE', 1)"
        ),
        {
            "id": str(uuid.uuid4()),
            "tenant": tenant,
            "cal": calendar_id,
            "code": f"c-{uuid.uuid4().hex[:8]}",
            "trt": target_run_type,
            "pf": portfolio_id,
            "mv": model_version_id,
            "ck": cadence_kind,
            "iv": interval_days,
            "anchor": date(2026, 1, 1),
        },
    )


def _run_family_matrix(conn) -> None:  # noqa: ANN001
    """Drive the registry's OWN declaration through the DB, both directions, every family.

    Raises ``AssertionError`` if the DB disagrees with the registry — which is what the negative
    control below proves this helper can actually detect.
    """
    tenant = str(uuid.uuid4())
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
    portfolio_id, model_version_id = _seed_referents(conn, tenant)
    for family, spec in FAMILY_REGISTRY.items():
        for supply_mv in (True, False):
            expected_ok = supply_mv == spec.requires_model_version
            sp = conn.begin_nested()
            try:
                _raw_insert_schedule(
                    conn,
                    tenant=tenant,
                    target_run_type=family,
                    model_version_id=model_version_id if supply_mv else None,
                    portfolio_id=portfolio_id,
                )
                accepted, why = True, ""
            except IntegrityError as exc:
                accepted, why = False, str(exc.orig).splitlines()[0]
            finally:
                sp.rollback()
            assert accepted == expected_ok, (
                f"{family} with model_version={'set' if supply_mv else 'NULL'}: "
                f"DB {'accepted' if accepted else 'rejected'}, registry expects "
                f"{'accept' if expected_ok else 'reject'}{f' — {why}' if why else ''}"
            )


def test_the_family_check_agrees_with_the_registry(app_url: str) -> None:  # noqa: F811
    """THE PIN: adding a registry family whose migration was forgotten fails here, and so does
    changing a CHECK the registry does not declare."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        _run_family_matrix(conn)
        trans.rollback()
    engine.dispose()


def test_the_family_matrix_actually_observes_the_constraint() -> None:
    """THE EXECUTED NEGATIVE CONTROL: with the constraint dropped, the SAME helper must FAIL.
    Without this, a matrix that silently accepted everything would look identical to a passing pin.
    PG DDL is transactional, so the rollback restores the constraint.

    Runs as the OWNER, not ``irp_app``: the app role cannot DROP a constraint (correctly — it holds
    no DDL rights), and a CHECK is enforced for superusers too, so the control is unaffected.
    """
    engine = make_engine(URL, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text(f"ALTER TABLE schedule DROP CONSTRAINT {_CHECK_FAMILY}"))
        with pytest.raises(AssertionError):
            _run_family_matrix(conn)
        trans.rollback()
    engine.dispose()


def test_the_cadence_check_forbids_a_meaningless_interval(app_url: str) -> None:  # noqa: F811
    """A calendar grid has no interval; an INTERVAL grid must have a positive one (the ``> 0``
    rule the DB never carried before SCH-2 — it lived only in the service)."""
    engine = make_engine(app_url, poolclass=NullPool)
    tenant = str(uuid.uuid4())
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        pf, _ = _seed_referents(conn, tenant)
        for cadence, interval in (("CALENDAR_MONTH_END", 7), ("INTERVAL", 0)):
            sp = conn.begin_nested()
            with pytest.raises(IntegrityError):
                _raw_insert_schedule(
                    conn,
                    tenant=tenant,
                    target_run_type="EXPOSURE_AGGREGATE",
                    model_version_id=None,
                    portfolio_id=pf,
                    cadence_kind=cadence,
                    interval_days=interval,
                )
            sp.rollback()
        trans.rollback()
    engine.dispose()


def test_an_unenumerated_family_is_refused_by_the_check(app_url: str) -> None:  # noqa: F811
    """The CHECK is a TOTAL ENUMERATION, not an implication. The implication form
    ``(trt <> 'VAR' OR mv IS NOT NULL) AND (trt <> 'EXPOSURE_AGGREGATE' OR mv IS NULL)`` FAILS OPEN
    for a family nobody enumerated — it would admit a future family with either value. The total
    form refuses it, so admitting family 3 REQUIRES a migration (deliberate: the DB becomes a
    genuine third gate that agrees with the registry by construction)."""
    engine = make_engine(app_url, poolclass=NullPool)
    tenant = str(uuid.uuid4())
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        pf, mv_id = _seed_referents(conn, tenant)
        for mv in (mv_id, None):
            sp = conn.begin_nested()
            with pytest.raises(IntegrityError):
                _raw_insert_schedule(
                    conn,
                    tenant=tenant,
                    target_run_type="ACTIVE_RISK",
                    model_version_id=mv,
                    portfolio_id=pf,
                )
            sp.rollback()
        trans.rollback()
    engine.dispose()


def test_downgrade_body_under_nonsuperuser_owner_member_role(app_url: str) -> None:  # noqa: F811
    """The 0041/0042 owner-via-membership mechanics against 0053's TWO-TABLE cascade.

    Three things this proves that the CI ``alembic downgrade base`` smoke could not (SCH-2 verifier
    B2/B3): the child FK is ``NO ACTION`` so ``scheduled_run`` rows must go FIRST; those children
    carry BOTH the P0001 append-only trigger AND FORCE RLS, so the sandwich needs the trigger leg
    the draft record wrongly said was unnecessary; and the zero-row trap is live — an unsandwiched
    DELETE under FORCE RLS silently matches nothing even as the owner.
    """
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())

    # Seed an UNREPRESENTABLE schedule (model-less) + an append-only child, COMMITTED — this is
    # what the CI downgrade smoke never had (no demo stage created a schedule before SCH-2).
    session = factory()
    schedule_id = str(uuid.uuid4())
    try:
        session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, _ = _seed_referents(session, tenant)
        session.execute(
            text(
                "INSERT INTO schedule (id, tenant_id, valid_from, created_at, updated_at, code,"
                " name, target_run_type, scope_portfolio_id, model_version_id, environment_id,"
                " cadence_kind, interval_days, anchor_date, status, record_version)"
                " VALUES (:id, :t, now(), now(), now(), :code, 'n', 'EXPOSURE_AGGREGATE', :pf,"
                " NULL, 'ci', 'CALENDAR_MONTH_END', NULL, :anchor, 'ACTIVE', 1)"
            ),
            {
                "id": schedule_id,
                "t": tenant,
                "code": f"dg-{uuid.uuid4().hex[:8]}",
                "pf": portfolio_id,
                "anchor": date(2026, 1, 1),
            },
        )
        session.execute(
            text(
                "INSERT INTO scheduled_run (id, tenant_id, system_from, schedule_id,"
                " scheduled_for, fired_at, calculation_run_id, outcome)"
                " VALUES (:id, :t, now(), :sid, now(), now(), NULL, 'FAILED')"
            ),
            {"id": str(uuid.uuid4()), "t": tenant, "sid": schedule_id},
        )
        session.commit()
    finally:
        session.close()

    su = create_engine(URL, poolclass=NullPool)
    with su.connect() as c:
        owner_role = c.execute(
            text("SELECT tableowner FROM pg_tables WHERE tablename='schedule'")
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
        / "0053_schedule_cadence_family.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0053_schedule_cadence", mig_path)
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from irp_shared.models import metadata as target_metadata

    with mig_engine.connect() as conn:
        # (a) The RECORDED trap, live: an UNSANDWICHED delete under FORCE RLS matches ZERO rows
        #     even as the table owner.
        trans = conn.begin()
        gone = conn.execute(text("DELETE FROM schedule WHERE model_version_id IS NULL")).rowcount
        assert gone == 0  # the row EXISTS (committed above) — FORCE RLS hid it
        trans.rollback()

        # (b) The real downgrade body: children first, trigger + RLS sandwiched, then re-tighten.
        trans = conn.begin()
        ctx = MigrationContext.configure(conn, opts={"target_metadata": target_metadata})
        with Operations.context(ctx):
            mig.downgrade()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        remaining_children = conn.execute(
            text("SELECT count(*) FROM scheduled_run WHERE schedule_id = :sid"),
            {"sid": schedule_id},
        ).scalar_one()
        remaining_schedules = conn.execute(
            text("SELECT count(*) FROM schedule WHERE id = :sid"), {"sid": schedule_id}
        ).scalar_one()
        assert remaining_children == 0  # the FK cascade was handled child-first
        assert remaining_schedules == 0  # ...and the unrepresentable parent is gone

        # (c) THE RE-TIGHTEN, asserted (4-finder review, schema lens). Clearing the rows was the
        #     only thing checked before, so deleting the sandwich's CLOSING legs left this test
        #     green — and CI's `downgrade base` smoke is equally blind, because 0049 then DROPS
        #     both tables and erases the evidence. The realistic production rollback is 0053 -> 0052
        #     and STOP, which would leave `scheduled_run` MUTABLE (its append-only trigger off) and
        #     both tables readable ACROSS TENANTS (RLS off) — an IA + isolation breach that no
        #     other gate would catch.
        for table in ("schedule", "scheduled_run"):
            rls_on, force_on = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE oid = to_regclass(:t)"
                ),
                {"t": table},
            ).one()
            assert rls_on is True, f"{table}: RLS left DISABLED by the downgrade"
            assert force_on is True, f"{table}: FORCE RLS left off by the downgrade"
        trigger_state = conn.execute(
            text(
                "SELECT tgenabled FROM pg_trigger WHERE tgname = 'scheduled_run_append_only'"
                " AND tgrelid = to_regclass('scheduled_run')"
            )
        ).scalar_one()
        # 'O' = enabled for ORIGIN (what 0049 created); 'D' = disabled.
        assert trigger_state == "O", f"append-only trigger left in state {trigger_state!r}"
        trans.rollback()  # PG DDL is transactional — the relaxed state is restored

    mig_engine.dispose()
    su.dispose()
    engine.dispose()


def test_an_unenumerated_cadence_is_refused_by_the_vocab_check(app_url: str) -> None:  # noqa: F811
    """The THIRD CHECK shipped with no test at all (4-finder review, claims lens).

    ``ck_schedule_cadence_kind_vocab`` exists so an unresolvable ``cadence_kind`` cannot reach the
    poll loop in the first place — the DB half of the defence whose service half is
    ``current_tick``'s fail-closed branch. It is migration-only, so no other tier can see it: a
    typo'd or dropped constraint was invisible to the entire battery.

    ``CADENCE_CALENDAR_RESERVED`` is the sharpest probe available — it is a real constant in the
    vocabulary module, deliberately RESERVED-and-unimplemented (OD-SCH-1-F), so a CHECK written
    against the reserved name instead of the shipped one would pass a lazier test.
    """
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenant = str(uuid.uuid4())
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, model_version_id = _seed_referents(conn, tenant)
        for bad in (CADENCE_CALENDAR_RESERVED, "MONTHLY", "interval", ""):
            with pytest.raises(IntegrityError) as caught:
                _raw_insert_schedule(
                    conn,
                    tenant=tenant,
                    target_run_type="VAR",
                    model_version_id=model_version_id,
                    portfolio_id=portfolio_id,
                    cadence_kind=bad,
                )
            assert "ck_schedule_cadence_kind_vocab" in str(
                caught.value.orig
            ), f"cadence_kind={bad!r} was refused by the WRONG constraint"
            conn.rollback()
            trans = conn.begin()
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
            portfolio_id, model_version_id = _seed_referents(conn, tenant)
        trans.rollback()
    engine.dispose()


def test_the_runaway_interval_envelope_is_enforced_by_the_db_too(app_url: str) -> None:  # noqa: F811
    """The DB layer of ``MAX_INTERVAL_DAYS``. The service refuses it at create, but the ceiling
    exists for the row written by something OTHER than ``create_schedule`` — which is precisely the
    row that would then kill the tenant's whole tick cycle on every poll."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenant = str(uuid.uuid4())
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, model_version_id = _seed_referents(conn, tenant)
        with pytest.raises(IntegrityError) as caught:
            _raw_insert_schedule(
                conn,
                tenant=tenant,
                target_run_type="VAR",
                model_version_id=model_version_id,
                portfolio_id=portfolio_id,
                interval_days=MAX_INTERVAL_DAYS + 1,
            )
        assert "ck_schedule_interval_days_by_cadence" in str(caught.value.orig)
        trans.rollback()
    engine.dispose()


# ---------------------------------------------------- the OQ-SCH-2-7c read surface, under RLS ---
def _raw_insert_scheduled_run(
    conn,  # noqa: ANN001
    *,
    tenant: str,
    schedule_id: str,
    tick: datetime,
    outcome: str,
) -> None:
    conn.execute(
        text(
            "INSERT INTO scheduled_run (id, tenant_id, system_from, schedule_id, scheduled_for,"
            " fired_at, calculation_run_id, outcome)"
            " VALUES (:id, :tenant, now(), :sched, :tick, now(), NULL, :outcome)"
        ),
        {
            "id": str(uuid.uuid4()),
            "tenant": tenant,
            "sched": schedule_id,
            "tick": tick,
            "outcome": outcome,
        },
    )


def _seed_two_tenant_schedules(conn) -> tuple[str, str]:  # noqa: ANN001
    """One month-end EXPOSURE schedule with a FAILED fire in EACH of two tenants.

    The GUC is re-armed per tenant: the app role is NON-BYPASSRLS, so the WRITE policy refuses an
    insert whose ``tenant_id`` does not match ``app.current_tenant``. (Which is itself a small
    proof that the role under test really is subject to RLS.)
    """
    tenants = (str(uuid.uuid4()), str(uuid.uuid4()))
    for tenant in tenants:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        pf, _mv = _seed_referents(conn, tenant)
        sched = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO schedule (id, tenant_id, valid_from, created_at, updated_at, code,"
                " name, target_run_type, scope_portfolio_id, model_version_id, environment_id,"
                " cadence_kind, interval_days, anchor_date, status, record_version)"
                " VALUES (:id, :t, now(), now(), now(), :code, 'n', 'EXPOSURE_AGGREGATE', :pf,"
                " NULL, 'ci', 'CALENDAR_MONTH_END', NULL, :anchor, 'ACTIVE', 1)"
            ),
            {
                "id": sched,
                "t": tenant,
                "code": f"c-{uuid.uuid4().hex[:8]}",
                "pf": pf,
                "anchor": date(2026, 1, 1),
            },
        )
        _raw_insert_scheduled_run(
            conn,
            tenant=tenant,
            schedule_id=sched,
            tick=datetime(2026, 5, 29, 23, 59, 59, 999999, tzinfo=UTC),
            outcome="FAILED",
        )
    return tenants


def test_the_schedule_reads_are_rls_scoped_under_the_app_role(app_url: str) -> None:  # noqa: F811
    """The OQ-SCH-2-7c operator surface, proven at the tier that can prove it.

    The endpoint tests run on SQLite, where RLS is a no-op — so they can only show the explicit
    ``tenant_id`` predicate refusing. Here BOTH layers are live and each is checked ALONE:

    1. GUC = A, ``acting_tenant`` = A → sees exactly A's rows (the normal path).
    2. GUC = A, ``acting_tenant`` = B → EMPTY. RLS alone already hides B, so a caller who
       mis-passes an ``acting_tenant`` cannot read across the boundary.
    3. GUC = B, ``acting_tenant`` = A → EMPTY. The explicit predicate alone already refuses, so a
       session whose GUC was armed for the wrong tenant cannot leak A's rows either.

    (2) and (3) are the belt and the suspenders tested SEPARATELY — a test that only ever ran with
    both agreeing would pass with either one deleted.
    """
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        conn = session.connection()
        tenant_a, tenant_b = _seed_two_tenant_schedules(conn)

        persistent_tenant_context(session, tenant_a)
        mine = list_schedules(session, acting_tenant=tenant_a)
        assert len(mine) == 1
        assert mine[0].schedule.tenant_id == tenant_a
        # The head's last-fire join must not reach across the boundary either.
        assert mine[0].last_outcome == "FAILED"
        assert len(list_scheduled_runs(session, acting_tenant=tenant_a)) == 1
        assert len(list_scheduled_runs(session, acting_tenant=tenant_a, outcome="FAILED")) == 1

        # (2) RLS alone refuses: the GUC is still A's.
        assert list_schedules(session, acting_tenant=tenant_b) == []
        assert list_scheduled_runs(session, acting_tenant=tenant_b) == []

        # (3) The explicit predicate alone refuses: arm the GUC for B, ask for A.
        persistent_tenant_context(session, tenant_b)
        assert list_schedules(session, acting_tenant=tenant_a) == []
        assert list_scheduled_runs(session, acting_tenant=tenant_a) == []
        # ...and B's own session still reads B, so the emptiness above is scoping, not a dead query.
        assert len(list_schedules(session, acting_tenant=tenant_b)) == 1
    finally:
        session.rollback()
        session.close()
        engine.dispose()


# --- CAL-1b: the BUSINESS_MONTH_END DDL matrix (migration 0059) -----------------------------------


def _seed_calendar_row(conn, tenant: str) -> str:  # noqa: ANN001
    cal = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO calendar (id, tenant_id, valid_from, created_at, updated_at, code, name,"
            " is_active, record_version, holidays_complete_through)"
            " VALUES (:id, :t, now(), now(), now(), :code, 'n', true, 1, '2035-12-31')"
        ),
        {"id": cal, "t": tenant, "code": f"K{uuid.uuid4().hex[:6].upper()}"},
    )
    return cal


def test_business_month_end_ddl_matrix(app_url: str) -> None:
    """The 0059 total enumerations, asked of the DATABASE (the CON-1 lesson): the widened vocab
    ADMITS the new kind; the kind-gated calendar CHECK refuses BOTH directions BY NAME; the
    widened interval CHECK's business arm refuses an interval."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        conn.begin()
        tenant = str(uuid.uuid4())
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, _mv = _seed_referents(conn, tenant)
        calendar_id = _seed_calendar_row(conn, tenant)

        # POSITIVE: a BUSINESS_MONTH_END row with a calendar and no interval INSERTS.
        _raw_insert_schedule(
            conn,
            tenant=tenant,
            target_run_type="EXPOSURE_AGGREGATE",
            model_version_id=None,
            portfolio_id=portfolio_id,
            cadence_kind="BUSINESS_MONTH_END",
            interval_days=None,
            calendar_id=calendar_id,
        )

        # NEGATIVE 1: the new kind WITHOUT a calendar — refused by the kind-gated CHECK BY NAME.
        with pytest.raises(IntegrityError) as caught:
            _raw_insert_schedule(
                conn,
                tenant=tenant,
                target_run_type="EXPOSURE_AGGREGATE",
                model_version_id=None,
                portfolio_id=portfolio_id,
                cadence_kind="BUSINESS_MONTH_END",
                interval_days=None,
            )
        assert "ck_schedule_calendar_id_by_cadence" in str(caught.value.orig)
        conn.rollback()
        conn.begin()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, _mv = _seed_referents(conn, tenant)
        calendar_id = _seed_calendar_row(conn, tenant)

        # NEGATIVE 2: a LEGACY kind WITH a calendar — the other direction of the enumeration.
        with pytest.raises(IntegrityError) as caught:
            _raw_insert_schedule(
                conn,
                tenant=tenant,
                target_run_type="EXPOSURE_AGGREGATE",
                model_version_id=None,
                portfolio_id=portfolio_id,
                cadence_kind="CALENDAR_MONTH_END",
                interval_days=None,
                calendar_id=calendar_id,
            )
        assert "ck_schedule_calendar_id_by_cadence" in str(caught.value.orig)
        conn.rollback()
        conn.begin()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, _mv = _seed_referents(conn, tenant)
        calendar_id = _seed_calendar_row(conn, tenant)

        # NEGATIVE 3: the new kind with an interval — the widened interval CHECK's business arm.
        with pytest.raises(IntegrityError) as caught:
            _raw_insert_schedule(
                conn,
                tenant=tenant,
                target_run_type="EXPOSURE_AGGREGATE",
                model_version_id=None,
                portfolio_id=portfolio_id,
                cadence_kind="BUSINESS_MONTH_END",
                interval_days=7,
                calendar_id=calendar_id,
            )
        assert "ck_schedule_interval_days_by_cadence" in str(caught.value.orig)
        conn.rollback()
    engine.dispose()


def test_the_period_partial_unique_collides_by_name(app_url: str) -> None:
    """OQ-CAL-1-5's DB backstop: two rows for one (schedule, period) collide on
    uq_scheduled_run_schedule_period even at DIFFERENT instants — the exact race the instant uq
    cannot close; NULL period_keys (legacy kinds) never collide."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        conn.begin()
        tenant = str(uuid.uuid4())
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, _mv = _seed_referents(conn, tenant)
        calendar_id = _seed_calendar_row(conn, tenant)
        sched = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO schedule (id, tenant_id, valid_from, created_at, updated_at, code,"
                " name, target_run_type, scope_portfolio_id, environment_id, cadence_kind,"
                " calendar_id, anchor_date, status, record_version)"
                " VALUES (:id, :t, now(), now(), now(), :code, 'n', 'EXPOSURE_AGGREGATE', :pf,"
                " 'ci', 'BUSINESS_MONTH_END', :cal, '2027-01-01', 'ACTIVE', 1)"
            ),
            {
                "id": sched,
                "t": tenant,
                "code": f"c-{uuid.uuid4().hex[:8]}",
                "pf": portfolio_id,
                "cal": calendar_id,
            },
        )

        def _insert_run(instant: str, period: str | None) -> None:
            conn.execute(
                text(
                    "INSERT INTO scheduled_run (id, tenant_id, system_from, schedule_id,"
                    " scheduled_for, period_key, fired_at, outcome)"
                    " VALUES (:id, :t, now(), :s, :sf, :pk, now(), 'DISPATCHED')"
                ),
                {"id": str(uuid.uuid4()), "t": tenant, "s": sched, "sf": instant, "pk": period},
            )

        _insert_run("2027-05-31 23:59:59.999999+00", "2027-05")
        with pytest.raises(IntegrityError) as caught:
            _insert_run("2027-05-28 23:59:59.999999+00", "2027-05")  # a DIFFERENT instant
        assert "uq_scheduled_run_schedule_period" in str(caught.value)
        conn.rollback()
        conn.begin()
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
        portfolio_id, mv = _seed_referents(conn, tenant)
        # NULL period keys (the legacy kinds) never collide on the partial unique.
        sched2 = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO schedule (id, tenant_id, valid_from, created_at, updated_at, code,"
                " name, target_run_type, scope_portfolio_id, model_version_id, environment_id,"
                " cadence_kind, interval_days, anchor_date, status, record_version)"
                " VALUES (:id, :t, now(), now(), now(), :code, 'n', 'VAR', :pf, :mv, 'ci',"
                " 'INTERVAL', 7, '2026-01-01', 'ACTIVE', 1)"
            ),
            {
                "id": sched2,
                "t": tenant,
                "code": f"c-{uuid.uuid4().hex[:8]}",
                "pf": portfolio_id,
                "mv": mv,
            },
        )
        for instant in ("2026-01-08 00:00:00+00", "2026-01-15 00:00:00+00"):
            conn.execute(
                text(
                    "INSERT INTO scheduled_run (id, tenant_id, system_from, schedule_id,"
                    " scheduled_for, period_key, fired_at, outcome)"
                    " VALUES (:id, :t, now(), :s, :sf, NULL, now(), 'DISPATCHED')"
                ),
                {"id": str(uuid.uuid4()), "t": tenant, "s": sched2, "sf": instant},
            )
        conn.rollback()
    engine.dispose()
