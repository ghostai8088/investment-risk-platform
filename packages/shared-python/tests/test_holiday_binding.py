"""parse_pinned_holidays' fail-closed arms (CAL-1b review fold — every refusal EXECUTED, not
believed; the LIM-2 standard)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import pytest

from irp_shared.perf.holiday_binding import parse_pinned_holidays
from irp_shared.snapshot.models import COMPONENT_KIND_HOLIDAY_CALENDAR


@dataclass
class _Pin:
    component_kind: str
    captured_content: str


class _Err(Exception):
    pass


def _pin(**overrides: object) -> _Pin:
    content: dict[str, object] = {
        "code": "XNYS",
        "mic": "XNYS",
        "holidays_complete_through": "2035-12-31",
        "holiday_dates": ["2027-05-31"],
    }
    content.update(overrides)
    return _Pin(COMPONENT_KIND_HOLIDAY_CALENDAR, json.dumps(content))


def test_the_happy_path_parses() -> None:
    dates, coverage = parse_pinned_holidays([_pin()], declared_code="XNYS", error=_Err)
    assert len(dates) == 1 and str(coverage) == "2035-12-31"


def test_no_pin_refuses() -> None:
    with pytest.raises(_Err, match="pins no HOLIDAY_CALENDAR"):
        parse_pinned_holidays([], declared_code="XNYS", error=_Err)


def test_two_pins_refuse() -> None:
    with pytest.raises(_Err, match="exactly one calendar"):
        parse_pinned_holidays([_pin(), _pin(code="XLON")], declared_code="XNYS", error=_Err)


def test_a_code_mismatch_refuses() -> None:
    """The declared-vs-pinned cross-check — the sharpest arm: a regression here computes a
    governed number under a calendar other than the registered identity declares."""
    with pytest.raises(_Err, match="declares\n?.*holiday_calendar|declares"):
        parse_pinned_holidays([_pin(code="XLON")], declared_code="XNYS", error=_Err)


def test_null_coverage_refuses() -> None:
    with pytest.raises(_Err, match="declares no holiday coverage"):
        parse_pinned_holidays(
            [_pin(holidays_complete_through=None)], declared_code="XNYS", error=_Err
        )


def test_malformed_coverage_is_a_governed_refusal_not_a_500() -> None:
    """The review's MED: a non-ISO coverage string previously leaked a raw ValueError past the
    governed envelope from the return line."""
    with pytest.raises(_Err, match="malformed"):
        parse_pinned_holidays(
            [_pin(holidays_complete_through="not-a-date")], declared_code="XNYS", error=_Err
        )


def test_malformed_dates_and_truncated_json_refuse() -> None:
    with pytest.raises(_Err, match="malformed"):
        parse_pinned_holidays([_pin(holiday_dates=["garbage"])], declared_code="XNYS", error=_Err)
    with pytest.raises(_Err, match="malformed"):
        parse_pinned_holidays(
            [_Pin(COMPONENT_KIND_HOLIDAY_CALENDAR, "{not json")], declared_code="XNYS", error=_Err
        )
    with pytest.raises(_Err, match="malformed"):
        parse_pinned_holidays(
            [_Pin(COMPONENT_KIND_HOLIDAY_CALENDAR, json.dumps({"code": "XNYS"}))],
            declared_code="XNYS",
            error=_Err,
        )


# --- the two-sided coverage gate (the Wave-14 close's HIGH: the start side was ABSENT) ---


class _GateError(Exception):
    pass


def _gate(boundaries, holidays, through):  # noqa: ANN001, ANN202
    from irp_shared.perf.holiday_binding import assert_boundaries_covered

    return assert_boundaries_covered(
        boundaries,
        holidays=frozenset(holidays),
        holidays_complete_through=through,
        error=_GateError,
    )


def test_the_start_side_FIRES_on_a_window_opening_before_the_dataset() -> None:
    """The close's reproduction, as a permanent control (P9: a refusal is not shipped until a
    test has made it fire). First shipment: only ``boundaries[-1]`` was checked, so a window
    opening 2023-12 over the 2024-anchored XNYS set rolled weekend-only, silently."""
    with pytest.raises(_GateError, match="before the pinned calendar's earliest covered year"):
        _gate(
            [date(2023, 12, 29), date(2024, 1, 31), date(2024, 2, 29)],
            {date(2024, 1, 1), date(2024, 12, 25)},
            date(2024, 12, 31),
        )


def test_the_boundary_negative_control_a_window_opening_AT_the_derived_start_passes() -> None:
    """Equal is covered — the gate must not over-refuse (the sub-floor-control lesson: a refusal
    control that cannot distinguish the boundary proves nothing)."""
    _gate(
        [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 28)],
        {date(2024, 1, 1), date(2024, 12, 25)},
        date(2024, 12, 31),
    )


def test_the_end_side_still_fires_unchanged() -> None:
    """OQ-CAL-1-4, now delegated to the shared site — the fold must not have weakened it."""
    with pytest.raises(_GateError, match="beyond the pinned calendar's declared"):
        _gate(
            [date(2024, 1, 31), date(2024, 11, 29), date(2025, 1, 31)],
            {date(2024, 1, 1)},
            date(2024, 12, 31),
        )


def test_an_empty_pinned_set_refuses_outright() -> None:
    """A coverage window with no holidays cannot anchor a derived start; unknown is not covered."""
    with pytest.raises(_GateError, match="EMPTY"):
        _gate([date(2024, 1, 31)], set(), date(2024, 12, 31))


def test_both_v2_binders_delegate_to_the_shared_gate() -> None:
    """P10's pin: the pair of coverage sides lives in ONE site, and both consumers call it. A
    binder that re-inlines the check (and re-forgets a side) fails here by name."""
    import pathlib

    import irp_shared.perf as perf

    root = pathlib.Path(perf.__file__).parent
    for svc in ("rolling_service.py", "sharpe_service.py"):
        text = (root / svc).read_text()
        assert "assert_boundaries_covered(" in text, f"{svc} no longer calls the shared gate"
        assert (
            "boundaries[-1] > holidays_complete_through" not in text
        ), f"{svc} re-inlined the end-side check — the class fix has been undone"
