"""SR-1 PostgreSQL enforcement tier for ENT-065 ``sharpe_ratio_result``.

**Shipped FROM BIRTH, not after a review.** RM-1's 4-finder review found ENT-064 was the only
governed result family with no PG suite at all — its SQLite battery and its demo stage exercised
nothing the database itself guarantees, and those guarantees are ORM-invisible by construction: the
CHECK and the RLS policy are created imperatively in the migration, and the append-only trigger is a
PL/pgSQL function. SR-1 owes the same suite on day one.

Five controls, each with its reject side EXECUTED (the standing rule: a guard never demonstrated to
fire is not a guard):

1. the suppression CHECK refuses every incoherent state and accepts both coherent ones;
2. the four-column grain refuses a true duplicate — the collision the grain exists to prevent;
3. the append-only trigger refuses UPDATE and DELETE;
4. tenant RLS hides another tenant's rows from a NON-BYPASSRLS role, with the explicit predicate and
   the policy checked SEPARATELY so neither can mask the other's absence;
5. the CHECK's NAME matches the ORM's — the RM-1 drift class, where ``op.create_table`` silently
   doubled and hash-truncated a full-literal constraint name while ``alembic check`` stayed blind
   because it does not compare CHECK constraints.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_CHECK = "ck_sharpe_ratio_result_suppression_coherent"
_GRAIN = "uq_sharpe_ratio_result_run_grain"


@pytest.fixture(scope="module")
def app_url() -> str:
    """The NON-superuser, NON-BYPASSRLS role the application actually connects as. RLS must hold for
    THAT role — a superuser bypasses it and would make the isolation test vacuous."""
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
        # Every referent table is granted EXPLICITLY here rather than inherited from another suite's
        # fixture: the SCH-2 review found a file that was green in CI only by GRANT LEAKAGE from
        # ~30 earlier suites in the same job, which would have gone red the moment it ran alone.
        for table in (
            "sharpe_ratio_result",
            "calculation_run",
            "dataset_snapshot",
            "portfolio",
            "model",
            "model_version",
            "benchmark",
            "currency",
        ):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_referents(conn, tenant: str) -> dict[str, str]:  # noqa: ANN001
    """Real FK referents. Random UUIDs would make every INSERT fail on the FK instead of on the
    constraint under test — the matrix would then 'pass' for entirely the wrong reason."""
    ids = {
        k: str(uuid.uuid4())
        for k in (
            "portfolio",
            "run",
            "return_run",
            "snapshot",
            "model",
            "model_version",
            "benchmark",
        )
    }
    conn.execute(
        text(
            "INSERT INTO portfolio (id, tenant_id, valid_from, created_at, updated_at, code, name,"
            " node_type, status, record_version)"
            " VALUES (:id, :t, now(), now(), now(), :code, 'p', 'ACCOUNT', 'ACTIVE', 1)"
        ),
        {"id": ids["portfolio"], "t": tenant, "code": f"pf-{uuid.uuid4().hex[:8]}"},
    )
    for key, run_type in (("run", "SHARPE"), ("return_run", "PORTFOLIO_RETURN")):
        conn.execute(
            text(
                "INSERT INTO calculation_run (run_id, id, tenant_id, system_from, run_type, status,"
                " initiated_by, code_version, environment_id, created_at)"
                " VALUES (:id, :id, :t, now(), :rt, 'COMPLETED', 'seed', 'v', 'test', now())"
            ),
            {"id": ids[key], "t": tenant, "rt": run_type},
        )
    conn.execute(
        text(
            "INSERT INTO model (id, tenant_id, valid_from, created_at, updated_at, record_version,"
            " code, name, model_type, is_active)"
            " VALUES (:id, :t, now(), now(), now(), 1, :code, 'm', 'PERF', true)"
        ),
        {"id": ids["model"], "t": tenant, "code": f"m-{uuid.uuid4().hex[:8]}"},
    )
    conn.execute(
        text(
            "INSERT INTO model_version (id, tenant_id, system_from, model_id, version_label)"
            " VALUES (:id, :t, now(), :model, 'v1')"
        ),
        {"id": ids["model_version"], "t": tenant, "model": ids["model"]},
    )
    conn.execute(
        text(
            "INSERT INTO dataset_snapshot (id, tenant_id, system_from, created_at, updated_at,"
            " label, purpose, as_of_valid_at, as_of_known_at, as_of_valuation_date,"
            " binding_predicate_version, component_count, manifest_hash)"
            " VALUES (:id, :t, now(), now(), now(), '', 'SHARPE_INPUT', now(), now(),"
            " :vd, 'v1:test', 0, :h)"
        ),
        {"id": ids["snapshot"], "t": tenant, "vd": date(2026, 1, 31), "h": "0" * 64},
    )
    conn.execute(
        text(
            "INSERT INTO benchmark (id, tenant_id, valid_from, created_at, updated_at,"
            " record_version, benchmark_code, benchmark_source, benchmark_currency)"
            " VALUES (:id, :t, now(), now(), now(), 1, :code, 'VENDOR', 'USD')"
        ),
        {"id": ids["benchmark"], "t": tenant, "code": f"rf-{uuid.uuid4().hex[:8]}"},
    )
    return ids


def _insert_row(conn, tenant: str, ids: dict[str, str], **over) -> None:  # noqa: ANN001, ANN003
    """A raw INSERT — the DB is the only judge here. Going through the binder would short-circuit on
    the service gate and prove nothing about the database."""
    values = {
        "id": str(uuid.uuid4()),
        "tenant": tenant,
        "run": ids["run"],
        "snapshot": ids["snapshot"],
        "model_version": ids["model_version"],
        "portfolio": ids["portfolio"],
        "return_run": ids["return_run"],
        "benchmark": ids["benchmark"],
        "rf_return_basis": "TOTAL",
        "metric_type": "SHARPE_RATIO",
        "window_months": 12,
        "period_start": date(2025, 1, 31),
        "period_end": date(2026, 1, 30),
        "metric_value": Decimal("0.65"),
        "suppressed": False,
        "suppression_reason": None,
        "annualization_basis": "NONE",
        "sampling_frequency": "MONTHLY",
        "n_observations": 12,
    }
    values.update(over)
    conn.execute(
        text(
            "INSERT INTO sharpe_ratio_result (id, tenant_id, system_from, calculation_run_id,"
            " input_snapshot_id, model_version_id, portfolio_id, portfolio_return_run_id,"
            " risk_free_benchmark_id, rf_return_basis, metric_type, window_months, period_start,"
            " period_end, metric_value, suppressed, suppression_reason, annualization_basis,"
            " sampling_frequency, n_observations)"
            " VALUES (:id, :tenant, now(), :run, :snapshot, :model_version, :portfolio,"
            " :return_run, :benchmark, :rf_return_basis, :metric_type, :window_months,"
            " :period_start, :period_end, :metric_value, :suppressed, :suppression_reason,"
            " :annualization_basis, :sampling_frequency, :n_observations)"
        ),
        values,
    )


def _arm(conn, tenant: str) -> None:  # noqa: ANN001
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})


# --- 1. the suppression CHECK ---------------------------------------------------------------------


def test_the_suppression_check_refuses_every_incoherent_state(app_url: str) -> None:  # noqa: F811
    """A TOTAL enumeration over the boolean, so no third state passes vacuously. Both coherent
    shapes are also asserted ACCEPTED — without that, a constraint refusing everything would look
    identical to a correct one."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenant = str(uuid.uuid4())
        _arm(conn, tenant)
        ids = _seed_referents(conn, tenant)

        incoherent = (
            ("suppressed with a value", {"suppressed": True, "suppression_reason": "why"}),
            (
                "suppressed with no reason",
                {"suppressed": True, "metric_value": None, "suppression_reason": None},
            ),
            ("emitted with a reason", {"suppressed": False, "suppression_reason": "why"}),
            ("emitted with no value", {"suppressed": False, "metric_value": None}),
        )
        for label, over in incoherent:
            sp = conn.begin_nested()
            with pytest.raises(IntegrityError) as caught:
                _insert_row(conn, tenant, ids, **over)
            assert _CHECK in str(caught.value.orig), f"{label} was refused by the WRONG constraint"
            sp.rollback()

        for _label, over in (
            ("a genuine value", {}),
            # A genuine ZERO — a book that exactly earns the risk-free rate. This shape is why the
            # column is nullable rather than sentinel-valued, so the CHECK must accept it.
            ("a genuine zero", {"metric_value": Decimal("0")}),
            (
                "a zero-dispersion suppression",
                {
                    "suppressed": True,
                    "metric_value": None,
                    "suppression_reason": "zero dispersion",
                    "window_months": 36,
                },
            ),
            (
                "an unfillable-window suppression",
                {
                    "suppressed": True,
                    "metric_value": None,
                    "suppression_reason": "insufficient history",
                    "n_observations": None,
                    "window_months": 36,
                },
            ),
        ):
            sp = conn.begin_nested()
            _insert_row(conn, tenant, ids, **over)  # must NOT raise
            sp.rollback()
        trans.rollback()
    engine.dispose()


def test_the_check_matrix_actually_observes_the_constraint() -> None:
    """THE EXECUTED NEGATIVE CONTROL. With the CHECK dropped, the incoherent rows must be ACCEPTED —
    otherwise the matrix above proves nothing about the constraint. Runs as the OWNER (irp_app holds
    no DDL rights) inside a transaction; PG DDL is transactional, so the rollback restores it."""
    engine = make_engine(URL, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text(f"ALTER TABLE sharpe_ratio_result DROP CONSTRAINT {_CHECK}"))
        tenant = str(uuid.uuid4())
        _arm(conn, tenant)
        ids = _seed_referents(conn, tenant)
        _insert_row(conn, tenant, ids, suppressed=True, suppression_reason="why")  # was refused
        trans.rollback()
    engine.dispose()


def test_the_check_constraint_NAME_matches_the_ORM_declaration() -> None:
    """THE RM-1 DRIFT CLASS, pinned rather than re-learned.

    ``env.py`` passes ``target_metadata``, so ``op.create_table`` DOES apply the
    ``ck_%(table_name)s_%(constraint_name)s`` convention — passing the full literal in the migration
    mints ``ck_..._ck_..._suppressi_075e`` (doubled, truncated to 63 chars, hash-suffixed) which
    silently diverges from the ORM's name. **``alembic check`` does not compare CHECK constraints**,
    so the drift gate is structurally blind to it; RM-1 found it only by applying the migration and
    reading ``pg_constraint`` back. This test IS that read.
    """
    engine = make_engine(URL, poolclass=NullPool)
    with engine.connect() as conn:
        names = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT conname FROM pg_constraint"
                    " WHERE conrelid = 'sharpe_ratio_result'::regclass AND contype = 'c'"
                )
            )
        ]
    engine.dispose()
    assert _CHECK in names, f"expected {_CHECK}, found {names}"


# --- 2. the four-column grain ---------------------------------------------------------------------


def test_the_four_column_grain_refuses_a_duplicate(app_url: str) -> None:  # noqa: F811
    """The collision the grain exists to prevent. Also proves the WINDOW is genuinely part of the
    key: the SAME (run, metric, period_start) at a DIFFERENT window is accepted, which is precisely
    why three columns were insufficient — under a three-column grain this family's two windows would
    collide at flush, i.e. a 500 inside the emit path rather than a governed refusal."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenant = str(uuid.uuid4())
        _arm(conn, tenant)
        ids = _seed_referents(conn, tenant)
        _insert_row(conn, tenant, ids)

        sp = conn.begin_nested()
        with pytest.raises(IntegrityError) as caught:
            _insert_row(conn, tenant, ids)  # identical four-tuple
        assert _GRAIN in str(caught.value.orig)
        sp.rollback()

        _insert_row(conn, tenant, ids, window_months=36)  # same three, different window: ACCEPTED
        # And the ratio/annualized PAIR shares everything but metric_type — the other reason the
        # grain needs all four columns.
        _insert_row(conn, tenant, ids, metric_type="SHARPE_RATIO_ANN")
        trans.rollback()
    engine.dispose()


# --- 3. the append-only trigger ------------------------------------------------------------------


def test_the_append_only_trigger_refuses_update_and_delete(app_url: str) -> None:  # noqa: F811
    """IA TRUE append-only at the DATABASE, not merely in the ORM guard: a direct SQL UPDATE or
    DELETE — which no ORM listener can see — must raise P0001 from ``irp_prevent_mutation``."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenant = str(uuid.uuid4())
        _arm(conn, tenant)
        ids = _seed_referents(conn, tenant)
        _insert_row(conn, tenant, ids)

        for statement in (
            "UPDATE sharpe_ratio_result SET metric_value = 0.99 WHERE tenant_id = :t",
            "DELETE FROM sharpe_ratio_result WHERE tenant_id = :t",
        ):
            sp = conn.begin_nested()
            with pytest.raises(DBAPIError) as caught:
                conn.execute(text(statement), {"t": tenant})
            assert "append-only" in str(caught.value.orig).lower()
            sp.rollback()
        trans.rollback()
    engine.dispose()


# --- 4. tenant isolation -------------------------------------------------------------------------


def test_rls_hides_another_tenants_rows_from_the_app_role(app_url: str) -> None:  # noqa: F811
    """Both layers, checked SEPARATELY — a test run only with the GUC and the predicate agreeing
    would pass with either one deleted."""
    engine = make_engine(app_url, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenants = []
        for _ in range(2):
            tenant = str(uuid.uuid4())
            _arm(conn, tenant)
            ids = _seed_referents(conn, tenant)
            _insert_row(conn, tenant, ids)
            tenants.append(tenant)
        a, b = tenants

        _arm(conn, a)
        mine = conn.execute(text("SELECT count(*) FROM sharpe_ratio_result")).scalar_one()
        assert mine == 1, "RLS did not scope the read to the armed tenant"
        # RLS ALONE: no predicate, B's row is still invisible while the GUC says A.
        foreign = conn.execute(
            text("SELECT count(*) FROM sharpe_ratio_result WHERE tenant_id = :t"), {"t": b}
        ).scalar_one()
        assert foreign == 0

        _arm(conn, b)
        assert conn.execute(text("SELECT count(*) FROM sharpe_ratio_result")).scalar_one() == 1
        trans.rollback()
    engine.dispose()


def test_the_isolation_test_would_notice_if_rls_were_off() -> None:
    """THE NEGATIVE CONTROL for the isolation test. As a SUPERUSER (who bypasses RLS entirely) both
    tenants' rows are visible from one session — so the assertion above is discriminating rather
    than an artefact of the seeding."""
    engine = make_engine(URL, poolclass=NullPool)
    with engine.connect() as conn:
        trans = conn.begin()
        tenants = []
        for _ in range(2):
            tenant = str(uuid.uuid4())
            _arm(conn, tenant)
            ids = _seed_referents(conn, tenant)
            _insert_row(conn, tenant, ids)
            tenants.append(tenant)
        _arm(conn, tenants[0])
        visible = conn.execute(
            text("SELECT count(*) FROM sharpe_ratio_result WHERE tenant_id = ANY(:ts)"),
            {"ts": tenants},
        ).scalar_one()
        assert visible == 2, "the superuser did not bypass RLS — the control proves nothing"
        trans.rollback()
    engine.dispose()
