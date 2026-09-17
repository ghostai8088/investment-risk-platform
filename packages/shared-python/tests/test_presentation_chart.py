"""W19-S1: REQ-PRS-002 — the governed chart is deterministic, contract-driven, and honest.

The acceptance, abbreviated: the same pinned evidence renders BYTE-IDENTICAL SVG; the fragment
carries the run id; altering any bound input moves the bytes; the chart's content is covered by the
REPORT content hash; the SVG is produced FROM the family's PINNED contract; and it contains the
DECLARED MARK SHAPES for its mark type — not only text nodes.

**The anti-vacuity guard is per-mark-type, and the first draft of it was unbuildable.** The plan
asked for "at least as many mark elements as datapoints". That is unsatisfiable for a line chart:
ONE `<path>` element legitimately carries all N points. A different-engine pass caught it. So for
`path` the guard counts COORDINATE COMMANDS; for `rect`/`circle` it counts elements. Either way a
chart that renders no data fails.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from irp_shared.presentation.chart import render_series_chart, select_series

_CONTRACT = {
    "mark": "path",
    "unit": "fraction",
    "precision": 12,
    "identity": ("metric_type", "window_months"),
    "series_selector": {"metric_type": "ROLLING_VOLATILITY", "window_months": 12},
}


def _section(values: list[tuple[str, str]], run_id: str = "run-abc") -> dict:
    return {
        "family": "rolling_risk",
        "source_run_id": run_id,
        "values": [{"metric": m, "value": v} for m, v in values],
    }


#: Shaped like the REAL pinned keys: `{metric_type}:{window_months}m:{period_end}`.
_REAL = [
    ("ROLLING_VOLATILITY:12m:2026-01-31", "0.110000000000"),
    ("ROLLING_VOLATILITY:12m:2026-02-28", "0.130000000000"),
    ("ROLLING_VOLATILITY:12m:2026-03-31", "0.120000000000"),
    # a suppressed row INSIDE the selected series — the disclosure path
    ("ROLLING_VOLATILITY:12m:2026-04-30", "SUPPRESSED (insufficient history)"),
    # a DIFFERENT metric, same window — must be excluded
    ("MAX_DRAWDOWN:12m:2026-01-31", "-0.080000000000"),
    # a different WINDOW whose period_end contains "12" — the substring trap. A `"12" in metric`
    # test matches this and mixes a 36-month series into the 12-month line.
    ("ROLLING_VOLATILITY:36m:2026-12-31", "0.400000000000"),
]


def _coord_count(svg: str) -> int:
    """Coordinate commands in the path — the datapoint count a `<path>` actually encodes."""
    match = re.search(r"<path d='([^']*)'", svg)
    return 0 if not match else len(re.findall(r"[ML][-0-9.]+,[-0-9.]+", match.group(1)))


def test_the_series_comes_from_the_CONTRACT_and_excludes_other_series() -> None:
    """The selector picks ONE of the family's nine series. Without it the chart would concatenate
    drawdown, return and volatility into one meaningless line — which is what "chart rolling_risk"
    meant before the shape was measured."""
    points, skipped = select_series(_section(_REAL)["values"], _CONTRACT)
    assert points == [
        Decimal("0.110000000000"),
        Decimal("0.130000000000"),
        Decimal("0.120000000000"),
    ]
    assert skipped == 1  # the suppressed 12m row, excluded and counted
    # THE SUBSTRING TRAP, pinned: `ROLLING_VOLATILITY:36m:2026-12-31` contains "12" and must NOT
    # be plotted. The first implementation matched substrings and mixed the two series.
    assert Decimal("0.400000000000") not in points


def test_a_SUPPRESSED_value_is_excluded_AND_DISCLOSED() -> None:
    """`rolling_risk` pins `SUPPRESSED (...)` strings and every seeded run has five. Dropping them
    silently would let the chart claim a completeness it does not have."""
    svg = render_series_chart(_section(_REAL), _CONTRACT)
    assert "data-skipped='1'" in svg
    assert "suppressed and omitted" in svg


def test_the_same_pinned_evidence_renders_BYTE_IDENTICAL_SVG() -> None:
    """The headline determinism clause."""
    a = render_series_chart(_section(_REAL), _CONTRACT)
    b = render_series_chart(_section(_REAL), _CONTRACT)
    assert a == b


def test_altering_a_BOUND_INPUT_moves_the_bytes() -> None:
    """A datapoint, and separately the contract — both are bound inputs."""
    base = render_series_chart(_section(_REAL), _CONTRACT)

    moved = list(_REAL)
    moved[1] = ("ROLLING_VOLATILITY:12m:2026-02", "0.135000000000")
    assert render_series_chart(_section(moved), _CONTRACT) != base

    # ...and a CONTRACT edit: a different selector is a different chart. This is what makes
    # "produced FROM the pinned contract" bite — a hard-coded renderer would be unmoved.
    other = {**_CONTRACT, "series_selector": {"metric_type": "MAX_DRAWDOWN", "window_months": 12}}
    assert render_series_chart(_section(_REAL), other) != base


def test_the_fragment_CARRIES_its_run_id() -> None:
    svg = render_series_chart(_section(_REAL, run_id="run-xyz"), _CONTRACT)
    assert "data-run-id='run-xyz'" in svg
    assert render_series_chart(_section(_REAL, run_id="run-other"), _CONTRACT) != svg


def test_the_fragment_contains_DECLARED_MARK_SHAPES_not_only_text() -> None:
    """REQ-PRS-002's added clause: a table drawn in SVG is not a chart.

    The guard is per-mark-type. For `path`, ONE element carries every point, so the count that
    matters is coordinate commands — the version of this proof that counted elements was
    unsatisfiable and a review said so before it shipped.
    """
    svg = render_series_chart(_section(_REAL), _CONTRACT)
    assert "<path " in svg
    assert _coord_count(svg) == 3, "the path encodes fewer commands than plotted datapoints"

    rects = render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "rect"})
    assert rects.count("<rect ") == 3

    circles = render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "circle"})
    assert circles.count("<circle ") == 3

    lines = render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "line"})
    assert lines.count("<line ") == 2  # n-1 segments for n points


def test_ZERO_datapoints_is_an_honest_empty_not_a_crash_and_not_a_blank() -> None:
    empty = [("MAX_DRAWDOWN:12m:2026-01-31", "-0.08")]  # nothing matches the selector
    svg = render_series_chart(_section(empty), _CONTRACT)
    assert "data-points='0'" in svg
    assert "no plottable values" in svg
    assert "<path" not in svg


def test_ONE_datapoint_renders_a_mark_rather_than_dividing_by_zero() -> None:
    one = [("ROLLING_VOLATILITY:12m:2026-01-31", "0.11")]
    svg = render_series_chart(_section(one), _CONTRACT)
    assert "data-points='1'" in svg
    assert _coord_count(svg) == 1


def test_a_ZERO_RANGE_series_is_flat_rather_than_a_division_by_zero() -> None:
    """Every value equal. The obvious crash, and the one a real book produces on a quiet month."""
    flat = [(f"ROLLING_VOLATILITY:12m:2026-0{i}-28", "0.12") for i in (1, 2, 3)]
    svg = render_series_chart(_section(flat), _CONTRACT)
    assert _coord_count(svg) == 3
    ys = re.findall(r"[ML][-0-9.]+,([-0-9.]+)", svg)
    assert len(set(ys)) == 1, "a flat series should render at ONE height, not scatter"


def test_NEGATIVE_values_are_plotted_over_a_min_to_max_domain() -> None:
    """Drawdowns are negative. A 0..max domain would push every point off the canvas."""
    neg = [
        ("ROLLING_VOLATILITY:12m:2026-01-31", "-0.20"),
        ("ROLLING_VOLATILITY:12m:2026-02-28", "-0.05"),
    ]
    svg = render_series_chart(_section(neg), _CONTRACT)
    ys = [Decimal(y) for y in re.findall(r"[ML][-0-9.]+,([-0-9.]+)", svg)]
    assert len(ys) == 2
    assert all(Decimal(0) <= y <= Decimal(180) for y in ys), f"points off canvas: {ys}"
    assert ys[0] != ys[1]


def test_no_FLOAT_appears_anywhere_in_the_projection() -> None:
    """Decimal only. A float round-trip would make the bytes depend on binary representation, which
    is precisely the drift a governed hash exists to catch."""
    import ast
    import pathlib

    import irp_shared.presentation.chart as chart_mod

    tree = ast.parse(pathlib.Path(chart_mod.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "float", "float() in the coordinate projection"
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            raise AssertionError(f"float literal {node.value} in the chart module")


# --- what the different-engine review found, each now a permanent control ------------------------


def test_the_marks_actually_PAINT() -> None:
    """The first implementation shipped an INVISIBLE chart and every test passed.

    `<path d='...' fill='none' />` with no stroke renders nothing at all. Every assertion in this
    file checked STRUCTURE — the element is present, the coordinate count is right — and none
    checked the marks were visible. A review rendered it and looked.
    """
    svg = render_series_chart(_section(_REAL), _CONTRACT)
    path = re.search(r"<path[^>]*>", svg).group(0)
    assert "stroke=" in path and "stroke-width=" in path, f"the path paints nothing: {path}"

    rects = render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "rect"})
    assert re.search(r"<rect[^>]*fill=", rects), "rect marks have no fill — nothing is painted"

    circles = render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "circle"})
    assert re.search(r"<circle[^>]*fill=", circles)

    lines = render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "line"})
    assert re.search(r"<line[^>]*stroke=", lines)


def test_a_SINGLE_POINT_line_is_visible_rather_than_zero_length() -> None:
    """A zero-length line paints nothing. The module's own docstring says a single point gets "a
    single mark"; an invisible one is not a mark."""
    one = [("ROLLING_VOLATILITY:12m:2026-01-31", "0.11")]
    svg = render_series_chart(_section(one), {**_CONTRACT, "mark": "line"})
    match = re.search(r"<line x1='([-0-9.]+)'[^>]*x2='([-0-9.]+)'", svg)
    assert match and match.group(1) != match.group(2), "the single-point line has zero length"


def test_a_QUOTE_in_a_pinned_field_cannot_BREAK_OUT_of_its_attribute() -> None:
    """A live injection, executed by a review against the first implementation.

    `xml.sax.saxutils.escape` handles `&`, `<` and `>` and leaves quotes alone. Every attribute here
    is single-quoted, so `x' onload='alert(1)` rendered as `data-run-id='x' onload='alert(1)'` — an
    injected event handler in a GOVERNED report, from a field read straight off a pinned snapshot.
    """
    evil = "x' onload='alert(1)"
    svg = render_series_chart(_section(_REAL, run_id=evil), _CONTRACT)
    assert "onload='alert(1)'" not in svg, f"attribute breakout: {svg[:200]}"
    assert "&apos;" in svg, "the quote was not escaped at all"
    # ...and the value is still FAITHFULLY carried, not silently stripped
    assert "onload=&apos;alert(1)" in svg

    # the same for the mark attribute, which is also interpolated
    assert "<" not in re.search(r"data-mark='([^']*)'", svg).group(1)


def test_an_UNKNOWN_mark_is_REFUSED_rather_than_drawn_as_something_else() -> None:
    """P9. `contracts.py` claimed "the renderer refuses it"; the renderer drew a line chart.

    A default here makes the declared mark decorative — a contract could name anything and get a
    line — which is the inert-declaration shape this slice exists to remove.
    """
    from irp_shared.presentation.contracts import PresentationContractError

    with pytest.raises(PresentationContractError):
        render_series_chart(_section(_REAL), {**_CONTRACT, "mark": "hexagon"})
    # ...and a MISSING mark is refused too, rather than defaulting to path
    with pytest.raises(PresentationContractError):
        render_series_chart(_section(_REAL), {k: v for k, v in _CONTRACT.items() if k != "mark"})


def test_a_NON_FINITE_pinned_value_is_SKIPPED_rather_than_crashing_the_report() -> None:
    """`Decimal("NaN")` and `Decimal("Infinity")` PARSE. They then poison every comparison and blow
    up in quantize — so one bad pin would crash the render of an entire governed report, not just
    its chart."""
    for bad in ("NaN", "Infinity", "-Infinity", "sNaN"):
        values = [("ROLLING_VOLATILITY:12m:2026-01-31", bad), *_REAL[:3]]
        svg = render_series_chart(_section(values), _CONTRACT)
        assert "data-points='3'" in svg, f"{bad} was plotted instead of skipped"
        # _REAL[:3] are the three plottable 12m points and carry no suppressed row, so the
        # non-finite value is the ONLY skipped point.
        assert "data-skipped='1'" in svg, f"{bad} was not disclosed as skipped"
