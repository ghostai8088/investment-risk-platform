"""The current_state.md freshness gate (housekeeping fold, 2026-08-14).

CLAUDE.md orders every session to read `current_state.md` second. On 2026-08-14 its top block was
headed `CURRENT TRUTH (2026-08-08, latest) — read this block; everything below it is HISTORY`, and
its `NEXT` named a slice that had shipped as PR #191 twenty-three merges earlier. The block that
was actually true sat a hundred lines lower, under a heading telling the reader to treat it as
history.

That was the SECOND time. The Wave-17 close had already found the class ("P1 ledger (4) went
unswept across five consecutive slice closeouts") and recorded that nothing mechanical would ever
catch it, because `test_ledger_census.py:19` leaves that ledger procedural. The fix applied then was
to append a newer block underneath the stale one, which is how it recurred within the week.

WHAT THIS FILE LEARNED FROM ITS OWN REVIEW. The first version of these tests had twenty controls
and every one of them asserted the gate FIRES. An adversarial pass ran 24 mutants against it and
16 SURVIVED, including deleting the `main()` call outright — the gate printed "Documentation check
passed" over the real defect while all twenty tests stayed green. Two lessons are built in here:

  * `test_the_ENTRY_POINT_fails_on_a_stale_file` runs `main()`, not the internals. A control that
    only ever calls the helper cannot see the wire being cut.
  * The NEGATIVE controls below are half the file. Six false positives reached review because
    nothing asserted the gate stays QUIET on legitimate authoring, and every one of them would
    have turned CI red on an honest edit.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

from check_docs import (  # noqa: E402
    _MIN_TRUTH_HEADING_SHARE,
    _MIN_TRUTH_HEADINGS,
    _current_state_errors,
    _freshness_errors,
    _strip_fences,
    _truth_headings,
)


def _doc(*blocks: str) -> str:
    return "# Current State\n\n" + "\n\n---\n\n".join(blocks) + "\n"


def _block(heading: str, body: str = "Body text.") -> str:
    return f"{heading}\n\n{body}"


#: Nine blocks, matching the real file's shape and ordering.
def _nine(top: str = "## ⚠️ CURRENT TRUTH (2026-08-14) — read this block") -> str:
    return _doc(
        _block(top, "Main `0cf3e31`. Migration head `0070_app_role`, one head."),
        _block("## Previous truth — swept at the Wave-17 close, 2026-08-11"),
        _block("> ## Previous truth (2026-08-08) — the Wave-17 planning gate"),
        _block("> ## Previous truth (2026-08-08, earlier) — FK-1's close"),
        _block("> ## Previous truth (2026-08-08, earlier) — REPRO-1"),
        _block("> ## Previous truth (2026-08-07, later) — RPT-2"),
        _block("> ## Previous truth (2026-08-07, earlier) — RPT-1"),
        _block("> ## Previous truth (2026-08-02) — LQ-1 / Wave 14"),
        _block("> ## Prior current-truth block (2026-07-29c), kept as history"),
    )


_WELL_FORMED = _nine()


# =============================================================================================
# THE ENTRY POINT. The one control the review said it would not merge without.
# =============================================================================================


def test_the_ENTRY_POINT_fails_on_a_stale_file(tmp_path: Path) -> None:
    """`main()` must reach these rules.

    Deleting `errors.extend(_current_state_errors())` from `main()` left all twenty of the first
    version's tests green, while `scripts/check_docs.py` exited 0 over a `current_state.md`
    carrying the 2026-08-14 defect. Every test called the helpers directly, so nothing noticed the
    gate had been unplugged from the command CI actually runs. That is the inert-control class this
    repository has shipped three times.
    """
    stale = _doc(
        _block(
            "## ⚠️ CURRENT TRUTH (2026-08-08, latest) — everything below is HISTORY",
            "NEXT = the ONBOARD-1a implementation plan.",
        ),
        _block("## CURRENT TRUTH — the product RE-BASELINE, 2026-08-12"),
        _block("> ## Previous truth (2026-08-07) — RPT-2"),
    )
    target = tmp_path / "docs" / "project_memory"
    target.mkdir(parents=True)
    (target / "current_state.md").write_text(stale, encoding="utf-8")

    # The helper sees it...
    errors = _current_state_errors(root=tmp_path)
    assert any("NEWER block sits below an OLDER one" in e for e in errors), errors

    # ...and so must `main()`, which is what `make check` and CI actually run. Monkeypatching the
    # module ROOT is the whole point: with the `main()` call deleted, the assertions below fail
    # while every other test in this file still passes.
    import check_docs

    original_root = check_docs.ROOT
    try:
        check_docs.ROOT = tmp_path
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = check_docs.main()
    finally:
        check_docs.ROOT = original_root

    printed = buf.getvalue()
    assert rc == 1, f"main() returned {rc} on a stale current_state.md"
    assert "NEWER block sits below an OLDER one" in printed, printed


def test_the_entry_point_is_QUIET_on_the_real_file() -> None:
    """The gate must be green on the file as it actually stands, or it is not a gate."""
    assert _current_state_errors() == []


# =============================================================================================
# POSITIVE controls: one specifically broken document each, and the gate must fire.
# =============================================================================================


def test_a_newer_block_below_an_older_one_FAILS() -> None:
    """THE 2026-08-14 defect."""
    broken = _doc(
        _block("## ⚠️ CURRENT TRUTH (2026-08-08, latest)", "Body."),
        _block("## Previous truth — the re-baseline, 2026-08-12"),
        _block("> ## Previous truth (2026-08-07) — RPT-2"),
    )
    errors = _freshness_errors(broken)
    assert any("NEWER block sits below an OLDER one" in e for e in errors), errors
    assert any("2026-08-12" in e and "2026-08-08" in e for e in errors), errors


def test_an_inversion_DEEP_in_the_file_FAILS() -> None:
    """The walk covers every adjacent pair, not just the top one.

    Truncating the loop to `zip(headings[:1], headings[1:])` survived the entire first test suite,
    because its only inversion case put the defect in positions 1 and 2. The real file has nine
    blocks.
    """
    broken = _nine().replace(
        "> ## Previous truth (2026-08-02) — LQ-1 / Wave 14",
        "> ## Previous truth (2026-08-09) — LQ-1 / Wave 14",
    )
    errors = _freshness_errors(broken)
    assert any("NEWER block sits below an OLDER one" in e for e in errors), errors
    assert any("2026-08-09" in e for e in errors), errors


def test_a_stale_BANNER_above_the_current_block_FAILS() -> None:
    """A "read this first" banner the matcher does not recognise, sitting above everything.

    Five spellings of this passed the first version — `#`, `#####`, bold, and two rewordings — each
    carrying the 2026-08-14 defect verbatim. The gate policed the shape it knew while the file's
    actual first content was unconstrained. The fix is structural rather than a wider matcher: the
    first heading in the file must BE a truth heading.
    """
    for banner in (
        "# ⚠️ READ THIS FIRST (2026-08-08, latest)",
        "##### Where things stand",
        "## START HERE",
    ):
        broken = _nine().replace("# Current State\n", f"# Current State\n\n{banner}\n\nStale.\n", 1)
        errors = _freshness_errors(broken)
        assert any("sits above the first truth block" in e for e in errors), (banner, errors)


def test_two_blocks_claiming_CURRENT_TRUTH_FAILS() -> None:
    broken = _nine().replace(
        "## Previous truth — swept at the Wave-17 close, 2026-08-11",
        "## CURRENT TRUTH — swept at the Wave-17 close, 2026-08-11",
    )
    errors = _freshness_errors(broken)
    assert any("claim CURRENT TRUTH" in e for e in errors), errors


def test_the_CURRENT_TRUTH_block_not_being_first_FAILS() -> None:
    broken = _doc(
        _block("## Previous truth (2026-08-14) — mislabelled", "Body."),
        _block("## CURRENT TRUTH — 2026-08-12"),
        _block("> ## Previous truth (2026-08-08)"),
    )
    errors = _freshness_errors(broken)
    assert any("not the first truth block" in e for e in errors), errors


def test_no_CURRENT_TRUTH_heading_at_all_FAILS() -> None:
    broken = _nine().replace(
        "## ⚠️ CURRENT TRUTH (2026-08-14) — read this block", "## Previous truth (2026-08-14)"
    )
    errors = _freshness_errors(broken)
    assert any("no `CURRENT TRUTH` heading" in e for e in errors), errors


def test_an_undated_truth_heading_FAILS() -> None:
    broken = _nine().replace(
        "## Previous truth — swept at the Wave-17 close, 2026-08-11",
        "## Previous truth — swept at the Wave-17 close",
    )
    errors = _freshness_errors(broken)
    assert any("carry no ISO date" in e for e in errors), errors


def test_the_COUNT_floor_FIRES_when_almost_nothing_parses() -> None:
    unrecognisable = _doc(
        _block("## Where things stand (2026-08-14)", "Body."),
        _block("## Earlier (2026-08-11)"),
    )
    errors = _freshness_errors(unrecognisable)
    assert any("NON-VACUITY" in e for e in errors), errors


def test_the_SHARE_floor_FIRES_on_PARTIAL_heading_drift() -> None:
    """The realistic drift: most blocks rewritten in a shape the matcher misses, a couple left.

    A count floor cannot see this — the first version's floor of 5 was survivable down to 1 because
    its only drift case had ZERO headings parsing, which proves the floor is above zero and nothing
    more. Here 2 of 10 headings parse and the newest blocks are invisible.
    """
    drifted = _nine()
    for old, new in (
        (
            "## Previous truth — swept at the Wave-17 close, 2026-08-11",
            "## Wave-17 close (2026-08-11)",
        ),
        (
            "> ## Previous truth (2026-08-08) — the Wave-17 planning gate",
            "> ## Planning gate (2026-08-08)",
        ),
        ("> ## Previous truth (2026-08-08, earlier) — FK-1's close", "> ## FK-1 (2026-08-08)"),
        ("> ## Previous truth (2026-08-08, earlier) — REPRO-1", "> ## REPRO-1 (2026-08-08)"),
        ("> ## Previous truth (2026-08-07, later) — RPT-2", "> ## RPT-2 (2026-08-07)"),
        ("> ## Previous truth (2026-08-07, earlier) — RPT-1", "> ## RPT-1 (2026-08-07)"),
        ("> ## Previous truth (2026-08-02) — LQ-1 / Wave 14", "> ## LQ-1 (2026-08-02)"),
    ):
        drifted = drifted.replace(old, new)
    parsed = _truth_headings(drifted)
    assert len(parsed) == 2, [h for h, _, _ in parsed]
    errors = _freshness_errors(drifted)
    assert any("headings this gate recognises" in e for e in errors), errors


def test_the_floor_VALUES_are_pinned() -> None:
    """Both floors survived being moved almost anywhere in the first version, because no test
    asserted their value. These are the numbers the two cases above are built against."""
    assert _MIN_TRUTH_HEADINGS == 2
    assert _MIN_TRUTH_HEADING_SHARE == 0.30


# =============================================================================================
# NEGATIVE controls. Every one of these is legitimate authoring that the FIRST version rejected.
# =============================================================================================


def test_the_current_block_may_QUOTE_the_stale_heading_it_is_fixing() -> None:
    """This file's house style quotes the heading under discussion, in a fence. The first version
    read the quotation as a second CURRENT TRUTH heading AND as an out-of-order block — two errors
    from one citation, and the fold's own commit message does exactly this quoting."""
    doc = _nine().replace(
        "Main `0cf3e31`. Migration head `0070_app_role`, one head.",
        "The heading that shipped stale for six days, quoted verbatim:\n\n"
        "```\n"
        "## ⚠️ CURRENT TRUTH (2026-08-08, latest) — read this block; everything below is HISTORY\n"
        "```\n",
    )
    assert _freshness_errors(doc) == []


def test_a_heading_may_cite_a_SECOND_newer_date() -> None:
    """`Previous truth (2026-08-08) — superseded at the 2026-08-12 re-baseline` is the file's own
    cross-reference style. Taking `max()` of the dates on the line scored it 08-12 and fired
    against the 08-11 block above it. The heading's OWN date comes first."""
    doc = _nine().replace(
        "> ## Previous truth (2026-08-08) — the Wave-17 planning gate",
        "> ## Previous truth (2026-08-08) — superseded at the 2026-08-12 re-baseline",
    )
    assert _freshness_errors(doc) == []


def test_re_confirming_a_stale_heading_does_NOT_lift_it() -> None:
    """The other direction of the same rule, and the reason it is first-date rather than last.

    Appending "re-confirmed 2026-08-14" to a stale 2026-08-08 heading is six characters, and under
    `max()` it sorted that heading to the top and silenced the ordering check completely.
    """
    broken = _doc(
        _block("## ⚠️ CURRENT TRUTH (2026-08-08, re-confirmed 2026-08-14)", "Body."),
        _block("## Previous truth — the re-baseline, 2026-08-12"),
        _block("> ## Previous truth (2026-08-07) — RPT-2"),
    )
    errors = _freshness_errors(broken)
    assert any("NEWER block sits below an OLDER one" in e for e in errors), errors


def test_prior_current_truth_WITHOUT_the_hyphen_is_not_a_second_current_block() -> None:
    """The hyphen in `Prior current-truth` was load-bearing and nothing said so: a substring test
    on the raw line read the unhyphenated spelling as a second CURRENT TRUTH heading, and told the
    author to demote a heading that was already demoted."""
    doc = _nine().replace("Prior current-truth block", "Prior current truth block")
    assert _freshness_errors(doc) == []


def test_two_blocks_written_on_the_SAME_DAY_are_fine() -> None:
    doc = _nine().replace(
        "## Previous truth — swept at the Wave-17 close, 2026-08-11",
        "## Previous truth — a second block the same day, 2026-08-14",
    )
    assert _freshness_errors(doc) == []


def test_a_hard_WRAPPED_line_is_fine() -> None:
    """The file is hard-wrapped at ~100 columns and gets reflowed constantly."""
    doc = _nine().replace(
        "Main `0cf3e31`. Migration head `0070_app_role`, one head.",
        "Main `0cf3e31`, tree clean, CI green on all nine checks. Migration head\n"
        "`0070_app_role`, one head. Next free canonical id ENT-076.",
    )
    assert _freshness_errors(doc) == []


def test_the_current_block_may_narrate_a_PAST_migration_head() -> None:
    """The current block's whole subject can be the drift it fixed. Naming the head it drifted
    from is the natural sentence, and the first version false-failed on it."""
    doc = _nine().replace(
        "Main `0cf3e31`. Migration head `0070_app_role`, one head.",
        "Migration head `0070_app_role`. The drift this fold fixes: the top block claimed "
        "`0068_entitlement_request` for six days after the repository had moved past it.",
    )
    assert _freshness_errors(doc) == []


def test_ARCHIVING_history_down_to_two_blocks_is_fine() -> None:
    """Moving old blocks to `current_state_archive.md` is a user-ratified act (2026-07-30). The
    first version's floor of 5 hard-failed it and the message said "Fix the matcher, not the
    floor", which is the wrong instruction for that case."""
    archived = _doc(
        _block("## ⚠️ CURRENT TRUTH (2026-08-14) — read this block", "Body."),
        _block("## Previous truth — swept at the Wave-17 close, 2026-08-11"),
    )
    assert _freshness_errors(archived) == []


# =============================================================================================
# Parsing details, each a shape live in the real file today.
# =============================================================================================


def test_a_date_with_a_disambiguating_letter_parses() -> None:
    """`2026-07-29c` — the file appends a letter when a day carries more than one block. The first
    draft used a trailing `\\b`, which does not match a digit followed by a letter, and it failed
    on this heading on its very first run."""
    parsed = _truth_headings("> ## Prior current-truth block (2026-07-29c), kept as history\n")
    assert parsed[0][2] == "2026-07-29"
    assert parsed[0][1] == "PRIOR CURRENT-TRUTH"


def test_all_THREE_spelling_branches_are_recognised() -> None:
    """One witness per alternative in `_TRUTH_HEADING`, on synthetic input so that archiving the
    real file can never take a branch's only proof away with it."""
    cases = {
        "## ⚠️ CURRENT TRUTH (2026-08-14) — read this": "CURRENT TRUTH",
        "## Previous truth — the Wave-17 close, 2026-08-11": "PREVIOUS TRUTH",
        "> ## Prior current-truth block (2026-07-29c)": "PRIOR CURRENT-TRUTH",
        "> ## Prior current truth block (2026-07-29c)": "PRIOR CURRENT-TRUTH",
    }
    for line, expected in cases.items():
        parsed = _truth_headings(line + "\n")
        assert parsed, f"not recognised at all: {line}"
        assert parsed[0][1] == expected, (line, parsed[0][1])


def test_a_block_spanning_two_days_takes_its_OPENING_date() -> None:
    """The re-baseline heading read `2026-08-12/13`. Note `13` is not an ISO date, so this yields
    one date — which is why the first version's test of the same name was vacuous: a one-element
    list cannot distinguish max from min from first."""
    assert (
        _truth_headings("## CURRENT TRUTH — the RE-BASELINE, 2026-08-12/13\n")[0][2] == "2026-08-12"
    )


def test_the_FIRST_of_two_real_dates_wins_not_the_max() -> None:
    """The case the vacuous test could not reach: a heading carrying two full ISO dates."""
    line = "## Previous truth — 2026-08-11, which supersedes the 2026-08-15 draft\n"
    assert _truth_headings(line)[0][2] == "2026-08-11"


def test_a_trailing_date_is_found_not_just_a_parenthesised_one() -> None:
    assert (
        _truth_headings("## Previous truth — swept at the Wave-17 close, 2026-08-11\n")[0][2]
        == "2026-08-11"
    )


def test_fences_are_stripped_without_moving_line_numbers() -> None:
    text = "a\n```\nhidden\n```\nb\n"
    assert _strip_fences(text).splitlines() == ["a", "", "", "", "b"]


def test_the_real_file_parses_the_headings_we_think_it_does() -> None:
    """What must hold of the live file, whatever its archive depth.

    This test used to also assert `"PRIOR CURRENT-TRUTH" in kinds` and `count("PREVIOUS TRUTH")
    >= 6`. Both pinned the file's shape on 2026-08-14 rather than an invariant of it, and the
    archive shrink later the same day removed those blocks legitimately and turned the test red.
    A witness is only worth pinning if the thing it witnesses cannot go away for a GOOD reason —
    the Wave-17 close's witnesses were shipped slices, which can never un-ship, and archive depth
    is not that. The parser's three spelling branches are witnessed on synthetic input instead,
    where archiving cannot reach them (see the parsing-detail tests above).
    """
    parsed = _truth_headings(
        (_ROOT / "docs/project_memory/current_state.md").read_text(encoding="utf-8")
    )
    kinds = [k for _, k, _ in parsed]
    dates = [d for _, _, d in parsed]
    assert kinds[0] == "CURRENT TRUTH"
    assert kinds.count("CURRENT TRUTH") == 1
    assert len(parsed) >= _MIN_TRUTH_HEADINGS
    assert None not in dates
    assert dates == sorted(dates, reverse=True), dates


# =============================================================================================
# The coverage RATIO, added 2026-08-14 while doing the archive shrink the review predicted would
# trip the floor. It did — and diagnosing it found the denominator was wrong on its own terms.
# =============================================================================================


def test_ARCHIVING_down_to_two_blocks_does_not_trip_the_RATIO() -> None:
    """Archiving removes numerator and denominator together, so the ratio must be indifferent to
    it. The four trailer sections (`## Repository`, `## Re-check at session start`, ...) stay."""
    archived = _doc(
        _block("## ⚠️ CURRENT TRUTH (2026-08-14) — read this block", "Body."),
        _block("## Previous truth — swept at the Wave-17 close, 2026-08-11"),
        _block("## History archive"),
        _block("## Repository"),
        _block("## Housekeeping / security"),
        _block("## Re-check at session start"),
    )
    assert _freshness_errors(archived) == []


def test_many_SUBSECTIONS_in_the_current_block_do_not_trip_the_RATIO() -> None:
    """An `###` is a section INSIDE a block and can never be a block. Counting them diluted the
    ratio to 0.29 on twelve subsections — a false positive with nothing archived at all."""
    subsections = "\n\n".join(f"### Section {i}\n\nProse." for i in range(12))
    doc = _nine().replace("Main `0cf3e31`. Migration head `0070_app_role`, one head.", subsections)
    assert _freshness_errors(doc) == []


def test_the_ratio_STILL_FIRES_when_blocks_go_INVISIBLE() -> None:
    """The failure it exists for, and the one archiving must not be confused with: the blocks are
    still in the file, at H2, but written in a shape the matcher cannot see."""
    drifted = _nine()
    for old, new in (
        (
            "## Previous truth — swept at the Wave-17 close, 2026-08-11",
            "## Wave-17 close (2026-08-11)",
        ),
        (
            "> ## Previous truth (2026-08-08) — the Wave-17 planning gate",
            "> ## Planning gate (2026-08-08)",
        ),
        ("> ## Previous truth (2026-08-08, earlier) — FK-1's close", "> ## FK-1 (2026-08-08)"),
        ("> ## Previous truth (2026-08-08, earlier) — REPRO-1", "> ## REPRO-1 (2026-08-08)"),
        ("> ## Previous truth (2026-08-07, later) — RPT-2", "> ## RPT-2 (2026-08-07)"),
        ("> ## Previous truth (2026-08-07, earlier) — RPT-1", "> ## RPT-1 (2026-08-07)"),
        ("> ## Previous truth (2026-08-02) — LQ-1 / Wave 14", "> ## LQ-1 (2026-08-02)"),
    ):
        drifted = drifted.replace(old, new)
    errors = _freshness_errors(drifted)
    assert any("H2 headings are truth headings" in e for e in errors), errors
