"""CLI shim: seed demo stage 7 (BT-3 — the ES backtest + the Christoffersen leg) into the
durable demo tenant. Usage: DATABASE_URL=... python scripts/run_demo_bt3.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "shared-python", "src")
)

from irp_shared.db.session import make_engine, make_session_factory  # noqa: E402
from irp_shared.demo.bt3_stage7 import run_demo_bt3_stage7  # noqa: E402


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        summary = run_demo_bt3_stage7(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
    print("demo stage 7 (BT-3) seeded:")
    print(f"  es-backtest run:    {summary.es_backtest_run_id}")
    print(f"  christoffersen run: {summary.christoffersen_run_id}")
    print(f"  pairs/exceptions:   {summary.n_pairs}/{summary.n_exceptions}")
    print(f"  Z2 (off-domain):    {summary.z2_value} decision={summary.z2_decision}")
    print(f"  Z1:                 {summary.z1_value}")
    print(f"  LR_IND/LR_CC:       {summary.lr_ind_decision}/{summary.lr_cc_decision}")
    print(f"  initials filed:     {summary.initials_filed} (NO TRIGGERED - recorded)")


if __name__ == "__main__":
    main()
