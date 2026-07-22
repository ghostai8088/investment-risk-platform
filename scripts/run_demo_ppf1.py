"""Run the PPF-1 stage-11 demo (OD-PPF-1-F) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_ppf1_stage11`: registers
``risk.factor_return.pure_private`` v1, and per seeded PRIVATE segment (PE-HARBOR-IV /
PC-BRIDGEWATER-II) creates the segment factor + a weight-1 MANUAL membership row and runs the
pooled pure-private factor return over the already-seeded desmoothing + REGRESSION-blend substrate
(ZERO new book data), then files the INITIAL AWC. The GOVERNED-NUMBER contrast with stage 10's
runs-only: the counts MOVE (20/35/101 -> 21/36/103). Requires the campaign + HG-1; refuse-not-skip
on this stage's own footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_ppf1.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-11 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoPpf1AlreadySeededError,
        DemoPpf1PrereqError,
        run_demo_ppf1_stage11,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_ppf1_stage11(session)
            session.commit()
        except (DemoPpf1AlreadySeededError, DemoPpf1PrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("PPF-1 stage-11 demo COMPLETE")
    print(f"  tenant:        {summary.tenant_id}")
    print(f"  model:         {summary.pure_private_model_version_id}")
    print("  model code:    risk.factor_return.pure_private v1")
    print(f"  runs:          {len(summary.run_ids)} pooled pure-private factor returns")
    print(f"  segments:      {', '.join(summary.segment_factor_ids)}")
    print(f"  period rows:   {summary.total_period_rows} total")
    print(f"  INITIAL AWC:   {summary.initials_filed} filed")
    print("  counts:        21 codes / 36 records / 103 runs — MOVED (the 18th governed number)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
