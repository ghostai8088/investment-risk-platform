"""PERF-0 — the scale seed's gates, determinism, and shape (unit tier, SQLite).

The seed is the input to every reading the probe produces, so it is proven here BEFORE any number
is measured: a seed that silently wrote a different book each run would make the ladder's growth
exponent meaningless.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.models import Base
from irp_shared.position.models import Position
from irp_shared.synthetic.ids import SYNTHETIC_TENANT_ID
from irp_shared.synthetic.scale import (
    ALLOW_PERF_SEED_ENV,
    PERF_TENANT_ID,
    PerfSeedRefused,
    build_perf_book,
)
from irp_shared.valuation.models import Valuation

_RUNG = 8  # a tiny rung: this file proves SHAPE and DETERMINISM, never performance


@pytest.fixture
def db():  # noqa: ANN201
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def _allow(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv(ALLOW_PERF_SEED_ENV, "1")


class TestGates:
    """Three independent refusals — each proven, none inferred from the others."""

    def test_refuses_without_explicit_confirmation(self, db, _allow) -> None:  # noqa: ANN001
        with pytest.raises(PerfSeedRefused, match="never-auto-run"):
            build_perf_book(db, rung_positions=_RUNG, allow_perf_seed=False)

    def test_refuses_without_the_env_gate(self, db, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.delenv(ALLOW_PERF_SEED_ENV, raising=False)
        with pytest.raises(PerfSeedRefused, match="non-production gate"):
            build_perf_book(db, rung_positions=_RUNG, allow_perf_seed=True)

    def test_refuses_the_SYNTHETIC_tenant_specifically(self, db, _allow) -> None:  # noqa: ANN001
        """The reversal that created this module (OQ-PERF-0-10): the perf seed must never write to
        the synthetic tenant, whose RLS-scoped exact-count guards it would corrupt."""
        with pytest.raises(PerfSeedRefused, match="reserved PERF tenant"):
            build_perf_book(
                db,
                rung_positions=_RUNG,
                allow_perf_seed=True,
                tenant_id=SYNTHETIC_TENANT_ID,
            )

    def test_the_two_reserved_tenants_are_distinct(self) -> None:
        assert PERF_TENANT_ID != SYNTHETIC_TENANT_ID


class TestShape:
    """What the seed actually wrote — counted from the DATABASE, not taken from the summary."""

    def test_row_counts_match_the_reported_summary(self, db, _allow) -> None:  # noqa: ANN001
        summary = build_perf_book(db, rung_positions=_RUNG, allow_perf_seed=True)
        db.flush()
        positions = db.execute(select(func.count()).select_from(Position)).scalar_one()
        valuations = db.execute(select(func.count()).select_from(Valuation)).scalar_one()
        assert positions == _RUNG, f"seeded {positions} positions, asked for {_RUNG}"
        assert summary.positions == positions, "the summary disagrees with the database"
        # 36 month-end marks per position (OQ-PERF-0-2's ratified shape), asserted as the PRODUCT
        # the seeder must have produced — computed HERE (the test may multiply; the seed may not).
        assert valuations == _RUNG * 36, f"expected {_RUNG * 36} marks, got {valuations}"
        assert summary.valuations == valuations
        assert summary.tenant_id == PERF_TENANT_ID

    def test_factor_counts_are_COUNTED_not_echoed_from_the_arguments(self, db, _allow) -> None:  # noqa: ANN001
        """An earlier draft reported ``factors=n_factors`` while creating NONE and
        ``factor_returns=0`` unconditionally — a summary that describes its arguments rather than
        its writes. Both halves are now read back from the database."""
        from irp_shared.marketdata.models import Factor, FactorReturn

        summary = build_perf_book(
            db, rung_positions=4, allow_perf_seed=True, n_factors=3, n_return_days=5
        )
        db.flush()
        factors = db.execute(select(func.count()).select_from(Factor)).scalar_one()
        returns = db.execute(select(func.count()).select_from(FactorReturn)).scalar_one()
        assert factors == 3, f"asked for 3 factors, seeded {factors}"
        assert returns == 3 * 5, f"asked for 15 factor returns, seeded {returns}"
        assert summary.factors == factors, "the summary's factor count disagrees with the database"
        assert summary.factor_returns == returns, "the summary's return count disagrees"

    def test_no_factor_series_is_constant(self, db, _allow) -> None:
        """A constant return series makes the covariance matrix singular, so the chain would fail
        for a reason that has nothing to do with scale — the probe would measure a bug."""
        from irp_shared.marketdata.models import FactorReturn

        build_perf_book(db, rung_positions=4, allow_perf_seed=True, n_factors=3, n_return_days=8)
        db.flush()
        by_factor: dict[str, set] = {}
        for fid, value in db.execute(
            select(FactorReturn.factor_id, FactorReturn.return_value)
        ).all():
            by_factor.setdefault(str(fid), set()).add(value)
        assert by_factor, "no factor returns were seeded"
        for fid, values in by_factor.items():
            assert len(values) > 1, f"factor {fid} has a CONSTANT series ({values}) — singular"

    def test_every_row_lands_in_the_PERF_tenant_only(self, db, _allow) -> None:  # noqa: ANN001
        build_perf_book(db, rung_positions=_RUNG, allow_perf_seed=True)
        db.flush()
        tenants = {r[0] for r in db.execute(select(Position.tenant_id).distinct()).all()} | {
            r[0] for r in db.execute(select(Valuation.tenant_id).distinct()).all()
        }
        assert tenants == {PERF_TENANT_ID}, f"the seed leaked into {tenants - {PERF_TENANT_ID}}"


class TestDeterminism:
    """The property the whole probe rests on: the same rung yields the same book, every run."""

    @staticmethod
    def _seed_ids(rung: int):  # noqa: ANN205
        engine = make_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session = make_session_factory(engine)()
        try:
            build_perf_book(session, rung_positions=rung, allow_perf_seed=True)
            session.flush()
            return sorted(str(r[0]) for r in session.execute(select(Position.id)).all())
        finally:
            session.close()
            engine.dispose()

    def test_two_independent_seeds_produce_identical_ids(self, _allow) -> None:  # noqa: ANN001
        first = self._seed_ids(_RUNG)
        second = self._seed_ids(_RUNG)
        assert first == second, "the scale seed is not reproducible — the ladder would be noise"
        assert len(first) == _RUNG

    def test_a_LARGER_rung_extends_the_smaller_one_rather_than_reshuffling(self, _allow) -> None:  # noqa: ANN001
        """Ids are keyed by ordinal, so rung N+k must CONTAIN rung N's ids. Without this the rungs
        are different books and the growth exponent compares unlike things."""
        small = set(self._seed_ids(_RUNG))
        large = set(self._seed_ids(_RUNG + 4))
        assert small < large, "a larger rung reshuffled the smaller rung's positions"
