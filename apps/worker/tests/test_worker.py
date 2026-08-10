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


def test_parse_tenant_ids_REFUSES_a_malformed_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CAD-1 OQ-3=A skip-and-continue behavior, SUPERSEDED at REPRO-2 — rewritten as the
    supersession's twin rather than deleted, because the reason it changed is the point.

    Under config-as-the-tenant-set, dropping one fat-fingered id left the other tenants ticking
    and an all-bad list fell through to the empty-list refusal: a bounded loss. Under registry
    discovery an empty parse means "no restriction", so skipping a typo would silently widen the
    filter to EVERY tenant — the looks-configured-but-isn't state CAD-1 FOLD-2 ratified against,
    inverted into over-ticking. A typo is now a refusal.

    The `on_bad` callback still fires first, so the offending entry is NAMED before the refusal.
    """
    bad: list[str] = []
    with pytest.raises(TenantIdError):
        parse_tenant_ids(f"{_A},garbage,{_B}", on_bad=lambda e, _exc: bad.append(e))
    assert bad == ["garbage"], "the refusal did not name the offending entry first"


def test_parse_tenant_ids_ignores_blanks_but_not_typos() -> None:
    """A trailing comma is not a typo; `not-a-uuid` is. The discriminating pair."""
    assert parse_tenant_ids(f"{_A}, ,{_B},") == [_A, _B]
    with pytest.raises(TenantIdError):
        parse_tenant_ids(f"{_A},not-a-uuid")


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


def test_supervisor_main_empty_tenant_ids_reaches_discovery_and_an_unreadable_registry_refuses(
    monkeypatch,  # type: ignore[no-untyped-def]
    capsys,
) -> None:
    """The CAD-1 FOLD-2 empty-list refusal at main(), SUPERSEDED at REPRO-2 — rewritten as the
    supersession's twin, and this rewrite was forced by CI, not by the blast-radius sweep.

    The old test asserted exit 2 on an empty IRP_TENANT_IDS and KEPT PASSING locally after the
    supersession — through a completely different refusal that happens to share the exit code
    (the fake DB URL made the STARTUP REGISTRY READ refuse). CI, with no psycopg installed,
    surfaced the truth: the test was reaching engine creation, which the behavior it claimed to
    pin never did. So this pins the MESSAGE, not just the code: an empty filter must NOT die at
    env-parse (no 'no valid tenants'), and an unreadable registry at startup refuses as ITSELF.
    """
    import irp_worker.supervisor as sup

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x/y")
    monkeypatch.setenv("IRP_TENANT_IDS", "")

    class _DeadSession:
        def execute(self, *_a: object, **_k: object) -> object:
            raise RuntimeError("registry unreachable")

        def __enter__(self) -> _DeadSession:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    class _DeadEngine:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(sup, "make_engine", lambda _url: _DeadEngine())
    monkeypatch.setattr(sup, "make_session_factory", lambda _e: _DeadSession)
    assert supervisor_main([]) == 2
    err = capsys.readouterr().err
    assert "could not be read" in err, "the refusal was not the startup-registry one"
    assert "no valid tenants" not in err, "the superseded empty-list refusal came back"


def test_supervisor_main_a_malformed_tenant_id_fails_closed(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    # REPRO-2 strict parse: the entry itself refuses (never 'all skipped → empty → fail closed',
    # which was the CAD-1 shape this test used to describe). Refusal happens BEFORE any engine
    # exists, and the message names the parse — pinned so this cannot pass through a later
    # refusal that shares the exit code.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x/y")
    monkeypatch.setenv("IRP_TENANT_IDS", "garbage,also-bad")
    assert supervisor_main([]) == 2
    assert "malformed tenant id" in capsys.readouterr().err


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


def test_the_period_dedup_key_classifies_benign() -> None:
    """The CAL-1b review's MED: the classifier's new period-key arm, EXECUTED in both forms
    (diag name and string fallback) plus the neither-name negative."""
    from sqlalchemy.exc import IntegrityError

    from irp_worker.scheduler import _is_tick_dedup

    class _Diag:
        def __init__(self, name: str | None) -> None:
            self.constraint_name = name

    class _Orig(Exception):
        def __init__(self, name: str | None) -> None:
            self.diag = _Diag(name)

    def _exc(name: str | None, text: str) -> IntegrityError:
        return IntegrityError(text, {}, _Orig(name))

    assert _is_tick_dedup(_exc("uq_scheduled_run_schedule_period", "x")) is True
    assert _is_tick_dedup(_exc("uq_scheduled_run_schedule_tick", "x")) is True
    assert _is_tick_dedup(_exc(None, "... uq_scheduled_run_schedule_period ...")) is True
    assert _is_tick_dedup(_exc(None, "some other constraint entirely")) is False
