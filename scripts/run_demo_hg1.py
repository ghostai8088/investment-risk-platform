"""Run the HG-1 stage-3 demo (OD-HG-1-D) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_hg1_private`: the genuinely-private alpha=0.4 chain
on multi-family factors. Requires BOTH prior stages (run ``scripts/run_demo_campaign.py`` then
``scripts/run_demo_multifamily.py``); refuse-not-skip on this stage's own footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_hg1.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-3 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoHg1AlreadySeededError,
        DemoHg1PrereqError,
        run_demo_hg1_private,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_hg1_private(session)
            session.commit()
        except (DemoHg1AlreadySeededError, DemoHg1PrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("HG-1 stage-3 demo COMPLETE")
    print(f"  tenant:            {summary.tenant_id}")
    print(f"  instrument:        {summary.instrument_id}")
    print(f"  desmooth -> est:   {summary.desmoothed_run_id} -> {summary.estimate_run_id}")
    print(f"  promoted loadings: {summary.promoted_loadings}")
    print(f"  minted returns:    {summary.minted_return_rows}")
    print(f"  loadings run:      {summary.loadings_run_id}")
    print(f"  covariance run:    {summary.covariance_run_id}")
    for code, run_id in sorted(summary.flagship_run_ids.items()):
        print(f"  evidence {code}: {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
