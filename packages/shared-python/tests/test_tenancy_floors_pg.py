"""Platform-wide tenancy FLOORS (REF-1, OQ-REF-1-12) — the P6 obligation on a widened guard.

REF-1 grew the closed hybrid set from five tables to seven and collapsed 31 hand-mirrored copies of
the expected set into one declaration. That collapse is right — 31 independently-maintained copies
of an expected value ARE the drift surface the census exists to detect — but it converts 31
independent checks into derived ones, so the census alone is no longer sufficient evidence. P6:
a guard that works by ENUMERATION ships with a coverage floor that fails loudly when its in-scope
population collapses.

Two floors here, both platform-wide rather than per-slice, because both close paths that every
existing enumerated guard is structurally blind to:

**Floor 1 — the EFFECTIVE write check.** Every existing census asks "is the SYSTEM literal in
``with_check``?". In PostgreSQL a policy created WITHOUT a ``WITH CHECK`` clause reuses its
``USING`` expression as the write check, and ``pg_policies.with_check`` then reads **NULL** — so a
hybrid-shaped policy authored as ``USING (own OR SYSTEM)`` with the clause omitted is exactly the
cross-tenant write breach migration 0008 warns about, and every census reads NULL and passes.
Six ``USING``-only policies already exist on ``main``, so this is the natural shape to copy, not a
hypothetical. The floor tests ``COALESCE(with_check, qual)`` and carries a negative control that
creates precisely that policy and proves the floor FIRES.

**Floor 2 — FORCE RLS coverage.** A tenant-scoped table that loses (or never gains) FORCE RLS is
invisible to a set-membership census, which only ever looks at the tables it enumerates. This floor
inverts the question: it walks every ``tenant_id``-bearing table in the ORM metadata and asserts
each one is both RLS-enabled and FORCE-enabled — so a NEW tenant table that nobody remembered to
police fails here rather than shipping silently.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.models import Base
from irp_shared.reference.models import HYBRID_TABLES

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _tenant_scoped_tables() -> set[str]:
    """Every mapped table carrying a ``tenant_id`` column — the floor's in-scope population."""
    return {
        name
        for name, table in Base.metadata.tables.items()
        if "tenant_id" in table.columns  # noqa: SIM118 - SQLAlchemy ColumnCollection
    }


def test_no_policy_admits_a_system_write_through_its_effective_check() -> None:
    """FLOOR 1: no policy anywhere may carry the SYSTEM literal in its EFFECTIVE write check.

    ``COALESCE(with_check, qual)`` is the effective check — that COALESCE is the entire point, and
    is what every per-table census misses.
    """
    engine = make_engine(URL, poolclass=NullPool)
    with engine.begin() as conn:
        offenders = conn.execute(
            text(
                """
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND COALESCE(with_check, qual) LIKE :sys
                ORDER BY tablename, policyname
                """
            ),
            {"sys": f"%{SYSTEM_TENANT_ID}%"},
        ).all()
    assert not offenders, (
        "policies admit a SYSTEM-tenant WRITE through their effective check "
        f"(COALESCE(with_check, qual)): {[(t, p) for t, p in offenders]}"
    )
    engine.dispose()


def test_floor_1_fires_on_a_using_only_hybrid_policy() -> None:
    """NEGATIVE CONTROL for floor 1 — without this the floor could be vacuous.

    Creates the exact defect the floor exists for: a hybrid-shaped policy with the ``WITH CHECK``
    clause OMITTED, so PostgreSQL reuses ``USING`` as the write check and ``with_check`` is NULL.
    A census over ``with_check`` alone reads NULL and passes; the floor must FAIL.
    """
    engine = make_engine(URL, poolclass=NullPool)
    table = "_floor_probe_using_only"
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            conn.execute(
                text(f"CREATE TABLE {table} (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
            )
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            # The defect: USING own-OR-SYSTEM and NO WITH CHECK clause.
            conn.execute(
                text(
                    f"CREATE POLICY tenant_isolation_{table} ON {table} "
                    f"USING (tenant_id::text = current_setting('app.current_tenant', true) "
                    f"OR tenant_id::text = '{SYSTEM_TENANT_ID}')"
                )
            )

        # The naive census passes: with_check is NULL, so it contains no SYSTEM literal.
        with engine.begin() as conn:
            naive = conn.execute(
                text(
                    "SELECT with_check FROM pg_policies "
                    "WHERE schemaname='public' AND tablename = :t"
                ),
                {"t": table},
            ).scalar_one()
        assert naive is None, "the probe must produce a NULL with_check — that IS the blind spot"

        # The floor catches it.
        with engine.begin() as conn:
            effective = conn.execute(
                text(
                    "SELECT COALESCE(with_check, qual) FROM pg_policies "
                    "WHERE schemaname='public' AND tablename = :t"
                ),
                {"t": table},
            ).scalar_one()
        assert SYSTEM_TENANT_ID in effective, "floor 1 failed to see the USING-only write breach"
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        engine.dispose()


def test_every_tenant_scoped_table_is_rls_forced() -> None:
    """FLOOR 2: coverage, not membership — a new tenant table nobody policed fails HERE."""
    engine = make_engine(URL, poolclass=NullPool)
    expected = _tenant_scoped_tables()
    assert expected, "the floor's own population is empty — the floor would pass vacuously"
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                """
            )
        ).all()
    state = {name: (enabled, forced) for name, enabled, forced in rows}
    missing = sorted(t for t in expected if t in state and not state[t][0])
    unforced = sorted(t for t in expected if t in state and state[t][0] and not state[t][1])
    assert not missing, f"tenant-scoped tables without RLS ENABLED: {missing}"
    assert not unforced, f"tenant-scoped tables without FORCE RLS (owner bypasses): {unforced}"
    engine.dispose()


def test_hybrid_membership_is_exactly_the_declared_set() -> None:
    """The census itself, now derived from ONE declaration — paired with the floors above so that
    deriving it does not make it weaker."""
    engine = make_engine(URL, poolclass=NullPool)
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT DISTINCT tablename FROM pg_policies "
                    "WHERE schemaname='public' AND qual LIKE :sys ORDER BY tablename"
                ),
                {"sys": f"%{SYSTEM_TENANT_ID}%"},
            )
            .scalars()
            .all()
        )
    assert set(rows) == set(HYBRID_TABLES), (
        "tables whose USING admits the SYSTEM tenant must be EXACTLY the declared hybrid set "
        f"(declared={sorted(HYBRID_TABLES)}, actual={sorted(rows)})"
    )
    assert len(HYBRID_TABLES) == 7, "AD-013-R2 ratified N = 7"
    engine.dispose()
