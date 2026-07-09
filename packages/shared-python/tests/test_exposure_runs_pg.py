"""PostgreSQL-only proofs for the P3-C2 ``list_exposure_runs`` query (OD-C) — the exposure
sibling of ``test_risk_runs_pg.py``, run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app``
role (the CI/pipeline posture):

- FORCE-RLS tenant isolation THROUGH the listing (tenant A never sees B; no-context = zero
  rows — RLS fails closed underneath the query's own tenant predicate);
- the ``EXPOSURE_AGGREGATE``-only fence on PG (a real ``VAR`` run in the same table never
  appears — the mirror of the risk listing's four-family fence);
- the ``created_at DESC, run_id`` tie-break under PostgreSQL's native GUID ordering (explicit
  non-ascending insertion order — the tie-break is the only thing that can sort the page;
  review fold E2: the SQLite endpoint suite mints only distinct timestamps, so the tie-break
  is unexercised there);
- ``failure_reason`` PERSISTENCE on a FAILED exposure run under the app role (review fold E3:
  the P3-C2 scaffold improvement was proven only on SQLite — this pins it on the authoritative
  engine, catching a column/grant defect that only manifests on PostgreSQL).

The SQLite endpoint suite (``apps/backend/tests/test_exposure_runs_list_endpoint.py``) proves the
HTTP layer; this file proves the same fences hold on the authoritative engine.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.exposure import ExposureRunQueryError, list_exposure_runs
from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_T0 = datetime(2026, 6, 1, tzinfo=UTC)


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
        conn.execute(text("GRANT SELECT, INSERT, UPDATE ON calculation_run TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _mint(session, tenant_id: str, run_type: str, **kw) -> str:
    run = CalculationRun(
        tenant_id=tenant_id,
        run_type=run_type,
        status=kw.pop("status", "COMPLETED"),
        initiated_by="seed",
        created_at=kw.pop("created_at", _T0),
        **kw,
    )
    session.add(run)
    session.flush()
    return str(run.run_id)


def test_listing_is_tenant_isolated_and_fenced_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())

    with factory() as s:
        set_tenant_context(s, tenant_a)
        ids_a = {
            _mint(s, tenant_a, RUN_TYPE_EXPOSURE_AGGREGATE, created_at=_T0 + timedelta(minutes=i))
            for i in range(3)
        }
        _mint(s, tenant_a, "VAR")  # a real RISK run_type — the exposure fence must exclude it
        s.commit()
    with factory() as s:
        set_tenant_context(s, tenant_b)
        id_b = _mint(s, tenant_b, RUN_TYPE_EXPOSURE_AGGREGATE)
        s.commit()

    with factory() as s:
        set_tenant_context(s, tenant_a)
        got = {r.run_id for r in list_exposure_runs(s, acting_tenant=tenant_a)}
        assert ids_a <= got  # all of tenant A's exposure runs visible
        assert id_b not in got  # tenant B invisible
        # The fence: ONLY EXPOSURE_AGGREGATE — the VAR run never appears.
        assert all(
            r.run_type == RUN_TYPE_EXPOSURE_AGGREGATE
            for r in list_exposure_runs(s, acting_tenant=tenant_a)
        )

    # RLS fails closed underneath the predicate: tenant B's context + tenant A's id = nothing.
    with factory() as s:
        set_tenant_context(s, tenant_b)
        assert list_exposure_runs(s, acting_tenant=tenant_a) == []
    engine.dispose()


def test_tie_break_orders_by_run_id_on_pg(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    # Random ids SORTED ascending, then inserted in a rotated (never-ascending) order: with a
    # shared created_at, the run_id tie-break is the ONLY thing that can produce the sorted page.
    tie_ids = sorted(str(uuid.uuid4()) for _ in range(3))

    with factory() as s:
        set_tenant_context(s, tenant)
        for insertion_order in (2, 0, 1):  # insert 3rd, 1st, 2nd — never ascending
            _mint(
                s,
                tenant,
                RUN_TYPE_EXPOSURE_AGGREGATE,
                run_id=tie_ids[insertion_order],
                created_at=_T0,
            )
        newest = _mint(s, tenant, RUN_TYPE_EXPOSURE_AGGREGATE, created_at=_T0 + timedelta(hours=1))
        s.commit()
        set_tenant_context(s, tenant)  # the GUC is transaction-local (AD-016) — reset post-commit

        page = [r.run_id for r in list_exposure_runs(s, acting_tenant=tenant)]
        assert page == [newest, *tie_ids]
        # Offset pages partition on the same total order (PG uuid comparison).
        first = list_exposure_runs(s, acting_tenant=tenant, limit=2)
        rest = list_exposure_runs(s, acting_tenant=tenant, limit=2, offset=2)
        assert [r.run_id for r in first] + [r.run_id for r in rest] == page
    engine.dispose()


def test_failed_run_failure_reason_persists_under_app_role(app_url: str) -> None:
    """Review fold E3: the P3-C2 scaffold improvement (persisted ``failure_reason`` on FAILED
    exposure runs) round-trips through the constrained app role on PostgreSQL — the column is
    written and read back verbatim, not silently dropped."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    reason = "rule 'exposure.completeness' failed (severity=ERROR)"

    with factory() as s:
        set_tenant_context(s, tenant)
        run_id = _mint(
            s, tenant, RUN_TYPE_EXPOSURE_AGGREGATE, status="FAILED", failure_reason=reason
        )
        s.commit()
        set_tenant_context(s, tenant)  # GUC is transaction-local — reset post-commit

        rows = list_exposure_runs(s, acting_tenant=tenant, status="FAILED")
        assert [r.run_id for r in rows] == [run_id]
        assert rows[0].failure_reason == reason
    engine.dispose()


def test_unknown_status_refuses(app_url: str) -> None:
    """The fail-closed filter is a 422-class refusal on PG too (never a silently-empty page)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    with factory() as s:
        set_tenant_context(s, tenant)
        with pytest.raises(ExposureRunQueryError):
            list_exposure_runs(s, acting_tenant=tenant, status="NOPE")
    engine.dispose()
