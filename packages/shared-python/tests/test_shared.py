"""Placeholder tests for the shared Python library."""

from __future__ import annotations

from irp_shared import __version__
from irp_shared.temporal import TemporalClass


def test_version_present() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_temporal_classes() -> None:
    assert {c.value for c in TemporalClass} == {"FR", "IA", "EV"}
