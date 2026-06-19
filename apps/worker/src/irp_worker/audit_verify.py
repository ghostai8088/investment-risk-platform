"""Audit-chain verification ops CLI (BR-12, BR-18; CTRL-026).

Runs ``verify_all_chains`` against the configured database and reports per-tenant chain
integrity; exit code 1 if any chain is broken. ``--checkpoint`` writes a checkpoint per
healthy chain. This is an ops job/CLI, not an HTTP endpoint.

Usage:
    python -m irp_worker.audit_verify [--database-url URL] [--checkpoint]
"""

from __future__ import annotations

import argparse
import os
import sys

from irp_shared.audit.service import verify_all_chains
from irp_shared.db.session import make_engine, make_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify audit hash chains for all tenants.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy database URL (defaults to $DATABASE_URL).",
    )
    parser.add_argument(
        "--checkpoint",
        action="store_true",
        help="Write a checkpoint per healthy chain.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("error: no database URL (set --database-url or $DATABASE_URL)", file=sys.stderr)
        return 2

    engine = make_engine(args.database_url)
    session = make_session_factory(engine)()
    try:
        reports = verify_all_chains(session, create_checkpoints=args.checkpoint)
        if args.checkpoint:
            session.commit()
    finally:
        session.close()
        engine.dispose()

    broken = [r for r in reports if not r.result.ok]
    for report in reports:
        if report.result.ok:
            status = "OK"
        else:
            status = f"BROKEN@{report.result.broken_sequence_no} ({report.result.reason})"
        checkpoint = (
            f" checkpoint@{report.checkpoint_sequence_no}"
            if report.checkpoint_sequence_no is not None
            else ""
        )
        print(
            f"chain {report.chain_id}: {status} ({report.result.events_checked} events){checkpoint}"
        )
    print(f"summary: {len(reports)} chains, {len(broken)} broken")
    return 1 if broken else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
