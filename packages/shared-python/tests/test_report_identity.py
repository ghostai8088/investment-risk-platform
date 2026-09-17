"""RPT-1's identity invariants — I1, I2 and the refusals, proven by execution.

The claim REQ-RPT-001/BR-9 makes is *"report binds run IDs; regenerates identically"*. These tests
prove the strong reading of it: the report re-renders from PINNED content and is byte-identical, and
it REFUSES loudly when it cannot be.

Every refusal here fires against the LIKELY hostile input, not the easy one — the LIM-2 lesson that
cost this project a vacuous control twice (a nonexistent id 404s whether or not a fence exists; the
input that discriminates is a REAL object owned by someone else).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from irp_shared.presentation.contracts import PresentationContractError
from irp_shared.report.families import REPORT_FAMILIES, family_for
from irp_shared.report.service import (
    RENDERER_VERSION_RPT1,
    RENDERER_VERSION_RPT2,
    ReportInputError,
    canonical_known_at,
    governed_value_content,
    render_report_html,
)

_AS_OF = date(2026, 6, 30)


def _section(
    family_key: str = "concentration",
    values: list[tuple[str, str]] | None = None,
    model_code: str | None = None,
    renderer_version: str = RENDERER_VERSION_RPT1,
    presentation_contract: dict | None = None,
) -> dict:
    """One PINNED section, shaped exactly as ``governed_value_content`` produces it.

    ``model_code`` defaults to the family's first registered model. It is a parameter because the
    VaR family registers SEVEN, and a helper that silently picked one would let a test claim
    "every family renders its methodology" while exercising a seventh of the VaR family.

    **``renderer_version`` defaults to RPT-1, and that is deliberate rather than lazy.** This helper
    used to stamp the LIVE ``RENDERER_VERSION`` constant, so the moment W19-S1 bumped it every test
    here silently became an rpt-2 test — constructing sections with no presentation contract, which
    the rpt-2 renderer correctly refuses. Eight tests detonated at once. Defaulting to the OLD
    version keeps each test's subject stable across future bumps: a test about escaping should not
    change what it is testing because a renderer shipped. rpt-2 coverage is explicit, below.
    """
    fam = family_for(family_key)
    code = model_code or sorted(fam.registered_methodologies)[0]
    return {
        "family": fam.key,
        "section_title": fam.section_title,
        "model_code": code,
        "methodology_ref": fam.registered_methodologies[code],
        "model_version_id": "22222222-2222-2222-2222-222222222222",
        "source_run_id": "11111111-1111-1111-1111-111111111111",
        "source_snapshot_id": "33333333-3333-3333-3333-333333333333",
        "source_known_at": "2026-07-01T12:00:00+00:00",
        "renderer_version": renderer_version,
        "values": [
            {"metric": m, "value": v}
            for m, v in (values or [("MAX_SHARE:__SUMMARY__", "0.412300")])
        ],
        **({"presentation_contract": presentation_contract} if presentation_contract else {}),
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
    """I5 in full: model CODE, model VERSION, run, input snapshot, methodology.

    The version id is asserted because a code alone cannot tell a reader WHICH registration produced
    the number, and MG-10's change-means-a-new-version rule guarantees there will be more than one.
    """
    body = render_report_html(
        portfolio_code="P-1", as_of=_AS_OF, sections=[_section("liquidity")]
    ).body
    fam = family_for("liquidity")
    code = sorted(fam.registered_methodologies)[0]
    assert code in body
    assert fam.registered_methodologies[code] in body
    assert "11111111-1111-1111-1111-111111111111" in body, "the source run is not rendered"
    assert "22222222-2222-2222-2222-222222222222" in body, "the model VERSION is not rendered"
    assert "33333333-3333-3333-3333-333333333333" in body, "the input snapshot is not rendered"


def test_the_rendered_methodology_refs_are_the_REGISTERED_ones() -> None:
    """Guards against the report inventing a plausible-looking path.

    EVERY registered model of every family, not one per family: the VaR family declares seven, and
    a loop over families alone would have exercised one of them and reported full coverage.
    """
    seen = 0
    for fam in REPORT_FAMILIES:
        for code, ref in fam.registered_methodologies.items():
            body = render_report_html(
                portfolio_code="P-1", as_of=_AS_OF, sections=[_section(fam.key, model_code=code)]
            ).body
            assert ref in body
            assert ref.endswith(".md")
            assert code in body
            seen += 1
    # Non-vacuity floor: four families, seven VaR models plus one each.
    assert seen >= 10, f"only {seen} (family, model) pairs rendered — the registry went thin"


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


def test_the_KNOWN_AT_string_is_ENGINE_INDEPENDENT() -> None:
    """The portability defect that made the identity claim engine-dependent.

    PostgreSQL hands back ``as_of_known_at`` tz-AWARE; SQLite hands back the same instant NAIVE. The
    first version rendered ``.isoformat()`` directly, so one engine produced
    ``...T12:00:00+00:00`` and the other ``...T12:00:00`` — different BYTES, and the content hash is
    over the bytes. Found by running the I3 test, not by reading the renderer.

    Both spellings of the same instant must canonicalize to one string, and a DIFFERENT instant must
    still differ — otherwise "canonical" could be satisfied by returning a constant.
    """
    naive = datetime(2026, 7, 1, 12, 0)
    aware = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    offset = datetime(2026, 7, 1, 8, 0, tzinfo=timezone(timedelta(hours=-4)))  # the same instant
    assert canonical_known_at(naive) == canonical_known_at(aware)
    assert canonical_known_at(offset) == canonical_known_at(aware)
    later = datetime(2026, 7, 1, 12, 0, 1, tzinfo=UTC)
    assert canonical_known_at(later) != canonical_known_at(aware), "a different instant collapsed"


# --- W19-S1 (PRESENT-1): the contract is pinned, carried forward, and CONSUMED -------------------


_CONTRACT_RR = {
    "mark": "path",
    "unit": "fraction",
    "precision": 12,
    "identity": ("metric_type", "window_months"),
    "series_selector": {"metric_type": "ROLLING_VOLATILITY", "window_months": 12},
}


def _rr_values() -> list[tuple[str, str]]:
    """A rolling_risk section shaped like the real one: several series, and a SUPPRESSED row.

    Every seeded rolling_risk run has five suppressed rows, so a fixture without one would test a
    shape the platform never produces.
    """
    return [
        ("ROLLING_VOLATILITY:12m:2026-01", "0.110000000000"),
        ("ROLLING_VOLATILITY:12m:2026-02", "0.130000000000"),
        ("ROLLING_VOLATILITY:12m:2026-03", "0.120000000000"),
        ("MAX_DRAWDOWN:12m:2026-01", "-0.080000000000"),  # a DIFFERENT series, must be excluded
        ("ROLLING_VOLATILITY:36m:2026-01", "SUPPRESSED (insufficient history)"),
    ]


def test_an_RPT1_section_renders_BYTE_FOR_BYTE_as_it_always_did() -> None:
    """The dispatch's whole point: a section pinned by the old renderer is untouched by the new one.

    This is what makes "a regenerated historical report is byte-identical" structural. If the
    dispatch ever defaults an rpt-1 section into the rpt-2 path, this fails.
    """
    section = _section(renderer_version=RENDERER_VERSION_RPT1)
    body = render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[section]).body
    assert "governed-chart" not in body
    assert "class='identity'" not in body
    assert "<table>" in body  # the rpt-1 shape is still fully rendered


def test_an_RPT2_section_CONSUMES_its_pinned_contract() -> None:
    """Identity fields, unit and precision reach the BYTES. A contract that changed no bytes would
    be the inert declaration this slice exists to remove."""
    section = _section(
        family_key="rolling_risk",
        values=_rr_values(),
        renderer_version=RENDERER_VERSION_RPT2,
        presentation_contract=_CONTRACT_RR,
    )
    body = render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[section]).body
    assert "metric_type, window_months" in body  # identity fields RENDERED, not merely declared
    assert "fraction" in body and "12 dp" in body
    assert "governed-chart" in body


def test_an_RPT2_section_WITHOUT_a_contract_is_REFUSED() -> None:
    """P9 — 'a family whose contract no renderer can resolve FAILS', fired. A default here would
    reintroduce the inert declaration inside its own fix."""
    section = _section(renderer_version=RENDERER_VERSION_RPT2)  # no contract
    with pytest.raises(PresentationContractError):
        render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[section])


def test_an_UNKNOWN_renderer_version_is_REFUSED_rather_than_guessed() -> None:
    """A section pinned by a renderer this build does not have cannot be rendered as something
    else — its bytes would mean nothing."""
    section = _section(renderer_version="rpt-99-html-v1")
    with pytest.raises(PresentationContractError):
        render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[section])


def test_a_CONTRACT_EDIT_moves_NEW_bytes_and_leaves_the_OLD_ONES_ALONE() -> None:
    """BOTH HALVES, in one test, with the 'before' rendered FIRST.

    This is the clause the whole pinning design exists for. The edit is applied to the PINNED
    contract of the new section — which is what a contract edit actually does, since the contract is
    resolved at pin time — while the previously pinned section is re-rendered untouched.
    """
    before_section = _section(
        family_key="rolling_risk",
        values=_rr_values(),
        renderer_version=RENDERER_VERSION_RPT2,
        presentation_contract=_CONTRACT_RR,
    )
    before = render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[before_section])

    edited = {**_CONTRACT_RR, "precision": 4}  # the declared precision changes
    after_section = _section(
        family_key="rolling_risk",
        values=_rr_values(),
        renderer_version=RENDERER_VERSION_RPT2,
        presentation_contract=edited,
    )
    after = render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[after_section])

    assert after.content_hash != before.content_hash, (
        "a declared precision change did not move a NEW report's bytes — the contract is pinned "
        "but not consumed"
    )
    # ...and the ORIGINAL regenerates byte-identically, because it renders through ITS pin.
    again = render_report_html(portfolio_code="P", as_of=_AS_OF, sections=[before_section])
    assert again.content_hash == before.content_hash, (
        "a report generated before the edit no longer regenerates byte-identically — the render is "
        "reaching for the live contract instead of the pinned one"
    )


# --- W19-S1: the PRE-BUMP pin must not redden at verify -------------------------------------------
#
# THE proof for the BLOCKING defect the planning gate's different-engine pass found. The first
# version of this slice's plan bumped RENDERER_VERSION unconditionally; `_reresolve_content`
# re-derives a GOVERNED_VALUE component by CALLING `governed_value_content` and `verify_snapshot`
# hash-compares the result against the pin — so the bump alone would have reddened every pre-S1
# report snapshot on the platform, before any contract existed.
#
# The mechanism of the proof matters as much as the proof. A pin built through the NEW code would
# pass while real pre-S1 pins redden, so the fixture below is the LITERAL pre-S1 dict: renderer
# rpt-1, and NO `presentation_contract` key at all.


def _literal_pre_s1_pin() -> dict:
    """A section exactly as RPT-1 pinned it — written out, not generated by today's code.

    Generating it would defeat the test: the whole question is whether today's re-derivation
    reproduces bytes that were written by code that no longer exists.
    """
    return {
        "family": "concentration",
        "section_title": "Concentration",
        "model_code": "concentration.share.v1",
        "methodology_ref": "docs/methodology/concentration.md",
        "model_version_id": "22222222-2222-2222-2222-222222222222",
        "source_run_id": "11111111-1111-1111-1111-111111111111",
        "source_snapshot_id": "33333333-3333-3333-3333-333333333333",
        "source_known_at": "2026-07-01T12:00:00+00:00",
        "renderer_version": "rpt-1-html-v1",
        "values": [{"metric": "MAX_SHARE:__SUMMARY__", "value": "0.412300"}],
    }


def test_a_PRE_BUMP_pin_RE_DERIVES_to_byte_identical_content() -> None:
    """The re-derivation of a pre-S1 pin must produce the SAME bytes, key for key.

    Two failure modes, and the second is the one the `source_known_at` analogy misses:

    1. stamping the LIVE renderer version — the pin says rpt-1, the re-derive must too;
    2. emitting `presentation_contract: null` — the pin has NO such key, and `serialize_content`
       canonicalizes over sorted keys, so an extra key with a null value changes the bytes just as
       surely as a changed value would.

    Driven through `governed_value_content` with exactly the arguments `_reresolve_content` passes.
    """
    from irp_shared.snapshot.serialize import content_hash, serialize_content

    pin = _literal_pre_s1_pin()

    rederived = governed_value_content(
        family_key=pin["family"],
        section_title=pin["section_title"],
        model_code=pin["model_code"],
        methodology_ref=pin["methodology_ref"],
        model_version_id=pin["model_version_id"],
        run_id=pin["source_run_id"],
        source_snapshot_id=pin["source_snapshot_id"],
        source_known_at=pin["source_known_at"],
        values=[(v["metric"], v["value"]) for v in pin["values"]],
        # exactly what the re-derive branch passes forward from the pin
        renderer_version=str(pin["renderer_version"]),
        presentation_contract=pin.get("presentation_contract"),
    )

    assert "presentation_contract" not in rederived, (
        "the re-derivation added a presentation_contract key to a pin that never had one — "
        "serialization is exact over sorted keys, so every pre-S1 report snapshot would redden"
    )
    assert rederived["renderer_version"] == "rpt-1-html-v1"
    assert rederived == pin, f"re-derived content differs from the pin: {rederived} != {pin}"
    assert content_hash(serialize_content(rederived)) == content_hash(serialize_content(pin)), (
        "the re-derived component hashes differently from its pin — verify_snapshot would report "
        "drift on evidence nothing has touched"
    )


def test_the_REDERIVE_BRANCH_itself_carries_both_fields_forward() -> None:
    """The proof above drives `governed_value_content`; this one pins that `_reresolve_content`
    actually PASSES the pinned values to it.

    Without this, the carry-forward could be removed from the branch and the test above would still
    pass — it would be testing that the parameters work, not that anything uses them. That is the
    exact gap that let a mutant survive at W19-S3b.
    """
    import ast
    import pathlib

    import irp_shared.snapshot.service as snap

    tree = ast.parse(pathlib.Path(snap.__file__).read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "governed_value_content"
    ]
    assert calls, "the GOVERNED_VALUE re-derive branch no longer calls governed_value_content"
    for call in calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        for field in ("renderer_version", "presentation_contract"):
            assert field in kwargs, (
                f"the re-derive passes no {field} — it would stamp the LIVE value and redden every "
                f"pin made before it last changed"
            )
            source = ast.unparse(kwargs[field])
            assert "pinned" in source, (
                f"{field} is passed as {source!r}, which does not come from the pin — carrying "
                f"anything else forward re-derives a different question than the one pinned"
            )


def test_a_POST_S1_pin_also_RE_DERIVES_to_byte_identical_content() -> None:
    """The born-drifted case — the mirror of the pre-bump proof, and it fails differently.

    A report generated AFTER this slice pins `rpt-2-html-v1` AND a presentation contract. If the
    re-derive carried the renderer forward but resolved the contract LIVE, every new report snapshot
    would be born drifted the first time anyone edited a contract — and the pre-bump proof above
    would still pass, because it only exercises pins that have no contract at all.

    So both directions are asserted: a pin WITH a contract must re-derive with the SAME contract,
    not with today's.
    """
    from irp_shared.snapshot.serialize import content_hash, serialize_content

    pinned_contract = {
        "mark": "path",
        "unit": "fraction",
        "precision": 12,
        "identity": ["metric_type", "window_months"],
        "series_selector": {"metric_type": "ROLLING_VOLATILITY", "window_months": 12},
    }
    pin = {
        **_literal_pre_s1_pin(),
        "renderer_version": RENDERER_VERSION_RPT2,
        "presentation_contract": pinned_contract,
    }

    rederived = governed_value_content(
        family_key=pin["family"],
        section_title=pin["section_title"],
        model_code=pin["model_code"],
        methodology_ref=pin["methodology_ref"],
        model_version_id=pin["model_version_id"],
        run_id=pin["source_run_id"],
        source_snapshot_id=pin["source_snapshot_id"],
        source_known_at=pin["source_known_at"],
        values=[(v["metric"], v["value"]) for v in pin["values"]],
        renderer_version=str(pin["renderer_version"]),
        presentation_contract=pin.get("presentation_contract"),
    )

    assert rederived["presentation_contract"] == pinned_contract
    assert content_hash(serialize_content(rederived)) == content_hash(serialize_content(pin)), (
        "a POST-S1 pin does not re-derive to its own bytes — new report snapshots would be born "
        "drifted the first time a contract is edited"
    )

    # ...and the negative half: re-deriving with a DIFFERENT contract MUST move the bytes. Without
    # it, the assertion above would pass for a re-derive that ignored the pin entirely and happened
    # to agree with it.
    #
    # The comparison is on SERIALIZED bytes, not on Python equality, and the first version of this
    # test got that wrong: it used the live contract, asserted `live != pinned_contract` (True,
    # because `identity` is a TUPLE live and a LIST once round-tripped through JSON) and then
    # expected different hashes. JSON renders both as arrays, so the bytes were identical and the
    # test failed — correctly. A contract edit is only an edit if it survives serialization.
    live = {**pinned_contract, "precision": 4}
    assert serialize_content({"c": live}) != serialize_content({"c": pinned_contract})
    with_live = governed_value_content(
        family_key=pin["family"],
        section_title=pin["section_title"],
        model_code=pin["model_code"],
        methodology_ref=pin["methodology_ref"],
        model_version_id=pin["model_version_id"],
        run_id=pin["source_run_id"],
        source_snapshot_id=pin["source_snapshot_id"],
        source_known_at=pin["source_known_at"],
        values=[(v["metric"], v["value"]) for v in pin["values"]],
        renderer_version=str(pin["renderer_version"]),
        presentation_contract=live,
    )
    assert content_hash(serialize_content(with_live)) != content_hash(serialize_content(pin))
