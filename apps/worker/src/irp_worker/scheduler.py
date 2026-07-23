"""SCH-1 worker scheduler — the per-tenant poll loop (Wave-11 slice 1).

Under OQ-SCH-1-1=B (infra-driven per-tenant dispatch) the deploy layer invokes the worker once per
tenant; the whole poll+dispatch runs inside ONE tenant's NON-BYPASSRLS ``run_in_tenant`` context.
The app never reads cross-tenant and never uses the BYPASSRLS ops role — the standing "no BYPASSRLS
business path" doctrine is preserved (Option A, an in-app cross-tenant ops read, was REJECTED at
ratification).

Per-schedule error isolation (the verifier fold): each ``dispatch_one`` runs in its OWN SAVEPOINT so
a unique-violation dedup or a per-schedule failure rolls back only THAT schedule's phantom work —
one schedule's collision never starves the tenant's other due schedules.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from irp_shared.db.mixins import utcnow
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import run_in_tenant
from irp_shared.scheduling.events import (
    OUTCOME_FAILED,
    OUTCOME_SKIPPED_DUPLICATE,
)
from irp_shared.scheduling.service import (
    dispatch_one,
    record_failed_dispatch,
    select_active_due,
)


def poll_tenant_schedules(
    session: Session, now: datetime, *, code_version: str
) -> list[tuple[str, str]]:
    """Fire every due schedule for the current tenant; return ``(schedule_id, outcome)`` pairs.

    Each schedule dispatches in its own SAVEPOINT: a concurrent unique-violation is swallowed as
    ``SKIPPED_DUPLICATE`` (the losing SAVEPOINT rolls back its phantom governed run); any other
    per-schedule failure is recorded as a FAILED ledger row (record + continue, OD-SCH-1-J) and the
    loop moves on. The tenant session commit happens once, in ``run_in_tenant``.
    """
    results: list[tuple[str, str]] = []
    for schedule, tick in select_active_due(session, now):
        savepoint = session.begin_nested()
        try:
            row = dispatch_one(session, schedule, tick, now, code_version=code_version)
            savepoint.commit()
            results.append((schedule.id, row.outcome))
            continue
        except IntegrityError:
            # A concurrent poll already fired this (schedule, tick) — benign dedup.
            savepoint.rollback()
            results.append((schedule.id, OUTCOME_SKIPPED_DUPLICATE))
            continue
        except Exception as exc:  # noqa: BLE001 - fail-closed per-schedule isolation
            savepoint.rollback()
            reason = f"{type(exc).__name__}: {exc}"

        # Record a FAILED ledger row in a fresh SAVEPOINT (pre-create refusal etc.).
        failed_sp = session.begin_nested()
        try:
            record_failed_dispatch(session, schedule, tick, now, reason=reason)
            failed_sp.commit()
            results.append((schedule.id, OUTCOME_FAILED))
        except IntegrityError:
            # A concurrent poll occupied this tick between our rollback and insert.
            failed_sp.rollback()
            results.append((schedule.id, OUTCOME_SKIPPED_DUPLICATE))
    return results


def run_scheduler_for_tenant(
    session_factory: sessionmaker[Session],
    tenant_id: str,
    *,
    code_version: str,
    now: datetime | None = None,
) -> list[tuple[str, str]]:
    """Run one scheduler tick for ONE tenant under tenant-scoped RLS, then commit.

    ``now`` defaults to the canonical UTC wall clock; only this top-level entry reads it (the
    due-computation itself is a pure function of the injected ``now`` — INV-SCH-1).
    """
    tick_now = now if now is not None else utcnow()
    return run_in_tenant(
        session_factory,
        tenant_id,
        lambda session: poll_tenant_schedules(session, tick_now, code_version=code_version),
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin entrypoint
    """CLI entry — infra invokes this once per tenant (OQ-SCH-1-1=B).

    Runs a single scheduler tick for ``--tenant`` under the ordinary (non-BYPASSRLS) app role. It is
    deliberately NOT a cross-tenant sweep: the app has no tenant registry and no ops-role read here.
    """
    parser = argparse.ArgumentParser(description="Run one scheduler tick for one tenant.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--tenant", default=os.environ.get("IRP_TENANT_ID"))
    parser.add_argument(
        "--code-version", default=os.environ.get("IRP_CODE_VERSION", "irp-worker")
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        print("error: no database URL (set --database-url or $DATABASE_URL)", file=sys.stderr)
        return 2
    if not args.tenant:
        print("error: no tenant (set --tenant or $IRP_TENANT_ID)", file=sys.stderr)
        return 2

    engine = make_engine(args.database_url)
    factory = make_session_factory(engine)
    try:
        results = run_scheduler_for_tenant(
            factory, args.tenant, code_version=args.code_version
        )
    finally:
        engine.dispose()
    print(f"irp-scheduler: tenant={args.tenant} fired={len(results)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
