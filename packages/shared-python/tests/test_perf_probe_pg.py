"""PERF-0 — the CI smoke: the harness still drives the WHOLE chain (PostgreSQL).

**A correctness smoke, NOT a performance gate.** It asserts that every one of the six segments
still executes end-to-end and produces a COMPLETED governed run. It deliberately asserts **NO
timing budget**: CI runners are noisy shared hardware, so a wall-clock assertion here would be a
flaky gate that teaches people to ignore it (OQ-PERF-0-4). The budget is checked against readings
taken on a quiet machine, recorded in ``perf_0_readings.md``.

Why it exists at all: the CON-1 lesson is that unexecuted machinery rots. A probe that only ever
runs by hand will be broken the next time someone reaches for it — and it will be discovered broken
precisely when a scale question is urgent. The rung is TINY on purpose; the subject is the harness,
not the platform's speed.

It imports the REAL ``scripts/perf_probe.py`` by path rather than re-implementing the chain: a copy
would pass while the harness itself rotted, which is the failure this test exists to prevent.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.synthetic.scale import ALLOW_PERF_SEED_ENV, PERF_TENANT_ID

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

#: Small enough to keep CI honest about time, large enough that the book spans TWO portfolios —
#: the shape that caught the ``portfolio_return`` multi-portfolio defect a single-portfolio smoke
#: could not see.
_RUNG = 3
_FACTORS = 2
_RETURN_DAYS = 4

_EXPECTED_SEGMENTS = (
    "exposure",
    "factor_exposure",
    "covariance",
    "var",
    "portfolio_return",
    "concentration",
)


def _load_harness():  # noqa: ANN202
    """Import ``scripts/perf_probe.py`` by path — the REAL harness, never a copy."""
    root = pathlib.Path(__file__).resolve().parents[3]
    path = root / "scripts" / "perf_probe.py"
    assert path.exists(), f"the perf harness is missing at {path}"
    spec = importlib.util.spec_from_file_location("perf_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # REGISTER before exec: the harness defines dataclasses, and dataclass field-type resolution
    # looks the defining module up in sys.modules. Executing an unregistered module makes that
    # lookup return None and fail deep inside the stdlib with an unhelpful AttributeError.
    sys.modules["perf_probe"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def probe_reading():  # noqa: ANN201
    """ONE rung for the whole module. The seed refuses a tenant that already holds a rung (ids are
    ordinal-keyed, so rungs overlap by design), and this smoke must NOT reset the schema — it shares
    a database with the rest of the battery. So the rung runs once and both tests read it."""
    previous = os.environ.get(ALLOW_PERF_SEED_ENV)
    os.environ[ALLOW_PERF_SEED_ENV] = "1"
    try:
        harness = _load_harness()
        yield harness.run_rung(URL, _RUNG, n_factors=_FACTORS, n_return_days=_RETURN_DAYS)
    finally:
        if previous is None:
            os.environ.pop(ALLOW_PERF_SEED_ENV, None)
        else:
            os.environ[ALLOW_PERF_SEED_ENV] = previous


def test_the_harness_still_drives_every_segment(probe_reading) -> None:  # noqa: ANN001
    """Every segment runs and reports ``ok``. A segment that silently stopped running would make
    every future batch reading a lower bound without anyone noticing — which is exactly what
    happened before ``portfolio_return`` and ``concentration`` were fixed."""
    reading = probe_reading

    names = [s.name for s in reading.segments]
    assert names == list(_EXPECTED_SEGMENTS), f"segment set changed: {names}"

    failed = [(s.name, s.detail) for s in reading.segments if not s.ok]
    assert failed == [], f"segments failed: {failed}"

    # Timing is REPORTED, never asserted (see the module docstring).
    assert reading.seed_seconds > 0
    assert reading.batch_seconds > 0
    assert reading.seed_rows > 0


def test_the_chain_produced_COMPLETED_governed_runs(probe_reading) -> None:  # noqa: ANN001
    """Segments reporting ``ok`` is the harness's own account; this reads the DATABASE. A binder
    that returned without minting a governed run would satisfy the first test and nothing else."""
    assert probe_reading is not None  # the module-scoped rung already ran

    engine = make_engine(URL, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        set_tenant_context(session, PERF_TENANT_ID)
        completed = session.execute(
            select(CalculationRun.run_type, func.count())
            .where(
                CalculationRun.tenant_id == PERF_TENANT_ID,
                CalculationRun.status == "COMPLETED",
            )
            .group_by(CalculationRun.run_type)
        ).all()
        by_type = {str(r[0]): r[1] for r in completed}
        assert by_type, "the chain minted no COMPLETED runs in the PERF tenant"
        # Each family that the chain drives must appear at least once.
        for run_type in ("EXPOSURE_AGGREGATE", "COVARIANCE", "CONCENTRATION"):
            assert by_type.get(run_type, 0) >= 1, f"no COMPLETED {run_type} run: {by_type}"
    finally:
        session.close()
        engine.dispose()
