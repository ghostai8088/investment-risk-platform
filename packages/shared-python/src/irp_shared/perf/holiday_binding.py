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


def assert_boundaries_covered(
    boundaries: list[dt_date],
    *,
    holidays: frozenset[dt_date],
    holidays_complete_through: dt_date,
    error: type[Exception],
) -> None:
    """BOTH sides of the coverage gate, in one shared site (P10: the class, not the site).

    The end side is the original OQ-CAL-1-4 refusal: a series closing beyond the DECLARED
    ``holidays_complete_through`` must refuse, never degrade to the weekend-only answer.

    The start side is the Wave-14 close's HIGH, absent from the first shipment: nothing compared
    the series START against where the calendar begins, so a v2 window opening before the
    dataset's first covered year (XNYS starts 2024) rolled those months WEEKEND-ONLY — a silently
    wrong governed boundary, the exact degradation the end side exists to refuse. Both binders
    carried the end-side check inline and identically; the fold moves the pair HERE so a third
    v2 consumer inherits both sides rather than re-forgetting one.

    The start bound is DERIVED (January 1 of the earliest pinned holiday's year) because the
    calendar declares only forward coverage — there is no ``holidays_complete_from`` column. The
    derivation's error direction is REFUSAL: a partially-loaded first year moves the derived
    start LATER and refuses more, never less. Interior gaps are the refresh verb's declared
    forward-only-advance contract, not this gate's. A DECLARED start bound is the named carry
    (trigger: the next calendar-touching slice); an EMPTY pinned set refuses outright, because a
    coverage window with no holidays cannot anchor a derived start and no real exchange calendar
    is holiday-free.
    """
    if not holidays:
        raise error(
            "the pinned HOLIDAY_CALENDAR set is EMPTY — a derived coverage start cannot be "
            "anchored, so the run refuses rather than rolling weekend-only (the Wave-14 close's "
            "start-side gate; a DECLARED holidays_complete_from is the named carry)"
        )
    if boundaries[-1] > holidays_complete_through:
        raise error(
            f"the series closes on {boundaries[-1]}, beyond the pinned calendar's declared "
            f"holiday coverage ({holidays_complete_through}) — an uncovered month must refuse, "
            "never degrade to the weekend-only answer (OQ-CAL-1-4)"
        )
    derived_start = dt_date(min(holidays).year, 1, 1)
    if boundaries[0] < derived_start:
        raise error(
            f"the series opens on {boundaries[0]}, before the pinned calendar's earliest covered "
            f"year (derived start {derived_start}) — months before the dataset begins would roll "
            "WEEKEND-ONLY and produce silently wrong BUSINESS boundaries (the Wave-14 close's "
            "start-side gate, symmetric with OQ-CAL-1-4's end side)"
        )
