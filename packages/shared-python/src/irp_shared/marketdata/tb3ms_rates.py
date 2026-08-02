"""The TB3MS dataset (DATA-1) — 3-Month Treasury Bill Secondary Market Rate, Discount Basis.

The platform's FIRST genuinely external dataset: hand-encoded literals of the Board of Governors'
H.15 monthly series (percent, annualized on a 360-day discount basis, monthly average of business
days), re-expressed at capture as canonical DECIMAL FRACTIONS (``0.0522`` = 5.22% — the ENT-025
units convention; the ONLY transformation, a pure units change — the annualized→period-return
conversion is a registered-model carry, OQ-DATA-1-1).

PROVENANCE (CTRL-034 Execution 2, checklist items 2/3): origin = Board of Governors of the
Federal Reserve System, H.15 Selected Interest Rates (U.S. public domain at origin, 17 U.S.C.
§105 + the Board's disclaimer; cite the Board). Access channel = FRED (series TB3MS,
https://fred.stlouisfed.org/series/TB3MS — attribution given per its ToU). Values were read from
proxy-rendered single-page views (fred.stlouisfed.org refuses this environment's direct fetcher)
and verified by THREE independent extraction passes agreeing on all 30 values (two at recon, one
at implementation, 2026-08-02), cross-checked against the Board's live H.15 daily release
(late-July dailies 3.69–3.82 sit 3–16bp above the June average — plausibility only). The series
is REVISABLE (the Board's historical-correction page, selected 2002–2005 dates): a published
correction goes through ``correct_benchmark_rate``, never a re-encode.

DATING (checklist item 4): each observation is dated the FIRST of its OBSERVATION month (the
vendor's own dating) — conforming with the declared INSIDE-the-month convention at the
observation grain; the return-month mapping (contemporaneous vs ex-ante) is expressly assigned
to the conversion-model carry. The 2026-07 value was UNPUBLISHED at encoding (posts ~1 business
day after month end): the declared horizon ends at 2026-06-30 and the add-only refresh verb is
the paid path for later months.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

#: The declared series START (OQ-DATA-1-4: the expected set derives from TWO declarations, never
#: from the data — a data-derived start could not represent a missing first month).
TB3MS_SERIES_START: date = date(2024, 1, 1)

#: The declared coverage horizon: the last day of the last PUBLISHED observation month.
TB3MS_COMPLETE_THROUGH: date = date(2026, 6, 30)

#: The 30 published monthly observations 2024-01..2026-06 as (rate_date, fraction) — percent/100
#: exactly, dated on the vendor's first-of-observation-month convention. Verbatim from the
#: published series; NEVER derived. (Per-value provenance: the module docstring.)
TB3MS_RATES: tuple[tuple[date, Decimal], ...] = (
    (date(2024, 1, 1), Decimal("0.0522")),
    (date(2024, 2, 1), Decimal("0.0524")),
    (date(2024, 3, 1), Decimal("0.0524")),
    (date(2024, 4, 1), Decimal("0.0524")),
    (date(2024, 5, 1), Decimal("0.0525")),
    (date(2024, 6, 1), Decimal("0.0524")),
    (date(2024, 7, 1), Decimal("0.0520")),
    (date(2024, 8, 1), Decimal("0.0505")),
    (date(2024, 9, 1), Decimal("0.0472")),
    (date(2024, 10, 1), Decimal("0.0451")),
    (date(2024, 11, 1), Decimal("0.0442")),
    (date(2024, 12, 1), Decimal("0.0427")),
    (date(2025, 1, 1), Decimal("0.0421")),
    (date(2025, 2, 1), Decimal("0.0422")),
    (date(2025, 3, 1), Decimal("0.0420")),
    (date(2025, 4, 1), Decimal("0.0421")),
    (date(2025, 5, 1), Decimal("0.0425")),
    (date(2025, 6, 1), Decimal("0.0423")),
    (date(2025, 7, 1), Decimal("0.0425")),
    (date(2025, 8, 1), Decimal("0.0412")),
    (date(2025, 9, 1), Decimal("0.0392")),
    (date(2025, 10, 1), Decimal("0.0382")),
    (date(2025, 11, 1), Decimal("0.0378")),
    (date(2025, 12, 1), Decimal("0.0359")),
    (date(2026, 1, 1), Decimal("0.0357")),
    (date(2026, 2, 1), Decimal("0.0360")),
    (date(2026, 3, 1), Decimal("0.0361")),
    (date(2026, 4, 1), Decimal("0.0361")),
    (date(2026, 5, 1), Decimal("0.0360")),
    (date(2026, 6, 1), Decimal("0.0366")),
)

__all__ = ["TB3MS_SERIES_START", "TB3MS_COMPLETE_THROUGH", "TB3MS_RATES"]
