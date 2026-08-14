"""The current_state.md freshness gate (housekeeping fold, 2026-08-14).

CLAUDE.md orders every session to read `current_state.md` second. On 2026-08-14 its top block was
headed `CURRENT TRUTH (2026-08-08, latest) — read this block; everything below it is HISTORY`, and
two facts inside it were wrong: its `NEXT` named a slice that had shipped as PR #191 twenty-three
merges earlier, and it claimed migration head `0068_entitlement_request` when the head was
`0070_app_role`. The block that was actually true sat a hundred lines lower, under a heading
telling the reader to treat it as history.

That was the SECOND time. The Wave-17 close had already found the class ("P1 ledger (4) went
unswept across five consecutive slice closeouts") and recorded that nothing mechanical would ever
catch it, because `test_ledger_census.py:19` leaves that ledger procedural. The fix applied then was
to append a newer block underneath the stale one, which is how it recurred within the week.

So the tests below are mostly POSITIVE controls: each one hands the gate a document that is broken
in one specific way and asserts it FIRES. A freshness gate that cannot be shown failing is worth
nothing, and this repository has shipped three controls that were written, believed and inert.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

from check_docs import (  # noqa: E402
    CURRENT_STATE,
    _actual_migration_head,
    _current_state_errors,
    _freshness_errors,
    _top_block,
    _truth_headings,
)

_HEAD = "0070_app_role"


def _doc(*blocks: str) -> str:
    """A minimal current_state.md: a title, then the given blocks in order."""
    return "# Current State\n\n" + "\n\n---\n\n".join(blocks) + "\n"


def _block(heading: str, body: str = "Body text.") -> str:
    return f"{heading}\n\n{body}"


_WELL_FORMED = _doc(
    _block(
        "## ⚠️ CURRENT TRUTH (2026-08-14) — read this block",
        f"Main `0cf3e31`. Migration head `{_HEAD}`, one head.",
    ),
    _block("## Previous truth — the Wave-17 close, 2026-08-11"),
    _block("> ## Previous truth (2026-08-08) — the Wave-17 planning gate"),
    _block("> ## Previous truth (2026-08-07, later) — RPT-2"),
    _block("> ## Prior current-truth block (2026-07-29c), kept as history"),
)


# --------------------------------------------------------------------------------------------
# The negative control: a well-formed document is silent.
# --------------------------------------------------------------------------------------------


def test_a_well_formed_document_passes() -> None:
    assert _freshness_errors(_WELL_FORMED, _HEAD) == []


def test_the_real_current_state_file_passes() -> None:
    """The gate must be green on the file as it actually stands, or it is not a gate."""
    assert _current_state_errors() == []


# --------------------------------------------------------------------------------------------
# Positive controls: one broken document each, and the gate must fire.
# --------------------------------------------------------------------------------------------


def test_a_newer_block_below_an_older_one_FAILS() -> None:
    """THE 2026-08-14 defect, in its simplest form."""
    broken = _doc(
        _block(
            "## ⚠️ CURRENT TRUTH (2026-08-08, latest) — everything below is HISTORY",
            f"Migration head `{_HEAD}`.",
        ),
        _block("## Previous truth — the re-baseline, 2026-08-12"),
        _block("> ## Previous truth (2026-08-07) — RPT-2"),
        _block("> ## Previous truth (2026-08-02) — LQ-1"),
        _block("> ## Prior current-truth block (2026-07-29c)"),
    )
    errors = _freshness_errors(broken, _HEAD)
    assert any("NEWER block sits below an OLDER one" in e for e in errors), errors
    # It must name BOTH headings, so the reader knows which two to reorder.
    assert any("2026-08-12" in e and "2026-08-08" in e for e in errors), errors


def test_two_blocks_claiming_CURRENT_TRUTH_FAILS() -> None:
    broken = _doc(
        _block("## CURRENT TRUTH (2026-08-14)", f"Migration head `{_HEAD}`."),
        _block("## CURRENT TRUTH — the re-baseline, 2026-08-12"),
        _block("> ## Previous truth (2026-08-08)"),
        _block("> ## Previous truth (2026-08-07)"),
        _block("> ## Prior current-truth block (2026-07-29c)"),
    )
    errors = _freshness_errors(broken, _HEAD)
    assert any("claim CURRENT TRUTH" in e for e in errors), errors


def test_the_CURRENT_TRUTH_block_not_being_first_FAILS() -> None:
    """A reader following CLAUDE.md acts on the first block they meet, whatever it is called."""
    broken = _doc(
        _block("## Previous truth (2026-08-14) — mislabelled", f"Migration head `{_HEAD}`."),
        _block("## CURRENT TRUTH — 2026-08-12"),
        _block("> ## Previous truth (2026-08-08)"),
        _block("> ## Previous truth (2026-08-07)"),
        _block("> ## Prior current-truth block (2026-07-29c)"),
    )
    errors = _freshness_errors(broken, _HEAD)
    assert any("not at the top of the file" in e for e in errors), errors


def test_a_stale_migration_head_claim_FAILS() -> None:
    """The other half of the 2026-08-14 defect: the block claimed 0068, the repo had 0070."""
    broken = _WELL_FORMED.replace(f"`{_HEAD}`", "`0068_entitlement_request`")
    errors = _freshness_errors(broken, _HEAD)
    assert any("0068_entitlement_request" in e and _HEAD in e for e in errors), errors


def test_a_head_claim_in_a_LOWER_block_is_not_checked() -> None:
    """History is allowed to record the head that was true when it was written. Only the CURRENT
    block makes a claim about now, so only the current block is compared."""
    doc = _WELL_FORMED.replace(
        "> ## Previous truth (2026-08-07, later) — RPT-2\n\nBody text.",
        "> ## Previous truth (2026-08-07, later) — RPT-2\n\n"
        "> Migration head `0064_entitlement_sync` at the time.",
    )
    assert _freshness_errors(doc, _HEAD) == []


def test_a_CURRENT_block_naming_no_migration_head_FAILS() -> None:
    """The non-vacuity half: with no claim there is nothing to compare, and silence would read as
    a pass."""
    broken = _WELL_FORMED.replace(f"Main `0cf3e31`. Migration head `{_HEAD}`, one head.", "Main.")
    errors = _freshness_errors(broken, _HEAD)
    assert any("names no migration head" in e for e in errors), errors


def test_an_undated_truth_heading_FAILS() -> None:
    """An undated block cannot be ordered, so it could hide any staleness behind it."""
    broken = _WELL_FORMED.replace(
        "## Previous truth — the Wave-17 close, 2026-08-11",
        "## Previous truth — the Wave-17 close",
    )
    errors = _freshness_errors(broken, _HEAD)
    assert any("carry no ISO date" in e for e in errors), errors


def test_the_vacuity_floor_FIRES_when_the_heading_shape_drifts() -> None:
    """If the matcher stops recognising headings, the gate would order an empty list and exit 0 —
    which is exactly how the closure-discipline gate in this same file guarded nothing for a wave.
    """
    unrecognisable = _doc(
        _block("## Where things stand (2026-08-14)", f"Migration head `{_HEAD}`."),
        _block("## Earlier (2026-08-11)"),
    )
    errors = _freshness_errors(unrecognisable, _HEAD)
    assert any("NON-VACUITY" in e for e in errors), errors


# --------------------------------------------------------------------------------------------
# The parsing details, each one a shape that is live in the real file today.
# --------------------------------------------------------------------------------------------


def test_a_date_with_a_disambiguating_letter_parses() -> None:
    """`2026-07-29c` — the file appends a letter when a day carries more than one block. The first
    draft of this gate used a trailing `\\b`, which does not match a digit followed by a letter, and
    it failed on this heading on its very first run."""
    headings = _truth_headings("> ## Prior current-truth block (2026-07-29c), kept as history\n")
    assert headings == [
        ("> ## Prior current-truth block (2026-07-29c), kept as history", "2026-07-29")
    ]


def test_a_block_spanning_two_days_takes_the_later_date() -> None:
    """The re-baseline heading read `2026-08-12/13`."""
    headings = _truth_headings("## CURRENT TRUTH — the product RE-BASELINE, 2026-08-12/13\n")
    assert headings[0][1] == "2026-08-12"


def test_a_trailing_date_is_found_not_just_a_parenthesised_one() -> None:
    """The Wave-17 close heading carries its date at the end of the line."""
    headings = _truth_headings("## Previous truth — swept at the Wave-17 close, 2026-08-11\n")
    assert headings[0][1] == "2026-08-11"


def test_the_top_block_stops_at_the_next_truth_heading() -> None:
    top = _top_block(_WELL_FORMED)
    assert "CURRENT TRUTH (2026-08-14)" in top
    assert "Wave-17 close" not in top


def test_the_real_file_head_claim_matches_the_repository() -> None:
    """Belt and braces on the two live inputs: the shipped file names a head, and it is the real
    one. Written as its own test so a failure says which half broke."""
    top = _top_block((_ROOT / CURRENT_STATE).read_text(encoding="utf-8"))
    assert f"`{_actual_migration_head()}`" in top
