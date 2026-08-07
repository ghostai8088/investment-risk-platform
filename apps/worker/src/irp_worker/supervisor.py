"""CAD-1 supervisor — the cadence driver that finally turns the per-tenant operational tick.

Wave-11 built ``run_operational_tick_for_tenant`` (schedules → breaches → deadlines → notification);
CAD-1 (Wave-12 slice 3, OQ-1=A) adds the in-process supervisor that invokes it on a real cadence,
retiring the ``irp_worker.main`` heartbeat placeholder. Every ``IRP_TICK_INTERVAL_SECONDS`` the
supervisor ticks each **configured** tenant (``IRP_TENANT_IDS`` — OQ-2=A: config, NOT a DB sweep, so
the app never reads cross-tenant and never uses the BYPASSRLS ops role; the ratified OQ-SCH-1-1=B
doctrine is intact). Each tick opens its OWN non-BYPASSRLS session under forced RLS.

Fault model:
- **Per-tenant isolation** — one tenant's tick raising is logged and never halts the cycle or
  starves the other tenants (mirrors the per-schedule isolation inside the tick).
- **Malformed tenant id** (OQ-3=A) — skipped with a logged error, the valid tenants keep ticking.
- **Empty tenant list** (FOLD-2) — fail CLOSED at startup: a silently-idle engine is the exact
  failure this slice exists to prevent, so an empty ``IRP_TENANT_IDS`` refuses to start.

The one-shot ``irp_worker.scheduler --tenant`` entrypoint is retained (OQ-1=A) for an external
scheduler (k8s CronJob / cloud scheduler / host cron) that prefers once-per-tenant invocation.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from irp_shared.db.session import make_engine, make_session_factory
from irp_worker.scheduler import run_operational_tick_for_tenant
from irp_worker.tenants import parse_tenant_ids

log = logging.getLogger("irp_worker.supervisor")

#: Default cadence if ``IRP_TICK_INTERVAL_SECONDS`` is unset. 300s (5 min) is a sane operational
#: default; the demo/compose env can shorten it for visibility.
_DEFAULT_INTERVAL_SECONDS = 300

#: After this many CONSECUTIVE failed cycles for one tenant, escalate the log from per-cycle ERROR
#: to a distinct WARNING that names the streak — so a tenant stuck in a permanent, evidence-free
#: no-work state (M2: the supervisor level records no durable FAILED row, unlike dispatch) is
#: observable rather than lost in per-cycle log spam.
_FAILURE_STREAK_ALERT = 3

TickFn = Callable[..., dict[str, list[Any]]]


class SupervisorConfigError(ValueError):
    """A supervisor misconfiguration that must fail closed at startup (e.g. no tenants)."""


def run_tick_cycle(
    session_factory: sessionmaker[Session],
    tenant_ids: list[str],
    *,
    code_version: str,
    run_tick: TickFn = run_operational_tick_for_tenant,
) -> dict[str, dict[str, list[Any]] | None]:
    """Run ONE operational tick for every configured tenant, in order, with per-tenant isolation.

    Returns ``{tenant_id: tick_result}`` — the result is ``None`` for a tenant whose tick raised
    (logged, never re-raised). ``now`` is intentionally NOT passed: each tick reads the canonical
    ``utcnow()`` itself, so a slow cycle does not smear every tenant onto one frozen instant.
    """
    summary: dict[str, dict[str, list[Any]] | None] = {}
    for tenant_id in tenant_ids:
        try:
            result = run_tick(session_factory, tenant_id, code_version=code_version)
        except Exception:  # noqa: BLE001 - per-tenant isolation: one tenant never starves the rest
            log.exception("tick FAILED for tenant=%s (isolated; continuing)", tenant_id)
            summary[tenant_id] = None
            continue
        # Record + log OUTSIDE the isolation try (L3): a book-keeping/formatting error here must
        # never convert an already-committed successful tick into a reported failure.
        summary[tenant_id] = result
        log.info(
            "tick tenant=%s fired=%d breaches=%d escalated=%d notified=%d repro_alarmed=%d",
            tenant_id,
            len(result["scheduled"]),
            sum(1 for _lim, breach_id in result["breached"] if breach_id is not None),
            len(result["escalated"]),
            len(result["notified"]),
            # REPRO-1's phase 5. `.get` rather than `[...]`: this log line is book-keeping OUTSIDE
            # the per-tenant isolation try, and a KeyError here would turn an already-committed
            # successful tick into a reported failure (the L3 rule this block already carries).
            len(result.get("repro_alarmed", ())),
        )
    return summary


def run_supervisor(
    session_factory: sessionmaker[Session],
    tenant_ids: list[str],
    *,
    interval_seconds: int,
    code_version: str,
    sleep: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
    run_tick: TickFn = run_operational_tick_for_tenant,
) -> int:
    """Loop: tick every tenant, sleep ``interval_seconds``, repeat. Fail closed on an empty list.

    ``max_cycles`` (test seam) bounds the loop; ``None`` runs forever. ``sleep`` is injectable so
    unit tests drive the cadence without real waits. Returns the number of cycles run.
    """
    if not tenant_ids:
        raise SupervisorConfigError(
            "no tenants configured (IRP_TENANT_IDS is empty) — refusing to start a silently-idle "
            "engine"
        )
    log.info(
        "supervisor start: %d tenant(s), interval=%ds, code_version=%s",
        len(tenant_ids),
        interval_seconds,
        code_version,
    )
    cycles = 0
    streaks: dict[str, int] = dict.fromkeys(tenant_ids, 0)
    while True:
        summary = run_tick_cycle(
            session_factory, tenant_ids, code_version=code_version, run_tick=run_tick
        )
        _update_failure_streaks(streaks, summary)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return cycles
        sleep(interval_seconds)


def _update_failure_streaks(
    streaks: dict[str, int], summary: dict[str, dict[str, list[Any]] | None]
) -> None:
    """Track CONSECUTIVE per-tenant tick failures across cycles and escalate the log once a tenant
    crosses ``_FAILURE_STREAK_ALERT`` (M2 observability: the supervisor level leaves no durable
    FAILED evidence, so a tenant stuck failing every cycle would otherwise be invisible beyond
    per-cycle spam). A success resets the streak."""
    for tenant_id, result in summary.items():
        if result is None:
            streaks[tenant_id] = streaks.get(tenant_id, 0) + 1
            if streaks[tenant_id] >= _FAILURE_STREAK_ALERT:
                log.warning(
                    "tenant=%s has failed %d consecutive ticks — no governed work landing for it",
                    tenant_id,
                    streaks[tenant_id],
                )
        else:
            streaks[tenant_id] = 0


def _interval_from_env(raw: str | None) -> int:
    """Parse ``IRP_TICK_INTERVAL_SECONDS`` → a positive int; fall back to the default; fail closed
    on a non-positive or non-numeric value (a zero-interval hot loop is a misconfiguration)."""
    if raw is None or not raw.strip():
        return _DEFAULT_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise SupervisorConfigError(
            f"IRP_TICK_INTERVAL_SECONDS is not an integer: {raw!r}"
        ) from exc
    if value <= 0:
        raise SupervisorConfigError(f"IRP_TICK_INTERVAL_SECONDS must be positive: {value}")
    return value


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin env-driven entrypoint
    """Env-driven supervisor entrypoint (the worker container CMD).

    Config: ``DATABASE_URL``, ``IRP_TENANT_IDS`` (comma-separated), ``IRP_TICK_INTERVAL_SECONDS``
    (default 300), ``IRP_CODE_VERSION`` (default ``irp-worker``). Tenant ids are canonicalized and
    a malformed entry is skipped with a logged error (OQ-3=A); an empty resulting list fails closed.
    """
    logging.basicConfig(level=os.environ.get("IRP_LOG_LEVEL", "INFO"))
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("error: no database URL (set $DATABASE_URL)", file=sys.stderr)
        return 2

    def _log_bad(entry: str, exc: Exception) -> None:
        log.error("skipping malformed tenant id %r: %s", entry, exc)

    tenant_ids = parse_tenant_ids(os.environ.get("IRP_TENANT_IDS"), on_bad=_log_bad)
    if not tenant_ids:
        print(
            "error: no valid tenants (set $IRP_TENANT_IDS to a comma-separated list of tenant "
            "UUIDs)",
            file=sys.stderr,
        )
        return 2

    interval_seconds = _interval_from_env(os.environ.get("IRP_TICK_INTERVAL_SECONDS"))
    code_version = os.environ.get("IRP_CODE_VERSION", "irp-worker")

    engine = make_engine(database_url)
    factory = make_session_factory(engine)
    try:
        run_supervisor(
            factory,
            tenant_ids,
            interval_seconds=interval_seconds,
            code_version=code_version,
        )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
