"""Engine and session factory helpers.

The database URL is supplied by configuration/environment (no secrets in source — BR-10).
Unit tests build an in-memory SQLite engine; runtime uses PostgreSQL (AD-004 / AD-011).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from irp_shared.db.tenant import attach_tenant_reset


def make_engine(url: str, **kwargs: Any) -> Engine:
    engine = create_engine(url, future=True, **kwargs)
    attach_tenant_reset(
        engine
    )  # pool check-in RESET of app.current_tenant (AD-016); no-op on SQLite
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
