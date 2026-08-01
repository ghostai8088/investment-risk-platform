"""parse_pinned_holidays' fail-closed arms (CAL-1b review fold — every refusal EXECUTED, not
believed; the LIM-2 standard)."""

from __future__ import annotations

import json
from dataclasses import dataclass

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
