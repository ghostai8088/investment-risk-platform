"""The XNYS (NYSE) full-day scheduled holiday set, 2023-2035 (CAL-1a, OQ-CAL-1-8).

BACKWARD EXTENSION (Wave-14 close): the set originally opened at 2024, and that was an OFF-BY-ONE
against its own consumers. A BUSINESS_MONTH_END grid's opening boundary d_0 is the close of the
month BEFORE the first measured month, so ANY v2 run whose first measured month is January 2024 --
the earliest month the 2024-anchored set could serve -- adjudicates d_0 = 2023-12-29 against a
calendar that knows nothing about 2023. The shipped RM-1/SR-1 demo did exactly that and rolled its
opening boundary WEEKEND-ONLY; nothing detected it until the close's start-side coverage gate
(``holiday_binding.assert_boundaries_covered``) was added and the demo refused. The dataset, not
the gate, was wrong: a month-end calendar must cover one year further back than the earliest month
it is meant to serve. Adding 2023 moved NO governed boundary literal (December 2023's last weekday
is Friday the 29th with or without holiday knowledge -- Christmas fell on the Monday), which is
what makes this an extension rather than a restatement of shipped numbers.

HAND-ENCODED LITERALS, never derived at runtime (the ratified rule: the runtime set must not be
computed from an observance rule -- a naive "Saturday holiday => preceding Friday observed"
derivation wrongly adds 2027-12-31 and 2032-12-31, both REAL trading days under NYSE Rule 7.2's
year-end exception, and both last-weekday December month-ends). The dataset is verified three
ways: the census test pins per-year COUNTS plus anchor dates (the tricky observance dates and
the exact 9-member 2028/2033 sets); an INDEPENDENTLY-implemented rule cross-check (with Rule
7.2) must agree on FULL membership; and the two Rule 7.2 negatives are pinned ABSENT.

Provenance (the diligence checklist's Execution 1 records the walk-through):

- **2023: the NYSE published holiday schedule as it stood IN 2023**, recovered from the Wayback
  Machine's 2023-03-05 capture of nyse.com/markets/hours-calendars (a contemporaneous three-year
  2023|2024|2025 table). The capture's 2024 and 2025 columns were checked against the literals
  ALREADY shipped here and agree date-for-date -- which is what establishes that the 2023 column
  was read from the right position rather than merely looking plausible. The early-close markers
  in that table (July 3, the Friday after Thanksgiving) are half-days, hence TRADING days, and are
  excluded on the same rule as every other year.
- **2024-2028: the NYSE published holiday schedule** (nyse.com "Holidays and Trading Hours" --
  the exchange publishes roughly three years ahead; 2024-2025 verified against the archived
  pages). Scheduled FULL-DAY closures only: early-close half-days (e.g. July 3 2025,
  Nov 28 2025) are TRADING days and are deliberately absent; unscheduled event closures
  (e.g. mourning days) cannot be scheduled and are out of scope.
- **2029-2035: PROJECTED** from the NYSE's holiday definitions (New Year's Day, MLK Day,
  Washington's Birthday, Good Friday, Memorial Day, Juneteenth, Independence Day, Labor Day,
  Thanksgiving, Christmas) with the observance rules INCLUDING the Rule 7.2 year-end exception:
  a Saturday holiday whose substitute Friday would be the last business day of the month is NOT
  observed (the exchange stays open) -- hence 2028 and 2033 carry NINE holidays (New Year's Day
  unobserved) and 2027-12-31 / 2032-12-31 are trading days. Projections are re-verified against
  the published schedule as the exchange extends it (a diligence-checklist re-execution item).

The two token dates the 0008-era seed carried (2026-01-01, 2026-12-25) are members of this set,
so the add-only refresh (``refresh_calendar_holidays``) is idempotent over the seeded calendar.
"""

from __future__ import annotations

from datetime import date

#: (holiday_date, name) -- full-day scheduled XNYS closures, 2024-2035 inclusive.
XNYS_HOLIDAYS: tuple[tuple[date, str], ...] = (
    # --- 2023 (published; added at the Wave-14 close — see the BACKWARD EXTENSION note above) ---
    (date(2023, 1, 2), "New Year's Day"),  # observed: 2023-01-01 was a Sunday
    (date(2023, 1, 16), "Martin Luther King, Jr. Day"),
    (date(2023, 2, 20), "Washington's Birthday"),
    (date(2023, 4, 7), "Good Friday"),
    (date(2023, 5, 29), "Memorial Day"),
    (date(2023, 6, 19), "Juneteenth National Independence Day"),
    (date(2023, 7, 4), "Independence Day"),
    (date(2023, 9, 4), "Labor Day"),
    (date(2023, 11, 23), "Thanksgiving Day"),
    (date(2023, 12, 25), "Christmas Day"),
    # --- 2024 (published) ---
    (date(2024, 1, 1), "New Year's Day"),
    (date(2024, 1, 15), "Martin Luther King, Jr. Day"),
    (date(2024, 2, 19), "Washington's Birthday"),
    (date(2024, 3, 29), "Good Friday"),
    (date(2024, 5, 27), "Memorial Day"),
    (date(2024, 6, 19), "Juneteenth National Independence Day"),
    (date(2024, 7, 4), "Independence Day"),
    (date(2024, 9, 2), "Labor Day"),
    (date(2024, 11, 28), "Thanksgiving Day"),
    (date(2024, 12, 25), "Christmas Day"),
    # --- 2025 (published) ---
    (date(2025, 1, 1), "New Year's Day"),
    (date(2025, 1, 20), "Martin Luther King, Jr. Day"),
    (date(2025, 2, 17), "Washington's Birthday"),
    (date(2025, 4, 18), "Good Friday"),
    (date(2025, 5, 26), "Memorial Day"),
    (date(2025, 6, 19), "Juneteenth National Independence Day"),
    (date(2025, 7, 4), "Independence Day"),
    (date(2025, 9, 1), "Labor Day"),
    (date(2025, 11, 27), "Thanksgiving Day"),
    (date(2025, 12, 25), "Christmas Day"),
    # --- 2026 (published) ---
    (date(2026, 1, 1), "New Year's Day"),
    (date(2026, 1, 19), "Martin Luther King, Jr. Day"),
    (date(2026, 2, 16), "Washington's Birthday"),
    (date(2026, 4, 3), "Good Friday"),
    (date(2026, 5, 25), "Memorial Day"),
    (date(2026, 6, 19), "Juneteenth National Independence Day"),
    (date(2026, 7, 3), "Independence Day"),
    (date(2026, 9, 7), "Labor Day"),
    (date(2026, 11, 26), "Thanksgiving Day"),
    (date(2026, 12, 25), "Christmas Day"),
    # --- 2027 (published) ---
    (date(2027, 1, 1), "New Year's Day"),
    (date(2027, 1, 18), "Martin Luther King, Jr. Day"),
    (date(2027, 2, 15), "Washington's Birthday"),
    (date(2027, 3, 26), "Good Friday"),
    (date(2027, 5, 31), "Memorial Day"),
    (date(2027, 6, 18), "Juneteenth National Independence Day"),
    (date(2027, 7, 5), "Independence Day"),
    (date(2027, 9, 6), "Labor Day"),
    (date(2027, 11, 25), "Thanksgiving Day"),
    (date(2027, 12, 24), "Christmas Day"),
    # --- 2028 (published) ---
    (date(2028, 1, 17), "Martin Luther King, Jr. Day"),
    (date(2028, 2, 21), "Washington's Birthday"),
    (date(2028, 4, 14), "Good Friday"),
    (date(2028, 5, 29), "Memorial Day"),
    (date(2028, 6, 19), "Juneteenth National Independence Day"),
    (date(2028, 7, 4), "Independence Day"),
    (date(2028, 9, 4), "Labor Day"),
    (date(2028, 11, 23), "Thanksgiving Day"),
    (date(2028, 12, 25), "Christmas Day"),
    # --- 2029 (PROJECTED) ---
    (date(2029, 1, 1), "New Year's Day"),
    (date(2029, 1, 15), "Martin Luther King, Jr. Day"),
    (date(2029, 2, 19), "Washington's Birthday"),
    (date(2029, 3, 30), "Good Friday"),
    (date(2029, 5, 28), "Memorial Day"),
    (date(2029, 6, 19), "Juneteenth National Independence Day"),
    (date(2029, 7, 4), "Independence Day"),
    (date(2029, 9, 3), "Labor Day"),
    (date(2029, 11, 22), "Thanksgiving Day"),
    (date(2029, 12, 25), "Christmas Day"),
    # --- 2030 (PROJECTED) ---
    (date(2030, 1, 1), "New Year's Day"),
    (date(2030, 1, 21), "Martin Luther King, Jr. Day"),
    (date(2030, 2, 18), "Washington's Birthday"),
    (date(2030, 4, 19), "Good Friday"),
    (date(2030, 5, 27), "Memorial Day"),
    (date(2030, 6, 19), "Juneteenth National Independence Day"),
    (date(2030, 7, 4), "Independence Day"),
    (date(2030, 9, 2), "Labor Day"),
    (date(2030, 11, 28), "Thanksgiving Day"),
    (date(2030, 12, 25), "Christmas Day"),
    # --- 2031 (PROJECTED) ---
    (date(2031, 1, 1), "New Year's Day"),
    (date(2031, 1, 20), "Martin Luther King, Jr. Day"),
    (date(2031, 2, 17), "Washington's Birthday"),
    (date(2031, 4, 11), "Good Friday"),
    (date(2031, 5, 26), "Memorial Day"),
    (date(2031, 6, 19), "Juneteenth National Independence Day"),
    (date(2031, 7, 4), "Independence Day"),
    (date(2031, 9, 1), "Labor Day"),
    (date(2031, 11, 27), "Thanksgiving Day"),
    (date(2031, 12, 25), "Christmas Day"),
    # --- 2032 (PROJECTED) ---
    (date(2032, 1, 1), "New Year's Day"),
    (date(2032, 1, 19), "Martin Luther King, Jr. Day"),
    (date(2032, 2, 16), "Washington's Birthday"),
    (date(2032, 3, 26), "Good Friday"),
    (date(2032, 5, 31), "Memorial Day"),
    (date(2032, 6, 18), "Juneteenth National Independence Day"),
    (date(2032, 7, 5), "Independence Day"),
    (date(2032, 9, 6), "Labor Day"),
    (date(2032, 11, 25), "Thanksgiving Day"),
    (date(2032, 12, 24), "Christmas Day"),
    # --- 2033 (PROJECTED) ---
    (date(2033, 1, 17), "Martin Luther King, Jr. Day"),
    (date(2033, 2, 21), "Washington's Birthday"),
    (date(2033, 4, 15), "Good Friday"),
    (date(2033, 5, 30), "Memorial Day"),
    (date(2033, 6, 20), "Juneteenth National Independence Day"),
    (date(2033, 7, 4), "Independence Day"),
    (date(2033, 9, 5), "Labor Day"),
    (date(2033, 11, 24), "Thanksgiving Day"),
    (date(2033, 12, 26), "Christmas Day"),
    # --- 2034 (PROJECTED) ---
    (date(2034, 1, 2), "New Year's Day"),
    (date(2034, 1, 16), "Martin Luther King, Jr. Day"),
    (date(2034, 2, 20), "Washington's Birthday"),
    (date(2034, 4, 7), "Good Friday"),
    (date(2034, 5, 29), "Memorial Day"),
    (date(2034, 6, 19), "Juneteenth National Independence Day"),
    (date(2034, 7, 4), "Independence Day"),
    (date(2034, 9, 4), "Labor Day"),
    (date(2034, 11, 23), "Thanksgiving Day"),
    (date(2034, 12, 25), "Christmas Day"),
    # --- 2035 (PROJECTED) ---
    (date(2035, 1, 1), "New Year's Day"),
    (date(2035, 1, 15), "Martin Luther King, Jr. Day"),
    (date(2035, 2, 19), "Washington's Birthday"),
    (date(2035, 3, 23), "Good Friday"),
    (date(2035, 5, 28), "Memorial Day"),
    (date(2035, 6, 19), "Juneteenth National Independence Day"),
    (date(2035, 7, 4), "Independence Day"),
    (date(2035, 9, 3), "Labor Day"),
    (date(2035, 11, 22), "Thanksgiving Day"),
    (date(2035, 12, 25), "Christmas Day"),
)

#: The Rule 7.2 negatives: Saturday New Year's Days whose substitute Friday is a month-end --
#: the exchange stays OPEN. Pinned ABSENT by the census test; listed here so the next encoder
#: sees them before "fixing" the 9-holiday years.
XNYS_RULE_72_OPEN_FRIDAYS: tuple[date, ...] = (date(2027, 12, 31), date(2032, 12, 31))

#: The dataset's DECLARED coverage horizon (OQ-CAL-1-4): the last date through which this module
#: asserts the closure set is complete. Advanced (forward-only) by the refresh verb whenever the
#: dataset is extended; a BUSINESS_MONTH_END tick or a v2 perf span beyond it REFUSES.
XNYS_COMPLETE_THROUGH: date = date(2035, 12, 31)
