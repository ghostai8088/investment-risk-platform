"""Engine and session factory helpers.

The database URL is supplied by configuration/environment (no secrets in source — BR-10).
Unit tests build an in-memory SQLite engine; runtime uses PostgreSQL (AD-004 / AD-011).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from irp_shared.db.tenant import attach_tenant_reset


def make_engine(url: str, **kwargs: Any) -> Engine:
    engine = create_engine(url, future=True, **kwargs)
    attach_tenant_reset(
        engine
    )  # pool check-in RESET of app.current_tenant (AD-016); no-op on SQLite
    if engine.dialect.name == "sqlite":
        # FOREIGN KEYS ARE ENFORCED ON EVERY SQLITE ENGINE THIS FACTORY BUILDS — the FK-1 fix.
        #
        # SQLite ships with ``PRAGMA foreign_keys`` OFF, so for the platform's whole life an INSERT
        # naming a parent that does not exist succeeded silently on the unit tier while PostgreSQL
        # refused it. The cost was measured, not argued: RPT-1 generated reports against a
        # ``portfolio_id`` resolving to NOTHING through eighteen green tests, found only when the
        # deployed restore proof ran the same rows through PostgreSQL; the wider census found 115
        # tests across 12 suites writing dangling foreign keys, all green (P15 at engine scale —
        # every suite shared the assumption that the parent existed).
        #
        # Enforcement lives HERE, in the factory, not in per-suite fixtures: an opt-in control is a
        # control only for the suites that opted in, and the next suite would be born blind. The
        # dialect guard keeps this a no-op for PostgreSQL, where FKs are always enforced.
        @event.listens_for(engine, "connect")
        def _enforce_sqlite_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
