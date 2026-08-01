"""PERF-0 — the scale probe harness.

Seeds one rung of the ladder, then drives the governed chain SEGMENT BY SEGMENT through the SHIPPED
binders, timing each and recording memory. Reports dated readings; asserts nothing.

**This file lives OUTSIDE ``irp_shared`` deliberately.** The seed it calls is AST-fenced against
wall-clock and ``random`` so its output is byte-reproducible (OQ-PERF-0-9); a ``perf_counter()``
inside that package would break the guarantee the fence exists to provide. All timing therefore
wraps the calls from out here. It is also why the repo-wide "nothing imports synthetic" fence is not
tripped: that fence scans ``migrations/`` and ``apps/``, and this is neither.

**Every segment runs the REAL binder.** A reimplementation would measure code that does not ship.

Usage (never automatic — the seed's own env gate must be set):

    IRP_ALLOW_PERF_SEED=1 DATABASE_URL=... .venv/bin/python scripts/perf_probe.py --rungs 50,200

Each rung needs a FRESH schema (ordinal-keyed ids mean rungs overlap by design); pass
``--reset`` to have the harness drop and re-migrate between rungs.
"""

from __future__ import annotations

import argparse
import os
import resource
import subprocess
import sys
import time
import tracemalloc
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.synthetic.scale import (
    PERF_ACTOR_ID,
    PERF_TENANT_ID,
    _month_end_offsets,
    build_perf_book,
    perf_business_day,
)

_CODE_VERSION = "perf-0-probe"
_ENVIRONMENT_ID = "perf-probe"


@dataclass
class SegmentReading:
    """One segment's dated reading. ``ok=False`` records a segment that did not run and WHY —
    a probe that silently skipped a segment would overstate how fast the chain is."""

    name: str
    seconds: float
    peak_tracemalloc_mb: float
    peak_rss_mb: float
    ok: bool = True
    detail: str = ""


@dataclass
class RungReading:
    rung: int
    seed_seconds: float
    seed_rows: int
    segments: list[SegmentReading] = field(default_factory=list)

    @property
    def batch_seconds(self) -> float:
        """The DAILY BATCH total — compute only. The seed is one-time onboarding and is
        deliberately excluded (OQ-PERF-0-1/5): the ratified budget is about the nightly run."""
        return sum(s.seconds for s in self.segments if s.ok)


def _peak_rss_mb() -> float:
    """Peak RSS for this process. ``ru_maxrss`` is BYTES on macOS and KILOBYTES on Linux — a
    platform difference that silently scales the number by 1024 if assumed either way."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


class _Timed:
    """Times a block and captures peak allocation, from OUTSIDE the fenced seed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.reading: SegmentReading | None = None

    def __enter__(self) -> _Timed:
        tracemalloc.start()
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        seconds = time.perf_counter() - self._t0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.reading = SegmentReading(
            name=self.name,
            seconds=seconds,
            peak_tracemalloc_mb=peak / (1024 * 1024),
            peak_rss_mb=_peak_rss_mb(),
            ok=exc is None,
            detail="" if exc is None else f"{type(exc).__name__}: {exc}",
        )
        return True  # a failing segment is RECORDED, never fatal — the rest still measures


def reset_schema(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO PUBLIC"))
        conn.execute(text("GRANT CREATE ON SCHEMA public TO PUBLIC"))
    engine.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        capture_output=True,
        env={**os.environ, "DATABASE_URL": url},
    )


def _fail_segment_on_non_completed(reading: SegmentReading, statuses: list[str]) -> None:
    """F2 (the 2026-08-01 review): ``ok`` was exception-only, while every binder documents a
    commit-FAILED-and-return contract — the EXACT mechanism behind Reading 3's wrong concentration
    row, recreated for the segments whose statuses the harness discarded. A segment is only ``ok``
    when every run it minted COMPLETED; a FAILED run's time is the failure path's cost, and filing
    it as the segment's cost is how a reading lies."""
    bad = [x for x in statuses if x != "COMPLETED"]
    if bad and reading.ok:
        reading.ok = False
        reading.detail = f"{len(bad)} run(s) not COMPLETED: {sorted(set(bad))}"


def run_rung(
    url: str,
    rung: int,
    *,
    n_factors: int,
    n_return_days: int,
    positions_per_portfolio: int | None = None,
) -> RungReading:
    """Seed one rung, then drive the chain. Seed and compute are timed SEPARATELY."""
    from sqlalchemy import select

    from irp_shared.concentration.bootstrap import register_concentration_model
    from irp_shared.concentration.events import ConcentrationActor
    from irp_shared.concentration.service import run_concentration
    from irp_shared.exposure import ExposureActor, run_exposure
    from irp_shared.marketdata.models import Factor
    from irp_shared.perf.bootstrap import register_portfolio_return_model
    from irp_shared.perf.return_service import run_portfolio_return
    from irp_shared.portfolio.models import Portfolio
    from irp_shared.risk.bootstrap import (
        register_covariance_model,
        register_factor_exposure_model,
        register_var_model,
    )
    from irp_shared.risk.covariance_service import run_covariance
    from irp_shared.risk.factor_service import run_factor_exposure
    from irp_shared.risk.var_service import run_var

    engine = make_engine(url, poolclass=NullPool)
    session = make_session_factory(engine)()
    try:
        # --- SEED (timed on its own; NOT part of the daily-batch number) ---
        with _Timed("seed") as t:
            summary = build_perf_book(
                session,
                rung_positions=rung,
                allow_perf_seed=True,
                n_factors=n_factors,
                n_return_days=n_return_days,
                # PG has the SYSTEM currency reference migrated, and the allocation
                # model requires a CURRENCY factor to carry a currency scope.
                factor_currency_code="USD",
                # Seeds a minimal SECTOR_INDUSTRY taxonomy + per-instrument assignments;
                # concentration refuses without a classification dimension and scheme.
                classify=True,
                **(
                    {"positions_per_portfolio": positions_per_portfolio}
                    if positions_per_portfolio is not None
                    else {}
                ),
            )
            session.commit()
        seed_reading = t.reading
        assert seed_reading is not None
        if not seed_reading.ok:
            raise RuntimeError(f"seed failed: {seed_reading.detail}")
        seed_rows = (
            summary.positions
            + summary.valuations
            + summary.instruments
            + summary.portfolios
            + summary.factors
            + summary.factor_returns
        )

        reading = RungReading(rung=rung, seed_seconds=seed_reading.seconds, seed_rows=seed_rows)

        # Model registrations are SETUP, not a measured segment — they are a handful of rows and
        # would otherwise be charged to whichever segment happened to run first.
        fe_version = register_factor_exposure_model(
            session, tenant_id=PERF_TENANT_ID, actor_id=PERF_ACTOR_ID, code_version=_CODE_VERSION
        )
        cov_version = register_covariance_model(
            session,
            tenant_id=PERF_TENANT_ID,
            actor_id=PERF_ACTOR_ID,
            code_version=_CODE_VERSION,
            window_observations=n_return_days,
        )
        ret_version = register_portfolio_return_model(
            session, tenant_id=PERF_TENANT_ID, actor_id=PERF_ACTOR_ID, code_version=_CODE_VERSION
        )
        var_version = register_var_model(
            session,
            tenant_id=PERF_TENANT_ID,
            actor_id=PERF_ACTOR_ID,
            code_version=_CODE_VERSION,
            confidence_level="0.99",
            horizon_days=1,
        )
        con_version = register_concentration_model(
            session,
            tenant_id=PERF_TENANT_ID,
            actor_id=PERF_ACTOR_ID,
            code_version=_CODE_VERSION,
            coverage_floor="0.5",
        )
        session.commit()

        portfolio_ids = [
            str(r[0])
            for r in session.execute(
                select(Portfolio.id).where(Portfolio.tenant_id == PERF_TENANT_ID)
            ).all()
        ]
        factor_ids = [
            str(r[0])
            for r in session.execute(
                select(Factor.id).where(Factor.tenant_id == PERF_TENANT_ID)
            ).all()
        ]
        as_of = summary.measurement_date
        # The PRIOR month-end, selected explicitly (never "the latest" — the OQ-CON-1-20 rule).
        prior_as_of = perf_business_day(_month_end_offsets()[-2])

        # --- SEGMENT 1: exposure (model-less family) ---
        # TWO boundary dates per portfolio: portfolio_return measures a return BETWEEN two
        # points and refuses a single run ("exposure_run_ids (>= 2 boundary runs) are required"),
        # so a one-date probe would leave that segment permanently unmeasured.
        exposure_run_ids: list[str] = []
        latest_run_ids: list[str] = []
        # PER-PORTFOLIO boundary pairs: portfolio_return v1 REFUSES an atom set spanning more than
        # one portfolio ("v1 measures a SINGLE portfolio"). Passing every portfolio's runs into one
        # call was a harness defect the 20-position smoke could not see, because that whole book fit
        # in a single portfolio.
        runs_by_portfolio: dict[str, list[str]] = {}
        with _Timed("exposure") as t:
            for pid in portfolio_ids:
                for boundary in (prior_as_of, as_of):
                    result = run_exposure(
                        session,
                        acting_tenant=PERF_TENANT_ID,
                        actor=ExposureActor(actor_id=PERF_ACTOR_ID),
                        code_version=_CODE_VERSION,
                        environment_id=_ENVIRONMENT_ID,
                        portfolio_id=pid,
                        as_of_valid_at=boundary,
                        base_currency="USD",
                    )
                    exposure_run_ids.append(str(result.run.run_id))
                    runs_by_portfolio.setdefault(pid, []).append(str(result.run.run_id))
                    if boundary == as_of:
                        latest_run_ids.append(str(result.run.run_id))
            session.commit()
        reading.segments.append(t.reading)

        # --- SEGMENT 2: factor exposure ---
        factor_exposure_run_ids: list[str] = []
        with _Timed("factor_exposure") as t:
            for exposure_run_id in latest_run_ids:
                fe_result = run_factor_exposure(
                    session,
                    acting_tenant=PERF_TENANT_ID,
                    actor=ExposureActor(actor_id=PERF_ACTOR_ID),
                    code_version=_CODE_VERSION,
                    environment_id=_ENVIRONMENT_ID,
                    model_version_id=str(fe_version.id),
                    exposure_run_id=exposure_run_id,
                    factor_ids=factor_ids,
                )
                factor_exposure_run_ids.append(str(fe_result.run.run_id))
            session.commit()
        reading.segments.append(t.reading)

        # --- SEGMENT 3: covariance ---
        covariance_run_id = None
        with _Timed("covariance") as t:
            cov = run_covariance(
                session,
                acting_tenant=PERF_TENANT_ID,
                actor=ExposureActor(actor_id=PERF_ACTOR_ID),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=str(cov_version.id),
                factor_ids=factor_ids,
                as_of_valid_at=as_of,
            )
            covariance_run_id = str(cov.run.run_id)
            session.commit()
        reading.segments.append(t.reading)

        # --- SEGMENT 4: VaR ---
        with _Timed("var") as t:
            if covariance_run_id is None:
                raise RuntimeError("covariance did not produce a run — VaR cannot bind")
            var_statuses: list[str] = []
            for exposure_run_id in factor_exposure_run_ids:
                var_result = run_var(
                    session,
                    acting_tenant=PERF_TENANT_ID,
                    actor=ExposureActor(actor_id=PERF_ACTOR_ID),
                    code_version=_CODE_VERSION,
                    environment_id=_ENVIRONMENT_ID,
                    model_version_id=str(var_version.id),
                    exposure_run_id=exposure_run_id,
                    covariance_run_id=covariance_run_id,
                )
                var_statuses.append(str(var_result.status))
            session.commit()
        assert t.reading is not None
        _fail_segment_on_non_completed(t.reading, var_statuses)
        reading.segments.append(t.reading)

        # --- SEGMENT 5: portfolio return ---
        with _Timed("portfolio_return") as t:
            ret_statuses: list[str] = []
            for pid_runs in runs_by_portfolio.values():
                ret_result = run_portfolio_return(
                    session,
                    acting_tenant=PERF_TENANT_ID,
                    actor=ExposureActor(actor_id=PERF_ACTOR_ID),
                    code_version=_CODE_VERSION,
                    environment_id=_ENVIRONMENT_ID,
                    model_version_id=str(ret_version.id),
                    exposure_run_ids=pid_runs,
                )
                ret_statuses.append(str(ret_result.status))
            session.commit()
        assert t.reading is not None
        _fail_segment_on_non_completed(t.reading, ret_statuses)
        reading.segments.append(t.reading)

        # --- SEGMENT 6: concentration (CON-1 — added because it shipped after the roadmap row) ---
        with _Timed("concentration") as t:
            for exposure_run_id in latest_run_ids:
                run_concentration(
                    session,
                    acting_tenant=PERF_TENANT_ID,
                    actor=ConcentrationActor(actor_id=PERF_ACTOR_ID),
                    code_version=_CODE_VERSION,
                    environment_id=_ENVIRONMENT_ID,
                    model_version_id=str(con_version.id),
                    exposure_run_id=exposure_run_id,
                    scheme_by_dimension=(
                        {}
                        if summary.sector_scheme_id is None
                        else {"SECTOR_INDUSTRY": summary.sector_scheme_id}
                    ),
                )
            session.commit()
        reading.segments.append(t.reading)

        return reading
    finally:
        session.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="PERF-0 scale probe")
    parser.add_argument("--rungs", default="50", help="comma-separated ladder points")
    parser.add_argument("--factors", type=int, default=8)
    parser.add_argument("--return-days", type=int, default=260)
    parser.add_argument("--reset", action="store_true", help="reset the schema before each rung")
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()

    if not args.url:
        print("DATABASE_URL (or --url) is required", file=sys.stderr)
        return 2
    if os.environ.get("IRP_ALLOW_PERF_SEED") != "1":
        print("IRP_ALLOW_PERF_SEED=1 is required (the seed's non-production gate)", file=sys.stderr)
        return 2

    readings: list[RungReading] = []
    for rung in [int(r) for r in args.rungs.split(",") if r.strip()]:
        if args.reset:
            reset_schema(args.url)
        r = run_rung(args.url, rung, n_factors=args.factors, n_return_days=args.return_days)
        readings.append(r)
        print(
            f"\nrung={r.rung}  seed={r.seed_seconds:.2f}s ({r.seed_rows} rows)  "
            f"BATCH={r.batch_seconds:.2f}s",
            flush=True,
        )
        for s in r.segments:
            status = "" if s.ok else f"  !! {s.detail}"
            print(
                f"    {s.name:18s} {s.seconds:9.2f}s  "
                f"tracemalloc_peak={s.peak_tracemalloc_mb:7.1f}MB  "
                f"rss_peak={s.peak_rss_mb:7.1f}MB{status}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
