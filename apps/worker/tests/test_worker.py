"""CAD-1 supervisor + tenant-canonicalization unit tests.

Pure/unit tier: the operational tick itself is faked (injected ``run_tick``) so these tests exercise
the supervisor's fault model — per-tenant isolation, the cadence loop, empty/malformed tenant
handling — without a DB. The real tick chain is covered in the PG/scheduler-dispatch tiers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from irp_worker.scheduler import main as scheduler_main
from irp_worker.scheduler import run_operational_tick_for_tenant
from irp_worker.supervisor import (
    _FAILURE_STREAK_ALERT,
    SupervisorConfigError,
    _interval_from_env,
    _update_failure_streaks,
    run_supervisor,
    run_tick_cycle,
)
from irp_worker.supervisor import main as supervisor_main
from irp_worker.tenants import TenantIdError, canonical_tenant_id, parse_tenant_ids

_A = str(uuid.uuid4())
_B = str(uuid.uuid4())


def _ok_tick(*_args: object, **_kwargs: object) -> dict[str, list[object]]:
    """A stand-in for ``run_operational_tick_for_tenant`` that always succeeds with empty work."""
    return {"scheduled": [], "breached": [], "escalated": [], "notified": []}


# --------------------------------------------------------------------- tenant canonicalization ---
def test_canonical_tenant_id_lowercases_and_strips_braces() -> None:
    raw = "{" + _A.upper() + "}"
    assert canonical_tenant_id(raw) == _A  # canonical == lowercase-hyphenated, no braces


def test_canonical_tenant_id_rejects_non_uuid() -> None:
    with pytest.raises(TenantIdError):
        canonical_tenant_id("not-a-uuid")


def test_parse_tenant_ids_skips_blanks_and_dedupes_preserving_order() -> None:
    raw = f" {_A} , , {_B} , {_A.upper()} "  # trailing dup (different case) is de-duplicated
    assert parse_tenant_ids(raw) == [_A, _B]


def test_parse_tenant_ids_skips_malformed_and_reports_it() -> None:
    bad: list[str] = []
    result = parse_tenant_ids(f"{_A},garbage,{_B}", on_bad=lambda e, _exc: bad.append(e))
    assert result == [_A, _B]  # the valid ones survive (OQ-3=A)
    assert bad == ["garbage"]


def test_parse_tenant_ids_empty_is_empty_list() -> None:
    assert parse_tenant_ids("") == []
    assert parse_tenant_ids(None) == []


# ------------------------------------------------------------------------------- the tick cycle ---
def test_run_tick_cycle_ticks_every_tenant() -> None:
    seen: list[str] = []

    def tick(_factory: object, tenant_id: str, **_k: object) -> dict[str, list[object]]:
        seen.append(tenant_id)
        return _ok_tick()

    summary = run_tick_cycle(None, [_A, _B], code_version="v", run_tick=tick)
    assert seen == [_A, _B]
    assert set(summary) == {_A, _B}


def test_run_tick_cycle_isolates_a_failing_tenant() -> None:
    seen: list[str] = []

    def tick(_factory: object, tenant_id: str, **_k: object) -> dict[str, list[object]]:
        seen.append(tenant_id)
        if tenant_id == _A:
            raise RuntimeError("tenant A DB is down")
        return _ok_tick()

    summary = run_tick_cycle(None, [_A, _B], code_version="v", run_tick=tick)
    assert seen == [_A, _B]  # B still ticked after A raised — isolation
    assert summary[_A] is None  # the failed tenant recorded as None, not re-raised
    assert summary[_B] == _ok_tick()


# ----------------------------------------------------------------------------- the cadence loop ---
def test_run_supervisor_empty_tenant_list_fails_closed() -> None:
    with pytest.raises(SupervisorConfigError):
        run_supervisor(None, [], interval_seconds=1, code_version="v", run_tick=_ok_tick)


def test_run_supervisor_runs_max_cycles_and_sleeps_between_them() -> None:
    ticks: list[str] = []
    sleeps: list[float] = []

    def tick(_factory: object, tenant_id: str, **_k: object) -> dict[str, list[object]]:
        ticks.append(tenant_id)
        return _ok_tick()

    cycles = run_supervisor(
        None,
        [_A, _B],
        interval_seconds=42,
        code_version="v",
        sleep=sleeps.append,
        max_cycles=3,
        run_tick=tick,
    )
    assert cycles == 3
    assert ticks == [_A, _B, _A, _B, _A, _B]  # every tenant, every cycle
    assert sleeps == [42, 42]  # sleeps BETWEEN cycles only — not after the final one


# ------------------------------------------------------------------------------- interval parse ---
def test_interval_from_env_default_and_bounds() -> None:
    assert _interval_from_env(None) == 300
    assert _interval_from_env("") == 300
    assert _interval_from_env("60") == 60
    with pytest.raises(SupervisorConfigError):
        _interval_from_env("0")
    with pytest.raises(SupervisorConfigError):
        _interval_from_env("-5")
    with pytest.raises(SupervisorConfigError):
        _interval_from_env("abc")


# --------------------------------------------------------------- M2: per-tenant failure streak ---
def test_update_failure_streaks_escalates_after_threshold(caplog) -> None:  # type: ignore[no-untyped-def]
    streaks = {_A: 0}
    fail = {_A: None}
    for _ in range(_FAILURE_STREAK_ALERT - 1):
        _update_failure_streaks(streaks, fail)
    assert streaks[_A] == _FAILURE_STREAK_ALERT - 1
    import logging

    with caplog.at_level(logging.WARNING, logger="irp_worker.supervisor"):
        _update_failure_streaks(streaks, fail)  # crosses the threshold → WARNING
    assert streaks[_A] == _FAILURE_STREAK_ALERT
    assert any("consecutive" in r.message for r in caplog.records)
    # a success resets the streak
    _update_failure_streaks(streaks, {_A: _ok_tick()})
    assert streaks[_A] == 0


# ----------------------------------------------------------------------- M1: main() fail-closed ---
def test_scheduler_main_rejects_non_uuid_tenant() -> None:
    # OQ-a: a non-UUID --tenant must fail CLOSED (exit 2) BEFORE any engine/RLS arming.
    assert scheduler_main(["--database-url", "postgresql+psycopg://x/y", "--tenant", "nope"]) == 2


def test_scheduler_main_missing_tenant(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("IRP_TENANT_ID", raising=False)
    assert scheduler_main(["--database-url", "postgresql+psycopg://x/y"]) == 2


def test_scheduler_main_missing_db_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert scheduler_main(["--tenant", _A]) == 2


def test_supervisor_main_missing_db_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert supervisor_main([]) == 2


def test_supervisor_main_empty_tenant_ids_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x/y")
    monkeypatch.setenv("IRP_TENANT_IDS", "")
    assert supervisor_main([]) == 2  # FOLD-2: an empty list is refused, not silently idle


def test_supervisor_main_all_malformed_tenant_ids_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x/y")
    monkeypatch.setenv("IRP_TENANT_IDS", "garbage,also-bad")  # all skipped → empty → fail closed
    assert supervisor_main([]) == 2


# ----------------------------------------------------- L4: defensive tick canonicalization ---
def test_run_operational_tick_rejects_non_uuid_tenant() -> None:
    # The shared tick arms RLS from tenant_id — it canonicalizes defensively and fails closed on a
    # non-UUID BEFORE opening a session (the dummy factory is never called).
    def _boom_factory() -> object:  # pragma: no cover - must not be reached
        raise AssertionError("session factory should not be called for a bad tenant id")

    with pytest.raises(TenantIdError):
        run_operational_tick_for_tenant(_boom_factory, "not-a-uuid", code_version="v")  # type: ignore[arg-type]


# ------------------------------------------- the OUTCOME_UNRECORDED distinction (SCH-2 review) ---
def test_record_failed_reports_unrecorded_when_the_recording_path_itself_fails() -> None:
    """SCH-2 added a THIRD outcome to the worker's reporting vocabulary and shipped it untested.

    The distinction is load-bearing: `FAILED` means the tick bucket is durably occupied and that
    month is BURNED; `UNRECORDED` means the tick was never fired at all and the NEXT poll retries
    it. Returning `FAILED` for both — which is what the code did before — makes a recoverable
    outage indistinguishable from a lost month at the only surface an operator sees.

    Driven by making `record_failed_dispatch` raise a non-Integrity error, the one path that
    reaches the branch.
    """
    from irp_worker import scheduler as sched_mod

    class _FakeSavepoint:
        def commit(self) -> None: ...
        def rollback(self) -> None: ...

    class _FakeSession:
        def begin_nested(self) -> _FakeSavepoint:
            return _FakeSavepoint()

    class _FakeSchedule:
        id = "sched-1"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the ledger insert itself failed")

    original = sched_mod.record_failed_dispatch
    sched_mod.record_failed_dispatch = _boom  # type: ignore[assignment]
    try:
        outcome = sched_mod._record_failed(
            _FakeSession(),  # type: ignore[arg-type]
            _FakeSchedule(),
            datetime(2026, 5, 29, 23, 59, 59, 999999, tzinfo=UTC),
            datetime(2026, 6, 1, 6, 5, tzinfo=UTC),
            "some reason",
        )
    finally:
        sched_mod.record_failed_dispatch = original  # type: ignore[assignment]

    assert outcome == sched_mod.OUTCOME_UNRECORDED
    assert outcome != sched_mod.OUTCOME_FAILED  # the whole point of the distinction


def test_record_failed_reports_failed_on_the_ordinary_path() -> None:
    """The control for the test above: the SAME helper returns FAILED when recording succeeds, so
    the assertion is discriminating rather than always-UNRECORDED."""
    from irp_worker import scheduler as sched_mod

    class _FakeSavepoint:
        def commit(self) -> None: ...
        def rollback(self) -> None: ...

    class _FakeSession:
        def begin_nested(self) -> _FakeSavepoint:
            return _FakeSavepoint()

    original = sched_mod.record_failed_dispatch
    sched_mod.record_failed_dispatch = lambda *a, **k: None  # type: ignore[assignment]
    try:
        outcome = sched_mod._record_failed(
            _FakeSession(),  # type: ignore[arg-type]
            type("S", (), {"id": "sched-1"})(),
            datetime(2026, 5, 29, 23, 59, 59, 999999, tzinfo=UTC),
            datetime(2026, 6, 1, 6, 5, tzinfo=UTC),
            "some reason",
        )
    finally:
        sched_mod.record_failed_dispatch = original  # type: ignore[assignment]

    assert outcome == sched_mod.OUTCOME_FAILED
