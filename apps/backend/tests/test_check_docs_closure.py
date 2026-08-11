"""API-1b (OQ-W9C-5) + the Wave-10 broadening (OQ-W10C): the closure-discipline docs-check — teeth
for the missing-stamp miss that recurred at SIX consecutive wave closes. Guards the two failure
modes the verifier (CLAIM 6) proved a naive check would hit — a slice-id in another row's PROSE, and
an in-flight planning DRAFT whose own roadmap row is not yet DONE — AND the two blind spots the
Wave-10 close found: the teeth matched only the literal "DRAFT for ratification" (PPF-3 sat at
"RATIFIED" and slipped), and the done-set keyed only on the leading `✅ **DONE**` row shape (the PPF
arc row marks each slice inline as `✅ **PPF-N**`, so all three arc slices were invisible)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

from check_docs import (  # noqa: E402
    _closure_stamp_errors,
    _done_slice_ids,
    _is_unstamped_shipped,
    _status_lines,
)


def test_done_slice_ids_are_row_anchored_not_prose() -> None:
    roadmap = "\n".join(
        [
            "| 1 | **API-1 — the read surface** ✅ **DONE** (the API-1b scope-column gap) | M |",
            "| 4 | **FE-3 — the product UI** ✅ **DONE** (the API-1b entity-read gap) | L |",
            "| 1 | **API-1b — the flagship reads** (OD-API-1-H, not yet done) | S/M |",
            "| 2 | **FE-3b — the browser login** | M |",
        ]
    )
    done = _done_slice_ids(roadmap)
    # Row-anchored: the leading bold title token of each ✅ **DONE** row is a match.
    assert {"API-1", "FE-3"} <= done
    # The CLAIM-6 trap: "API-1b" appears inside TWO ✅ **DONE** rows' prose — it must NOT be counted
    # (else CI false-fails the in-flight API-1b planning DRAFT).
    assert "API-1B" not in done
    # A row without the DONE marker is not counted (an in-flight planning DRAFT is legitimate).
    assert "FE-3B" not in done
    # The harmless extra token "DONE" (from `✅ **DONE**`) may be present — it matches no record
    # filename, so it can never false-flag; assert only that real slices are captured (superset).


def test_done_slice_ids_capture_the_arc_row_inline_marks() -> None:
    """The OQ-W10C broadening: the PPF arc row marks each slice INLINE as `✅ **PPF-N**` (never the
    leading `✅ **DONE**` row shape), so the old leading-token-only detector left all three arc
    slices out of the done-set entirely — the exact hole that let PPF-3's stamp miss slip."""
    arc = "| 3 | **X** ✅ **ALL 3 ARC SLICES DONE** ✅ **PPF-1** ✅ **PPF-2** ✅ **PPF-3** | L |"
    done = _done_slice_ids(arc)
    assert {"PPF-1", "PPF-2", "PPF-3"} <= done


def test_teeth_fire_on_a_shipped_but_unclosed_record() -> None:
    """The rule's TEETH (review finding B2 + OQ-W10C): fail iff a DONE slice's Status cell is not
    stamped CLOSED — catching ANY pre-close stamp, not just the one "DRAFT for ratification" literal
    the pre-Wave-10 teeth matched (PPF-3 sat at "RATIFIED" and slipped the sixth close)."""
    done = {"API-1", "PPF-3"}
    draft = ["| **Status** | **DRAFT for ratification (OQ-API-1-1…8)** foo |"]
    ratified = ["| **Status** | **RATIFIED by the user 2026-07-22 (OQ-PPF-3-1…4)** foo |"]
    closed = ["| **Status** | **CLOSED 2026-07-21 — DONE (PR #82 / CI #449)** foo |"]
    # DONE + still DRAFT → the miss fires (the API-1 stamp miss).
    assert _is_unstamped_shipped("API-1", draft, done) is True
    # DONE + still RATIFIED (never bumped to CLOSED) → the miss fires (the PPF-3 sixth-close miss).
    assert _is_unstamped_shipped("PPF-3", ratified, done) is True
    # DONE + stamped CLOSED → no miss.
    assert _is_unstamped_shipped("API-1", closed, done) is False
    # NOT-done (in-flight planning) + DRAFT → legitimate, no miss.
    assert _is_unstamped_shipped("API-1B", draft, done) is False
    # DONE + no Status cell at all (a pre-cadence record) → no false-fire.
    assert _is_unstamped_shipped("API-1", [], done) is False


def test_status_lines_recognize_the_prose_shape_the_wave12_records_use() -> None:
    """Wave-12 close broadening: CAD-1 and OPS-1 carry status as a `**Status:**` PROSE line and
    contain ZERO `| **Status** |` table rows — the table-only matcher silently exempted both, so
    had either shipped un-CLOSED the gate would have stayed green (the exact coverage-narrowing
    class OQ-W10C fixed on the roadmap side). Tested against the ACTUAL failure forms: the real
    prose shape at RATIFIED must FIRE, at CLOSED must not."""
    prose_ratified = ["**Status:** **RATIFIED 2026-07-25 (OQ-CAD-1-1/2/3 = A)** — implementation"]
    prose_closed = ["**Status:** **✅ CLOSED 2026-07-25 — SHIPPED (PR #125, CI green)**"]
    assert _status_lines("\n".join(prose_ratified)) == prose_ratified
    assert _is_unstamped_shipped("CAD-1", prose_ratified, {"CAD-1"}) is True
    assert _is_unstamped_shipped("CAD-1", prose_closed, {"CAD-1"}) is False
    # Prose ABOUT a prose Status line (indented/quoted mid-sentence) still does not count.
    quoting = "  the record carries a `**Status:**` line per the template."
    assert _status_lines(quoting) == []


def test_status_lines_ignore_prose_describing_a_status_line() -> None:
    """Real false-positive this check hit on itself (API-1b's own record): Part 3 quotes the rule
    verbatim — "`| **Status** |` cell contains 'DRAFT for ratification'" — which is prose ABOUT the
    rule, not an actual Status table row. Only a line STARTING WITH the table-row pattern counts."""
    text = (
        "# some record\n\n"
        "| **Status** | **CLOSED** foo |\n\n"
        "## Part 3\n"
        '  `| **Status** |` cell contains "DRAFT for ratification" AND its filename-slice maps '
        "`done=True`. This\n"
    )
    lines = _status_lines(text)
    assert len(lines) == 1  # only the real table row, not the Part-3 prose quoting it
    assert "CLOSED" in lines[0]
    assert _is_unstamped_shipped("API-1", lines, {"API-1"}) is False


def test_real_tree_has_no_unstamped_shipped_record() -> None:
    """Regression guard: every DONE slice's decision record is stamped (not left 'DRAFT for
    ratification'). This is the exact invariant the API-1 stamp miss violated before the Wave-9
    close fixed it.

    **This assertion is vacuous on its own, and the Wave-17 close proved it by execution.** An
    empty error list is what a working gate returns AND what a gate returns when its done-set no
    longer contains the slices it is supposed to police — which is the state this repository was
    in for thirteen days. The test below is what makes this one mean something; keep them adjacent.
    """
    assert _closure_stamp_errors() == []


def test_the_REAL_roadmaps_done_set_contains_the_slices_that_cannot_un_ship() -> None:
    """**The Wave-17 close's HIGH 1, as a mechanical act rather than a lesson.**

    The gate above was structurally blind from 2026-07-29 to 2026-08-11 and reported exit 0
    throughout, because ``_DONE_MARK`` was the literal ``"✅ **DONE**"`` and every roadmap row from
    Wave 14 on writes ``✅ **DONE + CLOSED <date> …**``. The leading-title branch stopped running;
    ``_TICK_SLICE`` matched ``✅ **DONE`` and added the WORD ``DONE`` to the done-set. Eleven
    shipped slices went invisible to a CI-BLOCKING gate that had been rebuilt four times for this
    exact purpose.

    Every guard that should have caught it was a SUBSET or a COUNT:

    * the tests above assert ``{"API-1", "FE-3"} <= done`` over a SYNTHETIC roadmap fixture, which
      stays true no matter what the real file says;
    * the non-vacuity floor compared 55 parsed against a floor of 38, and a set can lose every
      member that matters while staying large.

    So this test asserts membership in the REAL tree, names the slices, and covers each parser
    branch — the same correction RPT-3's audit forced one slice earlier, applied to the instrument
    that was supposed to be watching.
    """
    done = _done_slice_ids((_ROOT / "10_delivery_backlog" / "delivery_roadmap.md").read_text())

    # The `✅ **DONE + CLOSED …**` shape — the one that broke, and the one that will break next.
    assert {"REF-1", "DATA-1", "LQ-1"} <= done, (
        "the leading-title branch has stopped matching the roadmap's own row shape again"
    )
    # The Wave-10 arc's inline marks, and the Wave-13 tick-inside-the-bold shape.
    assert {"PPF-1", "PPF-3"} <= done, "the arc-style inline branch has regressed"
    assert {"SR-1", "OPS-H1"} <= done, "the tick-inside-the-bold branch has regressed"
    # And the plain early shape, so no branch is left without a witness.
    assert "API-1" in done


def test_the_witness_check_INSIDE_the_gate_actually_fires(monkeypatch) -> None:  # noqa: ANN001
    """The twin for the test above, and it was added because the battery demanded it.

    Mutant W-B2 deleted the gate's witness check and every test still passed: the test above reads
    ``_done_slice_ids`` directly, so it proves the PARSER works while saying nothing about whether
    the GATE would complain. A non-vacuity check that no test can make fire is the same inert
    control this whole fold is about — so it is asserted here through ``_closure_stamp_errors``,
    the function CI actually calls.
    """
    import check_docs

    monkeypatch.setattr(check_docs, "_MUST_PARSE_AS_DONE", frozenset({"NO-SUCH-SLICE-99"}))
    errors = check_docs._closure_stamp_errors()
    assert any("NO-SUCH-SLICE-99" in e for e in errors), (
        "the gate did not complain about a witness that cannot possibly be in the done-set — the "
        "non-vacuity check is present and inert"
    )
