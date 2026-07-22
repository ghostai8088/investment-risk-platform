"""PostgreSQL migration-mechanics proofs for PPF-1 ``private_factor_return_result`` (ENT-060, IA).

Catalog-introspection only (no FK-parent seeding — the binder + its full-chain end-to-end proof
land at demo stage 11): the symmetric FORCE-RLS policy (``USING == WITH CHECK == own-tenant``, NOT
hybrid), the append-only P0001 trigger's existence, and the closed 5-table hybrid set unchanged.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TABLE = "private_factor_return_result"
_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")


def test_symmetric_force_rls_not_hybrid() -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            qual, with_check = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE schemaname='public' AND tablename=:t"
                ),
                {"t": _TABLE},
            ).one()
            assert SYSTEM_TENANT_ID not in qual, "must NOT be hybrid"
            assert SYSTEM_TENANT_ID not in with_check
            # Symmetric: USING and WITH CHECK are the same own-tenant predicate.
            assert "current_setting" in qual and "current_setting" in with_check
            enabled, forced = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
                ),
                {"t": _TABLE},
            ).one()
            assert enabled is True and forced is True, "FORCE RLS must be on"
    finally:
        engine.dispose()


def test_append_only_trigger_installed() -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            n = conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = :g AND NOT tgisinternal"),
                {"g": f"{_TABLE}_append_only"},
            ).scalar_one()
            assert n == 1, "the irp_prevent_mutation P0001 trigger must be installed"
    finally:
        engine.dispose()


def test_closed_hybrid_set_unchanged() -> None:
    engine = make_engine(URL, poolclass=NullPool)
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
            assert hybrid == set(_HYBRID), f"hybrid set drifted: {hybrid}"
    finally:
        engine.dispose()
