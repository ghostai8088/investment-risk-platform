"""Unit-tier (SQLite) probes for the MF-1 extension's two refusal guards (OD-MF-1-B).

The PG suite cannot exercise the PREREQ refusal in CI — its own load-bearing ordering (the
campaign step seeds the tenant first) makes the probe self-skip there (the scope finder's MED-2).
Both guards fire BEFORE any PG-specific work (``set_tenant_context`` is a no-op off PostgreSQL),
so the refusal semantics get their executable coverage HERE, in every ``make check``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoMultifamilyAlreadySeededError,
    DemoMultifamilyPrereqError,
    run_demo_multifamily_extension,
)
from irp_shared.models import Base
from irp_shared.risk import register_factor_exposure_loadings_model


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def test_prereq_refusal_on_an_unseeded_tenant(session: Session) -> None:
    # The extension never bootstraps: a demo tenant with NO model rows refuses outright.
    with pytest.raises(DemoMultifamilyPrereqError, match="never bootstraps"):
        run_demo_multifamily_extension(session)


def test_own_footprint_refusal_is_refuse_not_skip(session: Session) -> None:
    # A tenant that already holds the loadings model refuses (never skips or double-files) —
    # registering ONLY the loadings code passes the prereq count and trips the footprint probe.
    register_factor_exposure_loadings_model(
        session, tenant_id=DEMO_TENANT_ID, actor_id="probe", code_version="probe"
    )
    session.flush()
    with pytest.raises(DemoMultifamilyAlreadySeededError):
        run_demo_multifamily_extension(session)
