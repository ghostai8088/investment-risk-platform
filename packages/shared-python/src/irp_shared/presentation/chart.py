"""PRESENT-1 (REQ-PRS-002): the governed chart — a deterministic inline-SVG fragment.

The fragment is emitted INSIDE the report body, because the report content hash is `sha256` over
that one joined string and nothing else. A chart served alongside the report would satisfy every
other clause and fail the one that says the chart's content is covered by the hash.

## Determinism, which is the whole requirement

Two renders of the same pinned evidence must produce BYTE-IDENTICAL SVG. So:

- **Decimal throughout, never float.** Coordinates are computed with `Decimal` and quantized with an
  explicit `ROUND_HALF_EVEN`. A float round-trip would make the bytes depend on the platform's
  binary representation, which is exactly the class of drift a governed hash exists to catch.
- **No timestamps, no ids that vary per render, no unordered iteration.** The same rules the HTML
  renderer already states, for the same reason.
- **A fixed viewBox**, so the geometry does not depend on anything ambient.

## The series comes from the CONTRACT, not from here

`series_selector` lives in the pinned presentation contract. This module reads it; it does not know
which series it is drawing. That is what makes REQ-PRS-002's "the SVG is produced FROM the family's
PINNED presentation contract" bite: change the selector and the chart changes. A renderer that hard-
coded the series would satisfy every other clause while consulting no contract at all, which is the
exploit that amendment was written to close.

## Degenerate cases, each defined rather than discovered

- **0 datapoints** — an empty plot with a stated reason, never a crash and never a blank.
- **1 datapoint** — a single mark; a line through one point is not a line.
- **zero range** (every value equal) — a flat line at mid-height, because the alternative divides
  by zero.
- **negative values** — the domain is min..max, not 0..max.
- **a NON-NUMERIC pinned value** — `rolling_risk` pins `SUPPRESSED (...)` strings and every seeded
  run has five of them, so this is guaranteed rather than hypothetical. Such points are EXCLUDED
  from the plotted series and their count is disclosed in the fragment, because silently dropping a
  suppressed value would let a chart claim completeness it does not have.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any
from xml.sax.saxutils import escape

#: Fixed geometry. Ambient sizing would make the bytes depend on something outside the pin.
_WIDTH = Decimal(640)
_HEIGHT = Decimal(180)
_PAD = Decimal(20)

#: Coordinate precision. Explicit rounding mode: the default context's mode is ambient state, and
#: ambient state in a hashed artifact is a drift source.
_COORD = Decimal("0.001")


def _q(value: Decimal) -> str:
    """A coordinate, quantized and rendered with no exponent and no trailing-zero ambiguity."""
    return format(value.quantize(_COORD, rounding=ROUND_HALF_EVEN), "f")


def _numeric(raw: str) -> Decimal | None:
    """The pinned value as a Decimal, or None when it is not a number.

    `rolling_risk` pins `SUPPRESSED (reason)` for a suppressed row. That is a legitimate pinned
    value, not corrupt data, so it is skipped rather than raised on — and counted, so the fragment
    can say how many points it left out.
    """
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return None


def select_series(
    values: list[dict[str, str]], contract: dict[str, Any]
) -> tuple[list[Decimal], int]:
    """(plottable values in pinned order, count of non-numeric points skipped).

    The metric key is the pinned `metric` string; the contract's `series_selector` names the values
    its parts must match. Matching is on the pinned key text because that is what the section
    carries — the source rows are long gone by render time, which is the point of pinning.
    """
    selector = contract.get("series_selector") or {}
    if not selector:
        return [], 0
    # STRUCTURAL match on the key's parts, never a substring scan.
    #
    # The pinned key is `{metric_type}:{window_months}m:{period_end}` (families.py). A substring
    # test for the window — `"12" in metric` — was the first implementation and it is WRONG: it
    # matches `ROLLING_VOLATILITY:36m:2026-12-31`, a December period_end in a THIRTY-SIX month
    # window, and silently mixes two series into one line. Found by a test written against the real
    # key format rather than against the fixture.
    want_metric = str(selector.get("metric_type", ""))
    want_window = f"{selector.get('window_months')}m"
    plottable: list[Decimal] = []
    skipped = 0
    for item in values:
        metric = str(item.get("metric", ""))
        parts = metric.split(":")
        if len(parts) < 2 or parts[0] != want_metric or parts[1] != want_window:
            continue
        number = _numeric(str(item.get("value", "")))
        if number is None:
            skipped += 1
            continue
        plottable.append(number)
    return plottable, skipped


def render_series_chart(section: dict[str, Any], contract: dict[str, Any]) -> str:
    """One inline-SVG fragment for the section's declared series. Deterministic by construction."""
    run_id = escape(str(section.get("source_run_id", "")))
    mark = str(contract.get("mark", "path"))
    points, skipped = select_series(list(section.get("values", [])), contract)

    # The run id is on the fragment itself: REQ-PRS-002 requires the chart to carry the run it was
    # produced from, and a caption would not survive being extracted from the report.
    head = (
        f"<svg class='governed-chart' xmlns='http://www.w3.org/2000/svg' "
        f"viewBox='0 0 {_q(_WIDTH)} {_q(_HEIGHT)}' role='img' "
        f"data-run-id='{run_id}' data-mark='{escape(mark)}' "
        f"data-points='{len(points)}' data-skipped='{skipped}'>"
    )
    note = (
        f"<desc>{len(points)} plotted"
        + (f", {skipped} suppressed and omitted" if skipped else "")
        + "</desc>"
    )

    if not points:
        # Honest-empty. A blank chart and a chart of nothing are different claims.
        return (
            head
            + note
            + "<text x='20' y='96' class='state'>no plottable values in this series</text></svg>"
        )

    lo, hi = min(points), max(points)
    span = hi - lo
    inner_w = _WIDTH - _PAD - _PAD
    inner_h = _HEIGHT - _PAD - _PAD

    def _x(index: int) -> Decimal:
        if len(points) == 1:
            return _PAD + inner_w / 2  # a single point sits in the middle, not at the origin
        return _PAD + inner_w * Decimal(index) / Decimal(len(points) - 1)

    def _y(value: Decimal) -> Decimal:
        if span == 0:
            return _PAD + inner_h / 2  # flat series: mid-height, never a division by zero
        return _PAD + inner_h - (inner_h * (value - lo) / span)

    body: list[str] = []
    if mark == "path":
        # ONE path element carrying every datapoint. The anti-vacuity guard counts coordinate
        # commands rather than elements, because counting elements is unsatisfiable for a line.
        commands = " ".join(
            f"{'M' if i == 0 else 'L'}{_q(_x(i))},{_q(_y(v))}" for i, v in enumerate(points)
        )
        body.append(f"<path d='{commands}' fill='none' />")
    elif mark == "rect":
        base = _PAD + inner_h
        for i, v in enumerate(points):
            top = _y(v)
            body.append(
                f"<rect x='{_q(_x(i))}' y='{_q(top)}' width='4' " f"height='{_q(base - top)}' />"
            )
    elif mark == "circle":
        for i, v in enumerate(points):
            body.append(f"<circle cx='{_q(_x(i))}' cy='{_q(_y(v))}' r='2' />")
    else:  # "line"
        for i in range(len(points) - 1):
            body.append(
                f"<line x1='{_q(_x(i))}' y1='{_q(_y(points[i]))}' "
                f"x2='{_q(_x(i + 1))}' y2='{_q(_y(points[i + 1]))}' />"
            )
        if len(points) == 1:
            body.append(
                f"<line x1='{_q(_x(0))}' y1='{_q(_y(points[0]))}' "
                f"x2='{_q(_x(0))}' y2='{_q(_y(points[0]))}' />"
            )

    return head + note + "".join(body) + "</svg>"


__all__ = ["render_series_chart", "select_series"]
