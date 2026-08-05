"""RPT-1's identity invariants — I1, I2 and the refusals, proven by execution.

The claim REQ-RPT-001/BR-9 makes is *"report binds run IDs; regenerates identically"*. These tests
prove the strong reading of it: the report re-renders from PINNED content and is byte-identical, and
it REFUSES loudly when it cannot be.

Every refusal here fires against the LIKELY hostile input, not the easy one — the LIM-2 lesson that
cost this project a vacuous control twice (a nonexistent id 404s whether or not a fence exists; the
input that discriminates is a REAL object owned by someone else).
"""

from __future__ import annotations

from datetime import date

import pytest

from irp_shared.report.families import REPORT_FAMILIES, family_for
from irp_shared.report.service import (
    RENDERER_VERSION,
    ReportInputError,
    render_report_html,
)

_AS_OF = date(2026, 6, 30)


def _section(
    family_key: str = "concentration", values: list[tuple[str, str]] | None = None
) -> dict:
    fam = family_for(family_key)
    return {
        "family": fam.key,
        "section_title": fam.section_title,
        "model_code": fam.model_code,
        "methodology_ref": fam.methodology_ref,
        "source_run_id": "11111111-1111-1111-1111-111111111111",
        "renderer_version": RENDERER_VERSION,
        "values": [
            {"metric": m, "value": v}
            for m, v in (values or [("MAX_SHARE:__SUMMARY__", "0.412300")])
        ],
    }


# --- I2: byte-identical regeneration -------------------------------------------------------------


def test_the_SAME_pinned_content_renders_BYTE_IDENTICALLY(**_: object) -> None:
    """I2's core. Two renders of the same pinned content must agree exactly — not 'equivalently'."""
    first = render_report_html(portfolio_code="P-1", as_of=_AS_OF, sections=[_section()])
    second = render_report_html(portfolio_code="P-1", as_of=_AS_OF, sections=[_section()])
    assert first.body == second.body
    assert first.content_hash == second.content_hash


def test_the_render_carries_NO_wall_clock_and_no_per_render_identifier() -> None:
    """The property that MAKES I2 provable, asserted directly rather than assumed.

    A `generated_at` stamp or a per-render uuid in the body would make every regeneration differ,
    and the identity check would then be either always-failing or quietly weakened to ignore it.
    `generated_at` lives on the ROW, deliberately, not in the bytes the hash covers.
    """
    body = render_report_html(portfolio_code="P-1", as_of=_AS_OF, sections=[_section()]).body
    assert "generated_at" not in body
    # A second render a moment later is still identical — the direct check that nothing time-varying
    # leaked in (a wall-clock in the body would make these two differ).
    again = render_report_html(portfolio_code="P-1", as_of=_AS_OF, sections=[_section()]).body
    assert body == again


def test_a_CHANGED_VALUE_changes_the_hash() -> None:
    """The non-vacuity twin. Without it, a renderer that emitted a constant string would satisfy
    every identity test above — hash-equality proves reproducibility only if the hash also MOVES
    when the content does."""
    base = render_report_html(portfolio_code="P-1", as_of=_AS_OF, sections=[_section()])
    moved = render_report_html(
        portfolio_code="P-1",
        as_of=_AS_OF,
        sections=[_section(values=[("MAX_SHARE:__SUMMARY__", "0.412301")])],  # 1e-6 apart
    )
    assert (
        moved.content_hash != base.content_hash
    ), "a one-ulp value change did not move the hash — the identity check cannot detect drift"


def test_the_VALUE_IS_RENDERED_VERBATIM_never_reformatted() -> None:
    """A governed number must appear exactly as the source row carried it. Trailing zeros are
    SIGNIFICANT here: 0.410000 and 0.41 are the same quantity and a different disclosure, and the
    platform's whole Decimal discipline exists to keep that distinction."""
    body = render_report_html(
        portfolio_code="P-1",
        as_of=_AS_OF,
        sections=[_section(values=[("MAX_SHARE:__SUMMARY__", "0.410000")])],
    ).body
    assert "0.410000" in body, "the value was reformatted — a governed report may not do that"


# --- I5: provenance is rendered ------------------------------------------------------------------


def test_every_section_renders_its_model_run_and_methodology() -> None:
    """I5: a number without its provenance is not a governed number. The methodology ref rendered
    here is the one the RPT-1 census guarantees RESOLVES — which is why the pre-work had to land
    before the report could render it."""
    fam = family_for("liquidity")
    body = render_report_html(
        portfolio_code="P-1", as_of=_AS_OF, sections=[_section("liquidity")]
    ).body
    assert fam.model_code in body
    assert fam.methodology_ref in body
    assert "11111111-1111-1111-1111-111111111111" in body


def test_the_rendered_methodology_refs_are_the_REGISTERED_ones() -> None:
    """Guards against the report inventing a plausible-looking path. Every family's rendered ref is
    the constant the model registration uses, so the census over those constants transitively
    covers the report."""
    for fam in REPORT_FAMILIES:
        body = render_report_html(
            portfolio_code="P-1", as_of=_AS_OF, sections=[_section(fam.key)]
        ).body
        assert fam.methodology_ref in body
        assert fam.methodology_ref.endswith(".md")


# --- refusals (P9: each made to FIRE) ------------------------------------------------------------


def test_an_unknown_family_is_REFUSED_not_rendered_empty() -> None:
    """The vacuous-read class, refused at the registry. An unknown family returning None would
    render an EMPTY section, and 'no concentration data' is indistinguishable from 'this family
    does not exist' — the failure this platform has now hit three times."""
    with pytest.raises(ValueError, match="unknown report family"):
        family_for("concentraton")  # the typo


def test_html_is_ESCAPED_so_a_portfolio_code_cannot_inject_markup() -> None:
    """A report is an outward-facing artifact. A portfolio code is tenant-supplied data, so it is
    escaped rather than trusted — otherwise a crafted code becomes markup in a board document."""
    body = render_report_html(
        portfolio_code="<script>alert(1)</script>", as_of=_AS_OF, sections=[_section()]
    ).body
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_a_hostile_metric_name_is_also_escaped() -> None:
    """The same fence one level down: metric names come from pinned content, which came from a
    tenant's classification vocabulary. Escaping the title and not the rows would be the
    half-applied fence this session already found once."""
    body = render_report_html(
        portfolio_code="P-1",
        as_of=_AS_OF,
        sections=[_section(values=[("<img src=x onerror=1>", "0.1")])],
    ).body
    assert "<img" not in body
    assert "&lt;img" in body


def test_ReportInputError_is_a_ValueError_subclass_for_the_422_map() -> None:
    """The API error map keys on exact type; a bare ValueError would relabel a genuine server bug as
    a client 422 (the API-2 MRO trap). Subclassing keeps existing handlers intact."""
    assert issubclass(ReportInputError, ValueError)
