"""Run the RS-1 stage-5 demo (OD-RS-1-E) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_rs1_stage5`: grows the equity sleeve to the EB
identifiability floor (MF-EQ-C), registers the two residual-estimator versions (EWMA declared
lambda=0.94; EB shrinkage method-as-identity), re-estimates MF-EQ-B (EWMA) and shrinks MF-EQ-A
(EB over the 3-equity cohort; the bond excluded + asserted-raw), re-promotes both, runs fresh
flagship total-VaR/ES-total evidence on the demo-mg1 versions, and files the 2 TRIGGERED
closures + 2 INITIAL AWC dossiers. Requires the MG-1 campaign AND the MF-1 extension (run
``scripts/run_demo_campaign.py`` + ``scripts/run_demo_multifamily.py`` first); refuse-not-skip
on this stage's own footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_rs1.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-5 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoRs1AlreadySeededError,
        DemoRs1PrereqError,
        run_demo_rs1_stage5,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_rs1_stage5(session)
            session.commit()
        except (DemoRs1AlreadySeededError, DemoRs1PrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("RS-1 stage-5 demo COMPLETE")
    print(f"  tenant:            {summary.tenant_id}")
    print(f"  EWMA version:      {summary.ewma_version_id}")
    print(f"  shrinkage version: {summary.shrinkage_version_id}")
    print(
        f"  MF-EQ-A residual:  raw {summary.raw_residual_stdev} -> shrunk "
        f"{summary.shrunk_residual_stdev}"
    )
    print(f"  MF-EQ-B residual:  EWMA {summary.ewma_residual_stdev}")
    print(
        f"  evidence runs:     total-VaR {summary.total_var_run_id} / ES-total "
        f"{summary.es_total_run_id}"
    )
    print(
        f"  filed:             {summary.triggered_filed} TRIGGERED + "
        f"{summary.initials_filed} INITIAL"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
