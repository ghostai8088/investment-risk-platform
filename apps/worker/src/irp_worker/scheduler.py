"""SCH-1 worker scheduler — the per-tenant poll loop (Wave-11 slice 1).

Under OQ-SCH-1-1=B (infra-driven per-tenant dispatch) the deploy layer invokes the worker once per
tenant; the whole poll+dispatch runs inside ONE tenant's NON-BYPASSRLS app-role session
(``persistent_tenant_context`` — re-armed per transaction since the API-2b P1 restructure).
The app never reads cross-tenant and never uses the BYPASSRLS ops role — the standing "no BYPASSRLS
business path" doctrine is preserved (Option A, an in-app cross-tenant ops read, was REJECTED at
ratification).

Per-schedule error isolation (the verifier fold): each ``dispatch_one`` runs in its OWN SAVEPOINT so
a unique-violation dedup or a per-schedule failure rolls back only THAT schedule's phantom work —
one schedule's collision never starves the tenant's other due schedules. The failure-recording path
is FULLY catch-all: nothing escapes the per-schedule handler, so the phases-1–2 terminal
commit always durably lands every successful sibling dispatch.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from irp_shared.db.mixins import utcnow
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.scheduling.events import (
    OUTCOME_FAILED,
    OUTCOME_SKIPPED_DUPLICATE,
)
from irp_shared.scheduling.service import (
    dispatch_one,
    record_failed_dispatch,
    select_active_due,
)
from irp_worker.breaches import poll_tenant_breaches
from irp_worker.deadlines import poll_tenant_breach_deadlines
from irp_worker.notifications import poll_tenant_notifications
from irp_worker.tenants import TenantIdError, canonical_tenant_id

log = logging.getLogger(__name__)

#: A worker-level REPORTING value (never a ``scheduled_run.outcome`` — no row carries it): the
#: recording path itself failed, so NOTHING was written and the tick stays un-fired and retryable.
#: Distinct from ``OUTCOME_FAILED``, which means FAILED evidence was durably recorded and the tick
#: bucket is permanently occupied — at a monthly cadence that is the difference between a retry
#: next poll and a lost month (SCH-2).
OUTCOME_UNRECORDED = "UNRECORDED"

#: The unique constraint that backstops the per-(schedule, tick) idempotency race. ONLY a violation
#: of THIS constraint is the benign concurrent-double-fire dedup; any OTHER IntegrityError from the
#: governed-run stack is a real defect that must be recorded as FAILED evidence, not masked.
_TICK_DEDUP_CONSTRAINT = "uq_scheduled_run_schedule_tick"
#: CAL-1b (OQ-CAL-1-5): the MONTH-grain partial unique for BUSINESS_MONTH_END rows — its OWN key
#: in this classifier (the LIM-2 own-keys lesson: a registry/error-map entry the code path can
#: reach needs its own key, or the collision surfaces as an opaque FAILED row instead of a benign
#: SKIPPED_DUPLICATE). PG reports the violated unique INDEX's name in diag.constraint_name.
_PERIOD_DEDUP_CONSTRAINT = "uq_scheduled_run_schedule_period"


def _is_tick_dedup(exc: IntegrityError) -> bool:
    """True only when ``exc`` is the ``(schedule, tick)`` unique-constraint race (SQLSTATE 23505 on
    ``uq_scheduled_run_schedule_tick``), NOT some other governed-write constraint violation. Checks
    the psycopg ``diag.constraint_name`` (PG) and falls back to the constraint name in the message
    (SQLite/other drivers expose it only in the text)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    if getattr(diag, "constraint_name", None) in (_TICK_DEDUP_CONSTRAINT, _PERIOD_DEDUP_CONSTRAINT):
        return True
    # The string fallback serves PG-like drivers without diag only — SQLite reports COLUMN
    # names, never constraint/index names, so on the unit tier this is dead code and the benign
    # classification arrives via _record_failed's IntegrityError catch (the CAL-1b review LOW).
    return _TICK_DEDUP_CONSTRAINT in str(exc) or _PERIOD_DEDUP_CONSTRAINT in str(exc)


def poll_tenant_schedules(
    session: Session, now: datetime, *, code_version: str, acting_tenant: str
) -> list[tuple[str, str]]:
    """Fire every due schedule for the current tenant; return ``(schedule_id, outcome)`` pairs.

    Each schedule dispatches in its own SAVEPOINT: a concurrent unique-violation on the
    ``(schedule, tick)`` constraint is swallowed as ``SKIPPED_DUPLICATE`` (the loser SAVEPOINT rolls
    back its phantom governed run); ANY OTHER failure — including a non-dedup constraint violation
    from the governed-run stack — is recorded as a FAILED ledger row (record + continue, OD-SCH-1-J)
    so it is never masked and never hot-loops. The failure-recording path is itself catch-all, so
    nothing escapes to abort the phases-1–2 terminal commit.
    """
    results: list[tuple[str, str]] = []
    for schedule, tick, holidays in select_active_due(session, now, acting_tenant=acting_tenant):
        savepoint = session.begin_nested()
        try:
            row = dispatch_one(
                session, schedule, tick, now, code_version=code_version, holidays=holidays
            )
            savepoint.commit()
            results.append((schedule.id, row.outcome))
            continue
        except IntegrityError as exc:
            savepoint.rollback()
            if _is_tick_dedup(exc):
                # A concurrent poll already fired this (schedule, tick) — benign dedup.
                results.append((schedule.id, OUTCOME_SKIPPED_DUPLICATE))
                continue
            # A REAL governed-write constraint violation — record FAILED evidence, do not mask.
            reason = f"IntegrityError: {exc}"
        except Exception as exc:  # noqa: BLE001 - fail-closed per-schedule isolation
            savepoint.rollback()
            reason = f"{type(exc).__name__}: {exc}"

        results.append(
            (schedule.id, _record_failed(session, schedule, tick, now, reason, holidays=holidays))
        )
    return results


def _record_failed(
    session: Session,
    schedule: Any,
    tick: datetime,
    now: datetime,
    reason: str,
    holidays: frozenset[date] | None = None,
) -> str:
    """Append a FAILED ledger row in a fresh SAVEPOINT; FULLY catch-all so a failure in recording
    path itself cannot escape and unwind the tenant's other successful dispatches (the starvation
    fold). If even the record fails, the tick simply stays un-fired and retries next poll."""
    failed_sp = session.begin_nested()
    try:
        record_failed_dispatch(session, schedule, tick, now, reason=reason, holidays=holidays)
        failed_sp.commit()
        return OUTCOME_FAILED
    except IntegrityError as exc:
        # A concurrent poll occupied this tick/period between our rollback and insert — benign.
        # Logged because this catch is NAME-BLIND: a genuinely non-dedup violation would also
        # land here (visible in the log, not silently swallowed — the CAL-1b review LOW).
        log.info("FAILED-row insert classified duplicate for schedule %s: %s", schedule.id, exc)
        failed_sp.rollback()
        return OUTCOME_SKIPPED_DUPLICATE
    except Exception:  # noqa: BLE001 - the recording path must never starve sibling schedules
        # SCH-2: distinguish "recorded FAILED evidence" from "could not even record it". The former
        # durably occupies the tick bucket; the latter leaves the tick un-fired and retryable — at
        # a monthly cadence that difference is a month of lost evidence versus a retry next poll,
        # and returning OUTCOME_FAILED for both made them indistinguishable to the caller.
        failed_sp.rollback()
        log.exception("could not record FAILED evidence for schedule %s tick %s", schedule.id, tick)
        return OUTCOME_UNRECORDED


def run_operational_tick_for_tenant(
    session_factory: sessionmaker[Session],
    tenant_id: str,
    *,
    code_version: str,
    now: datetime | None = None,
) -> dict[str, list[Any]]:
    """Run ONE per-tenant operational tick under tenant-scoped RLS, then commit — the single
    per-tenant tick the Fable audit ratified (schedules + breaches + deadlines under ONE
    entrypoint, so operational concerns never accrete separate CLI entrypoints).

    **Ordering INVARIANT (OD-LIM-1-G), restated family-specifically at SCH-2:** phase 1 (schedules)
    runs BEFORE phase 2 (breaches) because a dispatched **VaR** fire runs its binder inline, so it
    reaches a COMPLETED run visible to the breach evaluation in the SAME transaction (same-tick
    detection). The rationale is about the VaR family, not about scheduling in general: SCH-2's
    second family (``EXPOSURE_AGGREGATE``) has no phase-2 consumer — LIM-1's ``_METRIC_MAP`` keys
    only on VaR/active-risk run types — so admitting it neither strengthens nor breaks the ordering.
    Reversing the order stays correct but adds one tick of breach latency; all phases land under the
    single terminal commit.

    **Phase 3 (breach deadlines, MG-2)** auto-escalates overdue breaches. A breach DETECTED this
    tick has no ``response_due`` (stamped only at the human ASSIGN, never in a tick), so it is never
    same-tick escalatable; phase 3 only ever acts on breaches ASSIGNED in a prior committed request.

    **Phase 4 (breach notification, NOTIF-1)** runs LAST — it consumes the ``BREACH.DETECT``/
    ``BREACH.ESCALATE`` audit events that phases 2-3 just committed (so a same-tick DETECT is
    alerted this tick), appending durable ``breach_notification`` rows per (event, recipient). Like
    phase 3 it runs as per-item (per-event) top-level transactions after the phases-1–2 commit.

    **Commit topology (OD-LIM-1-G as RE-RATIFIED at API-2b OQ-3=A — the B-F1 deadlock fix):**
    phases 1–2 land under ONE terminal commit (unchanged internally — SAVEPOINT-per-item); phase 3
    then runs as PER-BREACH TOP-LEVEL transactions. Rationale: the frozen ``record_event`` takes the
    per-tenant audit-chain ADVISORY lock, held to top-level commit — a single-transaction tick held
    it across phase 3's breach ROW locks while every HTTP breach verb acquires row→advisory, an
    order inversion = a reachable tick×HTTP (and tick×tick) deadlock. Splitting phase 3 off removes
    the breach-row leg of that cycle. HONEST RESIDUAL (Wave-12 close): phases 1–2 are NOT lock-free
    — a new-breach INSERT takes FK ``FOR KEY SHARE`` on the parent ``limit_definition`` row, so
    with the advisory already held from an earlier same-transaction emit, a concurrent limit verb
    (``FOR UPDATE`` then advisory) can still close a 40P01 cycle. Both sides treat it as transient:
    the tick's per-limit SAVEPOINT recovers and retries next tick; every write router maps 40P01 →
    503 + Retry-After (``deadlock_503``). Phases 1–2 can also tuple-wait on unique-index entries —
    made order-deterministic via ORDER BY id in the phase selectors, and SAVEPOINT-recovered.
    ``persistent_tenant_context`` is LOAD-BEARING here: the RLS GUC is transaction-local
    and clears at COMMIT — without the re-arm listener, phase 3 would run RLS-unarmed and silently
    escalate NOTHING (the OQ-a fail-open pattern; the API-2b verifier's blocking fold).

    ``now`` defaults to the canonical UTC wall clock; only this top-level entry reads it (the
    due/breach computation is a pure function of the injected ``now`` — INV-SCH-1).
    """
    # Defense-in-depth (L4): the boundary entrypoints already canonicalize, but this shared,
    # importable unit arms the RLS GUC from ``tenant_id`` — canonicalize here too so a future direct
    # caller can never arm RLS from a non-canonical string (the SSO-1 silent RLS-hide fail-open).
    tenant_id = canonical_tenant_id(tenant_id)
    tick_now = now if now is not None else utcnow()
    session = session_factory()
    try:
        detach = persistent_tenant_context(session, tenant_id)
        try:
            scheduled = poll_tenant_schedules(
                session, tick_now, code_version=code_version, acting_tenant=tenant_id
            )
            breached = poll_tenant_breaches(session, tick_now, acting_tenant=tenant_id)
            session.commit()  # the phases-1–2 terminal commit (releases the advisory lock)
            escalated = poll_tenant_breach_deadlines(session, tick_now, acting_tenant=tenant_id)
            # Phase 4 (NOTIF-1): notify unnotified alarm events — runs LAST because it consumes the
            # BREACH.DETECT/ESCALATE audit events that phases 2-3 just committed (same tick).
            notified = poll_tenant_notifications(session, tick_now, acting_tenant=tenant_id)
            return {
                "scheduled": scheduled,
                "breached": breached,
                "escalated": escalated,
                "notified": notified,
            }
        finally:
            detach()
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin entrypoint
    """CLI entry — infra invokes this once per tenant (OQ-SCH-1-1=B).

    Runs a single OPERATIONAL tick for ``--tenant`` (schedules + breaches + deadlines) under the
    ordinary
    (non-BYPASSRLS) app role. Deliberately NOT a cross-tenant sweep: the app has no tenant registry
    and no ops-role read here.
    """
    parser = argparse.ArgumentParser(description="Run one operational tick for one tenant.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--tenant", default=os.environ.get("IRP_TENANT_ID"))
    parser.add_argument("--code-version", default=os.environ.get("IRP_CODE_VERSION", "irp-worker"))
    args = parser.parse_args(argv)
    if not args.database_url:
        print("error: no database URL (set --database-url or $DATABASE_URL)", file=sys.stderr)
        return 2
    if not args.tenant:
        print("error: no tenant (set --tenant or $IRP_TENANT_ID)", file=sys.stderr)
        return 2
    # OQ-a fail-open fix: canonicalize the tenant id BEFORE it arms the RLS GUC. A non-canonical
    # UUID would silently RLS-hide every row and make the tick do nothing (SSO-1's second instance);
    # a non-UUID fails CLOSED here (exit 2), never arming RLS from an uncanonicalizable string.
    try:
        tenant = canonical_tenant_id(args.tenant)
    except TenantIdError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    engine = make_engine(args.database_url)
    factory = make_session_factory(engine)
    try:
        results = run_operational_tick_for_tenant(factory, tenant, code_version=args.code_version)
    finally:
        engine.dispose()
    n_sched = len(results["scheduled"])
    n_breach = sum(1 for _limit_id, breach_id in results["breached"] if breach_id is not None)
    n_escalated = len(results["escalated"])
    n_notified = len(results["notified"])
    print(
        f"irp-worker: tenant={tenant} fired={n_sched} "
        f"breaches={n_breach} escalated={n_escalated} notified={n_notified}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
