"""Run the CC-2 stage-9 demo (OD-CC-2-G) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_cc2_stage9`: captures the 11.2M NAV mark for
PE-MERIDIAN-X, registers ``pacing.commitment_projection`` v1 with the PE-shaped declared
parameters, builds the PACING_INPUT snapshot on the stage-8 pair, runs the FUTURE-ONLY
projection through the governed-run scaffold, and files the INITIAL AWC. The GOVERNED contrast
with stage 8's capture-only: the counts MOVE (20 codes / 35 validation records / 96 runs).
Requires the CC-1 stage-8 capture (+ the MG-1 campaign); refuse-not-skip on this stage's own
footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_cc2.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-9 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoCc2AlreadySeededError,
        DemoCc2PrereqError,
        run_demo_cc2_stage9,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_cc2_stage9(session)
            session.commit()
        except (DemoCc2AlreadySeededError, DemoCc2PrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("CC-2 stage-9 demo COMPLETE")
    print(f"  tenant:        {summary.tenant_id}")
    print(f"  pacing model:  {summary.pacing_model_version_id} (pacing.commitment_projection v1)")
    print(
        f"  projection:    run {summary.projection_run_id} -> {summary.n_periods} future periods "
        f"(ages {summary.first_period_index}..{summary.last_period_index})"
    )
    print(f"  INITIAL AWC:   {summary.initials_filed} filed (CC2_PACING_INITIAL)")
    print("  counts:        20 codes / 35 validation records / 96 runs — MOVED (governed number)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
