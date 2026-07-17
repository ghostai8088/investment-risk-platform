"""Run the ES-HS-1 stage-4 demo (OD-ES-HS-1-F) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_eshs_stage4`: the 18th registered code
(``risk.var.historical_es``), the flagship empirical-ES run on the SHARED snapshot of the
flagship historical-VaR forecast, the TIER_1 assignment, and the INITIAL AWC dossier. Requires
the MG-1 campaign (run ``scripts/run_demo_campaign.py`` first; stages 2-3 are independent of
this stage but the full living tenant runs all four in order); refuse-not-skip on this stage's
own footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_eshs.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-4 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoEshsAlreadySeededError,
        DemoEshsPrereqError,
        run_demo_eshs_stage4,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_eshs_stage4(session)
            session.commit()
        except (DemoEshsAlreadySeededError, DemoEshsPrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("ES-HS-1 stage-4 demo COMPLETE")
    print(f"  tenant:           {summary.tenant_id}")
    print(f"  model version:    {summary.model_version_id} (tier {summary.tier})")
    print(f"  es run:           {summary.es_run_id}")
    print(f"  shared snapshot:  {summary.shared_snapshot_id}")
    print(f"  ES vs paired VaR: {summary.es_value} >= {summary.paired_var_value}")
    print(f"  initials filed:   {summary.initials_filed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
