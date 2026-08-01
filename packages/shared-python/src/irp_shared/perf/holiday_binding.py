"""The v2 holiday-pin adjudication SHARED by the RM-1 and SR-1 binders (CAL-1b, OQ-CAL-1-2/6).

One implementation, two callers — deliberately: the month-end predicate chain is duplicated
verbatim across the two binders' adjudication paths, and a convention split between them over the
same pin shape is the exact hazard the Wave-13 ``parse_strict_decimal`` fold recorded. Under
AD-014 the v2 kernel reads ONLY pinned content: the binder never re-reads ``calendar_holiday``
live — the holiday set comes from the snapshot's ``HOLIDAY_CALENDAR`` component, cross-checked
against the model version's DECLARED calendar literal (a v2 run over a snapshot pinned with the
wrong — or no — calendar refuses pre-create, zero rows minted).
"""

from __future__ import annotations

import json
from datetime import date as dt_date
from typing import Any

from irp_shared.snapshot.models import COMPONENT_KIND_HOLIDAY_CALENDAR


def parse_pinned_holidays(
    components: list[Any], *, declared_code: str, error: type[Exception]
) -> tuple[frozenset[dt_date], dt_date]:
    """Adjudicate the snapshot's HOLIDAY_CALENDAR pin for a v2 run — fail-closed on every arm.

    Refusals (all raised as the binder's own ``error`` class, the governed 422 pattern): no pin
    (a v2 run needs the set it computes under to be PINNED — AD-014); more than one pin; a pinned
    calendar whose ``code`` is not the version's DECLARED literal (the declared-vs-pinned
    cross-check); a pin with NO declared coverage (an undeclared horizon cannot gate anything);
    malformed content. Returns ``(holiday_dates, holidays_complete_through)`` — the caller
    compares coverage against the series span BEFORE the alignment gate."""
    pins = [c for c in components if c.component_kind == COMPONENT_KIND_HOLIDAY_CALENDAR]
    if not pins:
        raise error(
            "the snapshot pins no HOLIDAY_CALENDAR component — a BUSINESS-convention (v2) run "
            "requires its holiday set pinned (AD-014: the compute reads only pinned content); "
            "rebuild the snapshot with holiday_calendar_code set"
        )
    if len(pins) > 1:
        raise error(
            f"the snapshot pins {len(pins)} HOLIDAY_CALENDAR components — exactly one calendar "
            "governs a v2 grid"
        )
    try:
        content = json.loads(pins[0].captured_content)
        code = str(content["code"])
        raw_dates = content["holiday_dates"]
        raw_coverage = content["holidays_complete_through"]
        dates = frozenset(dt_date.fromisoformat(str(d)) for d in raw_dates)
        # Parsed INSIDE the malformed envelope (the CAL-1b review's MED: a non-ISO coverage
        # string previously leaked a raw ValueError past the governed refusal from the return
        # line). None survives to the explicit refusal below.
        coverage = None if raw_coverage is None else dt_date.fromisoformat(str(raw_coverage))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise error(f"the pinned HOLIDAY_CALENDAR component is malformed: {exc}") from exc
    if code != declared_code:
        raise error(
            f"the snapshot pins calendar {code!r} but this model version declares "
            f"holiday_calendar={declared_code!r} — a v2 run must compute under its declared "
            "calendar (rebuild the snapshot)"
        )
    if coverage is None:
        raise error(
            f"the pinned calendar {code!r} declares no holiday coverage "
            "(holidays_complete_through is NULL) — a declared horizon is required (OQ-CAL-1-4)"
        )
    return dates, coverage
