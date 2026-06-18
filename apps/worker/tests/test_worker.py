"""Placeholder test proving worker wiring."""

from __future__ import annotations

from irp_worker.main import run_once


def test_run_once() -> None:
    result = run_once()
    assert result["status"] == "idle"
    assert result["component"] == "worker"
